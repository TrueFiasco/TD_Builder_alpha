"""W2d load-time trust boundary — kb_integrity verdict + receipt lifecycle.

Hermetic (no KB, no ML deps): every KB here is a tmp_path fake. The security
property under test: pickle bytes are NEVER unpickled unless they match a
receipt entry or a pinned release-manifest hash — proven with a poison pickle
whose deserialization would create a sentinel directory.
"""
import json
import pickle
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

import kb_integrity as ki  # noqa: E402

GPICKLE = "knowledge_graph_enhanced.gpickle"
BM25 = "lexical_index/bm25.pkl"


def _fake_kb(tmp_path, name="KB"):
    kb = tmp_path / name
    (kb / "lexical_index").mkdir(parents=True)
    (kb / GPICKLE).write_bytes(pickle.dumps({"nodes": {}, "edges": []}))
    (kb / BM25).write_bytes(pickle.dumps({"bm25": None, "ids": []}))
    return kb


def _verify(kb, rel):
    p = kb / rel
    return ki.verify_pickle_bytes(p.read_bytes(), p, kb)


# -- receipt lifecycle ---------------------------------------------------------

def test_receipt_write_then_verify_ok(tmp_path):
    kb = _fake_kb(tmp_path)
    rp = ki.write_receipt(kb, source="test")
    assert rp == kb / ki.RECEIPT_NAME and rp.exists()
    receipt = json.loads(rp.read_text(encoding="utf-8"))
    assert receipt["source"] == "test"
    assert set(receipt["artifacts"]) == {GPICKLE, BM25}
    for rel in (GPICKLE, BM25):
        v = _verify(kb, rel)
        assert v.ok and v.anchor == "receipt"


def test_tampered_after_receipt_is_refused(tmp_path):
    kb = _fake_kb(tmp_path)
    ki.write_receipt(kb, source="test")
    raw = bytearray((kb / GPICKLE).read_bytes())
    raw[5] ^= 0xFF
    (kb / GPICKLE).write_bytes(bytes(raw))
    v = _verify(kb, GPICKLE)
    assert not v.ok
    assert "mismatch" in v.reason and "REFUSING" in v.reason
    assert "fetch_vector_db.py" in v.reason  # actionable fix in the error text
    # the untouched artifact still verifies
    assert _verify(kb, BM25).ok


def test_unreceipted_is_refused(tmp_path):
    kb = _fake_kb(tmp_path)  # no receipt, no reachable release manifest
    v = _verify(kb, GPICKLE)
    assert not v.ok
    assert "no integrity anchor" in v.reason and "REFUSING" in v.reason


def test_malformed_receipt_is_refused(tmp_path):
    kb = _fake_kb(tmp_path)
    (kb / ki.RECEIPT_NAME).write_text("{not json", encoding="utf-8")
    v = _verify(kb, GPICKLE)
    assert not v.ok and "malformed" in v.reason


def test_rewrite_receipt_after_rebuild(tmp_path):
    """A deliberate rebuild + re-receipt must verify again (the maintainer loop)."""
    kb = _fake_kb(tmp_path)
    ki.write_receipt(kb, source="test")
    (kb / GPICKLE).write_bytes(pickle.dumps({"nodes": {"x": {}}, "edges": []}))
    assert not _verify(kb, GPICKLE).ok          # stale receipt refuses
    ki.write_receipt(kb, source="rebuild")
    assert _verify(kb, GPICKLE).ok              # fresh receipt blesses


# -- pinned release manifest ---------------------------------------------------

def _fake_repo(tmp_path, pins):
    """<tmp>/repo/{KB,scripts/vector_db_release.json} — the standard layout."""
    repo = tmp_path / "repo"
    kb = _fake_kb(repo)
    (repo / "scripts").mkdir()
    (repo / "scripts" / "vector_db_release.json").write_text(
        json.dumps({"artifact_sha256": pins}), encoding="utf-8")
    return repo, kb


def test_manifest_pin_verifies_without_receipt(tmp_path):
    repo, kb = _fake_repo(tmp_path, {})
    pins = {rel: ki.sha256_file(kb / rel) for rel in (GPICKLE, BM25)}
    (repo / "scripts" / "vector_db_release.json").write_text(
        json.dumps({"artifact_sha256": pins}), encoding="utf-8")
    for rel in (GPICKLE, BM25):
        v = _verify(kb, rel)
        assert v.ok and v.anchor == "manifest"


def test_manifest_pin_mismatch_is_refused(tmp_path):
    repo, kb = _fake_repo(tmp_path, {GPICKLE: "0" * 64})
    v = _verify(kb, GPICKLE)
    assert not v.ok and "release manifest" in v.reason and "REFUSING" in v.reason


def test_receipt_wins_over_manifest(tmp_path):
    """Local receipt = deliberate rebuild; it outranks a disagreeing release pin."""
    repo, kb = _fake_repo(tmp_path, {GPICKLE: "0" * 64})  # pin says NO
    ki.write_receipt(kb, source="test")                   # receipt says YES
    v = _verify(kb, GPICKLE)
    assert v.ok and v.anchor == "receipt"


def test_receipt_mismatch_fails_hard_despite_good_pin(tmp_path):
    """A receipt entry that mismatches refuses immediately — it never falls
    through to a manifest pin that would have passed (changed-after-receipt
    is the tamper signal)."""
    repo, kb = _fake_repo(tmp_path, {})
    pins = {GPICKLE: ki.sha256_file(kb / GPICKLE)}
    (repo / "scripts" / "vector_db_release.json").write_text(
        json.dumps({"artifact_sha256": pins}), encoding="utf-8")
    ki.write_receipt(kb, source="test")
    stale = json.loads((kb / ki.RECEIPT_NAME).read_text(encoding="utf-8"))
    stale["artifacts"][GPICKLE]["sha256"] = "f" * 64
    (kb / ki.RECEIPT_NAME).write_text(json.dumps(stale), encoding="utf-8")
    v = _verify(kb, GPICKLE)
    assert not v.ok and ki.RECEIPT_NAME in v.reason


def test_receipt_without_entry_falls_through_to_manifest(tmp_path):
    repo, kb = _fake_repo(tmp_path, {})
    pins = {GPICKLE: ki.sha256_file(kb / GPICKLE)}
    (repo / "scripts" / "vector_db_release.json").write_text(
        json.dumps({"artifact_sha256": pins}), encoding="utf-8")
    ki.write_receipt(kb, source="test", artifacts=[BM25])  # receipt covers bm25 only
    v = _verify(kb, GPICKLE)
    assert v.ok and v.anchor == "manifest"


# -- trust override ------------------------------------------------------------

def test_trust_env_overrides_with_warning(tmp_path, monkeypatch, capsys):
    kb = _fake_kb(tmp_path)  # unreceipted — would refuse
    monkeypatch.setenv(ki.TRUST_ENV, "1")
    v = _verify(kb, GPICKLE)
    assert v.ok and v.anchor == "trust-env"
    assert ki.TRUST_ENV in capsys.readouterr().err  # loud, on stderr


def test_trust_env_off_values_do_not_override(tmp_path, monkeypatch):
    kb = _fake_kb(tmp_path)
    monkeypatch.setenv(ki.TRUST_ENV, "0")
    assert not _verify(kb, GPICKLE).ok


# -- the actual security property ----------------------------------------------

class _Poison:
    """Pickle whose DESERIALIZATION creates a sentinel dir (stand-in for ACE)."""
    sentinel: str = ""

    def __reduce__(self):
        import os
        return (os.mkdir, (self.sentinel,))


def test_refused_bytes_are_never_unpickled(tmp_path):
    kb = tmp_path / "KB"
    (kb / "lexical_index").mkdir(parents=True)
    sentinel = tmp_path / "PWNED"
    poison = _Poison()
    poison.sentinel = str(sentinel)
    (kb / BM25).write_bytes(pickle.dumps(poison))

    obj, verdict = ki.load_verified_pickle(kb / BM25, kb)
    assert obj is None and not verdict.ok
    assert not sentinel.exists()  # refusal happened BEFORE deserialization


def test_load_verified_pickle_roundtrip(tmp_path):
    kb = _fake_kb(tmp_path)
    ki.write_receipt(kb, source="test")
    obj, verdict = ki.load_verified_pickle(kb / GPICKLE, kb)
    assert verdict.ok and obj == {"nodes": {}, "edges": []}

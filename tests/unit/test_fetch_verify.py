"""W2d — fetch_vector_db.py verifies BEFORE extracting, on BOTH download paths.

Hermetic: downloads are stubbed (no network, no gh); the "release zip" is
built in tmp. Locks in the fetch-side half of the trust boundary:
  - zip sha256 mismatch -> SystemExit with NOTHING extracted (HTTPS and gh);
  - artifact pins checked after extract (publishing-skew tripwire);
  - a receipt is written for the verified extraction.
"""
import hashlib
import importlib.util
import json
import shutil
import sys
import zipfile
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


@pytest.fixture()
def fetch(monkeypatch, tmp_path):
    """A fresh fetch_vector_db module wired to a tmp repo layout."""
    spec = importlib.util.spec_from_file_location(
        "_w2d_fetch", str(_REPO_ROOT / "scripts" / "fetch_vector_db.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_w2d_fetch"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "KB_DIR", tmp_path / "KB")
    monkeypatch.setattr(mod, "MANIFEST", tmp_path / "vector_db_release.json")
    monkeypatch.setattr(mod, "_kb_integrity", lambda: ki)
    return mod


def _make_zip(tmp_path) -> tuple[Path, dict]:
    """Build a fake release zip; return (zip_path, correct artifact pins)."""
    src = tmp_path / "zip_src"
    (src / "lexical_index").mkdir(parents=True)
    (src / GPICKLE).write_bytes(b"graph-bytes-v1")
    (src / BM25).write_bytes(b"bm25-bytes-v1")
    zp = tmp_path / "kb.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.write(src / GPICKLE, GPICKLE)
        zf.write(src / BM25, BM25)
    pins = {GPICKLE: hashlib.sha256(b"graph-bytes-v1").hexdigest(),
            BM25: hashlib.sha256(b"bm25-bytes-v1").hexdigest()}
    return zp, pins


def _manifest(fetch, zp: Path, pins=None, sha=None):
    m = {"repo": "x/y", "tag": "vT", "asset": "kb.zip",
         "sha256": sha if sha is not None else ki.sha256_file(zp)}
    if pins is not None:
        m["artifact_sha256"] = pins
    fetch.MANIFEST.write_text(json.dumps(m), encoding="utf-8")


def _stub_https(fetch, monkeypatch, zp: Path, succeed=True):
    calls = []

    def fake(url, dest):
        calls.append(url)
        if succeed:
            shutil.copyfile(zp, dest)
        return succeed

    monkeypatch.setattr(fetch, "_download_https", fake)
    return calls


def _stub_gh(fetch, monkeypatch, zp: Path, succeed=True):
    calls = []

    def fake(repo, tag, asset, out_dir):
        calls.append((repo, tag, asset))
        if succeed:
            shutil.copyfile(zp, Path(out_dir) / asset)
        return succeed

    monkeypatch.setattr(fetch, "_download_gh", fake)
    return calls


def test_https_good_sha_extracts_and_receipts(fetch, monkeypatch, tmp_path, capsys):
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins)
    _stub_https(fetch, monkeypatch, zp)
    assert fetch.main() == 0
    assert (fetch.KB_DIR / GPICKLE).exists() and (fetch.KB_DIR / BM25).exists()
    out = capsys.readouterr().out
    assert "SHA256 verified" in out and "Artifact pins verified" in out
    receipt = json.loads((fetch.KB_DIR / ki.RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt["source"] == "fetch_vector_db"
    assert receipt["artifacts"][GPICKLE]["sha256"] == pins[GPICKLE]


def test_https_bad_sha_refuses_before_extract(fetch, monkeypatch, tmp_path):
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins, sha="0" * 64)
    _stub_https(fetch, monkeypatch, zp)
    with pytest.raises(SystemExit) as exc:
        fetch.main()
    assert "SHA256 mismatch" in str(exc.value)
    assert not (fetch.KB_DIR / GPICKLE).exists()   # nothing extracted
    assert not (fetch.KB_DIR / ki.RECEIPT_NAME).exists()


def test_gh_fallback_good_sha_extracts_and_receipts(fetch, monkeypatch, tmp_path):
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins)
    _stub_https(fetch, monkeypatch, zp, succeed=False)
    gh_calls = _stub_gh(fetch, monkeypatch, zp)
    assert fetch.main() == 0
    assert gh_calls == [("x/y", "vT", "kb.zip")]
    assert (fetch.KB_DIR / GPICKLE).exists()
    assert (fetch.KB_DIR / ki.RECEIPT_NAME).exists()


def test_gh_fallback_bad_sha_refuses_before_extract(fetch, monkeypatch, tmp_path):
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins, sha="f" * 64)
    _stub_https(fetch, monkeypatch, zp, succeed=False)
    _stub_gh(fetch, monkeypatch, zp)
    with pytest.raises(SystemExit) as exc:
        fetch.main()
    assert "SHA256 mismatch" in str(exc.value)
    assert not (fetch.KB_DIR / GPICKLE).exists()


def test_artifact_pin_skew_fails_loud_and_unreceipted(fetch, monkeypatch, tmp_path):
    """Zip verifies but a pin disagrees = the manifest and the published zip
    drifted (publishing mistake). Fail the fetch; leave no receipt behind."""
    zp, pins = _make_zip(tmp_path)
    pins[BM25] = "a" * 64
    _manifest(fetch, zp, pins)
    _stub_https(fetch, monkeypatch, zp)
    with pytest.raises(SystemExit) as exc:
        fetch.main()
    assert "pin mismatch" in str(exc.value)
    assert not (fetch.KB_DIR / ki.RECEIPT_NAME).exists()


def test_no_pins_warns_but_receipts(fetch, monkeypatch, tmp_path, capsys):
    """Older manifest without artifact_sha256: fetch still succeeds and the
    receipt becomes the only load-time anchor."""
    zp, _ = _make_zip(tmp_path)
    _manifest(fetch, zp, pins=None)
    _stub_https(fetch, monkeypatch, zp)
    assert fetch.main() == 0
    assert "no artifact_sha256 pins" in capsys.readouterr().out
    assert (fetch.KB_DIR / ki.RECEIPT_NAME).exists()

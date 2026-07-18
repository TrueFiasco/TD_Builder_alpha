"""A8/AN1/BM1 — the ingest regime-rewrite guard, hermetic units.

Runs in the KB-free CI lane: every test here exercises code paths that stop
BEFORE `_open_user_collection` (chromadb) or `_load_embedder` (sentence-
transformers), so no heavy deps and no fetched KB are needed. The end-to-end
"silent-heal is dead" proof (real store + boot guard) lives in the requires_kb
lane at tests/retrieval_user/test_user_store.py.

Covers:
  * A8   — ingest_incremental refuses a regime CHANGE before any write; the
           manifest is byte-unchanged and the vector_db is never created.
  * A8   — first-ingest and regime-unchanged are allowed (guard is a no-op);
           reindex's allow_regime_change flag is honoured only on an EMPTY store.
  * AN1  — _manifest_regime_or_current resolves all-or-nothing (never a mixed
           regime); _regime_differs mirrors the boot guard's three-field compare.
  * BM1  — the CLI --reindex-all / --remove flags invoke the engine internals.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from kb_build import user_components as uc  # noqa: E402


# regime fixtures ------------------------------------------------------------
X = {"model_id": "all-MiniLM-L6-v2", "normalize": False, "query_prefix": ""}
Y = {"model_id": "bge-large-en-v1.5", "normalize": True, "query_prefix": "query: "}


def _seed_manifest(user_dir: Path, regime: dict, *, hashes=None) -> Path:
    """Write a user_index/manifest.json recording `regime` (mirrors the shape
    _write_user_manifest emits) and return its path."""
    mp = user_dir / "user_index" / "manifest.json"
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps({
        "embedding_model": regime["model_id"],
        "normalize": bool(regime["normalize"]),
        "query_prefix": regime["query_prefix"] or "",
        "collection": "td_unified",
        "semantic_hash": dict(hashes or {"seedComp": "h0"}),
    }, indent=2) + "\n", encoding="utf-8")
    return mp


class _ExplodingModel:
    """A passage embedder that must never be reached on a refused ingest."""
    def encode(self, *a, **k):  # noqa: D401
        raise AssertionError("embedding ran on a refused ingest — guard too late")


def _row(name="seedComp"):
    return {"id": f"user:block:{name}:overview", "text": "x",
            "meta": {"name": name}}


# ---------------------------------------------------------------------------
# _regime_differs — mirrors retrieval_stack's user-store health check exactly
# ---------------------------------------------------------------------------
def test_regime_differs_matches_boot_guard_three_fields():
    same = {"embedding_model": "all-MiniLM-L6-v2", "normalize": False,
            "query_prefix": ""}
    assert uc._regime_differs(same, X) is False
    # case-only model difference is NOT a mismatch (HF ids are case-insensitive)
    assert uc._regime_differs({**same, "embedding_model": "all-minilm-l6-v2"}, X) \
        is False
    # each of the three fields, alone, is a mismatch
    assert uc._regime_differs({**same, "embedding_model": "bge-large-en-v1.5"}, X)
    assert uc._regime_differs({**same, "normalize": True}, X)
    assert uc._regime_differs({**same, "query_prefix": "query: "}, X)


# ---------------------------------------------------------------------------
# AN1 — _manifest_regime_or_current resolves all-or-nothing
# ---------------------------------------------------------------------------
def test_manifest_regime_preserved_when_complete(monkeypatch):
    monkeypatch.setattr(uc, "_resolve_user_regime",
                        lambda: {"model_id": "SHOULD-NOT-BE-USED",
                                 "normalize": True, "query_prefix": "q: "})
    man = {"embedding_model": "all-MiniLM-L6-v2", "normalize": False,
           "query_prefix": ""}
    got = uc._manifest_regime_or_current(man)
    assert got == {"model_id": "all-MiniLM-L6-v2", "normalize": False,
                   "query_prefix": ""}


def test_manifest_regime_falls_back_as_a_unit_when_incomplete(monkeypatch):
    """AN1: a manifest missing normalize/query_prefix must NOT pair its stored
    model_id with defaulted flags — it falls back to the current regime WHOLE."""
    current = {"model_id": "cur-model", "normalize": True, "query_prefix": "q: "}
    monkeypatch.setattr(uc, "_resolve_user_regime", lambda: current)
    # model_id present but the other two fields absent -> whole-unit fallback,
    # never {"model_id": "all-MiniLM-L6-v2", "normalize": False, ...} (the mix).
    got = uc._manifest_regime_or_current({"embedding_model": "all-MiniLM-L6-v2"})
    assert got == current


# ---------------------------------------------------------------------------
# A8 — _guard_regime_change: refuse-hard on an unauthorised regime change
# ---------------------------------------------------------------------------
def test_guard_no_manifest_is_first_ingest(monkeypatch, tmp_path):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    monkeypatch.setattr(uc, "_resolve_user_regime", lambda: Y)
    uc._guard_regime_change(Y, allow_regime_change=False)  # no raise


def test_guard_same_regime_is_noop(monkeypatch, tmp_path):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    _seed_manifest(tmp_path, X)
    monkeypatch.setattr(uc, "_resolve_user_regime", lambda: X)
    uc._guard_regime_change(X, allow_regime_change=False)  # no raise


def test_guard_refuses_regime_change_without_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    _seed_manifest(tmp_path, X)
    monkeypatch.setattr(uc, "_resolve_user_regime", lambda: Y)
    with pytest.raises(uc.UserComponentError) as ei:
        uc._guard_regime_change(Y, allow_regime_change=False)
    assert ei.value.kind == "regime_mismatch"
    assert "reindex" in str(ei.value).lower()  # remedy is named


def test_guard_flag_allows_change_only_on_empty_store(monkeypatch, tmp_path):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    _seed_manifest(tmp_path, X)
    monkeypatch.setattr(uc, "_resolve_user_regime", lambda: Y)
    # empty store -> the authorised reindex path is allowed
    monkeypatch.setattr(uc, "_user_store_vector_count", lambda: 0)
    uc._guard_regime_change(Y, allow_regime_change=True)  # no raise
    # non-empty store -> even WITH the flag, refuse (defense in depth)
    monkeypatch.setattr(uc, "_user_store_vector_count", lambda: 5)
    with pytest.raises(uc.UserComponentError) as ei:
        uc._guard_regime_change(Y, allow_regime_change=True)
    assert ei.value.kind == "regime_mismatch"


# ---------------------------------------------------------------------------
# A8 — ingest_incremental refuses BEFORE any write (manifest + vector_db intact)
# ---------------------------------------------------------------------------
def test_ingest_refuses_regime_change_no_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    mp = _seed_manifest(tmp_path, X)
    before = mp.read_bytes()
    monkeypatch.setattr(uc, "_resolve_user_regime", lambda: Y)

    with pytest.raises(uc.UserComponentError) as ei:
        uc.ingest_incremental([_row()], {"seedComp": "h1"},
                              model=_ExplodingModel())
    assert ei.value.kind == "regime_mismatch"
    # manifest byte-identical; the vector store was never even created
    assert mp.read_bytes() == before
    assert not (tmp_path / "user_index" / "vector_db").exists()


def test_ingest_refusal_surfaces_kind_for_the_mcp_handler(monkeypatch, tmp_path):
    """The register_component handler does _reg_err(getattr(e,'kind',...), str(e))
    — the refusal must carry the machine-readable kind, not a bare Exception."""
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    _seed_manifest(tmp_path, X)
    monkeypatch.setattr(uc, "_resolve_user_regime", lambda: Y)
    with pytest.raises(uc.UserComponentError) as ei:
        uc.ingest_incremental([_row()], {"seedComp": "h1"}, model=_ExplodingModel())
    assert getattr(ei.value, "kind", None) == "regime_mismatch"


# ---------------------------------------------------------------------------
# BM1 — the CLI --reindex-all / --remove flags invoke the engine internals
# ---------------------------------------------------------------------------
@pytest.fixture()
def rcli():
    import importlib
    mod = importlib.import_module("kb_build.register_user_component")
    return mod


def test_cli_reindex_all_invokes_engine(rcli, monkeypatch):
    calls = []
    monkeypatch.setattr(rcli, "reindex_all",
                        lambda **kw: calls.append(kw) or {"components": 0, "chunks": 0})
    rc = rcli.main(["--reindex-all"])
    assert rc == 0 and len(calls) == 1


def test_cli_remove_invokes_engine(rcli, monkeypatch):
    calls = []
    monkeypatch.setattr(rcli, "remove_component",
                        lambda name, **kw: calls.append(name) or
                        {"name": name, "removed_from_registry": True,
                         "chunks_deleted": True})
    rc = rcli.main(["--remove", "glowPulse"])
    assert rc == 0 and calls == ["glowPulse"]


def test_cli_modes_reject_a_stray_tox(rcli):
    assert rcli.main(["--reindex-all", "some.tox"]) == 2


def test_cli_modes_are_mutually_exclusive(rcli):
    assert rcli.main(["--reindex-all", "--remove", "x"]) == 2

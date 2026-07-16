"""KB health gate — an empty-but-present vector_db must never report "ready".

Guards the trap this machine actually hit: `KB/vector_db/` exists, Chroma loads
it "successfully", and `hybrid_search` returns empty `semantic_results` forever
while every gate said the KB was fine. The gate lives in `_load_kb` (dense
document count), the repair message is composed at runtime from
`scripts/vector_db_release.json` (never hardcoded release strings), and health
is surfaced via `get_server_info` + a `kb_health` advisory block appended to
KB-dependent tool responses while the KB is partial (owner D1/D3, 2026-07-16).

Fully hermetic: no real KB, no chromadb, no network — mcp_server imports
KB-free (the graph/search load lazily), and everything heavy is faked at the
module-global seams `_load_kb` actually uses.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "MCP" / "server_core"))

import mcp_server as srv  # noqa: E402

# Import-time defaults of the KB state machine; restored around every test so
# _load_kb's direct global writes never leak between tests (or into other
# test modules sharing the imported module object).
_BASELINE = {
    "_KB_STATUS": "pending",
    "_KB_REASON": "",
    "_DENSE_COUNT": None,
    "knowledge_graph": None,
    "hybrid_search": None,
}

_SYNTH_MANIFEST = {"repo": "acme/widgets", "tag": "v9.9.9", "asset": "kb_test.zip"}
_SYNTH_URL = "https://github.com/acme/widgets/releases/download/v9.9.9/kb_test.zip"
_SYNTH_RELEASE_PAGE = "https://github.com/acme/widgets/releases/tag/v9.9.9"


@pytest.fixture(autouse=True)
def _kb_state_reset():
    for k, v in _BASELINE.items():
        setattr(srv, k, v)
    yield
    for k, v in _BASELINE.items():
        setattr(srv, k, v)


class _FakeGraph:
    """Stands in for UnifiedGraphQuery — only `.nodes` is touched by _load_kb."""

    def __init__(self, **_kw):
        self.nodes = ["opA", "opB"]


def _adapter_factory(doc_count):
    def _make(**_kw):
        return SimpleNamespace(vector_search=SimpleNamespace(doc_count=doc_count))
    return _make


def _boom_adapter(**_kw):
    raise RuntimeError("Collection td_unified does not exist")


def _wire_kb(monkeypatch, tmp_path, *, gpickle=True, vdb=True,
             adapter=None, manifest=_SYNTH_MANIFEST):
    """Point every path/class global _load_kb uses at a tmp fixture tree."""
    kb = tmp_path / "KB"
    kb.mkdir(exist_ok=True)
    gp = kb / "knowledge_graph_enhanced.gpickle"
    if gpickle:
        gp.write_bytes(b"fake-gpickle")
    vdb_dir = kb / "vector_db"
    if vdb:
        vdb_dir.mkdir(exist_ok=True)
    if manifest is not None:
        sdir = tmp_path / "scripts"
        sdir.mkdir(exist_ok=True)
        (sdir / "vector_db_release.json").write_text(
            json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(srv, "_RELEASE_ROOT", tmp_path)
    monkeypatch.setattr(srv, "enhanced_graph_path", gp)
    monkeypatch.setattr(srv, "graphrag_json_path", kb / "graphrag.json")
    monkeypatch.setattr(srv, "enriched_wiki_path", kb / "operators.json")
    monkeypatch.setattr(srv, "vectordb_path", vdb_dir)
    monkeypatch.setattr(srv, "UnifiedGraphQuery", _FakeGraph)
    monkeypatch.setattr(srv, "UnifiedSearchAdapter",
                        adapter if adapter is not None else _adapter_factory(1234))
    return vdb_dir


# ---------------------------------------------------------------------------
# _load_kb state machine
# ---------------------------------------------------------------------------

def test_empty_vector_db_goes_partial_with_repair_message(monkeypatch, tmp_path):
    vdb_dir = _wire_kb(monkeypatch, tmp_path, adapter=_adapter_factory(0))
    srv._load_kb()
    assert srv._KB_STATUS == "partial"
    assert srv.hybrid_search is None            # documented partial invariant
    assert srv._DENSE_COUNT == 0                # measured empty, not "unknown"
    assert "EMPTY" in srv._KB_REASON
    assert str(vdb_dir) in srv._KB_REASON
    assert "python scripts/fetch_vector_db.py" in srv._KB_REASON
    assert _SYNTH_URL in srv._KB_REASON         # manifest-derived, not hardcoded


def test_healthy_kb_is_ready_and_counts_documents(monkeypatch, tmp_path):
    _wire_kb(monkeypatch, tmp_path, adapter=_adapter_factory(1234))
    srv._load_kb()
    assert srv._KB_STATUS == "ready"
    assert srv._KB_REASON == ""
    assert srv._DENSE_COUNT == 1234
    assert srv.hybrid_search is not None
    assert srv.hybrid_search.vector_search.doc_count == 1234


def test_missing_vector_db_dir_goes_partial_with_repair_message(monkeypatch, tmp_path):
    _wire_kb(monkeypatch, tmp_path, vdb=False)
    srv._load_kb()
    assert srv._KB_STATUS == "partial"
    assert srv._DENSE_COUNT is None             # never measured
    assert srv.hybrid_search is None
    assert "vector DB missing" in srv._KB_REASON
    assert "python scripts/fetch_vector_db.py" in srv._KB_REASON
    assert _SYNTH_URL in srv._KB_REASON


def test_missing_gpickle_goes_failed_with_repair_message(monkeypatch, tmp_path):
    _wire_kb(monkeypatch, tmp_path, gpickle=False)
    srv._load_kb()
    assert srv._KB_STATUS == "failed"
    assert "Knowledge graph file not found" in srv._KB_REASON
    assert "python scripts/fetch_vector_db.py" in srv._KB_REASON
    assert _SYNTH_URL in srv._KB_REASON


def test_adapter_init_error_goes_partial_with_repair_message(monkeypatch, tmp_path):
    _wire_kb(monkeypatch, tmp_path, adapter=_boom_adapter)
    srv._load_kb()
    assert srv._KB_STATUS == "partial"
    assert srv.hybrid_search is None
    assert srv._DENSE_COUNT is None
    assert "Collection td_unified does not exist" in srv._KB_REASON
    assert "python scripts/fetch_vector_db.py" in srv._KB_REASON


# ---------------------------------------------------------------------------
# The repair-message composer
# ---------------------------------------------------------------------------

def test_repair_message_derives_url_from_manifest(monkeypatch, tmp_path):
    _wire_kb(monkeypatch, tmp_path)
    msg = srv._kb_repair_message("problem line")
    assert msg.splitlines()[0] == "problem line"
    assert _SYNTH_URL in msg
    assert _SYNTH_RELEASE_PAGE in msg
    assert "kb_test.zip" in msg


def test_repair_message_fix_line_comes_first(monkeypatch, tmp_path):
    # Clip-resistance: even a truncated preview of the reason must show the fix.
    _wire_kb(monkeypatch, tmp_path)
    lines = srv._kb_repair_message("problem line").splitlines()
    assert lines[1].startswith("Fix: run")
    assert "python scripts/fetch_vector_db.py" in lines[1]


def test_repair_message_honors_explicit_url_override(monkeypatch, tmp_path):
    manifest = dict(_SYNTH_MANIFEST, url="https://mirror.example/kb.zip")
    _wire_kb(monkeypatch, tmp_path, manifest=manifest)
    msg = srv._kb_repair_message("problem")
    assert "https://mirror.example/kb.zip" in msg
    assert _SYNTH_URL not in msg


def test_repair_message_missing_manifest_falls_back_generic(monkeypatch, tmp_path):
    _wire_kb(monkeypatch, tmp_path, manifest=None)
    msg = srv._kb_repair_message("problem")
    assert "python scripts/fetch_vector_db.py" in msg
    assert "github.com" not in msg              # no invented coordinates


def test_repair_message_pinned_to_real_manifest(monkeypatch):
    """A manifest key rename must break THIS test, not the runtime message.

    _RELEASE_ROOT is pinned to this checkout explicitly so an inherited
    TD_BUILDER_ROOT (relocated install) can't swap the manifest under us.
    """
    monkeypatch.setattr(srv, "_RELEASE_ROOT", REPO)
    manifest = json.loads(
        (REPO / "scripts" / "vector_db_release.json").read_text(encoding="utf-8"))
    msg = srv._kb_repair_message("problem")
    assert manifest["asset"] in msg
    assert f"https://github.com/{manifest['repo']}/releases/tag/{manifest['tag']}" in msg
    expected_url = manifest.get("url") or (
        f"https://github.com/{manifest['repo']}/releases/download/"
        f"{manifest['tag']}/{manifest['asset']}")
    assert expected_url in msg


# ---------------------------------------------------------------------------
# Delivery: _kb_check + the dispatcher advisory (owner D1)
# ---------------------------------------------------------------------------

def test_kb_check_partial_blocks_semantic_with_reason():
    srv._KB_STATUS = "partial"
    srv._KB_REASON = "the repair message"
    err = srv._kb_check(needs_semantic=True)
    assert err["status"] == "kb_partial"
    assert err["message"] == "the repair message"
    assert srv._kb_check(needs_semantic=False) is None  # graph tools proceed


def test_partial_appends_kb_health_advisory_to_graph_tool():
    srv._KB_STATUS = "partial"
    srv._KB_REASON = "the repair message"
    srv.knowledge_graph = SimpleNamespace()      # truthy; early-arg-error path
    res = asyncio.run(srv.call_tool("query_graph", {"command": "params"}))
    assert len(res) == 2                         # payload + advisory
    advisory = json.loads(res[1].text)
    assert advisory["kb_health"]["status"] == "kb_partial"
    assert advisory["kb_health"]["message"] == "the repair message"


def test_ready_appends_no_advisory():
    srv._KB_STATUS = "ready"
    srv.knowledge_graph = SimpleNamespace()
    res = asyncio.run(srv.call_tool("query_graph", {"command": "params"}))
    assert len(res) == 1


def test_partial_hybrid_search_is_blocked_without_duplicate_advisory():
    srv._KB_STATUS = "partial"
    srv._KB_REASON = "the repair message"
    res = asyncio.run(srv.call_tool("hybrid_search", {"query": "noise"}))
    assert len(res) == 1                         # gate error only, no append
    payload = json.loads(res[0].text)
    assert payload["ok"] is False
    assert payload["error"]["status"] == "kb_partial"
    assert payload["error"]["message"] == "the repair message"


# ---------------------------------------------------------------------------
# get_server_info health fields (owner D3)
# ---------------------------------------------------------------------------

def _server_info(res):
    assert len(res) == 1  # health rides fields here, never the advisory block
    return json.loads(res[0].text)["data"]


def test_get_server_info_healthy_fields(monkeypatch, tmp_path):
    vdb_dir = tmp_path / "vector_db"
    vdb_dir.mkdir()
    monkeypatch.setattr(srv, "vectordb_path", vdb_dir)
    srv._KB_STATUS = "ready"
    srv._DENSE_COUNT = 4321
    srv.hybrid_search = SimpleNamespace(
        retrieval_stack=SimpleNamespace(_reranker=object(), _bm25=object()))
    data = _server_info(asyncio.run(srv.call_tool("get_server_info", {})))
    assert data["kb_status"] == "ready"
    assert data["kb_reason"] is None
    assert data["retrieval_backend"]["dense_count"] == 4321
    assert data["retrieval_backend"]["vector_db_present"] is True
    assert data["retrieval_backend"]["reranker_active"] is True
    assert data["retrieval_backend"]["bm25_active"] is True


def test_get_server_info_partial_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "vectordb_path", tmp_path / "nope")
    srv._KB_STATUS = "partial"
    srv._KB_REASON = "the repair message"
    srv._DENSE_COUNT = 0
    data = _server_info(asyncio.run(srv.call_tool("get_server_info", {})))
    assert data["kb_status"] == "partial"
    assert data["kb_reason"] == "the repair message"
    assert data["retrieval_backend"]["dense_count"] == 0
    assert data["retrieval_backend"]["vector_db_present"] is False


def test_get_server_info_pending_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "vectordb_path", tmp_path / "nope")
    data = _server_info(asyncio.run(srv.call_tool("get_server_info", {})))
    assert data["kb_status"] == "pending"
    assert data["kb_reason"] is None
    assert data["retrieval_backend"]["dense_count"] is None
    assert data["retrieval_backend"]["vector_db_present"] is False

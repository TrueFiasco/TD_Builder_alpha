"""Exact KB lookups answer as soon as the graph is loaded, not after search warm-up.

`_load_kb` has two halves: the knowledge graph (seconds) and the search stack
(embedding model + vector store + reranker; minutes on a cold machine). A long
real-world build lost one exact lookup in four to "still loading" answers that
were only waiting on the second half. These tests hold the loader between its
two halves and check what each kind of tool answers in that window.

Hermetic: the graph and the search adapter are faked at the module-global seams
`_load_kb` uses; the adapter blocks on an Event so the window is deterministic.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "MCP" / "server_core"))

import mcp_server as srv  # noqa: E402

_BASELINE = {
    "_KB_STATUS": "pending",
    "_KB_REASON": "",
    "_DENSE_COUNT": None,
    "knowledge_graph": None,
    "hybrid_search": None,
}


@pytest.fixture(autouse=True)
def _kb_state_reset():
    for k, v in _BASELINE.items():
        setattr(srv, k, v)
    yield
    for k, v in _BASELINE.items():
        setattr(srv, k, v)


class _FakeGraph:
    """Just enough UnifiedGraphQuery for `_load_kb` and `get_operator_info`."""

    def __init__(self, **_kw):
        self.nodes = ["noiseTOP"]

    def get_operator_info(self, name):
        if name.lower() != "noise top":
            return None
        return {"name": "Noise TOP", "family": "TOP", "summary": "Noise.",
                "wiki_parameters": {"amp": {"type": "float", "description": "Amplitude."}}}


@pytest.fixture
def held_loader(monkeypatch, tmp_path):
    """Run `_load_kb` on a thread and park it after the graph half.

    Yields once the graph is published; releasing `gate` lets the search half
    finish (healthy, 1234 documents)."""
    kb = tmp_path / "KB"
    (kb / "vector_db").mkdir(parents=True)
    gp = kb / "knowledge_graph_enhanced.gpickle"
    gp.write_bytes(b"fake")
    monkeypatch.setattr(srv, "enhanced_graph_path", gp)
    monkeypatch.setattr(srv, "graphrag_json_path", kb / "graphrag.json")
    monkeypatch.setattr(srv, "enriched_wiki_path", kb / "operators.json")
    monkeypatch.setattr(srv, "vectordb_path", kb / "vector_db")
    monkeypatch.setattr(srv, "_vector_db_ro_doc_count", lambda p: 1234)
    monkeypatch.setattr(srv, "UnifiedGraphQuery", _FakeGraph)

    gate, entered = threading.Event(), threading.Event()

    def _slow_adapter(**_kw):
        entered.set()
        assert gate.wait(10), "test never released the loader"
        return SimpleNamespace(vector_search=SimpleNamespace(doc_count=1234))

    monkeypatch.setattr(srv, "UnifiedSearchAdapter", _slow_adapter)
    t = threading.Thread(target=srv._load_kb, daemon=True)
    t.start()
    assert entered.wait(10), "loader never reached the search half"
    try:
        yield SimpleNamespace(gate=gate, thread=t)
    finally:
        gate.set()
        t.join(10)


def _call(name, args):
    out = asyncio.run(srv.call_tool(name, args))
    return out[0].text


def test_exact_lookup_answers_while_search_still_loading(held_loader):
    assert srv._KB_STATUS == "graph_ready"

    info = json.loads(_call("get_operator_info", {"operator_name": "Noise TOP"}))
    assert info.get("name") == "Noise TOP"          # a real answer, not an envelope

    hs = json.loads(_call("hybrid_search", {"query": "noise"}))
    assert hs["ok"] is False
    assert hs["error"]["status"] == "kb_warming"
    # The refusal tells the caller exact lookups already work.
    assert "get_operator_info" in hs["error"]["message"]


def test_register_component_still_waits_for_search(held_loader):
    out = json.loads(_call("register_component", {"source_path": "x.tox"}))
    assert out["error"]["status"] == "kb_warming"


def test_get_server_info_reports_graph_ready(held_loader):
    data = json.loads(_call("get_server_info", {}))["data"]
    assert data["kb_status"] == "graph_ready"


def test_loader_finishes_ready_after_release(held_loader):
    held_loader.gate.set()
    held_loader.thread.join(10)
    assert srv._KB_STATUS == "ready"
    assert srv.hybrid_search is not None


def test_before_graph_every_kb_tool_waits():
    srv._KB_STATUS = "warming"
    for tool, args in (("get_operator_info", {"operator_name": "Noise TOP"}),
                       ("hybrid_search", {"query": "noise"})):
        out = json.loads(_call(tool, args))
        assert out["error"]["status"] == "kb_warming", tool

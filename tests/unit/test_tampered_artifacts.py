"""W2d — tampered/unreceipted KB pickles: both load sites refuse + degrade.

Exercises the REAL guard sites (retrieval_stack._load_bm25 and
EnhancedGraphQuery.__init__) against tmp-dir KBs. Hermetic: fake artifacts,
reranker disabled, no chromadb/sentence-transformers imports. NEVER points at
the fetched KB/ — tamper fixtures are copies in tmp dirs by construction.
"""
import importlib.util
import pickle
import sys
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

import kb_integrity as ki  # noqa: E402
from enhanced_graph_query import EnhancedGraphQuery  # noqa: E402


def _load_retrieval_stack():
    mod = sys.modules.get("_w2d_retrieval_stack")
    if mod is None:
        p = _REPO_ROOT / "MCP" / "server_core" / "search" / "retrieval_stack.py"
        spec = importlib.util.spec_from_file_location("_w2d_retrieval_stack", str(p))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_w2d_retrieval_stack"] = mod
        spec.loader.exec_module(mod)
    return mod


def _flip_byte(path: Path, offset: int = 7):
    raw = bytearray(path.read_bytes())
    raw[offset] ^= 0xFF
    path.write_bytes(bytes(raw))


# -- bm25 / RetrievalStack -------------------------------------------------------

def _bm25_kb(tmp_path):
    """tmp KB with a well-formed (stub) bm25 payload + receipt."""
    kb = tmp_path / "KB"
    (kb / "lexical_index").mkdir(parents=True)
    payload = {
        "bm25": types.SimpleNamespace(),  # never queried in these tests
        "ids": ["row1"], "texts": ["t"], "metas": [{}],
        "tokenizer_pattern": r"[a-z0-9]+",
    }
    (kb / "lexical_index" / "bm25.pkl").write_bytes(pickle.dumps(payload))
    ki.write_receipt(kb, source="test")
    return kb


def _stack(rs_mod, kb):
    stub = types.SimpleNamespace(collection=None, model=None)
    return rs_mod.RetrievalStack(kb_root=kb, vector_search=stub)


@pytest.fixture(autouse=True)
def _no_rerank(monkeypatch):
    monkeypatch.setenv("RS_USE_RERANK", "0")


def test_receipted_bm25_loads(tmp_path):
    rs = _stack(_load_retrieval_stack(), _bm25_kb(tmp_path))
    assert rs._bm25 is not None and rs._bm25_ids == ["row1"]


def test_tampered_bm25_refused_dense_only_continue(tmp_path, capsys):
    kb = _bm25_kb(tmp_path)
    _flip_byte(kb / "lexical_index" / "bm25.pkl")
    rs = _stack(_load_retrieval_stack(), kb)   # must NOT raise
    out = capsys.readouterr().out
    assert rs._bm25 is None                    # refused
    assert "SECURITY" in out and "DENSE-ONLY" in out
    assert "mismatch" in out                   # actionable: says what failed
    # degraded stack still answers (dense channel empty here -> empty list, no crash)
    assert rs.search("noise", 3) == []


def test_unreceipted_bm25_refused(tmp_path, capsys):
    kb = _bm25_kb(tmp_path)
    (kb / ki.RECEIPT_NAME).unlink()
    rs = _stack(_load_retrieval_stack(), kb)
    assert rs._bm25 is None
    assert "no integrity anchor" in capsys.readouterr().out


# -- gpickle / EnhancedGraphQuery -------------------------------------------------

def _graph_kb(tmp_path):
    kb = tmp_path / "KB"
    kb.mkdir()
    nodes = {"op1": {"id": "op1", "type": "Operator", "name": "noiseTOP", "family": "TOP"}}
    gp = kb / "knowledge_graph_enhanced.gpickle"
    gp.write_bytes(pickle.dumps({"nodes": nodes, "edges": []}))
    ki.write_receipt(kb, source="test")
    return gp


def test_receipted_gpickle_loads(tmp_path):
    eq = EnhancedGraphQuery(str(_graph_kb(tmp_path)))
    assert not eq.integrity_failed and len(eq.nodes) == 1


def test_tampered_gpickle_refused_graph_off_continue(tmp_path, capsys):
    gp = _graph_kb(tmp_path)
    _flip_byte(gp)
    eq = EnhancedGraphQuery(str(gp))           # must NOT raise
    err = capsys.readouterr().err
    assert eq.integrity_failed and "mismatch" in eq.integrity_reason
    assert eq.nodes == {} and eq.edges == []   # graph features off...
    assert "[SECURITY]" in err and "REFUSED" in err
    # ...but the engine still answers queries (empty, not crashing)
    assert eq.find_examples_by_operator("noiseTOP") == []
    assert eq.get_network_patterns() == []


def test_unreceipted_gpickle_refused(tmp_path, capsys):
    gp = _graph_kb(tmp_path)
    (gp.parent / ki.RECEIPT_NAME).unlink()
    eq = EnhancedGraphQuery(str(gp))
    assert eq.integrity_failed and eq.nodes == {}
    assert "no integrity anchor" in eq.integrity_reason


def test_missing_gpickle_still_raises_filenotfound(tmp_path):
    """Missing-file semantics are unchanged (mcp_server's pre-flight relies on it)."""
    with pytest.raises(FileNotFoundError):
        EnhancedGraphQuery(str(tmp_path / "absent.gpickle"))


def test_poisoned_gpickle_payload_never_executes(tmp_path):
    """The ACE-shaped case end-to-end: a poison pickle swapped into a receipted
    KB is refused BEFORE deserialization — the payload must not run."""
    gp = _graph_kb(tmp_path)
    sentinel = tmp_path / "PWNED"

    class Poison:
        def __reduce__(self):
            import os
            return (os.mkdir, (str(sentinel),))

    gp.write_bytes(pickle.dumps(Poison()))     # attacker swap, receipt now stale
    eq = EnhancedGraphQuery(str(gp))
    assert eq.integrity_failed
    assert not sentinel.exists()

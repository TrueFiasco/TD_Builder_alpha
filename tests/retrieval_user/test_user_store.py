"""W7 — user-store retrieval integration (T3/T5/T6/T8): LOCAL kb-full lane only.

Needs chromadb + sentence-transformers + the fetched KB (vector_db, bm25,
reranker bundle), so it runs in NO CI lane — it is part of the local merge gate:

    py -3.11 -m pytest tests/retrieval_user -q

Covers: ingest → reload → healthy-mode retrieval; T3 zero-displacement + the
cap-binding exact-name guarantee (weird tokenization + short names, R2.2-3);
T5 incremental lifecycle incl. the degrade-in-place empty store (W2); T6
degrades (regime mismatch, corrupt manifest, no-CE dense_fallback at a >cap
store, RS_DISABLE dense-only adapter); T8 stale-summary loud warning.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "MCP" / "server_core")):
    if p not in sys.path:
        sys.path.insert(0, p)

pytestmark = pytest.mark.requires_kb

from kb_build import user_components as uc  # noqa: E402

KB_ROOT = REPO / "KB"

if not (KB_ROOT / "vector_db").exists():
    pytest.skip("KB vector_db not fetched", allow_module_level=True)


def _load_by_path(name: str, rel: str):
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, str(REPO / rel))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# module-scoped heavy pieces (one model, one KB vector search, one stack)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sd():
    return _load_by_path("w7_search_docs", "MCP/server_core/search_docs.py")


@pytest.fixture(scope="module")
def rs():
    return _load_by_path("w7_retrieval_stack", "MCP/server_core/search/retrieval_stack.py")


@pytest.fixture(scope="module")
def vector_search(sd):
    return sd.TDDocSearch(str(KB_ROOT / "vector_db"))


@pytest.fixture(scope="module")
def emb_model(vector_search):
    # the RAW sentence-transformer under the _QueryEncoder (passage embedding)
    return getattr(vector_search.model, "_model", vector_search.model)


@pytest.fixture(scope="module")
def stack(rs, vector_search):
    s = rs.RetrievalStack(kb_root=KB_ROOT, vector_search=vector_search)
    yield s
    s._user = None


def _register(monkeypatch, user_dir: Path, comps: dict, model) -> None:
    """comps = {name: (summary, contained, cparm_text)} — fabricated skeletons,
    no toeexpand; upsert + one batched incremental ingest under the lock."""
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(user_dir))
    rows, hashes = [], {}
    shipped = uc.shipped_component_names()
    with uc.commit_lock():
        for name, (summary, contained, cparm) in comps.items():
            sk = {
                "manifest": {
                    "inputs": [{"name": "in1", "op_type": "CHOP:in"}],
                    "outputs": [{"name": "out1", "op_type": "CHOP:out"}],
                    "families": {"CHOP": 3}, "operator_count": 4,
                    "connection_count": 2, "interface_path": f"/{name}",
                    "wrapper": False, "summary": "",
                },
                "inner_type": "COMP:base", "subcompname": None,
                "contained_operators": sorted(contained),
                "interface_files": {"cparm": cparm, "parm_values": {}},
            }
            pars, warns = uc.custom_parameters_from_skeleton(sk)
            sk["custom_parameters"], sk["parse_warnings"] = pars, warns
            entry, _ = uc.build_entry(sk, source="project",
                                      tox_path=f"C:/proj/{name}.tox", summary=summary)
            uc.upsert_registry_entry(name, entry)
            rows.extend(uc.component_block_rows(name, entry,
                                                shadows_shipped=name in shipped))
            hashes[name] = uc.semantic_hash_of_entry(entry)
        uc.ingest_incremental(rows, hashes, model=model)


def _user_hits(results, name=None):
    out = [r for r in results if r["metadata"].get("license_tier") == "user"]
    if name is not None:
        out = [r for r in out if r["metadata"].get("name") == name]
    return out


# ---------------------------------------------------------------------------
# ingest → reload → healthy retrieval
# ---------------------------------------------------------------------------
def test_ingest_reload_and_healthy_search(stack, emb_model, tmp_path, monkeypatch):
    _register(monkeypatch, tmp_path,
              {"glowPulse": ("Audio-reactive glow pulse generator for LED strips.",
                             ["CHOP:lfo", "CHOP:math"], None)}, emb_model)
    ok, reason = stack.reload_user_store(tmp_path / "user_index")
    assert ok, reason
    assert stack._user is not None and stack._user.count == 3
    # regime recorded == shipped KB regime
    man = json.loads((tmp_path / "user_index" / "manifest.json").read_text("utf-8"))
    assert man["embedding_model"].casefold() == "all-minilm-l6-v2"
    assert man["collection"] == "td_unified"
    assert set(man["semantic_hash"]) == {"glowPulse"}

    res = stack.search("audio reactive glow pulse for LED strips component", 8)
    mine = _user_hits(res, "glowPulse")
    assert mine, f"user chunk missing from results: {[r['metadata'].get('name') for r in res]}"
    if stack._reranker is not None:
        assert mine[0]["score_kind"] == "reranked"   # healthy-mode honesty (Δ1)


# ---------------------------------------------------------------------------
# T3 — zero displacement + cap-binding exact-name direct-injection
# ---------------------------------------------------------------------------
KB_QUERIES = [
    "how do I blur an image",
    "audio reactive visuals from microphone input",
    "instance geometry from a point cloud",
]

JUNK = {f"fixtureComp{i:02d}": (f"Placeholder fixture component number {i} for "
                                f"displacement testing, does nothing real.",
                                ["CHOP:math"], None)
        for i in range(11)}
JUNK["myWeirdComp_v3"] = ("Weirdly tokenized fixture comp.", ["CHOP:math"], None)
JUNK["glow"] = ("Short-named fixture comp.", ["CHOP:math"], None)


def test_t3_displacement_and_cap_binding(stack, emb_model, tmp_path, monkeypatch):
    if stack._reranker is None:
        pytest.skip("reranker bundle missing — healthy-mode displacement needs it")
    # pristine top-5 first (no user store)
    stack.reload_user_store(tmp_path / "nonexistent")
    assert stack._user is None
    pristine = {}
    for q in KB_QUERIES:
        pristine[q] = [r["metadata"].get("orig_id") or r["content"][:60]
                       for r in stack.search(q, 5)]

    _register(monkeypatch, tmp_path, JUNK, emb_model)     # 13 unrelated comps
    ok, reason = stack.reload_user_store(tmp_path / "user_index")
    assert ok, reason

    for q in KB_QUERIES:
        got = [r["metadata"].get("orig_id") or r["content"][:60]
               for r in stack.search(q, 5)]
        assert got == pristine[q], \
            f"KB top-5 displaced for {q!r}: {got} != {pristine[q]}"

    # cap-binding half (W1b/W4, R2.2-3): with the dense cut squeezed to 3, the
    # exact-name direct-injection must still guarantee recall — including a
    # weird-tokenization name AND a short name the KB resolver's >=5 guard
    # would have dropped.
    old_top = stack.cfg.user_top
    stack.cfg.user_top = 3
    try:
        for name, q in (("myWeirdComp_v3", "configure myWeirdComp_v3 output"),
                        ("glow", "add my glow comp to the network")):
            res = stack.search(q, 10)
            assert _user_hits(res, name), \
                f"exact-name recall lost for {name!r} at RS_USER_TOP=3"
    finally:
        stack.cfg.user_top = old_top


# ---------------------------------------------------------------------------
# T5 — incremental lifecycle + degrade-in-place empty store
# ---------------------------------------------------------------------------
def test_t5_lifecycle(stack, emb_model, tmp_path, monkeypatch):
    _register(monkeypatch, tmp_path,
              {"compA": ("Fixture comp A for lifecycle.", ["CHOP:math"], None)},
              emb_model)
    _register(monkeypatch, tmp_path,
              {"compB": ("Fixture comp B for lifecycle.", ["CHOP:lfo"], None)},
              emb_model)
    ok, _ = stack.reload_user_store(tmp_path / "user_index")
    assert ok and stack._user.count == 6 and set(stack._user.semantic_hash) == \
        {"compA", "compB"}

    # re-register B with FEWER chunks: name-scoped delete must drop the io chunk
    _register(monkeypatch, tmp_path,
              {"compB": ("Fixture comp B v2.", [], None)}, emb_model)
    ok, _ = stack.reload_user_store(tmp_path / "user_index")
    assert ok and stack._user.count == 5
    ids = stack._user.collection.get().get("ids", [])
    assert "user:block:compb:io" not in ids and "user:block:compa:io" in ids

    # remove one comp
    uc.remove_component("compA")
    ok, _ = stack.reload_user_store(tmp_path / "user_index")
    assert ok and stack._user.count == 2

    # remove the LAST comp -> degrade-in-place (W2): rows gone, hash map empty,
    # the DIRECTORY still exists (never deleted under open handles), and the
    # store is treated as absent — KB-only search keeps working.
    uc.remove_component("compB")
    ok, reason = stack.reload_user_store(tmp_path / "user_index")
    assert not ok and "empty" in reason
    assert stack._user is None
    assert (tmp_path / "user_index").is_dir(), "degrade-in-place must not delete the dir"
    man = json.loads((tmp_path / "user_index" / "manifest.json").read_text("utf-8"))
    assert man["semantic_hash"] == {}
    reg = json.loads((tmp_path / "user_components.json").read_text("utf-8"))
    assert reg["components"] == {}
    assert stack.search("blur an image", 3), "KB-only search must still work"

    # store comes back to life through the same reload path
    _register(monkeypatch, tmp_path,
              {"compC": ("Fixture comp C revival.", ["CHOP:math"], None)}, emb_model)
    ok, _ = stack.reload_user_store(tmp_path / "user_index")
    assert ok and stack._user.count == 3


# ---------------------------------------------------------------------------
# T8 — edited-summary staleness is loud (still serves)
# ---------------------------------------------------------------------------
def test_t8_stale_summary_warns_loud(stack, emb_model, tmp_path, monkeypatch, capfd):
    _register(monkeypatch, tmp_path,
              {"staleComp": ("Original summary.", ["CHOP:math"], None)}, emb_model)
    reg_p = tmp_path / "user_components.json"
    spec = json.loads(reg_p.read_text("utf-8"))
    spec["components"]["staleComp"]["summary"] = "Edited after ingest."
    reg_p.write_text(json.dumps(spec), encoding="utf-8")

    ok, _ = stack.reload_user_store(tmp_path / "user_index")
    assert ok, "stale text beats absent — the store must still serve"
    out = capfd.readouterr().out
    assert "STALE" in out and "staleComp" in out


# ---------------------------------------------------------------------------
# T6 — degrades: regime mismatch, corrupt manifest, no-CE fallback, RS_DISABLE
# ---------------------------------------------------------------------------
def test_t6_regime_mismatch_refused(stack, emb_model, tmp_path, monkeypatch):
    monkeypatch.delenv("TD_BUILDER_TRUST_KB", raising=False)   # never false-green
    _register(monkeypatch, tmp_path,
              {"mismatch": ("Regime mismatch fixture.", [], None)}, emb_model)
    mp = tmp_path / "user_index" / "manifest.json"
    man = json.loads(mp.read_text("utf-8"))
    man["embedding_model"] = "bge-large-en-v1.5"
    mp.write_text(json.dumps(man), encoding="utf-8")
    ok, reason = stack.reload_user_store(tmp_path / "user_index")
    assert not ok and "regime mismatch" in reason
    assert stack._user is None
    assert stack.search("blur an image", 3), "KB results unaffected"


def test_t6_corrupt_manifest_refused(stack, emb_model, tmp_path, monkeypatch):
    monkeypatch.delenv("TD_BUILDER_TRUST_KB", raising=False)
    _register(monkeypatch, tmp_path,
              {"corrupt": ("Corrupt manifest fixture.", [], None)}, emb_model)
    (tmp_path / "user_index" / "manifest.json").write_text("{not json",
                                                           encoding="utf-8")
    ok, reason = stack.reload_user_store(tmp_path / "user_index")
    assert not ok and "unreadable" in reason
    assert stack._user is None
    assert stack.search("blur an image", 3)


def test_t6_noce_fallback_exact_name_over_cap(rs, vector_search, emb_model,
                                              tmp_path, monkeypatch, capfd):
    """W1×W3 intersection (R2.2-1/R2.2-2): no reranker + >RS_USER_TOP store +
    exact-name query -> the direct-injected chunk (assigned dense_score=1.0,
    scaled ×RS_USER_NOCE_SCALE=4.0) must outrank every KB fallback hit
    (ceiling ≈ 3.3) and carry the honest score_kind 'dense_fallback' (Δ1).
    This doubles as the mis-scaling tripwire."""
    monkeypatch.setenv("RS_USE_RERANK", "0")
    monkeypatch.setenv("RS_USER_TOP", "3")
    comps = {f"noceFill{i}": (f"No-CE filler comp {i}.", [], None) for i in range(4)}
    comps["zetaFlowMix_v2"] = ("Fixture comp with an unrelated summary about "
                               "spreadsheet accounting.", [], None)
    _register(monkeypatch, tmp_path, comps, emb_model)

    s2 = rs.RetrievalStack(kb_root=KB_ROOT, vector_search=vector_search,
                           user_store=tmp_path / "user_index")
    assert s2._reranker is None
    # 5 comps × 2 chunks (no inventory/pars -> no io chunk) = 10 > the cap of 3
    assert s2._user is not None and s2._user.count == 10 > s2.cfg.user_top
    out = capfd.readouterr().out
    assert "degraded" in out and "reranker unavailable" in out   # W3 loud log

    res = s2.search("zetaFlowMix_v2 component", 8)
    mine = _user_hits(res, "zetaFlowMix_v2")
    assert mine, "exact-name recall lost in no-CE mode"
    assert mine[0]["score_kind"] == "dense_fallback"
    # the mis-scaling tripwire (R2.2-2): assigned 1.0 × RS_USER_NOCE_SCALE must
    # clear the UNBOOSTED KB fallback ceiling (dual-ladder rrf*100 ≈ 3.3) — it
    # fails if the 4.0 default ever stops doing so. (Router type-affinity can
    # legitimately lift KB chunks further on strongly build-phrased queries;
    # that headroom is what the env-tunable scale is for.)
    assert mine[0]["score"] > rs._sigmoid(3.3)
    top_kb_rank = next((i for i, r in enumerate(res)
                        if r["metadata"].get("license_tier") != "user"), len(res))
    my_rank = next(i for i, r in enumerate(res)
                   if r["metadata"].get("name") == "zetaFlowMix_v2")
    assert my_rank < top_kb_rank, \
        "palette-intent exact-name query must rank the user comp first in no-CE mode"


def test_t6_rs_disable_dense_only_adapter(tmp_path, monkeypatch):
    """W6: RS_DISABLE -> retrieval_stack=None -> reload returns (False, reason);
    a register_component commit on such an install stays valid (buildable ≠
    searchable) — the handler surfaces retrievable:false with this reason."""
    monkeypatch.setenv("RS_DISABLE", "1")
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    us = _load_by_path("w7_unified_search", "MCP/server_core/search/unified_search.py")
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        adapter = us.UnifiedSearchAdapter(
            vectordb_path=str(KB_ROOT / "vector_db"),
            graph_path=str(KB_ROOT / "knowledge_graph_enhanced.gpickle"),
            user_search=True)
    assert adapter.retrieval_stack is None
    ok, reason = adapter.reload_user_store()
    assert not ok and "dense-only" in reason

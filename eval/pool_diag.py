#!/usr/bin/env python3
r"""
Phase-3 FAIRNESS diagnostic for an embedder arm that LOSES recall vs the control.

The Phase-2 stack's candidate-pool sizes (dense_top / rerank_top) and RRF_PRIOR were
tuned for MiniLM. A different embedder can lose a query for two very different reasons:

  (a) DEMOTED  — the gold chunk WAS in the pre-rerank candidate pool the cross-encoder
                 scored, but MiniLM-tuned rerank/RRF-prior ordering pushed it below top-5.
                 → an ordering artifact; that embedder could compete with stack re-tuning.
  (b) ABSENT   — the gold chunk was NOT in the pool at all (dense+BM25 never retrieved it,
                 or it fell outside the rerank_top cut). → genuine dense-recall inferiority
                 (the cut case is recoverable by a larger pool).

This reconstructs the EXACT pre-rerank pool/keep set by calling the live RetrievalStack
internals (the stack code is untouched), then checks whether any pooled chunk satisfies the
query's relevance predicate. Reported SEPARATELY from the byte-identical-stack A/B.

  py -3.11 eval/pool_diag.py --arm-kb "<KB_arm>" --arm-model <hf id> \
      --queries eval/heldout_queries.jsonl \
      --control-details "<KB control details.json>" --arm-details "<KB_arm details.json>"
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("EMBEDDING_PROVIDER", "local")
os.environ["CACHE_ENABLED"] = "false"
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

EVAL_DIR = Path(__file__).resolve().parent
REPO = EVAL_DIR.parent
SERVER_CORE = REPO / "MCP" / "server_core"
sys.path.insert(0, str(EVAL_DIR))
from predicates import is_relevant  # noqa: E402


def build_adapter(kb_root: str):
    sys.path.insert(0, str(SERVER_CORE))
    os.chdir(SERVER_CORE)
    try:
        import torch
        torch.set_num_threads(1)
    except Exception:
        pass
    from search.unified_search import UnifiedSearchAdapter
    return UnifiedSearchAdapter(vectordb_path=str(Path(kb_root) / "vector_db"),
                                graph_path=str(Path(kb_root) / "knowledge_graph_enhanced.gpickle"),
                                use_legacy=False)


def reconstruct(rs, query: str):
    """Replicates RetrievalStack.search()'s pre-rerank pool/keep construction exactly."""
    cfg = rs.cfg
    dense = rs._dense(query, cfg.dense_top)
    bm25 = rs._bm25_search(query, cfg.bm25_top) if cfg.use_bm25 else []
    pool = rs._rrf(dense, bm25)
    route = (rs._route(query) if cfg.use_router
             else {"named_op": None, "intents": set(), "do_param_filter": False, "op_lookup": False})
    if cfg.use_router:
        rs._inject_op_chunks(route, pool)
    ranked = sorted(pool, key=lambda i: pool[i].get("rrf", 0.0), reverse=True)
    keep = set(ranked[:cfg.rerank_top]) | {i for i in pool if pool[i].get("injected")}
    if cfg.use_router and route.get("op_lookup"):
        keep |= {i for i in pool if pool[i]["metadata"].get("type") == "operator_overview"}
    return dense, bm25, pool, keep


def _gold_in(cands: dict, pred) -> bool:
    for c in cands.values():
        if is_relevant({"content": c.get("content"), "metadata": c.get("metadata", {})}, pred):
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description="Phase-3 pool-membership fairness diagnostic")
    ap.add_argument("--arm-kb", required=True)
    ap.add_argument("--arm-model", required=True)
    ap.add_argument("--queries", required=True)
    ap.add_argument("--control-details", required=True, help="control run details.json")
    ap.add_argument("--arm-details", required=True, help="arm run details.json")
    ap.add_argument("--backend", default="enhanced")
    ap.add_argument("--label", default="arm")
    args = ap.parse_args()

    os.environ["EMBEDDING_MODEL"] = args.arm_model
    queries = {}
    for ln in Path(args.queries).read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            queries[r["id"]] = r
    ctrl = {r["id"]: r for r in json.loads(Path(args.control_details).read_text(encoding="utf-8"))[args.backend]}
    arm = {r["id"]: r for r in json.loads(Path(args.arm_details).read_text(encoding="utf-8"))[args.backend]}
    lost = [qid for qid in ctrl if qid in arm
            and ctrl[qid].get("recall_at_k", 0) == 1 and arm[qid].get("recall_at_k", 0) == 0]

    print(f"\n=== Fairness diagnostic: {args.label} (lost {len(lost)} queries vs control) ===")
    if not lost:
        print("  (no recall losses vs control — nothing to diagnose)")
        return

    with contextlib.redirect_stdout(sys.stderr):
        adapter = build_adapter(args.arm_kb)
        rs = adapter.retrieval_stack
    counts = {"DEMOTED": 0, "DROPPED@cut": 0, "ABSENT": 0}
    for qid in lost:
        q = queries[qid]["query"]
        pred = queries[qid]["relevant_predicate"]
        with contextlib.redirect_stdout(sys.stderr):
            dense, bm25, pool, keep = reconstruct(rs, q)
        in_keep = _gold_in({i: pool[i] for i in keep}, pred)
        in_pool = _gold_in(pool, pred)
        in_dense = _gold_in({d["id"]: d for d in dense}, pred)
        in_bm25 = _gold_in({b["id"]: b for b in bm25}, pred)
        if in_keep:
            cls = "DEMOTED"          # reranker saw the gold but MiniLM-tuned ordering buried it
        elif in_pool:
            cls = "DROPPED@cut"      # in the fused pool but outside rerank_top (pool-size artifact)
        else:
            cls = "ABSENT"          # never retrieved by dense+BM25 (genuine dense miss)
        counts[cls] += 1
        print(f"  {qid:8s} {queries[qid].get('category',''):18s} {cls:12s} "
              f"(gold in dense={int(in_dense)} bm25={int(in_bm25)} pool={int(in_pool)} keep={int(in_keep)})")

    print(f"\n  summary: DEMOTED={counts['DEMOTED']} (ordering artifact, MiniLM-tuned)  "
          f"DROPPED@cut={counts['DROPPED@cut']} (pool-size, raise rerank_top)  "
          f"ABSENT={counts['ABSENT']} (genuine dense miss)")
    if counts["DEMOTED"] or counts["DROPPED@cut"]:
        print("  => some losses are NOT dense-recall inferiority; that arm is 'competitive with "
              "pool/stack re-tune', not strictly worse. Re-tune diagnostic = RS_DENSE_TOP/RS_RERANK_TOP up.")


if __name__ == "__main__":
    main()

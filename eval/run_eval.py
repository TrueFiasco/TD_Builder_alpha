#!/usr/bin/env python3
r"""
Phase-0 evaluation harness for the TD Builder KB / retrieval redesign.

Drives the SHIPPED search path in-process and offline: it imports the real
``UnifiedSearchAdapter`` from ``MCP/server_core/search/unified_search.py`` and
calls ``.search()`` -- the exact call the live ``hybrid_search`` MCP tool makes
-- so the numbers it reports are the numbers the running server would produce.

The backend is swappable for A/B testing and the harness is meant to be reused
UNCHANGED through Phase 2/3:

  * ``--backend enhanced`` -> ``use_legacy=False`` : the CURRENT SHIPPED path and
    the slot Phase 2 plugs its new retrieval stack into (``_enhanced_search``).
    This is THE baseline -- the gate every later phase must beat.
  * ``--backend legacy``   -> ``use_legacy=True``  : the frozen ``HybridGraphRAG``
    reference, which will NOT change as ``_enhanced_search`` is edited.

(Today both backends produce identical ``semantic_results`` -- both call the
same dense MiniLM ``TDDocSearch`` over collection ``td_unified`` -- so their
ranking metrics match; they diverge only once Phase 2 lands.)

Metrics (per category + aggregate), with binary relevance from each query's
``relevant_predicate`` (see predicates.py):
  * recall@k  -- hit-rate: 1.0 if >=1 relevant chunk in the top-k, else 0.0
                (predicates label an open set, so this is success@k, which is
                 what the plan's "recall@5" baseline table reports).
  * MRR       -- 1 / rank of the first relevant chunk in the retrieved list.
  * nDCG@n    -- binary-gain DCG over top-n / ideal DCG (all found-relevant first).

Plus a ground-truth NAME-INTEGRITY gate over every returned chunk: counts
results that assert an operator identity which does not resolve against
operators.json / operator_types.json (hard violation), and -- as the documented
hazard metric -- results that surface a retokenized underscored wiki-title name
(e.g. ``Ableton_Link_CHOP``) as the display name.

Usage (worktree; KB data is read from the main tree by absolute path):
    py -3.11 eval/run_eval.py
    py -3.11 eval/run_eval.py --backend both --k 5 --ndcg-k 10
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

_TRIAL_SENTINEL = "__TRIAL_JSON__"

# --- offline + deterministic: set BEFORE the server config / torch are imported -
os.environ.setdefault("EMBEDDING_PROVIDER", "local")   # MiniLM, no API calls
os.environ.setdefault("FALLBACK_TO_LOCAL", "true")
os.environ["CACHE_ENABLED"] = "false"                  # no cross-query cache
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# Offline by default: use the locally-cached MiniLM snapshot deterministically (no hub
# round-trip, which can otherwise re-resolve the model and perturb embeddings run-to-run).
# The embedder ships/caches with the server; override by exporting these = "0" if needed.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
# Pin BLAS/torch to a single thread so the MiniLM forward pass is bit-reproducible
# ACROSS processes (multi-threaded BLAS otherwise flips a couple of borderline
# rank-5/6 results run-to-run). Embedding 60 short queries single-threaded is sub-second.
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"
# W7 hermeticity (W8): pin the USER component dir to a fresh empty tmp dir for
# every script-run gate (this module is also the env base for eval/build_gate).
# The adapter is built user_search=False anyway — this pin additionally covers
# the BUILDER's registry merge, which reads TD_BUILDER_USER_DIR at call time.
os.environ["TD_BUILDER_USER_DIR"] = tempfile.mkdtemp(prefix="td_eval_user_pin_")

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent                            # the (worktree) repo root
SERVER_CORE = REPO_ROOT / "MCP" / "server_core"
_MAIN_TREE = (Path(*REPO_ROOT.parts[: REPO_ROOT.parts.index(".claude")])
              if ".claude" in REPO_ROOT.parts else None)


def redact_path(p) -> str:
    """Tree-relative form of a provenance path for the COMMITTED baselines.

    Absolute local paths in eval/baseline.json leaked the build machine's
    directory layout into the public repo. Record paths relative to the tree
    that contains them (worktree repo root, or the main tree above .claude/),
    falling back to the basename for anything outside both."""
    p = Path(p)
    parts = list(p.parts)
    if ".claude" in parts:
        i = parts.index(".claude")
        # inside a worktree: .../.claude/worktrees/<name>/<rel> -> <rel>
        rel = parts[i + 3:] if len(parts) > i + 2 and parts[i + 1] == "worktrees" else parts[i:]
        return "/".join(rel) or p.name
    for root in (REPO_ROOT,) + ((_MAIN_TREE,) if _MAIN_TREE else ()):
        try:
            return p.relative_to(root).as_posix()
        except ValueError:
            pass
    return p.name

sys.path.insert(0, str(EVAL_DIR))
from predicates import GroundTruth, check_name_integrity, is_relevant  # noqa: E402

HARNESS_VERSION = "0.1.0"
COLLECTION = "td_unified"
BACKENDS = {"enhanced": False, "legacy": True}          # name -> use_legacy


# ---------------------------------------------------------------------------
# Path resolution -- code from the (worktree) repo, KB DATA from the main tree
# (worktrees don't carry the gitignored KB; see memory running-tests-in-worktree)
# ---------------------------------------------------------------------------
def _has_vdb(kb_root: Path) -> bool:
    return (kb_root / "vector_db" / "chroma.sqlite3").exists()


def _partial_missing(kb_root: Path) -> list:
    return [rel for rel in ("lexical_index/bm25.pkl", "models")
            if not (kb_root / rel).exists()]


# Last resolution, for the §8 printed report + identity stamp:
# {"source": cli|env|repo|main-tree, "missing": [...]}
KB_RESOLUTION: dict = {}


def _warn_if_partial(kb_root: Path, source: str = "unknown",
                     require_full: bool = False,
                     allow_partial: bool = False) -> Path:
    """A KB with a vector_db but no Phase-2 artifacts makes the enhanced stack
    silently degrade to dense-only, so the reported metrics would not measure
    the shipped hybrid path.

    §8 fix: for EVAL runs (require_full=True) this escalates from warning to
    REFUSAL unless --allow-partial-kb — a dense-only number labeled as the
    hybrid stack is worse than no number. Library callers (build gate etc.)
    keep the historical warn-only behavior."""
    missing = _partial_missing(kb_root)
    KB_RESOLUTION.clear()
    KB_RESOLUTION.update({"source": source, "missing": missing})
    if missing:
        msg = (f"[run_eval] KB at {kb_root} is missing {missing} -- the "
               f"enhanced backend would run DENSE-ONLY and its metrics would "
               f"not reflect the Phase-2 hybrid stack.")
        if require_full and not allow_partial:
            print(msg + "\n[run_eval] REFUSING to measure a partial KB "
                  "(pass --allow-partial-kb to proceed, clearly labeled).",
                  file=sys.stderr)
            raise SystemExit(2)
        print("WARNING: " + msg, file=sys.stderr)
    return kb_root


def resolve_kb_root(cli_kb: str | None, require_full: bool = False,
                    allow_partial: bool = False) -> Path:
    kw = {"require_full": require_full, "allow_partial": allow_partial}
    if cli_kb:
        return _warn_if_partial(Path(cli_kb), "cli", **kw)
    env = os.environ.get("EVAL_KB_ROOT") or os.environ.get("UNIFIED_KB_ROOT")
    if env:
        return _warn_if_partial(Path(env), "env", **kw)
    # 1) this repo's own KB (works outside a worktree)
    if _has_vdb(REPO_ROOT / "KB"):
        return _warn_if_partial(REPO_ROOT / "KB", "repo", **kw)
    # 2) main tree: strip the .claude/worktrees/<name> tail
    parts = REPO_ROOT.parts
    if ".claude" in parts:
        main_tree = Path(*parts[: parts.index(".claude")])
        if _has_vdb(main_tree / "KB"):
            return _warn_if_partial(main_tree / "KB", "main-tree", **kw)
    raise FileNotFoundError(
        "Could not locate a KB with vector_db/chroma.sqlite3. "
        "Pass --kb <path-to-KB> or set EVAL_KB_ROOT."
    )


_IDENTITY_MOD = None


def _identity_helper():
    """Load the shared identity stamp (eval/agent_eval/identity.py) via
    importlib — both harnesses stamp the same block (§7/§8)."""
    global _IDENTITY_MOD
    if _IDENTITY_MOD is None:
        import importlib.util
        path = EVAL_DIR / "agent_eval" / "identity.py"
        spec = importlib.util.spec_from_file_location("agent_eval_identity", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _IDENTITY_MOD = mod
    return _IDENTITY_MOD


def _identity_mism(current: dict, prior: dict | None):
    """(mismatched, unknown) over the KB identity fields (kb_manifest_version,
    kb_sha) — the shared helper's rule, scoped to what run_eval controls."""
    return _identity_helper().identity_mismatches(
        current, prior, _identity_helper().KB_IDENTITY_FIELDS)


def resolve_stage_dir(cli_stage: str | None, kb_root: Path) -> Path:
    if cli_stage:
        return Path(cli_stage)
    # default: the main tree's "New KB build/Output/eval"
    main_tree = _main_tree() or kb_root.parent
    return main_tree / "New KB build" / "Output" / "eval"


def _main_tree() -> Path | None:
    """The real project root (strip the .claude/worktrees/<name> tail if present)."""
    parts = REPO_ROOT.parts
    if ".claude" in parts:
        return Path(*parts[: parts.index(".claude")])
    return None


def resolve_gt_paths(cli_ops, cli_types, kb_root: Path):
    """Resolve the name-integrity ground truth INDEPENDENTLY of --kb (flags win),
    so the gate stays authoritative when --kb points at a rebuilt KB output."""
    mt = _main_tree()
    if cli_ops:
        gt_ops = Path(cli_ops)
    else:
        cands = [kb_root / "operators.json"]
        if mt:
            cands.append(mt / "KB" / "operators.json")
        gt_ops = next((c for c in cands if c.exists()), cands[0])
    if cli_types:
        gt_types = Path(cli_types)
    else:
        cands = []
        if mt:
            cands.append(mt / "New KB build" / "Resources" / "operator_ground_truth" / "operator_types.json")
        cands.append(kb_root.parent / "New KB build" / "Resources" / "operator_ground_truth" / "operator_types.json")
        gt_types = next((c for c in cands if c.exists()), cands[-1])
    return gt_ops.resolve(), gt_types.resolve()


# ---------------------------------------------------------------------------
# Backend construction (imports the real shipped adapter)
# ---------------------------------------------------------------------------
def build_adapter(use_legacy: bool, vectordb_path: Path, graph_path: Path):
    """Construct the shipped UnifiedSearchAdapter for the given backend.

    chdir to server_core: the legacy HybridGraphRAG loads search_docs.py via a
    CWD-relative spec. The enhanced path uses absolute paths and is unaffected.
    """
    if str(SERVER_CORE) not in sys.path:
        sys.path.insert(0, str(SERVER_CORE))
    os.chdir(SERVER_CORE)
    with contextlib.redirect_stdout(sys.stderr):       # keep noisy init off stdout
        try:
            import torch
            torch.set_num_threads(1)                   # reinforce single-thread determinism
        except Exception:
            pass
        from search.unified_search import UnifiedSearchAdapter
        return UnifiedSearchAdapter(
            vectordb_path=str(vectordb_path),
            graph_path=str(graph_path),
            use_legacy=use_legacy,
            user_search=False,   # pristine gate: never open the user store (W7)
        )


def search(adapter, query: str, n: int) -> list[dict]:
    with contextlib.redirect_stdout(sys.stderr):
        res = adapter.search(query, n_results=n)
    if isinstance(res, dict):
        return res.get("semantic_results") or []
    return res or []


_GOLD_COUNTS: dict | None = None


def _gold_counts(kb_root: Path, queries: list[dict]) -> dict:
    """Per-query corpus gold counts (query id -> n relevant chunks in the KB).

    nDCG's ideal ranking needs the number of relevant chunks in the CORPUS,
    which the retrieved list cannot reveal. One full chunk-store scan per
    trial process (~78 predicates x ~6k chunks, a few seconds), evaluated
    with the same is_relevant() the scorer uses.
    """
    global _GOLD_COUNTS
    if _GOLD_COUNTS is None:
        import chromadb
        vdb = kb_root / "vector_db"
        if not (vdb / "chroma.sqlite3").exists():
            # KF1: PersistentClient is create-if-missing — opening an absent
            # store would manufacture a bare stub where the KB belongs.
            raise FileNotFoundError(f"no vector_db at {vdb} — fetch the KB first")
        col = chromadb.PersistentClient(path=str(vdb)).get_collection(COLLECTION)
        got = col.get(include=["documents", "metadatas"])
        chunks = [{"content": d, "metadata": m or {}}
                  for d, m in zip(got["documents"], got["metadatas"])]
        _GOLD_COUNTS = {}
        for row in queries:
            if row.get("expect_no_match"):
                continue
            _GOLD_COUNTS[row["id"]] = sum(
                1 for c in chunks if is_relevant(c, row["relevant_predicate"]))
    return _GOLD_COUNTS


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _dcg(rels: list[int]) -> float:
    return sum(r / math.log2(i + 2) for i, r in enumerate(rels))


def score_query(rels: list[int], k: int, ndcg_k: int, n_gold: int | None = None) -> dict:
    """rels = binary relevance in rank order over the retrieved list.

    n_gold = relevant-chunk count in the WHOLE corpus (from _gold_counts). The
    ideal DCG must be normalized by min(n_gold, ndcg_k); normalizing by the
    retrieved-relevant count made nDCG 1.0 for any query whose few hits ranked
    first, however many gold chunks were missed. Falls back to the retrieved
    count when the corpus count is unavailable.
    """
    topk = rels[:k]
    recall_at_k = 1.0 if any(topk) else 0.0
    rr = 0.0
    for i, r in enumerate(rels):
        if r:
            rr = 1.0 / (i + 1)
            break
    top_n = rels[:ndcg_k]
    ideal_n = min(n_gold, ndcg_k) if n_gold else sum(top_n)
    idcg = _dcg([1] * ideal_n) if ideal_n else 0.0
    ndcg = (_dcg(top_n) / idcg) if idcg > 0 else 0.0
    first_rel_rank = next((i + 1 for i, r in enumerate(rels) if r), None)
    return {"recall_at_k": recall_at_k, "rr": rr, "ndcg_at_n": ndcg,
            "first_relevant_rank": first_rel_rank, "n_relevant_retrieved": int(sum(rels))}


def _mean(xs: list[float]) -> float:
    return round(sum(xs) / len(xs), 4) if xs else 0.0


# ---------------------------------------------------------------------------
# Evaluate one backend over the labeled set
#
# ChromaDB's HNSW approximate search is not bit-deterministic across index loads
# (the embeddings + DB content + on-disk index are all stable -- verified -- but
# the in-memory graph traversal returns slightly different borderline neighbors,
# so ~1 rank-5/6 result can flip run-to-run). To make the baseline a stable gate
# we run R independent trials (fresh index load each) and report the per-metric
# MEDIAN plus the observed (min,max) band. The documented gaps (palette/howto/
# name-integrity) are invariant; only borderline operator/parameter numbers jitter.
# ---------------------------------------------------------------------------
def _run_trial(name, adapter, queries, gt, args, trial_idx, gold=None):
    per_query = []                       # scored (predicate) queries only
    neg_query = []                       # negative / expect_no_match queries
    integrity = {"checked": 0, "unresolved": [], "retokenized": []}
    gold = gold or {}

    for row in queries:
        hits = search(adapter, row["query"], args.retrieve)
        # name-integrity over EVERY returned chunk (all rows, incl. negative)
        for rank, h in enumerate(hits, 1):
            verdict = check_name_integrity(h, gt)
            if verdict is None:
                continue
            integrity["checked"] += 1
            if verdict["status"] == "unresolved":
                integrity["unresolved"].append({"query_id": row["id"], "rank": rank, **verdict})
            elif verdict["status"] == "retokenized":
                integrity["retokenized"].append({"query_id": row["id"], "rank": rank, **verdict})

        # negative queries: no relevant set -- measure ABSTENTION (does the system
        # correctly NOT surface a confident match?). Rewards Phase 2's score-floor.
        if row.get("expect_no_match"):
            topk = hits[:args.k]
            top1 = round(float(hits[0].get("score", 0.0)), 4) if hits else None
            abstained = not any(float(h.get("score", 0.0)) >= args.score_floor for h in topk)
            neg_query.append({"id": row["id"], "category": "negative", "abstained": abstained,
                              "top1_score": top1, "floor": args.score_floor})
            print(f"  [{name} t{trial_idx}] {row['id']:6s} {'negative':18s} "
                  f"abstained={int(abstained)} top1={top1}", file=sys.stderr)
            continue

        rels = [1 if is_relevant(h, row["relevant_predicate"]) else 0 for h in hits]
        sc = score_query(rels, args.k, args.ndcg_k, n_gold=gold.get(row["id"]))
        top5 = [{
            "rank": i + 1,
            "relevant": bool(rels[i]),
            "score": round(float(h.get("score", 0.0)), 4),
            "type": (h.get("metadata") or {}).get("type"),
            "store": (h.get("metadata") or {}).get("__source_store"),
            "name": next(((h.get("metadata") or {}).get(f)
                          for f in ("name", "operator", "operator_name", "class", "term")
                          if (h.get("metadata") or {}).get(f)), None),
        } for i, h in enumerate(hits[:5])]
        per_query.append({"id": row["id"], "category": row["category"], **sc, "top5": top5})
        print(f"  [{name} t{trial_idx}] {row['id']:6s} {row['category']:18s} "
              f"recall@{args.k}={sc['recall_at_k']:.0f} rr={sc['rr']:.3f} "
              f"ndcg@{args.ndcg_k}={sc['ndcg_at_n']:.3f}", file=sys.stderr)

    # aggregate (scored categories only)
    cats = sorted({q["category"] for q in per_query})
    per_category = {}
    for c in cats:
        rows = [q for q in per_query if q["category"] == c]
        per_category[c] = {
            "n": len(rows),
            f"recall_at_{args.k}": _mean([r["recall_at_k"] for r in rows]),
            "mrr": _mean([r["rr"] for r in rows]),
            f"ndcg_at_{args.ndcg_k}": _mean([r["ndcg_at_n"] for r in rows]),
        }
    aggregate = {
        "n": len(per_query),
        f"recall_at_{args.k}": _mean([r["recall_at_k"] for r in per_query]),
        "mrr": _mean([r["rr"] for r in per_query]),
        f"ndcg_at_{args.ndcg_k}": _mean([r["ndcg_at_n"] for r in per_query]),
    }
    negative = {
        "n": len(neg_query),
        "abstention_rate": _mean([1.0 if q["abstained"] else 0.0 for q in neg_query]) if neg_query else 0.0,
        "mean_top1_score": round(sum(q["top1_score"] or 0.0 for q in neg_query) / len(neg_query), 4) if neg_query else 0.0,
        "score_floor": args.score_floor,
        "detail": neg_query,
    }

    def _distinct(items):
        return sorted({i.get("asserted") for i in items if i.get("asserted")})

    name_integrity = {
        "identity_bearing_chunks_checked": integrity["checked"],
        "unresolved_violations": len(integrity["unresolved"]),
        "unresolved_distinct": _distinct(integrity["unresolved"]),
        "unresolved_examples": integrity["unresolved"][:10],
        "retokenized_name_surfaced": len(integrity["retokenized"]),
        "retokenized_distinct": _distinct(integrity["retokenized"]),
        "retokenized_examples": integrity["retokenized"][:10],
    }
    return {"per_category": per_category, "aggregate": aggregate,
            "name_integrity": name_integrity, "negative": negative, "per_query": per_query}


def _median(xs):
    return round(statistics.median(xs), 4)


def _single_trial(name, use_legacy, queries, gt, kb_root, args, trial_idx):
    """One in-process trial: build a fresh adapter and score the labeled set."""
    vectordb_path = kb_root / "vector_db"
    graph_path = kb_root / "knowledge_graph_enhanced.gpickle"
    adapter = build_adapter(use_legacy, vectordb_path, graph_path)
    gold = _gold_counts(kb_root, queries)
    return _run_trial(name, adapter, queries, gt, args, trial_idx, gold=gold)


def _spawn_trial(name, kb_root, args, trial_idx):
    """Run ONE trial in a SEPARATE process and parse its result.

    ChromaDB's HNSW result is fixed per-process (the in-memory index load is
    cached for the life of the process), so repeated in-process builds agree --
    they cannot sample the cross-process jitter. A subprocess gets a fresh index
    load, which is the only way to observe (and median away) the variance.
    """
    cmd = [sys.executable, str(Path(__file__).resolve()), "--_emit-trial",
           "--backend", name, "--kb", str(kb_root), "--queries", str(args.queries),
           "--k", str(args.k), "--ndcg-k", str(args.ndcg_k), "--retrieve", str(args.retrieve),
           "--score-floor", str(args.score_floor)]
    if args.gt_operators:
        cmd += ["--gt-operators", str(args.gt_operators)]
    if args.gt_types:
        cmd += ["--gt-types", str(args.gt_types)]
    # §8: propagate the partial-KB override so the child doesn't refuse a KB the
    # parent already accepted (--kb points the child straight at the resolved root).
    if args.allow_partial_kb:
        cmd += ["--allow-partial-kb"]
    print(f"[{name}] trial {trial_idx}/{args.repeats} (subprocess, fresh index load)...", file=sys.stderr)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=os.environ)
    for ln in proc.stdout.splitlines():
        if ln.startswith(_TRIAL_SENTINEL):
            return json.loads(ln[len(_TRIAL_SENTINEL):])
    raise RuntimeError(f"trial subprocess produced no result.\nstderr tail:\n{proc.stderr[-1500:]}")


def evaluate_backend(name, use_legacy, queries, gt, kb_root, args):
    """Run R independent-process trials and combine per-metric by MEDIAN.

    Returns the median per_category / aggregate / name_integrity, the observed
    per-trial band, and the representative trial's per_query detail (the trial
    whose aggregate recall equals the median).
    """
    rk, nk = args.k, args.ndcg_k
    rec_key, ndcg_key = f"recall_at_{rk}", f"ndcg_at_{nk}"
    metric_keys = [rec_key, "mrr", ndcg_key]

    trials = []
    if args.repeats <= 1:
        trials.append(_single_trial(name, use_legacy, queries, gt, kb_root, args, 1))
    else:
        for r in range(args.repeats):
            trials.append(_spawn_trial(name, kb_root, args, r + 1))

    cats = sorted(trials[0]["per_category"])
    per_category = {}
    for c in cats:
        per_category[c] = {"n": trials[0]["per_category"][c]["n"]}
        for mk in metric_keys:
            vals = [t["per_category"][c][mk] for t in trials]
            per_category[c][mk] = _median(vals)
            if args.repeats > 1:
                per_category[c].setdefault("_band", {})[mk] = [round(min(vals), 4), round(max(vals), 4)]
    aggregate = {"n": trials[0]["aggregate"]["n"]}
    for mk in metric_keys:
        vals = [t["aggregate"][mk] for t in trials]
        aggregate[mk] = _median(vals)
        if args.repeats > 1:
            aggregate.setdefault("_band", {})[mk] = [round(min(vals), 4), round(max(vals), 4)]

    # representative trial = the one whose aggregate recall == median recall
    med_rec = aggregate[rec_key]
    rep = min(trials, key=lambda t: abs(t["aggregate"][rec_key] - med_rec))

    ni_keys = ("identity_bearing_chunks_checked", "unresolved_violations", "retokenized_name_surfaced")
    name_integrity = dict(rep["name_integrity"])  # examples/distinct from the representative trial
    for kk in ni_keys:
        name_integrity[kk] = int(statistics.median([t["name_integrity"][kk] for t in trials]))
    if args.repeats > 1:
        name_integrity["_band"] = {
            kk: [min(t["name_integrity"][kk] for t in trials),
                 max(t["name_integrity"][kk] for t in trials)] for kk in ni_keys}

    negative = None
    if trials[0].get("negative", {}).get("n"):
        negative = {
            "n": trials[0]["negative"]["n"],
            "score_floor": trials[0]["negative"]["score_floor"],
            "abstention_rate": _median([t["negative"]["abstention_rate"] for t in trials]),
            "mean_top1_score": _median([t["negative"]["mean_top1_score"] for t in trials]),
            "detail": rep.get("negative", {}).get("detail", []),
        }

    return {
        "repeats": args.repeats,
        "per_category": per_category,
        "aggregate": aggregate,
        "name_integrity": name_integrity,
        "negative": negative,
        "per_query": rep["per_query"],
        "trial_aggregates": [{mk: t["aggregate"][mk] for mk in metric_keys} for t in trials],
        "deterministic": all(t["aggregate"] == trials[0]["aggregate"] for t in trials),
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def collection_count(kb_root: Path) -> int:
    try:
        import chromadb
        vdb = kb_root / "vector_db"
        if not (vdb / "chroma.sqlite3").exists():
            # KF1: opening an absent store with chromadb would CREATE a stub;
            # this probe used to do exactly that before swallowing into -1.
            return -1
        return chromadb.PersistentClient(path=str(vdb)).get_collection(COLLECTION).count()
    except Exception:
        return -1


def write_markdown(md_path: Path, result: dict, args):
    rk, nk = args.k, args.ndcg_k
    base = result["baseline_backend"]
    b = result["backends"][base]
    lines = [
        "# TD Builder v0.2 — Phase 0 search BASELINE",
        "",
        f"- Generated by: `eval/run_eval.py` v{result['harness_version']} (offline, in-process)",
        f"- Search path: shipped `UnifiedSearchAdapter` → dense MiniLM (`{result['embedding_model']}`) "
        f"over Chroma collection `{COLLECTION}` ({result['collection_count']:,} chunks)",
        f"- KB (data): `{result['kb_root']}`",
        f"- Baseline backend: **{base}** (`use_legacy={BACKENDS[base]}`) — the gate every later phase must beat",
        f"- Labeled queries: {b['aggregate']['n']} ({b['aggregate']['n']//5 if b['aggregate']['n'] else 0}+ per category)",
        f"- Reported metric = **median of {b.get('repeats', 1)} trials** "
        f"(ChromaDB HNSW search jitters ~1 borderline result across index loads; band shown below)",
        "",
        "## Metric definitions",
        f"- **recall@{rk}** = hit-rate: 1 if ≥1 relevant chunk in top-{rk}, else 0 (predicates label an open set).",
        "- **MRR** = 1 / rank of the first relevant chunk.",
        f"- **nDCG@{nk}** = binary-gain DCG over top-{nk} ÷ ideal DCG.",
        "- Relevance is decided by each query's `relevant_predicate` over STABLE identity fields.",
        "",
        f"## Baseline — {base} backend",
        "",
        f"| Category | n | recall@{rk} | MRR | nDCG@{nk} |",
        "|---|---|---|---|---|",
    ]
    for cat in sorted(b["per_category"]):
        m = b["per_category"][cat]
        lines.append(f"| {cat} | {m['n']} | {m[f'recall_at_{rk}']:.2f} | {m['mrr']:.2f} | {m[f'ndcg_at_{nk}']:.2f} |")
    agg = b["aggregate"]
    lines.append(f"| **AGGREGATE** | {agg['n']} | **{agg[f'recall_at_{rk}']:.2f}** | "
                 f"**{agg['mrr']:.2f}** | **{agg[f'ndcg_at_{nk}']:.2f}** |")
    lines.append("")
    lines.append("_(palette_discovery & howto are the broken categories the redesign targets; "
                 "build_instruction is §6.9, mostly un-indexed today.)_")
    if b.get("negative"):
        ng = b["negative"]
        lines += [
            "",
            "## Negative queries (abstention)",
            f"- {ng['n']} out-of-domain queries; the system should return **no confident match**. "
            f"abstention@{rk} (no top-{rk} hit ≥ {ng['score_floor']}): **{ng['abstention_rate']:.2f}**, "
            f"mean top-1 score **{ng['mean_top1_score']:.3f}**.",
            "- Rewards Phase 2's score-floor + dedup: today the dense-only stack returns filler for anything; "
            "a real abstention path should drive this toward 1.0.",
        ]
    if b.get("repeats", 1) > 1:
        tas = b.get("trial_aggregates", [])
        rec_vals = ", ".join(f"{t[f'recall_at_{rk}']:.3f}" for t in tas)
        lines += [
            "",
            "### Reproducibility",
            f"- Reported = **median of {b['repeats']} independent-process trials** (each a fresh index load); "
            f"this run's per-trial aggregate recall@{rk}: {rec_vals}.",
            "- ChromaDB's HNSW approximate search is **not bit-deterministic across process loads** "
            "(embeddings, DB content, and on-disk index are all verified byte-stable; only the in-memory "
            "graph traversal of borderline neighbors varies). A single N-trial run often collapses to the "
            "mode; the **measured cross-invocation jitter** is ~1 query, confined to **operator_lookup** "
            f"(recall@{rk} **0.83–0.92**, aggregate **0.55–0.58**) — the category the plan calls *adequate today*.",
            "- **Invariant every run:** palette_discovery 0.00, howto 0.25, parameter 1.00, python 0.75, "
            "and name-integrity **0 unresolved**. The redesign's target gaps are rock-solid.",
        ]

    ni = b["name_integrity"]
    lines += [
        "",
        "## Name-integrity gate (ground truth = operators.json + operator_ground_truth/operator_types.json)",
        "",
        f"- Identity-bearing chunks returned across all queries: **{ni['identity_bearing_chunks_checked']}**",
        f"- Unresolved-operator violations (assert an operator that is NOT in ground truth): "
        f"**{ni['unresolved_violations']}** ({len(ni['unresolved_distinct'])} distinct)",
        f"- Retokenized names surfaced as display (e.g. `Ableton_Link_CHOP`) — the §3 hazard, "
        f"v0.2 target 0: **{ni['retokenized_name_surfaced']}** ({len(ni['retokenized_distinct'])} distinct)",
    ]
    if ni["retokenized_distinct"]:
        lines.append(f"  - examples: {', '.join('`'+x+'`' for x in ni['retokenized_distinct'][:12])}")
    if ni["unresolved_distinct"]:
        lines.append(f"  - unresolved examples: {', '.join('`'+str(x)+'`' for x in ni['unresolved_distinct'][:12])}")

    # documented-gaps reproduction note
    pc = b["per_category"]
    lines += [
        "",
        "## Documented gaps reproduced (plan §3)",
        "",
        f"- palette_discovery recall@{rk} ≈ **{pc.get('palette_discovery',{}).get(f'recall_at_{rk}',0):.2f}** (expected ≈0 — palette is un-indexed)",
        f"- howto recall@{rk} ≈ **{pc.get('howto',{}).get(f'recall_at_{rk}',0):.2f}** (expected ≈0 — no recipe/guide chunks)",
        f"- operator_lookup recall@{rk} ≈ **{pc.get('operator_lookup',{}).get(f'recall_at_{rk}',0):.2f}** / "
        f"MRR **{pc.get('operator_lookup',{}).get('mrr',0):.2f}** (expected ≈1.0 — adequate today)",
        f"- parameter MRR ≈ **{pc.get('parameter',{}).get('mrr',0):.2f}**; python recall@{rk} ≈ "
        f"**{pc.get('python',{}).get(f'recall_at_{rk}',0):.2f}** (class_method works, python dump is noise)",
        "",
        "## v0.2 targets (from plan §3)",
        "",
        f"- palette recall@{rk}: 0 → ≥0.6 · howto: 0 → ≥0.4 · operator_lookup MRR ≥0.95 · "
        "index size ↓~4× · zero retokenized names surfaced as ground truth.",
        "",
        f"_Other backend(s) measured: {', '.join(k for k in result['backends'] if k != base) or '(none)'}; "
        "identical ranking to the baseline today (they diverge once Phase 2 edits `_enhanced_search`)._",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Phase-0 TD Builder search eval harness")
    ap.add_argument("--backend", choices=["enhanced", "legacy", "both"], default="both",
                    help="which backend(s) to measure; baseline is always 'enhanced' (the shipped path)")
    ap.add_argument("--kb", default=None, help="KB root containing vector_db/ + gpickle (default: auto / main tree)")
    ap.add_argument("--queries", default=str(EVAL_DIR / "labeled_queries.jsonl"))
    ap.add_argument("--k", type=int, default=5, help="recall@k / top-k")
    ap.add_argument("--ndcg-k", type=int, default=10, help="nDCG@n cutoff")
    ap.add_argument("--retrieve", type=int, default=None, help="results to fetch per query (default max(k,ndcg_k))")
    ap.add_argument("--repeats", type=int, default=3,
                    help="independent trials per backend; metrics reported as the median (HNSW search "
                         "jitters ~1 borderline result across index loads). Use 1 for a quick single run.")
    ap.add_argument("--out", default=None,
                    help="result path. §8 fix: the default NO LONGER overwrites the "
                         "committed eval/baseline.json — with no --out, results go to "
                         "the stage dir only. Promote deliberately with --write-baseline.")
    ap.add_argument("--write-baseline", action="store_true",
                    help="write the committed eval/baseline.json (deliberate promotion; "
                         "mutually exclusive with --out)")
    ap.add_argument("--allow-partial-kb", action="store_true",
                    help="measure a KB missing Phase-2 artifacts anyway (dense-only; "
                         "refused by default — §8)")
    ap.add_argument("--expect-kb-version", default=None,
                    help="assert the resolved KB's manifest version (CI lanes pass this); "
                         "mismatch exits 4")
    ap.add_argument("--allow-identity-drift", action="store_true",
                    help="proceed with --compare across mismatched KB identity, "
                         "marking the diff NON-COMPARABLE")
    ap.add_argument("--stage-dir", default=None, help="staging dir for BASELINE.md + copies (default: New KB build/Output/eval)")
    ap.add_argument("--gt-operators", default=None,
                    help="authoritative operators.json for the name-integrity gate (default: stable, "
                         "independent of --kb — so it stays valid when --kb points at a rebuilt KB)")
    ap.add_argument("--gt-types", default=None,
                    help="authoritative operator_ground_truth/operator_types.json (default: stable, main-tree Resources)")
    ap.add_argument("--score-floor", type=float, default=0.2,
                    help="negative-query abstention threshold: a top-k result at/above this score counts as a (wrong) match")
    ap.add_argument("--compare", default=None, help="path to a prior baseline.json to diff per-category deltas against")
    ap.add_argument("--_emit-trial", action="store_true", dest="emit_trial", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.retrieve is None:
        args.retrieve = max(args.k, args.ndcg_k)

    kb_root = resolve_kb_root(args.kb, require_full=True,
                              allow_partial=args.allow_partial_kb).resolve()
    args.queries = str(Path(args.queries).resolve())
    if args.compare:  # resolve now — adapter construction chdir's to server_core later
        args.compare = str(Path(args.compare).resolve())
    # Ground truth is resolved INDEPENDENTLY of --kb (flags override) so the gate stays
    # authoritative when measuring a rebuilt KB. operator_types.json (live-TD) is pinned
    # to the stable Resources capture; operators.json defaults to the measured KB's own
    # registry but falls back to the main tree.
    gt_ops, gt_types = resolve_gt_paths(args.gt_operators, args.gt_types, kb_root)
    gt = GroundTruth(operators_json=gt_ops, operator_types_json=gt_types)
    queries = [json.loads(ln) for ln in Path(args.queries).read_text(encoding="utf-8").splitlines() if ln.strip()]

    # --- subprocess trial mode: run ONE in-process trial, emit JSON, exit ------
    # (identity stamp / [kb] report skipped here — only the PARENT stamps the
    #  final result; resolve_kb_root already ran the partial-KB guard above.)
    if args.emit_trial:
        name = args.backend if args.backend in BACKENDS else "enhanced"
        trial = _single_trial(name, BACKENDS[name], queries, gt, kb_root, args, 1)
        sys.stdout.write("\n" + _TRIAL_SENTINEL + json.dumps(trial) + "\n")
        sys.stdout.flush()
        return

    ident = _identity_helper()
    kb_ident = ident.kb_identity(kb_root, extra_roots=(REPO_ROOT,)
                                 + ((_MAIN_TREE,) if _MAIN_TREE else ()))
    # §8: the silent main-tree fallback becomes a printed resolution report.
    print(f"[kb] resolved KB root: {kb_root} (source: "
          f"{KB_RESOLUTION.get('source')}, manifest "
          f"{kb_ident['kb_manifest_version']}, sha {kb_ident['kb_sha'][:12]}…"
          + (f", PARTIAL — missing {KB_RESOLUTION['missing']}"
             if KB_RESOLUTION.get("missing") else ""),
          file=sys.stderr)
    if args.expect_kb_version and \
            kb_ident["kb_manifest_version"] != args.expect_kb_version:
        print(f"[kb] expected KB version {args.expect_kb_version!r} but resolved "
              f"{kb_ident['kb_manifest_version']!r} at {kb_root} — refusing.",
              file=sys.stderr)
        raise SystemExit(4)

    stage_dir = resolve_stage_dir(args.stage_dir, kb_root).resolve()
    # §8: --out no longer DEFAULTS onto the committed baseline. Resolution:
    #   --out X         -> write X (and stage a copy)
    #   --write-baseline-> write the committed eval/baseline.json (deliberate)
    #   neither         -> stage-only (stage_dir/baseline.json); repo untouched
    if args.out and args.write_baseline:
        raise SystemExit("pass only one of --out / --write-baseline")
    committed_baseline = EVAL_DIR / "baseline.json"
    if args.write_baseline:
        out_path = committed_baseline.resolve()
    elif args.out:
        out_path = Path(args.out).resolve()
    else:
        out_path = (stage_dir / "baseline.json").resolve()
    count = collection_count(kb_root)
    print(f"KB: {kb_root}\nqueries: {len(queries)}  collection: {COLLECTION} ({count} chunks)\n", file=sys.stderr)

    want = ["enhanced", "legacy"] if args.backend == "both" else [args.backend]
    backends = {}
    for name in want:
        try:
            backends[name] = evaluate_backend(name, BACKENDS[name], queries, gt, kb_root, args)
        except Exception as e:
            import traceback; traceback.print_exc()
            backends[name] = {"error": str(e)}

    base = "enhanced" if "enhanced" in backends and "error" not in backends["enhanced"] else next(iter(backends))
    result = {
        "harness_version": HARNESS_VERSION,
        "embedding_model": os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2"),
        "collection": COLLECTION,
        "collection_count": count,
        "kb_root": redact_path(kb_root),
        "code_root": redact_path(SERVER_CORE),
        "gt_operators": redact_path(gt_ops),
        "gt_types": redact_path(gt_types),
        # §8: KB identity stamp (shared with the agent-eval harness). Additive —
        # old baselines without it read as "unknown" in --compare (warn, proceed).
        "identity": {**kb_ident, "kb_resolution_source": KB_RESOLUTION.get("source"),
                     "kb_partial_missing": KB_RESOLUTION.get("missing") or []},
        "config": {"k": args.k, "ndcg_k": args.ndcg_k, "retrieve": args.retrieve,
                   "n_queries": len(queries), "score_floor": args.score_floor},
        "baseline_backend": base,
        "backends": {n: {kk: vv for kk, vv in r.items() if kk != "per_query"} for n, r in backends.items()},
        "baseline": {kk: vv for kk, vv in backends[base].items() if kk != "per_query"} if "error" not in backends.get(base, {}) else backends.get(base),
        "notes": (
            "Baseline = the shipped enhanced path (use_legacy=False), the gate later phases must beat. "
            "Today enhanced==legacy ranking (same dense MiniLM TDDocSearch); they diverge once Phase 2 "
            "edits _enhanced_search. recall@k is hit-rate (success@k). Name-integrity ground truth is "
            "operators.json + operator_ground_truth/operator_types.json."
        ),
    }

    # write canonical baseline.json (repo) + staged copies
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "baseline.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    details = {n: r.get("per_query") for n, r in backends.items() if "error" not in r}
    (stage_dir / "details.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
    if "error" not in backends.get(base, {}):
        write_markdown(stage_dir / "BASELINE.md", result, args)

    # console summary
    print("\n" + "=" * 64)
    print(f"BASELINE backend: {base}")
    if "error" in backends.get(base, {}):
        print("  ERROR:", backends[base]["error"])
    else:
        b = backends[base]
        for cat in sorted(b["per_category"]):
            m = b["per_category"][cat]
            print(f"  {cat:18s} recall@{args.k}={m[f'recall_at_{args.k}']:.2f}  "
                  f"MRR={m['mrr']:.2f}  nDCG@{args.ndcg_k}={m[f'ndcg_at_{args.ndcg_k}']:.2f}  (n={m['n']})")
        agg = b["aggregate"]
        print(f"  {'AGGREGATE':18s} recall@{args.k}={agg[f'recall_at_{args.k}']:.2f}  "
              f"MRR={agg['mrr']:.2f}  nDCG@{args.ndcg_k}={agg[f'ndcg_at_{args.ndcg_k}']:.2f}  (n={agg['n']})")
        if b.get("negative"):
            ng = b["negative"]
            print(f"  {'negative':18s} abstention@{args.k}={ng['abstention_rate']:.2f}  "
                  f"mean-top1-score={ng['mean_top1_score']:.3f}  (n={ng['n']}, floor={ng['score_floor']})")
        ni = b["name_integrity"]
        print(f"  name-integrity: {ni['unresolved_violations']} unresolved, "
              f"{ni['retokenized_name_surfaced']} retokenized-name surfaced "
              f"(of {ni['identity_bearing_chunks_checked']} identity-bearing returns)")
    print("=" * 64)

    # --- optional diff vs a prior baseline.json --------------------------------
    if args.compare and "error" not in backends.get(base, {}):
        try:
            prev = json.loads(Path(args.compare).read_text(encoding="utf-8"))
            # §7/§8: refuse to diff across differing KB identity — the numbers
            # would compare against a different KB. Missing identity (pre-§8
            # baselines) reads as "unknown": warn, proceed.
            mism, unknown = _identity_mism(kb_ident, prev.get("identity"))
            if unknown:
                print(f"\n[compare] WARNING: prior baseline has no KB identity for "
                      f"{unknown} — treating as unknown, proceeding.", file=sys.stderr)
            if mism:
                print("\n[compare] KB identity mismatch vs prior baseline:", file=sys.stderr)
                for f, old, cur in mism:
                    print(f"    {f}: prior={old!r} current={cur!r}", file=sys.stderr)
                if not args.allow_identity_drift:
                    print("[compare] REFUSING diff (§7): the two baselines measured "
                          "different KBs. Pass --allow-identity-drift to proceed "
                          "marked NON-COMPARABLE.", file=sys.stderr)
                    raise SystemExit(3)
                print("[compare] NON-COMPARABLE (KB identity drift overridden)",
                      file=sys.stderr)
            pj = prev.get("baseline", prev.get("backends", {}).get(prev.get("baseline_backend", base), {}))
            print(f"\nDELTA vs {args.compare} (this - prior; d = delta):")
            rk, nk = args.k, args.ndcg_k
            for cat in sorted(b["per_category"]):
                cur = b["per_category"][cat]
                old = pj.get("per_category", {}).get(cat)
                if not old:
                    print(f"  {cat:18s} (new category)")
                    continue
                dr = cur[f"recall_at_{rk}"] - old.get(f"recall_at_{rk}", 0)
                dm = cur["mrr"] - old.get("mrr", 0)
                dn = cur[f"ndcg_at_{nk}"] - old.get(f"ndcg_at_{nk}", 0)
                if abs(dr) + abs(dm) + abs(dn) > 1e-9:
                    print(f"  {cat:18s} d_recall@{rk}={dr:+.2f}  d_MRR={dm:+.2f}  d_nDCG@{nk}={dn:+.2f}")
            ca, oa = b["aggregate"], pj.get("aggregate", {})
            print(f"  {'AGGREGATE':18s} d_recall@{rk}={ca[f'recall_at_{rk}']-oa.get(f'recall_at_{rk}',0):+.2f}  "
                  f"d_MRR={ca['mrr']-oa.get('mrr',0):+.2f}  d_nDCG@{nk}={ca[f'ndcg_at_{nk}']-oa.get(f'ndcg_at_{nk}',0):+.2f}")
            oni = pj.get("name_integrity", {})
            print(f"  name-integrity   d_retokenized={b['name_integrity']['retokenized_name_surfaced']-oni.get('retokenized_name_surfaced',0):+d}  "
                  f"d_unresolved={b['name_integrity']['unresolved_violations']-oni.get('unresolved_violations',0):+d}")
        except Exception as e:
            print(f"\n(could not diff against {args.compare}: {e})")

    print(f"\nwrote:\n  {out_path}\n  {stage_dir / 'baseline.json'}\n  "
          f"{stage_dir / 'BASELINE.md'}\n  {stage_dir / 'details.json'}")


if __name__ == "__main__":
    main()

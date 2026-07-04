#!/usr/bin/env python3
"""CI eval non-regression gate (kb-full lane; created by harness remediation W1).

run_eval.py has no pass/fail semantics of its own (its --compare only prints
deltas), and it overwrites eval/baseline.json in place when run with defaults
(known wart; the real fix rides work item 2c). The CI lane therefore runs

    python eval/run_eval.py --backend enhanced --repeats 3 \
        --out  <tmp>/candidate.json --stage-dir <tmp>/stage \
        --gt-types eval/ground_truth/operator_types.json

and this script turns "candidate vs the committed eval/baseline.json" into an
exit code.

Tolerances (constants below) and why:
  * AGG_TOL 0.02  -- aggregate recall@k / MRR / nDCG@n may drop at most 0.02.
    The committed baseline's median-of-3 jitter band is degenerate
    (deterministic capture), so 0.02 is pure headroom for runner-vs-local
    float drift (different BLAS/OS); the lane runs on windows-latest to keep
    that drift minimal.
  * CAT_TOL 0.05  -- per-category metrics are over n=12 queries, so one
    borderline flip moves recall by 0.083; 0.05 still catches a flip while
    tolerating sub-flip score drift on MRR/nDCG.
  * name-integrity counts and negative-query abstention are STRICT
    (candidate must not be worse): both are 0-violations / 1.0 in the
    committed baseline and deterministic. If the first hosted runs show
    honest drift here, loosening is an owner-blessed edit to this file.

collection_count differences are WARN-only: a KB re-release legitimately
changes chunk counts (the cache key rotates via scripts/vector_db_release.json).
A config.n_queries mismatch is a hard FAIL: it means the two files scored
different query sets and the comparison is meaningless.

Usage:
    python scripts/ci_compare_eval.py <committed_baseline.json> <candidate.json>
Exit codes: 0 pass, 1 regression/malformed comparison, 2 usage/self-error.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

AGG_TOL = 0.02
CAT_TOL = 0.05

_METRIC_KEY = re.compile(r"^(?:recall_at_\d+|mrr|ndcg_at_\d+)$")


def _metrics_block(doc: dict, label: str) -> dict:
    """The canonical backend's metrics: prefer the 'baseline' copy."""
    block = doc.get("baseline")
    if not block:
        backend = doc.get("baseline_backend")
        block = (doc.get("backends") or {}).get(backend)
    if not block:
        raise ValueError(f"{label}: no 'baseline' block and no backends[baseline_backend]")
    return block


def _metric_names(agg: dict) -> list[str]:
    return sorted(k for k in agg if _METRIC_KEY.match(k))


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: python scripts/ci_compare_eval.py <committed_baseline.json> <candidate.json>",
              file=sys.stderr)
        return 2
    try:
        committed = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        candidate = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ci_compare_eval: cannot load inputs ({exc})", file=sys.stderr)
        return 2

    rows: list[tuple[str, str, str, float | int, float | int, str]] = []
    failures = 0
    warns = 0

    def check(scope: str, metric: str, comm, cand, ok: bool, warn_only: bool = False) -> None:
        nonlocal failures, warns
        status = "PASS" if ok else ("WARN" if warn_only else "FAIL")
        if not ok:
            if warn_only:
                warns += 1
            else:
                failures += 1
        rows.append((status, scope, metric, comm, cand, ""))

    try:
        comm_b = _metrics_block(committed, "committed")
        cand_b = _metrics_block(candidate, "candidate")
    except ValueError as exc:
        print(f"ci_compare_eval: {exc}", file=sys.stderr)
        return 1

    # Same experiment? Different query sets are not comparable.
    comm_nq = (committed.get("config") or {}).get("n_queries")
    cand_nq = (candidate.get("config") or {}).get("n_queries")
    check("config", "n_queries", comm_nq, cand_nq, comm_nq == cand_nq)

    comm_cc = committed.get("collection_count")
    cand_cc = candidate.get("collection_count")
    check("config", "collection_count", comm_cc, cand_cc, comm_cc == cand_cc, warn_only=True)

    # Aggregate metrics.
    comm_agg, cand_agg = comm_b.get("aggregate") or {}, cand_b.get("aggregate") or {}
    names = _metric_names(comm_agg)
    if not names:
        print("ci_compare_eval: committed aggregate has no recognizable metrics", file=sys.stderr)
        return 1
    for m in names:
        comm_v, cand_v = comm_agg.get(m), cand_agg.get(m)
        check("aggregate", m, comm_v, cand_v,
              isinstance(cand_v, (int, float)) and cand_v >= comm_v - AGG_TOL)

    # Per-category metrics: every committed category must exist and hold.
    comm_cats = comm_b.get("per_category") or {}
    cand_cats = cand_b.get("per_category") or {}
    for cat, comm_metrics in sorted(comm_cats.items()):
        cand_metrics = cand_cats.get(cat)
        if cand_metrics is None:
            check(f"category:{cat}", "(present)", "yes", "MISSING", False)
            continue
        for m in _metric_names(comm_metrics):
            comm_v, cand_v = comm_metrics.get(m), cand_metrics.get(m)
            check(f"category:{cat}", m, comm_v, cand_v,
                  isinstance(cand_v, (int, float)) and cand_v >= comm_v - CAT_TOL)

    # Name integrity: strictly no worse than committed (both 0 today).
    comm_ni, cand_ni = comm_b.get("name_integrity") or {}, cand_b.get("name_integrity") or {}
    for m in ("unresolved_violations", "retokenized_name_surfaced"):
        comm_v, cand_v = comm_ni.get(m, 0), cand_ni.get(m)
        check("name_integrity", m, comm_v, cand_v,
              isinstance(cand_v, (int, float)) and cand_v <= comm_v)

    # Negative-query abstention: strictly no worse (1.0 and deterministic today).
    comm_neg, cand_neg = comm_b.get("negative") or {}, cand_b.get("negative") or {}
    if "abstention_rate" in comm_neg:
        comm_v, cand_v = comm_neg["abstention_rate"], cand_neg.get("abstention_rate")
        check("negative", "abstention_rate", comm_v, cand_v,
              isinstance(cand_v, (int, float)) and cand_v >= comm_v)

    width = max(len(r[1]) for r in rows)
    print(f"{'':4s} {'scope':{width}s} {'metric':28s} {'committed':>10s} {'candidate':>10s}")
    for status, scope, metric, comm_v, cand_v, _ in rows:
        print(f"{status:4s} {scope:{width}s} {metric:28s} {str(comm_v):>10s} {str(cand_v):>10s}")
    print(f"ci_compare_eval: {failures} failure(s), {warns} warning(s) "
          f"(AGG_TOL={AGG_TOL}, CAT_TOL={CAT_TOL})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

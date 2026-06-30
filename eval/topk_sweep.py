#!/usr/bin/env python3
r"""
Top-k sweep: slice recall@{5,6,8,10} from ONE full-stack run per set.

The retrieval stack produces a single ranked list per query; recall@k is just
reading that list at different cutoffs. So we run run_eval ONCE per set at
`--retrieve 15 --k 10` (rerank + floor + dedup applied as normal) and read the
`first_relevant_rank` it records per query (in details.json). recall@k =
fraction of scored queries with first_relevant_rank <= k.

  * MRR is k-invariant -> reported once.
  * Negative abstention is monotonic in k: a wider top-k can only ADD a chance to
    breach the floor, never remove one. So abstention@10 == 1.00 (from the --k 10
    run's baseline.json) PROVES abstention@k == 1.00 for every k <= 10.

This DOES NOT touch the eval gate (which stays recall@5). It only informs the
runtime hybrid_search default n_results.

Usage:
  py -3.11 eval/topk_sweep.py \
    --set heldout  <details.json> <baseline.json> <queries.jsonl> \
    --set frozen78 <details.json> <baseline.json> <queries.jsonl> \
    --out "<...>/TOPK_SWEEP.md"
"""
from __future__ import annotations
import argparse, io, json, sys
from collections import defaultdict
from pathlib import Path

KS = [5, 6, 8, 10]
TOK_PER_RESULT = 150          # v0.2 condensed chunk ~150 tok (parameter_group ~250-440)


def _load_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def gold_of(q):
    for cl in (q.get("relevant_predicate") or {}).get("clauses", []):
        for k in ("op_name_any", "python_class_any", "meta_name_any", "term_any", "method_any"):
            if cl.get(k):
                return cl[k][0]
    return "?"


def analyze(details_path, baseline_path, queries_path, backend="enhanced"):
    details = json.loads(Path(details_path).read_text(encoding="utf-8"))
    pq = details.get(backend) or next(iter(details.values()))
    base = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    qmap = {q["id"]: q for q in _load_jsonl(queries_path)}

    cats = sorted({r["category"] for r in pq})
    # recall@k per category + aggregate, from first_relevant_rank
    def recall(rows, k):
        if not rows:
            return None
        hit = sum(1 for r in rows if r.get("first_relevant_rank") and r["first_relevant_rank"] <= k)
        return hit / len(rows)
    percat = {}
    for c in cats:
        rows = [r for r in pq if r["category"] == c]
        percat[c] = {k: recall(rows, k) for k in KS}
        percat[c]["mrr"] = round(sum(r["rr"] for r in rows) / len(rows), 3)
        percat[c]["n"] = len(rows)
    agg = {k: recall(pq, k) for k in KS}
    agg["mrr"] = round(sum(r["rr"] for r in pq) / len(pq), 3)
    agg["n"] = len(pq)

    # recovered queries per step: first_relevant_rank exactly in the step's band
    bands = {"5->6": [6], "6->8": [7, 8], "8->10": [9, 10]}
    recovered = {step: [] for step in bands}
    misses_after10 = []
    for r in pq:
        frr = r.get("first_relevant_rank")
        for step, rr in bands.items():
            if frr in rr:
                recovered[step].append({"id": r["id"], "category": r["category"],
                                        "rank": frr, "gold": gold_of(qmap.get(r["id"], {}))})
        if not frr or frr > 10:
            misses_after10.append({"id": r["id"], "category": r["category"], "rank": frr,
                                   "gold": gold_of(qmap.get(r["id"], {}))})

    b = base.get("baseline") or base.get("backends", {}).get(backend, {})
    neg = b.get("negative") or {}
    cfg = base.get("config", {})
    return {"percat": percat, "agg": agg, "recovered": recovered, "misses_after10": misses_after10,
            "neg_abstention": neg.get("abstention_rate"), "neg_n": neg.get("n"),
            "neg_floor": neg.get("score_floor"), "run_k": cfg.get("k"), "retrieve": cfg.get("retrieve"),
            "name_integrity": b.get("name_integrity", {})}


def _row(label, d):
    cells = []
    for k in KS:
        v = d.get(k)
        cells.append(f"{v:.2f}" if v is not None else "—")
    d56 = (d[6] - d[5]) if d.get(5) is not None and d.get(6) is not None else 0
    d68 = (d[8] - d[6]) if d.get(6) is not None and d.get(8) is not None else 0
    d810 = (d[10] - d[8]) if d.get(8) is not None and d.get(10) is not None else 0
    return (f"| {label} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | "
            f"{d56:+.3f} | {d68:+.3f} | {d810:+.3f} |")


def section(name, A):
    L = [f"## {name} (run: --retrieve {A['retrieve']} --k {A['run_k']}, full stack)", "",
         f"| category | recall@5 | @6 | @8 | @10 | Δ5→6 | Δ6→8 | Δ8→10 |", "|---|---|---|---|---|---|---|---|"]
    for c in sorted(A["percat"]):
        L.append(_row(c, A["percat"][c]))
    L.append(_row("**AGGREGATE**", A["agg"]).replace("AGGREGATE", "**AGGREGATE**"))
    L += ["", f"_MRR (k-invariant): aggregate **{A['agg']['mrr']}** · per-cat "
          + ", ".join(f"{c} {A['percat'][c]['mrr']}" for c in sorted(A['percat'])) + "._", ""]
    # recovered queries
    for step, items in A["recovered"].items():
        if items:
            L.append(f"- **recovered at {step}** ({len(items)}): "
                     + ", ".join(f"`{it['id']}`→{it['gold']} (rank {it['rank']})" for it in items))
    if A["misses_after10"]:
        L.append(f"- **still missed at @10** ({len(A['misses_after10'])}): "
                 + ", ".join(f"`{it['id']}`→{it['gold']} (rank {it['rank']})" for it in A["misses_after10"]))
    L.append(f"- **negative abstention@{A['run_k']} = {A['neg_abstention']:.2f}** "
             f"({A['neg_n']} negatives, floor {A['neg_floor']}) — monotonic ⇒ holds at every k≤{A['run_k']}. "
             f"name-integrity {A['name_integrity'].get('unresolved_violations','?')}u/"
             f"{A['name_integrity'].get('retokenized_name_surfaced','?')}r.")
    L.append("")
    return L


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", nargs=4, action="append", metavar=("NAME", "DETAILS", "BASELINE", "QUERIES"),
                    required=True, help="repeatable: NAME details.json baseline.json queries.jsonl")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    analyses = [(s[0], analyze(s[1], s[2], s[3])) for s in args.set]

    L = ["# v0.2 — runtime top-k sweep (recall@5/6/8/10)", "",
         "_Decides the **runtime** `hybrid_search` default `n_results` by measuring marginal recall gain per "
         "extra result. The **eval gate stays recall@5** — `--k` in the committed harness is unchanged; this "
         "only informs the runtime default. One full-stack run per set at retrieve depth 15, recall@k sliced "
         "from `first_relevant_rank`._", ""]
    for name, A in analyses:
        L += section(name, A)

    # token-cost table (use the decisive held-out aggregate if present, else first set)
    dec = next((A for n, A in analyses if "held" in n.lower()), analyses[0][1])
    L += ["## Recall gain vs token cost (held-out AGGREGATE)", "",
          f"Each extra result ≈ **+{TOK_PER_RESULT} tok/search** (v0.2 condensed chunk; parameter_group "
          "~250–440). Marginal recall per step and its token price:", "",
          "| step | Δrecall (held-out agg) | +tok/search | recall-gain per +1k tok |", "|---|---|---|---|"]
    for step, k0, k1 in [("5→6", 5, 6), ("6→8", 6, 8), ("8→10", 8, 10)]:
        dr = dec["agg"][k1] - dec["agg"][k0]
        extra = (k1 - k0) * TOK_PER_RESULT
        per1k = (dr / extra * 1000) if extra else 0
        L.append(f"| {step} | {dr:+.3f} | +{extra} | {per1k:+.3f} |")
    L += ["", "_(per-result tokens are an average; a parameter-heavy result can be ~250–440 tok, so a "
          "+1 step is ~150–440 tok in practice.)_", ""]
    Path(args.out).write_text("\n".join(L) + "\n", encoding="utf-8")

    # console
    for name, A in analyses:
        a = A["agg"]
        print(f"[{name}] recall@5={a[5]:.3f} @6={a[6]:.3f} @8={a[8]:.3f} @10={a[10]:.3f} "
              f"(Δ5→6 {a[6]-a[5]:+.3f}, Δ6→8 {a[8]-a[6]:+.3f}, Δ8→10 {a[10]-a[8]:+.3f}) "
              f"MRR={a['mrr']} | neg-abstention@{A['run_k']}={A['neg_abstention']}")
        for step, items in A["recovered"].items():
            if items:
                print(f"   recovered {step}: " + ", ".join(f"{it['id']}({it['rank']})" for it in items))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

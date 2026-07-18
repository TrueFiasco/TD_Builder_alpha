#!/usr/bin/env python3
r"""
Coverage-tier reporter: per-FAMILY / per-CHUNK-TYPE / per-PARAM-KIND breakdowns
that ``run_eval.py`` (category-only) does not produce, with the Phase-0.6b
ambiguity model baked in.

SEARCH-FREE: joins ``run_eval``'s ``details.json`` (per-query scores) with
``coverage_queries.jsonl`` (the ``gen`` block: family/kind/chunk_type/ambiguity)
on ``id``. Aggregate / negatives / name-integrity come from ``baseline.json``.

Key reporting rules (match the generator's guarantees):
  * UNAMBIGUOUS slice = items tagged ambiguity in {unique, disambiguated}. Its
    recall/MRR/nDCG are the headline.
  * MULTI slice = ambiguity=="multi" (accept-set OR-predicate). Reported SEPARATELY
    as SET-recall / SET-MRR — never folded into the single-gold MRR.
  * Negatives split EASY vs HARD (TD-adjacent) abstention.

Run order:
    py -3.11 eval/gen_coverage.py --seed 0
    # then run_eval on the chosen backend (Phase-2 stack recommended), staging to .../coverage
    py -3.11 eval/coverage_report.py --seed 0 --stack "Phase-2 retrieval_stack" \
        --queries eval/coverage_queries.jsonl \
        --details  ".../coverage/details.json" \
        --baseline ".../coverage/coverage_baseline.json" \
        --out      ".../coverage/COVERAGE.md"
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def _load_jsonl(p: Path):
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _mean(xs):
    return round(sum(xs) / len(xs), 3) if xs else 0.0


def aggregate_by(rows, group_fn):
    groups = defaultdict(list)
    for r in rows:
        g = group_fn(r)
        if g is not None:
            groups[g].append(r)
    out = {}
    for g, rs in groups.items():
        out[g] = {"n": len(rs),
                  "recall": _mean([r["recall_at_k"] for r in rs]),
                  "mrr": _mean([r["rr"] for r in rs]),
                  "ndcg": _mean([r["ndcg_at_n"] for r in rs])}
    return out


def _agg(rows):
    return {"n": len(rows), "recall": _mean([r["recall_at_k"] for r in rows]),
            "mrr": _mean([r["rr"] for r in rows]), "ndcg": _mean([r["ndcg_at_n"] for r in rows])}


def _table(title, d, k, nk, label="group", metric="recall@{k}"):
    rk = metric.format(k=k)
    lines = [f"### {title}", "", f"| {label} | n | {rk} | MRR | nDCG@{nk} |", "|---|---|---|---|---|"]
    for g in sorted(d, key=lambda x: (-d[x]["n"], str(x))):
        m = d[g]
        lines.append(f"| {g} | {m['n']} | {m['recall']:.2f} | {m['mrr']:.2f} | {m['ndcg']:.2f} |")
    lines.append("")
    return lines


def main():
    ap = argparse.ArgumentParser(description="Coverage-tier reporter (ambiguity-aware)")
    ap.add_argument("--queries", default=str(Path(__file__).resolve().parent / "coverage_queries.jsonl"))
    ap.add_argument("--details", default=None, help="run_eval details.json (optional; omit for coverage-only report)")
    ap.add_argument("--baseline", default=None, help="run_eval baseline.json (optional)")
    ap.add_argument("--backend", default="enhanced")
    ap.add_argument("--out", default=None)
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--stack", default=None,
                    help="retrieval-path label, e.g. 'Phase-2 retrieval_stack' or 'baseline dense MiniLM'")
    ap.add_argument("--coverage-meta", default=None,
                    help="coverage_meta.json from gen_coverage (default: alongside --queries)")
    args = ap.parse_args()

    queries = {q["id"]: q for q in _load_jsonl(Path(args.queries))}
    cm_path = Path(args.coverage_meta) if args.coverage_meta else Path(args.queries).with_name("coverage_meta.json")
    cm = json.loads(cm_path.read_text(encoding="utf-8")) if cm_path.exists() else None

    have_measure = bool(args.details and Path(args.details).exists())
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8")) if (args.baseline and Path(args.baseline).exists()) else {}
    details = json.loads(Path(args.details).read_text(encoding="utf-8")) if have_measure else {}

    cfg = baseline.get("config", {})
    k, nk = cfg.get("k", 5), cfg.get("ndcg_k", 10)
    base_key = args.backend if args.backend in details else (next(iter(details)) if details else args.backend)
    per_query = details.get(base_key, []) if details else []

    joined = []
    for pq in per_query:
        q = queries.get(pq["id"])
        if not q:
            continue
        joined.append({**pq, "gen": q.get("gen", {}), "category": pq.get("category")})

    FAMILIES = ["CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP"]

    # partition: unambiguous (unique/disambiguated) vs multi accept-set
    main_rows = [r for r in joined if r["gen"].get("ambiguity") in ("unique", "disambiguated")]
    multi_rows = [r for r in joined if r["gen"].get("ambiguity") == "multi"]

    by_category = aggregate_by(main_rows, lambda r: r["category"])
    by_chunk = aggregate_by(main_rows, lambda r: r["gen"].get("chunk_type"))
    op_by_fam = aggregate_by([r for r in main_rows if r["category"] == "operator_lookup"],
                             lambda r: r["gen"].get("family"))
    pa_by_fam = aggregate_by([r for r in main_rows if r["category"] == "parameter"],
                             lambda r: r["gen"].get("family"))
    pa_by_kind = aggregate_by([r for r in main_rows if r["category"] == "parameter"],
                              lambda r: r["gen"].get("kind"))
    pd_by_cat = aggregate_by([r for r in main_rows if r["category"] == "palette_discovery"],
                             lambda r: r["gen"].get("kind"))
    bi_by_pair = aggregate_by([r for r in main_rows if r["category"] == "build_instruction"],
                              lambda r: r["gen"].get("kind"))
    multi_by_cat = aggregate_by(multi_rows, lambda r: r["category"])
    agg_main = _agg(main_rows)

    # ambiguity census (from the queries file)
    amb = defaultdict(lambda: defaultdict(int))
    for q in queries.values():
        amb[q["category"]][q.get("gen", {}).get("ambiguity", "?")] += 1

    b = baseline.get("baseline") or baseline.get("backends", {}).get(base_key, {})
    ni = b.get("name_integrity", {})
    neg = b.get("negative") or {}

    # negatives split easy vs hard (join neg detail id -> gen.kind)
    neg_detail = neg.get("detail", []) or []
    neg_split = {"easy": [], "hard": []}
    for d in neg_detail:
        kind = queries.get(d.get("id"), {}).get("gen", {}).get("kind")
        if kind in neg_split:
            neg_split[kind].append(1.0 if d.get("abstained") else 0.0)
    easy_abs = _mean(neg_split["easy"])
    hard_abs = _mean(neg_split["hard"])

    stack = args.stack or f"{base_key} backend"

    # ---- markdown ----
    seed_str = f" (gen seed {args.seed})" if args.seed is not None else ""
    total_items = cm["total_items"] if cm else len(queries)
    meas = f"**{stack}** (backend `{base_key}`)" if have_measure else "**NOT MEASURED — coverage-only report**"
    L = [
        "# TD Builder v0.2 — COVERAGE tier (Phase 0.6c — set-cover breadth)",
        "",
        f"- Generated by `eval/coverage_report.py`{seed_str}.",
        f"- Coverage set: **{total_items} items** (greedy set-cover toward max DB coverage; the gen-side "
        f"coverage accounting below is from `coverage_meta.json`).",
        f"- Retrieval path (measurement section): {meas}.",
        "",
        "## What this tier is for",
        "Coverage tests **BREADTH** — *does family/chunk-type X retrieve at all* — on labels that are "
        "ground-truth-derived AND uniqueness-gated by construction (every gold resolves; the gold is the "
        "unique/clearly-best answer; the query never leaks the operator/comp/term/method name).",
        "",
    ]
    # ---- DB-COVERAGE (set-cover) section + GOAL CHECKLIST (from coverage_meta.json) ----
    if cm:
        kinds6 = {"scalar", "menu", "string", "toggle", "op", "tuplet"}
        chunk6 = {"operator_overview", "parameter_group", "block_overview", "class_method",
                  "concept", "build_instruction"}
        unamb_ok = all(v >= 0.9 for v in cm["unambiguous_rate_by_category"].values())
        match = cm.get("kb_matchable") or {}
        valid_ok = all(m == t for m, t in match.values()) if match else None
        worst = cm["worst_family_coverage_pct"]
        chk = [
            ("operators >=90% in EVERY family (worst {}%)".format(worst), worst >= 90),
            ("all 6 param kinds present", kinds6 <= set(cm["param_kinds_present"])),
            ("all targeted chunk types present", chunk6 <= set(cm["chunk_type_counts"])),
            ("per-category unambiguous-rate >=0.9", unamb_ok),
            ("0 answer-leakage ({})".format(cm["answer_leaks"]), cm["answer_leaks"] == 0),
            ("~100% valid gold (KB-matchable)", bool(valid_ok)),
            ("total <= {} ({})".format(cm["max_total"], cm["total_items"]), cm["total_items"] <= cm["max_total"]),
        ]
        L += ["## DB COVERAGE (greedy set-cover) — the Phase-0.6c headline", "",
              "_Operators covered = appears as a gold in operator_lookup ∪ parameter ∪ build. "
              "operator_lookup enumerates ALL 663 KB entries (no cap); ops it can't yield a valid query for are "
              "recovered via an op-specific parameter, else listed as skipped (a KB-quality signal)._", "",
              "| family | covered/total | coverage% | via operator_lookup |", "|---|---|---|---|"]
        for f in FAMILIES:
            tot = cm["operators_total_by_family"][f]; cov = cm["operators_covered_by_family"][f]
            pct = cm["coverage_pct_by_family"][f]; ol = cm["operator_lookup_emit_by_family"][f]
            L.append(f"| {f} | {cov}/{tot} | {'**' if pct>=90 else ''}{pct}%{'**' if pct>=90 else ''} | {ol} |")
        L += ["", f"**Worst family = {worst}%**, total items {cm['total_items']} (cap {cm['max_total']}), "
              f"operators skipped-from-operator_lookup {len(cm['skipped_operators'])} "
              f"(uncovered-entirely {len(cm['skipped_uncovered'])}).", "",
              "### GOAL CHECKLIST", ""]
        for label, ok in chk:
            L.append(f"- [{'x' if ok else ' '}] {label}")
        L += ["", "### Skipped-from-operator_lookup operators (KB-quality finding)",
              "_Reasons an op yielded no valid capability query; many are still covered via a parameter._", ""]
        skip_by_reason = defaultdict(list)
        for s in cm["skipped_operators"]:
            skip_by_reason[s["reason"]].append(s)
        L += ["| reason | count | examples |", "|---|---|---|"]
        for reason in sorted(skip_by_reason, key=lambda r: -len(skip_by_reason[r])):
            sk = skip_by_reason[reason]
            ex = ", ".join(s["operator"] for s in sk[:6])
            L.append(f"| {reason} | {len(sk)} | {ex} |")
        L += ["", f"**Uncovered-entirely ({len(cm['skipped_uncovered'])})** "
              f"(no operator_lookup query AND no op-specific parameter): "
              f"{', '.join(cm['skipped_uncovered'][:25])}{' …' if len(cm['skipped_uncovered'])>25 else ''}", ""]
        # console checklist (the /goal evaluator reads the transcript)
        print("DB-COVERAGE per family:", {f: f"{cm['coverage_pct_by_family'][f]}%" for f in FAMILIES})
        print("GOAL CHECKLIST:")
        for label, ok in chk:
            print(f"  [{'x' if ok else ' '}] {label}")

    if have_measure:
        L += [f"## With-stack measurement — UNAMBIGUOUS slice ({agg_main['n']} items): "
              f"recall@{k} **{agg_main['recall']:.2f}** · MRR **{agg_main['mrr']:.2f}** · "
              f"nDCG@{nk} **{agg_main['ndcg']:.2f}**", "",
              "_(multi accept-set slice reported separately as set-recall; never folded into MRR.)_", ""]
        L += _table("By category (unambiguous slice)", by_category, k, nk, "category")
        L += _table("By chunk type (the §6 type each recipe targets)", by_chunk, k, nk, "chunk_type")
        L += _table("operator_lookup recall by family", op_by_fam, k, nk, "family")
        L += _table("parameter recall by family (op-named, op-specific params)", pa_by_fam, k, nk, "family")
        L += _table("parameter recall by kind", pa_by_kind, k, nk, "kind")
        L += _table("palette_discovery recall by category", pd_by_cat, k, nk, "category")
        L += _table("build_instruction recall by family edge", bi_by_pair, k, nk, "src->dst")
        if multi_rows:
            L += ["### Multi accept-set slice (SET-recall — separate from single-gold MRR)", ""]
            L += _table("multi by category", multi_by_cat, k, nk, "category", metric="set-recall@{k}")
        L += [
            "## Negatives (abstention) & name-integrity (with-stack)",
            "",
            f"- Abstention@{k} overall: **{neg.get('abstention_rate', 0):.2f}** "
            f"(floor {neg.get('score_floor', '?')}, mean top-1 {neg.get('mean_top1_score', 0):.3f}).",
            f"- **EASY** abstention: **{easy_abs:.2f}** ({len(neg_split['easy'])} q) · "
            f"**HARD** (TD-adjacent: Shadertoy/Unreal/Houdini/Max) abstention: **{hard_abs:.2f}** "
            f"({len(neg_split['hard'])} q).",
            f"- Name-integrity: **{ni.get('unresolved_violations', '?')}** unresolved, "
            f"**{ni.get('retokenized_name_surfaced', '?')}** retokenized "
            f"(of {ni.get('identity_bearing_chunks_checked', '?')} identity-bearing returns).",
            "",
        ]

    # ambiguity census (gen-side; always present)
    L += ["## Ambiguity census (generator tags)", "",
          "| category | unique | disambiguated | multi |", "|---|---|---|---|"]
    for cat in sorted(c for c in amb if c != "negative"):
        a = amb[cat]
        L.append(f"| {cat} | {a.get('unique',0)} | {a.get('disambiguated',0)} | {a.get('multi',0)} |")
    L += [
        "",
        "## Three-tier eval discipline",
        "",
        "| Tier | File | Tests | Decision role |",
        "|---|---|---|---|",
        "| **Frozen 78** | `labeled_queries.jsonl` | the same 23 ops/seeded failures every phase | "
        "cross-phase TREND gate |",
        "| **Held-out** | `heldout_queries.jsonl` | paraphrases of the 78 (same predicates) | "
        "OVERFIT detector / real decision metric |",
        "| **Coverage** | `coverage_queries.jsonl` (this) | breadth × 7 families × §6 chunk types × param "
        "kinds; uniqueness-gated; rotates per `--seed` | does family X retrieve **at all** |",
        "",
        "Coverage = BREADTH, held-out = DIFFICULTY (paraphrase robustness). This tier is a **Phase-3 "
        "input**: the embedder A/B is judged on held-out + coverage, NOT the frozen 78.",
        "",
    ]
    out_md = Path(args.out) if args.out else cm_path.parent / "COVERAGE.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(L) + "\n", encoding="utf-8")

    report = {
        "stack": stack, "backend": base_key, "seed": args.seed, "k": k, "ndcg_k": nk,
        "unambiguous_n": len(main_rows), "multi_n": len(multi_rows), "negatives_n": neg.get("n", 0),
        "aggregate_unambiguous": agg_main,
        "by_category": by_category, "by_chunk_type": by_chunk,
        "operator_by_family": op_by_fam, "parameter_by_family": pa_by_fam,
        "parameter_by_kind": pa_by_kind, "palette_by_category": pd_by_cat,
        "build_by_edge": bi_by_pair, "multi_by_category": multi_by_cat,
        "abstention": {"overall": neg.get("abstention_rate"), "easy": easy_abs, "hard": hard_abs},
        "name_integrity": {"unresolved": ni.get("unresolved_violations"),
                           "retokenized": ni.get("retokenized_name_surfaced")},
        "have_measurement": have_measure,
        "coverage_meta": {kk: cm.get(kk) for kk in ("coverage_pct_by_family", "worst_family_coverage_pct",
                          "total_items", "answer_leaks")} if cm else None,
    }
    out_json = Path(args.out_json) if args.out_json else out_md.with_suffix(".json")
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # console (measurement lines only when measured)
    if have_measure:
        print(f"[{stack}] unambiguous {len(main_rows)} | multi {len(multi_rows)} | "
              f"agg recall@{k}={agg_main['recall']:.2f} MRR={agg_main['mrr']:.2f} nDCG@{nk}={agg_main['ndcg']:.2f}")
        print("operator_lookup recall by family:", {f: f"{op_by_fam.get(f, {}).get('recall', 0):.2f}" for f in FAMILIES})
        print("parameter recall by family:      ", {f: f"{pa_by_fam.get(f, {}).get('recall', 0):.2f}" for f in FAMILIES})
        if multi_rows:
            print("multi set-recall by cat:  ", {c: f"{v['recall']:.2f}" for c, v in multi_by_cat.items()})
        print(f"abstention easy={easy_abs:.2f} hard={hard_abs:.2f} | "
              f"name-integrity {ni.get('unresolved_violations')}u/{ni.get('retokenized_name_surfaced')}r")
    else:
        print("(coverage-only report — no measurement; run run_eval + re-run with --details for with-stack recall)")
    print(f"wrote {out_md}\n      {out_json}")


if __name__ == "__main__":
    main()

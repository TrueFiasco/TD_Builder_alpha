#!/usr/bin/env python3
r"""
Phase-0.6 MINIMAL coverage-FLOOR set (companion to the max-coverage set-cover).

Finds the FEWEST tests (greedy partial set-cover, selected from the existing
coverage_queries.jsonl) that hit a coverage FLOOR:
  * ALL: >= --op-floor (default 0.80) of operators covered OVERALL, and
  * EVERY section (the 7 op families AND each category) >= --section-floor (0.75).

Coverage cell model (each test covers exactly the entities it golds for):
  * operator_lookup / parameter / build_instruction item -> covers ONE operator
    (counts toward OVERALL + its family) AND its category entity (the operator).
  * palette/python/concept item -> covers ONE category entity (comp / (class,method)
    / term); these do NOT touch the 7 op-families.
  * negative item -> covers itself (category 'negative').
Because each test covers exactly ONE operator, covering F% of N operators needs
>= ceil(F*N) tests — a PROVABLE lower bound the greedy is compared against.

Two floors reported:
  * V2 (literal ask): OVERALL ops >= op-floor, every family AND every category >= section-floor.
  * V1 (operator-only, leaner): OVERALL ops >= op-floor, every family >= section-floor;
    categories unconstrained (the pure operator-coverage floor — its size is the hard
    lower bound set by the operator floor).

Greedy is tie-break-randomized; we sweep --seeds orderings and report the SMALLEST
set found (deterministic: smallest count, ties -> lowest seed). Offline.

Usage:
  py -3.11 eval/minimal_cover.py --queries eval/coverage_queries.jsonl \
      --coverage-meta eval/coverage_meta.json --seeds 300 \
      --out eval/coverage_minimal.jsonl --report "<...>/COVERAGE.md"
"""
from __future__ import annotations
import argparse, io, json, math, random, sys
from collections import defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
FAMILIES = ["CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP"]
CATS = ["operator_lookup", "parameter", "palette_discovery", "python", "build_instruction", "concept", "negative"]
OP_CATS = {"operator_lookup", "parameter", "build_instruction"}


def _load_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def cat_entity(r):
    c = r["category"]; g = r.get("gen", {})
    if c in OP_CATS:
        return g.get("op")
    pred = r.get("relevant_predicate") or {"clauses": [{}]}
    cl = pred["clauses"][0]
    if c == "palette_discovery":
        return cl.get("meta_name_any", [None])[0]
    if c == "python":
        return (tuple(cl.get("class_any", [])), cl.get("method_any", [None])[0])
    if c == "concept":
        return cl.get("term_any", [None])[0]
    if c == "negative":
        return r["id"]
    return None


def build_constraints(rows, fam_total, op_floor, section_floor, with_cat):
    """Return constraints {name: {'target': int, 'cells': set(all), 'item_cell': {id: cell}}}."""
    full_ops = {r["gen"]["op"] for r in rows if r["category"] in OP_CATS and r["gen"].get("op")}
    overall_total = sum(fam_total.values())
    cons = {}
    # OVERALL operators
    cons["ALL:operators"] = {"target": math.ceil(op_floor * overall_total), "universe": overall_total,
                             "item_cell": {r["id"]: r["gen"]["op"] for r in rows
                                           if r["category"] in OP_CATS and r["gen"].get("op")}}
    # per family
    for f in FAMILIES:
        ic = {r["id"]: r["gen"]["op"] for r in rows
              if r["category"] in OP_CATS and r["gen"].get("family") == f and r["gen"].get("op")}
        cons[f"FAM:{f}"] = {"target": math.ceil(section_floor * fam_total[f]), "universe": fam_total[f], "item_cell": ic}
    if with_cat:
        for c in CATS:
            ents = {}
            for r in rows:
                if r["category"] == c:
                    e = cat_entity(r)
                    if e is not None:
                        ents[r["id"]] = e
            full = len(set(ents.values()))
            cons[f"CAT:{c}"] = {"target": math.ceil(section_floor * full), "universe": full, "item_cell": ents}
    return cons


def greedy(rows, cons, seed):
    rng = random.Random(seed)
    order = sorted(r["id"] for r in rows)
    rng.shuffle(order)
    # precompute each item's relevant (constraint, cell) pairs (most items touch ~3)
    item_pairs = defaultdict(list)
    for name, c in cons.items():
        for iid, cell in c["item_cell"].items():
            item_pairs[iid].append((name, cell))
    covered = {name: set() for name in cons}
    met = {name: c["target"] <= 0 for name, c in cons.items()}
    sat_order, selected, sel_ids = [], [], set()
    for name in cons:
        if met[name]:
            sat_order.append((0, name))
    while not all(met.values()):
        best, best_score = None, 0
        for iid in order:
            if iid in sel_ids:
                continue
            score = 0
            for name, cell in item_pairs[iid]:
                if not met[name] and cell not in covered[name]:
                    score += 1
            if score > best_score:
                best, best_score = iid, score
        if best is None:                       # no item helps any unmet constraint -> infeasible
            return None, sat_order, covered, met
        sel_ids.add(best); selected.append(best)
        for name, cell in item_pairs[best]:
            covered[name].add(cell)
            if not met[name] and len(covered[name]) >= cons[name]["target"]:
                met[name] = True
                sat_order.append((len(selected), name))
    return selected, sat_order, covered, met


def section_pcts(selected_ids, rows, fam_total):
    by_id = {r["id"]: r for r in rows}
    sel = [by_id[i] for i in selected_ids]
    fam_cov = defaultdict(set); cat_cov = defaultdict(set); cat_full = defaultdict(set)
    for r in rows:
        e = cat_entity(r)
        if e is not None:
            cat_full[r["category"]].add(e)
    for r in sel:
        if r["category"] in OP_CATS and r["gen"].get("op"):
            fam_cov[r["gen"]["family"]].add(r["gen"]["op"])
        e = cat_entity(r)
        if e is not None:
            cat_cov[r["category"]].add(e)
    all_ops = set().union(*fam_cov.values()) if fam_cov else set()
    overall = round(100 * len(all_ops) / sum(fam_total.values()), 1)
    fam_pct = {f: round(100 * len(fam_cov[f]) / fam_total[f], 1) for f in FAMILIES}
    cat_pct = {c: round(100 * len(cat_cov[c]) / max(len(cat_full[c]), 1), 1) for c in CATS}
    return overall, fam_pct, cat_pct, len(all_ops)


def run_variant(rows, fam_total, op_floor, section_floor, with_cat, seeds):
    cons = build_constraints(rows, fam_total, op_floor, section_floor, with_cat)
    best = None
    for s in range(seeds):
        sel, sat, cov, met = greedy(rows, cons, s)
        if sel is None:
            continue
        if best is None or len(sel) < best[0] or (len(sel) == best[0] and s < best[3]):
            best = (len(sel), sel, sat, s)
    return cons, best


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="Minimal coverage-floor set (greedy partial set-cover)")
    ap.add_argument("--queries", default=str(EVAL_DIR / "coverage_queries.jsonl"))
    ap.add_argument("--coverage-meta", default=str(EVAL_DIR / "coverage_meta.json"))
    ap.add_argument("--op-floor", type=float, default=0.80)
    ap.add_argument("--section-floor", type=float, default=0.75)
    ap.add_argument("--seeds", type=int, default=300)
    ap.add_argument("--out", default=str(EVAL_DIR / "coverage_minimal.jsonl"))
    ap.add_argument("--report", default=None, help="append a MINIMAL-FLOOR section to this COVERAGE.md")
    args = ap.parse_args()

    rows = _load_jsonl(args.queries)
    cm = json.loads(Path(args.coverage_meta).read_text(encoding="utf-8"))
    fam_total = cm["operators_total_by_family"]
    overall_total = sum(fam_total.values())
    lb = math.ceil(args.op_floor * overall_total)
    print(f"candidates {len(rows)} | overall operators {overall_total} | "
          f"op-floor {args.op_floor:.0%} -> >= {lb} tests (1 operator/test = PROVABLE lower bound) | "
          f"section-floor {args.section_floor:.0%}")

    # V2 (literal): families AND categories >= section-floor
    cons2, best2 = run_variant(rows, fam_total, args.op_floor, args.section_floor, True, args.seeds)
    # V1 (operator-only): families only
    cons1, best1 = run_variant(rows, fam_total, args.op_floor, args.section_floor, False, args.seeds)

    out_lines = []
    for tag, desc, cons, best in [
        ("V1", "operator-coverage floor (ops>=op-floor overall + per-family; categories unconstrained)", cons1, best1),
        ("V2", "FULL floor (literal ask): ops>=op-floor overall + EVERY family AND category >=section-floor", cons2, best2)]:
        n, sel, sat, seed = best
        overall, fam_pct, cat_pct, nops = section_pcts(sel, rows, fam_total)
        # binding = constraints satisfied LAST (largest item-count in sat order)
        order_sorted = sorted(sat, key=lambda x: -x[0])
        binders = [name for cnt, name in order_sorted if cnt >= n - max(1, int(0.03 * n))][:6]
        last_cnt = order_sorted[0][0] if order_sorted else n
        print(f"\n=== {tag}: {desc} ===")
        print(f"  MINIMAL TESTS = {n}  (best of {args.seeds} greedy orderings; seed {seed}; lower bound {lb})")
        print(f"  at-floor coverage: OVERALL operators {overall}% ({nops}); families " +
              " ".join(f"{f}={fam_pct[f]}%" for f in FAMILIES))
        print(f"  categories: " + " ".join(f"{c}={cat_pct[c]}%" for c in CATS))
        print(f"  BINDS LAST (the sections that determine the count): {binders}")
        out_lines += [f"### {tag} — {desc}", "",
                      f"- **Minimal tests = {n}** (greedy, best of {args.seeds} orderings; lower bound {lb} = ⌈{args.op_floor:.0%}×{overall_total}⌉, since each test covers exactly one operator).",
                      f"- At-floor coverage: **OVERALL operators {overall}%** ({nops}/{overall_total}); "
                      f"families " + ", ".join(f"{f} {fam_pct[f]}%" for f in FAMILIES) + ".",
                      f"- Categories: " + ", ".join(f"{c} {cat_pct[c]}%" for c in CATS) + ".",
                      f"- **Binds last (determines the count): {', '.join(binders)}**.", ""]
        if tag == "V2":
            Path(args.out).write_text("\n".join(json.dumps(by, ensure_ascii=False)
                                      for by in [r for r in rows if r["id"] in set(sel)]) + "\n", encoding="utf-8")
            print(f"  wrote minimal set -> {args.out}")

    if args.report and Path(args.report).exists():
        md = Path(args.report).read_text(encoding="utf-8")
        block = ("\n## MINIMAL coverage-FLOOR set (fewest tests for solid coverage)\n\n"
                 "_Greedy partial set-cover selected from the full set. Each test covers exactly one "
                 "operator, so ≥80% of operators needs ≥⌈0.8×N⌉ tests — a hard lower bound. The full "
                 f"~95%/family set ({len(rows)}) is the max; these are the leaner floor options._\n\n"
                 + "\n".join(out_lines))
        if "## MINIMAL coverage-FLOOR set" not in md:
            Path(args.report).write_text(md.rstrip() + "\n" + block, encoding="utf-8")
            print(f"\nappended MINIMAL section to {args.report}")


if __name__ == "__main__":
    main()

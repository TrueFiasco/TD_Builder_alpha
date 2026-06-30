#!/usr/bin/env python3
r"""
Layer-1 review sheet: EXPECTED (gold) vs ACTUAL (Phase-2 retrieval top-5).

Joins a query set with run_eval's details.json (which records each query's top-5
hits + a `relevant` flag = does that hit satisfy the gold predicate). For each
item it finds the RANK of the first relevant (gold) hit and auto-flags:
  * rank 1            -> HEALTHY (query->gold clean + learnable)
  * rank 2..k         -> CHECK_AMBIGUITY (gold retrieved but something ranks above it)
  * not in top-k      -> MISS (bad query? wrong gold? or KB gap — Layer-2 decides)
Writes REVIEW_SHEET.md (human) + review_flagged.json (the MISS/CHECK items, for the
Layer-2 blind-adjudication pass). Search-free; just reads details.json.
"""
from __future__ import annotations
import argparse, io, json, sys
from pathlib import Path
from collections import Counter, defaultdict


def _load_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def gold_op(r):
    for cl in (r.get("relevant_predicate") or {}).get("clauses", []):
        for k in ("op_name_any", "python_class_any", "meta_name_any", "term_any"):
            if cl.get(k):
                return cl[k][0]
    return "?"


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", required=True)
    ap.add_argument("--details", required=True)
    ap.add_argument("--backend", default="enhanced")
    ap.add_argument("--out", required=True, help="REVIEW_SHEET.md")
    args = ap.parse_args()

    queries = {q["id"]: q for q in _load_jsonl(args.queries)}
    details = json.loads(Path(args.details).read_text(encoding="utf-8"))
    pq = details.get(args.backend) or next(iter(details.values()))
    pq = {r["id"]: r for r in pq}

    rows, flagged = [], []
    for qid, q in queries.items():
        d = pq.get(qid)
        top5 = (d or {}).get("top5", [])
        rank = next((h["rank"] for h in top5 if h.get("relevant")), None)
        flag = "HEALTHY" if rank == 1 else ("CHECK_AMBIGUITY" if rank else "MISS")
        fam = q.get("gen", {}).get("family", "?")
        rows.append({"id": qid, "family": fam, "query": q["query"], "gold": gold_op(q),
                     "rank": rank, "flag": flag,
                     "top5": [{"r": h["rank"], "name": h.get("name"), "type": h.get("type"),
                               "rel": bool(h.get("relevant"))} for h in top5],
                     "official_purpose": q.get("gen", {}).get("official_purpose", "")})
        if flag != "HEALTHY":
            flagged.append({"id": qid, "family": fam, "query": q["query"], "gold": gold_op(q),
                            "flag": flag, "top5_names": [h.get("name") for h in top5]})

    flags = Counter(r["flag"] for r in rows)
    by_fam_health = defaultdict(lambda: [0, 0])
    for r in rows:
        by_fam_health[r["family"]][0] += 1
        if r["flag"] == "HEALTHY":
            by_fam_health[r["family"]][1] += 1

    L = ["# Sweet-16 / curated GOLD — Layer-1 review sheet (expected vs actual)", "",
         f"- {len(rows)} curated gold queries through the **Phase-2 retrieval_stack** over the v0.2 KB.",
         f"- **{flags['HEALTHY']} HEALTHY** (gold = top-1) · **{flags['CHECK_AMBIGUITY']} CHECK_AMBIGUITY** "
         f"(gold in top-5, not #1) · **{flags['MISS']} MISS** (gold absent from top-5).",
         "- A MISS is NOT automatically a bad item — Layer-2 blind adjudication decides bad-query vs "
         "wrong-gold vs **KB-gap** (a KB-gap means keep the item; it's the signal the eval exists to find).",
         "", "## Health by family", "", "| family | healthy/total |", "|---|---|"]
    for f in sorted(by_fam_health):
        t, h = by_fam_health[f]
        L.append(f"| {f} | {h}/{t} |")
    L += ["", "## Flagged items (need Layer-2 adjudication)", "",
          "| id | family | query | expected gold | rank | flag | actual top-5 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["flag"] == "HEALTHY":
            continue
        t5 = " · ".join(f"{h['r']}.{h['name'] or h['type']}{'*' if h['rel'] else ''}" for h in r["top5"])
        L.append(f"| {r['id']} | {r['family']} | {r['query'][:60]} | {r['gold']} | {r['rank']} | {r['flag']} | {t5} |")
    L += ["", "_`*` marks a top-5 hit that satisfies the gold predicate._", "",
          "## All items (full)", "", "| id | family | gold | rank | flag |", "|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['id']} | {r['family']} | {r['gold']} | {r['rank']} | {r['flag']} |")

    Path(args.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    Path(args.out).with_name("review_flagged.json").write_text(json.dumps(flagged, indent=2), encoding="utf-8")
    print(f"health: {dict(flags)}  ({flags['HEALTHY']}/{len(rows)} = "
          f"{round(100*flags['HEALTHY']/len(rows))}% top-1)")
    print("by family healthy/total:", {f: f"{h}/{t}" for f, (t, h) in sorted(by_fam_health.items())})
    print(f"flagged for Layer-2: {len(flagged)}")
    for fl in flagged:
        print(f"  [{fl['flag']}] {fl['id']} {fl['gold']}: {fl['query'][:62]}")
    print(f"\nwrote {args.out}\n      {Path(args.out).with_name('review_flagged.json')}")


if __name__ == "__main__":
    main()

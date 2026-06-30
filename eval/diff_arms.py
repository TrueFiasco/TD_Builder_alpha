#!/usr/bin/env python3
r"""
Phase-3 per-query WIN/LOSE diff between two run_eval arms (the embedder A/B).

n is only ~12 per category, so a category-level gate ("operator_lookup +0.08") is
often a SINGLE query and can sit inside the ChromaDB HNSW jitter band. This tool
joins two arms' per-query results by query id and shows exactly WHICH queries moved
(recall flip and/or first-relevant-rank change), so a "win" concentrated in 1-2
queries — or one inside the band — is visible as noise rather than signal.

Inputs are the ``details.json`` each run stages (``{backend: [per_query, ...]}``),
or any json carrying a top-level ``per_query`` list. Optionally pass the two
``baseline.json`` (run_eval ``--out``) to print the aggregate + per-trial bands.

  py -3.11 eval/diff_arms.py --a <A details.json> --b <B details.json> \
      --label-a KB_minilm_norm --label-b KB_bge \
      [--a-base <A baseline.json> --b-base <B baseline.json>]
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def _load_per_query(path: str, backend: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if isinstance(data.get(backend), list):
            return data[backend]
        if isinstance(data.get("per_query"), list):
            return data["per_query"]
        # baseline.json shape: details live elsewhere; per_query is stripped there
    raise SystemExit(f"no per_query for backend {backend!r} in {path}")


def _index(rows: list[dict]) -> dict:
    return {r["id"]: r for r in rows}


def _agg_line(base_path: str, backend: str) -> str:
    try:
        d = json.loads(Path(base_path).read_text(encoding="utf-8"))
        b = d.get("baseline") or d.get("backends", {}).get(backend, {})
        agg = b.get("aggregate", {})
        band = agg.get("_band", {})
        rec = agg.get("recall_at_5", agg.get("recall_at_k"))
        mrr = agg.get("mrr")
        rb = band.get("recall_at_5") or band.get("recall_at_k")
        mb = band.get("mrr")
        return (f"aggregate recall@5={rec} (band {rb})  MRR={mrr} (band {mb})  "
                f"model={d.get('embedding_model')}")
    except Exception as e:
        return f"(could not read aggregate from {base_path}: {e})"


def main():
    ap = argparse.ArgumentParser(description="Per-query WIN/LOSE diff between two run_eval arms")
    ap.add_argument("--a", required=True, help="arm A details.json (the BASELINE arm)")
    ap.add_argument("--b", required=True, help="arm B details.json (the CANDIDATE arm)")
    ap.add_argument("--backend", default="enhanced")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--a-base", default=None, help="optional arm A baseline.json (aggregate + bands)")
    ap.add_argument("--b-base", default=None, help="optional arm B baseline.json (aggregate + bands)")
    args = ap.parse_args()

    A = _index(_load_per_query(args.a, args.backend))
    B = _index(_load_per_query(args.b, args.backend))
    ids = sorted(set(A) & set(B))
    only_a = sorted(set(A) - set(B))
    only_b = sorted(set(B) - set(A))

    cat = defaultdict(lambda: {"n": 0, "win": 0, "lose": 0, "same": 0, "a_rec": 0.0, "b_rec": 0.0})
    flips = []   # (id, category, verdict, a_rec, b_rec, a_rank, b_rank)
    for qid in ids:
        a, b = A[qid], B[qid]
        c = a.get("category", "?")
        ar = float(a.get("recall_at_k", 0.0))
        br = float(b.get("recall_at_k", 0.0))
        arank = a.get("first_relevant_rank")
        brank = b.get("first_relevant_rank")
        rec = cat[c]
        rec["n"] += 1
        rec["a_rec"] += ar
        rec["b_rec"] += br
        verdict = "same"
        if br > ar:
            verdict = "win"
        elif br < ar:
            verdict = "lose"
        elif arank is not None and brank is not None:
            if brank < arank:
                verdict = "win"
            elif brank > arank:
                verdict = "lose"
        rec[verdict] += 1
        if verdict != "same":
            flips.append((qid, c, verdict, ar, br, arank, brank))

    print(f"\n=== Per-query diff: {args.label_a} (A)  ->  {args.label_b} (B) ===")
    print(f"backend={args.backend}  joined={len(ids)}  A-only={len(only_a)}  B-only={len(only_b)}")
    if args.a_base:
        print(f"  A  {args.label_a:16s} {_agg_line(args.a_base, args.backend)}")
    if args.b_base:
        print(f"  B  {args.label_b:16s} {_agg_line(args.b_base, args.backend)}")

    print(f"\n{'category':18s} {'n':>3} {'A_recall':>9} {'B_recall':>9} {'d':>6}  {'win':>3} {'lose':>4} {'same':>4}")
    print("-" * 70)
    tot = {"n": 0, "win": 0, "lose": 0, "same": 0, "a": 0.0, "b": 0.0}
    for c in sorted(cat):
        r = cat[c]
        a_mean = r["a_rec"] / r["n"] if r["n"] else 0.0
        b_mean = r["b_rec"] / r["n"] if r["n"] else 0.0
        print(f"{c:18s} {r['n']:>3} {a_mean:>9.3f} {b_mean:>9.3f} {b_mean-a_mean:>+6.3f}  "
              f"{r['win']:>3} {r['lose']:>4} {r['same']:>4}")
        tot["n"] += r["n"]; tot["win"] += r["win"]; tot["lose"] += r["lose"]; tot["same"] += r["same"]
        tot["a"] += r["a_rec"]; tot["b"] += r["b_rec"]
    if tot["n"]:
        print("-" * 70)
        print(f"{'AGGREGATE':18s} {tot['n']:>3} {tot['a']/tot['n']:>9.3f} {tot['b']/tot['n']:>9.3f} "
              f"{(tot['b']-tot['a'])/tot['n']:>+6.3f}  {tot['win']:>3} {tot['lose']:>4} {tot['same']:>4}")

    if flips:
        print(f"\n--- {len(flips)} query(ies) MOVED (recall flip and/or rank change) ---")
        for qid, c, v, ar, br, arank, brank in sorted(flips, key=lambda x: (x[1], x[0])):
            tag = "WIN " if v == "win" else "LOSE"
            print(f"  [{tag}] {qid:8s} {c:18s} recall {ar:.0f}->{br:.0f}  rank {arank}->{brank}")
        print("\nNOTE: if the net win is carried by 1-2 queries or sits inside the per-trial band, "
              "treat it as NOISE -- lean on the aggregate + coverage tier, not these.")
    else:
        print("\nNo query moved between arms (identical recall + first-relevant rank on the joined set).")


if __name__ == "__main__":
    main()

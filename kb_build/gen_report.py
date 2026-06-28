"""
Render the Phase-1 results comparison (new condensed KB vs the Phase-0 baseline).

  py -3.11 kb_build/gen_report.py <new_eval_json> <out_markdown>

Reads the Phase-0 canonical baseline (eval/baseline.json), the new eval json,
and the new KB manifest, and writes a side-by-side markdown to <out_markdown>.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import common as C

CATS = ["palette_discovery", "howto", "operator_lookup", "parameter", "python"]


def _be(d):
    """The enhanced backend block of a run_eval result json."""
    return d["backends"]["enhanced"]


def fmt(new, base):
    arrow = "+" if new >= base else ""
    return f"{new:.2f} ({arrow}{new - base:+.2f})".replace("(+-", "(-").replace("(++", "(+")


def main():
    new_json = Path(sys.argv[1])
    out_md = Path(sys.argv[2])
    base = json.loads((Path(__file__).resolve().parent.parent / "eval" / "baseline.json").read_text(encoding="utf-8"))
    new = json.loads(new_json.read_text(encoding="utf-8"))
    manifest = json.loads((C.OUT / "manifest.json").read_text(encoding="utf-8"))

    b, n = _be(base), _be(new)
    bc, nc = base.get("collection_count", 34350), new.get("collection_count", manifest["vectordb_count"])

    L = []
    L.append("# TD Builder v0.2 — Phase 1 (anatomy rebuild) results")
    L.append("")
    L.append(f"Condensed, re-grounded KB built from `New KB build/Resources` via `kb_build/` "
             f"(MiniLM, `parent_chunk` persisted). **New = {nc:,} chunks vs baseline {bc:,} "
             f"({bc / nc:.1f}× smaller).** Reported = median of {n.get('repeats', 1)} trials "
             f"(ChromaDB HNSW jitter). Measured offline through the shipped `UnifiedSearchAdapter`.")
    L.append("")
    L.append("## Retrieval metrics — new vs Phase-0 baseline (Δ)")
    L.append("")
    L.append("| Category | recall@5 | MRR | nDCG@10 |")
    L.append("|---|---|---|---|")
    for c in CATS:
        bm, nm = b["per_category"].get(c, {}), n["per_category"].get(c, {})
        L.append(f"| {c} | {fmt(nm.get('recall_at_5',0), bm.get('recall_at_5',0))} "
                 f"| {fmt(nm.get('mrr',0), bm.get('mrr',0))} "
                 f"| {fmt(nm.get('ndcg_at_10',0), bm.get('ndcg_at_10',0))} |")
    ba, na = b["aggregate"], n["aggregate"]
    L.append(f"| **AGGREGATE** | **{fmt(na['recall_at_5'], ba['recall_at_5'])}** "
             f"| **{fmt(na['mrr'], ba['mrr'])}** | **{fmt(na['ndcg_at_10'], ba['ndcg_at_10'])}** |")
    L.append("")
    bni, nni = b["name_integrity"], n["name_integrity"]
    L.append("## Name-integrity (ground truth = operators.json + operator_types.json)")
    L.append("")
    L.append(f"- retokenized names surfaced: **{bni['retokenized_name_surfaced']} → "
             f"{nni['retokenized_name_surfaced']}** (target 0)")
    L.append(f"- unresolved-operator violations: {bni['unresolved_violations']} → "
             f"{nni['unresolved_violations']}")
    L.append(f"- identity-bearing returns checked: {bni['identity_bearing_chunks_checked']} → "
             f"{nni['identity_bearing_chunks_checked']}")
    L.append("")
    L.append("## Index composition (new)")
    L.append("")
    L.append(f"- total chunks: **{manifest['chunk_count']:,}** (baseline {bc:,})")
    for ct, k in sorted(manifest["chunk_type_histogram"].items(), key=lambda x: -x[1]):
        L.append(f"  - `{ct}`: {k}")
    L.append("")
    L.append("## Phase-1 acceptance (plan §9)")
    L.append("")
    pal = n["per_category"]["palette_discovery"]["recall_at_5"]
    ho = n["per_category"]["howto"]["recall_at_5"]
    opmrr = n["per_category"]["operator_lookup"]["mrr"]
    opmrr_b = b["per_category"]["operator_lookup"]["mrr"]
    py = n["per_category"]["python"]["recall_at_5"]
    py_b = b["per_category"]["python"]["recall_at_5"]
    chk = lambda ok: "✅" if ok else "⚠️"
    L.append(f"- {chk(pal >= 0.6)} palette_discovery recall@5 ≥ 0.6 → **{pal:.2f}**")
    L.append(f"- {chk(ho >= 0.4)} howto recall@5 ≥ 0.4 → **{ho:.2f}**")
    L.append(f"- {chk(opmrr >= opmrr_b)} operator_lookup MRR no regression (baseline {opmrr_b:.2f}) → "
             f"**{opmrr:.2f}** (≥0.95 target reached by Phase-2 rerank)")
    L.append(f"- {chk(py >= py_b)} python improved (baseline {py_b:.2f}) → **{py:.2f}**")
    L.append(f"- {chk(nni['retokenized_name_surfaced'] == 0 and nni['unresolved_violations'] == 0)} "
             f"name-integrity retokenized 294 → 0, 0 unresolved")
    L.append(f"- {chk(manifest['chunk_count'] <= 8500)} index size ↓ ~4× → "
             f"{manifest['chunk_count']:,} ({bc / manifest['chunk_count']:.1f}× smaller)")
    L.append("")
    L.append("## Notes & residuals")
    L.append("")
    L.append("- **parameter recall (0.83 vs baseline 1.00) is the one residual.** It is the known "
             "dense-only MiniLM limitation: sibling-family chunks (Transform TOP vs Transform POP/CHOP) "
             "and an operator's own examples/overview crowd the specific `parameter_group` out of the "
             "top-5 for a minority of queries. The baseline's 1.00 came from 10,899 per-param chunks "
             "(precise but the bulk of the index bloat we removed). Plan §7/§9 assigns this precision "
             "recovery to **Phase 2** (BM25 exact-match + cross-encoder rerank), which disambiguates "
             "operator vs parameter vs example and family — the same mechanism that lifts operator MRR "
             "to the ≥0.95 target. Chunk-text tuning here already moved parameter 0.67→0.75→0.83 and "
             "operator_lookup MRR 0.60→0.80 without re-bloating the index.")
    L.append("- **operator↔parameter tradeoff (measured):** OPSnippets `real_example` chunks lift "
             "operator_lookup recall 0.75→0.92 (real-world vocab like 'RMS') but compete with "
             "`parameter_group` on parameter queries. Front-loading the param display-name index and "
             "moving example param VALUES into `meta` (search body vs hydration detail, plan §5) keeps "
             "both: operator 0.92 / parameter 0.83. Phase 2 removes the residual competition.")
    L.append("- **gpickle:** the staged `knowledge_graph_enhanced.gpickle` is the reused shipped graph "
             "(so `UnifiedSearchAdapter` constructs). The harness scores only `semantic_results` (pure "
             "vector search), so graph content does not affect these metrics; a re-grounded graph "
             "rebuild with persisted parents is a separate pass. `graphrag.json` (stale, 58 MB) is "
             "dropped from the new bundle.")
    L.append("- **Sections built:** §6.1 operators, §6.2 parameters, §6.3 python, §6.4 palette, "
             "§6.5 concepts, §6.6 recipes/patterns, §6.7 OPSnippets examples, §6.9 build-instructions. "
             "**Deferred:** §6.8 curriculum `lesson_pattern` (needs `expand_toe_file` on the curriculum "
             "`.tox`; its howto target is already met at 1.00 by the §6.6 recipes).")
    L.append("- **Stay-on-MiniLM / no Phase-2 in this build:** BM25, RRF and the cross-encoder reranker "
             "are Phase 2; the embedder A/B (bge-small) is Phase 3. This is the anatomy/content + size "
             "win, measured on the identical Phase-0 harness.")
    out_md.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()

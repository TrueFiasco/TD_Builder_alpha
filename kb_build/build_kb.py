"""
TD Builder v0.2 KB rebuild orchestrator (Phase 1, anatomy rebuild).

Runs the implemented §6 ingesters in plan order, accumulates condensed pointer
chunks, and stages the rebuilt KB under ``New KB build/Output/KB``:
  vector_db/                  — ChromaDB collection ``td_unified`` (MiniLM)
  operators.json              — identity/hydration registry (name-integrity GT)
  knowledge_graph_enhanced.gpickle — reused shipped graph (adapter load only)
  manifest.json               — model, counts, chunk_type/store histograms
  sources.lock.json           — pinned inputs (sha256 + size) + TD build

The build is ADDITIVE/section-by-section: each new ingester grows the cumulative
index so its eval delta is attributable. NEVER commit a KB.

  py -3.11 kb_build/build_kb.py                 # build every implemented section
  py -3.11 kb_build/build_kb.py --sections palette,operators
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

# (module, label) in plan build order. Missing modules are skipped (so the index
# can grow one section at a time). §6.1 + §6.2 share ingest_operators.
SECTION_ORDER = [
    ("ingest_palette", "palette"),          # §6.4
    ("ingest_recipes", "recipes"),          # §6.6 recipes/patterns
    ("ingest_guides", "guides"),            # §6.x Write_a_* authoring guides (type:guide)
    ("ingest_examples", "examples"),        # §6.7 OPSnippets real_example
    ("ingest_curriculum", "curriculum"),    # §6.8 lesson_pattern
    ("ingest_operators", "operators"),      # §6.1 operator_overview + §6.2 parameter_group
    ("ingest_python", "python"),            # §6.3 class_method / python_class_overview / python_pattern
    ("ingest_concepts", "concepts"),        # §6.5 concept
    ("ingest_build", "build"),              # §6.9 build_instruction / docked
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def write_sources_lock(inputs: list[Path], out_dir: Path):
    recs = []
    for p in sorted(set(inputs), key=lambda x: str(x)):
        if p.exists() and p.is_file():
            recs.append({"path": str(p.relative_to(C.RES)) if C.RES in p.parents else str(p),
                         "sha256": _sha256(p), "size": p.stat().st_size})
        else:
            recs.append({"path": str(p), "missing": True})
    lock = {
        "td_build": C.TD_BUILD,
        "corpus_root": str(C.RES),
        "embedding_model": C.MODEL_ID,
        "generated": datetime.now(timezone.utc).isoformat(),
        "inputs": recs,
    }
    (out_dir / "sources.lock.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sections", default="all", help="comma list, or 'all' implemented")
    ap.add_argument("--out", default=str(C.OUT))
    ap.add_argument("--no-vectordb", action="store_true", help="assemble rows + report only (no embed)")
    ap.add_argument("--no-models", action="store_true", help="skip the one-time cross-encoder fetch/bundle")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    want = None if args.sections == "all" else {s.strip() for s in args.sections.split(",")}

    print("[load] Identity registry (operator_ground_truth + operators.json)...")
    idn = C.Identity()
    print(f"  operators={len(idn.operators)} classes={len(idn.classes)} concepts={len(idn.concepts)}")
    print(f"  python_class: filled={idn.python_class_filled} "
          f"corrected={idn.python_class_corrected} "
          f"still-null={sum(1 for o in idn.operators if not o.get('python_class'))} "
          f"(nulls remaining are fossils absent from the census -- W7c retires them)")
    for fam, name, cur, derived in idn.python_class_unverified:
        # Not an error: a populated value disagreeing with the derivation is
        # REPORTED, never overwritten, until it is arbitrated against live TD.
        print(f"  ! python_class unverified: {fam} {name}: {cur!r} != derived {derived!r}")

    rows: list[dict] = []
    inputs: list[Path] = [idn.source_path, C.GT_OPERATOR_TYPES]
    section_counts: dict[str, int] = {}

    for mod_name, label in SECTION_ORDER:
        if want is not None and label not in want:
            continue
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue
        sec_rows = mod.build(idn)
        rows.extend(sec_rows)
        section_counts[label] = len(sec_rows)
        inputs.extend(getattr(mod, "INPUTS", []))
        print(f"[ingest] {label:12s} -> {len(sec_rows):5d} chunks")

    if not rows:
        print("No rows produced (no ingesters matched). Nothing to build.")
        return

    print(f"\n[total] {len(rows)} chunks across {len(section_counts)} section(s)")
    ctype_hist = Counter(r["chunk_type"] for r in rows)
    store_hist = Counter(r["meta"].get("__source_store") for r in rows)
    for ct, n in ctype_hist.most_common():
        print(f"    {ct:24s} {n}")

    # --- emit registry (regrounded + tuplet-enriched) + graph for adapter construction ---
    # Was a verbatim copy of the shipped operators.json; now writes the Identity's
    # registry — regrounded base (build-gate) + injected tuplet components — so the
    # runtime get_parameter_detail resolves tuplet codes (lag1=0.2) and the staged
    # registry matches the chunks. Classes/concepts/metadata are preserved.
    (out_dir / "operators.json").write_text(
        json.dumps(idn.raw, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[operators] registry source={idn.source_path.name}  "
          f"operators={len(idn.operators)}  tuplet components injected={idn.tuplets_injected}  "
          f"rules/fixes={idn.param_rules_applied}  docked summaries={idn.docked_attached}")
    # Deduped docked-DAT default templates (live-TD harvest): registry docked_dats
    # entries reference these by default_md5.
    dd_defaults = C.GT / "docked_dats" / "docked_dat_defaults.json"
    if dd_defaults.exists():
        shutil.copy2(dd_defaults, out_dir / "docked_contents.json")
        print(f"[docked] staged docked_contents.json "
              f"({len(json.loads(dd_defaults.read_text(encoding='utf-8')))} unique templates)")
    gp = C.SHIPPED_KB / "knowledge_graph_enhanced.gpickle"
    if gp.exists():
        # Rebuild the graph (canonical identity + OPType normalization + readMe filter,
        # §6.11) rather than reuse the stale shipped one. Falls back to a plain copy.
        try:
            import rebuild_graph
            gres = rebuild_graph.build(idn)
            print(f"[graph] rebuilt gpickle: {gres['stats']}")
        except Exception as e:
            print(f"[graph] rebuild failed ({e}); copying shipped gpickle")
            shutil.copy2(gp, out_dir / "knowledge_graph_enhanced.gpickle")

    if not args.no_vectordb:
        print("\n[embed] building vector_db (MiniLM, single-thread)...")
        count = C.build_vector_db(rows, out_dir)
        print(f"[ok] vector_db collection '{C.COLLECTION}' = {count} docs")

        # Phase-2 retrieval-stack artifacts (id-aligned to the vector DB just built).
        try:
            import build_bm25
            bm = build_bm25.build_from_vectordb(out_dir)
            print(f"[bm25] lexical_index = {bm['count']} rows ({bm['size_bytes']/1e6:.2f} MB)")
        except Exception as e:
            print(f"[bm25] SKIPPED ({e}) — retrieval_stack will fall back to dense-only")
        if not args.no_models:
            try:
                import build_models
                mr = build_models.build_models(out_dir)
                print(f"[models] cross-encoder {mr['status']}: {mr['path']}")
            except Exception as e:
                print(f"[models] SKIPPED ({e}) — bundle the reranker before enabling rerank")
    else:
        count = 0

    lex_pkl = out_dir / "lexical_index" / "bm25.pkl"
    ce_dir = out_dir / "models" / "ms-marco-MiniLM-L-6-v2"
    manifest = {
        "phase": "2-retrieval-stack",
        "generated": datetime.now(timezone.utc).isoformat(),
        "td_build": C.TD_BUILD,
        "embedding_model": C.MODEL_ID,
        "collection": C.COLLECTION,
        "chunk_count": len(rows),
        "vectordb_count": count,
        "sections": section_counts,
        "chunk_type_histogram": dict(ctype_hist),
        "store_histogram": dict(store_hist),
        # Phase-2 retrieval-stack artifacts (id-aligned to the vector DB).
        "retrieval_stack": {
            "bm25_index": "lexical_index/bm25.pkl" if lex_pkl.exists() else None,
            "reranker": "models/ms-marco-MiniLM-L-6-v2" if (ce_dir / "config.json").exists() else None,
            "pipeline": "dense + BM25 -> RRF(k=60) -> operator-aware router -> cross-encoder rerank "
                        "-> score-floor(calibrated) + dedup",
        },
        "source_pipeline": "kb_build (v0.2 condensed pointer chunks + Phase-2 retrieval artifacts)",
        "notes": "Condensed pointer chunks hydrate from operators.json + Resources via MCP tools. "
                 "graph (gpickle) rebuilt (canonical identity, readMe-clean). lexical_index/ + models/ "
                 "back the Phase-2 retrieval stack in MCP/server_core/search/retrieval_stack.py.",
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_sources_lock(inputs, out_dir)
    # W2d: receipt the staged pickles LAST so it hashes the final bytes
    # (graph rebuilt above, bm25 built above). Without this the runtime
    # refuses to unpickle a maintainer-built KB.
    C.write_kb_receipt(out_dir, "kb_build")
    print(f"\n[staged] {out_dir}")
    print(f"  manifest.json  sources.lock.json  operators.json  vector_db/  knowledge_graph_enhanced.gpickle")


if __name__ == "__main__":
    main()

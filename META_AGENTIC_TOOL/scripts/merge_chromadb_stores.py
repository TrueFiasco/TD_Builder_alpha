#!/usr/bin/env python3
"""B0 — Merge the two existing ChromaDB stores into one unified collection.

Source stores (read via direct sqlite — chromadb 0.5.23 can't open the
legacy schemas):

  - META_AGENTIC_TOOL/chroma_db/chroma.sqlite3
        collection: 'touchdesigner_knowledge'
        ~32,475 docs: per-parameter, per-method, per-class, python_examples,
        operator overviews (short headline form), abstract topology snippets.
        Carries `python_class` metadata the active store lacks.

  - META_AGENTIC_TOOL/data/vector_db/chroma.sqlite3
        collection: 'td_unified'
        ~1,869 docs: full-text operator overviews + concrete example
        networks with real parameter values.

Plus structured KB enrichment:

  - META_AGENTIC_TOOL/data/wiki_docs/td_universal_parsed_enriched.json
        6 operators (DAT to CHOP, SOP to CHOP, CHOP to TOP, Table DAT,
        Composite TOP, Feedback TOP) with hand-curated build_instructions
        (menu_parameters, connection_type, avoid lists, example blocks).
        These are rendered into prose docs and embedded so the strategy
        runner's retrieval can surface them.

Output:

  - META_AGENTIC_TOOL/data/vector_db_merged/   (idempotent — deleted if exists)
        collection: 'td_unified' (preserves the active name; minimises
        downstream code churn)
        Built with chromadb 0.5.x schema, embedded with
        sentence-transformers `all-MiniLM-L6-v2` (same 384-dim model both
        source stores used — verified).

Dedup strategy (revised after empirical analysis of 656 overlap pairs):

  KEEP BOTH operator-overview entries. Earlier draft said "drop the
  orphan stub, keep the longer active text" — wrong. The orphan and
  active operator entries are at different chunking granularities
  (orphan median 313 chars, active median 619 chars) AND carry
  different metadata fields (orphan has `python_class`; active has
  `source`). 75% of orphan stubs are essentially "<name>: " + first
  ~250 chars of active + "Python class: ClassName"; the remaining 25%
  have substantively different summaries. Both serve distinct retrieval
  modes (terse-identifier vs explanatory).

  Concrete rule: take the union. For each overlap pair matched on
  normalised `family + name`, copy the orphan's `python_class` onto
  the active doc's metadata so a single-entry retrieval against the
  active version still surfaces the python-class link. The orphan
  entry stays as-is.

Validation (run separately after this script): query the merged store
with the 8-prompt battery from the investigation. Expected: top-5
results include the union of orphan-best and active-best results from
the investigation; no prompt regresses versus its previous winning
store.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
ORPHAN_DB = REPO / "META_AGENTIC_TOOL" / "chroma_db" / "chroma.sqlite3"
ACTIVE_DB = REPO / "META_AGENTIC_TOOL" / "data" / "vector_db" / "chroma.sqlite3"
ENRICHED_KB = REPO / "META_AGENTIC_TOOL" / "data" / "wiki_docs" / "td_universal_parsed_enriched.json"
DEFAULT_OUTPUT_DIR = REPO / "META_AGENTIC_TOOL" / "data" / "vector_db_merged"
COLLECTION_NAME = "td_unified"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


# ----------------------------------------------------------------------------
# Doc model
# ----------------------------------------------------------------------------


@dataclass
class Doc:
    """One document destined for the merged collection."""

    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Source readers
# ----------------------------------------------------------------------------


def pull_docs_from_sqlite(path: Path, source_label: str, id_prefix: str) -> List[Doc]:
    """Read all (id, document, metadata) rows from a chromadb sqlite store.

    Each row in `embedding_metadata` is `(id, key, string_value, int_value,
    float_value, bool_value)`. We pivot per-id into a single dict; the
    `chroma:document` key holds the text content.
    """
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, key, string_value, int_value, float_value, bool_value "
        "FROM embedding_metadata"
    )
    by_id: Dict[Any, Dict[str, Any]] = {}
    for eid, key, sval, ival, fval, bval in cur.fetchall():
        meta = by_id.setdefault(eid, {})
        if sval is not None:
            meta[key] = sval
        elif ival is not None:
            meta[key] = ival
        elif fval is not None:
            meta[key] = fval
        elif bval is not None:
            meta[key] = bool(bval)
    conn.close()

    docs: List[Doc] = []
    for eid, meta in by_id.items():
        text = meta.pop("chroma:document", "") or ""
        if not text.strip():
            # ChromaDB allows ID-only entries; skip empty content.
            continue
        meta["__source_store"] = source_label
        docs.append(Doc(id=f"{id_prefix}_{eid}", text=text, metadata=meta))
    return docs


# ----------------------------------------------------------------------------
# Metadata normalisation + enrichment
# ----------------------------------------------------------------------------


_OP_NAME_KEY_RE = re.compile(r"\s+")


def _normalize_op_key(family: Optional[str], name: Optional[str]) -> Optional[Tuple[str, str]]:
    """Reduce ('CHOP', 'Noise CHOP') and ('CHOP', 'Noise_CHOP') to a stable key."""
    if not family or not name:
        return None
    return (family.strip().upper(), _OP_NAME_KEY_RE.sub("_", name.strip()))


def enrich_active_with_python_class(orphan_docs: List[Doc], active_docs: List[Doc]) -> int:
    """Copy `python_class` from orphan operator entries onto active doc entries.

    Mutates active_docs in place. Returns number of active entries enriched.
    """
    orphan_by_op = {}
    for d in orphan_docs:
        if d.metadata.get("type") != "operator":
            continue
        key = _normalize_op_key(d.metadata.get("family"), d.metadata.get("name"))
        if key is None:
            continue
        orphan_by_op.setdefault(key, d)

    enriched = 0
    for d in active_docs:
        if d.metadata.get("source") != "docs":
            continue
        key = _normalize_op_key(d.metadata.get("family"), d.metadata.get("name"))
        if key is None:
            continue
        match = orphan_by_op.get(key)
        if match is None:
            continue
        py_class = match.metadata.get("python_class")
        if py_class:
            d.metadata["python_class"] = py_class
            enriched += 1
    return enriched


def sanitize_for_chromadb(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """ChromaDB requires metadata values to be primitive (str/int/float/bool).

    Lists, dicts, and None values are dropped or coerced. Empty strings dropped
    too (Chroma rejects them).
    """
    cleaned: Dict[str, Any] = {}
    for k, v in metadata.items():
        if v is None:
            continue
        if isinstance(v, str):
            if not v:
                continue
            cleaned[k] = v
        elif isinstance(v, (int, float, bool)):
            cleaned[k] = v
        elif isinstance(v, (list, tuple)):
            cleaned[k] = ", ".join(str(x) for x in v if x is not None)
        elif isinstance(v, dict):
            # Skip nested dicts — Chroma can't filter on them anyway.
            continue
        else:
            cleaned[k] = str(v)
    return cleaned


# ----------------------------------------------------------------------------
# BUILD_INSTRUCTIONS ingest
# ----------------------------------------------------------------------------


def _render_build_instruction(name: str, family: str, bi: Dict[str, Any]) -> str:
    """Render a `build_instructions` dict into prose suitable for embedding."""
    lines: List[str] = []
    lines.append(f"Build instructions for {name} ({family} family).")
    lines.append("")

    conn_type = bi.get("connection_type")
    if conn_type:
        lines.append(f"Connection type: {conn_type}.")

    required = bi.get("required_params") or {}
    if required:
        rendered = "; ".join(f"`{p}` ({desc})" for p, desc in required.items())
        lines.append(f"Required parameters: {rendered}.")

    use_defaults = bi.get("use_defaults")
    if use_defaults is True:
        lines.append("Use TD defaults wherever possible — only override when the user explicitly specifies a value.")
    elif use_defaults is False:
        lines.append("Do not assume TD defaults are correct; always set parameters explicitly.")

    menu = bi.get("menu_parameters") or {}
    if menu:
        lines.append("")
        lines.append("Menu parameter rules:")
        for pname, pinfo in menu.items():
            valid = pinfo.get("valid_values") or []
            default = pinfo.get("default")
            rule = pinfo.get("decision_rule") or ""
            valid_str = ", ".join(f"'{v}'" for v in valid) if valid else "(unspecified)"
            default_str = f"'{default}'" if default else "(none)"
            lines.append(f"- `{pname}`: valid values {valid_str}; default {default_str}. {rule}")

    avoid = bi.get("avoid") or []
    if avoid:
        lines.append("")
        lines.append("Avoid these mistakes:")
        for rule in avoid:
            lines.append(f"- {rule}")

    notes = bi.get("notes")
    if notes:
        lines.append("")
        if isinstance(notes, list):
            for note in notes:
                lines.append(f"Note: {note}")
        else:
            lines.append(f"Note: {notes}")

    special = bi.get("special_features")
    if special:
        lines.append("")
        if isinstance(special, list):
            for feat in special:
                lines.append(f"Special feature: {feat}")
        else:
            lines.append(f"Special features: {special}")

    example = bi.get("example")
    if example:
        lines.append("")
        lines.append("Example:")
        if isinstance(example, dict):
            params = example.get("parameters") or {}
            if params:
                rendered = ", ".join(f"{p}={v!r}" for p, v in params.items())
                lines.append(f"- parameters: {rendered}")
            note = example.get("notes") or example.get("note")
            if note:
                lines.append(f"- note: {note}")
            for k, v in example.items():
                if k in ("parameters", "notes", "note"):
                    continue
                lines.append(f"- {k}: {v}")
        else:
            lines.append(f"- {example}")

    return "\n".join(lines).strip() + "\n"


def load_build_instruction_docs(enriched_path: Path) -> List[Doc]:
    """Read the enriched KB and emit one Doc per operator with build_instructions."""
    if not enriched_path.exists():
        print(f"  WARN: enriched KB not found at {enriched_path}; skipping build_instructions")
        return []

    with open(enriched_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    docs: List[Doc] = []
    for op in data.get("operators", []):
        bi = op.get("build_instructions")
        if not bi:
            continue
        name = op.get("name") or ""
        family = (op.get("family") or "").upper()
        if not name or not family:
            continue
        slug = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower()
        text = _render_build_instruction(name, family, bi)
        docs.append(Doc(
            id=f"bi_{slug}",
            text=text,
            metadata={
                "type": "build_instruction",
                "operator_name": name,
                "family": family,
                "source": "enriched_kb",
                "name": name,
                "__source_store": "enriched_kb",
            },
        ))
    return docs


# ----------------------------------------------------------------------------
# Embed + write
# ----------------------------------------------------------------------------


def embed_documents(docs: List[Doc], model_name: str, batch_size: int = 64):
    """Generate embeddings for all docs. Returns numpy ndarray (n, dim)."""
    print(f"  loading sentence-transformers model '{model_name}'...")
    from sentence_transformers import SentenceTransformer  # type: ignore

    t0 = time.time()
    model = SentenceTransformer(model_name)
    print(f"  model ready in {time.time() - t0:.1f}s")

    texts = [d.text for d in docs]
    print(f"  embedding {len(texts)} docs in batches of {batch_size}...")
    t0 = time.time()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
    )
    print(f"  embedded {len(texts)} docs in {time.time() - t0:.0f}s "
          f"({len(texts) / max(time.time() - t0, 1):.1f} docs/s)")
    return embeddings


def write_chromadb_collection(
    docs: List[Doc],
    embeddings,
    output_dir: Path,
    collection_name: str,
    batch_size: int = 1000,
) -> None:
    """Write a fresh chromadb 0.5.x store. Idempotent — deletes output_dir first."""
    if output_dir.exists():
        print(f"  deleting existing output dir {output_dir}...")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)

    import chromadb  # type: ignore

    print(f"  creating chromadb client at {output_dir}...")
    client = chromadb.PersistentClient(path=str(output_dir))
    coll = client.create_collection(
        name=collection_name,
        metadata={"description": "Merged TD knowledge base — orphan + active + build_instructions"},
    )

    n = len(docs)
    print(f"  upserting {n} docs into collection '{collection_name}' (batch={batch_size})...")
    for i in range(0, n, batch_size):
        end = min(i + batch_size, n)
        batch = docs[i:end]
        coll.add(
            ids=[d.id for d in batch],
            documents=[d.text for d in batch],
            embeddings=[embeddings[j].tolist() for j in range(i, end)],
            metadatas=[sanitize_for_chromadb(d.metadata) for d in batch],
        )
        print(f"    [{end}/{n}]")
    print(f"  collection.count() = {coll.count()}")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Merge ChromaDB stores into a unified collection.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"Output dir (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--collection", default=COLLECTION_NAME, help="Output collection name")
    parser.add_argument("--model", default=EMBEDDING_MODEL, help="sentence-transformers model")
    parser.add_argument("--no-embed", action="store_true",
                        help="Skip embedding + write; print what would be merged. Useful for dry runs.")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    args = parser.parse_args(argv)

    print(f"\n{'='*72}")
    print(f"B0 — ChromaDB merge")
    print(f"{'='*72}")
    print(f"  orphan store : {ORPHAN_DB}")
    print(f"  active store : {ACTIVE_DB}")
    print(f"  enriched KB  : {ENRICHED_KB}")
    print(f"  output       : {args.output}  (collection={args.collection!r})")
    print(f"  model        : {args.model}")

    # 1. Pull source docs
    print(f"\n[1/5] reading source stores via direct sqlite...")
    orphan_docs = pull_docs_from_sqlite(ORPHAN_DB, "orphan", "orphan")
    active_docs = pull_docs_from_sqlite(ACTIVE_DB, "active", "active")
    print(f"  orphan: {len(orphan_docs)} docs")
    print(f"  active: {len(active_docs)} docs")

    # 2. Enrich active with python_class from orphan operator overlap pairs
    print(f"\n[2/5] enriching active operator overviews with orphan's python_class...")
    enriched_count = enrich_active_with_python_class(orphan_docs, active_docs)
    print(f"  enriched {enriched_count} active doc entries with python_class")

    # 3. Load BUILD_INSTRUCTIONS
    print(f"\n[3/5] loading BUILD_INSTRUCTIONS from enriched KB...")
    bi_docs = load_build_instruction_docs(ENRICHED_KB)
    print(f"  ingested {len(bi_docs)} build_instruction docs:")
    for d in bi_docs:
        print(f"    - {d.metadata.get('operator_name')} ({d.metadata.get('family')})")

    # 4. Combine corpus
    all_docs = orphan_docs + active_docs + bi_docs
    print(f"\n[4/5] merged corpus: {len(all_docs)} docs total")
    print(f"  by source: orphan={len(orphan_docs)}, active={len(active_docs)}, build_instructions={len(bi_docs)}")

    if args.no_embed:
        print(f"\n--no-embed set; stopping here. Would write to {args.output}.")
        return 0

    # 5. Embed + write
    print(f"\n[5/5] embedding + writing chromadb 0.5.x store...")
    embeddings = embed_documents(all_docs, args.model, batch_size=args.batch_size)
    write_chromadb_collection(all_docs, embeddings, args.output, args.collection)

    print(f"\n{'='*72}")
    print(f"DONE. Merged store at {args.output}")
    print(f"  collection: {args.collection!r}")
    print(f"  doc count : {len(all_docs)}")
    print(f"{'='*72}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

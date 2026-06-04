#!/usr/bin/env python3
"""
Create a ChromaDB collection from the existing Phase-5 vector artifacts:
- vector_db/vector_index.json
- vector_db/embeddings.npy
- vector_db/embedding_ids.json

This avoids recomputing embeddings and makes it possible to use Chroma as a
single vector DB backend (metadata filtering + persistence).

Recommended runtime: Python 3.11 (see kb_pipeline/.venv_py311).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

KB_ROOT = Path(__file__).parent
VECTOR_DB = KB_ROOT / "vector_db"


def _coerce_chroma_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chroma metadata must be a dict of scalar values (str/int/float/bool).
    We stringify lists/dicts in a stable way.
    """
    out: Dict[str, Any] = {}
    for key, value in (meta or {}).items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
        elif isinstance(value, list):
            out[key] = "|".join(str(v) for v in value)
        elif isinstance(value, dict):
            out[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            out[key] = str(value)
    return out


def build_chroma(
    out_dir: Path,
    collection_name: str = "td_unified",
    batch_size: int = 500,
) -> None:
    # Disable telemetry to keep the environment quiet/offline-friendly.
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

    try:
        import chromadb
    except Exception as e:
        raise RuntimeError(
            "chromadb is not available in this Python environment. "
            "Run using kb_pipeline/.venv_py311."
        ) from e

    index_path = VECTOR_DB / "vector_index.json"
    ids_path = VECTOR_DB / "embedding_ids.json"
    emb_path = VECTOR_DB / "embeddings.npy"

    rows = json.loads(index_path.read_text(encoding="utf-8"))
    id_order: List[str] = json.loads(ids_path.read_text(encoding="utf-8"))
    embeddings = np.load(emb_path)

    if embeddings.shape[0] != len(id_order):
        raise ValueError(f"embeddings rows={embeddings.shape[0]} but embedding_ids={len(id_order)}")

    by_id: Dict[str, Dict[str, Any]] = {r["id"]: r for r in rows if isinstance(r, dict) and "id" in r}
    missing = [chunk_id for chunk_id in id_order if chunk_id not in by_id]
    if missing:
        raise ValueError(f"vector_index.json missing {len(missing)} IDs (example: {missing[0]})")

    # Chroma requires unique IDs; vector_index IDs can contain duplicates (rare).
    # We keep the original ID in metadata as `orig_id` and disambiguate the Chroma ID.
    seen: Dict[str, int] = {}
    chroma_ids: List[str] = []
    orig_ids: List[str] = []
    duplicate_total = 0
    for orig_id in id_order:
        count = seen.get(orig_id, 0)
        if count == 0:
            chroma_id = orig_id
        else:
            duplicate_total += 1
            chroma_id = f"{orig_id}__dup{count}"
        seen[orig_id] = count + 1
        chroma_ids.append(chroma_id)
        orig_ids.append(orig_id)

    if duplicate_total:
        print(f"Warning: Found {duplicate_total} duplicate IDs; disambiguating for Chroma.")

    out_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(out_dir))

    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    coll = client.create_collection(collection_name)

    total = len(orig_ids)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch_orig_ids = orig_ids[start:end]
        batch_chroma_ids = chroma_ids[start:end]
        batch_rows = [by_id[i] for i in batch_orig_ids]

        coll.upsert(
            ids=batch_chroma_ids,
            embeddings=embeddings[start:end].tolist(),
            documents=[r.get("text", "") for r in batch_rows],
            metadatas=[
                {
                    **_coerce_chroma_metadata(r.get("meta", {})),
                    "orig_id": r.get("id", ""),
                }
                for r in batch_rows
            ],
        )
        print(f"Upserted {end}/{total}")

    print(f"[OK] Chroma collection '{collection_name}' ready at: {out_dir}")


def main(argv: Optional[List[str]] = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Create ChromaDB from existing embeddings.npy + vector_index.json")
    parser.add_argument("--out", type=Path, default=KB_ROOT / "vector_db_chroma", help="Output directory for Chroma")
    parser.add_argument("--collection", type=str, default="td_unified", help="Collection name")
    parser.add_argument("--batch-size", type=int, default=500, help="Upsert batch size")
    args = parser.parse_args(argv)

    build_chroma(args.out, collection_name=args.collection, batch_size=args.batch_size)


if __name__ == "__main__":
    main()

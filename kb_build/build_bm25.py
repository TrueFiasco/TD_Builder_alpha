#!/usr/bin/env python3
r"""
Phase-2 BM25 lexical index — id-aligned to the vector DB.

Builds a ``rank_bm25.BM25Okapi`` index over the SAME chunk rows the vector DB
holds, reading them back FROM the built ChromaDB collection so the row<->id
alignment is exact (the dense channel returns Chroma ids; the BM25 channel
returns the identical ids, so RRF fuses on a common key). The index is a small
self-contained pickle (BM25 stats + parallel id/text/meta arrays) that the
runtime ``retrieval_stack`` loads offline — no Chroma round-trip needed for the
lexical channel.

  Output: <KB>/lexical_index/bm25.pkl  (+ row_id_map.json companion)

Wired into ``build_kb`` after ``build_vector_db``; also runnable standalone
against an existing KB so the lexical index can be (re)built without re-embedding:

  py -3.11 kb_build/build_bm25.py                      # default Output/KB
  py -3.11 kb_build/build_bm25.py --kb "<path>/KB"
"""
from __future__ import annotations

import json
import pickle
import re
from pathlib import Path

# Query- and corpus-side tokenizer. retrieval_stack.py MUST tokenize queries
# with this identical pattern (it stores the pattern in the pickle and asserts).
# Lowercase + alphanumeric runs: keeps param codes (rgba16float), splits
# op('noise1').par.amp -> op|noise1|par|amp, folds numSamples -> numsamples.
TOKENIZER_PATTERN = r"[a-z0-9]+"
_TOKEN_RE = re.compile(TOKENIZER_PATTERN)
COLLECTION = "td_unified"


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text).lower())


def build_from_vectordb(out_dir: Path) -> dict:
    """Read every row from <out_dir>/vector_db and write <out_dir>/lexical_index/bm25.pkl."""
    import chromadb
    from rank_bm25 import BM25Okapi

    out_dir = Path(out_dir)
    vdb = out_dir / "vector_db"
    if not (vdb / "chroma.sqlite3").exists():
        raise FileNotFoundError(f"no vector_db at {vdb} — build the vector DB first")

    coll = chromadb.PersistentClient(path=str(vdb)).get_collection(COLLECTION)
    got = coll.get(include=["documents", "metadatas"])   # ids returned by default
    ids: list[str] = got["ids"]
    texts: list[str] = got["documents"]
    metas: list[dict] = got["metadatas"]
    if not ids:
        raise RuntimeError(f"collection '{COLLECTION}' is empty at {vdb}")

    corpus = [tokenize(t) for t in texts]
    bm25 = BM25Okapi(corpus)

    lex = out_dir / "lexical_index"
    lex.mkdir(parents=True, exist_ok=True)
    payload = {
        "bm25": bm25,
        "ids": ids,
        "texts": texts,
        "metas": metas,
        "tokenizer_pattern": TOKENIZER_PATTERN,
        "collection": COLLECTION,
        "count": len(ids),
    }
    with open(lex / "bm25.pkl", "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    (lex / "row_id_map.json").write_text(json.dumps(ids), encoding="utf-8")
    return {"count": len(ids), "path": str(lex / "bm25.pkl"),
            "size_bytes": (lex / "bm25.pkl").stat().st_size}


def build(idn=None, out_dir: Path | None = None) -> dict:
    """build_kb-compatible entry point (idn unused; lexical index is content-only)."""
    if out_dir is None:
        import common as C
        out_dir = C.OUT
    return build_from_vectordb(Path(out_dir))


if __name__ == "__main__":
    import argparse
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import common as C  # noqa: E402

    ap = argparse.ArgumentParser(description="Build the Phase-2 BM25 lexical index")
    ap.add_argument("--kb", default=str(C.OUT), help="KB root containing vector_db/ (default: Output/KB)")
    args = ap.parse_args()
    res = build_from_vectordb(Path(args.kb))
    print(f"[bm25] indexed {res['count']} rows -> {res['path']} ({res['size_bytes']/1e6:.2f} MB)")
    # standalone rebuild replaced bm25.pkl in an existing KB -> re-receipt it
    # (inside build_kb the final kb_build receipt covers this instead)
    C.write_kb_receipt(Path(args.kb), "build_bm25")

#!/usr/bin/env python3
r"""
TD Builder v0.2 Phase-3 — re-embed the EXACT Phase-2 chunk set into a separate
KB per embedder/regime "arm" (the clean, reversible A/B build side).

The shipped MiniLM KB (``New KB build/Output/KB``) is indexed UN-normalized under
Chroma's default squared-L2 space. ``all-MiniLM-L6-v2`` is a cosine model, so part
of the held-out recall gap may be a NORMALIZATION artifact rather than a model
limitation. To separate the two we re-embed the *same chunks* under several arms:

  minilm_norm  all-MiniLM-L6-v2          normalize=True             (no fetch)
  bge          BAAI/bge-small-en-v1.5    normalize=True, q-prefix   (1x fetch)
  gte          Alibaba-NLP/gte-small     normalize=True             (1x fetch)   [sweep]
  e5           intfloat/e5-small-v2      normalize=True, q+p-prefix (1x fetch)   [sweep]

Rigor: chunk identity is taken VERBATIM from the source KB's Chroma collection
(ids / documents / metadatas via ``coll.get`` — the same round-trip build_bm25.py
uses), so only the embedding vectors + normalize regime differ across arms; the
chunk set is byte-identical and ingester nondeterminism is removed as a confound.
The embedder-independent artifacts (lexical_index/ BM25, models/ cross-encoder,
operators.json, gpickle) are COPIED unchanged. A MANDATORY manifest.json records
the arm's model + normalize + query_prefix so the query side selects the right
regime from ``--kb`` alone (see search_docs.py). Outputs stage under
``New KB build/Output/<arm out>`` — NEVER committed.

  py -3.11 kb_build/reembed.py --arm minilm_norm
  py -3.11 kb_build/reembed.py --arm bge
  py -3.11 kb_build/reembed.py --arm gte           # conditional sweep
  py -3.11 kb_build/reembed.py --arm e5            # conditional sweep
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

COLLECTION = "td_unified"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Each arm = (model, normalize regime, query/passage instruction prefixes, out dir).
# query_prefix is applied to the QUERY at search time (recorded in the manifest);
# passage_prefix is applied to PASSAGES here at build time (e5's asymmetric scheme).
ARMS: dict[str, dict] = {
    "minilm_norm": {"model_id": "all-MiniLM-L6-v2",        "normalize": True,
                    "query_prefix": "",               "passage_prefix": "",          "out": "KB_minilm_norm"},
    "bge":         {"model_id": "BAAI/bge-small-en-v1.5",  "normalize": True,
                    "query_prefix": BGE_QUERY_PREFIX, "passage_prefix": "",          "out": "KB_bge"},
    "gte":         {"model_id": "thenlper/gte-small",      "normalize": True,
                    "query_prefix": "",               "passage_prefix": "",          "out": "KB_gte"},
    "e5":          {"model_id": "intfloat/e5-small-v2",    "normalize": True,
                    "query_prefix": "query: ",        "passage_prefix": "passage: ", "out": "KB_e5"},
    # 768-dim arms (their Chroma collections are 768-dim — fine, each is its own KB).
    "bge_base":    {"model_id": "BAAI/bge-base-en-v1.5",   "normalize": True,
                    "query_prefix": BGE_QUERY_PREFIX, "passage_prefix": "",          "out": "KB_bge_base"},
    # thenlper/gte-base (v1.0, 768, no prefix, standard BERT) — avoids the trust_remote_code
    # that Alibaba-NLP/gte-base-en-v1.5 requires; consistent with the thenlper/gte-small arm.
    "gte_base":    {"model_id": "thenlper/gte-base",       "normalize": True,
                    "query_prefix": "",               "passage_prefix": "",          "out": "KB_gte_base"},
}

COPY_FILES = ["operators.json", "knowledge_graph_enhanced.gpickle"]
COPY_DIRS = ["lexical_index", "models"]


def _read_collection(kb_root: Path):
    import chromadb
    vdb = Path(kb_root) / "vector_db"
    if not (vdb / "chroma.sqlite3").exists():
        raise FileNotFoundError(f"no vector_db at {vdb}")
    coll = chromadb.PersistentClient(path=str(vdb)).get_collection(COLLECTION)
    got = coll.get(include=["documents", "metadatas"])   # ids returned by default
    return got["ids"], got["documents"], got["metadatas"]


def _hf_snapshot_sha(model_id: str):
    """Resolved HF snapshot commit hash from the local cache (provenance pin)."""
    from huggingface_hub import snapshot_download
    for rid in (model_id, f"sentence-transformers/{model_id}"):
        try:
            return Path(snapshot_download(rid, local_files_only=True)).name
        except Exception:
            continue
    return None


def reembed(arm_key: str, source_kb: Path, out_root: Path) -> dict:
    arm = ARMS[arm_key]
    model_id = arm["model_id"]
    normalize = arm["normalize"]
    qpre = arm["query_prefix"]
    ppre = arm["passage_prefix"]
    out_kb = Path(out_root) / arm["out"]
    src = Path(source_kb)

    print(f"[reembed] arm={arm_key} model={model_id} normalize={normalize} "
          f"qpre={qpre!r} ppre={ppre!r}\n          source={src}\n          out={out_kb}")

    ids, docs, metas = _read_collection(src)
    n = len(ids)
    print(f"[reembed] source rows: {n}")
    if n == 0:
        raise RuntimeError(f"source collection '{COLLECTION}' is empty at {src}")

    # --- one-time ONLINE fetch: clear offline pins just for the load+encode -----
    for v in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ.pop(v, None)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_id)
    passages = [ppre + d for d in docs] if ppre else docs
    threads = max(1, (os.cpu_count() or 4) - 2)   # multi-thread the one-shot passage embed
    print(f"[reembed] embedding {n} passages (normalize={normalize}, threads={threads})...")
    embs = C._encode(model, passages, normalize=normalize, threads=threads)

    # --- write the new collection: ids / documents / metadatas VERBATIM --------
    import chromadb
    vdb = out_kb / "vector_db"
    if vdb.exists():
        shutil.rmtree(vdb)
    vdb.mkdir(parents=True, exist_ok=True)
    coll = chromadb.PersistentClient(path=str(vdb)).create_collection(COLLECTION)  # default L2
    batch = 512
    for i in range(0, n, batch):
        j = min(i + batch, n)
        coll.upsert(ids=ids[i:j], embeddings=[e.tolist() for e in embs[i:j]],
                    documents=docs[i:j], metadatas=metas[i:j])
    count = coll.count()
    print(f"[reembed] wrote {count} docs -> {vdb}")

    # --- copy the embedder-independent artifacts unchanged ---------------------
    for name in COPY_FILES:
        if (src / name).exists():
            shutil.copy2(src / name, out_kb / name)
            print(f"[reembed] copied {name}")
        else:
            print(f"[reembed] WARNING: source missing {name}")
    for d in COPY_DIRS:
        if (src / d).exists():
            dst = out_kb / d
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src / d, dst)
            print(f"[reembed] copied {d}/")
        else:
            print(f"[reembed] WARNING: source missing {d}/")

    # --- provenance sha + OFFLINE smoke-load (prove the eval host can go offline)
    sha = _hf_snapshot_sha(model_id)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    SentenceTransformer(model_id)   # raises if the model is not self-contained in the HF cache
    print(f"[reembed] offline smoke-load OK; hf_snapshot_sha={sha}")

    # --- MANDATORY manifest.json (the query side reads model+normalize+prefix) --
    generated = datetime.now(timezone.utc).isoformat()
    has_bm25 = (out_kb / "lexical_index" / "bm25.pkl").exists()
    has_ce = (out_kb / "models" / "ms-marco-MiniLM-L-6-v2" / "config.json").exists()
    manifest = {
        "phase": "3-embedder-ab",
        "arm": arm_key,
        "generated": generated,
        "td_build": C.TD_BUILD,
        "embedding_model": model_id,
        "normalize": normalize,
        "query_prefix": qpre,
        "passage_prefix": ppre,
        "hf_snapshot_sha": sha,
        "collection": COLLECTION,
        "chunk_count": n,
        "vectordb_count": count,
        "source_kb": str(src),
        "retrieval_stack": {
            "bm25_index": "lexical_index/bm25.pkl" if has_bm25 else None,
            "reranker": "models/ms-marco-MiniLM-L-6-v2" if has_ce else None,
        },
        "notes": ("Phase-3 re-embed of the EXACT Phase-2 chunk set: ids/documents/metadatas taken "
                  "verbatim from source_kb's Chroma collection; only the embedding vectors + the "
                  "normalize regime differ. lexical_index/, models/, operators.json, gpickle copied "
                  "unchanged. query_prefix is applied to the QUERY at search time; passage_prefix was "
                  "applied to passages at build time."),
    }
    out_kb.mkdir(parents=True, exist_ok=True)
    (out_kb / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # --- sources.lock.json (pin model + sha + TD build; carry the source lock) --
    lock = {
        "td_build": C.TD_BUILD,
        "embedding_model": model_id,
        "normalize": normalize,
        "query_prefix": qpre,
        "passage_prefix": ppre,
        "hf_snapshot_sha": sha,
        "source_kb": str(src),
        "generated": generated,
    }
    if (src / "sources.lock.json").exists():
        try:
            lock["source_lock"] = json.loads((src / "sources.lock.json").read_text(encoding="utf-8"))
        except Exception:
            pass
    (out_kb / "sources.lock.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")

    # --- verification: id-set parity + count match vs source -------------------
    out_ids = _read_collection(out_kb)[0]
    id_parity = set(ids) == set(out_ids)
    print(f"[reembed] id-set parity vs source: {id_parity}; count match: {count == n} ({count} vs {n})")
    if not id_parity or count != n:
        raise RuntimeError("FAITHFULNESS CHECK FAILED: id-set or count differs from source")
    return {"arm": arm_key, "out": str(out_kb), "count": count, "n": n,
            "id_parity": id_parity, "hf_snapshot_sha": sha}


def main():
    ap = argparse.ArgumentParser(description="Phase-3 re-embed one arm into a separate KB")
    ap.add_argument("--arm", required=True, choices=sorted(ARMS), help="embedder/regime arm")
    ap.add_argument("--source", default=str(C.OUT),
                    help="source KB to re-embed (default: Output/KB = the MiniLM control)")
    ap.add_argument("--out-root", default=str(C.OUT.parent),
                    help="output root for KB_<arm> (default: Output/)")
    args = ap.parse_args()
    res = reembed(args.arm, Path(args.source), Path(args.out_root))
    print(f"[reembed] DONE: {json.dumps(res)}")


if __name__ == "__main__":
    main()

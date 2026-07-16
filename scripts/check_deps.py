#!/usr/bin/env python3
"""Dependency + knowledge-base readiness checker for TD Builder.

Run from the repo root:  python scripts/check_deps.py

Verifies the Python version is in the supported range, the runtime packages
import, and the knowledge base is present. Prints a green/red checklist with a
one-line fix for each problem. Exit code 0 = ready, 1 = something needs attention.
No API key required — this release is fully key-free / local-only.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OK = "[ OK ]"
BAD = "[FAIL]"


def _vector_db_doc_count(vdb: Path) -> int | None:
    """Chroma document count via fetch_vector_db's seam (single source of
    populated-truth; None = chromadb not importable, unmeasurable)."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location(
            "td_fetch_vector_db", str(Path(__file__).with_name("fetch_vector_db.py")))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod._vector_db_doc_count(vdb)
    except Exception:  # noqa: BLE001 — diagnostics must never crash
        return None


def main() -> int:
    problems: list[str] = []

    # Python version: 3.10-3.13 (chromadb / sentence-transformers cap at <3.14)
    v = sys.version_info
    if (3, 10) <= (v.major, v.minor) < (3, 14):
        print(f"{OK} Python {v.major}.{v.minor}.{v.micro}")
    else:
        print(f"{BAD} Python {v.major}.{v.minor} - need >=3.10,<3.14 (3.11 recommended)")
        problems.append("Install Python 3.11, then recreate the venv: py -3.11 -m venv .venv")

    # Runtime packages (all installed by `pip install -e .`)
    pkgs = {
        "mcp": "pip install -e .",
        "chromadb": "pip install -e .",
        "sentence_transformers": "pip install -e .",
        "numpy": "pip install -e .",
        "sklearn": "pip install -e .   (provides scikit-learn)",
        "networkx": "pip install -e .",
        "yaml": "pip install -e .   (provides pyyaml)",
        "jsonschema": "pip install -e .",
        "httpx": "pip install -e .",
        "rank_bm25": "pip install -e .   (provides rank-bm25; without it hybrid BM25 retrieval is dead)",
    }
    for mod, fix in pkgs.items():
        try:
            importlib.import_module(mod)
            print(f"{OK} import {mod}")
        except Exception as e:  # noqa: BLE001
            print(f"{BAD} import {mod} - {e}")
            problems.append(fix)

    # Fetched KB artifacts (not in git — downloaded by scripts/fetch_vector_db.py).
    # This set mirrors fetch_vector_db._already_populated().
    kb = REPO_ROOT / "KB"
    for rel in ("operators.json", "knowledge_graph_enhanced.gpickle"):
        p = kb / rel
        if p.exists():
            print(f"{OK} KB/{rel} ({p.stat().st_size // (1024 * 1024)} MB)")
        else:
            print(f"{BAD} KB/{rel} missing")
            problems.append("Download the KB bundle: python scripts/fetch_vector_db.py")

    # Vector store — same health rules as fetch_vector_db._already_populated():
    # Chroma's sqlite must exist AND (when chromadb is importable) hold >0
    # documents. An empty-but-present store is the trap where the server loads
    # "successfully" and semantic search returns nothing forever.
    vdb = kb / "vector_db"
    if not (vdb.exists() and any(vdb.iterdir())):
        print(f"{BAD} KB/vector_db/ empty - semantic search unavailable")
        problems.append("Download the KB bundle: python scripts/fetch_vector_db.py")
    elif not (vdb / "chroma.sqlite3").exists():
        print(f"{BAD} KB/vector_db/ has no Chroma store (chroma.sqlite3 missing)")
        problems.append("Re-fetch the KB bundle: python scripts/fetch_vector_db.py")
    else:
        count = _vector_db_doc_count(vdb)
        if count is None:
            print(f"{OK} KB/vector_db/ present (document count unverified - chromadb not importable)")
        elif count > 0:
            print(f"{OK} KB/vector_db/ populated ({count:,} documents)")
        else:
            print(f"{BAD} KB/vector_db/ EMPTY (0 documents) - semantic search would return nothing")
            problems.append("Re-fetch the KB bundle: python scripts/fetch_vector_db.py")

    # Phase-2 retrieval stack: BM25 lexical index + bundled cross-encoder reranker
    bm25 = kb / "lexical_index" / "bm25.pkl"
    if bm25.exists():
        print(f"{OK} KB/lexical_index/bm25.pkl ({bm25.stat().st_size // (1024 * 1024)} MB)")
    else:
        print(f"{BAD} KB/lexical_index/bm25.pkl missing - hybrid (BM25) retrieval unavailable")
        problems.append("Download the KB bundle: python scripts/fetch_vector_db.py")

    reranker = kb / "models" / "ms-marco-MiniLM-L-6-v2" / "config.json"
    if reranker.exists():
        print(f"{OK} KB/models/ms-marco-MiniLM-L-6-v2/ (bundled reranker)")
    else:
        print(f"{BAD} KB/models/ms-marco-MiniLM-L-6-v2/ missing - reranking unavailable")
        problems.append("Download the KB bundle: python scripts/fetch_vector_db.py")

    print()
    if problems:
        print(f"{len(problems)} issue(s) to fix:")
        for i, fix in enumerate(dict.fromkeys(problems), 1):
            print(f"  {i}. {fix}")
        return 1
    print("All good - TD Builder is ready. Register MCP/server.py (offline) and MCP/live_server.py (live) with your MCP client.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

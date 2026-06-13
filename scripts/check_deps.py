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
    }
    for mod, fix in pkgs.items():
        try:
            importlib.import_module(mod)
            print(f"{OK} import {mod}")
        except Exception as e:  # noqa: BLE001
            print(f"{BAD} import {mod} - {e}")
            problems.append(fix)

    # Pre-built KB artifacts (ship in-tree)
    kb = REPO_ROOT / "KB"
    for rel in ("operators.json", "graphrag.json", "knowledge_graph_enhanced.gpickle"):
        p = kb / rel
        if p.exists():
            print(f"{OK} KB/{rel} ({p.stat().st_size // (1024 * 1024)} MB)")
        else:
            print(f"{BAD} KB/{rel} missing")
            problems.append("Download the KB bundle: python scripts/fetch_vector_db.py")

    # Vector DB (fetched, not in git)
    vdb = kb / "vector_db"
    if vdb.exists() and any(vdb.iterdir()):
        print(f"{OK} KB/vector_db/ populated")
    else:
        print(f"{BAD} KB/vector_db/ empty - semantic search unavailable")
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

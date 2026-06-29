#!/usr/bin/env python3
r"""
Phase-2 reranker bundle — fetch the cross-encoder ONCE and stage it under
``<KB>/models/`` so the runtime ``retrieval_stack`` loads it fully OFFLINE.

The build host fetches ``cross-encoder/ms-marco-MiniLM-L-6-v2`` (~80 MB) from the
HF hub a single time and saves a self-contained copy to::

    <KB>/models/ms-marco-MiniLM-L-6-v2/

which ``CrossEncoder(<local-dir>)`` then loads with HF_HUB_OFFLINE=1 — no API,
no network at query time. Model weights are NEVER committed (staged under
``New KB build/Output``, gitignored, shipped only in the sha256-pinned bundle).

  py -3.11 kb_build/build_models.py                    # default Output/KB
  py -3.11 kb_build/build_models.py --kb "<path>/KB" --force
"""
from __future__ import annotations

import os
from pathlib import Path

CE_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
CE_DIRNAME = "ms-marco-MiniLM-L-6-v2"


def build_models(out_dir: Path, force: bool = False) -> dict:
    dest = Path(out_dir) / "models" / CE_DIRNAME
    if (dest / "config.json").exists() and not force:
        return {"status": "exists", "path": str(dest)}

    # one-time ONLINE fetch — clear offline pins for this process only
    for v in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ.pop(v, None)
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from sentence_transformers import CrossEncoder

    ce = CrossEncoder(CE_MODEL)
    dest.mkdir(parents=True, exist_ok=True)
    ce.save(str(dest))

    # smoke-load OFFLINE to prove the bundle is self-contained
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    ce2 = CrossEncoder(str(dest))
    score = float(ce2.predict([("noise texture generator",
                                "Noise TOP generates procedural noise textures")])[0])
    return {"status": "saved", "path": str(dest), "offline_smoke_score": round(score, 3)}


def build(idn=None, out_dir: Path | None = None, force: bool = False) -> dict:
    """build_kb-compatible entry point (idn unused)."""
    if out_dir is None:
        import common as C
        out_dir = C.OUT
    return build_models(Path(out_dir), force=force)


if __name__ == "__main__":
    import argparse
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import common as C  # noqa: E402

    ap = argparse.ArgumentParser(description="Bundle the Phase-2 cross-encoder reranker")
    ap.add_argument("--kb", default=str(C.OUT), help="KB root to stage models/ under (default: Output/KB)")
    ap.add_argument("--force", action="store_true", help="re-download even if already bundled")
    args = ap.parse_args()
    res = build_models(Path(args.kb), force=args.force)
    print(f"[models] {res['status']}: {res['path']}"
          + (f"  (offline smoke score {res['offline_smoke_score']})" if "offline_smoke_score" in res else ""))

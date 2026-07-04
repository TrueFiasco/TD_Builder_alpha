"""Download and extract the TD Builder knowledge base from the public GitHub Release.

Run from the repo root:  python scripts/fetch_vector_db.py

The runtime KB — `operators.json`, the knowledge graph, the vector store, the
BM25 lexical index, and the bundled cross-encoder reranker (~180 MB) — is
distributed as a single GitHub Release asset rather than committed to the repo
(it would bloat every clone). The download uses a plain public HTTPS request:
no `gh` CLI, no auth, no GitHub account needed. If the release is private it
falls back to `gh release download` (your `gh` token).

Skips if `KB/` is already populated (`operators.json` + a non-empty `vector_db/` +
the Phase-2 `lexical_index/bm25.pkl` and bundled `models/` reranker).
Reads repo/tag/asset/sha256 (and optional direct `url`) from
`scripts/vector_db_release.json`, verifies the hash, and extracts into `KB/`.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KB_DIR = REPO_ROOT / "KB"
MANIFEST = Path(__file__).with_name("vector_db_release.json")


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        sys.exit(f"Missing release manifest at {MANIFEST}. Expected keys: repo, tag, asset, sha256.")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _already_populated() -> bool:
    vdb = KB_DIR / "vector_db"
    base = (KB_DIR / "operators.json").exists() and vdb.exists() and any(vdb.iterdir())
    # Phase 2: the retrieval stack also needs the BM25 lexical index and the bundled
    # cross-encoder reranker. Treat the KB as populated only when those are present too,
    # so an older (vector-only) extraction is re-fetched to pick up the new artifacts.
    lexical = (KB_DIR / "lexical_index" / "bm25.pkl").exists()
    reranker = (KB_DIR / "models" / "ms-marco-MiniLM-L-6-v2" / "config.json").exists()
    return base and lexical and reranker


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _kb_integrity():
    """Load MCP/server_core/kb_integrity.py (W2d load-time trust boundary)."""
    import importlib.util
    mod = sys.modules.get("td_kb_integrity")
    if mod is None:
        p = REPO_ROOT / "MCP" / "server_core" / "kb_integrity.py"
        spec = importlib.util.spec_from_file_location("td_kb_integrity", str(p))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["td_kb_integrity"] = mod
        spec.loader.exec_module(mod)
    return mod


def _verify_and_receipt_artifacts(m: dict) -> None:
    """Post-extract: pin-check the pickled artifacts, then write the KB receipt.

    The zip-level sha256 above already proves the bundle; this closes two gaps:
      - artifact pins (manifest `artifact_sha256`) drifting from the published
        zip is a PUBLISHING mistake — fail loudly here (fetch rehearsal / CI
        cold cache) instead of every later server boot refusing to unpickle;
      - the receipt lets this exact extraction keep loading even where the
        repo manifest is not reachable from the KB (KB parked outside a repo).
    """
    ki = _kb_integrity()
    pins = m.get("artifact_sha256") or {}
    if pins:
        for rel, expected in pins.items():
            p = KB_DIR / rel
            if not p.exists():
                sys.exit(f"Pinned artifact missing after extract: {rel}\n"
                         "The release zip and the manifest's artifact_sha256 disagree - "
                         "fix scripts/vector_db_release.json (scripts/receipt_kb.py --print-pins).")
            actual = _sha256(p)
            if actual.lower() != str(expected).lower():
                sys.exit(f"Artifact pin mismatch for {rel}.\n  expected: {expected}\n  actual:   {actual}\n"
                         "The release zip and the manifest's artifact_sha256 disagree - "
                         "fix scripts/vector_db_release.json (scripts/receipt_kb.py --print-pins).")
        print(f"Artifact pins verified: {', '.join(pins)}")
    else:
        print("WARNING: no artifact_sha256 pins in the manifest - the runtime will rely "
              "on the KB receipt alone for pickle integrity.")
    rp = ki.write_receipt(KB_DIR, source="fetch_vector_db",
                          extra={"release_asset": m.get("asset"), "release_tag": m.get("tag")})
    if rp:
        print(f"Wrote KB receipt: {rp}")


def _download_https(url: str, dest: Path) -> bool:
    """Plain public download. Returns True on success, False to allow fallback."""
    try:
        print(f"Downloading {url} ...")
        req = urllib.request.Request(url, headers={"User-Agent": "td-builder-fetch"})
        with urllib.request.urlopen(req) as resp, dest.open("wb") as out:  # noqa: S310
            shutil.copyfileobj(resp, out)
        return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        print(f"  HTTPS download failed ({e}); trying `gh` fallback if available.")
        return False


def _download_gh(repo: str, tag: str, asset: str, out_dir: Path) -> bool:
    if shutil.which("gh") is None:
        return False
    print(f"Downloading {asset} via gh from {repo}@{tag} ...")
    r = subprocess.run(
        ["gh", "release", "download", tag, "--repo", repo,
         "--pattern", asset, "--dir", str(out_dir), "--clobber"],
        check=False,
    )
    return r.returncode == 0


def main() -> int:
    if _already_populated():
        print(f"KB/ already populated - nothing to do. ({KB_DIR})")
        return 0

    m = _load_manifest()
    repo, tag, asset = m["repo"], m["tag"], m["asset"]
    expected_sha = m.get("sha256")
    url = m.get("url") or f"https://github.com/{repo}/releases/download/{tag}/{asset}"

    dl_dir = REPO_ROOT / ".kb_download"
    dl_dir.mkdir(exist_ok=True)
    zip_path = dl_dir / asset

    if not _download_https(url, zip_path):
        if not _download_gh(repo, tag, asset, dl_dir):
            sys.exit(
                "Could not download the KB bundle.\n"
                f"  Tried: {url}\n"
                "  Public HTTPS failed and `gh` is unavailable/unauthenticated.\n"
                "  Fix: confirm the release asset exists and is public, or install +\n"
                "       auth the GitHub CLI (winget install GitHub.cli; gh auth login)."
            )

    if expected_sha:
        actual = _sha256(zip_path)
        if actual.lower() != expected_sha.lower():
            sys.exit(f"SHA256 mismatch for {asset}.\n  expected: {expected_sha}\n  actual:   {actual}\n"
                     "Refusing to extract. Delete the file and retry.")
        print(f"SHA256 verified: {actual}")
    else:
        print("WARNING: no sha256 in manifest - skipping verification.")

    KB_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Extracting the KB bundle into {KB_DIR} ...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(KB_DIR)

    _verify_and_receipt_artifacts(m)

    zip_path.unlink(missing_ok=True)
    try:
        dl_dir.rmdir()
    except OSError:
        pass
    print("Done. KB/ now has operators.json, the graph, vector_db/, lexical_index/, and models/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

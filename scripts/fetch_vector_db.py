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

import contextlib
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
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


def _vector_db_doc_count(vdb: Path) -> int | None:
    """Document count of the Chroma store, measured with a stdlib sqlite3
    READ-ONLY probe of ``chroma.sqlite3`` — deliberately NOT chromadb.

    chromadb's ``PersistentClient`` keeps the sqlite file open for the life of
    the process (Rust bindings, no close API; ``clear_system_cache()`` does not
    release it), so on Windows a chromadb probe here made the later
    ``_retire_unhealthy_vector_db`` rename fail against OUR OWN handle
    (WinError 5) while the error blamed a phantom "running MCP server" — and
    every retry re-downloaded the bundle first. The sqlite connection below is
    closed deterministically, so callers may rename/move the store right after
    probing. Bonus: the probe now works before deps are installed at all.

    Contract:
      - None  -> nothing to measure: ``chroma.sqlite3`` does not exist.
      - 0     -> measured unusable: the file exists but the ``td_unified``
                 collection is missing / holds zero embedding rows, or the
                 file is unreadable at the sqlite level (corrupt, not a
                 database, not a Chroma schema). The store holds nothing
                 usable either way.
      - N > 0 -> healthy: N embedding rows in the ``td_unified`` collection
                 (matches chromadb's ``collection.count()``).
    (check_deps.py mirrors this contract; keep the two in sync.)
    """
    db = vdb / "chroma.sqlite3"
    if not db.exists():
        return None
    try:
        # closing(): a bare `with sqlite3.connect(...)` only ends the
        # transaction — it does NOT release the file handle we exist to release.
        with contextlib.closing(
                sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM embeddings e"
                " JOIN segments s ON e.segment_id = s.id"
                " WHERE s.collection ="
                "   (SELECT id FROM collections WHERE name = ?)",
                ("td_unified",),
            ).fetchone()[0]
    except Exception:
        return 0


def _already_populated() -> bool:
    vdb = KB_DIR / "vector_db"
    base = (KB_DIR / "operators.json").exists() and vdb.exists() and any(vdb.iterdir())
    if not base:
        return False
    # KB health gate: a vector_db that exists but holds ZERO documents used to
    # count as "populated", trapping the user in a loop (the MCP server says
    # "run fetch_vector_db.py", this script says "nothing to do"). Require
    # Chroma's sqlite file and a non-zero measured document count. The stdlib
    # sqlite probe needs no installed deps, so there is no bootstrap fallback
    # any more: None (store vanished mid-check) and 0 (measured unusable)
    # both mean "not populated".
    if not (vdb / "chroma.sqlite3").exists():
        return False
    if not _vector_db_doc_count(vdb):
        return False
    # Phase 2: the retrieval stack also needs the BM25 lexical index and the bundled
    # cross-encoder reranker. Treat the KB as populated only when those are present too,
    # so an older (vector-only) extraction is re-fetched to pick up the new artifacts.
    lexical = (KB_DIR / "lexical_index" / "bm25.pkl").exists()
    reranker = (KB_DIR / "models" / "ms-marco-MiniLM-L-6-v2" / "config.json").exists()
    return lexical and reranker


def _retire_unhealthy_vector_db() -> None:
    """Move an existing-but-unhealthy vector_db/ aside before extraction.

    Called only after the bundle is downloaded and sha-verified, so a manifest
    or download failure can never touch the existing dir. Unhealthy = Chroma
    sqlite missing, or a measured document count of zero / unreadable store.
    Renamed, never deleted (non-destructive); extracting straight over a stale
    store would interleave the fresh sqlite with orphaned segment dirs.
    """
    vdb = KB_DIR / "vector_db"
    if not vdb.exists() or not any(vdb.iterdir()):
        return  # nothing there (or bare dir): extraction fills it fresh
    if (vdb / "chroma.sqlite3").exists():
        count = _vector_db_doc_count(vdb)
        if count is not None and count > 0:
            return  # healthy: leave it alone
        # None (sqlite vanished since the check above) falls through: a
        # sqlite-less dir is retired just like the no-sqlite branch below.
    stem = f"vector_db.bad-{time.strftime('%Y%m%d-%H%M%S')}"
    graveyard = vdb.with_name(stem)
    n = 0
    while graveyard.exists():  # same-second reruns: uniquify, never collide
        n += 1
        graveyard = vdb.with_name(f"{stem}-{n}")
    print(f"Existing {vdb} holds no usable documents - moving it aside to {graveyard}")
    print("  (delete the vector_db.bad-* dir once the fresh KB works)")
    try:
        vdb.rename(graveyard)
    except OSError as e:
        sys.exit(
            f"Could not move the unhealthy vector_db aside ({e}).\n"
            "  Another process holds KB/vector_db open - stop the MCP server\n"
            "  (and anything else using the KB), then re-run this script."
        )


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

    # Size sanity check BEFORE hashing: a truncated download should say so
    # plainly instead of surfacing as a scary SHA mismatch (two consecutive
    # ~4.6 MiB-short downloads on 2026-07-16 looked like tampering until the
    # sizes were compared). The manifest's size_mb is MiB, rounded — allow 1%.
    expected_mb = m.get("size_mb")
    if expected_mb:
        actual_mb = zip_path.stat().st_size / (1024 * 1024)
        if abs(actual_mb - expected_mb) / expected_mb > 0.01:
            shape = ("truncated/partial download" if actual_mb < expected_mb
                     else "unexpectedly large download")
            sys.exit(f"Size mismatch for {asset}: got {actual_mb:.2f} MiB, "
                     f"manifest says {expected_mb} MiB - {shape}.\n"
                     f"  Delete {zip_path} and retry.")

    if expected_sha:
        actual = _sha256(zip_path)
        if actual.lower() != expected_sha.lower():
            sys.exit(f"SHA256 mismatch for {asset}.\n  expected: {expected_sha}\n  actual:   {actual}\n"
                     "Refusing to extract. Delete the file and retry.")
        print(f"SHA256 verified: {actual}")
    else:
        print("WARNING: no sha256 in manifest - skipping verification.")

    KB_DIR.mkdir(parents=True, exist_ok=True)
    _retire_unhealthy_vector_db()
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

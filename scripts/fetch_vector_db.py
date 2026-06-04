"""Download and extract the vector DB bundle from the latest GitHub Release.

Run from the repo root:  `python scripts/fetch_vector_db.py`

Skips if `KB/vector_db/` already exists and is non-empty. Otherwise reads the
expected release tag + SHA256 from `scripts/vector_db_release.json`, calls
`gh release download` (private-repo friendly — uses your `gh auth` token),
verifies the hash, and extracts to `KB/vector_db/`.

Prereqs:
  - `gh` CLI installed and authenticated  (winget install GitHub.cli; gh auth login)
  - Repo access (private repo: you must be a collaborator)
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = REPO_ROOT / "KB" / "vector_db"
MANIFEST = Path(__file__).with_name("vector_db_release.json")


def _load_manifest() -> dict:
    if not MANIFEST.exists():
        sys.exit(
            f"Missing release manifest at {MANIFEST}. "
            "Expected JSON with keys: repo, tag, asset, sha256."
        )
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def _already_populated() -> bool:
    if not TARGET_DIR.exists():
        return False
    # Treat non-empty as already populated. ChromaDB drops several files;
    # this is a coarse but reliable signal.
    return any(TARGET_DIR.iterdir())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if _already_populated():
        print(f"KB/vector_db/ already populated — nothing to do. ({TARGET_DIR})")
        return 0

    manifest = _load_manifest()
    repo = manifest["repo"]
    tag = manifest["tag"]
    asset = manifest["asset"]
    expected_sha = manifest.get("sha256")

    if not _gh_available():
        sys.exit(
            "`gh` CLI not found on PATH. Install it (winget install GitHub.cli) "
            "and run `gh auth login` first."
        )

    download_dir = REPO_ROOT / ".vector_db_download"
    download_dir.mkdir(exist_ok=True)
    zip_path = download_dir / asset

    print(f"Downloading {asset} from {repo}@{tag}...")
    result = subprocess.run(
        [
            "gh", "release", "download", tag,
            "--repo", repo,
            "--pattern", asset,
            "--dir", str(download_dir),
            "--clobber",
        ],
        check=False,
    )
    if result.returncode != 0:
        sys.exit(
            f"`gh release download` failed (exit {result.returncode}). "
            "Confirm: repo access, gh auth status, and that the tag/asset exist."
        )

    if expected_sha:
        actual = _sha256(zip_path)
        if actual.lower() != expected_sha.lower():
            sys.exit(
                f"SHA256 mismatch for {asset}.\n"
                f"  expected: {expected_sha}\n"
                f"  actual:   {actual}\n"
                "Refusing to extract. Delete the file and retry."
            )
        print(f"SHA256 verified: {actual}")
    else:
        print("WARNING: no sha256 in manifest — skipping verification.")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Extracting to {TARGET_DIR}...")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(TARGET_DIR)

    zip_path.unlink()
    try:
        download_dir.rmdir()
    except OSError:
        pass

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

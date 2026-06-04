#!/usr/bin/env python3
"""
Batch Expand Ground Truth .tox Files
=====================================
Expands all .tox files in the tox/ directory using toeexpand.

Creates:
  - tox_expanded/{filename}.tox.dir/  - Expanded directory structure
  - tox_expanded/{filename}.tox.toc   - Table of contents file

Usage:
  python expand_all.py
"""

import os
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Configuration
TOEEXPAND = r"C:\Program Files\Derivative\TouchDesigner\bin\toeexpand.exe"
TOX_DIR = Path(__file__).parent / "tox"
OUTPUT_DIR = Path(__file__).parent / "tox_expanded"


def expand_tox(tox_path: Path, output_dir: Path) -> tuple[str, bool, str]:
    """
    Expand a single .tox file.

    Returns: (filename, success, error_message)
    """
    filename = tox_path.name

    try:
        # Create output directory for this .tox
        out_path = output_dir / filename

        # toeexpand creates {name}.tox.dir and {name}.tox.toc
        # It needs to be run from the directory where output should go

        # Copy tox to output dir and expand there
        import shutil
        temp_tox = output_dir / filename
        shutil.copy2(tox_path, temp_tox)

        # Run toeexpand
        result = subprocess.run(
            [TOEEXPAND, str(temp_tox)],
            capture_output=True,
            text=True,
            cwd=str(output_dir),
            timeout=60
        )

        # Remove the temp copy
        if temp_tox.exists():
            temp_tox.unlink()

        # Check if expansion was successful
        dir_path = output_dir / f"{filename}.dir"
        toc_path = output_dir / f"{filename}.toc"

        if dir_path.exists() and toc_path.exists():
            return filename, True, ""
        else:
            return filename, False, result.stderr or "No output directory created"

    except subprocess.TimeoutExpired:
        return filename, False, "Timeout after 60s"
    except Exception as e:
        return filename, False, str(e)


def main():
    print("=" * 70)
    print("Batch Expand Ground Truth .tox Files")
    print("=" * 70)

    # Check toeexpand exists
    if not Path(TOEEXPAND).exists():
        print(f"ERROR: toeexpand not found at {TOEEXPAND}")
        sys.exit(1)

    # Check input directory
    if not TOX_DIR.exists():
        print(f"ERROR: TOX directory not found: {TOX_DIR}")
        sys.exit(1)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Get all .tox files
    tox_files = list(TOX_DIR.glob("*.tox"))
    total = len(tox_files)

    print(f"\nInput:  {TOX_DIR}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Found:  {total} .tox files")
    print()

    if total == 0:
        print("No .tox files found!")
        sys.exit(1)

    # Process files
    results = {
        'success': [],
        'failed': []
    }

    start_time = time.time()

    # Process sequentially (toeexpand may not be thread-safe)
    for idx, tox_path in enumerate(tox_files, 1):
        filename, success, error = expand_tox(tox_path, OUTPUT_DIR)

        if success:
            results['success'].append(filename)
            status = "OK"
        else:
            results['failed'].append({'name': filename, 'error': error})
            status = f"FAIL: {error[:50]}"

        # Progress
        if idx % 50 == 0 or idx == total:
            elapsed = time.time() - start_time
            rate = idx / elapsed if elapsed > 0 else 0
            eta = (total - idx) / rate if rate > 0 else 0
            print(f"  [{idx:4d}/{total}] {status[:60]:60s} ({rate:.1f}/s, ETA: {eta:.0f}s)")

    # Summary
    elapsed = time.time() - start_time
    print()
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70)
    print(f"\nSuccess: {len(results['success'])}")
    print(f"Failed:  {len(results['failed'])}")
    print(f"Time:    {elapsed:.1f}s")

    if results['failed']:
        print(f"\nFailed files:")
        for fail in results['failed'][:20]:
            print(f"  {fail['name']}: {fail['error']}")
        if len(results['failed']) > 20:
            print(f"  ... and {len(results['failed']) - 20} more")

    # Save results
    import json
    results_path = OUTPUT_DIR / "expansion_results.json"
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {results_path}")

    return len(results['failed']) == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

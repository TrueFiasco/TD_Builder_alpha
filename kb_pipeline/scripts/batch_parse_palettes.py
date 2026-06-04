#!/usr/bin/env python3
"""
Batch parse all palette TOX files to compressed lossless JSON.

Usage:
    python batch_parse_palettes.py

Output:
    kb_pipeline/data/palette_lossless/*.json.gz
    kb_pipeline/data/palette_lossless/index.json
"""

import sys
import json
import gzip
from pathlib import Path
from datetime import datetime

# Add parser path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "td_builder_workspace" / "parsers"))
from toe_to_json_LOSSLESS import LosslessToeToJsonConverter

# Paths
PALETTE_ROOT = Path("C:/TD_Projects/Learn/Palette")
OUTPUT_DIR = Path("C:/TD_Projects/kb_pipeline/data/palette_lossless")
LOG_FILE = OUTPUT_DIR / "parse_log.txt"

# Categories based on directory structure
def get_category(tox_path: Path) -> str:
    """Extract category from path."""
    rel = tox_path.relative_to(PALETTE_ROOT)
    parts = rel.parts
    if len(parts) > 1:
        return parts[0]
    return "Uncategorized"

def parse_single_palette(tox_dir: Path) -> dict:
    """Parse a single palette TOX directory."""
    converter = LosslessToeToJsonConverter(
        tox_dir,
        strip_bloat=True,
        unwrap_palette=True
    )
    return converter.convert()

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Find all expanded palette directories
    tox_dirs = sorted(PALETTE_ROOT.rglob("*.tox.dir"))
    total = len(tox_dirs)

    print(f"Found {total} palette TOX directories")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    # Track results
    index = {
        "version": "1.0",
        "generated": datetime.now().isoformat(),
        "count": 0,
        "palettes": {}
    }

    success = 0
    failed = 0
    log_lines = []

    for i, tox_dir in enumerate(tox_dirs, 1):
        name = tox_dir.name.replace(".tox.dir", "")
        category = get_category(tox_dir)
        output_file = OUTPUT_DIR / f"{name}.json.gz"

        print(f"[{i}/{total}] {name} ({category})...", end=" ", flush=True)

        try:
            # Parse
            data = parse_single_palette(tox_dir)

            # Count operators
            op_count = len(data.get("operators", {}))

            # Compress and save
            json_str = json.dumps(data, indent=None, separators=(',', ':'))
            with gzip.open(output_file, 'wt', encoding='utf-8') as f:
                f.write(json_str)

            # Get file size
            size_bytes = output_file.stat().st_size

            # Add to index
            index["palettes"][name] = {
                "category": category,
                "file": f"{name}.json.gz",
                "size_bytes": size_bytes,
                "operator_count": op_count,
                "source": str(tox_dir.relative_to(PALETTE_ROOT))
            }

            success += 1
            print(f"OK ({op_count} ops, {size_bytes//1024}KB)")
            log_lines.append(f"OK: {name} - {op_count} operators, {size_bytes} bytes")

        except Exception as e:
            failed += 1
            error_msg = str(e)[:100]
            print(f"FAILED: {error_msg}")
            log_lines.append(f"FAILED: {name} - {error_msg}")

    # Update count
    index["count"] = success

    # Save index
    index_file = OUTPUT_DIR / "index.json"
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2)

    # Save log
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write(f"Batch Parse Log - {datetime.now().isoformat()}\n")
        f.write(f"Total: {total}, Success: {success}, Failed: {failed}\n")
        f.write("=" * 60 + "\n")
        f.write("\n".join(log_lines))

    print()
    print("=" * 60)
    print(f"COMPLETE: {success}/{total} palettes parsed")
    print(f"Failed: {failed}")
    print(f"Index: {index_file}")
    print(f"Log: {LOG_FILE}")

if __name__ == "__main__":
    main()

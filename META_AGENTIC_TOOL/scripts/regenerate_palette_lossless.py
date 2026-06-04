"""
Regenerate ALL palette_lossless files using the correct unified_system parser.

This script:
1. Finds all .tox files in TD's Palette directory
2. For each: toeexpand -> parse with LosslessParser -> save as .json.gz
3. Generates a new index.json with metadata
4. Reports progress and any errors

Usage:
    python regenerate_palette_lossless.py [--dry-run] [--single NAME]

Options:
    --dry-run       List files without processing
    --single NAME   Process only one palette by name (for testing)
    --parallel N    Number of parallel workers (default: 4)
    --clean         Remove temp directories after processing
"""

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add unified_system to path for imports
UNIFIED_SYSTEM_PATH = Path("C:/TD_Projects/unified_system")
sys.path.insert(0, str(UNIFIED_SYSTEM_PATH))

from parsers.lossless_parser import LosslessParser, parse_toe_lossless
from core.models import TDNetwork

# Configuration
PALETTE_SOURCE = Path("C:/Program Files/Derivative/TouchDesigner/Samples/Palette")
OUTPUT_DIR = Path("C:/TD_Projects/META_AGENTIC_TOOL/data/palette_lossless")
TOEEXPAND_PATH = Path("C:/Program Files/Derivative/TouchDesigner/bin/toeexpand.exe")
TEMP_BASE = Path(tempfile.gettempdir()) / "palette_regeneration"


@dataclass
class ProcessResult:
    """Result of processing a single palette."""
    name: str
    category: str
    source_path: str
    success: bool
    error_message: Optional[str] = None
    operator_count: int = 0
    file_count: int = 0
    output_size: int = 0
    processing_time: float = 0.0


def find_all_tox_files(palette_dir: Path) -> List[Path]:
    """Recursively find all .tox files in the palette directory."""
    tox_files = []
    for root, dirs, files in os.walk(palette_dir):
        for file in files:
            if file.endswith('.tox'):
                tox_files.append(Path(root) / file)
    return sorted(tox_files)


def get_category_from_path(tox_path: Path, palette_dir: Path) -> str:
    """Extract category (subfolder) from tox path."""
    try:
        relative = tox_path.relative_to(palette_dir)
        parts = relative.parts
        if len(parts) > 1:
            # Category is the first subfolder
            return parts[0]
        return "Root"
    except ValueError:
        return "Unknown"


def expand_tox(tox_path: Path, output_dir: Path) -> Optional[Path]:
    """
    Expand a .tox file using toeexpand.

    Returns path to .tox.dir or None on failure.
    """
    if not TOEEXPAND_PATH.exists():
        raise FileNotFoundError(f"toeexpand not found at {TOEEXPAND_PATH}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy tox to temp dir (toeexpand works in place)
    temp_tox = output_dir / tox_path.name
    shutil.copy2(tox_path, temp_tox)

    # Run toeexpand
    try:
        result = subprocess.run(
            [str(TOEEXPAND_PATH), str(temp_tox)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(output_dir)
        )

        if result.returncode != 0:
            return None

    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None

    # Find the .dir folder
    expected_dir = temp_tox.with_suffix('.tox.dir')
    if expected_dir.exists():
        return expected_dir

    # Fallback: search for any .dir
    for item in output_dir.iterdir():
        if item.is_dir() and item.suffix == '.dir':
            return item

    return None


def network_to_serializable(network: TDNetwork) -> Dict[str, Any]:
    """
    Convert TDNetwork to JSON-serializable dict.

    Uses the NEW format structure that unified_system expects:
    - operators as list (not dict)
    - lossless_data contains raw_files, toc_order, etc.
    """
    def convert_value(obj: Any) -> Any:
        """Recursively convert objects to JSON-serializable types."""
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, (list, tuple)):
            return [convert_value(item) for item in obj]
        if isinstance(obj, dict):
            return {str(k): convert_value(v) for k, v in obj.items()}
        if hasattr(obj, '__dict__'):
            # Dataclass or similar object
            result = {}
            for key, value in obj.__dict__.items():
                if not key.startswith('_'):
                    result[key] = convert_value(value)
            return result
        if hasattr(obj, 'value'):
            # Enum
            return obj.value
        return str(obj)

    return convert_value(network)


def process_single_palette(
    tox_path: Path,
    palette_dir: Path,
    output_dir: Path,
    temp_dir: Path,
    verbose: bool = False
) -> ProcessResult:
    """
    Process a single palette file.

    Steps:
    1. Create temp directory for this palette
    2. Expand .tox with toeexpand
    3. Parse with LosslessParser
    4. Save as compressed .json.gz
    5. Cleanup temp files
    """
    import time
    start_time = time.time()

    name = tox_path.stem
    category = get_category_from_path(tox_path, palette_dir)

    # Create unique temp dir for this palette
    palette_temp = temp_dir / f"{category}_{name}"
    palette_temp.mkdir(parents=True, exist_ok=True)

    result = ProcessResult(
        name=name,
        category=category,
        source_path=str(tox_path.relative_to(palette_dir)),
        success=False
    )

    try:
        # Step 1: Expand .tox
        if verbose:
            print(f"  Expanding {name}...")

        expanded_dir = expand_tox(tox_path, palette_temp)
        if not expanded_dir:
            result.error_message = "toeexpand failed"
            return result

        # Step 2: Parse with LosslessParser
        if verbose:
            print(f"  Parsing {name}...")

        parser = LosslessParser(expanded_dir)
        network = parser.parse(verbose=False)

        # Step 3: Convert to serializable dict
        network_dict = network_to_serializable(network)

        # Step 4: Save as compressed JSON
        output_file = output_dir / f"{name}.json.gz"
        with gzip.open(output_file, 'wt', encoding='utf-8') as f:
            json.dump(network_dict, f, indent=None, separators=(',', ':'))

        # Collect stats
        result.success = True
        result.operator_count = len(network.operators) if network.operators else 0
        result.file_count = len(network.lossless_data.raw_files) if network.lossless_data else 0
        result.output_size = output_file.stat().st_size

    except Exception as e:
        result.error_message = f"{type(e).__name__}: {str(e)}"
        if verbose:
            traceback.print_exc()

    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(palette_temp, ignore_errors=True)
        except Exception:
            pass

        result.processing_time = time.time() - start_time

    return result


def generate_index(results: List[ProcessResult], output_dir: Path) -> Dict[str, Any]:
    """Generate index.json from processing results."""
    palettes = {}

    for result in results:
        if result.success:
            palettes[result.name] = {
                "category": result.category,
                "file": f"{result.name}.json.gz",
                "size_bytes": result.output_size,
                "operator_count": result.operator_count,
                "file_count": result.file_count,
                "source": result.source_path
            }

    index = {
        "version": "2.0",
        "format": "unified_lossless",
        "generated": datetime.now().isoformat(),
        "count": len(palettes),
        "parser": "unified_system/parsers/lossless_parser.py",
        "palettes": palettes
    }

    # Write index
    index_path = output_dir / "index.json"
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2)

    return index


def main():
    parser = argparse.ArgumentParser(
        description="Regenerate all palette_lossless files using unified_system parser"
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='List files without processing')
    parser.add_argument('--single', type=str, metavar='NAME',
                        help='Process only one palette by name')
    parser.add_argument('--parallel', type=int, default=1,
                        help='Number of parallel workers (default: 1 - sequential)')
    parser.add_argument('--clean', action='store_true',
                        help='Remove temp directories after processing')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    parser.add_argument('--keep-old', action='store_true',
                        help='Keep old .json.gz files (default: remove before processing)')

    args = parser.parse_args()

    print("=" * 70)
    print("Palette Lossless Regeneration Script")
    print("=" * 70)
    print(f"Source:  {PALETTE_SOURCE}")
    print(f"Output:  {OUTPUT_DIR}")
    print(f"Parser:  {UNIFIED_SYSTEM_PATH / 'parsers/lossless_parser.py'}")
    print()

    # Validate paths
    if not PALETTE_SOURCE.exists():
        print(f"ERROR: Palette source not found: {PALETTE_SOURCE}")
        sys.exit(1)

    if not TOEEXPAND_PATH.exists():
        print(f"ERROR: toeexpand not found: {TOEEXPAND_PATH}")
        sys.exit(1)

    # Find all .tox files
    tox_files = find_all_tox_files(PALETTE_SOURCE)
    print(f"Found {len(tox_files)} .tox files")

    # Filter if single mode
    if args.single:
        tox_files = [f for f in tox_files if f.stem.lower() == args.single.lower()]
        if not tox_files:
            print(f"ERROR: No palette found with name '{args.single}'")
            sys.exit(1)
        print(f"Processing single palette: {args.single}")

    # Dry run - just list files
    if args.dry_run:
        print("\nDry run - files that would be processed:")
        categories = {}
        for tox in tox_files:
            cat = get_category_from_path(tox, PALETTE_SOURCE)
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(tox.stem)

        for cat in sorted(categories.keys()):
            print(f"\n{cat} ({len(categories[cat])}):")
            for name in sorted(categories[cat]):
                print(f"  - {name}")
        return

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Optionally clean old files
    if not args.keep_old and not args.single:
        print("\nRemoving old .json.gz files...")
        old_files = list(OUTPUT_DIR.glob("*.json.gz"))
        for f in old_files:
            f.unlink()
        print(f"  Removed {len(old_files)} files")

    # Create temp directory
    TEMP_BASE.mkdir(parents=True, exist_ok=True)

    # Process palettes
    print(f"\nProcessing {len(tox_files)} palettes...")
    results: List[ProcessResult] = []

    if args.parallel > 1:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(
                    process_single_palette,
                    tox, PALETTE_SOURCE, OUTPUT_DIR, TEMP_BASE, args.verbose
                ): tox for tox in tox_files
            }

            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                results.append(result)

                status = "OK" if result.success else "FAIL"
                print(f"[{i}/{len(tox_files)}] {status}: {result.name} ({result.category})")
                if not result.success and result.error_message:
                    print(f"         Error: {result.error_message}")
    else:
        # Sequential processing (safer, easier to debug)
        for i, tox in enumerate(tox_files, 1):
            result = process_single_palette(
                tox, PALETTE_SOURCE, OUTPUT_DIR, TEMP_BASE, args.verbose
            )
            results.append(result)

            status = "OK" if result.success else "FAIL"
            ops = f"({result.operator_count} ops)" if result.success else ""
            print(f"[{i}/{len(tox_files)}] {status}: {result.name} {ops}")
            if not result.success and result.error_message:
                print(f"         Error: {result.error_message}")

    # Generate index
    print("\nGenerating index.json...")
    index = generate_index(results, OUTPUT_DIR)

    # Summary
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total processed: {len(results)}")
    print(f"Successful:      {len(successful)}")
    print(f"Failed:          {len(failed)}")

    if successful:
        total_ops = sum(r.operator_count for r in successful)
        total_size = sum(r.output_size for r in successful)
        total_time = sum(r.processing_time for r in successful)
        print(f"\nTotal operators: {total_ops:,}")
        print(f"Total output:    {total_size / (1024*1024):.1f} MB")
        print(f"Total time:      {total_time:.1f} seconds")

    if failed:
        print("\nFailed palettes:")
        for r in failed:
            print(f"  - {r.name}: {r.error_message}")

    # Cleanup temp directory
    if args.clean:
        print("\nCleaning up temp directory...")
        shutil.rmtree(TEMP_BASE, ignore_errors=True)

    print(f"\nOutput written to: {OUTPUT_DIR}")
    print("Done!")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
td-convert: Convert TouchDesigner network JSON between format layers

Command-line tool for converting TD network JSON files between different
format layers (builder, extended, canonical).

Usage:
    td-convert network.json --from builder --to canonical
    td-convert network.json --from builder --to canonical --output out.json
    td-convert network.json --from canonical --to builder --pretty
"""

import sys
import argparse
import json
from pathlib import Path

# Add unified_system to path
UNIFIED_SYSTEM_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(UNIFIED_SYSTEM_ROOT))

from core.operator_registry import OperatorRegistry
from core.format_converter import FormatConverter


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Convert TouchDesigner network JSON between format layers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  td-convert network.json --from builder --to canonical
  td-convert network.json --from builder --to extended -o output.json
  td-convert network.json --from canonical --to builder --pretty
  td-convert network.json -f builder -t canonical

Format Layers:
  builder    - AI-friendly, simple paths, minimal structure
  extended   - Ground truth, complete operator data with defaults
  canonical  - Compact, string-table compression

Exit codes:
  0 - Conversion successful
  2 - Command error (file not found, invalid JSON, conversion failed, etc.)
        """
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input JSON file to convert"
    )

    parser.add_argument(
        "--from", "-f",
        dest="source_layer",
        choices=["builder", "extended", "canonical"],
        required=True,
        help="Source format layer"
    )

    parser.add_argument(
        "--to", "-t",
        dest="target_layer",
        choices=["builder", "extended", "canonical"],
        required=True,
        help="Target format layer"
    )

    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="Output file path (default: print to stdout)"
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output with indentation"
    )

    args = parser.parse_args()

    # Check if source and target are the same
    if args.source_layer == args.target_layer:
        print(f"Warning: Source and target layers are the same ({args.source_layer})", file=sys.stderr)
        print("No conversion needed. Outputting input as-is.", file=sys.stderr)

    # Check input file exists
    if not args.input.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        return 2

    # Load JSON
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            input_json = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error: Failed to read file: {e}", file=sys.stderr)
        return 2

    # Initialize converter
    try:
        registry = OperatorRegistry()
        converter = FormatConverter(registry)
    except Exception as e:
        print(f"Error: Failed to initialize converter: {e}", file=sys.stderr)
        return 2

    # Convert
    try:
        # If source == target, just pass through
        if args.source_layer == args.target_layer:
            output_json = input_json
        else:
            # Convert to TDNetwork (via Extended as hub)
            if args.source_layer == "builder":
                network = converter.from_builder(input_json)
            elif args.source_layer == "canonical":
                network = converter.from_canonical(input_json)
            else:  # extended
                # TODO: Implement proper Extended JSON deserialization
                # For now, assume builder format
                network = converter.from_builder(input_json)

            # Convert to target format
            if args.target_layer == "builder":
                output_json = converter.to_builder(network)
            elif args.target_layer == "canonical":
                output_json = converter.to_canonical(network)
            else:  # extended
                output_json = converter.to_extended(network)

    except Exception as e:
        print(f"Error: Conversion failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 2

    # Format JSON
    indent = 2 if args.pretty else None

    # Output
    try:
        if args.output:
            # Write to file
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(output_json, f, indent=indent)
            print(f"Converted {args.source_layer} -> {args.target_layer}: {args.output}", file=sys.stderr)
        else:
            # Print to stdout
            print(json.dumps(output_json, indent=indent))

    except Exception as e:
        print(f"Error: Failed to write output: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())

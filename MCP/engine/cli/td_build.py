#!/usr/bin/env python3
"""
td_build: Build TouchDesigner .toe/.tox files from network JSON

Command-line tool for building TouchDesigner project files (.toe) or
component files (.tox) from network JSON.

Usage (run directly — no console command is installed):
    python "Tools/offline Builder tools/td_build.py" network.json --output project.toe
    python "Tools/offline Builder tools/td_build.py" network.json -o component.tox --mode tox
    python "Tools/offline Builder tools/td_build.py" network.json -o project.toe --format builder --verbose
"""

import sys
import argparse
import json
from pathlib import Path

# Add unified_system to path
UNIFIED_SYSTEM_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(UNIFIED_SYSTEM_ROOT))

from api.network_builder import NetworkBuilder
from core.operator_registry import OperatorRegistry
from core.format_converter import FormatConverter
from builders.toe_builder import TOEBuilder
from core.lossless_json import from_lossless_json_dict


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build TouchDesigner .toe/.tox files from network JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  td_build.py network.json --output project.toe
  td_build.py network.json -o component.tox --mode tox
  td_build.py network.json -o project.toe --format builder --verbose
  td_build.py network.json -o project.toe -v

Output:
  Creates .toe.dir/ directory with all operator files
  Creates .toe.toc table of contents file
  Run 'toecollapse <file>.toc' to create final .toe file

Exit codes:
  0 - Build successful
  1 - Network validation failed
  2 - Command error (file not found, invalid JSON, build failed, etc.)
        """
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input JSON file to build from"
    )

    parser.add_argument(
        "--output", "-o",
        type=Path,
        required=True,
        help="Output .toe or .tox file path"
    )

    parser.add_argument(
        "--format", "-f",
        choices=["builder", "canonical", "lossless"],
        default="builder",
        help="Input format layer (default: builder; 'extended' is internal-only, not implemented as a JSON layer)"
    )

    parser.add_argument(
        "--mode", "-m",
        choices=["toe", "tox"],
        help="Build mode: toe (project) or tox (component). If not specified, inferred from output extension"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed build progress"
    )

    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip validation before building (not recommended)"
    )

    args = parser.parse_args()

    # Infer mode from output extension if not specified
    if args.mode is None:
        if args.output.suffix == ".tox":
            args.mode = "tox"
        else:
            args.mode = "toe"

    # Check input file exists
    if not args.input.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        return 2

    # Load JSON
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            network_json = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error: Failed to read file: {e}", file=sys.stderr)
        return 2

    # Initialize components
    registry = None
    converter = None
    if args.format != "lossless":
        try:
            registry = OperatorRegistry()
            converter = FormatConverter(registry)
        except Exception as e:
            print(f"Error: Failed to initialize builder: {e}", file=sys.stderr)
            return 2

    # Lossless build: JSON already contains the expanded-file representation
    if args.format == "lossless":
        try:
            network = from_lossless_json_dict(network_json)
            builder = TOEBuilder(network, verbose=args.verbose)
            toc_file = builder.build(args.output, mode=args.mode)
            print(f"Success! Created:")
            print(f"  {toc_file}")
            print(f"  {toc_file.name.replace('.toc', '.dir')}/")
            return 0
        except Exception as e:
            print(f"Error: Lossless build failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return 2

    # Build network using NetworkBuilder
    try:
        meta = network_json.get("meta", {})
        project_name = meta.get("project_name", "network")

        if args.verbose:
            print(f"Building network: {project_name}")
            print(f"Mode: {args.mode}")
            print()

        builder = NetworkBuilder(project_name, mode=args.mode)

        # Add operators
        nodes = network_json.get("nodes", [])
        for node in nodes:
            path = node.get("path", "")
            name = path.split("/")[-1] if path else node.get("name", "")
            family = node.get("family", "")
            op_type = node.get("type", "")

            if not name or not family or not op_type:
                continue

            # Determine parent
            parent = node.get("parent", None)  # Check explicit parent field first
            if "/" in path:
                parent = "/".join(path.split("/")[:-1])

            builder.add_operator(name, family, op_type, parent=parent)

            # Set parameters
            params = node.get("parameters", node.get("params", {}))
            for param_name, param_value in params.items():
                try:
                    builder.set_parameter(name, param_name, param_value)
                except Exception as e:
                    if args.verbose:
                        print(f"Warning: Failed to set parameter {name}.{param_name}: {e}", file=sys.stderr)

        # Add connections
        connections = network_json.get("connections", [])
        for conn in connections:
            from_name = conn.get("from", "")
            to_name = conn.get("to", "")
            to_input = conn.get("to_input", 0)

            if from_name and to_name:
                try:
                    builder.connect(from_name, to_name, target_input=to_input)
                except Exception as e:
                    if args.verbose:
                        print(f"Warning: Failed to connect {from_name} -> {to_name}: {e}", file=sys.stderr)

        if args.verbose:
            print(f"Added {len(builder)} operators")
            print(f"Added {len(builder.connections)} connections")
            print()

    except Exception as e:
        print(f"Error: Failed to build network: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 2

    # Validate
    if not args.no_validate:
        if args.verbose:
            print("Validating network...")

        if not builder.is_valid():
            report = builder.validate()
            print("Error: Network validation failed", file=sys.stderr)
            print(f"Errors: {report.total_errors}", file=sys.stderr)
            print(f"Warnings: {report.total_warnings}", file=sys.stderr)
            print()

            # Show first 10 errors
            for error in report.get_errors()[:10]:
                print(f"  - [{error.stage}] {error.message}", file=sys.stderr)

            if report.total_errors > 10:
                print(f"  ... and {report.total_errors - 10} more errors", file=sys.stderr)

            return 1

        if args.verbose:
            print("Validation passed")
            print()

    # Build
    try:
        if args.verbose:
            print(f"Building {args.mode} file...")

        if args.mode == "toe":
            toc_file = builder.build_toe(args.output, verbose=args.verbose)
        else:
            toc_file = builder.build_tox(args.output, verbose=args.verbose)

        print(f"Success! Created:")
        print(f"  {toc_file}")
        print(f"  {toc_file.name.replace('.toc', '.dir')}/")
        print()
        print("To collapse into final .toe file, run:")
        print(f"  toecollapse {toc_file}")

    except Exception as e:
        print(f"Error: Build failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
td_validate: Validate TouchDesigner network JSON

Command-line tool for validating TD network JSON files using the
5-stage validation pipeline.

Usage (run directly — no console command is installed):
    python "Tools/offline Builder tools/td_validate.py" network.json
    python "Tools/offline Builder tools/td_validate.py" network.json --verbose
    python "Tools/offline Builder tools/td_validate.py" network.json --format builder
"""

import sys
import argparse
import json
from pathlib import Path

# Add unified_system to path
UNIFIED_SYSTEM_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(UNIFIED_SYSTEM_ROOT))

from api.validate import build_validation_stack


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate TouchDesigner network JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  td_validate.py network.json
  td_validate.py network.json --verbose
  td_validate.py network.json --format builder
  td_validate.py network.json -v --no-color

Exit codes:
  0 - Network is valid
  1 - Network has errors
  2 - Command error (file not found, invalid JSON, etc.)
        """
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input JSON file to validate"
    )

    parser.add_argument(
        "--format", "-f",
        choices=["builder", "canonical"],
        default="builder",
        help="Input format layer (default: builder; 'extended' is internal-only, not implemented as a JSON layer)"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed validation stages"
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output validation report as JSON"
    )

    args = parser.parse_args()

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
    try:
        registry, converter, validator = build_validation_stack()
    except Exception as e:
        print(f"Error: Failed to initialize validator: {e}", file=sys.stderr)
        return 2

    # Convert to TDNetwork
    try:
        if args.format == "builder":
            network = converter.from_builder(network_json)
        else:  # canonical
            network = converter.from_canonical(network_json)
    except Exception as e:
        print(f"Error: Failed to convert network: {e}", file=sys.stderr)
        return 2

    # Validate
    try:
        project_name = network_json.get("meta", {}).get("project_name", "network")
        report = validator.validate(network, project_name)
    except Exception as e:
        print(f"Error: Validation failed: {e}", file=sys.stderr)
        return 2

    # Output results
    if args.json:
        # JSON output
        result = {
            "valid": report.valid,
            "total_errors": report.total_errors,
            "total_warnings": report.total_warnings,
            "errors": [
                {
                    "stage": e.stage,
                    "message": e.message,
                    "severity": e.severity
                }
                for e in report.get_errors()
            ],
            "warnings": [
                {
                    "stage": w.stage,
                    "message": w.message,
                    "severity": w.severity
                }
                for w in report.get_warnings()
            ]
        }

        if args.verbose:
            result["stages"] = {
                stage.stage: {
                    "status": stage.status,
                    "errors": len(stage.errors),
                    "warnings": len(stage.warnings)
                }
                for stage in report.stages
            }

        print(json.dumps(result, indent=2))
    else:
        # Human-readable output
        use_color = not args.no_color and sys.stdout.isatty()

        # Color codes
        if use_color:
            GREEN = '\033[92m'
            RED = '\033[91m'
            YELLOW = '\033[93m'
            BLUE = '\033[94m'
            BOLD = '\033[1m'
            RESET = '\033[0m'
        else:
            GREEN = RED = YELLOW = BLUE = BOLD = RESET = ''

        # Header
        print(f"\n{BOLD}TouchDesigner Network Validation{RESET}")
        print("=" * 70)
        print(f"File: {args.input}")
        print(f"Format: {args.format}")
        print()

        # Overall result
        if report.valid:
            print(f"{GREEN}{BOLD}[VALID]{RESET}")
        else:
            print(f"{RED}{BOLD}[INVALID]{RESET}")

        print()
        print(f"Errors: {report.total_errors}")
        print(f"Warnings: {report.total_warnings}")
        print(f"Operators: {len(network.operators)}")
        print(f"Connections: {len(network.connections)}")

        # Verbose: Stage details
        if args.verbose:
            print()
            print(f"{BOLD}Validation Stages:{RESET}")
            print("-" * 70)

            for stage in report.stages:
                stage_name = stage.stage.capitalize()
                if stage.status == "PASS":
                    print(f"  {GREEN}[OK]{RESET} {stage_name}")
                else:
                    print(f"  {RED}[FAIL]{RESET} {stage_name}")

        # Errors
        if report.total_errors > 0:
            print()
            print(f"{RED}{BOLD}Errors:{RESET}")
            print("-" * 70)
            for error in report.get_errors():
                print(f"  {RED}-{RESET} [{error.stage}] {error.message}")

        # Warnings
        if report.total_warnings > 0:
            print()
            print(f"{YELLOW}{BOLD}Warnings:{RESET}")
            print("-" * 70)
            for warning in report.get_warnings():
                print(f"  {YELLOW}-{RESET} [{warning.stage}] {warning.message}")

        print()

    # Exit code
    return 0 if report.valid else 1


if __name__ == "__main__":
    sys.exit(main())

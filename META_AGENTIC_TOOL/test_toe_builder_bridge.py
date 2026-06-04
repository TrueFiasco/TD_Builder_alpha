"""
Test script for toe_builder_bridge.py

Tests the bridge with the Teardrop V2 TD Designer output.
"""

from pathlib import Path
import sys

# Add meta_agentic to path
sys.path.insert(0, str(Path(__file__).parent))

from meta_agentic.execution.toe_builder_bridge import build_toe_from_yaml

def main():
    print("=" * 60)
    print("Testing toe_builder_bridge.py with Teardrop V2")
    print("=" * 60)

    # Use absolute paths relative to this script
    script_dir = Path(__file__).parent
    yaml_path = script_dir / "test_output" / "teardrop_v2_subagent" / "04_td_designer.yaml"
    output_dir = script_dir / "test_output" / "toe_bridge_test"

    if not yaml_path.exists():
        print(f"[ERROR] YAML file not found: {yaml_path}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nInput:  {yaml_path}")
    print(f"Output: {output_dir}")

    result = build_toe_from_yaml(yaml_path, output_dir)

    if result and result.exists():
        print(f"\n[SUCCESS] TOE created: {result}")
        print(f"         Size: {result.stat().st_size} bytes")

        # List what was created
        dir_path = output_dir / f"{result.stem}.dir"
        if dir_path.exists():
            print(f"\nTOE.dir contents:")
            for f in sorted(dir_path.rglob("*")):
                if f.is_file():
                    rel = f.relative_to(dir_path)
                    print(f"  {rel}")
        return 0
    else:
        print("\n[FAILED] TOE not created")
        return 1


if __name__ == "__main__":
    sys.exit(main())

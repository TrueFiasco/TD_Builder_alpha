"""
Test Strategy Integration

Simulates what strategy_runner.py does after TD Designer completes:
1. Load network design into blackboard
2. Call toe_builder_bridge to generate TOE
3. Verify TOE was created

Uses existing Teardrop TD Designer output - no API calls needed.
"""

import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

import yaml
from meta_agentic.execution.blackboard import Blackboard, SectionID
from meta_agentic.execution.toe_builder_bridge import build_toe_from_design


def main():
    print("=" * 60)
    print("Testing Strategy Runner Integration")
    print("=" * 60)

    # 1. Load existing TD Designer output
    yaml_path = Path(__file__).parent / "test_output" / "teardrop_v2_subagent" / "04_td_designer.yaml"

    if not yaml_path.exists():
        print(f"[ERROR] TD Designer output not found: {yaml_path}")
        return 1

    print(f"\n[1/4] Loading TD Designer output: {yaml_path.name}")
    with open(yaml_path, 'r') as f:
        td_designer_output = yaml.safe_load(f)

    # 2. Create blackboard and write network design (simulating strategy runner)
    print("\n[2/4] Creating blackboard and writing network design...")
    blackboard = Blackboard(project_name="teardrop_integration_test")

    # Write to NETWORK_DESIGN section (what TD Designer does)
    blackboard.write(
        SectionID.NETWORK_DESIGN,
        td_designer_output,
        author="td_designer"
    )

    print(f"  Blackboard project: {blackboard.project_name}")
    print(f"  Network design written successfully")

    # 3. Call toe_builder_bridge (what strategy runner does after network_builder)
    print("\n[3/4] Building TOE from network design...")

    network_design = blackboard.read(SectionID.NETWORK_DESIGN)

    if not network_design:
        print("[ERROR] No network design in blackboard")
        return 1

    output_dir = Path(__file__).parent / "test_output" / blackboard.project_name
    output_dir.mkdir(parents=True, exist_ok=True)

    toe_path = build_toe_from_design(
        network_design,
        output_dir,
        project_name=blackboard.project_name
    )

    # 4. Verify and update blackboard (what strategy runner does)
    print("\n[4/4] Verifying and updating blackboard...")

    if toe_path and toe_path.exists():
        # Update BUILD_ARTIFACTS (what strategy runner does)
        build_artifacts = {
            "toe_path": str(toe_path),
            "toe_size_bytes": toe_path.stat().st_size,
            "build_status": "success"
        }
        blackboard.write(
            SectionID.BUILD_ARTIFACTS,
            build_artifacts,
            author="toe_builder"
        )

        print(f"\n" + "=" * 60)
        print("[SUCCESS] Integration test passed!")
        print("=" * 60)
        print(f"  TOE Path: {toe_path}")
        print(f"  TOE Size: {toe_path.stat().st_size} bytes")
        print(f"  Build Artifacts written successfully")

        # Show blackboard summary
        artifacts = blackboard.read(SectionID.BUILD_ARTIFACTS)
        print(f"\n  BUILD_ARTIFACTS content:")
        for key, value in artifacts.items():
            print(f"    {key}: {value}")

        return 0
    else:
        print("\n[FAILED] TOE file was not created")
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Basic network examples using NetworkBuilder API.

Demonstrates common patterns for building TouchDesigner networks.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.network_builder import NetworkBuilder, quick_network


def example_simple_noise():
    """Example 1: Simple noise generator."""
    print("Example 1: Simple Noise Generator")
    print("=" * 70)

    # Create network
    builder = NetworkBuilder("simple_noise", mode="toe")

    # Add operators
    builder.add_operator("noise1", "CHOP", "noise")
    builder.add_operator("null1", "CHOP", "null")

    # Connect
    builder.connect("noise1", "null1")

    # Set parameters
    builder.set_parameter("noise1", "amp", 0.5)

    # Validate
    report = builder.validate()
    print(f"Valid: {report.valid}")
    print(f"Operators: {len(builder)}")
    print(f"Connections: {len(builder.connections)}")

    return builder


def example_audio_reactive():
    """Example 2: Audio reactive visualization."""
    print("\nExample 2: Audio Reactive Visualization")
    print("=" * 70)

    builder = quick_network("audio_reactive")

    # Audio input chain
    builder.add_operator("audioin", "CHOP", "audiofilein")
    builder.add_operator("beat", "CHOP", "beat")
    builder.add_operator("lag", "CHOP", "lag")

    # Visual generation
    builder.add_operator("noise1", "TOP", "noise")
    builder.add_operator("level1", "TOP", "level")
    builder.add_operator("render", "TOP", "render")

    # Connect audio chain
    builder.connect("audioin", "beat")
    builder.connect("beat", "lag")

    # Connect visual chain
    builder.connect("noise1", "level1")
    builder.connect("level1", "render")

    # Set parameters with expressions
    builder.set_parameter("audioin", "file", "audio.wav")
    builder.set_expression("noise1", "amp", "op('lag')['beat']", "python")

    # Auto-layout
    builder.auto_layout(spacing=150)

    # Validate
    report = builder.validate()
    print(f"Valid: {report.valid}")
    print(f"Operators: {len(builder)}")
    print(f"Connections: {len(builder.connections)}")

    if not report.valid:
        print("Errors:")
        for error in report.get_errors():
            print(f"  - {error.message}")

    return builder


def example_feedback_loop():
    """Example 3: Feedback loop (common TD pattern)."""
    print("\nExample 3: Feedback Loop")
    print("=" * 70)

    builder = NetworkBuilder("feedback_loop")

    # Create feedback loop
    builder.add_operator("noise1", "TOP", "noise")
    builder.add_operator("blur1", "TOP", "blur")
    builder.add_operator("feedback1", "TOP", "feedback")
    builder.add_operator("composite1", "TOP", "composite")
    builder.add_operator("render", "TOP", "render")

    # Connect
    builder.connect("noise1", "composite1")
    builder.connect("composite1", "blur1")
    builder.connect("blur1", "feedback1")
    builder.connect("feedback1", "composite1")  # Feedback!
    builder.connect("composite1", "render")

    # Parameters
    builder.set_parameter("blur1", "size", 3.0)
    builder.set_parameter("feedback1", "top", "feedback1")

    # Validate
    report = builder.validate()
    print(f"Valid: {report.valid}")
    print(f"Operators: {len(builder)}")
    print(f"Connections: {len(builder.connections)}")

    return builder


def example_comp_hierarchy():
    """Example 4: Component hierarchy."""
    print("\nExample 4: Component Hierarchy")
    print("=" * 70)

    builder = NetworkBuilder("comp_hierarchy")

    # Create base container
    builder.add_operator("base", "COMP", "container", parent="/project1")

    # Add operators inside base
    builder.add_operator("noise1", "CHOP", "noise", parent="/project1/base")
    builder.add_operator("null1", "CHOP", "null", parent="/project1/base")

    # Connect inside base
    builder.connect("noise1", "null1")

    # Validate
    report = builder.validate()
    print(f"Valid: {report.valid}")
    print(f"Operators: {len(builder)}")

    # List operators
    print("\nOperators:")
    for op in builder.list_operators():
        print(f"  {op.path} ({op.op_type})")

    return builder


def example_method_chaining():
    """Example 5: Method chaining."""
    print("\nExample 5: Method Chaining")
    print("=" * 70)

    # Build entire network with chained methods
    builder = (NetworkBuilder("chained_network")
               .add_operator("noise1", "CHOP", "noise")
               .add_operator("math1", "CHOP", "math")
               .add_operator("null1", "CHOP", "null")
               .connect("noise1", "math1")
               .connect("math1", "null1")
               .set_parameter("noise1", "amp", 1.0)
               .set_parameter("math1", "gain", 2.0)
               .auto_layout())

    print(f"Built network: {builder}")
    print(f"Valid: {builder.is_valid()}")

    return builder


def example_save_json():
    """Example 6: Save to JSON."""
    print("\nExample 6: Save to JSON")
    print("=" * 70)

    builder = (quick_network("saved_network")
               .add_operator("noise1", "CHOP", "noise")
               .add_operator("null1", "CHOP", "null")
               .connect("noise1", "null1"))

    # Save in different formats
    output_dir = Path(__file__).parent.parent / "examples" / "output"
    output_dir.mkdir(exist_ok=True)

    # Extended format
    builder.save_json(output_dir / "network_extended.json", layer="extended")
    print("Saved: network_extended.json")

    # Builder format
    builder.save_json(output_dir / "network_builder.json", layer="builder")
    print("Saved: network_builder.json")

    # Canonical format
    builder.save_json(output_dir / "network_canonical.json", layer="canonical")
    print("Saved: network_canonical.json")

    return builder


def example_build_toe():
    """Example 7: Build .toe file."""
    print("\nExample 7: Build .toe File")
    print("=" * 70)

    builder = (quick_network("build_example")
               .add_operator("noise1", "CHOP", "noise")
               .add_operator("math1", "CHOP", "math")
               .add_operator("null1", "CHOP", "null")
               .connect("noise1", "math1")
               .connect("math1", "null1")
               .set_parameter("noise1", "amp", 1.0)
               .set_parameter("math1", "gain", 2.0)
               .auto_layout())

    # Validate
    if not builder.is_valid():
        print("ERROR: Network is not valid!")
        return None

    # Build .toe file
    output_dir = Path(__file__).parent.parent / "examples" / "output"
    output_dir.mkdir(exist_ok=True)

    toe_path = output_dir / "example_network.toe"

    # Build (creates .toe.dir and .toe.toc)
    toc_file = builder.build_toe(toe_path, verbose=False)

    print(f"Built: {toc_file}")
    print(f"Directory: {toc_file.name.replace('.toc', '.dir')}/")
    print()
    print("To collapse into .toe file, run:")
    print(f"  toecollapse {toc_file}")

    return builder


if __name__ == "__main__":
    print("NetworkBuilder API Examples")
    print("=" * 70)
    print()

    # Run all examples
    example_simple_noise()
    example_audio_reactive()
    example_feedback_loop()
    example_comp_hierarchy()
    example_method_chaining()
    example_save_json()
    example_build_toe()

    print("\n" + "=" * 70)
    print("All examples completed!")

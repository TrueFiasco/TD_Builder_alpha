"""
Example: Using the Critic Integration for scoring workflow sections.

This example demonstrates how to use CriticIntegration to:
1. Critique creative vision
2. Critique technical approach
3. Critique network design
4. Parse critique results
5. Handle pass/fail scenarios
"""

from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from meta_agentic.execution import (
    Blackboard,
    SectionID,
    MetricsCollector,
    CriticIntegration,
)


def example_critique_creative_vision():
    """Example: Critique creative vision section."""
    print("=" * 60)
    print("Example 1: Critiquing Creative Vision")
    print("=" * 60)

    # Setup
    blackboard = Blackboard(project_name="example_project")
    metrics = MetricsCollector(strategy="v6", project="example")

    # Write some creative vision content
    creative_content = {
        "mood": {
            "primary": "ethereal",
            "modifier": "contemplative"
        },
        "color_palette": {
            "primary": ["#1a1a2e", "#16213e", "#0f3460"],
            "accent": ["#e94560"],
            "saturation": "low"
        },
        "aesthetic": "minimal",
        "core_concept": "Floating particles that respond to audio frequencies"
    }

    blackboard.write(
        SectionID.CREATIVE_VISION,
        creative_content,
        author="creative_expert"
    )

    # Create critic integration
    critic = CriticIntegration(blackboard, metrics)

    # Critique the creative vision
    result = critic.critique_creative_vision(threshold=0.85)

    # Display results
    print(f"\nSection: {result.section_id.value}")
    print(f"Score: {result.score:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Timestamp: {result.timestamp}")

    if result.criteria_scores:
        print("\nCriteria Scores:")
        for criterion, score in result.criteria_scores.items():
            print(f"  - {criterion}: {score:.2f}")

    print(f"\nFeedback: {result.feedback}")

    if result.issues:
        print("\nIssues Found:")
        for issue in result.issues:
            print(f"  - {issue}")

    if result.suggestions:
        print("\nSuggestions:")
        for suggestion in result.suggestions:
            print(f"  - {suggestion}")

    if result.blocking_issues:
        print("\nBlocking Issues:")
        for blocking in result.blocking_issues:
            print(f"  - {blocking}")

    print()


def example_critique_technical_approach():
    """Example: Critique technical approach section."""
    print("=" * 60)
    print("Example 2: Critiquing Technical Approach")
    print("=" * 60)

    # Setup
    blackboard = Blackboard(project_name="example_project")
    metrics = MetricsCollector(strategy="v6", project="example")

    # Write technical approach content
    technical_content = {
        "primary_technique": {
            "name": "GPU Particle System",
            "algorithm": "compute_shader_particles",
            "implementation": "Compute Shader with feedback"
        },
        "data_flow": {
            "input": "Audio analysis (FFT)",
            "processing": "Particle behavior computation",
            "output": "Rendered particle field"
        },
        "performance_targets": {
            "particle_count": "100K",
            "frame_rate": "60fps",
            "resolution": "1920x1080"
        }
    }

    blackboard.write(
        SectionID.TECHNICAL_APPROACH,
        technical_content,
        author="cg_expert"
    )

    # Create critic integration
    critic = CriticIntegration(blackboard, metrics)

    # Critique the technical approach
    result = critic.critique_technical_approach(threshold=0.85)

    # Display results
    print(f"\nSection: {result.section_id.value}")
    print(f"Score: {result.score:.2f}")
    print(f"Passed: {result.passed}")
    print(f"Has Blocking Issues: {result.has_blocking_issues}")

    print(f"\nFeedback: {result.feedback}")
    print()


def example_parse_critique_response():
    """Example: Parse a mock critique response."""
    print("=" * 60)
    print("Example 3: Parsing Critique Response")
    print("=" * 60)

    # Setup
    blackboard = Blackboard(project_name="example_project")
    metrics = MetricsCollector(strategy="v6", project="example")
    critic = CriticIntegration(blackboard, metrics)

    # Mock critique response
    mock_response = """
    Overall Score: 0.87

    Criteria Scores:
    - artistic_coherence: 0.90
    - technical_feasibility: 0.85
    - implementation_clarity: 0.88
    - creative_alignment: 0.86

    Feedback: The creative vision demonstrates strong coherence between mood,
    color palette, and aesthetic choices. The ethereal/contemplative mood is
    well-supported by the low saturation cool color palette.

    Issues Requiring Attention:
    - [medium] Motion quality not specified - should align with contemplative mood
    - [low] Animation timing could be more explicitly defined

    Suggestions:
    - Consider specifying slow, organic motion to match contemplative mood
    - Add timing parameters (ease curves, duration ranges)
    - Define interaction response behavior if applicable

    Blocking Issues:
    None
    """

    # Parse the response
    result = critic.parse_critique_response(
        response=mock_response,
        section_id=SectionID.CREATIVE_VISION,
        threshold=0.85
    )

    # Display parsed results
    print(f"\nParsed Score: {result.score:.2f}")
    print(f"Passed Threshold: {result.passed}")

    print("\nParsed Criteria Scores:")
    for criterion, score in result.criteria_scores.items():
        print(f"  - {criterion}: {score:.2f}")

    print(f"\nParsed Feedback:\n{result.feedback}")

    print(f"\nParsed Issues ({len(result.issues)}):")
    for issue in result.issues:
        print(f"  - {issue}")

    print(f"\nParsed Suggestions ({len(result.suggestions)}):")
    for suggestion in result.suggestions:
        print(f"  - {suggestion}")

    print(f"\nBlocking Issues: {len(result.blocking_issues)}")
    print()


def example_quality_thresholds():
    """Example: Get quality thresholds for different presets."""
    print("=" * 60)
    print("Example 4: Quality Thresholds by Preset")
    print("=" * 60)

    # Setup
    blackboard = Blackboard(project_name="example_project")
    metrics = MetricsCollector(strategy="v6", project="example")
    critic = CriticIntegration(blackboard, metrics)

    # Get thresholds for different presets
    presets = ["quick_draft", "standard", "excellence"]

    for preset in presets:
        thresholds = critic.get_quality_thresholds(preset)
        print(f"\n{preset.upper()} Preset:")
        print(f"  - Creative: {thresholds['creative']:.2f}")
        print(f"  - Technical: {thresholds['technical']:.2f}")
        print(f"  - Design: {thresholds['design']:.2f}")

    print()


def example_workflow_integration():
    """Example: Full workflow integration."""
    print("=" * 60)
    print("Example 5: Full Workflow Integration")
    print("=" * 60)

    # Setup
    blackboard = Blackboard(project_name="workflow_example")
    metrics = MetricsCollector(strategy="v6", project="workflow_example")
    critic = CriticIntegration(blackboard, metrics)

    # Get quality thresholds for standard preset
    thresholds = critic.get_quality_thresholds("standard")

    # Simulate workflow: Creative -> Technical -> Design
    print("\nPhase 1: Creative Vision")
    print("-" * 40)

    # Write creative content
    creative_content = {
        "mood": {"primary": "ethereal"},
        "aesthetic": "minimal"
    }
    blackboard.write(SectionID.CREATIVE_VISION, creative_content, "creative_expert")

    # Critique
    creative_result = critic.critique_creative_vision(thresholds["creative"])
    print(f"Score: {creative_result.score:.2f} (threshold: {thresholds['creative']})")
    print(f"Passed: {creative_result.passed}")

    if creative_result.passed:
        blackboard.lock(SectionID.CREATIVE_VISION, "Approved by critic")
        print("Section locked - proceeding to next phase")
    else:
        print("Revision required:")
        for issue in creative_result.issues:
            print(f"  - {issue}")

    print("\nPhase 2: Technical Approach")
    print("-" * 40)

    # Write technical content
    technical_content = {
        "primary_technique": "GPU Particles",
        "algorithm": "compute_shader"
    }
    blackboard.write(SectionID.TECHNICAL_APPROACH, technical_content, "cg_expert")

    # Critique
    technical_result = critic.critique_technical_approach(thresholds["technical"])
    print(f"Score: {technical_result.score:.2f} (threshold: {thresholds['technical']})")
    print(f"Passed: {technical_result.passed}")

    print("\nWorkflow Status:")
    print(f"  - Phase: {blackboard.current_phase.value}")
    print(f"  - Iteration: {blackboard.iteration}")
    print(f"  - Locked Sections: {sum(1 for s in blackboard.sections.values() if s.locked)}")

    print()


if __name__ == "__main__":
    example_critique_creative_vision()
    example_critique_technical_approach()
    example_parse_critique_response()
    example_quality_thresholds()
    example_workflow_integration()

    print("=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)

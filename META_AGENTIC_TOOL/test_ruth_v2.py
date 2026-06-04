"""
Test V2 Strategy with RUTH Spec

This script tests the V2 execution pipeline with the RUTH TouchDesigner specification.
It can run in mock mode (free) or real mode (uses Claude API, costs money).

Usage:
    # Mock mode (default, no API calls)
    python test_ruth_v2.py

    # Real mode (uses Claude API)
    python test_ruth_v2.py --real

    # Parallel mode (tests ParallelExecutor)
    python test_ruth_v2.py --parallel
"""

import argparse
import json
import logging
from pathlib import Path
from datetime import datetime

from meta_agentic.execution import (
    Blackboard, MetricsCollector, SectionID,
    ExpertExecutor, execute_expert, get_expert_executor,
    LLMExecutor, AnthropicExecutor, MockExecutor,
    KnowledgeBase, get_default_kb,
    ParallelExecutor, ParallelBuildConfig, RUTH_COMPONENTS
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_ruth_spec() -> str:
    """Load the RUTH spec from the known location."""
    spec_path = Path(r"C:\Users\jake_\Downloads\RUTH_TD_Spec_Final.md")

    if not spec_path.exists():
        raise FileNotFoundError(f"RUTH spec not found at {spec_path}")

    with open(spec_path, 'r', encoding='utf-8') as f:
        return f.read()


def create_mock_executor() -> MockExecutor:
    """Create a mock executor with realistic response templates."""

    # Response templates for different experts
    response_map = {
        "creative_expert": """```yaml
creative_spec:
  title: "Running Up That Hill - Visual System"
  mood: ethereal, confrontational, transcendent
  visual_language:
    warm_palette: ["#E8A87C", "#D4AF37", "#F5E6D3", "#FF6B35"]
    cold_palette: ["#1A0A0A", "#3D0C02", "#0D1B2A", "#8B0000"]
  key_elements:
    - kate_aura: "Golden ember particles, sacred geometry at high intensity"
    - tendrils: "Threatening organic growth, subsurface scattering"
    - membrane: "FFT-reactive portal between worlds"
    - demogorgon: "Flower-face creature with wound system"
  counter_breathing: "Kate contracts when bass swells - she resists the pulse"
  scene_arc:
    - INTRO: dreamy, isolated
    - VERSE: building tension
    - CHORUS: explosive confrontation
    - TRIUMPH: transcendence, healing
recommendation:
  action: proceed
  reason: "Creative vision established"
```""",

        "cg_expert": """```yaml
technical_approach:
  rendering_pipeline: "Deferred rendering with multiple render passes"
  performance_target: "60fps minimum at 4K"

techniques:
  particle_systems:
    - kate_embers: "GPU instanced particles with gravity-correct rising"
    - ash_spores: "Inverted gravity particles for UD environment"
  shaders:
    - membrane_displacement: "FFT-driven vertex displacement"
    - subsurface_tendrils: "SSS shader for organic look"
    - volumetric_haze: "Ray-marched fog with density control"
  audio_integration:
    - rms_bands: [20-80Hz, 250-2kHz, 4-16kHz]
    - onset_detection: "Kick and snare with retrigger lockout"
    - beat_sync: "Manual BPM override at 108"

performance_notes:
  - "Test BATTLE scene for maximum load"
  - "Consider LOD for tendril geometry"
  - "Batch particle systems where possible"

recommendation:
  action: proceed
  reason: "Technical approach validated"
```""",

        "td_designer": """```yaml
network_design:
  project: kate_bush_ruth
  tox_structure:
    - audio_analysis.tox:
        operators:
          - {name: audioDeviceIn1, type: audioDeviceIn, family: CHOP}
          - {name: audioFilter_low, type: audioFilter, family: CHOP, params: {lowpass: 80}}
          - {name: audioFilter_mid, type: audioFilter, family: CHOP, params: {bandpass: [250, 2000]}}
          - {name: audioFilter_high, type: audioFilter, family: CHOP, params: {highpass: 4000}}
          - {name: analyze_rms, type: analyze, family: CHOP}
          - {name: lag_envelope, type: lag, family: CHOP}
          - {name: beat1, type: beat, family: CHOP, params: {bpm: 108}}
        connections:
          - [audioDeviceIn1, audioFilter_low]
          - [audioFilter_low, analyze_rms]
          - [analyze_rms, lag_envelope]

    - kate_aura.tox:
        operators:
          - {name: circle_geo, type: sphere, family: SOP}
          - {name: particle1, type: particle, family: SOP}
          - {name: geo_aura, type: geometry, family: COMP}
          - {name: phong_warm, type: phongMAT, family: MAT}
        connections:
          - [circle_geo, geo_aura]
          - [particle1, geo_aura]

connections_summary:
  audio_to_visual: "CHOP exports drive all visual parameters"
  kate_aura_inputs: ["rmsLow (inverted)", "rmsMid", "beatPhase"]

recommendation:
  action: proceed
  reason: "Network design complete"
```""",

        "critic": """```yaml
score: 0.87
passed: true

feedback: "Strong creative foundation with clear visual language. Technical approach is sound."

issues:
  - "Kate counter-breathing could use more specific parameter mapping"
  - "Demogorgon wound system needs persistence mechanism"

suggestions:
  - "Add scene interpolation timing to network design"
  - "Consider fallback for missing audio stems"

criteria_scores:
  creative_coherence: 0.90
  technical_feasibility: 0.85
  td_compatibility: 0.88
  performance_viability: 0.82

blocking_issues: []
```"""
    }

    return MockExecutor(
        response_map=response_map,
        default_response="""```yaml
status: success
expert: unknown
step: unknown
recommendation:
  action: proceed
  reason: "Default mock response"
```"""
    )


def test_v2_sequential(spec: str, llm_executor: LLMExecutor, use_kb: bool = True):
    """Test V2 strategy in sequential mode."""
    print("\n" + "="*60)
    print("TESTING V2 STRATEGY - SEQUENTIAL MODE")
    print("="*60 + "\n")

    # Initialize components
    project_name = f"ruth_v2_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    blackboard = Blackboard(project_name=project_name)
    metrics = MetricsCollector(strategy="v2", project=project_name)
    kb = get_default_kb() if use_kb else None

    # Write spec to requirements
    blackboard.write(
        SectionID.REQUIREMENTS,
        {"original_prompt": spec},
        author="test_runner"
    )

    print(f"Project: {project_name}")
    print(f"KB enabled: {kb is not None}")
    print(f"LLM executor: {type(llm_executor).__name__}")
    print()

    # Run experts in V2 order
    experts = ["creative_expert", "cg_expert", "critic", "td_designer", "critic"]

    for expert_id in experts:
        print(f"\n--- Running {expert_id} ---")

        result = execute_expert(
            expert_id=expert_id,
            blackboard=blackboard,
            metrics=metrics,
            kb=kb,
            llm_executor=llm_executor
        )

        print(f"Status: {result.get('overall_success', 'N/A')}")

        # Show a bit of the output
        if 'plan' in result:
            plan_output = result['plan'].get('output', {})
            print(f"Plan status: {plan_output.get('status', 'unknown')}")

        # Write to blackboard if appropriate section exists
        if expert_id == "creative_expert":
            blackboard.write(
                SectionID.CREATIVE_VISION,
                result.get('final_output', result.get('build', {}).get('output', {})),
                author=expert_id
            )
        elif expert_id == "cg_expert":
            blackboard.write(
                SectionID.TECHNICAL_APPROACH,
                result.get('final_output', result.get('build', {}).get('output', {})),
                author=expert_id
            )
        elif expert_id == "td_designer":
            blackboard.write(
                SectionID.NETWORK_DESIGN,
                result.get('final_output', result.get('build', {}).get('output', {})),
                author=expert_id
            )

    # Print final metrics
    print("\n" + "="*60)
    print("METRICS SUMMARY")
    print("="*60)

    metrics_dict = metrics.get_report()
    print(json.dumps(metrics_dict, indent=2, default=str))

    return blackboard, metrics


def test_parallel_execution(spec: str):
    """Test ParallelExecutor with RUTH components."""
    print("\n" + "="*60)
    print("TESTING PARALLEL EXECUTOR")
    print("="*60 + "\n")

    # Configure for parallel execution
    config = ParallelBuildConfig(
        max_parallel_tasks=5,
        timeout_per_component=120,
        enable_parallel_visual=True,
        enable_parallel_integration=True
    )

    # Create parallel executor
    executor = ParallelExecutor(
        full_spec=spec,
        components=RUTH_COMPONENTS.copy(),
        config=config
    )

    print(f"Components to build: {len(executor.components)}")
    print(f"Spec sections extracted: {len(executor.component_specs)}")
    print()

    # Show what was extracted
    print("Component specs extracted:")
    for comp_id, spec_text in executor.component_specs.items():
        print(f"  - {comp_id}: {len(spec_text)} chars")
    print()

    # Execute (currently stub mode)
    print("Executing parallel build (stub mode)...")
    result = executor.execute()

    print("\n" + "="*60)
    print("PARALLEL EXECUTION RESULTS")
    print("="*60)

    print(f"Overall success: {result['success']}")
    print(f"Total time: {result['timing']['total_seconds']:.2f}s")
    print()

    print("Component results:")
    for comp_id, comp_result in result['components'].items():
        status = "OK" if comp_result['success'] else "FAILED"
        print(f"  [{status}] {comp_id} ({comp_result['phase']})")
        if comp_result['errors']:
            for err in comp_result['errors']:
                print(f"        Error: {err}")

    print()
    print("Phase timing:")
    for phase, time in result['timing']['phase_times'].items():
        print(f"  {phase}: {time:.2f}s")

    return result


def main():
    parser = argparse.ArgumentParser(description="Test V2 strategy with RUTH spec")
    parser.add_argument('--real', action='store_true', help="Use real Claude API (costs money)")
    parser.add_argument('--parallel', action='store_true', help="Test ParallelExecutor")
    parser.add_argument('--no-kb', action='store_true', help="Disable KnowledgeBase")
    args = parser.parse_args()

    print("="*60)
    print("RUTH V2 TEST RUNNER")
    print("="*60)

    # Load spec
    print("\nLoading RUTH spec...")
    spec = load_ruth_spec()
    print(f"Spec loaded: {len(spec)} chars")

    if args.parallel:
        # Test parallel execution
        test_parallel_execution(spec)
    else:
        # Create appropriate executor
        if args.real:
            print("\n[WARNING] Using REAL Claude API - this will cost money!")
            print("Press Ctrl+C within 5 seconds to cancel...")
            import time
            time.sleep(5)
            llm_executor = AnthropicExecutor()
        else:
            print("\nUsing MOCK executor (no API calls)")
            llm_executor = create_mock_executor()

        # Run test
        test_v2_sequential(spec, llm_executor, use_kb=not args.no_kb)

    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()

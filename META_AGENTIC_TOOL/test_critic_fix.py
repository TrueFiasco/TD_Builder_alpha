#!/usr/bin/env python3
"""
Minimal test to verify critic scoring works.
Runs 1 iteration of creative phase only.
"""

import sys
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

# Enable logging to see score extraction
import logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

def main():
    from meta_agentic.execution.strategy_runner import (
        StrategyConfig, QualityTargets, V2ImprovedStrategy
    )
    from meta_agentic.execution.blackboard import Blackboard
    from meta_agentic.execution.metrics import MetricsCollector

    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        return 1

    print("=" * 60)
    print("CRITIC FIX TEST")
    print("Testing: Creative phase + Critic scoring")
    print("=" * 60)

    # Minimal config - 1 iteration, low threshold
    config = StrategyConfig(
        max_iterations=1,  # Just 1 iteration
        quality_targets=QualityTargets(
            creative=0.3,  # Low threshold so it passes easily
            technical=0.3,
            design=0.3
        ),
        kb_query_enabled=True
    )

    # Simple test prompt
    prompt = "Create a simple noise pattern that pulses with audio"

    # Setup
    project_name = "critic_test"
    output_dir = Path("runs") / "critic_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    blackboard = Blackboard(project_name=project_name, persist_path=output_dir)
    metrics = MetricsCollector()

    # Run V2 strategy
    strategy = V2ImprovedStrategy()

    print(f"\nPrompt: {prompt}")
    print(f"Quality target: {config.quality_targets.creative}")
    print("\nRunning strategy...")
    print("-" * 60)

    result = strategy.execute_workflow(
        prompt=prompt,
        blackboard=blackboard,
        config=config,
        metrics=metrics
    )

    print("-" * 60)
    print("\nRESULTS:")
    print(f"  Success: {result.success}")
    print(f"  Quality Score: {result.quality_score}")
    print(f"  Errors: {result.errors}")

    if result.toe_path:
        print(f"  TOE Path: {result.toe_path}")

    # Check blackboard for scores
    from meta_agentic.execution.blackboard import SectionID
    creative = blackboard.read(SectionID.CREATIVE_VISION)
    technical = blackboard.read(SectionID.TECHNICAL_APPROACH)
    design = blackboard.read(SectionID.NETWORK_DESIGN)

    print("\nBLACKBOARD STATE:")
    print(f"  Creative Vision: {'Present' if creative else 'Empty'}")
    print(f"  Technical Approach: {'Present' if technical else 'Empty'}")
    print(f"  Network Design: {'Present' if design else 'Empty'}")

    print("=" * 60)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Test Runner: RUTH TD Spec across V0-V6 Strategies

This script runs the full RUTH (Running Up That Hill) spec through all
workflow strategies to compare their approaches.

Usage:
    python test_ruth_v0_v6.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Add meta_agentic to path
sys.path.insert(0, str(Path(__file__).parent))

from meta_agentic.execution import (
    StrategyConfig,
    Preset,
    InvolvementLevel,
    run_strategy,
    get_registry,
)


def load_spec(spec_path: Path) -> str:
    """Load the RUTH spec from file."""
    with open(spec_path, 'r', encoding='utf-8') as f:
        return f.read()


def run_all_strategies(prompt: str, project_name: str, output_dir: Path):
    """Run all V0-V6 strategies and compare results."""

    # Get all registered strategies
    registry = get_registry()
    strategies = registry.list_strategies()

    print("\n" + "=" * 80)
    print("RUTH TD SPEC - V0-V6 STRATEGY COMPARISON TEST")
    print("=" * 80)
    print(f"Project: {project_name}")
    print(f"Output: {output_dir}")
    print(f"Strategies: {', '.join(strategies)}")
    print(f"Prompt length: {len(prompt)} characters")
    print("=" * 80)

    # Create config from standard preset
    config = StrategyConfig.from_preset(Preset.STANDARD)
    config.involvement = InvolvementLevel.MINIMAL  # No user prompts

    results = {}

    for strategy_name in strategies:
        print(f"\n{'='*60}")
        print(f"RUNNING STRATEGY: {strategy_name.upper()}")
        print("=" * 60)

        # Create strategy-specific output directory
        strategy_output = output_dir / strategy_name
        strategy_output.mkdir(parents=True, exist_ok=True)

        strategy_project_name = f"{project_name}_{strategy_name}"
        persist_path = strategy_output / f"{strategy_project_name}_blackboard.yaml"

        try:
            result = run_strategy(
                strategy_name=strategy_name,
                prompt=prompt,
                config=config,
                project_name=strategy_project_name,
                persist_path=persist_path
            )

            results[strategy_name] = {
                "success": result.success,
                "errors": result.errors,
                "quality_score": result.quality_score,
                "toe_path": str(result.toe_path) if result.toe_path else None,
                "tokens": result.metrics.total_tokens.total_tokens if result.metrics else 0,
                "cost": result.metrics.total_tokens.estimated_cost_usd if result.metrics else 0,
                "iterations": result.metrics.total_iterations if result.metrics else 0,
            }

            # Save metrics if available
            if result.metrics:
                metrics_path = strategy_output / f"{strategy_project_name}_metrics.json"
                result.metrics.save(metrics_path)
                print(f"  Metrics saved: {metrics_path}")

            print(f"  Success: {result.success}")
            print(f"  Errors: {result.errors}")

        except Exception as e:
            print(f"  [ERROR] Strategy failed: {e}")
            results[strategy_name] = {
                "success": False,
                "errors": [str(e)],
                "quality_score": None,
                "toe_path": None,
                "tokens": 0,
                "cost": 0,
                "iterations": 0,
            }

    # Print comparison summary
    print("\n" + "=" * 80)
    print("STRATEGY COMPARISON SUMMARY")
    print("=" * 80)
    print(f"{'Strategy':<12} {'Success':<10} {'Quality':<10} {'Tokens':<10} {'Cost ($)':<10} {'Errors'}")
    print("-" * 80)

    for strategy_name, data in results.items():
        success_str = "Yes" if data["success"] else "No"
        quality_str = f"{data['quality_score']:.2f}" if data["quality_score"] else "N/A"
        error_count = len(data["errors"])
        print(f"{strategy_name:<12} {success_str:<10} {quality_str:<10} {data['tokens']:<10} {data['cost']:<10.4f} {error_count} error(s)")

    print("=" * 80)

    # Save comparison results
    import json
    comparison_path = output_dir / "comparison_results.json"
    with open(comparison_path, 'w', encoding='utf-8') as f:
        json.dump({
            "project": project_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "prompt_length": len(prompt),
            "strategies": results
        }, f, indent=2)
    print(f"\nComparison saved: {comparison_path}")

    return results


def main():
    # Paths
    spec_path = Path(r"C:\Users\jake_\Downloads\RUTH_TD_Spec_Final.md")
    output_dir = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\test_output\ruth_comparison")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load spec
    print("Loading RUTH spec...")
    prompt = load_spec(spec_path)
    print(f"Loaded {len(prompt)} characters from {spec_path.name}")

    # Generate project name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_name = f"ruth_td_{timestamp}"

    # Run all strategies
    results = run_all_strategies(prompt, project_name, output_dir)

    # Final status
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)

    successful = sum(1 for r in results.values() if r["success"])
    print(f"Successful strategies: {successful}/{len(results)}")
    print(f"Output directory: {output_dir}")

    print("\n[NOTE] All strategies are currently stubs.")
    print("This test validates the execution pipeline, not actual TOX generation.")
    print("To generate real output, implement the strategy execute_workflow() methods.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

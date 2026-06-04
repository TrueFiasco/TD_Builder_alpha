#!/usr/bin/env python3
"""
Workflow Executor CLI for META_AGENTIC_TOOL

This is the main entry point for running agentic workflows to generate
TouchDesigner networks. It provides a CLI interface to the execution layer.

Usage:
    python workflow_executor.py --prompt "Create an audio-reactive particle system"
    python workflow_executor.py --prompt "..." --strategy v6 --preset excellence
    python workflow_executor.py --list-strategies

For interactive mode (with user checkpoints):
    python workflow_executor.py --prompt "..." --interactive

For full automation:
    python workflow_executor.py --prompt "..." --involvement hands_off
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add meta_agentic to path
META_AGENTIC_ROOT = Path(__file__).parent / "meta_agentic"
sys.path.insert(0, str(META_AGENTIC_ROOT.parent))

from meta_agentic.execution import (
    Blackboard,
    Phase,
    SectionID,
    MetricsCollector,
    run_strategy,
    StrategyConfig,
    BuildResult,
    QualityTargets,
    InvolvementLevel,
    Preset,
    get_registry,
)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run agentic workflows for TouchDesigner network generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Quick draft with default strategy
    python workflow_executor.py --prompt "Audio-reactive waves"

    # High quality with V6 unified strategy
    python workflow_executor.py --prompt "Complex particle system" --strategy v6 --preset excellence

    # Interactive mode with user checkpoints
    python workflow_executor.py --prompt "..." --interactive

    # List available strategies
    python workflow_executor.py --list-strategies
        """
    )

    parser.add_argument(
        "--prompt", "-p",
        type=str,
        help="The generation prompt describing the desired TouchDesigner network"
    )

    parser.add_argument(
        "--strategy", "-s",
        type=str,
        default="v6",
        help="Workflow strategy to use (v0, v2, v3, v4, v5, v6). Default: v6"
    )

    parser.add_argument(
        "--preset",
        type=str,
        choices=["quick_draft", "standard", "excellence"],
        default="standard",
        help="Quality preset (quick_draft, standard, excellence). Default: standard"
    )

    parser.add_argument(
        "--involvement",
        type=str,
        choices=["full", "milestone", "hands_off"],
        default="milestone",
        help="User involvement level. Default: milestone"
    )

    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode with user prompts at checkpoints"
    )

    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("output"),
        help="Output directory for results. Default: ./output"
    )

    parser.add_argument(
        "--project-name",
        type=str,
        help="Project name (auto-generated from prompt if not specified)"
    )

    parser.add_argument(
        "--list-strategies",
        action="store_true",
        help="List available workflow strategies and exit"
    )

    parser.add_argument(
        "--compare",
        nargs="+",
        metavar="STRATEGY",
        help="Run multiple strategies and compare results (e.g., --compare v2 v3 v6)"
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum iterations per phase. Default: 10"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output with detailed logging"
    )

    return parser.parse_args()


def list_strategies():
    """Print available strategies and their descriptions."""
    registry = get_registry()

    print("\nAvailable Workflow Strategies:")
    print("=" * 60)

    for name in registry.list_strategies():
        strategy = registry.get(name)
        doc = strategy.__class__.__doc__ or 'No description'
        # Get first line of docstring
        first_line = doc.strip().split('\n')[0]
        print(f"\n  {name}:")
        print(f"    {first_line}")

    print("\n" + "=" * 60)
    print("\nPresets:")
    print("  quick_draft  - Fast iteration, lower quality bar (0.70/0.70/0.80)")
    print("  standard     - Balanced quality and speed (0.85/0.85/0.90)")
    print("  excellence   - High quality bar, more iterations (0.90/0.90/0.95)")

    print("\nInvolvement Levels:")
    print("  full       - User approval at every phase")
    print("  milestone  - User approval at key milestones only")
    print("  hands_off  - Fully automated, no user prompts")


def generate_project_name(prompt: str) -> str:
    """Generate a project name from the prompt."""
    # Take first 3-4 significant words
    words = prompt.lower().split()
    # Filter common words
    stop_words = {"a", "an", "the", "create", "make", "build", "generate", "with", "for", "and", "or"}
    significant = [w for w in words if w not in stop_words][:3]

    # Clean and join
    name = "_".join(significant)
    name = "".join(c if c.isalnum() or c == "_" else "" for c in name)

    # Add timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{name}_{timestamp}"


def run_single_strategy(
    prompt: str,
    strategy_name: str,
    project_name: str,
    config: StrategyConfig,
    output_dir: Path,
    verbose: bool = False
) -> BuildResult:
    """Run a single strategy and return results."""

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Set persist path in config
    persist_path = output_dir / f"{project_name}_blackboard.yaml"

    if verbose:
        print(f"\n[Workflow] Starting {strategy_name} strategy...")
        print(f"[Workflow] Project: {project_name}")
        print(f"[Workflow] Output: {output_dir}")

    # Run strategy using the convenience function
    result = run_strategy(
        strategy_name=strategy_name,
        prompt=prompt,
        config=config,
        project_name=project_name,
        persist_path=persist_path
    )

    # Save metrics
    if result.metrics:
        metrics_path = output_dir / f"{project_name}_metrics.json"
        result.metrics.save(metrics_path)
        if verbose:
            print(f"\n[Workflow] Metrics saved to {metrics_path}")

    # Blackboard is already saved by run_strategy if persist_path is set
    if verbose and result.blackboard:
        print(f"[Workflow] Blackboard saved to {persist_path}")

    return result


def run_comparison(
    prompt: str,
    strategies: list[str],
    project_name: str,
    config: StrategyConfig,
    output_dir: Path,
    verbose: bool = False
):
    """Run multiple strategies and compare results."""
    from meta_agentic.execution import compare_metrics

    results = []
    metrics_list = []

    for strategy_name in strategies:
        print(f"\n{'='*60}")
        print(f"Running strategy: {strategy_name}")
        print("=" * 60)

        # Create strategy-specific output directory
        strategy_output = output_dir / strategy_name
        strategy_project_name = f"{project_name}_{strategy_name}"

        try:
            result = run_single_strategy(
                prompt=prompt,
                strategy_name=strategy_name,
                project_name=strategy_project_name,
                config=config,
                output_dir=strategy_output,
                verbose=verbose
            )
            results.append((strategy_name, result))
            if result.metrics:
                metrics_list.append(result.metrics)
        except Exception as e:
            print(f"[ERROR] Strategy {strategy_name} failed: {e}")
            results.append((strategy_name, None))

    # Generate comparison report
    if metrics_list:
        comparison = compare_metrics(metrics_list)
        comparison_path = output_dir / "strategy_comparison.json"
        with open(comparison_path, "w", encoding="utf-8") as f:
            json.dump(comparison, f, indent=2)
        print(f"\n[Comparison] Report saved to {comparison_path}")

        # Print summary table
        print("\n" + "=" * 80)
        print("STRATEGY COMPARISON")
        print("=" * 80)
        print(f"{'Strategy':<12} {'Tokens':>10} {'Cost ($)':>10} {'Quality':>10} {'Iterations':>12} {'Success':>10}")
        print("-" * 80)

        for entry in comparison["strategies"]:
            success = "✓" if entry.get("toe_valid") else "✗"
            quality_str = f"{entry['quality']:.2f}" if entry['quality'] else "N/A"
            print(f"{entry['strategy']:<12} {entry['tokens']:>10} {entry['cost_usd']:>10.4f} {quality_str:>10} {entry['iterations']:>12} {success:>10}")

    return results


def main():
    """Main entry point."""
    args = parse_args()

    # Handle list-strategies
    if args.list_strategies:
        list_strategies()
        return 0

    # Validate prompt
    if not args.prompt and not args.compare:
        print("Error: --prompt is required")
        print("Use --help for usage information")
        return 1

    # Generate project name if not specified
    project_name = args.project_name or generate_project_name(args.prompt or "comparison")

    # Map preset string to enum and create config from preset
    preset_map = {
        "quick_draft": Preset.QUICK_DRAFT,
        "standard": Preset.STANDARD,
        "excellence": Preset.EXCELLENCE,
    }
    preset = preset_map.get(args.preset, Preset.STANDARD)

    # Create config from preset
    config = StrategyConfig.from_preset(preset)

    # Override max_iterations if specified
    if args.max_iterations != 10:  # 10 is default
        config.max_iterations = args.max_iterations

    # Override involvement if not interactive
    if not args.interactive:
        config.involvement = InvolvementLevel.MINIMAL

    # Ensure output directory exists
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("META_AGENTIC_TOOL Workflow Executor")
    print("=" * 60)
    print(f"Project: {project_name}")
    print(f"Strategy: {args.strategy}")
    print(f"Preset: {args.preset}")
    print(f"Involvement: {config.involvement.value}")
    print(f"Output: {output_dir}")

    if args.compare:
        # Run comparison mode
        results = run_comparison(
            prompt=args.prompt,
            strategies=args.compare,
            project_name=project_name,
            config=config,
            output_dir=output_dir,
            verbose=args.verbose
        )
    else:
        # Run single strategy
        result = run_single_strategy(
            prompt=args.prompt,
            strategy_name=args.strategy,
            project_name=project_name,
            config=config,
            output_dir=output_dir,
            verbose=args.verbose
        )

        # Print summary
        print("\n" + "=" * 60)
        print("WORKFLOW COMPLETE")
        print("=" * 60)
        print(f"Success: {result.success}")

        if result.toe_path:
            print(f"TOE File: {result.toe_path}")

        if result.metrics:
            total = result.metrics.total_tokens
            print(f"Tokens: {total.total_tokens} (${total.estimated_cost_usd:.4f})")
            print(f"Iterations: {result.metrics.total_iterations}")
            print(f"Quality: {result.metrics.final_quality_score}")

        if result.errors:
            print(f"\nErrors:")
            for error in result.errors:
                print(f"  - {error}")

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())

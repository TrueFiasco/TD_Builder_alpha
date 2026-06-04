#!/usr/bin/env python3
"""
Infrastructure test - validates all components load correctly WITHOUT making API calls.
This tests imports, file existence, and basic configuration.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_imports():
    """Test that all critical modules import correctly."""
    print("Testing imports...")

    errors = []

    # Core modules
    try:
        from meta_agentic.execution.strategy_runner import (
            run_strategy, StrategyConfig, QualityTargets,
            V6UnifiedStrategy, StrategyRegistry, get_registry
        )
        print("  [OK] strategy_runner")
    except Exception as e:
        errors.append(f"strategy_runner: {e}")
        print(f"  [FAIL] strategy_runner: {e}")

    try:
        from meta_agentic.execution.expert_executor import ExpertExecutor
        print("  [OK] expert_executor")
    except Exception as e:
        errors.append(f"expert_executor: {e}")
        print(f"  [FAIL] expert_executor: {e}")

    try:
        from meta_agentic.execution.blackboard import Blackboard, SectionID
        print("  [OK] blackboard")
    except Exception as e:
        errors.append(f"blackboard: {e}")
        print(f"  [FAIL] blackboard: {e}")

    try:
        from meta_agentic.execution.kb_query import KnowledgeBase, get_default_kb
        print("  [OK] kb_query (KnowledgeBase)")
    except Exception as e:
        errors.append(f"kb_query: {e}")
        print(f"  [FAIL] kb_query: {e}")

    try:
        from meta_agentic.execution.run_logger import RunLogger
        print("  [OK] run_logger")
    except Exception as e:
        errors.append(f"run_logger: {e}")
        print(f"  [FAIL] run_logger: {e}")

    return len(errors) == 0, errors


def test_expert_prompts_exist():
    """Verify all expert prompt files exist."""
    print("\nTesting expert prompts...")

    experts_dir = project_root / "meta_agentic" / "experts"
    required_prompts = [
        "creative_expert/build.md",
        "creative_expert/plan.md",
        "cg_expert/build.md",
        "cg_expert/plan.md",
        "td_designer/build.md",
        "td_designer/plan.md",
        "critic/build.md",
        "network_builder/build.md",
    ]

    missing = []
    for prompt in required_prompts:
        path = experts_dir / prompt
        if path.exists():
            print(f"  [OK] {prompt}")
        else:
            missing.append(prompt)
            print(f"  [FAIL] {prompt} - MISSING")

    return len(missing) == 0, missing


def test_kb_files_exist():
    """Verify knowledge base files exist."""
    print("\nTesting KB files...")

    # KB files are in meta_agentic/expertise/
    kb_dir = project_root / "meta_agentic" / "expertise"
    required_files = [
        "cg_concepts.yaml",
        "creative_vision.yaml",
        "td_operators.yaml",
        "td_network_patterns.yaml",
    ]

    missing = []
    for f in required_files:
        path = kb_dir / f
        if path.exists():
            print(f"  [OK] {f}")
        else:
            missing.append(f)
            print(f"  [FAIL] {f} - MISSING")

    return len(missing) == 0, missing


def test_config_creation():
    """Test strategy configuration creation."""
    print("\nTesting configuration...")

    from meta_agentic.execution.strategy_runner import StrategyConfig, QualityTargets

    config = StrategyConfig(
        max_iterations=1,
        quality_targets=QualityTargets(creative=0.6, technical=0.6, design=0.6),
        kb_query_enabled=True
    )

    assert config.max_iterations == 1
    assert config.quality_targets.creative == 0.6
    print("  [OK] StrategyConfig creation")
    print("  [OK] QualityTargets creation")

    return True, []


def test_strategy_registry():
    """Test that strategy registry works and strategies are registered."""
    print("\nTesting strategy registry...")

    from meta_agentic.execution.strategy_runner import get_registry

    registry = get_registry()
    strategies = registry.list_strategies()

    print(f"  Available strategies: {strategies}")

    if "v6" in strategies:
        print("  [OK] V6 strategy registered")
    else:
        return False, ["V6 strategy not registered"]

    return True, []


def test_knowledge_base():
    """Test KnowledgeBase initialization and queries."""
    print("\nTesting KnowledgeBase...")

    from meta_agentic.execution.kb_query import get_default_kb

    kb = get_default_kb()
    print("  [OK] Default KB loaded")

    # Test operator validation
    from meta_agentic.execution.kb_query import validate_operator
    is_valid = validate_operator("TOP", "noise")
    print(f"  [OK] validate_operator (noise TOP valid: {is_valid})")

    return True, []


def main():
    """Run all infrastructure tests."""
    print("=" * 60)
    print("META_AGENTIC_TOOL Infrastructure Test")
    print("(No API calls - validates code structure only)")
    print("=" * 60)

    all_passed = True
    all_errors = []

    tests = [
        ("Imports", test_imports),
        ("Expert Prompts", test_expert_prompts_exist),
        ("KB Files", test_kb_files_exist),
        ("Config Creation", test_config_creation),
        ("Strategy Registry", test_strategy_registry),
        ("Knowledge Base", test_knowledge_base),
    ]

    for name, test_fn in tests:
        try:
            passed, errors = test_fn()
            if not passed:
                all_passed = False
                all_errors.extend(errors)
        except Exception as e:
            all_passed = False
            all_errors.append(f"{name}: {e}")
            print(f"  [FAIL] EXCEPTION: {e}")

    print("\n" + "=" * 60)
    if all_passed:
        print("[PASS] ALL INFRASTRUCTURE TESTS PASSED")
        print("   Code structure is valid - ready for LLM integration")
    else:
        print("[FAIL] SOME TESTS FAILED")
        for err in all_errors:
            print(f"   - {err}")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

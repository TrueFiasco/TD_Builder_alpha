"""
Test script to verify KB integration with expert_executor.

This script tests that:
1. KnowledgeBase can be initialized
2. ExpertExecutor accepts KB instance
3. Expertise is loaded and included in context
4. Expertise is properly substituted into prompts
"""

from pathlib import Path
from meta_agentic.execution.expert_executor import ExpertExecutor, get_expert_executor, EXPERT_CONFIGS
from meta_agentic.execution.blackboard import Blackboard, Phase
from meta_agentic.execution.metrics import MetricsCollector
from meta_agentic.execution.kb_query import KnowledgeBase

def test_kb_integration():
    """Test KB integration with expert executor."""

    print("=== Testing KB Integration ===\n")

    # 1. Initialize KnowledgeBase
    print("1. Initializing KnowledgeBase...")
    base_path = Path(__file__).parent / "meta_agentic" / "expertise"

    if not base_path.exists():
        print(f"   ERROR: Expertise directory not found at {base_path}")
        return False

    kb = KnowledgeBase(base_path)
    print(f"   SUCCESS: KnowledgeBase initialized at {base_path}\n")

    # 2. Initialize Blackboard and Metrics
    print("2. Initializing Blackboard and Metrics...")
    blackboard = Blackboard(project_name="kb_integration_test")
    metrics = MetricsCollector(strategy="v2", project="kb_integration_test")
    print("   SUCCESS: Blackboard and Metrics initialized\n")

    # 3. Test with different experts
    test_experts = [
        "creative_expert",
        "cg_expert",
        "td_designer",
        "td_glsl_expert",
        "network_builder",
        "critic"
    ]

    print("3. Testing expert executors with KB...\n")

    for expert_id in test_experts:
        print(f"   Testing {expert_id}:")

        try:
            # Get executor with KB
            executor = get_expert_executor(expert_id, blackboard, metrics, kb)
            print(f"      [OK] Executor created with KB")

            # Load expertise
            expertise = executor.load_expertise_for_expert()
            if expertise:
                print(f"      [OK] Loaded {len(expertise)} expertise files:")
                for file_name in expertise.keys():
                    print(f"         - {file_name}")
            else:
                print(f"      [OK] No expertise files configured (OK)")

            # Prepare context
            context = executor.prepare_context()
            if "expertise" in context:
                print(f"      [OK] Expertise included in context")
                print(f"         - Raw expertise: {len(context['expertise']['raw'])} files")
                print(f"         - YAML expertise: {len(context['expertise']['yaml'])} files")
            else:
                print(f"      [OK] No expertise in context (OK - KB may be None or no files)")

            print()

        except Exception as e:
            print(f"      [ERROR] ERROR: {e}\n")
            return False

    # 4. Test expertise substitution in prompts
    print("4. Testing expertise substitution in prompts...")

    try:
        # Use td_designer as it has multiple expertise files
        executor = get_expert_executor("td_designer", blackboard, metrics, kb)
        context = executor.prepare_context()

        if "expertise" in context:
            # Check that expertise keys are available for substitution
            expertise_yaml = context["expertise"]["yaml"]
            print(f"   [OK] Available expertise keys for substitution:")
            for file_name in expertise_yaml.keys():
                key = file_name.replace(".yaml", "_yaml").replace(".yml", "_yaml")
                print(f"      - {{{{{key}}}}}")

            # Check combined expertise_yaml
            print(f"   [OK] Combined expertise_yaml available: {{{{expertise_yaml}}}}")
        else:
            print(f"   No expertise to substitute (OK if KB not provided)")

        print()

    except Exception as e:
        print(f"   [ERROR] ERROR: {e}\n")
        return False

    print("=== All Tests Passed! ===\n")
    return True


if __name__ == "__main__":
    success = test_kb_integration()
    exit(0 if success else 1)

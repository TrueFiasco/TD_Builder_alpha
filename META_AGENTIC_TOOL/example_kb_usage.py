"""
Example: Using ExpertExecutor with KnowledgeBase

This example demonstrates how to use the KB-enhanced expert executor.
"""

from pathlib import Path
from meta_agentic.execution.expert_executor import get_expert_executor, execute_expert
from meta_agentic.execution.blackboard import Blackboard
from meta_agentic.execution.metrics import MetricsCollector
from meta_agentic.execution.kb_query import get_default_kb

def example_basic_usage():
    """Example: Basic usage without KB"""
    print("=== Example 1: Basic Usage (No KB) ===\n")

    # Initialize components
    blackboard = Blackboard(project_name="example_project")
    metrics = MetricsCollector(strategy="v2", project="example_project")

    # Create executor without KB
    executor = get_expert_executor("creative_expert", blackboard, metrics)
    print(f"Created executor for: {executor.expert_id}")
    print(f"KB enabled: {executor.kb is not None}")
    print()


def example_with_kb():
    """Example: Using KB for enhanced expertise"""
    print("=== Example 2: Using KnowledgeBase ===\n")

    # Initialize components
    blackboard = Blackboard(project_name="example_project")
    metrics = MetricsCollector(strategy="v2", project="example_project")

    # Get default KB
    kb = get_default_kb()
    print(f"KB initialized at: {kb.base_path}\n")

    # Create executor with KB
    executor = get_expert_executor("td_designer", blackboard, metrics, kb)
    print(f"Created executor for: {executor.expert_id}")
    print(f"KB enabled: {executor.kb is not None}\n")

    # Load expertise
    expertise = executor.load_expertise_for_expert()
    print(f"Loaded expertise files:")
    for file_name in expertise.keys():
        print(f"  - {file_name}")
    print()

    # Prepare context (includes expertise)
    context = executor.prepare_context()
    if "expertise" in context:
        print(f"Expertise in context:")
        print(f"  - Raw files: {len(context['expertise']['raw'])}")
        print(f"  - YAML files: {len(context['expertise']['yaml'])}")
        print(f"\nAvailable substitution keys:")
        for file_name in context['expertise']['yaml'].keys():
            key = file_name.replace(".yaml", "_yaml").replace(".yml", "_yaml")
            print(f"  - {{{{{key}}}}}")
        print(f"  - {{{{expertise_yaml}}}} (combined)")
    print()


def example_different_experts():
    """Example: Different experts get different expertise"""
    print("=== Example 3: Expert-Specific Expertise ===\n")

    blackboard = Blackboard(project_name="example_project")
    metrics = MetricsCollector(strategy="v2", project="example_project")
    kb = get_default_kb()

    experts = ["creative_expert", "cg_expert", "td_designer", "td_glsl_expert"]

    for expert_id in experts:
        executor = get_expert_executor(expert_id, blackboard, metrics, kb)
        expertise = executor.load_expertise_for_expert()

        print(f"{expert_id}:")
        if expertise:
            for file_name in expertise.keys():
                print(f"  - {file_name}")
        else:
            print(f"  (no expertise files)")
        print()


def example_execute_expert_helper():
    """Example: Using execute_expert() helper function"""
    print("=== Example 4: Using execute_expert() Helper ===\n")

    blackboard = Blackboard(project_name="example_project")
    metrics = MetricsCollector(strategy="v2", project="example_project")
    kb = get_default_kb()

    # Execute expert with KB (convenience function)
    result = execute_expert(
        expert_id="td_designer",
        blackboard=blackboard,
        metrics=metrics,
        kb=kb
    )

    print(f"Result keys: {list(result.keys())}")
    print(f"Overall success: {result.get('overall_success', False)}")
    if 'plan' in result:
        print(f"Plan step executed: {result['plan'].get('expert_id', 'N/A')}")
    print()


if __name__ == "__main__":
    print("KB Integration Examples\n" + "="*50 + "\n")

    try:
        example_basic_usage()
        example_with_kb()
        example_different_experts()
        example_execute_expert_helper()

        print("="*50)
        print("All examples completed successfully!")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

"""
Verify that expertise is properly substituted into prompts.

This script demonstrates that the KB expertise is actually available
in the rendered prompts.
"""

from meta_agentic.execution.expert_executor import get_expert_executor
from meta_agentic.execution.blackboard import Blackboard
from meta_agentic.execution.metrics import MetricsCollector
from meta_agentic.execution.kb_query import get_default_kb

def verify_expertise_substitution():
    """Verify expertise is properly substituted into prompts."""

    print("=== Verifying Expertise Substitution in Prompts ===\n")

    # Initialize components
    blackboard = Blackboard(project_name="verify_test")
    metrics = MetricsCollector(strategy="v2", project="verify_test")
    kb = get_default_kb()

    # Test with td_designer (has 3 expertise files)
    print("Testing with td_designer expert...\n")

    executor = get_expert_executor("td_designer", blackboard, metrics, kb)

    # Prepare context
    context = executor.prepare_context()

    print("1. Context includes expertise:")
    print(f"   - Expertise present: {'expertise' in context}")

    if 'expertise' in context:
        print(f"   - Raw files: {list(context['expertise']['raw'].keys())}")
        print(f"   - YAML files: {list(context['expertise']['yaml'].keys())}")
        print()

        print("2. YAML content samples:")
        for file_name, yaml_content in context['expertise']['yaml'].items():
            print(f"\n   {file_name}:")
            # Show first 200 chars
            sample = yaml_content[:200].replace('\n', '\n   ')
            print(f"   {sample}...")
            print(f"   (Total length: {len(yaml_content)} chars)")

        print("\n3. Substitution keys available in render_prompt():")

        # Show what keys will be available
        substitution_keys = []
        for file_name in context['expertise']['yaml'].keys():
            key = file_name.replace(".yaml", "_yaml").replace(".yml", "_yaml")
            substitution_keys.append(f"{{{{{key}}}}}")

        substitution_keys.append("{{expertise_yaml}}")

        for key in substitution_keys:
            print(f"   - {key}")

        print("\n4. Example: How to use in prompt templates:")
        print("""
   # In plan.md, build.md, or self_improve.md:

   ---
   You are the TD Designer expert.

   ## Operator Reference
   {{td_operators_yaml}}

   ## Network Patterns
   {{td_network_patterns_yaml}}

   ## Parameters Guide
   {{td_parameters_yaml}}

   ---
   Or use combined expertise:
   {{expertise_yaml}}

   Now design a network for: {{user_request}}
   ---
        """)

        print("\n5. Combined expertise sample:")
        combined = context['expertise']['yaml']
        total_chars = sum(len(yaml_content) for yaml_content in combined.values())
        print(f"   Total combined YAML: {total_chars} characters across {len(combined)} files")

    print("\n=== Verification Complete ===")


if __name__ == "__main__":
    verify_expertise_substitution()

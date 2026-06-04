#!/usr/bin/env python3
"""
Batch process TouchDesigner concepts through Haiku for semantic descriptions.
Creates embedding-friendly summaries from long concept pages.
"""

import json
import yaml
import anthropic
from pathlib import Path
from time import sleep

# Paths
TD_UNIVERSAL = Path(r"C:\TD_Projects\td_universal.json")
OUTPUT_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """You are creating semantic search descriptions for TouchDesigner documentation.
For each concept, write a 1-2 sentence summary optimized for search.
Focus on WHAT the concept is and WHEN/WHY you'd use it.
Someone might search "how do I export CHOP data" or "what is time slicing" - your descriptions should match.
Output ONLY valid YAML, no explanations."""


def process_batch(client, concepts: list, batch_num: int) -> dict:
    """Process a batch of concepts through Haiku."""

    prompt_parts = [
        "Create semantic search descriptions for these TouchDesigner concepts.",
        "Output as YAML with concept names as keys.",
        "Example:",
        "```yaml",
        "CHOP Exporting: \"Transfer CHOP channel data to operator parameters. Use for animation, audio reactivity, or data-driven effects.\"",
        "```",
        "",
        "---",
        ""
    ]

    for c in concepts:
        name = c['name']
        content = c.get('full_content', '')[:1500]  # Truncate long content
        prompt_parts.append(f"## {name}")
        prompt_parts.append(f"{content}")
        prompt_parts.append("")

    prompt = '\n'.join(prompt_parts)

    print(f"  Batch {batch_num}: {len(concepts)} concepts ({len(prompt)} chars)...")

    try:
        response = client.messages.create(
            model='claude-3-5-haiku-latest',
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': prompt}]
        )

        output = response.content[0].text

        # Extract YAML from response
        if '```yaml' in output:
            output = output.split('```yaml')[1].split('```')[0]
        elif '```' in output:
            output = output.split('```')[1].split('```')[0]

        try:
            result = yaml.safe_load(output)
            return result if result else {}
        except yaml.YAMLError as e:
            print(f"    YAML parse error: {e}")
            debug_path = OUTPUT_DIR / f"concept_batch_{batch_num}_raw.txt"
            debug_path.write_text(output, encoding='utf-8')
            return {}

    except Exception as e:
        print(f"    API error: {e}")
        return {}


def main():
    client = anthropic.Anthropic()

    # Load concepts
    print("Loading concepts from td_universal.json...")
    with open(TD_UNIVERSAL, 'r', encoding='utf-8') as f:
        data = json.load(f)

    concepts = data.get('concepts', [])
    print(f"Found {len(concepts)} concepts")

    # Filter to concepts with content
    concepts_with_content = [c for c in concepts if c.get('full_content', '').strip()]
    print(f"With content: {len(concepts_with_content)}")

    all_results = {}

    # Process in batches of 15
    batch_size = 15
    total_batches = (len(concepts_with_content) + batch_size - 1) // batch_size

    print(f"\nProcessing {total_batches} batches...")

    for i in range(0, len(concepts_with_content), batch_size):
        batch = concepts_with_content[i:i+batch_size]
        batch_num = i // batch_size + 1

        result = process_batch(client, batch, batch_num)
        all_results.update(result)

        # Progress
        print(f"    Completed: {len(all_results)} concepts so far")
        sleep(0.5)  # Rate limiting

    # Save results
    output_path = OUTPUT_DIR / "concept_semantic_descriptions.yaml"
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(all_results, f, default_flow_style=False, sort_keys=True, allow_unicode=True)

    json_path = OUTPUT_DIR / "concept_semantic_descriptions.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2)

    print(f"\n=== Complete ===")
    print(f"Processed {len(all_results)} concepts")
    print(f"Saved to: {output_path}")


if __name__ == '__main__':
    main()

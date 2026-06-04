#!/usr/bin/env python3
"""
Batch process _Class documentation through Haiku for semantic descriptions.
Processes base classes and operator-specific classes separately.
"""

import json
import yaml
import anthropic
from pathlib import Path
from time import sleep

# Paths
FACTS_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts")
OUTPUT_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """You are a technical writer creating semantic descriptions for TouchDesigner's Python API.
For each method/member, write a 1-2 sentence description optimized for semantic search.
Focus on WHAT it does and WHEN/WHY you'd use it. Use natural language.
Someone might search "how do I get image dimensions" or "save image to disk" - your descriptions should match those queries.
Output ONLY valid YAML, no explanations."""


def format_class_prompt(cls: dict) -> str:
    """Format a single class for the prompt."""
    lines = [f"## {cls['class_name']}"]

    if cls.get('is_base_class'):
        lines.append(f"Base class for all {cls['family']} operators\n")
    else:
        lines.append(f"Operator: {cls.get('operator', 'unknown')} ({cls.get('family', 'unknown')})\n")

    if cls['members']:
        lines.append("### Members")
        for m in cls['members']:
            ro = ' (read-only)' if m.get('readonly') else ''
            desc = m.get('description', '')[:150]
            lines.append(f"- `{m['name']}` → {m['return_type']}{ro}: {desc}")
        lines.append("")

    if cls['methods']:
        lines.append("### Methods")
        for m in cls['methods']:
            desc = m.get('description', '')[:150]
            lines.append(f"- `{m['signature']}` → {m['return_type']}: {desc}")
        lines.append("")

    if cls.get('callbacks'):
        lines.append("### Callbacks")
        for cb in cls['callbacks']:
            params = ', '.join(cb.get('parameters', []))
            lines.append(f"- `{cb['name']}({params})`")
        lines.append("")

    return '\n'.join(lines)


def process_batch(client, classes: list, batch_name: str) -> dict:
    """Process a batch of classes through Haiku."""

    # Build prompt
    prompt_parts = [
        "Generate semantic descriptions for these TouchDesigner Python API items.",
        "Output as YAML with class names as top-level keys, member/method names as nested keys.",
        "Example format:",
        "```yaml",
        "TOP_Class:",
        "  width: \"Get the pixel width of an image texture...\"",
        "  save: \"Export the image to disk as JPG, PNG...\"",
        "```",
        "",
        "---",
        ""
    ]

    for cls in classes:
        if cls['members'] or cls['methods'] or cls.get('callbacks'):
            prompt_parts.append(format_class_prompt(cls))

    prompt = '\n'.join(prompt_parts)

    print(f"  Sending {batch_name} to Haiku ({len(prompt)} chars)...")

    try:
        response = client.messages.create(
            model='claude-3-5-haiku-latest',
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': prompt}]
        )

        output = response.content[0].text

        # Extract YAML from response (may be wrapped in code blocks)
        if '```yaml' in output:
            output = output.split('```yaml')[1].split('```')[0]
        elif '```' in output:
            output = output.split('```')[1].split('```')[0]

        # Parse YAML
        try:
            result = yaml.safe_load(output)
            return result if result else {}
        except yaml.YAMLError as e:
            print(f"  YAML parse error: {e}")
            # Save raw output for debugging
            debug_path = OUTPUT_DIR / f"{batch_name}_raw.txt"
            debug_path.write_text(output, encoding='utf-8')
            return {}

    except Exception as e:
        print(f"  API error: {e}")
        return {}


def main():
    client = anthropic.Anthropic()

    all_results = {}

    # Process base classes (high priority - shared by all operators)
    print("\n=== Processing Base Classes ===")
    base_path = FACTS_DIR / "base_classes.json"
    if base_path.exists():
        with open(base_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Process each base class individually (they're important)
        for cls in data['classes']:
            if cls['members'] or cls['methods']:
                result = process_batch(client, [cls], cls['class_name'])
                all_results.update(result)
                sleep(0.5)  # Rate limiting

    # Process operator-specific classes by family
    print("\n=== Processing Operator Classes ===")
    for family_file in sorted(FACTS_DIR.glob("*_operator_classes.json")):
        family = family_file.stem.replace('_operator_classes', '')
        print(f"\nProcessing {family}...")

        with open(family_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Filter to classes with content
        classes_with_content = [c for c in data['classes']
                               if c['members'] or c['methods'] or c.get('callbacks')]

        if not classes_with_content:
            print(f"  No unique content in {family}")
            continue

        # Batch into groups of 10 classes
        batch_size = 10
        for i in range(0, len(classes_with_content), batch_size):
            batch = classes_with_content[i:i+batch_size]
            batch_name = f"{family}_batch_{i//batch_size + 1}"
            result = process_batch(client, batch, batch_name)
            all_results.update(result)
            sleep(0.5)  # Rate limiting

    # Save combined results
    output_path = OUTPUT_DIR / "class_semantic_descriptions.yaml"
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(all_results, f, default_flow_style=False, sort_keys=True, allow_unicode=True)

    print(f"\n=== Complete ===")
    print(f"Processed {len(all_results)} classes")
    print(f"Saved to: {output_path}")

    # Also save as JSON for easier programmatic access
    json_path = OUTPUT_DIR / "class_semantic_descriptions.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2)
    print(f"Also saved: {json_path}")


if __name__ == '__main__':
    main()

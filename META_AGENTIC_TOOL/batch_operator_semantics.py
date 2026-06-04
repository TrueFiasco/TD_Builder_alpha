#!/usr/bin/env python3
"""
Batch process operator wiki pages through Haiku for semantic summaries.
"""

import json
import yaml
import anthropic
from pathlib import Path
from time import sleep

OUTPUT_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_output")
FACTS_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """You create semantic search descriptions for TouchDesigner operators.
For each operator, output:
1. A 1-2 sentence summary of what it does and when to use it
2. Key parameters with their programmatic name (par.xxx) and a 1 sentence description

Output ONLY valid YAML with operator names as keys. Example:
```yaml
Noise_CHOP:
  summary: "Generates irregular non-repeating waves for animation and procedural motion."
  parameters:
    type: "Select noise algorithm: Sparse, Hermite, Alligator, etc."
    amp: "Amplitude/strength of the noise output."
    period: "Time period over which noise pattern repeats."
```"""


def load_operators(family: str) -> list:
    """Load operators for a specific family."""
    path = FACTS_DIR / f"{family}_operators_wiki.json"
    if not path.exists():
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('operators', [])


def create_batch_prompt(operators: list) -> str:
    """Create prompt for a batch of operators."""
    parts = ["Create semantic summaries for these TouchDesigner operators:\n"]

    for op in operators:
        parts.append(f"## {op['name']}")
        parts.append(f"Summary: {op['summary'][:400]}")

        if op['parameters']:
            parts.append("Parameters:")
            # Include important parameters (skip common page params)
            key_params = [p for p in op['parameters']
                         if p.get('section', '') and 'Common Page' not in p.get('section', '')][:8]

            for param in key_params:
                code = param.get('code', 'unknown')
                desc = param.get('description', '')[:100]
                parts.append(f"  - {code}: {desc}")

        parts.append("")

    return '\n'.join(parts)


def process_batch(client, operators: list, batch_num: int, family: str) -> dict:
    """Process a batch through Haiku."""
    prompt = create_batch_prompt(operators)

    print(f"  Batch {batch_num}: {[o['name'][:20] for o in operators]}...")

    try:
        response = client.messages.create(
            model='claude-3-5-haiku-latest',
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{'role': 'user', 'content': prompt}]
        )

        output = response.content[0].text

        # Extract YAML
        if '```yaml' in output:
            output = output.split('```yaml')[1].split('```')[0]
        elif '```' in output:
            output = output.split('```')[1].split('```')[0]

        try:
            result = yaml.safe_load(output)
            return result if result else {}
        except yaml.YAMLError as e:
            print(f"    YAML error: {e}")
            return {}

    except Exception as e:
        print(f"    API error: {e}")
        return {}


def process_family(client, family: str):
    """Process all operators in a family."""
    operators = load_operators(family)
    if not operators:
        print(f"No operators found for {family}")
        return

    print(f"\n=== Processing {family}: {len(operators)} operators ===")

    all_results = {}
    batch_size = 5

    for i in range(0, len(operators), batch_size):
        batch = operators[i:i+batch_size]
        batch_num = i // batch_size + 1

        result = process_batch(client, batch, batch_num, family)
        all_results.update(result)

        print(f"    Completed: {len(all_results)} operators")
        sleep(0.3)  # Rate limiting

    # Save results
    output_path = OUTPUT_DIR / f"{family}_operator_wiki_semantics.yaml"
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(all_results, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"Saved {len(all_results)} {family} operators -> {output_path.name}")
    return all_results


def main():
    client = anthropic.Anthropic()

    families = ['CHOP', 'TOP', 'SOP', 'DAT', 'COMP', 'MAT', 'POP']

    all_results = {}

    for family in families:
        results = process_family(client, family)
        if results:
            all_results[family] = results

    # Save combined file
    combined_path = OUTPUT_DIR / "all_operator_wiki_semantics.yaml"
    with open(combined_path, 'w', encoding='utf-8') as f:
        yaml.dump(all_results, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    total = sum(len(r) for r in all_results.values())
    print(f"\n=== Complete ===")
    print(f"Total operators processed: {total}")
    print(f"Combined output: {combined_path}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Extract operator wiki data for knowledge base.
Creates structured facts + prepares for Haiku summarization.
"""

import json
import yaml
from pathlib import Path

TD_UNIVERSAL = Path(r"C:\TD_Projects\td_universal.json")
OUTPUT_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_operators():
    """Extract all operator data from td_universal.json."""

    with open(TD_UNIVERSAL, 'r', encoding='utf-8') as f:
        data = json.load(f)

    operators = data.get('operators', [])
    print(f"Found {len(operators)} operators")

    # Organize by family
    by_family = {}

    for op in operators:
        family = op.get('family', 'Unknown')
        if family not in by_family:
            by_family[family] = []

        # Extract key info
        op_data = {
            'name': op['name'],
            'family': family,
            'summary': op.get('summary', ''),
            'python_class': op.get('python_class', ''),
            'parameters': []
        }

        # Extract parameters with their codes (programmatic names)
        for param in op.get('parameters', []):
            op_data['parameters'].append({
                'code': param.get('code', ''),  # This is the actual par.xxx name
                'display_name': param.get('display_name', ''),
                'description': param.get('description', ''),
                'section': param.get('section', '')
            })

        by_family[family].append(op_data)

    return by_family


def save_structured_facts(by_family: dict):
    """Save structured operator facts by family."""

    for family, ops in by_family.items():
        output_path = OUTPUT_DIR / f"{family}_operators_wiki.json"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'family': family,
                'count': len(ops),
                'operators': ops
            }, f, indent=2, ensure_ascii=False)

        print(f"Saved {family}: {len(ops)} operators -> {output_path.name}")


def prepare_haiku_batches(by_family: dict, batch_size: int = 5):
    """Prepare batches for Haiku processing."""

    batches = []

    for family, ops in by_family.items():
        for i in range(0, len(ops), batch_size):
            batch_ops = ops[i:i+batch_size]

            # Create prompt content for this batch
            prompt_parts = []
            for op in batch_ops:
                prompt_parts.append(f"## {op['name']}")
                prompt_parts.append(f"Summary: {op['summary'][:500]}")
                prompt_parts.append("Parameters:")

                # Include first 10 parameters (most important)
                for param in op['parameters'][:10]:
                    code = param['code']
                    desc = param['description'][:150]
                    prompt_parts.append(f"  - {code}: {desc}")

                if len(op['parameters']) > 10:
                    prompt_parts.append(f"  ... and {len(op['parameters'])-10} more parameters")

                prompt_parts.append("")

            batches.append({
                'family': family,
                'batch_num': i // batch_size + 1,
                'operators': [op['name'] for op in batch_ops],
                'content': '\n'.join(prompt_parts)
            })

    return batches


def main():
    # Extract all operator data
    by_family = extract_operators()

    # Save structured facts
    save_structured_facts(by_family)

    # Prepare Haiku batches
    batches = prepare_haiku_batches(by_family)

    # Save batch info for processing
    batch_path = OUTPUT_DIR / "operator_wiki_batches.json"
    with open(batch_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_batches': len(batches),
            'batches': batches
        }, f, indent=2, ensure_ascii=False)

    print(f"\nPrepared {len(batches)} batches for Haiku processing")
    print(f"Batch info saved to: {batch_path}")

    # Summary stats
    total_params = sum(
        sum(len(op['parameters']) for op in ops)
        for ops in by_family.values()
    )
    print(f"\nTotal parameters across all operators: {total_params}")


if __name__ == '__main__':
    main()

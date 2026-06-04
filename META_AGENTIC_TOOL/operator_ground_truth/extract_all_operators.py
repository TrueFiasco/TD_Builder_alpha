#!/usr/bin/env python3
"""
Extract all operator types from our KB to generate the operator list
for the TouchDesigner sampling script.
"""

import json
from pathlib import Path

# Load from embedding docs
EMBEDDING_PATH = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\embedding_docs\all_embedding_docs.json")
OUTPUT_PATH = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\operator_ground_truth\operator_types.json")

def extract_operator_types():
    with open(EMBEDDING_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    docs = data.get('documents', [])

    # Extract operator info
    operators_by_family = {
        'CHOP': [],
        'TOP': [],
        'SOP': [],
        'DAT': [],
        'COMP': [],
        'MAT': [],
        'POP': [],
    }

    seen = set()

    # Filter out documentation/non-operator entries
    SKIP_PATTERNS = [
        'Anatomy_of_a_',
        'Introduction_to_',
        '_Class',  # Python class docs
        '_Vid_Notes',
        'Category:',
    ]

    for doc in docs:
        doc_id = doc.get('id', '')
        doc_type = doc.get('type', '')
        family = doc.get('family', '')

        if doc_type == 'operator' and doc_id.startswith('op_'):
            op_name = doc_id[3:]  # Remove 'op_' prefix

            # Skip documentation entries
            if any(pattern in op_name for pattern in SKIP_PATTERNS):
                continue

            # Skip if already seen
            if op_name in seen:
                continue
            seen.add(op_name)

            # Determine TD create name (e.g., Blur_TOP -> blurTOP)
            # Handle multi-word names: Audio_File_In_TOP -> audiofileinTOP
            if '_' in op_name:
                parts = op_name.rsplit('_', 1)
                family_suffix = parts[1]  # TOP, CHOP, etc.
                base_name = parts[0].replace('_', '').lower()
                td_create_name = f"{base_name}{family_suffix}"
            else:
                td_create_name = op_name.lower()

            if family in operators_by_family:
                operators_by_family[family].append({
                    'name': op_name,
                    'td_create': td_create_name,
                })

    # Sort each family
    for family in operators_by_family:
        operators_by_family[family].sort(key=lambda x: x['name'])

    # Stats
    total = sum(len(ops) for ops in operators_by_family.values())

    output = {
        'total_operators': total,
        'by_family': {k: len(v) for k, v in operators_by_family.items()},
        'operators': operators_by_family
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)

    print(f"Extracted {total} operators")
    for family, ops in operators_by_family.items():
        print(f"  {family}: {len(ops)}")
    print(f"\nSaved to: {OUTPUT_PATH}")

    return output

if __name__ == '__main__':
    extract_operator_types()

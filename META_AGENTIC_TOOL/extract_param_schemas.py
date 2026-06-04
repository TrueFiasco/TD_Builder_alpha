#!/usr/bin/env python3
"""
Extract complete parameter schemas from TouchDesigner knowledge base.
Generates operator_param_schemas.json for validation and tox building.

Handles:
- All documented parameters per operator
- Repeated parameter slots (name0-9, const0-39, etc.)
- Parameter types, defaults, and ranges where available
"""

import json
import re
from pathlib import Path
from collections import defaultdict

EMBEDDING_DOCS_PATH = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\embedding_docs\all_embedding_docs.json")
WIKI_PATH = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts")
OUTPUT_PATH = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\operator_param_schemas.json")

# Known repeated parameter patterns
REPEATED_PATTERNS = {
    # Constant CHOP: const0name/value through const39name/value
    'Constant_CHOP': {
        'const{n}name': {'range': (0, 39), 'type': 'string', 'default': ''},
        'const{n}value': {'range': (0, 39), 'type': 'float', 'default': 0.0},
    },
    # Pattern CHOP: similar patterns
    'Pattern_CHOP': {
        'chan{n}name': {'range': (0, 9), 'type': 'string', 'default': ''},
    },
    # Many operators have name0-9, value0-9 patterns
    '_common_channel_patterns': {
        'name{n}': {'range': (0, 9), 'type': 'string', 'default': ''},
        'value{n}': {'range': (0, 9), 'type': 'float', 'default': 0.0},
    },
    # GLSL operators
    'GLSL_TOP': {
        'uniname{n}': {'range': (0, 15), 'type': 'string', 'default': ''},
        'value{n}': {'range': (0, 15), 'type': 'float', 'default': 0.0},
    },
    'GLSL_MAT': {
        'uniname{n}': {'range': (0, 15), 'type': 'string', 'default': ''},
        'value{n}x': {'range': (0, 15), 'type': 'float', 'default': 0.0},
        'value{n}y': {'range': (0, 15), 'type': 'float', 'default': 0.0},
        'value{n}z': {'range': (0, 15), 'type': 'float', 'default': 0.0},
        'value{n}w': {'range': (0, 15), 'type': 'float', 'default': 0.0},
    },
    # Geometry COMP instancing
    'Geometry_COMP': {
        'instance{n}op': {'range': (0, 9), 'type': 'string', 'default': ''},
        'instance{n}tx': {'range': (0, 9), 'type': 'string', 'default': ''},
        'instance{n}ty': {'range': (0, 9), 'type': 'string', 'default': ''},
        'instance{n}tz': {'range': (0, 9), 'type': 'string', 'default': ''},
    },
}

# Parameter type inference from descriptions
TYPE_KEYWORDS = {
    'float': ['value', 'position', 'scale', 'rotate', 'angle', 'size', 'width', 'height',
              'radius', 'offset', 'amount', 'rate', 'speed', 'time', 'alpha', 'brightness'],
    'int': ['index', 'count', 'number', 'resolution', 'samples', 'frame', 'step', 'limit'],
    'string': ['name', 'file', 'path', 'text', 'label', 'url', 'expression', 'pattern'],
    'toggle': ['enable', 'active', 'on', 'off', 'bypass', 'lock', 'show', 'hide', 'use'],
    'menu': ['type', 'mode', 'method', 'format', 'unit', 'extend', 'justify', 'align'],
    'pulse': ['reset', 'pulse', 'trigger', 'snapshot', 'snap', 'cook', 'clear'],
}


def infer_param_type(param_code: str, description: str = '') -> str:
    """Infer parameter type from code and description."""
    code_lower = param_code.lower()
    desc_lower = description.lower()

    # Check pulse first (often named specifically)
    for keyword in TYPE_KEYWORDS['pulse']:
        if keyword in code_lower:
            return 'pulse'

    # Check toggle
    for keyword in TYPE_KEYWORDS['toggle']:
        if keyword in code_lower or f'turn {keyword}' in desc_lower:
            return 'toggle'

    # Check menu
    for keyword in TYPE_KEYWORDS['menu']:
        if keyword in code_lower and 'select' in desc_lower:
            return 'menu'

    # Check string
    for keyword in TYPE_KEYWORDS['string']:
        if keyword in code_lower:
            return 'string'

    # Check int
    for keyword in TYPE_KEYWORDS['int']:
        if keyword in code_lower:
            return 'int'

    # Default to float for numeric-like params
    for keyword in TYPE_KEYWORDS['float']:
        if keyword in code_lower:
            return 'float'

    return 'float'  # Default


def extract_default_from_description(description: str) -> any:
    """Try to extract default value from description."""
    # Look for patterns like "default is X" or "defaults to X"
    patterns = [
        r'default[s]?\s+(?:is|to|:)\s+(\d+\.?\d*)',
        r'default[s]?\s+(?:is|to|:)\s+"([^"]+)"',
        r'default[s]?\s+(?:is|to|:)\s+(\w+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, description.lower())
        if match:
            val = match.group(1)
            try:
                if '.' in val:
                    return float(val)
                return int(val)
            except ValueError:
                return val

    return None


def load_embedding_docs():
    """Load all embedding documents."""
    with open(EMBEDDING_DOCS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('documents', [])


def extract_operators_and_params(docs):
    """Extract all operators and their parameters from embedding docs."""
    operators = defaultdict(lambda: {'parameters': {}, 'family': '', 'python_class': ''})

    for doc in docs:
        doc_id = doc.get('id', '')
        doc_type = doc.get('type', '')
        text = doc.get('text', '')
        family = doc.get('family', '')

        # Extract operator info
        if doc_type == 'operator':
            # Parse operator name from id like "op_Blur_TOP"
            if doc_id.startswith('op_'):
                op_name = doc_id[3:]  # Remove 'op_' prefix
                operators[op_name]['family'] = family
                # Extract python class if mentioned
                if 'Python class:' in text:
                    match = re.search(r'Python class:\s*(\w+)', text)
                    if match:
                        operators[op_name]['python_class'] = match.group(1)

        # Extract parameter info
        elif doc_type == 'parameter':
            # Parse from id like "param_Blur_TOP_size"
            if doc_id.startswith('param_'):
                parts = doc_id[6:].rsplit('_', 1)  # Split off param name
                if len(parts) == 2:
                    op_name = parts[0]
                    param_code = parts[1]

                    # Get description (text after "parameter:")
                    description = ''
                    if ' parameter:' in text:
                        description = text.split(' parameter:', 1)[1].strip()

                    param_type = infer_param_type(param_code, description)
                    default = extract_default_from_description(description)

                    operators[op_name]['parameters'][param_code] = {
                        'type': param_type,
                        'default': default,
                        'description': description[:200] if description else ''
                    }
                    operators[op_name]['family'] = family

    return dict(operators)


def expand_repeated_params(operators):
    """Expand repeated parameter patterns (name0-9, const0-39, etc.)."""

    for op_name, patterns in REPEATED_PATTERNS.items():
        if op_name == '_common_channel_patterns':
            continue  # Skip common patterns placeholder

        if op_name in operators:
            for pattern, config in patterns.items():
                start, end = config['range']
                param_type = config['type']
                default = config['default']

                for n in range(start, end + 1):
                    param_name = pattern.replace('{n}', str(n))
                    if param_name not in operators[op_name]['parameters']:
                        operators[op_name]['parameters'][param_name] = {
                            'type': param_type,
                            'default': default,
                            'description': f'Repeated slot {n}',
                            'repeated': True,
                            'slot_index': n
                        }

    return operators


def add_common_chop_params(operators):
    """Add common CHOP parameters that most CHOPs share."""
    common_chop_params = {
        'start': {'type': 'float', 'default': 0, 'description': 'Start of interval'},
        'startunit': {'type': 'menu', 'default': 0, 'description': 'Start unit (samples/frames/seconds)'},
        'end': {'type': 'float', 'default': 0, 'description': 'End of interval'},
        'endunit': {'type': 'menu', 'default': 0, 'description': 'End unit'},
        'rate': {'type': 'float', 'default': 60, 'description': 'Sample rate'},
        'left': {'type': 'menu', 'default': 0, 'description': 'Left extend condition'},
        'right': {'type': 'menu', 'default': 0, 'description': 'Right extend condition'},
        'defval': {'type': 'float', 'default': 0, 'description': 'Default value for extend'},
    }

    for op_name, op_data in operators.items():
        if op_data.get('family') == 'CHOP':
            for param, config in common_chop_params.items():
                if param not in op_data['parameters']:
                    op_data['parameters'][param] = config.copy()

    return operators


def add_common_top_params(operators):
    """Add common TOP parameters."""
    common_top_params = {
        'resolutionw': {'type': 'int', 'default': 256, 'description': 'Output resolution width'},
        'resolutionh': {'type': 'int', 'default': 256, 'description': 'Output resolution height'},
        'outputresolution': {'type': 'menu', 'default': 9, 'description': 'Resolution mode'},
        'format': {'type': 'menu', 'default': 0, 'description': 'Pixel format'},
    }

    for op_name, op_data in operators.items():
        if op_data.get('family') == 'TOP':
            for param, config in common_top_params.items():
                if param not in op_data['parameters']:
                    op_data['parameters'][param] = config.copy()

    return operators


def generate_summary_stats(operators):
    """Generate summary statistics."""
    stats = {
        'total_operators': len(operators),
        'total_parameters': sum(len(op['parameters']) for op in operators.values()),
        'by_family': defaultdict(int),
        'operators_with_repeated_params': 0,
    }

    for op_name, op_data in operators.items():
        family = op_data.get('family', 'unknown')
        stats['by_family'][family] += 1

        if any(p.get('repeated') for p in op_data['parameters'].values()):
            stats['operators_with_repeated_params'] += 1

    stats['by_family'] = dict(stats['by_family'])
    return stats


def main():
    print("=" * 70)
    print("Parameter Schema Extraction for TouchDesigner Operators")
    print("=" * 70)

    print("\nLoading embedding documents...")
    docs = load_embedding_docs()
    print(f"  Loaded {len(docs)} documents")

    print("\nExtracting operators and parameters...")
    operators = extract_operators_and_params(docs)
    print(f"  Found {len(operators)} operators")

    print("\nExpanding repeated parameter patterns...")
    operators = expand_repeated_params(operators)

    print("Adding common CHOP parameters...")
    operators = add_common_chop_params(operators)

    print("Adding common TOP parameters...")
    operators = add_common_top_params(operators)

    # Count total params after expansion
    total_params = sum(len(op['parameters']) for op in operators.values())
    print(f"  Total parameters after expansion: {total_params}")

    # Generate stats
    stats = generate_summary_stats(operators)

    # Build output
    output = {
        'version': '1.0',
        'source': 'ChromaDB knowledge base + pattern expansion',
        'statistics': stats,
        'operators': operators
    }

    # Save
    print(f"\nSaving to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    file_size = OUTPUT_PATH.stat().st_size / 1024
    print(f"  Saved ({file_size:.1f} KB)")

    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total operators: {stats['total_operators']}")
    print(f"Total parameters: {stats['total_parameters']}")
    print(f"Operators with repeated params: {stats['operators_with_repeated_params']}")
    print("\nBy family:")
    for family, count in sorted(stats['by_family'].items(), key=lambda x: -x[1]):
        print(f"  {family}: {count}")

    # Show Constant CHOP as example
    if 'Constant_CHOP' in operators:
        print("\n" + "=" * 70)
        print("EXAMPLE: Constant_CHOP")
        print("=" * 70)
        const_params = operators['Constant_CHOP']['parameters']
        print(f"Total parameters: {len(const_params)}")
        print("\nFirst 10 parameters:")
        for i, (name, config) in enumerate(list(const_params.items())[:10]):
            print(f"  {name}: type={config['type']}, default={config['default']}")


if __name__ == '__main__':
    main()

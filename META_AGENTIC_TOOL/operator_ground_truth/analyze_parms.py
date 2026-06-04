#!/usr/bin/env python3
"""
Analyze Expanded .parm Files
=============================
Parses all expanded .parm files to document the format completely.

Outputs:
- parm_format_analysis.json: Complete analysis of .parm format
- mode_numbers.json: All discovered mode numbers and their meanings
- param_catalog.json: All parameters per operator type

Usage:
  python analyze_parms.py
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Tuple


EXPANDED_DIR = Path(__file__).parent / "tox_expanded"
OUTPUT_DIR = Path(__file__).parent


def parse_parm_file(parm_path: Path) -> List[Dict[str, Any]]:
    """
    Parse a .parm file and extract all parameters.

    Returns list of dicts with:
        - name: parameter name
        - mode: mode number (0=constant, 16=expression, etc.)
        - value: the value (could be numeric or string)
        - expression: expression if mode indicates expression
        - has_expression: bool
    """
    params = []

    try:
        content = parm_path.read_text(encoding='utf-8')
    except Exception as e:
        return params

    lines = content.strip().split('\n')

    for line in lines:
        line = line.strip()

        # Skip sentinel lines
        if line == '?' or not line:
            continue

        # Parse: param_name mode value [expression]
        # Split by whitespace, max 4 parts
        parts = line.split(None, 3)

        if len(parts) < 3:
            continue

        param_name = parts[0]
        try:
            mode = int(parts[1])
        except ValueError:
            # Some files might have different format
            continue

        value = parts[2]
        expression = parts[3] if len(parts) > 3 else None

        # Try to convert value to number
        try:
            if '.' in value:
                value = float(value)
            else:
                value = int(value)
        except ValueError:
            pass  # Keep as string

        params.append({
            'name': param_name,
            'mode': mode,
            'value': value,
            'expression': expression,
            'has_expression': expression is not None
        })

    return params


def analyze_all_parms():
    """Analyze all expanded .parm files."""

    print("=" * 70)
    print("Analyzing Expanded .parm Files")
    print("=" * 70)

    # Find all .parm files
    parm_files = list(EXPANDED_DIR.glob("**/*.parm"))
    print(f"\nFound {len(parm_files)} .parm files")

    # Analysis containers
    all_modes = defaultdict(list)  # mode -> list of (op_type, param_name, value)
    params_by_operator = defaultdict(dict)  # op_type -> {param_name: details}
    mode_counts = defaultdict(int)  # mode -> count

    # Track statistics
    stats = {
        'total_parm_files': 0,
        'total_parameters': 0,
        'parameters_with_expressions': 0,
        'unique_param_names': set(),
        'operators_analyzed': set()
    }

    # Process each .parm file
    for idx, parm_path in enumerate(parm_files, 1):
        if idx % 100 == 0:
            print(f"  Processing: {idx}/{len(parm_files)}")

        # Extract operator type from path
        # e.g., CHOP_Constant_CHOP.tox.dir/sample_Constant_CHOP/op_perturbed.parm
        # We want: Constant_CHOP
        parts = str(parm_path).split('\\')
        tox_dir_name = None
        for part in parts:
            if part.endswith('.tox.dir'):
                tox_dir_name = part.replace('.tox.dir', '')
                break

        if not tox_dir_name:
            continue

        # Extract family and op type: CHOP_Constant_CHOP -> (CHOP, Constant_CHOP)
        match = re.match(r'^(CHOP|TOP|SOP|DAT|COMP|MAT|POP)_(.+)$', tox_dir_name)
        if not match:
            continue

        family = match.group(1)
        op_type = match.group(2)
        full_type = f"{family}:{op_type}"

        # Only analyze perturbed params (has all non-default values)
        if 'op_perturbed.parm' not in str(parm_path):
            continue

        stats['total_parm_files'] += 1
        stats['operators_analyzed'].add(full_type)

        # Parse parameters
        params = parse_parm_file(parm_path)

        for param in params:
            stats['total_parameters'] += 1
            stats['unique_param_names'].add(param['name'])
            mode_counts[param['mode']] += 1

            if param['has_expression']:
                stats['parameters_with_expressions'] += 1

            # Track mode examples
            all_modes[param['mode']].append({
                'op_type': full_type,
                'param': param['name'],
                'value': param['value'],
                'expression': param['expression']
            })

            # Track params by operator
            if param['name'] not in params_by_operator[full_type]:
                params_by_operator[full_type][param['name']] = {
                    'modes_seen': set(),
                    'values_seen': [],
                    'has_expression': False
                }

            params_by_operator[full_type][param['name']]['modes_seen'].add(param['mode'])
            params_by_operator[full_type][param['name']]['values_seen'].append(param['value'])
            if param['has_expression']:
                params_by_operator[full_type][param['name']]['has_expression'] = True

    # Convert sets to lists for JSON serialization
    stats['unique_param_names'] = list(stats['unique_param_names'])
    stats['operators_analyzed'] = list(stats['operators_analyzed'])

    for op_type in params_by_operator:
        for param_name in params_by_operator[op_type]:
            params_by_operator[op_type][param_name]['modes_seen'] = list(
                params_by_operator[op_type][param_name]['modes_seen']
            )
            # Limit values to first 3 examples
            params_by_operator[op_type][param_name]['values_seen'] = \
                params_by_operator[op_type][param_name]['values_seen'][:3]

    # Analyze modes
    print("\n" + "=" * 70)
    print("Mode Number Analysis")
    print("=" * 70)

    mode_analysis = {}
    for mode, examples in sorted(all_modes.items()):
        print(f"\nMode {mode}: {len(examples)} occurrences")

        # Get sample examples
        samples = examples[:5]
        for sample in samples:
            expr_str = f" expr={sample['expression']}" if sample['expression'] else ""
            print(f"  {sample['op_type']}.{sample['param']} = {sample['value']}{expr_str}")

        # Determine mode meaning based on examples
        has_expressions = any(e['expression'] for e in examples)

        if mode == 0:
            meaning = "constant"
        elif has_expressions:
            meaning = "expression"
        else:
            meaning = "unknown"

        mode_analysis[mode] = {
            'count': len(examples),
            'meaning': meaning,
            'has_expressions': has_expressions,
            'examples': [
                {
                    'op': e['op_type'],
                    'param': e['param'],
                    'value': e['value'],
                    'expression': e['expression']
                }
                for e in examples[:10]
            ]
        }

    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Total .parm files analyzed: {stats['total_parm_files']}")
    print(f"Total parameters: {stats['total_parameters']}")
    print(f"Unique parameter names: {len(stats['unique_param_names'])}")
    print(f"Operators analyzed: {len(stats['operators_analyzed'])}")
    print(f"Parameters with expressions: {stats['parameters_with_expressions']}")
    print(f"\nMode counts:")
    for mode, count in sorted(mode_counts.items()):
        meaning = mode_analysis.get(mode, {}).get('meaning', 'unknown')
        print(f"  Mode {mode}: {count} ({meaning})")

    # Save outputs
    print("\n" + "=" * 70)
    print("Saving Outputs")
    print("=" * 70)

    # 1. Mode analysis
    modes_path = OUTPUT_DIR / "mode_numbers.json"
    with open(modes_path, 'w') as f:
        json.dump(mode_analysis, f, indent=2, default=str)
    print(f"[OK] {modes_path}")

    # 2. Parameter catalog (limited for size)
    catalog_path = OUTPUT_DIR / "param_catalog.json"
    with open(catalog_path, 'w') as f:
        json.dump(dict(params_by_operator), f, indent=2, default=str)
    print(f"[OK] {catalog_path}")

    # 3. Complete analysis
    analysis = {
        'statistics': stats,
        'mode_counts': dict(mode_counts),
        'mode_analysis': mode_analysis,
        'parm_format': {
            'description': 'TouchDesigner .parm file format',
            'structure': [
                '?',
                '{param_name} {mode} {value} [expression]',
                '...',
                '?'
            ],
            'modes': {
                '0': 'constant - static value',
                '16': 'expression - dynamic python/tscript expression',
            },
            'notes': [
                'Parameters are only written when value differs from default',
                'Expression mode includes both constant fallback and expression',
                'Multi-component params share same name with different indices',
                'Lines starting with ? are sentinels/delimiters'
            ]
        }
    }

    analysis_path = OUTPUT_DIR / "parm_format_analysis.json"
    with open(analysis_path, 'w') as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"[OK] {analysis_path}")

    return analysis


if __name__ == '__main__':
    analyze_all_parms()

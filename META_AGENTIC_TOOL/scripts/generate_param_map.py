#!/usr/bin/env python3
"""
Generate correct parameter mappings from KB data.
This script analyzes td_universal_parsed.json to create accurate
display_name -> code mappings for all operators.

Author: TERRY (Tool Manager)
Date: 2024-12-23
Purpose: Fix BUG-001 by generating mappings from source of truth
"""

import json
import re
from pathlib import Path
from collections import defaultdict

# Paths
KB_PATH = Path(__file__).parent.parent / "data" / "wiki_docs" / "td_universal_parsed.json"
OUTPUT_PATH = Path(__file__).parent.parent / "meta_agentic" / "execution" / "generated_param_map.py"

def normalize_name(name: str) -> str:
    """Normalize a display name for matching."""
    # Remove numbers at end (e.g., "Brightness 1" -> "brightness")
    name = re.sub(r'\s*\d+$', '', name.lower())
    # Remove special chars and spaces
    name = re.sub(r'[^a-z0-9]', '', name)
    return name

def get_operator_short_name(op_name: str) -> str:
    """Get short operator name (e.g., 'LFO CHOP' -> 'lfo')."""
    # Remove family suffix
    name = re.sub(r'\s*(CHOP|TOP|SOP|DAT|COMP|MAT|POP)$', '', op_name, flags=re.IGNORECASE)
    # Normalize
    return name.lower().replace(' ', '_').replace('-', '_')

def load_kb():
    """Load the knowledge base."""
    with open(KB_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_parameters(kb_data):
    """Analyze all parameters to build mappings."""

    # Per-operator parameter mappings
    op_param_map = defaultdict(dict)

    # Global mapping (display_name_normalized -> code)
    global_map = {}

    # Track conflicts (same display_name, different codes)
    conflicts = defaultdict(set)

    # Statistics
    stats = {
        'total_operators': 0,
        'total_parameters': 0,
        'unique_display_names': set(),
        'operators_with_params': 0,
    }

    for operator in kb_data.get('operators', []):
        op_name = operator.get('name', '')
        op_short = get_operator_short_name(op_name)
        family = operator.get('family', '')
        params = operator.get('parameters', [])

        stats['total_operators'] += 1

        if params:
            stats['operators_with_params'] += 1

        for param in params:
            code = param.get('code', '')
            display_name = param.get('display_name', '')

            if not code or not display_name:
                continue

            stats['total_parameters'] += 1

            # Normalize display name
            norm_name = normalize_name(display_name)
            stats['unique_display_names'].add(norm_name)

            # Add to operator-specific map
            op_key = f"{op_short}_{family.lower()}" if family else op_short

            # Map both the normalized name and the code itself
            op_param_map[op_key][norm_name] = code
            op_param_map[op_key][code.lower()] = code  # identity mapping

            # Track global mapping and conflicts
            if norm_name in global_map:
                if global_map[norm_name] != code:
                    conflicts[norm_name].add(global_map[norm_name])
                    conflicts[norm_name].add(code)
            else:
                global_map[norm_name] = code

    stats['unique_display_names'] = len(stats['unique_display_names'])

    return op_param_map, global_map, conflicts, stats

def validate_current_map():
    """Validate the current PARAM_NAME_MAP against KB."""

    # Current wrong mappings (from toe_builder_bridge.py)
    CURRENT_MAP = {
        "amplitude": "amp",
        "exponent": "exp",
        "harmonics": "harmon",
        "roughness": "rough",
        "brightness": "bright",  # WRONG - should be brightness1
        "gamma": "gamma1",
        "filtersize": "filterwidth",
        "size": "filterwidth",
        "displaceamplitude": "displaceweight",
        "strength": "bloomstrength",
        "threshold": "bloomthresh",
        "cutofffreq": "cutoff",
        "highfreq": "cutoffhigh",
        "filtertype": "filter",
        "maxparticles": "maxparts",
        "emitrate": "birthrate",
        "rendersize": "pointsize",
        "colorr": "cr",
        "colorg": "cg",
        "colorb": "cb",
        "alpha": "ca",
        "forcetype": "type",
        "type": "type",
        "operand": "operand",
        "opacity": "opacity",
        "numchannels": "channels",
        "device": "device",
        "targetop": "top",
        "colorlookup": "method",
        "preset": "preset",
        "name0": "const0name",
        "value0": "const0value",
        "name1": "const1name",
        "value1": "const1value",
        "name2": "const2name",
        "value2": "const2value",
        "name3": "const3name",
        "value3": "const3value",
        "birthrate": "birthrate",
        "life": "life",
        "lifedur": "lifevar",
        "inherit": "inheritvel",
        "forcex": "forcex",
        "forcey": "forcey",
        "forcez": "forcez",
        "points": "points",
        "miny": "miny",
        "minx": "minx",
        "minz": "minz",
        "maxy": "maxy",
        "maxx": "maxx",
        "maxz": "maxz",
        "rad": "rad1",
        "channels": "channelname",
        "freq": "freq",  # WRONG for LFO - should be frequency
        "satmult": "satmult",
        "valmult": "valmult",
        "huemult": "huemult",
        "hueoffset": "hueoff",
        "satoffset": "satoff",
        "valoffset": "valoff",
    }

    return CURRENT_MAP

def generate_output(op_param_map, global_map, conflicts):
    """Generate the Python code for parameter mapping."""

    lines = [
        '"""',
        'Auto-generated parameter mappings from TouchDesigner KB.',
        '',
        'Generated by: scripts/generate_param_map.py',
        'Source: data/wiki_docs/td_universal_parsed.json',
        '',
        'DO NOT EDIT MANUALLY - regenerate from KB instead.',
        '"""',
        '',
        '# Operator-specific parameter mappings',
        '# Key: operator_family (e.g., "lfo_chop", "level_top")',
        '# Value: dict of user_name -> td_internal_name',
        'OP_PARAM_MAP = {',
    ]

    # Sort operators for consistent output
    for op_key in sorted(op_param_map.keys()):
        params = op_param_map[op_key]
        if params:
            lines.append(f'    "{op_key}": {{')
            for user_name, td_name in sorted(params.items()):
                if user_name != td_name.lower():  # Only include non-identity mappings
                    lines.append(f'        "{user_name}": "{td_name}",')
            lines.append('    },')

    lines.append('}')
    lines.append('')

    # Add conflict documentation
    if conflicts:
        lines.append('# CONFLICTS: These display names map to different codes in different operators')
        lines.append('# Use OP_PARAM_MAP for operator-specific resolution')
        lines.append('PARAM_CONFLICTS = {')
        for name, codes in sorted(conflicts.items()):
            lines.append(f'    "{name}": {sorted(codes)},')
        lines.append('}')
        lines.append('')

    # Add helper function
    lines.extend([
        '',
        'def get_td_param_name(op_type: str, op_family: str, user_param: str) -> str:',
        '    """',
        '    Get the TD internal parameter name for a user-provided parameter name.',
        '    ',
        '    Args:',
        '        op_type: The operator type (e.g., "lfo", "level", "noise")',
        '        op_family: The operator family (e.g., "CHOP", "TOP")',
        '        user_param: The user-provided parameter name',
        '    ',
        '    Returns:',
        '        The TD internal parameter name',
        '    """',
        '    # Build operator key',
        '    op_key = f"{op_type.lower()}_{op_family.lower()}"',
        '    param_lower = user_param.lower()',
        '    ',
        '    # Check operator-specific map first',
        '    if op_key in OP_PARAM_MAP:',
        '        op_map = OP_PARAM_MAP[op_key]',
        '        if param_lower in op_map:',
        '            return op_map[param_lower]',
        '    ',
        '    # Return original if no mapping found',
        '    return user_param',
        '',
    ])

    return '\n'.join(lines)

def main():
    print("Loading KB data...")
    kb_data = load_kb()

    print("Analyzing parameters...")
    op_param_map, global_map, conflicts, stats = analyze_parameters(kb_data)

    print(f"\nStatistics:")
    print(f"  Total operators: {stats['total_operators']}")
    print(f"  Total parameters: {stats['total_parameters']}")
    print(f"  Unique display names: {stats['unique_display_names']}")
    print(f"  Operators with params: {stats['operators_with_params']}")
    print(f"  Parameter conflicts: {len(conflicts)}")

    # Show key conflicts
    print(f"\nKey conflicts (same name, different codes):")
    for name, codes in sorted(conflicts.items())[:20]:
        print(f"  '{name}' -> {sorted(codes)}")

    # Check specific problematic parameters
    print("\n=== VALIDATING AGAINST CURRENT PARAM_NAME_MAP ===")

    # Find specific operators
    lfo_params = op_param_map.get('lfo_chop', {})
    level_params = op_param_map.get('level_top', {})
    noise_top_params = op_param_map.get('noise_top', {})
    noise_chop_params = op_param_map.get('noise_chop', {})

    print(f"\nLFO CHOP params: {dict(lfo_params)}")
    print(f"\nLevel TOP params: {dict(level_params)}")
    print(f"\nNoise TOP params (sample): {dict(list(noise_top_params.items())[:10])}")
    print(f"\nNoise CHOP params (sample): {dict(list(noise_chop_params.items())[:10])}")

    # Generate output
    print("\nGenerating output...")
    output = generate_output(op_param_map, global_map, conflicts)

    # Write to file
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(output)

    print(f"\nOutput written to: {OUTPUT_PATH}")

    # Also print key findings for BUG-001
    print("\n" + "="*60)
    print("BUG-001 VALIDATION RESULTS")
    print("="*60)

    issues = []

    # Check brightness
    if 'brightness' in level_params:
        expected = level_params.get('brightness')
        current = 'bright'
        if expected != current:
            issues.append(f"Level TOP 'brightness': current='{current}', should be='{expected}'")

    # Check freq for LFO
    if 'frequency' in lfo_params or 'freq' in lfo_params:
        expected = lfo_params.get('frequency', lfo_params.get('freq'))
        current = 'freq'
        if expected and expected != current:
            issues.append(f"LFO CHOP 'freq': current='{current}', should be='{expected}'")

    # Check type for LFO
    if 'type' in lfo_params or 'wavetype' in lfo_params:
        expected = lfo_params.get('wavetype', lfo_params.get('type'))
        current = 'type'
        if expected and expected != current:
            issues.append(f"LFO CHOP 'type': current='{current}', should be='{expected}'")

    if issues:
        print("\nISSUES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nNo issues found in checked parameters.")

    return op_param_map, global_map, conflicts

if __name__ == "__main__":
    main()

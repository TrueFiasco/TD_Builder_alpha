"""
Parameter Name Resolver for TouchDesigner Builder.

This module resolves user-friendly parameter names to TD internal names
using the KB data as source of truth.

Author: TERRY (Tool Manager)
Date: 2024-12-23
Purpose: Fix BUG-001 by auto-generating correct param mappings from KB
"""

import json
import re
from pathlib import Path
from typing import Optional, Dict

# Path to KB data.
#
# Resolution is delegated to the repo-level paths module — single source of
# truth for the alpha → enriched → legacy fallback chain. See paths.py at the
# repo root. The schemas across all three candidates are identical at the
# top level ({metadata, operators, classes, concepts, errors}), so a switch
# among them is path-only — no adapter needed.
import sys as _sys
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))
from paths import kb_operators_path as _kb_operators_path  # noqa: E402

KB_PATH = _kb_operators_path()

# Cache for loaded KB data
_kb_cache: Optional[Dict] = None
_param_cache: Dict[str, Dict[str, str]] = {}


def _load_kb() -> Dict:
    """Load the knowledge base data."""
    global _kb_cache
    if _kb_cache is None:
        with open(KB_PATH, 'r', encoding='utf-8') as f:
            _kb_cache = json.load(f)
    return _kb_cache


def _get_operator_short_name(op_name: str) -> str:
    """Get short operator name (e.g., 'LFO CHOP' -> 'lfo')."""
    name = re.sub(r'\s*(CHOP|TOP|SOP|DAT|COMP|MAT|POP)$', '', op_name, flags=re.IGNORECASE)
    return name.lower().replace(' ', '_').replace('-', '_')


def _build_param_map(op_name: str, family: str) -> Dict[str, str]:
    """Build parameter mapping for a specific operator."""
    kb = _load_kb()

    param_map = {}

    for operator in kb.get('operators', []):
        if operator.get('name', '').lower() == op_name.lower():
            for param in operator.get('parameters', []):
                code = param.get('code', '')
                display_name = param.get('display_name', '')

                if not code:
                    continue

                # Add identity mapping (code -> code)
                param_map[code.lower()] = code

                if display_name:
                    # Add display_name -> code (normalized)
                    norm = display_name.lower().replace(' ', '').replace('-', '').replace('_', '')
                    param_map[norm] = code

                    # Also add without trailing numbers for user convenience
                    # BUT prefer "1" suffix versions for primary parameters
                    norm_no_num = re.sub(r'\d+$', '', norm)
                    if norm_no_num and norm_no_num not in param_map:
                        # Only add if not already mapped (so "brightness1" gets priority over "brightness2")
                        param_map[norm_no_num] = code

            break

    return param_map


def _get_op_key(op_type: str, family: str) -> str:
    """Get cache key for operator."""
    return f"{op_type.lower()}_{family.lower()}"


# ============================================================================
# USER-FRIENDLY ALIASES
# These are explicit overrides for common user inputs that don't match
# display names exactly. Manually curated based on common usage patterns.
# ============================================================================

USER_FRIENDLY_ALIASES = {
    # LFO CHOP - common abbreviations
    "lfo_chop": {
        "freq": "frequency",
        "amp": "amp",  # already correct
        "type": "wavetype",
    },

    # Level TOP - users say "brightness" meaning brightness1 (Pre page)
    "level_top": {
        "brightness": "brightness1",  # Primary brightness (Pre page)
        "gamma": "gamma1",  # Primary gamma (Pre page)
        # brightness2/gamma2 are on Post page, less commonly used
    },

    # Noise TOP/CHOP - common abbreviations
    "noise_top": {
        "amp": "amp",
        "amplitude": "amp",
        "harmonics": "harmon",
        "roughness": "rough",
        "exponent": "exp",
    },
    "noise_chop": {
        "amp": "amp",
        "amplitude": "amp",
        "harmonics": "harmon",
        "roughness": "rough",
        "exponent": "exp",
    },

    # Blur TOP
    "blur_top": {
        "size": "filterwidth",
        "filtersize": "filterwidth",
    },

    # Transform TOP
    "transform_top": {
        "scale": "sx",  # When user says "scale", they usually mean uniform scale
        "scalex": "sx",
        "scaley": "sy",
        "translatex": "tx",
        "translatey": "ty",
        "rotatex": "rx",
        "rotatey": "ry",
        "rotatez": "rz",
    },

    # Composite TOP
    "composite_top": {
        "operation": "operand",
        "op": "operand",
    },

    # Constant CHOP
    "constant_chop": {
        "name0": "const0name",
        "value0": "const0value",
        "name1": "const1name",
        "value1": "const1value",
        "name2": "const2name",
        "value2": "const2value",
        "name3": "const3name",
        "value3": "const3value",
    },

    # Audio Device In CHOP
    "audio_device_in_chop": {
        "numchans": "channels",
        "numchannels": "channels",
    },
    "audiodevin_chop": {
        "numchans": "channels",
        "numchannels": "channels",
    },

    # Trim CHOP - indexed parameters
    "trim_chop": {
        "source": "t0source",
        "start": "t0start",
        "end": "t0end",
    },

    # Math CHOP
    "math_chop": {
        "combine": "combine",
        "matchby": "matchby",
    },

    # Circle TOP
    "circle_top": {
        "radius": "radius1",
    },

    # CHOP To TOP
    "chopto_top": {
        "colormap": "colormap",
    },

    # Null TOP - reference parameter
    "null_top": {
        "top": "top",
        "input": "top",
    },

    # Select CHOP - reference parameter
    "select_chop": {
        "chop": "chop",
        "input": "chop",
    },

    # Feedback TOP
    "feedback_top": {
        "targetop": "top",
        "target": "top",
    },

    # Kaleidoscope TOP
    "kaleidoscope_top": {
        "numcopies": "copies",
        "copies": "copies",
    },

    # HSV Adjust TOP
    "hsvadjust_top": {
        "hueoffset": "hueoff",
        "satoffset": "satoff",
        "valoffset": "valoff",
    },

    # Displace TOP
    "displace_top": {
        "displaceamplitude": "displaceweight",
        "amplitude": "displaceweight",
    },

    # Bloom TOP
    "bloom_top": {
        "strength": "bloomstrength",
        "threshold": "bloomthresh",
    },
}


def resolve_param_name(op_type: str, op_family: str, user_param: str) -> str:
    """
    Resolve a user-provided parameter name to TD internal name.

    This function uses multiple strategies:
    1. Check user-friendly aliases (explicit overrides)
    2. Check KB-derived mappings (display_name -> code)
    3. Return original if no mapping found

    Args:
        op_type: Operator type (e.g., "lfo", "level", "noise")
        op_family: Operator family (e.g., "CHOP", "TOP", "SOP")
        user_param: User-provided parameter name

    Returns:
        TD internal parameter name

    Examples:
        >>> resolve_param_name("lfo", "CHOP", "freq")
        'frequency'
        >>> resolve_param_name("level", "TOP", "brightness")
        'brightness1'
        >>> resolve_param_name("noise", "TOP", "amplitude")
        'amp'
    """
    op_key = _get_op_key(op_type, op_family)
    param_lower = user_param.lower().strip()

    # 1. Check user-friendly aliases first (highest priority)
    if op_key in USER_FRIENDLY_ALIASES:
        aliases = USER_FRIENDLY_ALIASES[op_key]
        if param_lower in aliases:
            return aliases[param_lower]

    # 2. Check if it's already a valid TD param name (identity)
    # Build KB param map if not cached
    if op_key not in _param_cache:
        # Try to find the operator in KB
        op_name = f"{op_type} {op_family}".replace('_', ' ').title()
        _param_cache[op_key] = _build_param_map(op_name, op_family)

    kb_map = _param_cache.get(op_key, {})

    # Check if param is in KB mappings
    if param_lower in kb_map:
        return kb_map[param_lower]

    # 3. Return original if no mapping found
    return user_param


def get_all_aliases(op_type: str, op_family: str) -> Dict[str, str]:
    """
    Get all parameter aliases for an operator.

    Returns combined dict of user-friendly aliases and KB-derived mappings.
    """
    op_key = _get_op_key(op_type, op_family)

    result = {}

    # Add KB mappings
    if op_key not in _param_cache:
        op_name = f"{op_type} {op_family}".replace('_', ' ').title()
        _param_cache[op_key] = _build_param_map(op_name, op_family)

    result.update(_param_cache.get(op_key, {}))

    # Add user-friendly aliases (override KB)
    if op_key in USER_FRIENDLY_ALIASES:
        result.update(USER_FRIENDLY_ALIASES[op_key])

    return result


# ============================================================================
# MENU VALUE MAPPINGS
# For menu/enum parameters, TD expects string values not integers
# ============================================================================

MENU_VALUE_MAP = {
    # Composite operand - ONLY string aliases, integers pass through directly to TD
    # TD menu order: 0=add, 1=atop, 2=average, ... (integers work as-is)
    # BUG-005 FIX: Removed incorrect integer mappings that corrupted values
    "operand": {
        # String aliases only - integers pass through
        "add": "add",
        "over": "over",
        "screen": "screen",
        "multiply": "mult",
        "mult": "mult",
        "subtract": "subtract",
        "difference": "diff",
        "diff": "diff",
        "atop": "atop",
        "inside": "inside",
        "outside": "outside",
        "max": "max",
        "min": "min",
        "average": "average",
        "xor": "xor",
        "under": "under",
        "softlight": "softlight",
        "soft_light": "softlight",
    },

    # LFO wavetype
    "wavetype": {
        0: "sin",
        1: "triangle",
        2: "square",
        3: "ramp",
        4: "pulse",
        "sin": "sin",
        "sine": "sin",
        "triangle": "triangle",
        "square": "square",
        "ramp": "ramp",
        "pulse": "pulse",
    },

    # Noise type
    "type": {
        "perlin": "perlin2d",
        "simplex": "simplex3d",
        "sparse": "sparse",
        "random": "random",
        "hermite": "hermite",
        "perlin2d": "perlin2d",
        "simplex3d": "simplex3d",
    },

    # Math CHOP combine
    "combine": {
        0: "off",
        1: "add",
        2: "subtract",
        3: "multiply",
        4: "divide",
        5: "average",
        6: "maximum",
        7: "minimum",
        "off": "off",
        "add": "add",
        "average": "average",
        "multiply": "multiply",
    },
}


def resolve_menu_value(param_name: str, value) -> str:
    """
    Resolve a menu parameter value to TD internal string.

    Args:
        param_name: Parameter name (e.g., "operand", "wavetype")
        value: User-provided value (int or string)

    Returns:
        TD internal menu value string
    """
    # Python booleans are TD toggle values, never menu indices: True -> "on",
    # False -> "off". Without this, str(value) yields "True"/"False", which fails
    # TD's toggle parse so the parameter silently reverts to its default. Handled
    # before the menu lookup so a bool never accidentally matches an int menu key
    # (False == 0, True == 1).
    if isinstance(value, bool):
        return "on" if value else "off"

    if param_name not in MENU_VALUE_MAP:
        return str(value)

    menu_map = MENU_VALUE_MAP[param_name]

    if value in menu_map:
        return menu_map[value]

    # Try lowercase string
    if isinstance(value, str) and value.lower() in menu_map:
        return menu_map[value.lower()]

    return str(value)


# ============================================================================
# TESTING / VALIDATION
# ============================================================================

def validate_known_issues():
    """Validate that known BUG-001 issues are fixed."""
    issues = []

    # Test LFO CHOP
    result = resolve_param_name("lfo", "CHOP", "freq")
    if result != "frequency":
        issues.append(f"LFO freq: expected 'frequency', got '{result}'")

    result = resolve_param_name("lfo", "CHOP", "type")
    if result != "wavetype":
        issues.append(f"LFO type: expected 'wavetype', got '{result}'")

    result = resolve_param_name("lfo", "CHOP", "amplitude")
    if result != "amp":
        issues.append(f"LFO amplitude: expected 'amp', got '{result}'")

    # Test Level TOP
    result = resolve_param_name("level", "TOP", "brightness")
    if result != "brightness1":
        issues.append(f"Level brightness: expected 'brightness1', got '{result}'")

    result = resolve_param_name("level", "TOP", "gamma")
    if result != "gamma1":
        issues.append(f"Level gamma: expected 'gamma1', got '{result}'")

    # Test Noise TOP
    result = resolve_param_name("noise", "TOP", "amplitude")
    if result != "amp":
        issues.append(f"Noise amplitude: expected 'amp', got '{result}'")

    result = resolve_param_name("noise", "TOP", "harmonics")
    if result != "harmon":
        issues.append(f"Noise harmonics: expected 'harmon', got '{result}'")

    return issues


if __name__ == "__main__":
    print("Validating parameter name resolution...")
    issues = validate_known_issues()

    if issues:
        print("\nISSUES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nAll validations passed!")

    # Show sample resolutions
    print("\nSample resolutions:")
    samples = [
        ("lfo", "CHOP", "freq"),
        ("lfo", "CHOP", "type"),
        ("lfo", "CHOP", "amplitude"),
        ("level", "TOP", "brightness"),
        ("level", "TOP", "gamma"),
        ("noise", "TOP", "amp"),
        ("transform", "TOP", "scale"),
        ("constant", "CHOP", "name0"),
    ]

    for op_type, family, param in samples:
        result = resolve_param_name(op_type, family, param)
        print(f"  {op_type}_{family.lower()}.{param} -> {result}")

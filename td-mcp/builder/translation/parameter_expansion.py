"""Parameter expansion utilities for vector and indexed parameters."""

from typing import Dict, List, Any, Tuple

# Vector parameter mappings (param_name -> component names)
VECTOR_PARAMS = {
    # 3-component vectors (XYZ)
    't': ['tx', 'ty', 'tz'],
    'r': ['rx', 'ry', 'rz'],
    's': ['sx', 'sy', 'sz'],
    'p': ['px', 'py', 'pz'],
    'pivot': ['pivotx', 'pivoty', 'pivotz'],
    'scale': ['sx', 'sy', 'sz'],
    'translate': ['tx', 'ty', 'tz'],
    'rotate': ['rx', 'ry', 'rz'],
    'center': ['centerx', 'centery', 'centerz'],
    'size': ['sizex', 'sizey', 'sizez'],
    # 4-component vectors (RGBA)
    'color': ['colorr', 'colorg', 'colorb', 'colora'],
    'rgb': ['colorr', 'colorg', 'colorb'],
    'rgba': ['colorr', 'colorg', 'colorb', 'colora'],
    'bgcolor': ['bgcolorr', 'bgcolorg', 'bgcolorb', 'bgcolora'],
    # 2-component vectors (UV, WH)
    'uv': ['u', 'v'],
    'offset': ['offsetx', 'offsety'],
}

# Indexed parameter mappings (param_name -> base_name for numbered expansion)
INDEXED_PARAMS = {
    'fromrange': 'fromrange',
    'torange': 'torange',
    'const': 'const',
    'fills': 'fills',
}


def expand_vector_params(param_name: str, values: List[Any]) -> List[Tuple[str, Any]]:
    """
    Expand a vector parameter into its components.

    Args:
        param_name: Parameter name (e.g., 't', 'color', 'scale')
        values: List of component values

    Returns:
        List of (component_name, value) tuples
    """
    result = []
    param_lower = param_name.lower()

    if param_lower not in VECTOR_PARAMS:
        return result

    component_names = VECTOR_PARAMS[param_lower]
    for i, comp_name in enumerate(component_names):
        if i < len(values):
            result.append((comp_name, values[i]))

    return result


def expand_indexed_params(param_name: str, values: List[Any]) -> List[Tuple[str, Any]]:
    """
    Expand an indexed parameter into numbered components.

    Args:
        param_name: Parameter name (e.g., 'fromrange', 'torange')
        values: List of values

    Returns:
        List of (indexed_name, value) tuples (e.g., [('fromrange1', 0), ('fromrange2', 1)])
    """
    result = []
    param_lower = param_name.lower()

    if param_lower not in INDEXED_PARAMS:
        return result

    base_name = INDEXED_PARAMS[param_lower]
    for i, val in enumerate(values):
        indexed_name = f"{base_name}{i+1}"
        result.append((indexed_name, val))

    return result


def is_vector_param(param_name: str) -> bool:
    """Check if parameter is a vector type."""
    return param_name.lower() in VECTOR_PARAMS


def is_indexed_param(param_name: str) -> bool:
    """Check if parameter is an indexed type."""
    return param_name.lower() in INDEXED_PARAMS

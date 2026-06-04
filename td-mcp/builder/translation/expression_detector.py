"""Expression detection utilities for TouchDesigner parameters."""

from typing import Optional

# Pattern substrings that indicate a TD Python expression
EXPRESSION_PATTERNS = [
    'op(',
    'me.',
    'parent.',
    'parent(',
    'mod.',
    'ext.',
    'iop.',
    'ipar.',
    'tdu.',
    'absTime',
    'me.time',
    "op('",
    'op("',
    "chop('",
    'chop("',
]


def is_expression(value: str) -> bool:
    """
    Check if a string value is a TouchDesigner Python expression.

    Args:
        value: The parameter value string

    Returns:
        True if the value contains expression patterns
    """
    if not isinstance(value, str):
        return False

    return any(pattern in value for pattern in EXPRESSION_PATTERNS)


def detect_expression_mode(value) -> tuple:
    """
    Detect if a value contains an expression and determine the TD mode.

    TD .parm file modes:
    - 0: Constant value
    - 17: CHOP expression (older style)
    - 49: Python expression

    Args:
        value: Parameter value (can be any type, dict, or string)

    Returns:
        Tuple of (mode, constant_value, expression_string)
        - mode: 0 for constant, 49 for Python expression
        - constant_value: The numeric/constant value
        - expression_string: The expression string (or None)
    """
    # Handle dict format: {"expr": "...", "value": ...} or {"expression": "..."}
    if isinstance(value, dict):
        expression = value.get("expr") or value.get("expression")
        if expression:
            constant_val = value.get("value", 0)
            return (49, constant_val, expression)
        else:
            return (0, value, None)

    # Handle string that looks like an expression
    if isinstance(value, str) and is_expression(value):
        return (49, 0, value)

    # Regular constant value
    return (0, value, None)


def format_param_line(param_name: str, value, expression: str = None) -> str:
    """
    Format a parameter line for TD .parm file.

    Args:
        param_name: TD parameter name
        value: Constant value
        expression: Optional expression string

    Returns:
        Formatted .parm file line
    """
    if expression:
        # Mode 49 = Python expression
        return f"{param_name} 49 {value} {expression}"
    else:
        # Mode 0 = constant
        return f"{param_name} 0 {value}"

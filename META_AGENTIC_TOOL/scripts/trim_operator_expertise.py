"""
Trim bloat from td_operators.yaml

Removes unused fields:
- frequency (on parameters)
- _last_updated, _updated_by, _confidence (on operators)
- Empty lists/dicts
- Verbose common_use_cases structures
"""

import yaml
from pathlib import Path


def trim_operator(op_data: dict) -> dict:
    """Trim bloat from a single operator entry."""
    trimmed = {}

    # Keep purpose (required)
    if "purpose" in op_data:
        trimmed["purpose"] = op_data["purpose"]

    # Simplify common_use_cases - keep only strings
    if "common_use_cases" in op_data and op_data["common_use_cases"]:
        use_cases = []
        for uc in op_data["common_use_cases"]:
            if isinstance(uc, str):
                use_cases.append(uc)
            elif isinstance(uc, dict) and "description" in uc:
                use_cases.append(uc["description"])
        if use_cases:
            trimmed["common_use_cases"] = use_cases

    # Trim parameter_patterns - keep only common_values, remove frequency
    if "parameter_patterns" in op_data and op_data["parameter_patterns"]:
        params = {}
        for param_name, param_data in op_data["parameter_patterns"].items():
            if isinstance(param_data, dict) and "common_values" in param_data:
                values = param_data["common_values"]
                if values:  # Only keep non-empty
                    params[param_name] = values  # Just the values list, not nested dict
        if params:
            trimmed["key_params"] = params  # Renamed for clarity

    # Keep common_chains if non-empty
    if "common_chains" in op_data and op_data["common_chains"]:
        trimmed["common_chains"] = op_data["common_chains"]

    # Keep gotchas if non-empty
    if "gotchas" in op_data and op_data["gotchas"]:
        trimmed["gotchas"] = op_data["gotchas"]

    # Skip: _last_updated, _updated_by, _confidence, frequency

    return trimmed


def trim_expertise(input_path: Path, output_path: Path):
    """Trim the full expertise file."""
    with open(input_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    # Keep metadata
    trimmed = {
        "schema_version": "1.1",  # Bump version
        "last_updated": data.get("last_updated", ""),
        "update_count": data.get("update_count", 0) + 1,
        "validated_against": data.get("validated_against", ""),
        "note": "Trimmed version - removed unused metadata fields"
    }

    # Trim operators
    operators = {}
    stats = {"total": 0, "kept": 0, "empty": 0}

    for family, ops in data.get("operators", {}).items():
        if not isinstance(ops, dict):
            continue

        family_ops = {}
        for op_name, op_data in ops.items():
            stats["total"] += 1
            if isinstance(op_data, dict):
                trimmed_op = trim_operator(op_data)
                if trimmed_op:  # Only keep non-empty
                    family_ops[op_name] = trimmed_op
                    stats["kept"] += 1
                else:
                    stats["empty"] += 1

        if family_ops:
            operators[family] = family_ops

    trimmed["operators"] = operators

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(trimmed, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return stats


def main():
    base = Path(__file__).parent.parent / "meta_agentic" / "expertise"
    input_path = base / "td_operators.yaml"
    output_path = base / "td_operators_trimmed.yaml"

    print(f"Input: {input_path}")
    print(f"Output: {output_path}")

    # Get original size
    orig_size = input_path.stat().st_size
    print(f"\nOriginal size: {orig_size:,} bytes ({orig_size / 1024:.1f} KB)")

    # Trim
    stats = trim_expertise(input_path, output_path)

    # Get new size
    new_size = output_path.stat().st_size
    reduction = (1 - new_size / orig_size) * 100

    print(f"Trimmed size:  {new_size:,} bytes ({new_size / 1024:.1f} KB)")
    print(f"Reduction:     {reduction:.1f}%")
    print(f"\nOperators: {stats['total']} total, {stats['kept']} kept, {stats['empty']} empty removed")


if __name__ == "__main__":
    main()

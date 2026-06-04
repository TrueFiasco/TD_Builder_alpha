#!/usr/bin/env python3
"""
Merge Ground Truth Types into Enriched KB

Adds explicit parameter types from operator_ground_truth/params/*.json
into td_universal_parsed_enriched.json so MCP tools have real types
instead of inferring from descriptions.

Author: KYLE (KB Manager)
Date: 2024-12-28
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
import re


def normalize_name(name: str) -> str:
    """Convert 'Noise CHOP' to 'Noise_CHOP' for file matching."""
    return name.replace(" ", "_")


def find_ground_truth_file(family: str, op_name: str, gt_dir: Path) -> Optional[Path]:
    """Find the defaults ground truth file for an operator."""
    # Try exact match first: CHOP_Noise_CHOP_defaults.json
    normalized = normalize_name(op_name)
    exact_path = gt_dir / f"{family}_{normalized}_defaults.json"
    if exact_path.exists():
        return exact_path

    # Try without family suffix in name: CHOP_Noise_defaults.json
    base_name = normalized
    for suffix in ["_CHOP", "_TOP", "_SOP", "_DAT", "_MAT", "_COMP", "_POP"]:
        if base_name.endswith(suffix):
            base_name = base_name[:-len(suffix)]
            break

    alt_path = gt_dir / f"{family}_{base_name}_{family}_defaults.json"
    if alt_path.exists():
        return alt_path

    # Try case variations
    for f in gt_dir.glob(f"{family}_*_defaults.json"):
        if base_name.lower() in f.stem.lower():
            return f

    return None


def extract_param_type_info(gt_param: Dict[str, Any]) -> Dict[str, Any]:
    """Extract type information from ground truth parameter."""
    result = {}

    # Get value info
    value_info = gt_param.get("value", {})
    if isinstance(value_info, dict):
        param_type = value_info.get("type", "unknown")
        result["type"] = param_type

        # For menu types, extract menu options
        if param_type == "menu":
            if "menuNames" in value_info:
                result["menuNames"] = value_info["menuNames"]
            if "menuLabels" in value_info:
                result["menuLabels"] = value_info["menuLabels"]

    # Get other fields
    if "default" in gt_param:
        result["default"] = gt_param["default"]
    if "page" in gt_param:
        result["page"] = gt_param["page"]
    if "readOnly" in gt_param:
        result["readOnly"] = gt_param["readOnly"]

    # Mark source
    result["source"] = "ground_truth"

    return result


def merge_ground_truth_types(
    enriched_path: Path,
    gt_dir: Path,
    output_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Merge ground truth types into enriched wiki data.

    Args:
        enriched_path: Path to td_universal_parsed_enriched.json
        gt_dir: Path to operator_ground_truth/params/ directory
        output_path: Output path (defaults to overwriting enriched_path)

    Returns:
        Stats dict with merge results
    """
    print(f"Loading enriched wiki from {enriched_path}...")
    with open(enriched_path, "r", encoding="utf-8") as f:
        enriched = json.load(f)

    stats = {
        "total_operators": len(enriched.get("operators", [])),
        "operators_matched": 0,
        "operators_not_matched": 0,
        "params_enriched": 0,
        "params_not_found": 0,
        "unmatched_operators": []
    }

    print(f"Processing {stats['total_operators']} operators...")

    for op in enriched.get("operators", []):
        op_name = op.get("name", "")
        family = op.get("family", "")

        if not op_name or not family:
            continue

        # Find ground truth file
        gt_file = find_ground_truth_file(family, op_name, gt_dir)

        if not gt_file:
            stats["operators_not_matched"] += 1
            stats["unmatched_operators"].append(op_name)
            continue

        stats["operators_matched"] += 1

        # Load ground truth
        try:
            with open(gt_file, "r", encoding="utf-8") as f:
                gt_data = json.load(f)
        except Exception as e:
            print(f"  Warning: Could not load {gt_file}: {e}")
            continue

        gt_params = gt_data.get("parameters", {})

        # Enrich each parameter
        for param in op.get("parameters", []):
            param_code = param.get("code", "")
            if not param_code:
                continue

            if param_code in gt_params:
                gt_param = gt_params[param_code]
                type_info = extract_param_type_info(gt_param)

                # Merge type info into parameter
                param.update(type_info)
                stats["params_enriched"] += 1
            else:
                stats["params_not_found"] += 1

    # Update metadata
    if "metadata" not in enriched:
        enriched["metadata"] = {}
    enriched["metadata"]["ground_truth_merge"] = {
        "merged_at": __import__("datetime").datetime.now().isoformat(),
        "operators_matched": stats["operators_matched"],
        "params_enriched": stats["params_enriched"]
    }

    # Save output
    out_path = output_path or enriched_path
    print(f"Saving enriched data to {out_path}...")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    return stats


def main():
    """Run the merge."""
    # Paths
    base_dir = Path(__file__).parent
    enriched_path = base_dir / "data" / "wiki_docs" / "td_universal_parsed_enriched.json"
    gt_dir = base_dir / "operator_ground_truth" / "params"

    if not enriched_path.exists():
        print(f"ERROR: Enriched wiki not found at {enriched_path}")
        return

    if not gt_dir.exists():
        print(f"ERROR: Ground truth directory not found at {gt_dir}")
        return

    print("=" * 60)
    print("MERGE GROUND TRUTH TYPES INTO ENRICHED KB")
    print("=" * 60)
    print()

    stats = merge_ground_truth_types(enriched_path, gt_dir)

    print()
    print("=" * 60)
    print("MERGE COMPLETE")
    print("=" * 60)
    print(f"  Operators matched:     {stats['operators_matched']}/{stats['total_operators']}")
    print(f"  Operators not matched: {stats['operators_not_matched']}")
    print(f"  Parameters enriched:   {stats['params_enriched']}")
    print(f"  Parameters not found:  {stats['params_not_found']}")
    print()

    if stats["unmatched_operators"]:
        print(f"Unmatched operators ({len(stats['unmatched_operators'])}):")
        for op in stats["unmatched_operators"][:10]:
            print(f"  - {op}")
        if len(stats["unmatched_operators"]) > 10:
            print(f"  ... and {len(stats['unmatched_operators']) - 10} more")


if __name__ == "__main__":
    main()

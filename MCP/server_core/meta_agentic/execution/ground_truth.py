"""
Ground Truth Loader

Loads operator parameter schemas from operator_ground_truth/params/ for validation.
Provides lookup for correct TD parameter names and menu values.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# INERT SINCE BIRTH (W2a marker, 2026-07-04): this path resolves to
# MCP/server_core/operator_ground_truth/params, which has never existed in any
# release — load() warns "Ground truth directory not found" and every lookup
# returns None, so ToeBuilderBridge._param_lines' validation layer fail-soft
# passes params through unvalidated. The real corpus lives in the dev tree at
# "New KB build/Resources/operator_ground_truth/params" (not shipped). Wiring
# this against the real corpus is owned by remediation work item 3a; do not
# point the path there ad hoc — the corpus isn't part of the release bundle.
GROUND_TRUTH_DIR = Path(__file__).parent.parent.parent / "operator_ground_truth" / "params"


class GroundTruth:
    """Singleton loader for operator ground truth data."""

    _instance = None
    _operators: Dict[str, Dict] = {}
    _loaded = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, force_reload: bool = False):
        """Load all operator ground truth files."""
        if self._loaded and not force_reload:
            return

        if not GROUND_TRUTH_DIR.exists():
            logger.warning(f"Ground truth directory not found: {GROUND_TRUTH_DIR}")
            return

        count = 0
        for json_file in GROUND_TRUTH_DIR.glob("*_defaults.json"):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)

                # Key by operator name (e.g., "Noise_TOP", "Analyze_CHOP")
                op_name = data.get("operator", "")
                if op_name:
                    self._operators[op_name.lower()] = data

                    # Also key by td_create_name (e.g., "noiseTOP", "analyzeCHOP")
                    create_name = data.get("td_create_name", "")
                    if create_name:
                        self._operators[create_name.lower()] = data

                count += 1
            except Exception as e:
                logger.error(f"Error loading {json_file}: {e}")

        self._loaded = True
        logger.info(f"Loaded {count} operator ground truth files")

    def get_operator(self, op_type: str, family: str = None) -> Optional[Dict]:
        """
        Get operator schema by type.

        Args:
            op_type: Operator type (e.g., "noise", "noiseTOP", "Noise_TOP", "analyze")
            family: Optional family hint ("TOP", "CHOP", etc.)

        Returns:
            Operator schema dict or None
        """
        if not self._loaded:
            self.load()

        op_lower = op_type.lower().replace(" ", "").replace("_", "")

        # Try various name formats
        lookup_keys = [
            op_type.lower(),
            op_lower,
        ]

        # Add family-specific variations
        families = ["top", "chop", "sop", "comp", "dat", "mat"]
        if family:
            families = [family.lower()] + families

        for fam in families:
            lookup_keys.extend([
                f"{op_lower}{fam}",
                f"{op_lower}_{fam}",
                f"{op_type.lower()}{fam}",
                f"{op_type.lower()}_{fam}",
            ])

        for key in lookup_keys:
            if key in self._operators:
                return self._operators[key]

        # Try partial match
        for stored_key in self._operators:
            if op_lower in stored_key or stored_key.startswith(op_lower):
                return self._operators[stored_key]

        return None

    def get_param_info(self, op_type: str, param_name: str) -> Optional[Dict]:
        """
        Get parameter info for an operator.

        Args:
            op_type: Operator type
            param_name: Parameter name (TD Designer's name)

        Returns:
            Parameter info dict or None
        """
        op_schema = self.get_operator(op_type)
        if not op_schema:
            return None

        params = op_schema.get("parameters", {})

        # Direct match
        if param_name.lower() in params:
            return params[param_name.lower()]

        # Search by label
        for pname, pinfo in params.items():
            if pinfo.get("label", "").lower() == param_name.lower():
                return {**pinfo, "_td_name": pname}

        return None

    def get_correct_param_name(self, op_type: str, human_name: str) -> Optional[str]:
        """
        Get TD's internal param name from human-readable name.

        Args:
            op_type: Operator type
            human_name: Human-readable param name (from TD Designer)

        Returns:
            TD internal param name or None
        """
        param_info = self.get_param_info(op_type, human_name)
        if param_info:
            return param_info.get("_td_name", human_name.lower())
        return None

    def get_menu_value(self, op_type: str, param_name: str, label: str) -> Optional[str]:
        """
        Convert menu label to internal value.

        Args:
            op_type: Operator type
            param_name: Parameter name
            label: Menu label (human-readable)

        Returns:
            Internal menu value or None
        """
        param_info = self.get_param_info(op_type, param_name)
        if not param_info:
            return None

        value_info = param_info.get("value", {})
        if value_info.get("type") != "menu":
            return None

        menu_labels = value_info.get("menuLabels", [])
        menu_names = value_info.get("menuNames", [])

        # Find label in menuLabels, return corresponding menuName
        label_lower = label.lower().strip()
        for i, menu_label in enumerate(menu_labels):
            if menu_label.lower() == label_lower:
                if i < len(menu_names):
                    return menu_names[i]

        # Try direct match in menuNames
        for menu_name in menu_names:
            if menu_name.lower() == label_lower:
                return menu_name

        return None

    def validate_param(self, op_type: str, param_name: str, value: Any, family: str = None) -> Dict:
        """
        Validate a parameter against ground truth.

        Args:
            op_type: Operator type
            param_name: Parameter name
            value: Parameter value
            family: Optional family hint ("TOP", "CHOP", etc.)

        Returns:
            Dict with:
                valid: bool
                td_name: correct TD param name (if found)
                td_value: correct TD value (if menu)
                error: error message (if invalid)
        """
        result = {"valid": False, "td_name": None, "td_value": None, "error": None}

        op_schema = self.get_operator(op_type, family=family)
        if not op_schema:
            result["error"] = f"Unknown operator type: {op_type}"
            return result

        # Try to find the parameter
        params = op_schema.get("parameters", {})
        td_param_name = None
        param_info = None

        # Direct name match
        if param_name.lower() in params:
            td_param_name = param_name.lower()
            param_info = params[td_param_name]

        # Search by label
        if not param_info:
            for pname, pinfo in params.items():
                if pinfo.get("label", "").lower() == param_name.lower():
                    td_param_name = pname
                    param_info = pinfo
                    break

        if not param_info:
            result["error"] = f"Unknown parameter: {param_name} for {op_type}"
            return result

        result["td_name"] = td_param_name
        result["valid"] = True

        # Handle menu values
        value_info = param_info.get("value", {})
        if value_info.get("type") == "menu" and isinstance(value, str):
            menu_val = self.get_menu_value(op_type, td_param_name, value)
            if menu_val:
                result["td_value"] = menu_val
            else:
                result["td_value"] = value.lower()
        else:
            result["td_value"] = value

        return result

    def list_params(self, op_type: str) -> List[str]:
        """List all valid parameter names for an operator."""
        op_schema = self.get_operator(op_type)
        if not op_schema:
            return []
        return list(op_schema.get("parameters", {}).keys())


# Singleton instance
ground_truth = GroundTruth()


def get_ground_truth() -> GroundTruth:
    """Get the ground truth singleton, loading if needed."""
    if not ground_truth._loaded:
        ground_truth.load()
    return ground_truth

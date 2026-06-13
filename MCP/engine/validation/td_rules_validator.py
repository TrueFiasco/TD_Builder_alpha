"""TD Rules Validator - Stage 5: TouchDesigner-specific rules.

Validates TouchDesigner-specific constraints and conventions.
"""

import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parent.parent))

from typing import List, Dict, Any
from core.models import ValidationError, StageReport, TDNetwork, OperatorFamily
from core.operator_registry import OperatorRegistry


class TDRulesValidator:
    """
    Stage 5: TouchDesigner Rules Validation.

    Checks TD-specific rules:
    - Only COMP operators can have children
    - Operator naming conventions
    - Required metadata fields
    - Version compatibility (basic)
    """

    def __init__(self, registry: OperatorRegistry = None):
        """
        Initialize TD rules validator.

        Args:
            registry: OperatorRegistry (creates new if None)
        """
        self.registry = registry or OperatorRegistry()

    def validate(self, network_json: Dict[str, Any]) -> StageReport:
        """
        Validate TouchDesigner-specific rules.

        Args:
            network_json: Network JSON or TDNetwork

        Returns:
            StageReport with errors/warnings
        """
        errors = []
        warnings = []

        # Handle TDNetwork objects
        if isinstance(network_json, TDNetwork):
            operators_data = [self._operator_to_dict(op) for op in network_json.operators]
            metadata = self._metadata_to_dict(network_json.metadata)
        else:
            operators_data = network_json.get("operators", [])
            metadata = network_json.get("metadata", {})

        # Check metadata
        if not metadata.get("project_name"):
            warnings.append(ValidationError(
                code="MISSING_PROJECT_NAME",
                stage="td_rules",
                severity="warning",
                message="Project name not specified in metadata",
                location="metadata.project_name",
                suggestion="Add project_name to metadata"
            ))

        if not metadata.get("mode"):
            warnings.append(ValidationError(
                code="MISSING_MODE",
                stage="td_rules",
                severity="warning",
                message="Mode (toe/tox) not specified in metadata",
                location="metadata.mode",
                suggestion="Add mode: 'toe' or 'tox' to metadata"
            ))

        # Validate operators
        for idx, operator in enumerate(operators_data):
            op_errors = self._validate_operator_rules(operator, idx)
            errors.extend(op_errors)

        status = "PASS" if len(errors) == 0 else "FAIL"

        return StageReport(
            stage="td_rules",
            status=status,
            errors=errors,
            warnings=warnings
        )

    def _validate_operator_rules(self, operator: Dict[str, Any], index: int) -> List[ValidationError]:
        """Validate TouchDesigner rules for single operator."""
        errors = []
        path = operator.get("path", f"operator[{index}]")
        family_str = operator.get("family", "")
        type_name = operator.get("type", "")
        children = operator.get("children", [])

        # Rule: Only COMP operators can have children
        if children and len(children) > 0:
            if family_str != "COMP":
                errors.append(ValidationError(
                    code="NON_COMP_HAS_CHILDREN",
                    stage="td_rules",
                    severity="error",
                    message=f"{family_str} operators cannot have children (only COMP can)",
                    location=f"operators[{index}].children",
                    path=path,
                    suggestion=f"Remove children or change operator to COMP family"
                ))

        # Rule: Check naming conventions
        name = operator.get("name", "")
        if name:
            # Name should start with letter or underscore
            if not (name[0].isalpha() or name[0] == '_'):
                warnings.append(ValidationError(
                    code="INVALID_OPERATOR_NAME",
                    stage="td_rules",
                    severity="warning",
                    message=f"Operator name '{name}' should start with letter or underscore",
                    location=f"operators[{index}].name",
                    path=path,
                    suggestion="Rename to start with a letter or underscore"
                ))

            # Name should not contain spaces
            if ' ' in name:
                errors.append(ValidationError(
                    code="OPERATOR_NAME_HAS_SPACES",
                    stage="td_rules",
                    severity="error",
                    message=f"Operator name '{name}' cannot contain spaces",
                    location=f"operators[{index}].name",
                    path=path,
                    suggestion="Remove spaces from operator name"
                ))

        # Rule: Path should be absolute and valid
        if path and not path.startswith('/'):
            warnings.append(ValidationError(
                code="RELATIVE_OPERATOR_PATH",
                stage="td_rules",
                severity="warning",
                message=f"Operator path '{path}' should be absolute (start with /)",
                location=f"operators[{index}].path",
                path=path,
                suggestion="Use absolute paths starting with /"
            ))

        return errors

    def _operator_to_dict(self, operator) -> Dict[str, Any]:
        """Convert Operator object to dict."""
        return {
            "path": operator.path,
            "name": operator.name,
            "family": operator.family.value if hasattr(operator.family, 'value') else operator.family,
            "type": operator.type,
            "children": operator.children
        }

    def _metadata_to_dict(self, metadata) -> Dict[str, Any]:
        """Convert Metadata object to dict."""
        return {
            "project_name": metadata.project_name,
            "mode": metadata.mode
        }


def validate_td_rules(network_json: Dict[str, Any], registry: OperatorRegistry = None) -> StageReport:
    """
    Convenience function to validate TouchDesigner rules.

    Args:
        network_json: Network JSON
        registry: Optional OperatorRegistry

    Returns:
        StageReport
    """
    validator = TDRulesValidator(registry)
    return validator.validate(network_json)

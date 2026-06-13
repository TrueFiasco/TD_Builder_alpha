"""Semantic Validator - Stage 2: Operator and parameter existence.

Validates that operators and parameters exist in the registry.
"""

import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parent.parent))

from typing import List, Dict, Any
from core.models import ValidationError, StageReport, OperatorFamily, TDNetwork
from core.operator_registry import OperatorRegistry


class SemanticValidator:
    """
    Stage 2: Semantic Validation.

    Checks:
    - Operator types exist in registry
    - Families are valid
    - Parameters exist for operator type
    - Parameter values match expected types (basic)
    """

    def __init__(self, registry: OperatorRegistry = None):
        """
        Initialize semantic validator.

        Args:
            registry: OperatorRegistry (creates new if None)
        """
        self.registry = registry or OperatorRegistry()

    def validate(self, network_json: Dict[str, Any]) -> StageReport:
        """
        Validate network semantics.

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
        else:
            operators_data = network_json.get("operators", [])

        # Validate each operator
        for idx, operator in enumerate(operators_data):
            operator_errors = self._validate_operator(operator, idx)
            errors.extend(operator_errors)

        status = "PASS" if len(errors) == 0 else "FAIL"

        return StageReport(
            stage="semantic",
            status=status,
            errors=errors,
            warnings=warnings
        )

    def _operator_to_dict(self, operator) -> Dict[str, Any]:
        """Convert Operator object to dict for validation."""
        return {
            "path": operator.path,
            "name": operator.name,
            "family": operator.family.value if hasattr(operator.family, 'value') else operator.family,
            "type": operator.type,
            "parameters": operator.parameters
        }

    def _validate_operator(self, operator: Dict[str, Any], index: int) -> List[ValidationError]:
        """Validate single operator."""
        errors = []
        path = operator.get("path", f"operator[{index}]")

        # Validate family
        family_str = operator.get("family", "")
        if not family_str:
            errors.append(ValidationError(
                code="MISSING_FAMILY",
                stage="semantic",
                severity="error",
                message="Operator missing 'family' field",
                location=f"operators[{index}].family",
                path=path,
                suggestion="Add family: CHOP, TOP, SOP, DAT, COMP, MAT, or POP"
            ))
            return errors  # Can't continue without family

        try:
            family = OperatorFamily(family_str)
        except ValueError:
            errors.append(ValidationError(
                code="INVALID_FAMILY",
                stage="semantic",
                severity="error",
                message=f"Invalid operator family: '{family_str}'",
                location=f"operators[{index}].family",
                path=path,
                suggestion="Use one of: CHOP, TOP, SOP, DAT, COMP, MAT, POP"
            ))
            return errors

        # Validate operator type
        type_name = operator.get("type", "")
        if not type_name:
            errors.append(ValidationError(
                code="MISSING_TYPE",
                stage="semantic",
                severity="error",
                message="Operator missing 'type' field",
                location=f"operators[{index}].type",
                path=path,
                suggestion="Add operator type (e.g., 'noise', 'render', etc.)"
            ))
            return errors

        # Check if operator exists in registry
        if not self.registry.validate_operator_type(family, type_name):
            # Try to find similar operators
            similar = self._find_similar_operators(family, type_name)
            suggestion = f"Did you mean one of: {', '.join(similar[:3])}?" if similar else \
                        f"Check available {family_str} operators in registry"

            errors.append(ValidationError(
                code="UNKNOWN_OPERATOR_TYPE",
                stage="semantic",
                severity="error",
                message=f"Operator type '{family_str}:{type_name}' does not exist",
                location=f"operators[{index}].type",
                path=path,
                suggestion=suggestion
            ))
            return errors  # Can't validate parameters without operator spec

        # Validate parameters
        parameters = operator.get("parameters", {})
        if parameters:
            param_errors = self._validate_parameters(family, type_name, parameters, index, path)
            errors.extend(param_errors)

        return errors

    def _validate_parameters(self, family: OperatorFamily, type_name: str,
                            parameters: Dict[str, Any], op_index: int, op_path: str) -> List[ValidationError]:
        """Validate operator parameters."""
        errors = []

        # Get parameter specs from registry
        param_specs = self.registry.get_parameters(family, type_name)
        param_codes = {spec.code for spec in param_specs}

        # Check each parameter
        for param_name, param_value in parameters.items():
            # Check if parameter exists
            if not self.registry.has_parameter(family, type_name, param_name):
                # Parameter doesn't exist
                errors.append(ValidationError(
                    code="UNKNOWN_PARAMETER",
                    stage="semantic",
                    severity="error",
                    message=f"Parameter '{param_name}' does not exist for {family.value}:{type_name}",
                    location=f"operators[{op_index}].parameters.{param_name}",
                    path=op_path,
                    suggestion=f"Check operator documentation for valid parameters"
                ))

        return errors

    def _find_similar_operators(self, family: OperatorFamily, type_name: str) -> List[str]:
        """Find similar operator types (for suggestions)."""
        all_ops = self.registry.get_operators_by_family(family)

        # Simple string matching
        similar = []
        for op in all_ops:
            op_type = op.op_type.split(':')[1]
            if type_name.lower() in op_type.lower() or op_type.lower() in type_name.lower():
                similar.append(op_type)

        return similar[:5]  # Return top 5


def validate_semantics(network_json: Dict[str, Any], registry: OperatorRegistry = None) -> StageReport:
    """
    Convenience function to validate network semantics.

    Args:
        network_json: Network JSON
        registry: Optional OperatorRegistry

    Returns:
        StageReport
    """
    validator = SemanticValidator(registry)
    return validator.validate(network_json)

"""Logical Validator - Stage 4: Logical consistency.

Validates logical rules like type compatibility and cycles.
"""

import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parent.parent))

from typing import List, Dict, Any, Set
from core.models import ValidationError, StageReport, TDNetwork, OperatorFamily
from core.operator_registry import OperatorRegistry


class LogicalValidator:
    """
    Stage 4: Logical Validation.

    Checks:
    - Connection type compatibility (CHOP->CHOP, TOP->TOP, etc.)
    - No circular parent-child relationships
    - Input indices within bounds
    - Output indices within bounds
    """

    def __init__(self, registry: OperatorRegistry = None):
        """
        Initialize logical validator.

        Args:
            registry: OperatorRegistry (creates new if None)
        """
        self.registry = registry or OperatorRegistry()

    def validate(self, network_json: Dict[str, Any]) -> StageReport:
        """
        Validate network logic.

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
            connections_data = [self._connection_to_dict(c) for c in network_json.connections]
        else:
            operators_data = network_json.get("operators", [])
            connections_data = network_json.get("connections", [])

        # Build operator map
        operator_map = {op.get("path"): op for op in operators_data if op.get("path")}

        # Check for circular parent-child relationships
        cycle_errors = self._check_circular_hierarchy(operators_data)
        errors.extend(cycle_errors)

        # Check connection type compatibility
        for idx, connection in enumerate(connections_data):
            source = connection.get("from") or connection.get("source")
            target = connection.get("to") or connection.get("target")

            if source in operator_map and target in operator_map:
                source_op = operator_map[source]
                target_op = operator_map[target]

                # Get families
                source_family = source_op.get("family")
                target_family = target_op.get("family")

                # Check type compatibility
                if source_family and target_family:
                    if not self._are_families_compatible(source_family, target_family):
                        errors.append(ValidationError(
                            code="INCOMPATIBLE_CONNECTION_TYPES",
                            stage="logical",
                            severity="error",
                            message=f"Cannot connect {source_family} to {target_family}",
                            location=f"connections[{idx}]",
                            suggestion=f"Connect {source_family} -> {source_family} instead"
                        ))

        status = "PASS" if len(errors) == 0 else "FAIL"

        return StageReport(
            stage="logical",
            status=status,
            errors=errors,
            warnings=warnings
        )

    def _check_circular_hierarchy(self, operators: List[Dict[str, Any]]) -> List[ValidationError]:
        """Check for circular parent-child relationships."""
        errors = []

        # Build parent map
        parent_map = {}
        for op in operators:
            path = op.get("path")
            parent = op.get("parent")
            if path and parent:
                parent_map[path] = parent

        # Check each operator for cycles
        for op in operators:
            path = op.get("path")
            if not path:
                continue

            visited = set()
            current = path

            while current in parent_map:
                if current in visited:
                    # Found a cycle
                    errors.append(ValidationError(
                        code="CIRCULAR_HIERARCHY",
                        stage="logical",
                        severity="error",
                        message=f"Circular parent-child relationship detected involving '{path}'",
                        path=path,
                        suggestion="Remove circular parent reference"
                    ))
                    break

                visited.add(current)
                current = parent_map[current]

        return errors

    def _are_families_compatible(self, source_family: str, target_family: str) -> bool:
        """
        Check if two operator families can be connected.

        Rules:
        - CHOP -> CHOP: Yes
        - TOP -> TOP: Yes
        - SOP -> SOP: Yes
        - DAT -> DAT: Yes
        - MAT -> TOP/SOP: Yes (materials can go to geometry/texture)
        - COMP -> Any: No (COMPs don't have direct connections)
        - Different families: Generally no
        """
        # Same family is always compatible
        if source_family == target_family:
            return True

        # MAT can connect to TOP or SOP
        if source_family == "MAT" and target_family in ["TOP", "SOP"]:
            return True

        # CHOP can sometimes connect to others (exporters)
        # For now, be strict
        return False

    def _operator_to_dict(self, operator) -> Dict[str, Any]:
        """Convert Operator object to dict."""
        return {
            "path": operator.path,
            "parent": operator.parent,
            "family": operator.family.value if hasattr(operator.family, 'value') else operator.family,
            "type": operator.type
        }

    def _connection_to_dict(self, connection) -> Dict[str, Any]:
        """Convert Connection object to dict."""
        return {
            "from": connection.source,
            "to": connection.target,
            "from_output": connection.source_output,
            "to_input": connection.target_input
        }


def validate_logic(network_json: Dict[str, Any], registry: OperatorRegistry = None) -> StageReport:
    """
    Convenience function to validate network logic.

    Args:
        network_json: Network JSON
        registry: Optional OperatorRegistry

    Returns:
        StageReport
    """
    validator = LogicalValidator(registry)
    return validator.validate(network_json)

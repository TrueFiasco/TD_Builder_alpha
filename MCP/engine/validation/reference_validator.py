"""Reference Validator - Stage 3: Reference validity.

Validates that all references (connections, parents, children) resolve correctly.
"""

import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parent.parent))

from typing import List, Dict, Any, Set
from core.models import ValidationError, StageReport, TDNetwork


class ReferenceValidator:
    """
    Stage 3: Reference Validation.

    Checks:
    - All operator paths are unique
    - Parent operators exist
    - Connection sources exist
    - Connection targets exist
    - Children are listed in parent's children array
    - No dangling references
    """

    def validate(self, network_json: Dict[str, Any]) -> StageReport:
        """
        Validate network references.

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
            root_comp = f"/{network_json.metadata.root_comp}"
        else:
            operators_data = network_json.get("operators", [])
            connections_data = network_json.get("connections", [])
            metadata = network_json.get("metadata", {})
            root_comp = f"/{metadata.get('root_comp', 'project1')}"

        # Build operator path set for fast lookup (including root comp)
        operator_paths = {op.get("path") for op in operators_data if op.get("path")}
        operator_paths.add(root_comp)  # Root component always exists

        # Check for duplicate paths
        path_counts = {}
        for op in operators_data:
            path = op.get("path")
            if path:
                path_counts[path] = path_counts.get(path, 0) + 1

        for path, count in path_counts.items():
            if count > 1:
                errors.append(ValidationError(
                    code="DUPLICATE_OPERATOR_PATH",
                    stage="reference",
                    severity="error",
                    message=f"Duplicate operator path: '{path}' appears {count} times",
                    path=path,
                    suggestion="Ensure all operator paths are unique"
                ))

        # Validate parent references
        for idx, operator in enumerate(operators_data):
            path = operator.get("path")
            parent = operator.get("parent")

            if parent:
                if parent not in operator_paths:
                    errors.append(ValidationError(
                        code="MISSING_PARENT",
                        stage="reference",
                        severity="error",
                        message=f"Parent '{parent}' does not exist",
                        location=f"operators[{idx}].parent",
                        path=path,
                        suggestion=f"Create parent operator or fix parent path"
                    ))

        # Validate connections
        for idx, connection in enumerate(connections_data):
            source = connection.get("from") or connection.get("source")
            target = connection.get("to") or connection.get("target")

            if source and source not in operator_paths:
                errors.append(ValidationError(
                    code="MISSING_CONNECTION_SOURCE",
                    stage="reference",
                    severity="error",
                    message=f"Connection source '{source}' does not exist",
                    location=f"connections[{idx}].from",
                    suggestion="Check operator path spelling or create the operator"
                ))

            if target and target not in operator_paths:
                errors.append(ValidationError(
                    code="MISSING_CONNECTION_TARGET",
                    stage="reference",
                    severity="error",
                    message=f"Connection target '{target}' does not exist",
                    location=f"connections[{idx}].to",
                    suggestion="Check operator path spelling or create the operator"
                ))

        # Validate children references (optional - warning only)
        for idx, operator in enumerate(operators_data):
            path = operator.get("path")
            children = operator.get("children", [])

            for child_path in children:
                if child_path not in operator_paths:
                    warnings.append(ValidationError(
                        code="MISSING_CHILD",
                        stage="reference",
                        severity="warning",
                        message=f"Child '{child_path}' not found in operators list",
                        location=f"operators[{idx}].children",
                        path=path,
                        suggestion="Remove from children list or add the operator"
                    ))

        status = "PASS" if len(errors) == 0 else "FAIL"

        return StageReport(
            stage="reference",
            status=status,
            errors=errors,
            warnings=warnings
        )

    def _operator_to_dict(self, operator) -> Dict[str, Any]:
        """Convert Operator object to dict."""
        return {
            "path": operator.path,
            "parent": operator.parent,
            "children": operator.children
        }

    def _connection_to_dict(self, connection) -> Dict[str, Any]:
        """Convert Connection object to dict."""
        return {
            "from": connection.source,
            "to": connection.target
        }


def validate_references(network_json: Dict[str, Any]) -> StageReport:
    """
    Convenience function to validate network references.

    Args:
        network_json: Network JSON

    Returns:
        StageReport
    """
    validator = ReferenceValidator()
    return validator.validate(network_json)

"""Schema Validator - Stage 1: JSON Schema validation.

Validates network JSON against the unified v2 schema.
"""

import json
import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parent.parent))

from pathlib import Path
from typing import List, Dict, Any

try:
    import jsonschema
    from jsonschema import Draft7Validator, ValidationError as JSONSchemaError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

from core.models import ValidationError, StageReport


class SchemaValidator:
    """
    Stage 1: JSON Schema Validation.

    Validates network JSON structure against unified_v2.schema.json.
    Catches structural errors before semantic validation.
    """

    def __init__(self, schema_path: Path = None):
        """
        Initialize schema validator.

        Args:
            schema_path: Path to unified_v2.schema.json (auto-detect if None)
        """
        if schema_path is None:
            schema_path = Path(__file__).parent.parent / "schemas" / "unified_v2.schema.json"

        self.schema_path = Path(schema_path)
        self.schema = self._load_schema()
        self.validator = None

        if HAS_JSONSCHEMA and self.schema:
            self.validator = Draft7Validator(self.schema)

    def _load_schema(self) -> Dict[str, Any]:
        """Load JSON schema from file."""
        if not self.schema_path.exists():
            return {}

        with open(self.schema_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def validate(self, network_json: Dict[str, Any]) -> StageReport:
        """
        Validate network JSON against schema.

        Args:
            network_json: Network JSON to validate

        Returns:
            StageReport with errors/warnings
        """
        errors = []
        warnings = []

        if not HAS_JSONSCHEMA:
            warnings.append(ValidationError(
                code="JSONSCHEMA_NOT_AVAILABLE",
                stage="schema",
                severity="warning",
                message="jsonschema library not available - schema validation skipped",
                suggestion="Install jsonschema: pip install jsonschema"
            ))
            return StageReport(
                stage="schema",
                status="PASS",
                errors=errors,
                warnings=warnings
            )

        if not self.schema:
            warnings.append(ValidationError(
                code="SCHEMA_NOT_FOUND",
                stage="schema",
                severity="warning",
                message=f"Schema not found at {self.schema_path}",
                suggestion="Ensure unified_v2.schema.json exists"
            ))
            return StageReport(
                stage="schema",
                status="PASS",
                errors=errors,
                warnings=warnings
            )

        # Convert TDNetwork to dict if needed
        from core.models import TDNetwork, Connection, ParameterValue
        if isinstance(network_json, TDNetwork):
            # Convert to dict using the same serialization as NetworkBuilder
            from enum import Enum
            def _serialize(obj):
                """Recursively serialize dataclasses and enums."""
                if isinstance(obj, Enum):
                    return obj.value
                elif isinstance(obj, Connection):
                    # Special handling for Connection to map source->from, target->to
                    return {
                        "from": obj.source,
                        "to": obj.target,
                        "from_output": obj.source_output,
                        "to_input": obj.target_input
                    }
                elif isinstance(obj, ParameterValue):
                    # Special handling for ParameterValue - simplify to just the value or expression
                    if obj.mode.value == 'expression' and obj.expression:
                        # Return expression string directly (schema accepts string for parameters)
                        return obj.expression
                    else:
                        # Return constant value
                        return obj.value
                elif hasattr(obj, '__dict__'):
                    result = {}
                    for key, value in obj.__dict__.items():
                        # Skip None values to reduce schema errors
                        if value is not None:
                            result[key] = _serialize(value)
                    return result
                elif isinstance(obj, dict):
                    return {k: _serialize(v) for k, v in obj.items() if v is not None}
                elif isinstance(obj, (list, tuple)):
                    return [_serialize(item) for item in obj]
                else:
                    return obj

            network_dict = {
                "format_version": network_json.format_version,
                "format_layer": network_json.format_layer.value,
                "metadata": _serialize(network_json.metadata),
                "operators": [_serialize(op) for op in network_json.operators],
                "connections": [_serialize(conn) for conn in network_json.connections]
            }
        else:
            network_dict = network_json

        # Validate using jsonschema
        try:
            # Check if validator exists
            if self.validator is None:
                raise Exception("Validator not initialized")

            # Validate
            schema_errors = list(self.validator.iter_errors(network_dict))

            for err in schema_errors:
                # Convert jsonschema error to ValidationError
                location = ".".join(str(p) for p in err.path) if err.path else "root"

                error = ValidationError(
                    code="SCHEMA_VIOLATION",
                    stage="schema",
                    severity="error",
                    message=err.message,
                    location=location,
                    suggestion=self._get_suggestion(err)
                )
                errors.append(error)

        except Exception as e:
            errors.append(ValidationError(
                code="SCHEMA_VALIDATION_ERROR",
                stage="schema",
                severity="error",
                message=f"Schema validation failed: {str(e)}",
                suggestion="Check network JSON structure"
            ))

        status = "PASS" if len(errors) == 0 else "FAIL"

        return StageReport(
            stage="schema",
            status=status,
            errors=errors,
            warnings=warnings
        )

    def _get_suggestion(self, err: 'JSONSchemaError') -> str:
        """Get helpful suggestion for schema error."""
        if "required" in err.message.lower():
            return "Add the required field to the JSON"
        elif "type" in err.message.lower():
            return "Check that the value has the correct data type"
        elif "enum" in err.message.lower():
            return "Use one of the allowed values"
        elif "pattern" in err.message.lower():
            return "Ensure the string matches the expected pattern"
        else:
            return "Review the schema specification"


def validate_schema(network_json: Dict[str, Any], schema_path: Path = None) -> StageReport:
    """
    Convenience function to validate network JSON against schema.

    Args:
        network_json: Network JSON
        schema_path: Optional path to schema

    Returns:
        StageReport
    """
    validator = SchemaValidator(schema_path)
    return validator.validate(network_json)

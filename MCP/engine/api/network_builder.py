"""NetworkBuilder - High-level API for building TouchDesigner networks.

Provides an intuitive Python API for creating TD networks programmatically.
Integrates validation, operator registry, and format conversion.
"""

import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parent.parent))

from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from core.models import (
    TDNetwork, Operator, Connection, Metadata, Position, Flags,
    OperatorFamily, FormatLayer, Input, ParameterValue, ExpressionLanguage,
    ParameterMode, ValidationReport
)
from api.validate import build_validation_stack


class NetworkBuilder:
    """
    High-level API for building TouchDesigner networks.

    Example:
        builder = NetworkBuilder("audio_viz", mode="toe")
        builder.add_operator("noise1", "CHOP", "noise")
        builder.add_operator("null1", "CHOP", "null")
        builder.connect("noise1", "null1")
        builder.set_parameter("noise1", "amplitude", 0.5)

        if builder.validate():
            builder.build_toe("output.toe")
    """

    def __init__(self, project_name: str, mode: str = "toe", root_comp: str = "project1"):
        """
        Initialize network builder.

        Args:
            project_name: Project name
            mode: "toe" or "tox"
            root_comp: Root component path (default: "project1")
        """
        self.registry, self.converter, self.validator = build_validation_stack()

        # Initialize network
        self.metadata = Metadata(
            project_name=project_name,
            mode=mode,
            root_comp=root_comp,
            created_at=datetime.now().isoformat()
        )

        self.operators: Dict[str, Operator] = {}  # Key: name or path
        self.connections: List[Connection] = []
        self._operator_counter = {}  # Track auto-naming

    # =========================================================================
    # Operator Management
    # =========================================================================

    def add_operator(self,
                     name: str,
                     family: Union[str, OperatorFamily],
                     op_type: str,
                     parent: Optional[str] = None,
                     **kwargs) -> 'NetworkBuilder':
        """
        Add operator to network.

        Args:
            name: Operator name (e.g., "noise1")
            family: Operator family ("CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP")
            op_type: Operator type (e.g., "noise", "render")
            parent: Parent operator path (default: root_comp)
            **kwargs: Additional properties (flags, parameters, position)

        Returns:
            self (for chaining)

        Example:
            builder.add_operator("noise1", "CHOP", "noise", amplitude=0.5)
        """
        # Parse family
        if isinstance(family, str):
            family = OperatorFamily(family)

        # Validate operator type exists
        if not self.registry.validate_operator_type(family, op_type):
            raise ValueError(f"Unknown operator type: {family.value}:{op_type}")

        # Build path
        if parent is None:
            # Check if this IS the root component itself
            if name == self.metadata.root_comp:
                # Creating the root component - path is just /name
                path = f"/{name}"
            else:
                # Regular operator - parent defaults to root component
                parent = f"/{self.metadata.root_comp}"
                path = f"{parent}/{name}"
        else:
            # Parent specified explicitly
            if not parent.startswith("/"):
                parent = "/" + parent
            path = f"{parent}/{name}"

        # Extract parameters from kwargs
        parameters = kwargs.pop("parameters", {})

        # Handle parameter shortcuts (e.g., amplitude=0.5)
        for key, value in kwargs.copy().items():
            if key not in ["flags", "position", "children"]:
                parameters[key] = value
                kwargs.pop(key)

        # Create operator
        operator = Operator(
            path=path,
            name=name,
            family=family,
            type=op_type,
            parent=parent,
            flags=kwargs.pop("flags", Flags()),
            parameters=parameters,
            position=kwargs.pop("position", None),
            children=kwargs.pop("children", [])
        )

        # Store operator (by name for easy reference)
        self.operators[name] = operator
        self.operators[path] = operator  # Also by path

        return self

    def get_operator(self, name_or_path: str) -> Optional[Operator]:
        """
        Get operator by name or path.

        Args:
            name_or_path: Operator name or full path

        Returns:
            Operator or None if not found
        """
        return self.operators.get(name_or_path)

    def remove_operator(self, name_or_path: str) -> 'NetworkBuilder':
        """
        Remove operator from network.

        Args:
            name_or_path: Operator name or path

        Returns:
            self (for chaining)
        """
        operator = self.get_operator(name_or_path)
        if operator:
            # Remove from dict
            self.operators.pop(operator.name, None)
            self.operators.pop(operator.path, None)

            # Remove connections involving this operator
            self.connections = [
                conn for conn in self.connections
                if conn.source != operator.path and conn.target != operator.path
            ]

        return self

    def list_operators(self, family: Optional[Union[str, OperatorFamily]] = None) -> List[Operator]:
        """
        List all operators, optionally filtered by family.

        Args:
            family: Optional family filter

        Returns:
            List of operators
        """
        # Get unique operators (since we store by both name and path)
        operators = {op.path: op for op in self.operators.values()}.values()

        if family:
            if isinstance(family, str):
                family = OperatorFamily(family)
            return [op for op in operators if op.family == family]

        return list(operators)

    # =========================================================================
    # Connection Management
    # =========================================================================

    def connect(self,
                source: str,
                target: str,
                source_output: int = 0,
                target_input: int = 0) -> 'NetworkBuilder':
        """
        Connect two operators.

        Args:
            source: Source operator name or path
            target: Target operator name or path
            source_output: Output index (default: 0)
            target_input: Input index (default: 0)

        Returns:
            self (for chaining)

        Example:
            builder.connect("noise1", "null1")
        """
        # Resolve to full paths
        source_op = self.get_operator(source)
        target_op = self.get_operator(target)

        if not source_op:
            raise ValueError(f"Source operator not found: {source}")
        if not target_op:
            raise ValueError(f"Target operator not found: {target}")

        # Check type compatibility
        if source_op.family != target_op.family:
            # Allow some cross-family connections (e.g., MAT -> TOP)
            if not (source_op.family == OperatorFamily.MAT and
                   target_op.family in [OperatorFamily.TOP, OperatorFamily.SOP]):
                raise ValueError(
                    f"Cannot connect {source_op.family.value} to {target_op.family.value}"
                )

        # Create connection
        connection = Connection(
            source=source_op.path,
            target=target_op.path,
            source_output=source_output,
            target_input=target_input
        )

        self.connections.append(connection)

        # Add to target's inputs
        target_op.inputs.append(Input(
            index=target_input,
            src=source_op.name,  # Use local name
            src_path=source_op.path
        ))

        return self

    def disconnect(self, source: str, target: str) -> 'NetworkBuilder':
        """
        Remove connection between operators.

        Args:
            source: Source operator name or path
            target: Target operator name or path

        Returns:
            self (for chaining)
        """
        source_op = self.get_operator(source)
        target_op = self.get_operator(target)

        if source_op and target_op:
            # Remove connection
            self.connections = [
                conn for conn in self.connections
                if not (conn.source == source_op.path and conn.target == target_op.path)
            ]

            # Remove from inputs
            if target_op:
                target_op.inputs = [
                    inp for inp in target_op.inputs
                    if inp.src_path != source_op.path
                ]

        return self

    # =========================================================================
    # Parameter Management
    # =========================================================================

    def set_parameter(self,
                     operator: str,
                     param_name: str,
                     value: Any) -> 'NetworkBuilder':
        """
        Set operator parameter.

        Args:
            operator: Operator name or path
            param_name: Parameter name
            value: Parameter value

        Returns:
            self (for chaining)

        Example:
            builder.set_parameter("noise1", "amplitude", 0.5)
        """
        op = self.get_operator(operator)
        if not op:
            raise ValueError(f"Operator not found: {operator}")

        # Validate parameter exists
        if not self.registry.has_parameter(op.family, op.type, param_name):
            raise ValueError(
                f"Parameter '{param_name}' does not exist for {op.op_type}"
            )

        op.parameters[param_name] = value
        return self

    def set_text(self, operator: str, text: str) -> 'NetworkBuilder':
        """
        Set text content for a DAT operator.

        This is used to populate Table DAT, Text DAT, and Script DAT content.
        The text will be written as a binary .text file in the .toe/.tox output.

        Args:
            operator: Operator name or path
            text: Text content (e.g., TSV for Table DAT, code for Script DAT)

        Returns:
            self (for chaining)

        Example:
            # Table DAT with data
            builder.set_text("table1", "col1\\tcol2\\tcol3\\n0.1\\t0.2\\t0.3\\n0.4\\t0.5\\t0.6")

            # Text DAT with content
            builder.set_text("text1", "Hello World")

            # Script DAT with Python code
            builder.set_text("script1", "def onCook(dat):\\n    pass")
        """
        op = self.get_operator(operator)
        if not op:
            raise ValueError(f"Operator not found: {operator}")

        # Validate that this is a DAT operator
        if op.family != OperatorFamily.DAT:
            raise ValueError(
                f"set_text() only applies to DAT operators, but {operator} is {op.family.value}"
            )

        op.text = text
        return self

    def set_expression(self,
                      operator: str,
                      param_name: str,
                      expression: str,
                      language: str = "python") -> 'NetworkBuilder':
        """
        Set parameter expression.

        Args:
            operator: Operator name or path
            param_name: Parameter name
            expression: Expression string
            language: "python" or "tscript" (default: "python")

        Returns:
            self (for chaining)

        Example:
            builder.set_expression("noise1", "amplitude", "me.time.seconds")
        """
        op = self.get_operator(operator)
        if not op:
            raise ValueError(f"Operator not found: {operator}")

        # Create parameter value with expression
        param_value = ParameterValue(
            expression=expression,
            language=ExpressionLanguage(language),
            mode=ParameterMode.EXPRESSION
        )

        op.parameters[param_name] = param_value
        return self

    def get_parameter(self, operator: str, param_name: str) -> Any:
        """
        Get parameter value.

        Args:
            operator: Operator name or path
            param_name: Parameter name

        Returns:
            Parameter value
        """
        op = self.get_operator(operator)
        if not op:
            raise ValueError(f"Operator not found: {operator}")

        return op.parameters.get(param_name)

    # =========================================================================
    # Position Management
    # =========================================================================

    def set_position(self,
                    operator: str,
                    x: float,
                    y: float,
                    z: float = 0) -> 'NetworkBuilder':
        """
        Set operator viewport position.

        Args:
            operator: Operator name or path
            x: X coordinate
            y: Y coordinate
            z: Z coordinate (default: 0)

        Returns:
            self (for chaining)
        """
        op = self.get_operator(operator)
        if not op:
            raise ValueError(f"Operator not found: {operator}")

        if not op.position:
            op.position = Position()

        op.position.viewport = [x, y, z]
        return self

    def auto_layout(self, spacing: int = 200) -> 'NetworkBuilder':
        """
        Auto-layout operators in a grid.

        Args:
            spacing: Spacing between operators

        Returns:
            self (for chaining)
        """
        operators = self.list_operators()
        for idx, op in enumerate(operators):
            x = (idx % 5) * spacing
            y = (idx // 5) * spacing
            self.set_position(op.name, x, y)

        return self

    # =========================================================================
    # Validation & Export
    # =========================================================================

    def validate(self, verbose: bool = False) -> ValidationReport:
        """
        Validate network.

        Args:
            verbose: Print validation report

        Returns:
            ValidationReport
        """
        network = self.to_network()
        report = self.validator.validate(network, self.metadata.project_name)

        if verbose:
            from validation.pipeline import print_validation_report
            print_validation_report(report)

        return report

    def is_valid(self) -> bool:
        """
        Check if network is valid.

        Returns:
            True if valid
        """
        return self.validate().valid

    def to_network(self) -> TDNetwork:
        """
        Convert to TDNetwork object.

        Returns:
            TDNetwork
        """
        operators = self.list_operators()

        return TDNetwork(
            format_version="2.0.0",
            format_layer=FormatLayer.EXTENDED,
            metadata=self.metadata,
            operators=operators,
            connections=self.connections
        )

    def to_json(self, layer: str = "extended") -> Dict[str, Any]:
        """
        Export to JSON.

        Args:
            layer: Format layer ("builder", "extended", "canonical")

        Returns:
            JSON dict
        """
        network = self.to_network()

        if layer == "extended":
            # Use format converter's serialization (which handles the conversion properly)
            import json
            from dataclasses import asdict
            from enum import Enum

            def _serialize(obj):
                """Recursively serialize dataclasses and enums."""
                if isinstance(obj, Enum):
                    return obj.value
                elif hasattr(obj, '__dict__'):
                    result = {}
                    for key, value in obj.__dict__.items():
                        result[key] = _serialize(value)
                    return result
                elif isinstance(obj, dict):
                    return {k: _serialize(v) for k, v in obj.items()}
                elif isinstance(obj, (list, tuple)):
                    return [_serialize(item) for item in obj]
                else:
                    return obj

            return {
                "format_version": network.format_version,
                "format_layer": network.format_layer.value,
                "metadata": _serialize(network.metadata),
                "operators": [_serialize(op) for op in network.operators],
                "connections": [_serialize(conn) for conn in network.connections]
            }
        elif layer == "builder":
            return self.converter.to_builder(network)
        elif layer == "canonical":
            return self.converter.to_canonical(network)
        else:
            raise ValueError(f"Unknown layer: {layer}")

    def save_json(self, output_path: Path, layer: str = "extended"):
        """
        Save network to JSON file.

        Args:
            output_path: Output file path
            layer: Format layer
        """
        import json
        output_path = Path(output_path)

        json_data = self.to_json(layer)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2)

    def build_toe(self, output_path: Path, verbose: bool = True) -> Path:
        """
        Build .toe file from network.

        Args:
            output_path: Output .toe file path
            verbose: Print progress messages

        Returns:
            Path to created .toc file

        Example:
            builder.build_toe("output.toe")
            # Creates output.toe.dir/ and output.toe.toc
            # Run: toecollapse output.toe.toc
        """
        from builders.toe_builder import TOEBuilder

        # Validate first
        report = self.validate()
        if not report.valid:
            raise ValueError(
                f"Network has validation errors. Fix errors before building:\n" +
                "\n".join(f"  - {e.message}" for e in report.get_errors()[:5])
            )

        # Convert to TDNetwork
        network = self.to_network()

        # Build
        builder = TOEBuilder(network, verbose=verbose)
        return builder.build(output_path, mode="toe")

    def build_tox(self, output_path: Path, verbose: bool = True) -> Path:
        """
        Build .tox file from network.

        Args:
            output_path: Output .tox file path
            verbose: Print progress messages

        Returns:
            Path to created .toc file

        Example:
            builder.build_tox("component.tox")
        """
        from builders.toe_builder import TOEBuilder

        # Validate first
        report = self.validate()
        if not report.valid:
            raise ValueError(
                f"Network has validation errors. Fix errors before building:\n" +
                "\n".join(f"  - {e.message}" for e in report.get_errors()[:5])
            )

        # Convert to TDNetwork
        network = self.to_network()

        # Build
        builder = TOEBuilder(network, verbose=verbose)
        return builder.build(output_path, mode="tox")

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def clear(self) -> 'NetworkBuilder':
        """
        Clear all operators and connections.

        Returns:
            self (for chaining)
        """
        self.operators.clear()
        self.connections.clear()
        return self

    def __len__(self) -> int:
        """Get number of operators."""
        return len(self.list_operators())

    def __repr__(self) -> str:
        """String representation."""
        ops = len(self.list_operators())
        conns = len(self.connections)
        return f"<NetworkBuilder: {self.metadata.project_name} ({ops} ops, {conns} connections)>"


def quick_network(project_name: str) -> NetworkBuilder:
    """
    Create a new network builder quickly.

    Args:
        project_name: Project name

    Returns:
        NetworkBuilder

    Example:
        builder = quick_network("my_project")
    """
    return NetworkBuilder(project_name)

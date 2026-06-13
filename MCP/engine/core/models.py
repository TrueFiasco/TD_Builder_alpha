"""Data models for TouchDesigner networks.

These models represent the core data structures used throughout the unified system.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum


class FormatLayer(Enum):
    """JSON format layers."""
    BUILDER = "builder"      # AI-friendly, simple paths
    EXTENDED = "extended"    # Ground truth, complete data
    CANONICAL = "canonical"  # Compact, string-table compression
    LOSSLESS = "lossless"    # Perfect round-trip, all files


class OperatorFamily(Enum):
    """TouchDesigner operator families."""
    CHOP = "CHOP"  # Channel Operators
    TOP = "TOP"    # Texture Operators
    SOP = "SOP"    # Surface Operators
    MAT = "MAT"    # Material Operators
    DAT = "DAT"    # Data Operators
    COMP = "COMP"  # Component Operators
    POP = "POP"    # Particle Operators


class ExpressionLanguage(Enum):
    """Expression languages."""
    PYTHON = "python"
    TSCRIPT = "tscript"


class ParameterMode(Enum):
    """Parameter modes."""
    CONSTANT = "constant"    # Fixed value
    EXPRESSION = "expression"  # Dynamic expression
    EXPORT = "export"        # Exported to parent
    BIND = "bind"            # Bound to another parameter


@dataclass
class Position:
    """Operator position in network editor."""
    viewport: Optional[List[float]] = None  # [x, y, z]
    tile: Optional[List[int]] = None        # [x, y, width, height]


@dataclass
class Appearance:
    """Visual appearance settings."""
    color: Optional[List[float]] = None     # [r, g, b] 0-1
    node_shape: Optional[str] = None
    comment: Optional[str] = None


@dataclass
class Flags:
    """Operator flags."""
    display: bool = False   # Blue flag
    render: bool = False    # Purple flag
    bypass: bool = False    # Bypass cooking
    lock: bool = False      # Lock parameters
    viewer: bool = False    # Viewer active
    current: bool = False   # Current operator


@dataclass
class ParameterValue:
    """Parameter with optional expression."""
    value: Optional[Any] = None
    expression: Optional[str] = None
    language: ExpressionLanguage = ExpressionLanguage.PYTHON
    mode: ParameterMode = ParameterMode.CONSTANT
    td_mode: Optional[int] = None

    def is_expression(self) -> bool:
        """Check if this parameter has an expression."""
        return self.expression is not None and self.mode == ParameterMode.EXPRESSION


@dataclass
class Input:
    """Operator input connection."""
    index: int                      # Input index (0-based)
    src: str                        # Source operator name or path
    src_path: Optional[str] = None  # Absolute source path
    src_output: int = 0             # Source output index


@dataclass
class ExtraFile:
    """Extra file attached to operator."""
    content: str
    is_binary: bool = False
    encoding: str = "utf-8"


@dataclass
class Operator:
    """TouchDesigner operator with all properties."""
    path: str                                           # Absolute path
    name: str                                           # Operator name
    family: OperatorFamily                              # Operator family
    type: str                                           # Specific type

    parent: Optional[str] = None                        # Parent path
    op_type: Optional[str] = None                       # FAMILY:type

    position: Optional[Position] = None
    appearance: Optional[Appearance] = None
    flags: Flags = field(default_factory=Flags)

    parameters: Dict[str, Union[Any, ParameterValue]] = field(default_factory=dict)
    inputs: List[Input] = field(default_factory=list)
    children: List[str] = field(default_factory=list)

    extra_files: Dict[str, ExtraFile] = field(default_factory=dict)
    custom_data: Dict[str, Any] = field(default_factory=dict)

    text: Optional[str] = None  # Text content for DAT operators (tableDAT, textDAT, scriptDAT)

    def __post_init__(self):
        """Ensure op_type is set."""
        if self.op_type is None:
            self.op_type = f"{self.family.value}:{self.type}"


@dataclass
class Connection:
    """Wire connection between operators."""
    source: str                 # Source operator path (from)
    target: str                 # Target operator path (to)
    source_output: int = 0      # Source output index
    target_input: int = 0       # Target input index


@dataclass
class Metadata:
    """Project metadata."""
    project_name: str
    mode: str  # "toe" or "tox"

    root_comp: str = "project1"
    td_version: Optional[str] = None
    build_number: Optional[str] = None
    build_date: Optional[str] = None
    cookrate: int = 60
    realtime: bool = True

    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    author: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class LosslessData:
    """Layer 4: Complete file preservation data."""
    raw_files: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    toc_order: List[str] = field(default_factory=list)
    toc_raw_lines: List[str] = field(default_factory=list)
    toc_disk_paths: Dict[str, str] = field(default_factory=dict)


@dataclass
class CanonicalData:
    """Layer 3: String table compression data."""
    string_table: List[str] = field(default_factory=list)
    compressed_nodes: List[Any] = field(default_factory=list)


@dataclass
class Statistics:
    """Network statistics."""
    total_operators: int = 0
    total_connections: int = 0
    total_parameters: int = 0
    max_depth: int = 0
    by_family: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)


@dataclass
class TDNetwork:
    """Complete TouchDesigner network representation."""
    format_version: str
    format_layer: FormatLayer
    metadata: Metadata
    operators: List[Operator]

    connections: List[Connection] = field(default_factory=list)
    lossless_data: Optional[LosslessData] = None
    canonical_data: Optional[CanonicalData] = None
    statistics: Optional[Statistics] = None

    def get_operator(self, path: str) -> Optional[Operator]:
        """Get operator by path."""
        for op in self.operators:
            if op.path == path:
                return op
        return None

    def get_operators_by_family(self, family: OperatorFamily) -> List[Operator]:
        """Get all operators of a specific family."""
        return [op for op in self.operators if op.family == family]

    def get_connections_from(self, operator_path: str) -> List[Connection]:
        """Get all connections from an operator."""
        return [conn for conn in self.connections if conn.source == operator_path]

    def get_connections_to(self, operator_path: str) -> List[Connection]:
        """Get all connections to an operator."""
        return [conn for conn in self.connections if conn.target == operator_path]


@dataclass
class ParamSpec:
    """Parameter specification from operator documentation."""
    code: str                       # Internal parameter code
    display_name: str               # Display name
    description: str                # Parameter description
    section: str                    # UI section

    param_type: Optional[str] = None    # int, float, str, menu, toggle, etc.
    default: Optional[Any] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    menu_options: Optional[List[str]] = None
    required: bool = False


@dataclass
class OperatorSpec:
    """Complete operator specification from knowledge base."""
    name: str                       # Display name
    family: OperatorFamily          # Operator family
    op_type: str                    # FAMILY:type

    summary: Optional[str] = None   # Description
    parameters: List[ParamSpec] = field(default_factory=list)

    min_inputs: int = 0
    max_inputs: int = 1
    min_version: Optional[str] = None
    deprecated: bool = False
    is_comp: bool = False           # Can contain children

    def get_parameter(self, code: str) -> Optional[ParamSpec]:
        """Get parameter by code."""
        for param in self.parameters:
            if param.code == code:
                return param
        return None

    def has_parameter(self, code: str) -> bool:
        """Check if parameter exists."""
        return any(param.code == code for param in self.parameters)


@dataclass
class ValidationError:
    """Validation error."""
    code: str                       # Error code (e.g., UNKNOWN_OPERATOR_TYPE)
    stage: str                      # Which stage caught it
    severity: str                   # "error" or "warning"
    message: str                    # Human-readable message
    location: Optional[str] = None  # Where in JSON (e.g., "operators[2].type")
    path: Optional[str] = None      # Operator path if applicable
    suggestion: Optional[str] = None  # How to fix


@dataclass
class StageReport:
    """Validation stage report."""
    stage: str
    status: str  # "PASS" or "FAIL"
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Complete validation report."""
    overall_status: str  # "PASS" or "FAIL"
    timestamp: str
    network: str

    summary: Dict[str, int] = field(default_factory=dict)
    stages: List[StageReport] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        """Check if network is valid."""
        return self.overall_status == "PASS"

    @property
    def total_errors(self) -> int:
        """Get total error count."""
        return sum(len(stage.errors) for stage in self.stages)

    @property
    def total_warnings(self) -> int:
        """Get total warning count."""
        return sum(len(stage.warnings) for stage in self.stages)

    def get_errors(self) -> List[ValidationError]:
        """Get all errors from all stages."""
        errors = []
        for stage in self.stages:
            errors.extend(stage.errors)
        return errors

    def get_warnings(self) -> List[ValidationError]:
        """Get all warnings from all stages."""
        warnings = []
        for stage in self.stages:
            warnings.extend(stage.warnings)
        return warnings

# TouchDesigner Unified System - Architecture

## System Overview

The TouchDesigner Unified System is a layered architecture for building, validating, and managing TouchDesigner networks programmatically.

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface Layer                     │
├──────────────────────┬──────────────────────────────────────┤
│   CLI Tools          │   Python API                          │
│   - td-validate      │   - NetworkBuilder                    │
│   - td-convert       │   - quick_network()                   │
│   - td-build         │                                       │
└──────────────────────┴──────────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────┐
│                      Core Services Layer                     │
├──────────────────────┬──────────────────────────────────────┤
│  ValidationPipeline  │  Format Converter                     │
│  (5 stages)          │  (3 format layers)                    │
└──────────────────────┴──────────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────┐
│                    Foundation Layer                         │
├──────────────────────┬──────────────────────────────────────┤
│  OperatorRegistry    │  Data Models                          │
│  (670 operators)     │  (TDNetwork, Operator, Connection)    │
└──────────────────────┴──────────────────────────────────────┘
```

## Component Architecture

### 1. Foundation Layer

#### OperatorRegistry

**Purpose:** Central registry of all TouchDesigner operators

**Location:** `core/operator_registry.py`

**Key Responsibilities:**
- Load operator specifications from `td_universal_parsed.json`
- Provide operator lookup by family and type
- Supply parameter schemas and defaults
- Validate operator types and parameters

**API:**
```python
registry = OperatorRegistry()

# Get operator spec
spec = registry.get_operator_spec("CHOP", "noise")

# Check if operator exists
exists = registry.has_operator("CHOP", "noise")

# Get all operators in family
chops = registry.get_operators_by_family("CHOP")
```

**Data Source:**
- `C:\TD_Projects\kb_pipeline\data\wiki_docs\td_universal_parsed.json`
- 670 operators across 5 families (CHOP, TOP, SOP, MAT, COMP)

#### Data Models

**Purpose:** Unified data structures for network representation

**Location:** `core/models.py`

**Key Classes:**
```python
@dataclass
class Operator:
    path: str
    name: str
    family: OperatorFamily
    type: str
    op_type: str
    parent: Optional[str]
    position: Position
    flags: Flags
    parameters: Dict[str, Any]
    inputs: List[OperatorInput]
    children: List[str]

@dataclass
class Connection:
    from_path: str
    to_path: str
    to_input: int

@dataclass
class TDNetwork:
    metadata: Metadata
    operators: List[Operator]
    connections: List[Connection]
    lossless_data: Optional[LosslessData]
```

**Design Principles:**
- Immutable where possible (using dataclasses)
- Type-safe (using type hints)
- Serializable (to/from JSON)
- Extensible (optional fields for future features)

### 2. Core Services Layer

#### ValidationPipeline

**Purpose:** Multi-stage validation of TD networks

**Location:** `validation/pipeline.py`

**Architecture:**
```
Input (TDNetwork)
    ↓
┌─────────────────────────┐
│ Stage 1: Schema         │ ← Validates structure
├─────────────────────────┤
│ Stage 2: Semantic       │ ← Validates operators/params
├─────────────────────────┤
│ Stage 3: Reference      │ ← Validates connections/refs
├─────────────────────────┤
│ Stage 4: Logical        │ ← Validates logic/cycles
├─────────────────────────┤
│ Stage 5: TD Rules       │ ← Validates TD-specific rules
└─────────────────────────┘
    ↓
Output (ValidationReport)
```

**Validation Stages:**

1. **SchemaValidator** (`validation/schema_validator.py`)
   - Checks JSON structure
   - Validates required fields
   - Validates data types

2. **SemanticValidator** (`validation/semantic_validator.py`)
   - Validates operators exist in registry
   - Validates parameters for each operator
   - Checks parameter types

3. **ReferenceValidator** (`validation/reference_validator.py`)
   - Validates connection sources exist
   - Validates connection targets exist
   - Validates parent paths

4. **LogicalValidator** (`validation/logical_validator.py`)
   - Validates family compatibility
   - Detects circular dependencies
   - Checks input/output compatibility

5. **TDRulesValidator** (`validation/td_rules_validator.py`)
   - Validates family-specific rules
   - Checks version compatibility
   - Validates special operator requirements

**Output:**
```python
@dataclass
class ValidationReport:
    overall_status: str  # "PASS" or "FAIL"
    timestamp: str
    network: str
    stages: List[StageReport]

    @property
    def valid(self) -> bool

    @property
    def total_errors(self) -> int

    def get_errors(self) -> List[ValidationError]
    def get_warnings(self) -> List[ValidationError]
```

#### FormatConverter

**Purpose:** Convert between format layers

**Location:** `core/format_converter.py`

**Format Layers:**

```
Builder JSON (AI-Friendly)
    ↕
Extended JSON (Ground Truth)
    ↕
Canonical JSON (Compact)
```

**Conversion Matrix:**

| From      | To        | Method                  |
|-----------|-----------|-------------------------|
| Builder   | Extended  | `from_builder()`        |
| Extended  | Builder   | `to_builder()`          |
| Extended  | Canonical | `to_canonical()`        |
| Canonical | Extended  | `from_canonical()`      |
| Builder   | Canonical | via Extended (hub)      |
| Canonical | Builder   | via Extended (hub)      |

**Design Pattern:** Hub-and-Spoke
- Extended format is the hub
- All conversions go through Extended
- Maintains single source of truth

### 3. User Interface Layer

#### NetworkBuilder API

**Purpose:** Fluent Python API for building networks

**Location:** `api/network_builder.py`

**Design Patterns:**
- **Builder Pattern**: Method chaining for fluent API
- **Facade Pattern**: Simplifies complex subsystems
- **Template Method**: Common workflow patterns

**Method Categories:**

1. **Construction**
   - `add_operator()` - Add operator to network
   - `connect()` - Connect operators
   - `set_parameter()` - Set parameter values
   - `set_expression()` - Set parameter expressions

2. **Validation**
   - `validate()` - Full validation report
   - `is_valid()` - Quick validation check
   - `can_connect()` - Check connection validity

3. **Management**
   - `list_operators()` - List all operators
   - `get_operator()` - Get operator by name
   - `remove_operator()` - Remove operator

4. **Export**
   - `to_json()` - Export to JSON (any layer)
   - `save_json()` - Save JSON to file
   - `build_toe()` - Build .toe file
   - `build_tox()` - Build .tox file

**Example Flow:**
```python
NetworkBuilder("project")
    → add_operator()
    → connect()
    → set_parameter()
    → validate()  # Uses ValidationPipeline
    → build_toe() # Uses TOEBuilder
```

#### CLI Tools

**Purpose:** Command-line interface for common operations

**Location:** `cli/`

**Tools:**
- `td-validate.py` - Network validation
- `td-convert.py` - Format conversion
- `td-build.py` - File building

**Architecture:**
```
CLI Tool (argparse)
    ↓
Parse Arguments
    ↓
Initialize Components (Registry, Converter, Validator)
    ↓
Execute Operation
    ↓
Format Output (JSON or human-readable)
    ↓
Exit with Status Code
```

**Design Principles:**
- **Single Responsibility**: Each tool does one thing
- **Unix Philosophy**: Composable, pipeable
- **Exit Codes**: Standard codes for automation
- **Output Modes**: JSON for scripts, text for humans

## Data Flow

### Complete Pipeline

```
User Code
    ↓
NetworkBuilder.add_operator()
    ↓
Internal State (operators[], connections[])
    ↓
NetworkBuilder.validate()
    ↓
FormatConverter.from_builder()
    ↓
TDNetwork (data model)
    ↓
ValidationPipeline.validate()
    ↓
ValidationReport (errors, warnings)
    ↓
NetworkBuilder.build_toe()
    ↓
TOEBuilder.build()
    ↓
.toe.dir + .toe.toc files
    ↓
toecollapse (TD tool)
    ↓
.toe file
```

### Format Conversion Flow

```
Input JSON (any layer)
    ↓
Parse JSON
    ↓
Detect Format Layer
    ↓
Convert to Extended (hub)
    ↓
TDNetwork (canonical representation)
    ↓
Convert to Target Layer
    ↓
Output JSON (target layer)
```

## Design Decisions

### 1. Why Dataclasses?

**Decision:** Use Python dataclasses for models

**Rationale:**
- Type safety (helps catch bugs early)
- Automatic `__init__`, `__repr__`, `__eq__`
- Easy serialization with `asdict()`
- IDE support (autocomplete, type checking)

### 2. Why Hub-and-Spoke for Formats?

**Decision:** Extended format as central hub

**Rationale:**
- Single source of truth
- Simplified conversion logic (N formats → N converters, not N²)
- Easier to add new formats
- Clear data model (Extended = complete representation)

### 3. Why 5 Validation Stages?

**Decision:** Multi-stage validation pipeline

**Rationale:**
- Separation of concerns (each stage focuses on one aspect)
- Early failure (schema errors before semantic errors)
- Clear error messages (know which stage failed)
- Extensible (easy to add new stages)

### 4. Why Fluent API?

**Decision:** Method chaining for NetworkBuilder

**Rationale:**
- Readable code (reads like English)
- Concise (less boilerplate)
- Discoverable (IDE autocomplete shows next methods)
- Common pattern (familiar to developers)

### 5. Why Separate CLI Tools?

**Decision:** Three separate CLI tools vs one multi-command tool

**Rationale:**
- Unix philosophy (do one thing well)
- Simpler help text (focused on one operation)
- Easier to compose in scripts
- Clear naming (td-validate vs td validate)

## Performance Characteristics

### Validation

- **Small networks (10 ops)**: < 5ms
- **Medium networks (100 ops)**: < 30ms
- **Large networks (1000 ops)**: < 300ms

### Format Conversion

- **Builder → Canonical**: ~500ms (100 ops)
- **Canonical → Extended**: ~500ms (100 ops)

### File Building

- **Small .toe (2 ops)**: ~500ms
- **Medium .toe (50 ops)**: ~550ms

**Note:** Initial load times include registry initialization (~400ms)

## Extension Points

### Adding New Operators

```python
# Add to td_universal_parsed.json
{
    "family": "CHOP",
    "type": "custom",
    "display_name": "Custom CHOP",
    "parameters": [...]
}

# Registry will auto-load on next initialization
```

### Adding New Validation Stages

```python
# Create new validator
class CustomValidator:
    def validate(self, network: TDNetwork) -> StageReport:
        # Custom validation logic
        pass

# Add to pipeline
pipeline = ValidationPipeline(registry)
pipeline.add_stage("custom", CustomValidator())
```

### Adding New Format Layers

```python
# Implement converters
class FormatConverter:
    def to_custom(self, network: TDNetwork) -> Dict:
        # Convert Extended → Custom
        pass

    def from_custom(self, data: Dict) -> TDNetwork:
        # Convert Custom → Extended
        pass
```

## Testing Strategy

### Unit Tests

- Test individual components in isolation
- Mock dependencies
- Fast execution (< 1s per test)

**Example:** `tests/test_registry.py`

### Integration Tests

- Test component interactions
- Use real dependencies
- Medium execution (1-5s per test)

**Example:** `tests/test_builder_api.py`

### End-to-End Tests

- Test complete workflows
- No mocks, real files
- Slower execution (5-30s per test)

**Example:** `tests/test_e2e.py`

### Performance Tests

- Measure execution time
- Benchmark key operations
- Track regressions

**Example:** `tests/test_performance.py`

## Security Considerations

### Input Validation

- All user input validated before processing
- JSON schema validation prevents malformed data
- Parameter type checking prevents injection

### File Operations

- Paths sanitized to prevent directory traversal
- File permissions checked before writing
- Temporary files cleaned up

### Error Handling

- Sensitive information not exposed in error messages
- Stack traces only in verbose mode
- Graceful degradation

## Future Enhancements

### Planned Features

1. **Extended JSON Deserialization** - Full round-trip support
2. **Connection Export** - Include connections in builder JSON
3. **Performance Optimization** - Reduce initialization time
4. **Web API** - REST API for validation/conversion
5. **GUI Tool** - Visual network builder

### Known Limitations

1. **Canonical → Builder** - Incomplete round-trip
2. **Connections in Builder JSON** - Not always exported
3. **Binary Files** - BASIC mode doesn't generate binary content
4. **Requires toecollapse** - Manual step after building

## Conclusion

The Touchdesigner Unified System provides a robust, well-architected foundation for programmatic TD network management. Its layered design, comprehensive validation, and flexible format support make it suitable for both simple scripts and complex automation workflows.

**Key Strengths:**
- ✅ Comprehensive validation (5 stages)
- ✅ Multiple format layers (3 formats)
- ✅ Fluent Python API (NetworkBuilder)
- ✅ CLI tools for automation
- ✅ Excellent performance (< 300ms for 1000 ops)

**Next Steps:**
- Implement extended JSON deserialization
- Optimize initialization time
- Add more examples and templates

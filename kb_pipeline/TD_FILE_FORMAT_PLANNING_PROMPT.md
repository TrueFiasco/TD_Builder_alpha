# TouchDesigner File Format - Builder Rules & Validation System

**Copy this entire prompt into a new planning session to develop the TD file builder specification**

---

## Project Goal

Develop a **complete, formal specification and rule set** that ensures a builder can **always generate valid TouchDesigner files** (.tox/.toe) from JSON input.

### Success Criteria
1. **100% valid output** - JSON → .tox/.toe conversion never fails
2. **Parseable by TouchDesigner** - Generated files load without errors
3. **Comprehensive validation** - Catch all errors before file generation
4. **Well-documented rules** - Clear specification for all components
5. **Test coverage** - Validation against real TD file examples

---

## Background: TouchDesigner File Format

### File Structure Overview

TouchDesigner files (.toe = project, .tox = component) are **ZIP archives** containing:

```
component.tox/
├── component.toc          # Table of contents (XML/JSON-like format)
├── component.dir/         # Directory containing component data
│   ├── node1/
│   │   ├── node1.toc
│   │   └── node1.dir/
│   ├── node2/
│   └── ...
├── resources/             # External files (images, videos, etc.)
└── metadata files
```

### Key Components

1. **.toc (Table of Contents)**
   - Hierarchical structure defining operators and connections
   - Contains operator types, parameters, parent-child relationships
   - Stores network layout (position, size, viewer state)

2. **.dir/ (Directory)**
   - Contains nested component data
   - Recursive structure for COMP operators
   - Includes internal networks

3. **Metadata**
   - Version information
   - Build number compatibility
   - Timestamps, author info

### Current Knowledge State

We have a **knowledge base** with:
- **673 operators** with full documentation
- **1,210 real-world examples** (snippets)
- **121 palette components** (.tox files)
- **Parameter schemas** for all operators
- **Connection patterns** from 16,814 node graph

**Knowledge base location:** `C:\TD_Projects\kb_pipeline\`

---

## Current Problem

**We need to generate TD files programmatically** for:
- AI-assisted project generation
- Automated network creation from user descriptions
- Template systems
- Testing and validation

**Challenge:** TouchDesigner file format is complex and undocumented
- No official specification exists
- Format has evolved over multiple versions
- Subtle rules can cause files to fail loading
- Parameter types and validation rules vary by operator

---

## Research Phase Requirements

### 1. Reverse Engineer .tox/.toe Format

**Analyze existing files:**
- Extract and examine palette .tox files from knowledge base (121 files)
- Identify common patterns in .toc structure
- Document .dir/ hierarchy rules
- Map parameter types to storage formats

**Key questions to answer:**
1. What is the exact structure of a .toc file?
2. How are operators referenced (IDs, paths, names)?
3. How are connections stored (wire format)?
4. What metadata is required vs. optional?
5. How are parameters serialized by type?
6. What are the version compatibility rules?
7. How are external resources referenced?

### 2. Analyze Palette Examples

**Extract from knowledge base:**
```
C:\TD_Projects\kb_pipeline\data\palette_semantic\
- 529 palette JSON files with metadata
- Operator combinations that are known to work
- Real-world parameter configurations
```

**What to extract:**
- Common operator families used together
- Parameter value patterns (ranges, defaults, types)
- Network layout conventions
- Naming patterns

### 3. Study Operator Documentation

**From knowledge base:**
```
C:\TD_Projects\kb_pipeline\data\wiki_docs\td_universal_parsed.json
- 673 operators with full parameter schemas
- Parameter types: int, float, str, toggle, menu, etc.
- Parameter constraints (min, max, menu options)
- Required vs. optional parameters
```

**Extract:**
- Parameter type definitions
- Validation rules per parameter type
- Default values
- Inter-parameter dependencies (e.g., if mode=X, then param Y is required)

---

## Specification Development

### 1. Define JSON Schema for TD Projects

Create a **formal JSON schema** that represents a valid TD project:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TouchDesigner Project Schema",
  "type": "object",
  "required": ["version", "build", "operators", "connections"],
  "properties": {
    "version": {
      "type": "string",
      "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$",
      "description": "TouchDesigner version (e.g., 2023.11760)"
    },
    "build": {
      "type": "integer",
      "minimum": 11000,
      "description": "Build number"
    },
    "operators": {
      "type": "array",
      "items": { "$ref": "#/definitions/operator" }
    },
    "connections": {
      "type": "array",
      "items": { "$ref": "#/definitions/connection" }
    }
  },
  "definitions": {
    "operator": { ... },
    "connection": { ... },
    "parameter": { ... }
  }
}
```

**Must define schemas for:**
- Operators (type, name, position, parameters, parent)
- Connections (source, target, wire type)
- Parameters (name, type, value, expression mode)
- Networks (hierarchy, layout, viewer state)
- Resources (external files, paths)

### 2. Builder Rules Specification

Create **mandatory rules** the builder must follow:

#### Naming Rules
- Operator names must be valid identifiers
- No duplicate names within same network level
- Reserved keywords to avoid
- Naming conventions by operator family

#### Hierarchy Rules
- Valid parent-child relationships
- COMP operators can contain children
- Non-COMP operators cannot have children
- Root level requirements

#### Connection Rules
- Valid connection types by operator family:
  - TOP → TOP (texture)
  - CHOP → CHOP (channel)
  - SOP → SOP (surface)
  - DAT → DAT (data)
  - MAT → TOP/CHOP (material)
- Wire routing (input index, output index)
- Feedback loop constraints
- Connection to parameter (export/bind)

#### Parameter Rules
- Type validation (int, float, string, menu, toggle, etc.)
- Range validation (min/max for numeric types)
- Menu validation (value must be in allowed list)
- Expression mode (constant, expression, export)
- Required vs. optional parameters
- Default value fallback

#### Version Compatibility Rules
- Operator availability by version
- Parameter changes across versions
- Deprecated operators/parameters
- Minimum build number requirements

### 3. Validation System Design

Create **multi-stage validation**:

#### Stage 1: JSON Schema Validation
- Validate against JSON schema
- Check all required fields present
- Check data types correct
- Catch structural errors

#### Stage 2: Semantic Validation
- Verify operator types exist
- Verify parameters exist for operator type
- Check parameter values valid for type
- Verify connections are compatible

#### Stage 3: Reference Validation
- All operator references resolve
- Parent operators exist
- Connection endpoints exist
- No dangling references

#### Stage 4: Logical Validation
- No circular parent-child relationships
- Connection types match (TOP→TOP, etc.)
- No duplicate operator names in scope
- Resource files exist (if external)

#### Stage 5: TouchDesigner-Specific Rules
- Version compatibility checks
- Build number compatibility
- Operator family-specific rules
- Layout constraints (position, viewer state)

---

## Implementation Requirements

### 1. Builder API Specification

Define the **builder interface**:

```python
class TDProjectBuilder:
    """
    Builder for creating valid TouchDesigner projects programmatically.

    Ensures all generated projects are valid and loadable in TD.
    """

    def __init__(self, version: str, build: int):
        """Initialize builder with TD version."""
        pass

    def add_operator(self,
                     op_type: str,
                     name: str,
                     parent: str = "/project1",
                     parameters: dict = None,
                     position: tuple = (0, 0)) -> str:
        """
        Add operator to project.

        Args:
            op_type: Operator type (e.g., "moviefileinTOP", "noiseTOP")
            name: Unique operator name
            parent: Path to parent operator
            parameters: Dict of parameter values
            position: (x, y) position in network

        Returns:
            Operator path (e.g., "/project1/moviefilein1")

        Raises:
            ValidationError: If operator invalid
        """
        # Validate operator type exists
        # Validate name is unique in parent
        # Validate parameters
        # Add to internal structure
        pass

    def connect(self,
                source: str,
                target: str,
                source_index: int = 0,
                target_index: int = 0) -> None:
        """
        Create connection between operators.

        Args:
            source: Source operator path
            target: Target operator path
            source_index: Output index (default 0)
            target_index: Input index (default 0)

        Raises:
            ValidationError: If connection invalid
        """
        # Validate operators exist
        # Validate connection types compatible
        # Validate indices valid
        # Add to connections
        pass

    def validate(self) -> ValidationResult:
        """
        Validate entire project against all rules.

        Returns:
            ValidationResult with errors/warnings
        """
        # Run all validation stages
        # Return comprehensive result
        pass

    def build(self, output_path: str) -> None:
        """
        Build .tox/.toe file.

        Args:
            output_path: Path to output file

        Raises:
            ValidationError: If validation fails
        """
        # Validate project
        # Generate .toc structure
        # Create .dir/ hierarchy
        # Package as ZIP
        # Write to file
        pass
```

### 2. Validation Result Format

Define **comprehensive validation output**:

```python
@dataclass
class ValidationResult:
    """Result of project validation."""

    valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationWarning]

    def summary(self) -> str:
        """Human-readable summary."""
        pass

@dataclass
class ValidationError:
    """Validation error that prevents building."""

    stage: str  # "schema", "semantic", "reference", etc.
    rule: str   # Specific rule violated
    location: str  # Where error occurred (operator path, parameter)
    message: str
    suggestion: str  # How to fix

@dataclass
class ValidationWarning:
    """Non-fatal validation warning."""

    category: str
    location: str
    message: str
```

### 3. Operator Type Registry

Create **operator metadata registry** from knowledge base:

```python
class OperatorRegistry:
    """
    Registry of all valid operator types and their schemas.

    Built from knowledge base (673 operators).
    """

    def get_operator_schema(self, op_type: str) -> OperatorSchema:
        """Get schema for operator type."""
        pass

    def validate_parameter(self,
                          op_type: str,
                          param_name: str,
                          value: Any) -> bool:
        """Validate parameter value for operator type."""
        pass

    def get_default_parameters(self, op_type: str) -> dict:
        """Get default parameter values."""
        pass

    def is_comp(self, op_type: str) -> bool:
        """Check if operator is a COMP (can contain children)."""
        pass

    def get_family(self, op_type: str) -> str:
        """Get operator family (TOP, CHOP, SOP, DAT, COMP, etc.)."""
        pass

@dataclass
class OperatorSchema:
    """Schema for an operator type."""

    op_type: str
    family: str  # TOP, CHOP, SOP, DAT, COMP, MAT, POP
    is_comp: bool
    parameters: List[ParameterSchema]
    min_version: str
    deprecated: bool = False

@dataclass
class ParameterSchema:
    """Schema for a parameter."""

    name: str
    code: str  # Internal parameter code
    type: str  # int, float, str, menu, toggle, etc.
    default: Any
    required: bool = False
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    menu_options: Optional[List[str]] = None
```

---

## Testing Strategy

### 1. Unit Tests

Test each validation rule:

```python
def test_operator_name_uniqueness():
    """Test that duplicate operator names are rejected."""
    builder = TDProjectBuilder("2023.11760", 11760)
    builder.add_operator("noiseTOP", "noise1")

    with pytest.raises(ValidationError, match="duplicate name"):
        builder.add_operator("noiseTOP", "noise1")

def test_invalid_connection_types():
    """Test that TOP→CHOP connection is rejected."""
    builder = TDProjectBuilder("2023.11760", 11760)
    builder.add_operator("noiseTOP", "noise1")
    builder.add_operator("mathCHOP", "math1")

    with pytest.raises(ValidationError, match="incompatible types"):
        builder.connect("/project1/noise1", "/project1/math1")

def test_parameter_type_validation():
    """Test that invalid parameter types are rejected."""
    builder = TDProjectBuilder("2023.11760", 11760)

    with pytest.raises(ValidationError, match="expected float"):
        builder.add_operator("noiseTOP", "noise1",
                           parameters={"amplitude": "not a number"})
```

### 2. Integration Tests

Test with real palette examples:

```python
def test_palette_component_roundtrip():
    """Test that we can parse and rebuild palette components."""
    # Load palette .tox file
    palette_path = "C:/TD_Projects/kb_pipeline/data/palette_semantic/audioAnalysis.json"

    # Parse into JSON
    project_json = parse_tox_to_json(palette_path)

    # Validate JSON
    result = validate_project_json(project_json)
    assert result.valid, f"Validation failed: {result.errors}"

    # Build back to .tox
    builder = TDProjectBuilder.from_json(project_json)
    output_path = "/tmp/audioAnalysis_rebuilt.tox"
    builder.build(output_path)

    # Verify file is valid
    assert is_valid_tox(output_path)
```

### 3. Validation Test Suite

Create comprehensive test suite:

- **Positive tests**: Valid projects that should pass
- **Negative tests**: Invalid projects that should fail with specific errors
- **Edge cases**: Boundary conditions, empty projects, maximum complexity
- **Version compatibility**: Test across TD versions
- **Real-world examples**: All 121 palette components + 1,210 snippets

---

## Deliverables Required

Please provide a comprehensive plan that includes:

### 1. **File Format Specification**
   - Complete .toc structure documentation
   - .dir/ hierarchy rules
   - Metadata requirements
   - ZIP archive structure
   - Version compatibility matrix

### 2. **JSON Schema Definition**
   - Formal JSON schema for TD projects
   - All operator types
   - All parameter types
   - All connection types
   - Validation constraints

### 3. **Builder Rules**
   - Comprehensive list of ALL rules
   - Organized by category (naming, hierarchy, connections, parameters)
   - Priority levels (error vs. warning)
   - Examples for each rule

### 4. **Validation Architecture**
   - Multi-stage validation design
   - Validation algorithm for each stage
   - Error reporting format
   - Performance considerations

### 5. **Operator Registry Design**
   - How to extract schemas from knowledge base
   - Data structures for operator metadata
   - Parameter type system
   - Version compatibility tracking

### 6. **Builder API**
   - Complete API specification
   - Usage examples
   - Error handling strategy
   - Extension points for custom operators

### 7. **Testing Plan**
   - Unit test coverage strategy
   - Integration test scenarios
   - Validation test matrix
   - Performance benchmarks

### 8. **Implementation Roadmap**
   - Phase 1: Research & reverse engineering
   - Phase 2: Schema definition
   - Phase 3: Validation system
   - Phase 4: Builder implementation
   - Phase 5: Testing & validation
   - Phase 6: Documentation

### 9. **Known Limitations & Edge Cases**
   - Features that cannot be generated
   - Unsupported operator types
   - Version-specific issues
   - Workarounds for complex cases

### 10. **Example Implementations**
   - Simple project: "Noise TOP → Render TOP"
   - Medium complexity: "Audio visualization network"
   - Complex: "Multi-level COMP hierarchy with connections"

---

## Available Resources

### Knowledge Base Files

**Operator Documentation:**
```
C:\TD_Projects\kb_pipeline\data\wiki_docs\td_universal_parsed.json
- 673 operators
- Full parameter schemas
- Families: TOP, CHOP, SOP, DAT, COMP, MAT, POP
```

**Palette Components:**
```
C:\TD_Projects\kb_pipeline\data\palette_semantic\
- 529 palette JSON files
- Real-world working examples
- Operator combinations
```

**Real Examples:**
```
C:\TD_Projects\kb_pipeline\data\snippets\semantic\
- 1,210 snippet JSONs
- Practical operator usage
- Parameter configurations
```

**Palette Wiki Docs:**
```
C:\TD_Projects\kb_pipeline\data\palette_wiki\
- 182 HTML files
- Descriptions and usage
```

**Knowledge Graph:**
```
C:\TD_Projects\kb_pipeline\graph\td_knowledge_graph_simple.json
- 16,814 nodes
- 18,084 edges
- Operator relationships
- Parameter relationships
```

### Existing Analysis Tools

```
C:\TD_Projects\kb_pipeline\
- hybrid_retrieval_enhanced.py - Search operators/examples
- enrich_metadata.py - Semantic tags and categories
- test_search.py - Query knowledge base
```

---

## Research Questions to Answer

1. **File Format:**
   - What is the complete structure of a .toc file?
   - How are operators serialized?
   - How are connections represented?
   - What metadata is required?

2. **Validation:**
   - What makes a TD file "valid"?
   - What causes loading errors?
   - What are recoverable vs. fatal errors?
   - How does TD validate on load?

3. **Compatibility:**
   - How do different TD versions affect file format?
   - What operators are version-specific?
   - How are deprecated features handled?
   - What's the minimum supported version?

4. **Operators:**
   - What are all valid operator types?
   - What parameters are required vs. optional?
   - What are parameter type constraints?
   - What are valid parent-child relationships?

5. **Connections:**
   - What connection types exist?
   - What are compatibility rules?
   - How are multi-input operators handled?
   - How are exports/bindings represented?

6. **Parameters:**
   - What parameter types exist?
   - How is each type serialized?
   - What are expression modes?
   - How are parameter references handled?

7. **Resources:**
   - How are external files referenced?
   - How are embedded resources stored?
   - What path formats are valid?
   - How are missing resources handled?

---

## Success Metrics

The final system should achieve:

1. **100% validation accuracy** - No false positives or negatives
2. **100% TD compatibility** - All generated files load successfully
3. **Comprehensive coverage** - All 673 operator types supported
4. **Fast validation** - <100ms for typical projects
5. **Clear error messages** - Actionable feedback for all errors
6. **Complete documentation** - Every rule explained with examples
7. **Test coverage** - >95% code coverage
8. **Real-world validation** - All 121 palette components validate

---

## Example Use Cases

### Use Case 1: AI Project Generator
```python
# User: "Create audio visualization with beat detection"
builder = TDProjectBuilder("2023.11760", 11760)

# AI generates this code
builder.add_operator("audiodeviceinCHOP", "audioin")
builder.add_operator("beatCHOP", "beat")
builder.add_operator("particlegpuTOP", "particles")
builder.add_operator("renderTOP", "render")

builder.connect("/project1/audioin", "/project1/beat")
builder.connect("/project1/beat", "/project1/particles")
builder.connect("/project1/particles", "/project1/render")

# Validate before building
result = builder.validate()
if result.valid:
    builder.build("audio_visualization.toe")
else:
    print(f"Errors: {result.errors}")
```

### Use Case 2: Template System
```python
# Load template JSON
with open("templates/audio_viz.json") as f:
    template = json.load(f)

# Validate template
result = validate_project_json(template)
assert result.valid

# Customize
template["operators"][0]["parameters"]["file"] = "my_audio.wav"

# Build
builder = TDProjectBuilder.from_json(template)
builder.build("my_project.toe")
```

### Use Case 3: Automated Testing
```python
# Generate test projects for all operator types
for op_type in OperatorRegistry.get_all_types():
    builder = TDProjectBuilder("2023.11760", 11760)

    # Add operator with default parameters
    builder.add_operator(op_type, f"{op_type}_test")

    # Validate
    result = builder.validate()
    assert result.valid, f"{op_type} failed: {result.errors}"

    # Build
    builder.build(f"tests/{op_type}.toe")
```

---

## Constraints & Considerations

- **No official spec exists** - Must reverse engineer from examples
- **Format may change** - Must support multiple TD versions
- **Complex nested structures** - COMPs within COMPs
- **Expression language** - Parameters can have expressions
- **External resources** - Files may be embedded or referenced
- **Performance** - Large projects can have thousands of operators
- **Error recovery** - TD is sometimes lenient with errors

---

## Your Task

Please develop a comprehensive plan that:

1. **Researches** the TD file format thoroughly
2. **Documents** all rules and constraints
3. **Designs** a robust validation system
4. **Specifies** the builder API
5. **Plans** implementation phases
6. **Identifies** risks and edge cases
7. **Proposes** testing strategies
8. **Estimates** effort and complexity

Focus on creating a **formal specification** that can be implemented systematically. The goal is to make it **impossible to generate invalid TD files** through comprehensive validation.

**End of Prompt** - Copy everything above into your planning session

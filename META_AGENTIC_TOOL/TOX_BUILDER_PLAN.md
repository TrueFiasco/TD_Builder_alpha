# TOX Builder Completion Plan

## Current State Analysis

### What We Have (Assets)

| Asset | Location | Description |
|-------|----------|-------------|
| 640 Ground Truth .tox | `operator_ground_truth/tox/` | Each contains `op_default` + `op_perturbed` |
| 1,280 Param JSONs | `operator_ground_truth/params/` | `*_defaults.json` and `*_perturbed.json` |
| Operator Types | `operator_ground_truth/operator_types.json` | 685 operators with TD create names |
| Param Schemas | `operator_param_schemas.json` | 13,035 parameters with types/defaults |
| Lossless Parser | `td_builder_workspace/parsers/toe_to_json_LOSSLESS.py` | .tox.dir -> JSON |
| Lossless Builder | `td_builder_workspace/parsers/json_to_dir_LOSSLESS.py` | JSON -> .dir + .toc |
| TOE Builder | `unified_system/builders/toe_builder.py` | TDNetwork -> .toe/.tox |
| Core Models | `unified_system/core/models.py` | TDNetwork, Operator, etc. |

### What's Working

1. **Parser (toe_to_json_LOSSLESS.py)**: Converts expanded .tox/.toe directories to JSON with 100% file preservation
2. **Builder (json_to_dir_LOSSLESS.py)**: Reconstructs .dir + .toc from lossless JSON
3. **Ground Truth Generation**: 640 .tox files with all operators sampled
4. **Parameter Capture**: Default and perturbed parameter values captured for each operator

### What's Missing / Gaps

1. **Expanded Ground Truth**: The 640 .tox files haven't been expanded yet with `toeexpand`
2. **.parm Format Details**: Need to document exact .parm format (mode numbers, multi-value params)
3. **High-Level JSON Schema**: No AI-friendly JSON schema for defining new networks
4. **Validation Layer**: No validation against operator_types.json and param schemas
5. **New Network Builder**: Builders currently work with lossless round-trip, not new networks from scratch

---

## Phase 1: Ground Truth Expansion & Analysis

### Step 1.1: Batch Expand All Ground Truth .tox Files

```bash
# Create expansion script
for each .tox in operator_ground_truth/tox/:
    toeexpand {file}.tox {file}.tox.dir
```

**Output**: 640 `.tox.dir/` folders with `.n`, `.parm`, etc. files

### Step 1.2: Parse and Catalog All .parm Files

Extract from expanded files:
- All parameter names per operator
- Parameter mode numbers (0=constant, 17=expression, etc.)
- Multi-component parameters (e.g., color with indices 0,1,2,3)
- Expression syntax format

**Output**: `parm_format_analysis.json`

### Step 1.3: Compare Against Existing Schemas

Compare expanded .parm contents with:
- `operator_param_schemas.json` (our KB-extracted schemas)
- `*_perturbed.json` (our TD-captured params)

Identify:
- Missing parameters in our schemas
- Type mismatches
- Default value differences

**Output**: `schema_gaps.json`

---

## Phase 2: Format Documentation

### Step 2.1: Document .toc File Format

```
# {version} {flags...}
.build
project1/op_name.n
project1/op_name.parm
...
```

Header line: `# 4 0 0 0 1` - decode meaning of each number

### Step 2.2: Document .n File Format

```
{FAMILY}:{type}
v {x} {y} {z}
tile {x} {y} {w} {h}
flags = {key} {value} ...
inputs
{
{index} \t{source_path}
}
color {r} {g} {b}
end
```

### Step 2.3: Document .parm File Format

```
?
{param_name} {mode} {value} [expression]
{param_name} {index} {value}  # multi-component
?
```

Mode numbers:
- 0 = constant
- 17 = expression (python)
- ? = tscript expression
- ? = bind mode
- ? = export mode

### Step 2.4: Document Extra File Types

| Extension | Description | Operator Types |
|-----------|-------------|----------------|
| .text | Text content | Text DAT |
| .table | Table data | Table DAT |
| .panel | Panel config | All COMPs |
| .geo | Geometry | SOP import |

**Output**: `FORMAT_SPECIFICATION.md`

---

## Phase 3: High-Level JSON Schema Design

### Step 3.1: Define Builder JSON Schema

AI-friendly format for creating networks:

```json
{
  "format": "td_builder_v1",
  "metadata": {
    "name": "my_project",
    "td_version": "2023.11880"
  },
  "operators": [
    {
      "path": "/project1/noise1",
      "type": "noiseCHOP",
      "parameters": {
        "amp": 2.0,
        "period": 10
      },
      "position": {"x": 100, "y": 200}
    }
  ],
  "connections": [
    {"from": "/project1/noise1", "to": "/project1/math1", "input": 0}
  ]
}
```

### Step 3.2: Define Validation Rules

1. **Operator Type Validation**: Check against `operator_types.json`
2. **Parameter Validation**: Check against `operator_param_schemas.json`
3. **Connection Validation**: Ensure source/target exist, compatible families
4. **Path Validation**: Ensure valid hierarchical paths

---

## Phase 4: Validation Layer Implementation

### Step 4.1: Create Operator Registry

Load `operator_types.json` into a registry for validation:

```python
class OperatorRegistry:
    def is_valid_type(self, op_type: str) -> bool
    def get_create_name(self, kb_name: str) -> str
    def get_family(self, op_type: str) -> str
```

### Step 4.2: Create Parameter Validator

Load `operator_param_schemas.json`:

```python
class ParameterValidator:
    def validate_params(self, op_type: str, params: dict) -> List[ValidationError]
    def get_param_type(self, op_type: str, param_name: str) -> str
    def get_default(self, op_type: str, param_name: str) -> Any
```

### Step 4.3: Create Network Validator

```python
class NetworkValidator:
    def validate(self, network: dict) -> ValidationReport
    # Stages: schema, operators, parameters, connections, paths
```

---

## Phase 5: Builder Implementation

### Step 5.1: Enhance TOE Builder for New Networks

Current builder works with lossless data. Add "BASIC" mode:

```python
def build_basic(self, network_json: dict) -> Path:
    # 1. Validate network
    # 2. Generate .build, .start, .root, .grps, .parm, .application
    # 3. For each operator:
    #    - Generate .n file
    #    - Generate .parm file (only non-default values!)
    #    - Generate extra files if needed
    # 4. Write .toc
    # 5. Return path to .toc
```

### Step 5.2: Implement Parameter Serialization

Key insight: **TD only writes non-default parameters to .parm files**

```python
def serialize_params(self, op_type: str, params: dict) -> str:
    lines = ['?']
    for name, value in params.items():
        default = self.registry.get_default(op_type, name)
        if value != default:
            # Write to .parm
            mode = 0  # constant
            lines.append(f"{name} {mode} {value}")
    lines.append('?')
    return '\n'.join(lines) + '\n'
```

### Step 5.3: Implement toecollapse Integration

```python
def collapse(self, toc_path: Path) -> Path:
    # Run: toecollapse {toc_path}
    # Returns: path to collapsed .tox/.toe file
```

---

## Phase 6: Testing & Validation

### Step 6.1: Round-Trip Tests

For each operator type:
1. Create minimal JSON with operator
2. Build .tox
3. Expand with toeexpand
4. Parse with lossless parser
5. Compare JSON structures

### Step 6.2: Complex Network Tests

Build test networks:
- Audio analysis (CHOP chain)
- Video processing (TOP chain)
- Geometry (SOP -> COMP -> MAT)
- Interactive (Panel -> Execute DATs)

### Step 6.3: Validation in TouchDesigner

Load generated .tox files in TD and verify:
- Operators exist and have correct types
- Parameters are set correctly
- Connections work
- No errors in textport

---

## Implementation Order

| Priority | Task | Dependencies | Estimated Files |
|----------|------|--------------|-----------------|
| 1 | Batch expand ground truth | toeexpand | 1 script |
| 2 | Parse expanded .parm files | Step 1 | 1 script |
| 3 | Document format spec | Step 2 | 1 markdown |
| 4 | Create validation layer | Steps 2,3 | 3-4 files |
| 5 | Enhance builder for BASIC mode | Step 4 | Update 1 file |
| 6 | Round-trip tests | Step 5 | 1-2 test files |
| 7 | Complex network tests | Step 6 | Test cases |

---

## Files to Create/Modify

### New Files
- `operator_ground_truth/expand_all.py` - Batch expansion script
- `operator_ground_truth/analyze_parms.py` - .parm analysis
- `FORMAT_SPECIFICATION.md` - Complete format documentation
- `builders/network_validator.py` - Validation layer
- `tests/test_round_trip.py` - Round-trip tests

### Files to Modify
- `unified_system/builders/toe_builder.py` - Add BASIC mode
- `unified_system/core/models.py` - Add any missing fields

---

## Success Criteria

1. Can create ANY valid .tox file from high-level JSON
2. All 640+ operator types supported
3. Parameters validated against ground truth
4. Round-trip: JSON -> .tox -> expand -> JSON matches
5. Generated .tox files load without errors in TouchDesigner

# TouchDesigner .toe / .tox format — reverse-engineering learnings

> Provenance: this document is the reverse-engineering artefact that informed
> the mode-aware `.parm` parsing/writing in
> `MCP/engine/parsers/lossless_parser.py` and `MCP/engine/builders/toe_builder.py`.
> Any future work on `.toe` / `.tox` format internals should start here.

## Key Insights About .tox/.toe Format

### 1. Parameters Only Written When Non-Default
**Critical Finding**: TouchDesigner does NOT write parameters to `.parm` files if they are at their default values.

**Implication**: To capture all possible parameters for an operator, you must:
1. Set every parameter to a non-default value
2. Save the .tox
3. Expand and inspect the .parm file

**Evidence**: Constant CHOP with default values produces minimal .parm file. Same CHOP with perturbed values shows all 40 channel slots.

### 2. Repeated Parameter Patterns
Many operators have numbered parameter slots:

| Operator | Pattern | Range |
|----------|---------|-------|
| Constant CHOP | `const{N}name`, `const{N}value` | 0-39 |
| GLSL TOP | `uniname{N}`, `value{N}` | 0-15 |
| GLSL MAT | `uniname{N}`, `value{N}x/y/z/w` | 0-15 |
| Geometry COMP | `instance{N}op/tx/ty/tz` | 0-9 |

### 3. TD Create Name Convention
KB name → TD Python create name:
- `Blur_TOP` → `blurTOP`
- `Audio_File_In_CHOP` → `audiofileinCHOP`
- `Movie_File_In_TOP` → `moviefileinTOP`

Rule: Remove underscores from base, lowercase, append family suffix.

### 4. .toc File Structure
For .tox files:
```
# 4 0 0 0 1
.build
project1/op_name.n
project1/op_name.parm
```

Header line format: `# version ? ? ? ?` (need more samples to decode)

### 5. .parm File Format
```
param_name    index    value
```
- Tab-separated
- `?` as sentinel/separator lines
- Index typically 0 for scalar params
- Multi-component params (e.g., color) may have indices 0,1,2,3

### 6. .n File Format
```
FAMILY:type
v x y z      # viewport position
tile x y w h  # tile position/size
flags = ...   # operator flags
inputs
{
  0 /path/to/source
}
end
```

## Anti-Hallucination Rules

1. **Only generate operators that exist in operator_types.json**
2. **Only use parameters from operator_param_schemas.json**
3. **Validate td_create names before calling container.create()**
4. **Round-trip test: expand → parse → rebuild → collapse → verify**

## Files Generated

- `eval/ground_truth/operator_types.json` - the 647 creatable operators, generated
  from the live TouchDesigner census by `kb_build/gen_operator_types.py`
  (was "all 685 valid operators" from a wiki scrape that invented 13 operators
  and omitted 7 real ones; the corpus path above is a legacy fallback only)
- `operator_param_schemas.json` - 13,035 parameters with types/defaults
- `operator_ground_truth/tox/` - Ground truth .tox files (after sampling)
- `operator_ground_truth/params/` - Default and perturbed param JSONs

## Completed Steps (Session 2)

1. **Batch Expanded 640 Ground Truth .tox Files** - All successful in 19.6s
2. **Analyzed 18,084 Parameters** from expanded .parm files
3. **Documented Mode Numbers**:
   - Mode 0: constant (17,757 params)
   - Mode 16: expression (171 params)
   - Mode 256, 1024, 524288, 1048576, 67108928: special flags
4. **Created FORMAT_SPECIFICATION.md** - Complete .tox format documentation
5. **Implemented ToxBuilder** - Creates .tox from high-level JSON
6. **Successfully Round-Tripped** - JSON → .tox → works!

## Key Files Created

| File | Purpose |
|------|---------|
| `operator_ground_truth/expand_all.py` | Batch expand .tox files |
| `operator_ground_truth/analyze_parms.py` | Analyze .parm format |
| `operator_ground_truth/tox_expanded/` | 640 expanded .tox dirs |
| `operator_ground_truth/mode_numbers.json` | Mode number analysis |
| `operator_ground_truth/param_catalog.json` | Params per operator |
| `FORMAT_SPECIFICATION.md` | Complete format docs |
| `MCP/server_core/meta_agentic/execution/tox_builder.py` | `ToxBuilder` — high-level .tox builder (subclass of `ToeBuilderBridge`) |

> **Note (builder path update):** the standalone `tox_builder/` tree (and its
> `TOX_BUILDER_PLAN.md`) described in this historical session log was retired and
> folded into the engine. `ToxBuilder` now lives at
> `MCP/server_core/meta_agentic/execution/tox_builder.py` as a subclass of
> `ToeBuilderBridge`, and the canonical way to build is the **`td_build_project`
> MCP tool** (which routes through `_run_build` → `ToxBuilder`/`ToeBuilderBridge`),
> never a direct import.

## Builder Usage

The supported entry point is the `td_build_project` MCP tool (validate first with
`td_validate`). The low-level class it drives:

```python
# import path after the engine consolidation
from meta_agentic.execution.tox_builder import ToxBuilder   # subclass of ToeBuilderBridge

design = {  # builder-format network
    "name": "my_component",
    "operators": [
        {"name": "noise1", "type": "noiseCHOP", "parameters": {"amp": 2.0}},
        {"name": "math1", "type": "mathCHOP", "inputs": ["noise1"]}
    ]
}

builder = ToxBuilder("./output", verbose=True)
tox_path = builder.build_tox(design, project_name="my_component")

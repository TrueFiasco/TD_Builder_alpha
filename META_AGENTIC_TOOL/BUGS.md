# TD Builder Bug Tracker

**Maintained By**: BARRY (Bug Manager)
**Last Updated**: 2024-12-23

---

## CRITICAL (System Unusable)

*None currently*

---

## HIGH (Major Feature Broken)

### BUG-001: BASIC mode parameters not recognized by TouchDesigner
- **Reported By**: CLIFF
- **Date**: 2024-12-23
- **Component**: Builder / toe_builder_bridge.py
- **Status**: FIXED
- **Fixed By**: TERRY
- **Fixed Date**: 2024-12-23

**Root Cause**: PARAM_NAME_MAP had wrong/missing parameter name mappings

**Fix Applied**:
1. Created `param_name_resolver.py` - auto-generates mappings from KB
2. Added `USER_FRIENDLY_ALIASES` for common names
3. Updated `toe_builder_bridge.py` to use new resolver

**Test Results**: All parameter mapping tests PASSED

---

## MEDIUM (Feature Degraded)

### BUG-004: Palette TOX embedding fails - wrapper/media issues
- **Reported By**: Jake (via CLIFF)
- **Date**: 2024-12-23
- **Component**: Lossless Parser / KB storage
- **Status**: CLOSED
- **Fixed By**: TERRY
- **Fixed Date**: 2024-12-23

**Root Cause**: Lossless parser didn't handle palette wrapper structure, exports blocks, tags, or dock settings correctly.

**Fix Applied**:
1. Fixed `exports` blocks parsing (extracts from .nfo files)
2. Fixed `dict` lines extraction (all operators)
3. Fixed `tags` preservation (TDModuleComp etc.)
4. Fixed `dock` settings parsing
5. Fixed case collision handling (foo.n vs Foo.n)
6. Added wrapper container detection and inner component extraction
7. Added bloat stripping for large ops (audioin, moviein, cache, lag, locked data)

**Storage Strategy**: Gzip compressed lossless JSON
- Location: `kb_pipeline/data/palette_lossless/*.json.gz`
- ~10x compression (2.6MB → 200KB typical)
- Decompress in <10ms
- Perfect round-trip fidelity verified

**Tested Palettes**: audioAnalysis, julia, mandelbrot, slider2D - all PERFECT

**Delegations**:
- KYLE: KB update (replace old schematics, rebuild embeddings)
- PETER: Prompt updates (palette embedding instructions)

---

## LOW (Minor Issues)

### BUG-005: DATto CHOP incorrect usage in agent
- **Reported By**: Jake (via CLIFF)
- **Date**: 2024-12-23
- **Component**: Agent / expertise
- **Status**: FIXED
- **Fixed By**: PETER
- **Fixed Date**: 2024-12-23

**Description**: Agent used incorrect DATto CHOP conventions during Prompt 05 testing.

**Fix Applied**:
- Added `dat_to_chop_conversion` pattern to `td_network_patterns.yaml`
- Critical note: dattoCHOP does NOT use wire connections - uses `dat` parameter
- Documented `firstrow` and `firstcolumn` parameter usage
- Added common errors and fixes

**Assigned To**: PETER (expertise) + KYLE (KB verification)

---

### BUG-007: operator_param_schemas.json missing operator-specific parameters
- **Reported By**: KYLE
- **Date**: 2024-12-23
- **Component**: KB / operator_param_schemas.json
- **Status**: FIXED
- **Fixed By**: KYLE
- **Fixed Date**: 2024-12-24

**Description**:
The `operator_param_schemas.json` file only contains generic CHOP timing parameters (8 params) but `operator_ground_truth/params/` has complete schemas (31+ params per operator).

**Fix Applied (Option 3)**:
Migrated `kb_query.py` to use `ground_truth.py` instead of incomplete `operator_param_schemas.json`:
1. Added import for `ground_truth.py`
2. Replaced `_load_operator_schemas()` with `_get_ground_truth()`
3. Updated `validate_operator()` to use `gt.get_operator()`
4. Updated `validate_parameter()` to use `gt.get_param_info()`

**Files Modified**:
- `meta_agentic/execution/kb_query.py`

---

### BUG-013: Menu parameter format documentation
- **Reported By**: QUEENIE
- **Date**: 2024-12-24
- **Component**: KB / td_network_patterns.yaml
- **Status**: FIXED
- **Fixed By**: KYLE
- **Fixed Date**: 2024-12-24

**Description**:
Menu parameters have inconsistent format requirements - some need integers, some need strings. No documentation on which format each needs.

**Fix Applied**:
Added `format` field to menu parameters in `td_network_patterns.yaml`:

| Operator | Parameter | Format | Why |
|----------|-----------|--------|-----|
| Analyze CHOP | function | integer | Strings default to 0 |
| Composite TOP | operand | string | Integers are corrupted |
| Noise CHOP | type | string | Works with strings |
| Noise TOP | type | string | Works with strings |
| Math CHOP | chanop | integer | Integer-based menu |
| Math CHOP | match | integer | Integer-based menu |

**Files Modified**:
- `meta_agentic/expertise/td_network_patterns.yaml`

---

### BUG-008: td_build_toe doesn't populate nested container networks
- **Reported By**: QUEENIE (via bug_report_basic_1-10.md Task 06)
- **Date**: 2024-12-24
- **Component**: MCP Tool / toe_builder_bridge.py
- **Status**: OPEN
- **Severity**: CRITICAL

**Description**:
`td_build_toe` creates container shells but does not populate nested `network` content - all containers are empty.

**Evidence**:
- File size: 418 bytes (should be ~2000+ with 5 containers having operators)
- Container count: 5 (created correctly)
- Operators in containers: 0 (should be 20+)

**Root Cause**: Tool doesn't recurse into container `network` definitions to generate child operators.

**Reproduction**:
```json
{
  "containers": [
    {
      "name": "noise_chop",
      "type": "container",
      "network": {
        "operators": [{"name": "noise1", "type": "noise", "family": "CHOP"}]
      }
    }
  ]
}
```

**Assigned To**: TERRY
**Priority**: HIGH (major feature broken)

---

### BUG-011: Composite TOP type aliases not documented
- **Reported By**: QUEENIE
- **Date**: 2024-12-24
- **Component**: KB / expertise files
- **Status**: FIXED
- **Fixed By**: KYLE
- **Fixed Date**: 2024-12-24

**Description**: Composite TOP type aliases (composite_top, compTOP) not in KB, causing builder to fall back to Base COMP. Also missing complete operand parameter values.

**Fix Applied**:
1. Added type aliases to `td_file_formats.yaml`:
   - composite_top → TOP:comp
   - compTOP → TOP:comp
2. Added complete operand values (46 blend modes) to `td_network_patterns.yaml`

---

### BUG-002 (session): DATto CHOP parameter integer values not documented
- **Reported By**: QUEENIE (via BUG-002_datto_chop_params.md)
- **Date**: 2024-12-24
- **Component**: KB / expertise files
- **Status**: FIXED
- **Fixed By**: KYLE
- **Fixed Date**: 2024-12-24

**Description**: DATto CHOP `output`, `firstrow`, and `firstcolumn` parameters listed but integer value meanings not documented, causing incorrect table-to-channel conversion.

**Root Cause**: KB showed string values ("cpr", "cpc", "names", "values") but TD expects integers.

**Fix Applied**:
1. Added complete `parameter_integer_mappings` section to `td_network_patterns.yaml`:
   - `output`: 0=single, 1=chanperrow, 2=chanpercol, 3=chanperval
   - `firstrow`: 0=ignore, 1=names, 2=values
   - `firstcolumn`: 0=ignore, 1=names, 2=values
2. Added `common_pattern` example with table header row scenario
3. Updated `output_parameter` section to show integer keys (1, 2) instead of strings
4. Added `CRITICAL_NOTE` emphasizing integer values required

---

### BUG-003 (session): COMP input connections need .network file
- **Reported By**: QUEENIE (via BUG-003_comp_input_connections.md)
- **Date**: 2024-12-24
- **Component**: MCP Tool / toe_builder_bridge.py
- **Status**: OPEN
- **Severity**: HIGH

**Description**: Connections TO COMP internal inputs (e.g., `audioAnalysis/in1`) are not created. Tool needs to generate `.network` file with `compinputs` block.

**Related**: BUG-008 (same root cause - palette connections)

**Assigned To**: TERRY

---

### BUG-004 (session): GLSL raymarching quality checklist
- **Reported By**: QUEENIE (via BUG-004_glsl_quality_checklist.md)
- **Date**: 2024-12-24
- **Component**: Agent / GLSL Expert
- **Status**: OPEN
- **Severity**: MEDIUM

**Description**: Agent prioritized code complexity over visual validation. Camera/scene geometry mismatch caused invisible ground plane.

**Prevention**: Add pre-delivery checklist to GLSL expert prompts.

**Assigned To**: PETER

---

### BUG-005 (session): Composite TOP operand integers corrupted
- **Reported By**: QUEENIE (via BUG-005_composite_operand_string.md)
- **Date**: 2024-12-24
- **Component**: MCP Tool / toe_builder_bridge.py
- **Status**: OPEN
- **Severity**: MEDIUM

**Description**: Integer values passed to `operand` parameter are corrupted during build. Strings work correctly.

**Workaround**: Use string names (`"add"`, `"multiply"`) instead of integers (0, 27).

**Assigned To**: TERRY

---

### BUG-006 (session): Agent used web search instead of KB
- **Reported By**: QUEENIE (via BUG-006_agent_kb_workflow.md)
- **Date**: 2024-12-24
- **Component**: KB (analyze CHOP) + Agent workflow
- **Status**: PARTIAL FIX
- **Severity**: MEDIUM

**Description**: Agent used web search for Analyze CHOP function values instead of KB.

**KB Fix Applied** (KYLE):
- Added `analyze_chop` section to `td_network_patterns.yaml`
- Complete function parameter integer mappings (0-11)

**Remaining** (PETER): Agent workflow should query KB before web search.

---

### BUG-010 (session): GLSL uTD2DInfos without inputs
- **Reported By**: QUEENIE (via BUG_REPORT_10_glsl_uTD2DInfos_2025-12-24.md)
- **Date**: 2024-12-24
- **Component**: Agent / GLSL Expert
- **Status**: OPEN (Agent issue - KB already has warning)
- **Severity**: MEDIUM

**Description**: Agent used `uTD2DInfos[0]` in standalone shader with no inputs.

**KB Status**: Already documented in `td_glsl.yaml` as GLSL-004 anti-pattern.

**Fix Needed**: Agent must query GLSL expertise before writing shaders.

**Assigned To**: PETER

---

### BUG-E (session 3): Container CHOP expression pattern missing
- **Reported By**: QUEENIE (Session 3 testing)
- **Date**: 2024-12-24
- **Component**: KB / td_python.yaml
- **Status**: FIXED
- **Fixed By**: KYLE
- **Fixed Date**: 2024-12-24

**Description**: Agent used `op('../container')['channel']` but containers are not subscriptable - need internal CHOP path.

**TD Error**: `TypeError: 'td.containerCOMP' object is not subscriptable`

**Fix Applied**:
Added container_channel_access pattern to `td_python.yaml`:
- Wrong: `op('container')['channel']`
- Right: `op('container/chopName')['channel']`
- Alternative: `op('container').op('chopName')['channel']`

---

### BUG-A (session 3): DATto CHOP firstrow/firstcolumn truth table
- **Reported By**: QUEENIE (Session 3 testing)
- **Date**: 2024-12-24
- **Component**: KB / td_network_patterns.yaml
- **Status**: FIXED
- **Fixed By**: KYLE
- **Fixed Date**: 2024-12-24

**Description**: Missing complete 9-combination truth table for firstrow/firstcolumn parameters.

**Fix Applied**:
Added `firstrow_firstcolumn_truth_table` section with all 9 combinations:
- Each firstrow (0,1,2) × firstcolumn (0,1,2) meaning
- Use cases and examples
- Quick reference for common layouts

---

### BUG-H (session 3): Python math expression syntax
- **Reported By**: QUEENIE (Session 3 testing)
- **Date**: 2024-12-24
- **Component**: KB / td_python.yaml
- **Status**: FIXED
- **Fixed By**: KYLE
- **Fixed Date**: 2024-12-24

**Description**: Agent used bare `sin()` and `cos()` instead of `math.sin()` and `math.cos()`.

**TD Error**: `NameError: name 'sin' is not defined`

**Fix Applied**:
Added `math_functions` section to `td_python.yaml`:
- Common errors with correct patterns
- Complete list of math.* functions (trig, arithmetic, rounding)
- List of Python builtins that work without prefix (abs, min, max, round)
- tdu.* alternatives (rand, remap, clamp)

---

### BUG-006: Missing error messages for edge cases
- **Reported By**: TERRY
- **Date**: 2024-12-23
- **Component**: MCP Tools + Builder
- **Status**: PLANNED

**Description**:
TD Builder tools return generic error messages that don't help users debug issues.

**Gaps Found**:
- mcp_server.py: 6 error handling gaps (lines 288-403)
- toe_builder_bridge.py: 5 error handling gaps

**Planned Fix**:
- Create error_codes.py module
- Structured error responses with: error_code, message, context, suggestion
- Fuzzy matching for "Did you mean X?"
- List available options on unknown values

**Files to Modify**:
- meta_agentic/execution/error_codes.py (NEW)
- mcp_server.py (lines 288-340, 400-403)
- meta_agentic/execution/toe_builder_bridge.py (lines 55, 1049-1076, 1695-1718)

**Assigned To**: TERRY
**Plan Status**: APPROVED by CLIFF

---

## CLOSED

### BUG-002: hybrid_search tool not initialized
- **Status**: WONTFIX (legacy server)

### BUG-003: find_similar_networks calls wrong method name
- **Status**: WONTFIX (legacy server)

---

## Bug Statistics

| Severity | Open | In Progress | Fixed | WONTFIX |
|----------|------|-------------|-------|---------|
| HIGH | 2 | 0 | 2 | 1 |
| MEDIUM | 3 | 0 | 7 | 0 |
| LOW | 1 | 0 | 4 | 1 |

### Active Bugs - TERRY (Tool)
- **BUG-008**: HIGH - Container networks empty - OPEN
- **BUG-003 (s)**: HIGH - COMP input connections need .network - OPEN
- **BUG-005 (s)**: MEDIUM - Composite operand integers corrupted - OPEN
- **BUG-006**: LOW - Error messages - PLANNED

### Active Bugs - PETER (Agent)
- **BUG-004 (s)**: MEDIUM - GLSL raymarching checklist - OPEN
- **BUG-006 (s)**: MEDIUM - KB workflow (agent part) - OPEN
- **BUG-010 (s)**: MEDIUM - GLSL uTD2DInfos (KB exists, agent issue) - OPEN

### Fixed
- **BUG-001**: HIGH - Parameter mapping - FIXED by TERRY
- **BUG-004**: MEDIUM - Palette embedding - FIXED by TERRY
- **BUG-005**: LOW - DATto CHOP expertise - FIXED by PETER
- **BUG-011**: LOW - Composite TOP aliases - FIXED by KYLE
- **BUG-002 (s)**: MEDIUM - DATto CHOP integer params - FIXED by KYLE
- **BUG-006 (s)**: MEDIUM - Analyze CHOP integers (KB part) - FIXED by KYLE
- **BUG-007**: MEDIUM - Param schema migration - FIXED by KYLE
- **BUG-013**: MEDIUM - Menu param format docs - FIXED by KYLE
- **BUG-E**: HIGH - Container CHOP expression pattern - FIXED by KYLE
- **BUG-A**: MEDIUM - DATto CHOP truth table - FIXED by KYLE
- **BUG-H**: MEDIUM - Python math expression syntax - FIXED by KYLE

### Closed (WONTFIX)
- **BUG-002, BUG-003**: Legacy server issues

---

*Last Updated: 2024-12-24 by KYLE (Session 3: BUG-E, BUG-A, BUG-H fixed)*

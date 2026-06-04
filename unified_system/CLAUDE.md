# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the **TouchDesigner Unified System v2.0** - a production-ready system for building, validating, and converting TouchDesigner networks programmatically. It achieves **100% round-trip fidelity** when parsing .toe files and rebuilding them.

**Status:** Production-ready. All 8 implementation phases complete.

## Common Commands

### Installation
```bash
cd C:\TD_Projects\unified_system
pip install -e .
```

### Testing
```bash
# Run all tests (48 tests total)
pytest tests/

# Run specific test suites
pytest tests/test_e2e.py -v              # 7 end-to-end tests
pytest tests/test_builder_api.py -v      # 24 API tests
pytest tests/test_performance.py         # 10 performance benchmarks

# Run single test
pytest tests/test_e2e.py::test_simple_network_round_trip -v

# With coverage
pytest tests/ --cov=unified_system --cov-report=html
```

### CLI Tools (after pip install)
```bash
# Validate network JSON
td-validate network.json --verbose

# Convert between format layers
td-convert network.json --from builder --to canonical --pretty

# Build .toe file from JSON
td-build network.json --output project.toe --verbose

# Collapse .toe.dir to .toe (requires TouchDesigner)
"C:\Program Files\Derivative\TouchDesigner\bin\toecollapse.exe" project.toe.toc
```

### Complete Pipeline Test (Round-Trip)
```bash
# End-to-end fixture pipeline (parse → convert → rebuild)
cd C:\TD_Projects\unified_system
python cli/td_fixture_pipeline.py "path/to/project.toe" --out "output_dir" --pretty
```

This parses a .toe file, converts through all format layers, and rebuilds it. **Critical:** The v5 fix ensures 100% file preservation by using LOSSLESS mode directly (see Architecture section).

## High-Level Architecture

### Three Critical Concepts

#### 1. Three-Layer Format Strategy (Hub-and-Spoke)

```
Builder JSON ←→ Extended JSON ←→ Canonical JSON
  (Layer 1)      (Layer 2)         (Layer 3)
                    ↕
                Lossless JSON
                 (Layer 4)
```

- **Builder JSON (Layer 1)**: AI-friendly, simple paths (e.g., `"path": "noise1"`)
- **Extended JSON (Layer 2)**: Ground truth, complete operator data (absolute paths)
- **Canonical JSON (Layer 3)**: Compact, string-table compression for storage
- **Lossless JSON (Layer 4)**: Perfect .toe round-trip with `raw_files` preservation

**Key:** Extended format is the **hub** - all conversions go through it. FormatConverter handles all layer-to-layer conversions using this pattern.

#### 2. Dual-Mode Building (LOSSLESS vs BASIC)

`TOEBuilder` has two modes:

**LOSSLESS Mode** (Perfect Round-Trip):
- Requires `network.lossless_data` with `raw_files` dict
- Writes files exactly as parsed (byte-identical)
- Used by `td_fixture_pipeline.py` for 100% fidelity
- **Critical fix (v5):** Must use original parsed network, NOT rebuilt from builder JSON

**BASIC Mode** (Generate from Scratch):
- No `lossless_data` required
- Generates .toe from operators/connections/parameters
- Uses flag 0 for all parameters (safe default)
- Used by `NetworkBuilder.build_toe()` when creating new networks

**When to use which:**
- Round-tripping existing .toe: LOSSLESS mode
- Creating new networks from code: BASIC mode

#### 3. Five-Stage Validation Pipeline

Located in `validation/pipeline.py`, runs sequentially:

1. **Schema Validation** - JSON structure matches schema
2. **Semantic Validation** - Operators/parameters exist in registry (670 operators)
3. **Reference Validation** - Connections valid, parents exist
4. **Logical Validation** - Type compatibility, no cycles
5. **TD Rules Validation** - TouchDesigner-specific constraints

**Performance:** <30ms for 100 operators

### Critical File Paths

**Registry Data Source:**
```
C:\TD_Projects\kb_pipeline\data\wiki_docs\td_universal_parsed.json
```
Contains 670 verified operators with parameter schemas. OperatorRegistry loads this on init.

**Schemas:**
```
unified_system/schemas/
├── builder.schema.json      # Layer 1
├── unified_v2.schema.json   # Layer 2 (Extended)
├── canonical.schema.json    # Layer 3
└── lossless.schema.json     # Layer 4
```

## Key Design Decisions

### Why Dataclasses (not dict)?
Type safety, IDE autocomplete, validation at construction time. See `core/models.py` - all models are frozen dataclasses.

### Why Five Validation Stages?
Early stages catch simple errors fast (<1ms), later stages handle complex graph analysis. Sequential execution provides clear error messages at the appropriate level.

### Why Hub-and-Spoke Conversion?
Avoids O(n²) converter implementations. Only need 6 converters (3 formats × 2 directions to/from Extended) instead of 12.

### Why Separate .toe.dir and .toe?
TouchDesigner's native format. `.toe.dir` is the expanded directory, `.toe.toc` is the table of contents. The `toecollapse` tool combines them into final `.toe` file. We generate `.toe.dir` + `.toc`, user runs `toecollapse`.

## Critical Bug Fix (v5 - December 2024)

**Issue:** `td_fixture_pipeline.py` was losing 35 files (.network, .gnode, .panel) during round-trip.

**Root Cause:**
```python
# BROKEN (v4):
builder_json = converter.to_builder(network)      # Drops lossless_data
rebuilt_network = converter.from_builder(builder_json)  # No raw_files
rebuilt_toc = TOEBuilder(rebuilt_network, ...).build()  # Uses BASIC mode
```

**Fix (v5):**
```python
# FIXED - Use original network with lossless_data:
rebuilt_toc = TOEBuilder(network, verbose=False).build(rebuilt_toe, mode="toe")
```

**Impact:** 398/398 files preserved (100%), 0 errors in TouchDesigner, identical error log to original.

**File:** `cli/td_fixture_pipeline.py:188`

## Working with NetworkBuilder

The fluent API is in `api/network_builder.py`. Example pattern:

```python
from api.network_builder import NetworkBuilder

builder = NetworkBuilder("project_name", mode="toe")

# ALWAYS verify operator exists before adding
from core.operator_registry import OperatorRegistry
registry = OperatorRegistry()

op_spec = registry.get_operator("CHOP", "noise")
if op_spec:
    builder.add_operator("noise1", "CHOP", "noise")

    # Verify parameter exists
    param = next((p for p in op_spec.parameters if p.code == "amp"), None)
    if param:
        builder.set_parameter("noise1", "amp", 0.5)

# Validate before building
if builder.is_valid():
    builder.build_toe("output.toe")
```

**Never guess operator types or parameter names.** Always verify against registry.

## Testing Strategy

### End-to-End Tests (`test_e2e.py`)
Complete workflows: create network → validate → build → verify. Tests realistic scenarios like audio-reactive visualization, hierarchical networks, feedback loops.

### Unit Tests (`test_builder_api.py`, `test_registry.py`, etc.)
Test individual components in isolation. Particularly important for registry lookups and parameter validation.

### Round-Trip Tests (`td_fixture_pipeline.py` with real .toe files)
Parse real TouchDesigner projects → rebuild → compare. Current test fixture:
```
C:\TD_Projects\gpt\bigtest\LorenzAttractor_Yoav.20.toe (647,626 bytes, 192 operators)
```
Achieves 100% file preservation with v5 fix.

### Validate Expanded `.dir` Folders (`td_validate_expanded.py`)
Use this when `toecollapse` warns about missing files, or when a `.toc`/`.dir` pair is out of sync:
```
python cli/td_validate_expanded.py "path/to/project.toe.dir"
python cli/td_validate_expanded.py "path/to/project.tox.dir" --strict-extra
```

### Performance Benchmarks (`test_performance.py`)
Measure validation speed, build time, conversion time. Run with `python tests/test_performance.py`.

## Common Pitfalls

### 1. Parameter Flag Issues
**.parm files use a numeric TD mode field:** `param_name MODE value [expression...]`

Common modes (observed; not fully reverse-engineered):
- `0` - Simple constant
- `17` - Constant + expression payload (common for expressions)
- others (`16`, `32`, `48`, `49`, ...) occur in real projects and should be preserved when known

**In BASIC mode:** Use mode `0` unless you know the exact TD numeric mode required.
**In LOSSLESS mode:** Preserve the numeric mode via `ParameterValue.td_mode`.

### 2. Builder JSON Round-Trip
**Do NOT** round-trip through builder JSON for lossless workflows. Builder format is intentionally simplified and drops `lossless_data`. Use Extended or Lossless format for perfect preservation.

### 3. Parent Paths
All operator paths are **absolute** in Extended format: `/project1/base1/noise1`

Builder format allows **relative** paths: `"noise1"` or `"base1/noise1"`

FormatConverter handles this automatically, but if manually constructing operators, use absolute paths.

### 4. Component Inputs
Component-level inputs (e.g., `geo2` COMP with input from `wire1`) are stored in `.network` files, NOT `.n` files. These are preserved in `lossless_data.raw_files`. Losing `.network` files breaks connections.

## Documentation Map

- **README.md** - Overview, quick start, examples
- **docs/USER_GUIDE.md** (~800 lines) - Complete API reference, 4 examples, troubleshooting
- **docs/ARCHITECTURE.md** (~600 lines) - Design decisions, data flow, extension points
- **docs/MIGRATION_GUIDE.md** (~400 lines) - Migrating from legacy formats

Phase documentation:
- **PHASE1-8_COMPLETE.md** - Individual phase completion summaries

Recent achievements:
- **V5_ACHIEVEMENT_SUMMARY.md** - Perfect round-trip achievement (Dec 2024)
- **WIRE_CONNECTION_FIX_V5.md** - Technical details of v5 bug fix

## Performance Characteristics

From `tests/test_performance.py`:

| Operation | 10 ops | 100 ops | 1000 ops |
|-----------|--------|---------|----------|
| Validation | 3ms | 26ms | 282ms |
| Network Creation | 470ms | 468ms | 503ms |
| Format Conversion | - | ~500ms | - |

Validation is extremely fast (<30ms for typical networks). Building is dominated by file I/O.

## MCP Integration

Three MCP tools in `kb_pipeline/mcp/unified_mcp_server.py`:

1. **td_validate** - Validate network JSON with 5-stage pipeline
2. **td_convert** - Convert between format layers
3. **td_build_network** - Build .toe/.tox from JSON

These expose the unified system to AI agents via Model Context Protocol.

## Known Limitations

1. **Canonical → Builder conversion incomplete** - Use Extended as intermediate
2. **Binary files in BASIC mode** - Not generated (use LOSSLESS for round-trip)
3. **Requires toecollapse** - Manual step after build (TouchDesigner's official workflow)

All limitations documented in USER_GUIDE.md with workarounds.

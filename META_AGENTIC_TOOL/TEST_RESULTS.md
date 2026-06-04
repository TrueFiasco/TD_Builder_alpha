# Test Results Log

**Tester**: QUEENIE
**Date**: 2024-12-24
**Session**: BASIC_1-10 (Human validation in TouchDesigner)

---

## Session Status

| Phase | Tests | Passed | Failed | Status |
|-------|-------|--------|--------|--------|
| Tests 1-10 | 10 | 7 | 3 | **COMPLETE** |
| Bugs Found | 3 | - | - | LOGGED |

---

## Bug Summary (Tests 1-10)

| Bug | Test | Severity | Owner | Issue |
|-----|------|----------|-------|-------|
| BUG-005 | 5 | LOW | PETER | DAT to CHOP layout mismatch (cpr/cpc) |
| BUG-008/009 | 8,9 | **HIGH** | TERRY | Palette connections not created |
| BUG-010 | 10 | MEDIUM | PETER | GLSL uTD2DInfos vs uTDOutputInfo |

---

## TEST SESSION 2024-12-24

### TEST-001 through TEST-004: PASS
Basic operators working correctly.

### TEST-005: DAT to CHOP
**Result**: **FAIL**
**Bug**: Table layout didn't match datto CHOP output mode
- Created table with channels per column
- datto was configured for channels per row (`output: cpr`)
- Agent didn't call OP expert before creating datto setup
**Report**: `output/BUG_REPORT_05_datto_extractrows_2025-12-24.md`

---

### TEST-006, TEST-007: PASS
Palette embedding (julia, slider2D) working.

---

### TEST-008: Audio Analysis with Connections
**Result**: **FAIL**
**Bug**: Connections TO palette component not created
- audiodevicein1 -> audioAnalysis wire missing
- audioAnalysis -> null_audio wire missing
**Report**: `output/BUG_REPORT_08-09_palette_connections_2025-12-24.md`

---

### TEST-009: Container with Palette Inside
**Result**: **FAIL**
**Bug**: Same as TEST-008 - palette connections broken
- Wires to/from embedded audioAnalysis not created
**Report**: `output/BUG_REPORT_08-09_palette_connections_2025-12-24.md`

---

### TEST-010: GLSL Shader (Dali Scene)
**Result**: **FAIL** (then fixed)
**Bug**: Shader compilation error - wrong uniform
- Used `uTD2DInfos[0]` which requires connected inputs
- Should use `uTDOutputInfo` for standalone shaders
- Agent didn't call GLSL expert before writing shader
**Report**: `output/BUG_REPORT_10_glsl_uTD2DInfos_2025-12-24.md`
**Status**: Fixed after manual correction

---

## Summary

```
Tests Run:     10
Tests Passed:  7
Tests Failed:  3
Pass Rate:     70%
```

### Working
- Basic operators (CHOP, SOP, TOP)
- Palette embedding (standalone, no connections)
- Cross-family connections (non-palette)
- Multi-input operators

### Broken
- Palette component connections (HIGH priority)
- DAT-to-CHOP workflow guidance
- GLSL standalone shader patterns

---

## Bug Details

### BUG-005 (Test 5) - DAT to CHOP Layout
- **Root cause**: Agent didn't call OP expert before creating datto setup
- **Fix needed**: OP expert MUST be called for DAT<->CHOP conversions
- **Rule to add**: When using datto CHOP, verify table layout matches output mode

### BUG-008/009 (Tests 8,9) - Palette Connections
- **Root cause**: Tool doesn't resolve palette component -> internal in/out operators
- **Fix needed**: TERRY must update td_build_project to handle palette wiring
- **BLOCKING**: Audio-reactive workflows completely broken
- **Workaround**: Use Select CHOPs with explicit paths

### BUG-010 (Test 10) - GLSL Uniforms
- **Root cause**: Agent didn't call GLSL expert before writing shader
- **Fix needed**: GLSL expert MUST be called for any shader generation
- **Rule exists**: `td_glsl.yaml` has this info, just wasn't consulted

---

## Action Items

| Priority | Task | Owner |
|----------|------|-------|
| HIGH | Fix palette connection wiring in td_build_project | TERRY |
| MEDIUM | Add OP expert call requirement for DAT<->CHOP | PETER |
| MEDIUM | Add GLSL expert call requirement for shaders | PETER |
| LOW | Add cpr/cpc layout guidance to KB | KYLE |

---

## SESSION 2: Tests 7-14 (2024-12-24) - FINAL

### Status: COMPLETE

| Test | Description | Result | Notes |
|------|-------------|--------|-------|
| 7 | Julia Palette | **PASS** | 3,882 bytes |
| 8 | Audio Analysis Setup | **PASS** | 132,194 bytes |
| 9 | Show Controls Container | PARTIAL | BUG-003: COMP input connections |
| 10 | Dalí GLSL Scene | PARTIAL | 5.2/10 quality, BUG-004 |
| 11 | Fan-Out Network | **PASS** | After using string operand |
| 11b | Operand Format Tests | **PASS** | Discovered BUG-005 |
| 12 | Noise Merge Analyze | FAIL→PASS | BUG-006: strings vs integers |
| 13 | Feedback Trails | **FAIL** | BUG-007: Multiple issues |
| 14 | Cross-Container Refs | PARTIAL | BUG-008: Internal connections |

**Summary**: 3 PASS, 3 PARTIAL, 2 FAIL

---

### BUG-011: Composite TOP Type Resolution - FIXED

**Status**: FIXED
**Owner**: TERRY (Tool) + KYLE (KB)

---

### BUG-012: Menu Parameter Integer Corruption

**Severity**: MEDIUM
**Affects**: Tests 11, 13, and any operator with menu parameters
**Owner**: TERRY (Tool)

**Issue**: Integer values passed to menu parameters are corrupted during build. Strings work correctly.

**Evidence**:
| Input | Expected | Actual in TD |
|-------|----------|--------------|
| `operand: 0` | add | atop (index 1) |
| `operand: 9` | difference | soft_light (index 36) |
| `operand: "add"` | add | add ✓ |

**Workaround**: Use string names for menu parameters
```json
{"operand": "add"}      // WORKS
{"operand": 0}          // BROKEN
```

**Report**: `output/BUG-005_composite_operand_string.md`

---

### BUG-013: Agent KB Workflow - Web Search Before KB

**Severity**: MEDIUM
**Affects**: Test 12
**Owner**: PETER (Agent prompts)

**Issue**: Agent used web search to find Analyze CHOP parameter values instead of querying KB first.

**Discovery**: Menu parameter format is INCONSISTENT across operators:
| Operator | Parameter | Strings | Integers |
|----------|-----------|---------|----------|
| Composite TOP | operand | WORK | CORRUPTED |
| Analyze CHOP | function | DEFAULT TO 0 | WORK |

**Agent workflow should be:**
1. `td_get_expertise("operators")` - Sweet 16 info
2. `td_get_expertise("parameters")` - if values unclear
3. Check OP snippets in KB
4. Web search as LAST resort

**Report**: `output/BUG-006_agent_kb_workflow.md`

---

## Bug Summary (All Sessions)

| Bug | Test | Severity | Owner | Issue | Status |
|-----|------|----------|-------|-------|--------|
| BUG-003 | 9 | **HIGH** | TERRY | COMP input connections (.network file) | NEW |
| BUG-004 | 10 | MEDIUM | PETER | GLSL quality checklist needed | NEW |
| BUG-005 | 11 | MEDIUM | TERRY | Menu param integer corruption | WORKAROUND |
| BUG-006 | 12 | MEDIUM | PETER | Agent KB workflow - web before KB | NEW |
| BUG-007 | 13 | **HIGH** | PETER | Feedback loop checklist needed | NEW |
| BUG-008 | 14 | **HIGH** | TERRY | Container internal connections | NEW |
| ~~BUG-011~~ | 11,13 | ~~HIGH~~ | ~~TERRY+KYLE~~ | Composite TOP type resolution | **FIXED** |

### Legacy Bugs (Session 1)
| Bug | Test | Severity | Owner | Issue | Status |
|-----|------|----------|-------|-------|--------|
| BUG-005(old) | 5 | LOW | PETER | DAT to CHOP layout mismatch | KB DONE |
| BUG-008/009(old) | 8,9 | **HIGH** | TERRY | Palette connections not created | PENDING |
| BUG-010 | 10 | MEDIUM | PETER | GLSL uTD2DInfos vs uTDOutputInfo | PENDING |

---

## Updated Action Items

| Priority | Task | Owner | Status |
|----------|------|-------|--------|
| **HIGH** | Fix COMP input connections (.network file) | TERRY | NEW |
| **HIGH** | Fix container internal connections | TERRY | NEW |
| **HIGH** | Create feedback loop checklist | PETER | NEW |
| **HIGH** | Fix palette connection wiring | TERRY | PENDING |
| MEDIUM | Fix menu parameter integer corruption | TERRY | WORKAROUND |
| MEDIUM | Create GLSL quality checklist | PETER | NEW |
| MEDIUM | Enforce KB-first workflow in prompts | PETER | NEW |
| MEDIUM | Document menu param formats (int vs string) | KYLE | NEW |
| LOW | Add cpr/cpc layout guidance to KB | KYLE | DONE |
| ~~HIGH~~ | ~~Fix Composite TOP type resolution~~ | ~~TERRY~~ | **DONE** |

---

## Systemic Issues

### 1. Container/COMP Wiring
Tool cannot create:
- External wires INTO container inputs (BUG-003)
- Internal wires between operators in containers (BUG-008)
- Palette component connections (BUG-008/009 old)

### 2. Menu Parameter Format Inconsistency (SYSTEMIC)

**Scope**: ALL menu parameters that show strings in TD UI but expect integers.

| Operator | Parameter | Strings | Integers |
|----------|-----------|---------|----------|
| Composite TOP | operand | WORK | CORRUPTED |
| Analyze CHOP | function | DEFAULT TO 0 | WORK |
| Noise CHOP/TOP | type | ? | ? |
| Math CHOP | operations | ? | ? |
| Level TOP | modes | ? | ? |

**Workaround**: Use strings for menu params until fixed
**Status**: TERRY investigating - awaiting update

### 3. Agent Checklists Needed
- GLSL quality (camera, ground, performance)
- Feedback loops (animation, format, wiring, decay)
- DAT-to-CHOP (layout matches output mode)

---

## Key Learnings (Session 2)

### Parameter Format Rules
| Operator | Parameter | Format | Notes |
|----------|-----------|--------|-------|
| Composite TOP | operand | STRING | integers corrupted |
| Analyze CHOP | function | INTEGER | strings default to 0 |
| Noise CHOP | type | STRING | "harmonic", "sparse" |

### Feedback Loop Requirements
1. Source MUST be animated (expression, not static)
2. Feedback TOP needs WIRE input + `top` parameter
3. Use 16float or 32float pixel format
4. Level decay opacity < 1.0
5. Test `over` operand before `add`

---

*Last Updated: 2024-12-24 - SESSION 2 COMPLETE (Tests 7-14)*

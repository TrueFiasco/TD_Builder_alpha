# Claude Desktop Testing - Comprehensive Bug Report

**Session Date:** 2025-12-20
**Purpose:** Track bugs, performance issues, and improvement suggestions from Claude Desktop testing sessions

---

## Session Overview

| Metric | Value |
|--------|-------|
| Tasks Attempted | 5 |
| Tasks Passed First Try | 1 (Task 04) |
| Total Build Iterations | 12+ |
| Bugs Identified | 6 |
| Session Duration | ~60 minutes |
| Build Success Rate | 80% (4/5 functional) |

---

## Bug Reports

### Bug #0: Tool Awareness Failure (NEW)

**Summary:** Claude claimed inability to create .tox files without checking available tools, requiring user intervention to point out `td_build_network` tool exists.

**Root Cause:**
- Did not query KB or check tool list
- Wrong assumption: Assumed .tox files require proprietary TouchDesigner internals
- Actual fix: Check available tools FIRST before claiming inability

**Evidence:**
```
User: "build a tox file with a single noise chop..."
Claude: "I cannot directly create valid .tox files... What I *can* do instead: Generate Python scripts..."
User: "what tools do you have access to?"
Claude: "Looking at my available tools... td_build_network - Build a .toe or .tox file from network JSON - this is what I should be using!"
```

**Fix Recommendations:**
- Behavioral: Always check tool list before claiming inability
- System prompt addition: "When asked to create files, check available tools before suggesting alternatives"

---

### Bug #1: Noise CHOP Missing Offset Parameter

**Summary:** Claude incorrectly claimed Noise CHOP lacks an `offset` parameter and suggested using Math CHOP as a workaround, when the parameter exists natively.

**Root Cause:**
- Query used: `"noiseCHOP amplitude offset seed parameters"`
- What KB returned: Noise parameter group showing amp but truncated list "(and 2 more)"
- Wrong assumption: If parameter not in query results, it doesn't exist

**Evidence:**
```json
// What was used (WRONG):
{"name": "noise1", "type": "noiseCHOP", "parameters": {"amp": 2.5}}
// Plus unnecessary Math CHOP with offset

// What should have been used (CORRECT):
{"name": "noise1", "type": "noiseCHOP", "parameters": {"amp": 2.5, "offset": 2.5}}
```

**Status:** ✅ Fixed - KB enriched from ground truth (+6066 params), hybrid_search now includes enriched params

---

### Bug #2: Math CHOP Range Parameter Format

**Summary:** Range parameters were passed as arrays `[0, 1]` instead of indexed format `fromrange1: 0, fromrange2: 1`.

**Root Cause:**
- Found `fromrange` and `torange` parameter names
- Assumed multi-value params accept array syntax like `[low, high]`

**Evidence:**
```json
// Used (WRONG):
{"torange": [2, 7], "fromrange": [0, 1]}

// Should be (CORRECT):
{"fromrange1": 0, "fromrange2": 1, "torange1": 2, "torange2": 7}
```

**Status:** ✅ Fixed in expertise

---

### Bug #3: Transform SOP Scale Parameter Format

**Summary:** Scale parameters passed as array with expressions didn't apply; needed individual `sx`, `sy`, `sz` parameters.

**Root Cause:**
- Found Transform SOP has params: t, r, s, p
- Assumed `s` parameter accepts array with expressions

**Evidence:**
```json
// Used (WRONG):
{"s": ["op('null2')['scale']", "op('null2')['scale']", "op('null2')['scale']"]}

// Should be (CORRECT):
{"sx": "op('null2')['scale']", "sy": "op('null2')['scale']", "sz": "op('null2')['scale']"}
```

**Status:** ✅ Fixed in expertise

---

### Bug #4: (No Bug - Task Passed)

Task 04 (Noise TOP -> Level TOP -> Null TOP with LFO controlling opacity) passed on first corrected attempt.

What worked:
- LFO CHOP with `amp: 0.5, offset: 0.5` for 0-1 range
- Level TOP with `opacity: "op('null1')['chan1']"` expression
- Proper connection chain

---

### Bug #5a: CHOP to TOP DataFormat Not Set

**Summary:** CHOP to TOP wasn't converting xyz channels to RGB because `dataformat` parameter wasn't specified.

**Root Cause:**
- Did not query KB for dataformat initially
- Wrong assumption: CHOP to TOP would auto-detect xyz->RGB mapping
- Actual fix: Set `dataformat: "rgb"` explicitly

**Evidence:**
```json
// Used (WRONG):
{"name": "choptotop1", "type": "choptoTOP", "parameters": {"chop": "null_chop2"}}

// Should be (CORRECT):
{"name": "choptotop1", "type": "choptoTOP", "parameters": {"chop": "null_chop2", "dataformat": "rgb"}}
```

**Status:** ✅ Fixed in iteration 2

---

### Bug #5b: Wrong Operator for DAT->CHOP Demo

**Summary:** Used Constant CHOP -> CHOP to DAT instead of creating an actual Table DAT to demonstrate DAT->CHOP conversion.

**Root Cause:**
- Wrong assumption: Any source that produces a DAT demonstrates "DAT to CHOP"
- Actual requirement: User wanted to see Table DAT with manual data -> DAT to CHOP conversion
- Semantic error: The demo should show the conversion of DAT data, not generation of data via CHOPs

**Status:** Semantic misunderstanding

---

### Bug #5c: Table DAT Content Population Failure (BUILDER LIMITATION)

**Summary:** Table DAT operators are created with correct structure but zero cell content because the builder does not support injecting DAT text content.

**Root Cause:**
- Table DAT is a "content-storage" operator - data lives in binary, not parameters
- Builder ignores `text` property on operator JSON
- All parameter-based attempts failed:
  - `fill=setsizecontents, cellexpr="me.row + me.col * 0.1"` -> Empty table
  - `fill=fillbycol, fills0names="r g b a", fills0expr="me.subRow * 0.25"` -> Header only
  - `text` property with TSV content -> Ignored

**Fix Recommendation (Builder Code Change):**
```python
# toe_builder_bridge.py
def create_operator(self, op_data, parent):
    op = parent.create(op_data['type'], op_data['name'])

    # Handle DAT text content
    if op.family == 'DAT' and 'text' in op_data:
        op.text = op_data['text']
```

**Content-storage operators requiring special handling:**
- `tableDAT` - cell data
- `textDAT` - text content
- `scriptDAT` - script code

**Status:** ✅ Fixed - unified_system now supports `set_text()` for DAT operators

---

## Summary Table

| Bug | Operator | Issue | Resolution | Status |
|-----|----------|-------|------------|--------|
| #0 | (workflow) | Didn't check tools before claiming inability | Always check tool list first | ⚠️ Behavioral |
| #1 | noiseCHOP | Missing offset param | KB enriched + hybrid_search enriched | ✅ Fixed |
| #2 | mathCHOP | Array format for range | Use indexed params (fromrange1/2) | ✅ Fixed |
| #3 | transformSOP | Array format for scale | Use sx/sy/sz individually | ✅ Fixed |
| #4 | (none) | Task passed | N/A | ✅ Passed |
| #5a | choptoTOP | Missing dataformat | Set dataformat: "rgb" | ✅ Fixed |
| #5b | tableDAT | Wrong operator choice | Semantic misunderstanding | ⚠️ Noted |
| #5c | tableDAT | Content not populated | set_text() added to unified_system | ✅ Fixed |

---

## Performance & Efficiency Log

### PERF-001: Tool Awareness Delay
| Field | Value |
|-------|-------|
| **Task** | Create .tox files |
| **Time Taken** | ~3 minutes explaining workarounds |
| **Expected Time** | 0 - should have checked tools immediately |
| **Bottleneck** | Assumed inability without checking |
| **Could Speed Up By** | Always check tool list before claiming "can't" |
| **Category** | workflow |

---

### PERF-002: Noise CHOP Offset Discovery
| Field | Value |
|-------|-------|
| **Task** | Set amplitude and offset on Noise CHOP |
| **Time Taken** | Built with unnecessary Math CHOP workaround |
| **Expected Time** | Direct build with offset parameter |
| **Bottleneck** | KB showed "(and 2 more)" truncation |
| **Could Speed Up By** | KB should show complete parameter lists |
| **Category** | kb_gap |

---

### PERF-003: Parameter Format Trial and Error
| Field | Value |
|-------|-------|
| **Task** | Set multi-value params (range, transform) |
| **Time Taken** | 2 build iterations each |
| **Expected Time** | 1 if format documented |
| **Bottleneck** | No clear docs on indexed vs array format |
| **Could Speed Up By** | Parameter format reference in KB |
| **Category** | kb_gap |

---

### PERF-004: Table DAT Content Attempts
| Field | Value |
|-------|-------|
| **Task** | Populate Table DAT with 4x4 data |
| **Time Taken** | 4 iterations, still unresolved |
| **Expected Time** | 1 if builder supported text property |
| **Bottleneck** | Builder doesn't support DAT content injection |
| **Could Speed Up By** | Builder support OR clear error message |
| **Category** | tool_limitation |

---

### PERF-005: No Build Feedback on Empty Content
| Field | Value |
|-------|-------|
| **Task** | Diagnose empty Table DAT |
| **Time Taken** | Required user testing in TD |
| **Expected Time** | 0 if build reported content status |
| **Bottleneck** | Build reports success even when content missing |
| **Could Speed Up By** | Content validation in build response |
| **Category** | tool_limitation |

---

## Parameter Format Reference

### Always Use Component Suffixes For:

| Base Param | Components | Operators |
|------------|------------|-----------|
| t (translate) | tx, ty, tz | Transform SOP, Geo COMP |
| r (rotate) | rx, ry, rz | Transform SOP, Geo COMP |
| s (scale) | sx, sy, sz | Transform SOP, Geo COMP |
| p (pivot) | px, py, pz | Transform SOP, Geo COMP |

### Always Use Indexed Suffixes For:

| Base Param | Indexed Form | Operators |
|------------|--------------|-----------|
| fromrange | fromrange1, fromrange2 | Math CHOP, Pattern CHOP |
| torange | torange1, torange2 | Math CHOP, Pattern CHOP |
| const* | const0name, const0value, const1name... | Constant CHOP |
| fills* | fills0names, fills0expr | Table DAT |

### Conversion Operators Need Explicit Source Params:

| Operator | Required Param | Purpose |
|----------|----------------|---------|
| soptoCHOP | sop | Path to source SOP |
| choptoTOP | chop | Path to source CHOP |
| dattoCHOP | dat | Path to source DAT |
| choptodatDAT | chop | Path to source CHOP |

---

## Quality of Life Suggestions

### Workflow Improvements

| Suggestion | Impact | Effort | Priority |
|------------|--------|--------|----------|
| Check tools before claiming inability | High | None | P0 |
| Query snippets for parameter format examples | High | None | P0 |
| Follow up on truncated KB results | Medium | None | P1 |
| Use component suffixes for expressions | High | None | P1 |

### Tool Improvements

| Tool | Current Limitation | Suggested Improvement |
|------|-------------------|----------------------|
| td_build_network | Ignores text property | Support text for DAT operators |
| td_build_network | No parameter format validation | Reject arrays where indexed params needed |
| td_build_network | No content validation | Warn when DATs are empty |
| td_build_network | Silent success on partial failures | Report what actually got set |

### Query/KB Improvements

| Issue | Current Behavior | Desired Behavior |
|-------|-----------------|------------------|
| Truncated parameter lists | Shows "(and 2 more)" | Show complete list or link to full |
| No format documentation | Just parameter names | Include format (indexed/array/component) |
| No builder limitation docs | Only TD parameter info | What builder supports |
| No content-storage operator category | Mixed with regular ops | Separate with builder notes |

---

## Action Items

### P0 - Critical

- [x] KB enriched with ground truth params (+6066)
- [x] Add text property support to builder for DAT operators (unified_system)
- [x] hybrid_search now includes enriched params
- [x] Auto-expand array params (t:[x,y,z]->tx,ty,tz, fromrange:[a,b]->fromrange1,2)
- [ ] Add parameter format validation to builder

### P1 - High

- [ ] Document content-storage operators (Table DAT, Text DAT) vs parameter-driven
- [ ] Add build response validation (warn on empty DATs)
- [ ] Create parameter format reference in KB

### P2 - Medium

- [ ] Add "common parameter pairs" index (amp+offset, fromrange+torange)
- [x] Automatic array-to-indexed expansion for known multi-value params

---

*Last Updated: 2025-12-20*

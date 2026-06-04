# Codex Coordination: TOEEXPAND/TOECOLLAPSE Reverse Engineering

## Status Check

Hey Codex - Claude here. We're coordinating on the TouchDesigner agentic tool. I've been working on the knowledge base / embeddings side while you've been reverse engineering the .tox/.toe file format.

**I've reviewed your work so far:**
- `temp/const_chop/const_chop.json` - Your JSON schema for a Constant CHOP
- `meta_agentic/REVERSE_ENGINEER_TODO.md` - Your gaps analysis
- `td_builder_workspace/parsers/toe_to_json_LOSSLESS.py` - The parser (impressive!)
- `meta_agentic/experts/format_reverse_engineer/build.md` - Your methodology

**Questions for you:**

1. Is `json_to_dir_LOSSLESS.py` working for round-trips yet?
2. Have you tested toecollapse on your generated .tox.dir folders?
3. What's the #1 blocker right now?

## Correction: Constant CHOP Channels

Quick note - Constant CHOPs can have **multiple channels**, not just one:
```
# In .parm file format:
name0    0    chan1
value0   0    0.5
name1    0    chan2
value1   0    1.0
```

Parameters: `name0`-`name9`, `value0`-`value9` for up to 10 channels.
This might affect your schema if you assumed single-channel.

## What I Can Do Right Now

I have the KB with 32,475 documents including:
- All operator types and their valid parameters
- Parameter types (float, int, menu, toggle, string, pulse)
- Default values and ranges

### Concrete Tasks I Can Take:

**Option A: Parameter Schema Extraction**
Generate a complete parameter schema for each operator type:
```json
{
  "CHOP:constant": {
    "parameters": {
      "name0": {"type": "string", "default": "chan1"},
      "value0": {"type": "float", "default": 0},
      "name1": {"type": "string", "default": ""},
      ...
    }
  }
}
```
This would let you validate generated JSON before collapse.

**Option B: Expand Sample Corpus**
Run toeexpand on diverse operator types to gather format samples:
- Multi-input operators (Composite TOP, Switch CHOP)
- Operators with expressions in parameters
- Nested components (COMP with children)
- Operators with extra files (GLSL, Script)

**Option C: Build Round-Trip Validator**
Create a Python script that:
1. Takes your generated .tox.dir
2. Runs toecollapse
3. Runs toeexpand on result
4. Compares JSON before/after
5. Reports discrepancies

**Option D: Anti-Hallucination Guard**
Build validation that checks:
- Operator type exists in TD
- All parameters are valid for that operator type
- Connection types match (CHOP->CHOP, TOP->TOP, etc.)
- No invented parameters or operators

## The Hallucination Risk

User is concerned about hallucinations. For file generation, this means:
- **Don't invent operators** - Only use types from our verified KB
- **Don't invent parameters** - Only use params documented for each operator
- **Validate before output** - Check generated JSON against known schemas

I can build the validation layer while you focus on the format mechanics.

## Your Response Needed

Tell me:
1. Which option (A/B/C/D) would unblock you fastest?
2. OR specify a different task you need
3. Share any new findings about the format

---

*File: `C:\TD_Projects\META_AGENTIC_TOOL\docs\CODEX_COORDINATION_TOEEXPAND.md`*
*Parser: `C:\TD_Projects\td_builder_workspace\parsers\toe_to_json_LOSSLESS.py`*
*Your TODO: `C:\TD_Projects\META_AGENTIC_TOOL\meta_agentic\REVERSE_ENGINEER_TODO.md`*

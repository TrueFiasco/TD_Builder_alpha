# Phase 1 Agent System - Test Guide

## Quick Start Test

### Your Original Prompt:
```
"Create an interactive TouchDesigner project that showcases 
the fractal-like nature of salt crystals using POPs"
```

### How to Run This Through Phase 1 Agents:

---

## Manual Test (No MCP Tool Yet)

### Step 1: Creative Director

**You say**:
```
[Acting as Creative Director]
[Load: C:\TD_Projects\mcp_server\agents\creative_director.md]

User request: "Create an interactive TouchDesigner project that showcases 
the fractal-like nature of salt crystals using POPs"

Please create a Creative Brief.
```

**Creative Director should**:
1. Ask clarifying questions
2. Create detailed Creative Brief in JSON format
3. Hand off to Technical Architect

**Example Output**:
```json
{
  "project_title": "Salt Crystal Genesis",
  "vision": "Mesmerizing visualization of crystalline growth...",
  "aesthetics": ["crystalline", "geometric", "organic"],
  "interactions": [{"input": "audio", "response": "growth rate"}],
  "performance_context": {"type": "VJ set", "duration": "4 hours"}
}
```

---

### Step 2: Technical Architect

**You say**:
```
[Acting as Technical Architect]
[Load: C:\TD_Projects\mcp_server\agents\technical_architect.md]

Here is the Creative Brief from Creative Director:
<paste Creative Brief JSON>

Please create a Technical Specification.
Use TouchDesigner MCP tools to research operators.
```

**Technical Architect should**:
1. Use `touchdesigner:list_pop_operators()` (POPs mentioned!)
2. Use `touchdesigner:hybrid_search("particle crystal growth")`
3. Use `touchdesigner:get_operator_info("POP Network")`
4. Create Technical Specification in JSON format
5. Hand off to Builder

**Example Output**:
```json
{
  "feasibility": "feasible",
  "approach": "POP particle system with attraction forces",
  "operator_families": {"primary": ["POP", "CHOP", "SOP"]},
  "key_operators": [
    {"operator": "popnetPOP", "verified_with": "get_operator_info"}
  ],
  "workflow_choice": {"selected": "text_dat_script"},
  "estimated_complexity": "medium"
}
```

---

### Step 3: Builder

**You say**:
```
[Acting as Builder]
[Load: C:\TD_Projects\mcp_server\agents\builder.md]

Here is the Technical Specification from Technical Architect:
<paste Technical Spec JSON>

Please build the network.
MUST verify EVERY operator and parameter with MCP tools!
```

**Builder should**:
1. Use `touchdesigner:get_operator_info()` for EVERY operator
2. Verify ALL parameters exist
3. Generate Python script with verification comments
4. Hand off to Validator

**Example Output**:
```python
"""
PROJECT: Salt Crystal Genesis
VERIFIED: All operators checked with get_operator_info

OPERATOR VERIFICATION LOG:
- Geometry COMP: geometryCOMP_Class ✓
- POP Network: popnetPOP_Class ✓
- Grid SOP: gridSOP_Class ✓
"""

# Cleanup
try:
    op('/salt_crystal').destroy()
except:
    pass

# Build network...
# (Verified code)

print("✓ Salt Crystal system created")
```

---

### Step 4: Validator

**You say**:
```
[Acting as Validator]
[Load: C:\TD_Projects\mcp_server\agents\validator.md]

Here is the code from Builder:
<paste Python script>

Please validate against all 17 common mistakes.
```

**Validator should**:
1. Check against `common_mistakes_v2.md`
2. Verify tool usage
3. Check code quality
4. Return PASS/FAIL with detailed feedback

**Example Output**:
```json
{
  "status": "PASS",
  "checks_performed": [
    "Operator verification: PASS",
    "Parameter verification: PASS",
    "Wiring syntax: PASS",
    "Common mistakes: NONE FOUND"
  ],
  "ready_for_delivery": true,
  "delivery_instructions": {
    "workflow": "text_dat_script",
    "user_steps": [
      "1. Create Text DAT in TouchDesigner",
      "2. Paste script",
      "3. Right-click → Run Script"
    ]
  }
}
```

---

## Expected Results

For your salt crystal prompt, the system should:

✅ **Creative Director**:
- Recognizes VJ/live performance context
- Defines fractal growth aesthetic
- Specifies audio-reactive interaction

✅ **Technical Architect**:
- Searches POP operators (list_pop_operators)
- Finds POP Network, Force POP, Property POP
- Plans particle→geometry→render pipeline
- Chooses Text DAT workflow (~30 operators)

✅ **Builder**:
- Verifies popnetPOP, forcePOP, etc. with get_operator_info
- Creates particle system with forces
- Sets up audio analysis
- Instances geometry on particles
- Generates ~50-100 lines of Python

✅ **Validator**:
- Confirms all operators verified
- Checks no common mistakes
- Returns PASS
- Provides user instructions

---

## Testing Checklist

### Before Running Test:

- [ ] All 4 agent files created in `C:\TD_Projects\mcp_server\agents\`
- [ ] Creative Director: creative_director.md
- [ ] Technical Architect: technical_architect.md
- [ ] Builder: builder.md
- [ ] Validator: validator.md
- [ ] Protocol: phase1_protocol.md

- [ ] Supporting files available:
- [ ] common_mistakes_v2.md
- [ ] td_project_builder_skill_v3.md
- [ ] TD_MCP_INTEGRATION_GUIDE_v2.md

- [ ] MCP server running with TD tools:
- [ ] touchdesigner:hybrid_search
- [ ] touchdesigner:get_operator_info
- [ ] touchdesigner:query_graph
- [ ] touchdesigner:list_pop_operators

### During Test:

- [ ] Creative Director asks clarifying questions
- [ ] Technical Architect uses MCP tools (check tool usage!)
- [ ] Builder verifies EVERY operator
- [ ] Builder verifies EVERY parameter
- [ ] Validator catches any mistakes
- [ ] Final code is deliverable

### After Test:

- [ ] User can paste into Text DAT
- [ ] Script runs without errors
- [ ] Network appears in TD
- [ ] Matches creative vision
- [ ] Performance acceptable

---

## Common Issues & Fixes

### Issue 1: Agent Doesn't Use Tools

**Problem**: Technical Architect creates spec without using hybrid_search or get_operator_info

**Fix**: Explicitly remind in prompt:
```
"MANDATORY: You MUST use touchdesigner:hybrid_search and 
touchdesigner:get_operator_info before creating the spec."
```

### Issue 2: Builder Guesses Parameters

**Problem**: Builder creates code without verifying parameters

**Fix**: Validator should FAIL with specific mistake reference:
```json
{
  "status": "FAIL",
  "issues": [{
    "issue": "Parameter not verified with get_operator_info",
    "location": "Line 45: op.par.name0 = 'value'",
    "fix": "Use get_operator_info('Point SOP') to verify parameter exists"
  }]
}
```

### Issue 3: Validator Doesn't Catch Mistakes

**Problem**: Validator passes code with known mistakes

**Fix**: Validator must read `common_mistakes_v2.md` before validating

### Issue 4: Agents Don't Stay in Role

**Problem**: Technical Architect makes creative decisions or Creative Director mentions TD operators

**Fix**: Reinforce role boundaries:
```
"Remember: You are the Creative Director. You are TD-IGNORANT. 
Never mention TouchDesigner operators. Focus only on creative vision."
```

---

## Success Criteria

**Phase 1 Test Passes If**:

1. ✅ Creative Director produces valid Creative Brief
2. ✅ Technical Architect uses MCP tools before deciding
3. ✅ Builder verifies every operator with get_operator_info
4. ✅ Builder verifies every parameter
5. ✅ Validator catches any common mistakes
6. ✅ Final code runs in TD without errors
7. ✅ Output matches creative vision
8. ✅ All handoffs use structured JSON

---

## Sample Full Run

### User Input:
```
"Create salt crystals with audio"
```

### Creative Director Output:
```json
{
  "project_title": "Salt Crystal Genesis",
  "vision": "Crystalline growth responding to music",
  "interactions": [{"input": "audio - bass", "response": "particle birth"}]
}
```

### Technical Architect Output:
```json
{
  "feasibility": "feasible",
  "approach": "POP particles with audio-driven forces",
  "key_operators": ["popnetPOP", "audiofileinCHOP"],
  "workflow_choice": "text_dat_script"
}
```

### Builder Output:
```python
"""
VERIFIED: All operators and parameters checked
"""
# 50 lines of verified Python code
```

### Validator Output:
```json
{
  "status": "PASS",
  "ready_for_delivery": true
}
```

### User Receives:
- Working Python script
- Clear instructions
- Project that matches vision

---

## Next: Add MCP Tool

Once manual testing passes, implement `spawn_td_agent` MCP tool for automatic agent spawning.

---

Last Updated: 2024-12-06
Status: Ready for testing

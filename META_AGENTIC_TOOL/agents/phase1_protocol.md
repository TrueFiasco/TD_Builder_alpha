# Phase 1 Agent Coordination Protocol

## Overview

This document defines how the 4 Phase 1 agents work together to build TouchDesigner projects.

## Agent Roles

```
USER REQUEST
     ↓
┌────────────────────┐
│ CREATIVE DIRECTOR  │ → Creative Brief (JSON)
│ (TD Agnostic)      │
└─────────┬──────────┘
          ↓
┌────────────────────┐
│ TECHNICAL ARCHITECT│ → Technical Spec (JSON)
│ (TD Expert)        │
└─────────┬──────────┘
          ↓
┌────────────────────┐
│ BUILDER            │ → Code/JSON Output
│ (GraphRAG)         │
└─────────┬──────────┘
          ↓
┌────────────────────┐
│ VALIDATOR          │ → Pass/Fail + Feedback
│ (Quality Gate)     │
└─────────┬──────────┘
          ↓
     USER DELIVERY
```

## Communication Format

All agent handoffs use structured JSON for clarity and traceability.

### Handoff 1: User → Creative Director

**Input**: Natural language request
**Output**: Creative Brief (JSON)

```json
{
  "project_title": "...",
  "vision": "...",
  "detailed_description": "...",
  "aesthetics": [...],
  "interactions": [...],
  "performance_context": {...},
  "success_criteria": [...]
}
```

### Handoff 2: Creative Director → Technical Architect

**Input**: Creative Brief
**Output**: Technical Specification (JSON)

```json
{
  "feasibility": "feasible/not feasible",
  "approach": "...",
  "operator_families": {...},
  "network_architecture": {...},
  "key_operators": [...],
  "performance_strategy": {...},
  "workflow_choice": {...},
  "estimated_complexity": "simple/medium/complex"
}
```

### Handoff 3: Technical Architect → Builder

**Input**: Technical Specification
**Output**: Python Script OR JSON Structure

```python
# For Text DAT workflow
"""
PROJECT: ...
VERIFIED: All operators checked
"""
# Code here...
```

OR

```json
// For JSON workflow
{
  "metadata": {...},
  "operators": {...},
  "connections": [...]
}
```

### Handoff 4: Builder → Validator

**Input**: Code/JSON + Build Metadata
**Output**: Validation Result (JSON)

```json
{
  "status": "PASS/FAIL/NEEDS_REVIEW",
  "issues_found": [...],
  "ready_for_delivery": true/false
}
```

## Agent Coordination Flow

### Scenario 1: Successful Build

```
User Request: "Create salt crystals with audio"
     ↓
Creative Director
  - Asks clarifying questions
  - Creates Creative Brief
  → PASS to Technical Architect
     ↓
Technical Architect
  - Searches TD documentation (hybrid_search, get_operator_info)
  - Creates Technical Spec
  → PASS to Builder
     ↓
Builder
  - Verifies every operator (get_operator_info)
  - Verifies every parameter
  - Generates Python script
  → PASS to Validator
     ↓
Validator
  - Checks against 17 common mistakes
  - Verifies tool usage
  - Status: PASS ✓
  → DELIVER to User with instructions
```

### Scenario 2: Build Fails Validation

```
User Request: "..."
     ↓
Creative Director → Technical Architect → Builder
     ↓
Builder creates code
  → PASS to Validator
     ↓
Validator
  - Finds critical error: Using string 'box' instead of boxSOP
  - Status: FAIL ✗
  → RETURN to Builder with specific fix
     ↓
Builder
  - Fixes error
  - Resubmits
  → PASS to Validator
     ↓
Validator
  - Status: PASS ✓
  → DELIVER to User
```

### Scenario 3: Vision Modification Needed

```
User Request: "Create 1 million particles at 120fps"
     ↓
Creative Director
  - Creates ambitious Creative Brief
  → PASS to Technical Architect
     ↓
Technical Architect
  - Calculates: 1M particles impossible at 120fps
  - Creates modified spec: "Reduce to 50k particles OR 60fps"
  → DISCUSS with User (via Creative Director)
     ↓
User accepts modification
     ↓
Builder → Validator → DELIVER
```

## MCP Tool for Agent Spawning

### Tool Definition

```python
async def spawn_td_agent(
    agent_name: str,
    input_data: dict,
    context: dict = None
) -> dict:
    """
    Spawn a specialized TD agent in a new conversation
    
    Args:
        agent_name: "creative_director", "technical_architect", "builder", "validator"
        input_data: Agent-specific input (Creative Brief, Tech Spec, etc.)
        context: Optional additional context
    
    Returns:
        Agent output (Creative Brief, Tech Spec, Code, Validation)
    """
```

### Implementation

```python
# Load agent skill
agent_skill_path = f"C:/TD_Projects/mcp_server/agents/{agent_name}.md"
with open(agent_skill_path) as f:
    agent_skill = f.read()

# Load supporting knowledge
knowledge_base = load_knowledge_base()  # common_mistakes, skills, etc.

# Create new Claude conversation with agent context
system_prompt = f"""
{agent_skill}

Supporting Knowledge:
{knowledge_base}

You are now acting as the {agent_name} agent.
"""

# Make API call
response = await anthropic.messages.create(
    model="claude-sonnet-4-20250514",
    system=system_prompt,
    messages=[{
        "role": "user",
        "content": json.dumps(input_data)
    }],
    tools=[...td_mcp_tools...]  # Include TD documentation tools
)

return parse_agent_response(response)
```

## Workflow Implementations

### Option A: Manual Role Switching (Testing)

For initial testing without MCP tool:

```
[User in single Claude conversation]

User: "Create salt crystals with audio"

---

[You become Creative Director]
<Paste creative_director.md content into your context>

I'll create a Creative Brief for this project...

[Output Creative Brief JSON]

---

[You become Technical Architect]
<Paste technical_architect.md content>

I'll translate this into a Technical Specification...
[Use MCP tools to search TD docs]

[Output Technical Spec JSON]

---

[You become Builder]
<Paste builder.md content>

I'll build the network...
[Use MCP tools to verify operators]

[Output Python Script]

---

[You become Validator]
<Paste validator.md content>

I'll validate this code...

[Output Validation Result]
```

### Option B: MCP Agent Tool (Production)

Using the spawn_td_agent tool:

```python
# In main coordinator logic
result = await spawn_td_agent(
    agent_name="creative_director",
    input_data={
        "user_request": "Create salt crystals with audio",
        "user_context": {...}
    }
)

creative_brief = result['output']

# Pass to next agent
tech_spec = await spawn_td_agent(
    agent_name="technical_architect",
    input_data={
        "creative_brief": creative_brief
    }
)

# Continue pipeline...
```

## Error Handling

### If Agent Returns Error

```json
{
  "status": "ERROR",
  "agent": "technical_architect",
  "error_type": "insufficient_information",
  "message": "Cannot determine feasibility without audio format details",
  "needs_clarification": [
    "What audio input source? (microphone/file/stream)",
    "What audio format? (WAV/MP3/etc)"
  ],
  "action": "return_to_creative_director"
}
```

**Response**: Return to appropriate earlier agent or user for clarification

### If Agent Timeout

```json
{
  "status": "TIMEOUT",
  "agent": "builder",
  "partial_output": {...},
  "action": "retry / manual_intervention"
}
```

## State Management

Track the project state through the pipeline:

```json
{
  "project_id": "salt_crystal_001",
  "created": "2024-12-06T12:00:00Z",
  "status": "in_progress",
  "current_agent": "builder",
  "history": [
    {
      "agent": "creative_director",
      "timestamp": "2024-12-06T12:00:00Z",
      "input": {...},
      "output": {...},
      "status": "completed"
    },
    {
      "agent": "technical_architect",
      "timestamp": "2024-12-06T12:05:00Z",
      "input": {...},
      "output": {...},
      "status": "completed"
    },
    {
      "agent": "builder",
      "timestamp": "2024-12-06T12:10:00Z",
      "input": {...},
      "output": null,
      "status": "in_progress"
    }
  ],
  "artifacts": {
    "creative_brief": {...},
    "technical_spec": {...},
    "code": null,
    "validation": null
  }
}
```

## Testing Protocol

### Test 1: Simple Request
**Input**: "Create a rotating box"
**Expected**: All agents PASS, Text DAT script delivered

### Test 2: Complex Request
**Input**: "Create salt crystals with audio"
**Expected**: All agents PASS, ~30 operators, Text DAT script

### Test 3: Validation Failure
**Input**: Force Builder to use wrong syntax
**Expected**: Validator FAILS, returns to Builder

### Test 4: Modification Needed
**Input**: "Create 1 million particles at 240fps"
**Expected**: Technical Architect flags infeasibility, discusses with user

## Success Metrics

Track for each project:
- [ ] Creative Brief captured vision (user confirmation)
- [ ] Technical Spec was feasible
- [ ] Builder verified all operators with tools
- [ ] Validator caught any mistakes
- [ ] Final code runs without errors
- [ ] User satisfied with result

## Next Steps

### For Phase 1 Testing:
1. Test with manual role switching
2. Validate each agent's output format
3. Refine handoff protocols
4. Build MCP spawn_td_agent tool

### For Phase 2:
5. Add specialist consultants
6. Implement parallel consultation
7. Add performance optimization
8. Build learning system

---

Last Updated: 2024-12-06
Status: Ready for Phase 1 Testing
Next: Implement spawn_td_agent MCP tool

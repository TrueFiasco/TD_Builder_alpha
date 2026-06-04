# Agent Interface Specification

## Overview

This document specifies how expert agents are called, what context they receive, what they output, and how they hand off to each other. The system uses a three-step prompt pattern (Plan → Build → Self-Improve) executed via Claude Code conversations.

---

## Expert Catalog

| Expert | Purpose | Prompt Files | Reads | Writes |
|--------|---------|--------------|-------|--------|
| creative_expert | Artistic vision | plan.md, build.md, self_improve.md | §1 | §2 |
| cg_expert | Technical approach | plan.md, build.md, self_improve.md | §1, §2 | §3 |
| critic | Quality validation | plan.md, build.md, self_improve.md | §1-5 | §6 |
| td_designer | Network design | plan.md, build.md, self_improve.md | §1-4 | §5 |
| td_glsl_expert | GLSL shader code | plan.md, build.md, self_improve.md, question.md | §3, §5 | §5 (GLSL nodes) |
| td_python_expert | Python scripting | plan.md, build.md, self_improve.md | §3, §5 | §5 (Python nodes) |
| network_builder | JSON construction | plan.md, build.md, self_improve.md | §5 | §7 |
| summary_generator | Network documentation | plan.md, build.md, self_improve.md | §5, §7 | Documentation |
| **creative_orchestrator** | Multi-expert coordination | **orchestrate.md, state_machine.md** | All | All |

> **Note:** The creative_orchestrator uses a different pattern than domain experts. See [Orchestrator Pattern](#orchestrator-pattern-special-case) below.

---

## Orchestrator Pattern (Special Case)

The **creative_orchestrator** does NOT use the Plan → Build → Self-Improve pattern. Instead, it uses a state machine pattern for coordinating multiple experts across workflow phases.

### Why Different?

| Domain Experts | Orchestrator |
|----------------|--------------|
| Produce artifacts (specs, designs, code) | Coordinates other agents |
| Work on single blackboard section | Reads/writes all sections |
| Self-contained execution | Manages phase transitions |
| Quality via self-improvement | Quality via critic delegation |

### Orchestrator Prompt Files

```
meta_agentic/experts/creative_orchestrator/
├── orchestrate.md      # Main coordination logic
└── state_machine.md    # Phase transition rules
```

#### `orchestrate.md` - Coordination Logic

Defines how the orchestrator:
1. Reads current blackboard state
2. Determines which expert to activate next
3. Assembles context for that expert
4. Interprets expert output
5. Updates blackboard sections
6. Decides when to invoke critic

#### `state_machine.md` - Phase Transitions

Defines the workflow state machine:

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR STATE MACHINE               │
│                                                             │
│  [INIT] ──▶ [CREATIVE] ──▶ [TECHNICAL] ──▶ [DESIGN]       │
│               │    ▲           │    ▲          │           │
│               ▼    │           ▼    │          ▼           │
│            [CRITIC]         [CRITIC]       [CRITIC]        │
│               │                │               │            │
│               └── revision ────┴── revision ───┘            │
│                                                │            │
│                                          [BUILD] ──▶ [DONE]│
└─────────────────────────────────────────────────────────────┘
```

### Orchestrator Context

The orchestrator receives the full blackboard state:

```yaml
orchestrator_context:
  blackboard:
    §1_requirements: {...}
    §2_creative_vision: {...}
    §3_technical_approach: {...}
    §4_available_resources: {...}
    §5_network_design: {...}
    §6_validation_history: {...}
    §7_build_artifacts: {...}

  current_state:
    phase: "creative|technical|design|build"
    iteration: N
    blocking_issues: [...]

  strategy_config:
    preset: "quick_draft|standard|excellence"
    thresholds:
      creative: 0.85
      technical: 0.85
      design: 0.90
    max_iterations: 3
    convergence_window: 2
```

### Orchestrator Output

```yaml
orchestrator_decision:
  action: "activate_expert|request_revision|advance_phase|complete"

  # If activating expert:
  expert_activation:
    expert: "creative_expert|cg_expert|td_designer|critic|..."
    task: "{{task_description}}"
    context_sections: ["§1", "§2"]  # What to include

  # If requesting revision:
  revision_request:
    target_expert: "creative_expert"
    issues: ["{{issue_1}}", "{{issue_2}}"]
    guidance: "{{specific feedback}}"

  # If advancing phase:
  phase_transition:
    from: "creative"
    to: "technical"
    locked_sections: ["§2"]

  reasoning: "{{why this decision}}"
```

---

## Three-Step Prompt Pattern

Each expert follows a Plan → Build → Self-Improve cycle:

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXPERT EXECUTION CYCLE                        │
│                                                                  │
│   ┌──────────┐        ┌──────────┐        ┌──────────────────┐  │
│   │  PLAN    │──────▶│  BUILD   │──────▶│  SELF-IMPROVE    │  │
│   │          │        │          │        │                  │  │
│   │ plan.md  │        │ build.md │        │ self_improve.md  │  │
│   └──────────┘        └──────────┘        └──────────────────┘  │
│                                                   │              │
│                                                   ▼              │
│                                           ┌──────────────┐      │
│                                           │  OUTPUT OK?  │      │
│                                           └──────────────┘      │
│                                                   │              │
│                                       ┌───────────┴───────────┐ │
│                                       │                       │ │
│                                      YES                     NO │
│                                       │                       │ │
│                                       ▼                       ▼ │
│                               ┌──────────────┐      ┌──────────┐│
│                               │ Write to     │      │ Loop back││
│                               │ Blackboard   │      │ to PLAN  ││
│                               └──────────────┘      └──────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Step 1: Plan (`plan.md`)

**Purpose**: Understand the task, gather context, make initial decisions.

**Input Template**:
```yaml
# Expert Invocation: Plan
expert: "{{expert_name}}"
step: "plan"

context:
  user_request: "{{original prompt}}"
  phase: "{{current_phase}}"
  iteration: {{n}}

  blackboard_sections:
    §1_requirements: |
      {{requirements_yaml}}
    §2_creative_vision: |  # if available
      {{creative_yaml}}
    # ... other relevant sections

  expertise_query_results:
    - source: "operators.yaml"
      query: "{{query_used}}"
      results: [...]
    - source: "patterns.yaml"
      query: "{{query_used}}"
      results: [...]

  previous_feedback: |  # if iterating
    {{critic_feedback}}

task: "Create a plan for {{task_description}}"
```

**Output Format**:
```yaml
plan:
  expert: "{{expert_name}}"
  task: "{{task_summary}}"

  understanding:
    goal: "{{what user wants}}"
    constraints: ["{{constraint_1}}", ...]

  approach:
    strategy: "{{high-level approach}}"
    steps:
      - "{{step_1}}"
      - "{{step_2}}"

  gaps_identified:
    - area: "{{gap_description}}"
      impact: "{{how it affects output}}"

  confidence: 0.XX
```

### Step 2: Build (`build.md`)

**Purpose**: Execute the plan and produce the actual output.

**Input Template**:
```yaml
# Expert Invocation: Build
expert: "{{expert_name}}"
step: "build"

plan: |
  {{plan_output_from_step_1}}

context:
  # Same as plan step, plus:
  expertise_to_use:
    - file: "{{expertise_yaml}}"
      sections: ["{{section_1}}", "{{section_2}}"]
```

**Output Format** (varies by expert):
```yaml
# For Creative Expert:
creative_spec:
  concept:
    title: "{{evocative name}}"
    description: "{{2-3 sentence description}}"
  mood:
    primary: "{{mood_name}}"
    # ... full mood specification
  colors:
    # ... full color specification
  # etc.

# For CG Expert:
technical_approach:
  summary: "{{approach description}}"
  techniques:
    primary:
      name: "{{technique_name}}"
      rationale: "{{why this}}"
      td_operators: [...]
  # etc.

# For TD Designer:
network_design:
  description_visual: "{{for creative review}}"
  description_technical: "{{for CG review}}"
  network:
    containers: [...]
  json: {...}
```

### Step 3: Self-Improve (`self_improve.md`)

**Purpose**: Critically evaluate output and improve if needed.

**Input Template**:
```yaml
# Expert Invocation: Self-Improve
expert: "{{expert_name}}"
step: "self_improve"

output: |
  {{output_from_build_step}}

quality_targets:
  creative: 0.85
  technical: 0.85
  design: 0.90

self_review_checklist:
  # Expert-specific checklist items
```

**Output Format**:
```yaml
self_review:
  score: 0.XX
  passed: true|false

  strengths:
    - "{{what works well}}"

  weaknesses:
    - "{{what could be better}}"

  improvements_made:
    - "{{change_1}}"
    - "{{change_2}}"

  revised_output: |
    {{improved_output if changes made}}

  recommendation:
    action: "proceed|iterate|escalate"
    reason: "{{why this recommendation}}"
```

---

## Context Injection

Each expert receives specific sections of the blackboard based on their needs.

### Context Templates

**Creative Expert Context**:
```yaml
context:
  blackboard:
    §1_requirements:
      original_prompt: "..."
      clarifications: [...]
      constraints: [...]

  expertise:
    creative_vision.yaml:
      moods: [...]
      aesthetics: [...]
      color_palettes: [...]

  previous_feedback: null | "..."
```

**CG Expert Context**:
```yaml
context:
  blackboard:
    §1_requirements: {...}
    §2_creative_vision:
      current: {brief, mood, colors, motion, ...}

  expertise:
    operators.yaml:
      by_family: {...}
    patterns.yaml:
      relevant: [...]
    td_pipeline_patterns.yaml:
      audio_reactive: [...]

  previous_feedback: null | "..."
```

**TD Designer Context**:
```yaml
context:
  blackboard:
    §1_requirements: {...}
    §2_creative_vision: {...}
    §3_technical_approach: {...}
    §4_available_resources:
      operators: [...]
      palette_components: [...]
      example_patterns: [...]

  expertise:
    operators.yaml: {...}
    glsl_expertise.yaml: {...}
    python_expertise.yaml: {...}

  available_experts:
    - td_glsl_expert
    - td_python_expert

  previous_feedback: null | "..."
```

**Critic Context**:
```yaml
context:
  blackboard:
    §1_requirements: {...}
    §2_creative_vision: {...}
    §3_technical_approach: {...}
    §4_available_resources: {...}
    §5_network_design: {...}  # if validating design
    §6_validation_history:
      entries: [...]  # previous validations

  section_to_validate: "§2" | "§3" | "§5"
  version_to_validate: N

  quality_targets:
    creative: 0.85
    technical: 0.85
    design: 0.90
```

---

## Expert Consultation Protocol

During the Design phase, TD Designer can consult domain experts.

### Consultation Flow

```
TD Designer                    Domain Expert
     │                              │
     │ ──── question.md ──────────▶ │
     │                              │
     │      "How do I pass audio    │
     │       to a compute shader?"  │
     │                              │
     │ ◀──── answer ─────────────── │
     │                              │
     │      "Use TOP→CHOP→uniform   │
     │       binding in glslTOP"    │
     │                              │
     │ ──── integrate ────────────▶ │
     │       (update network)       │
     │                              │
```

### Question Format (`question.md`)

```yaml
consultation:
  from: "td_designer"
  to: "td_glsl_expert"

  context:
    project: "{{project_summary}}"
    current_network: "{{relevant_portion}}"
    §3_technical_approach: {...}

  question:
    type: "implementation|optimization|validation"
    description: "{{detailed question}}"
    constraints:
      - "{{constraint_1}}"
```

### Answer Format

```yaml
consultation_response:
  expert: "td_glsl_expert"
  question_id: "{{uuid}}"

  answer:
    summary: "{{one-line answer}}"
    explanation: "{{detailed explanation}}"
    implementation:
      code: |
        {{code if applicable}}
      integration_steps:
        - "{{step_1}}"
        - "{{step_2}}"

  validation:
    verified_with: "{{how verified}}"
    confidence: 0.XX

  warnings:
    - "{{potential issue}}"
```

---

## Handoff Protocol

When one expert completes, they hand off to the next expert.

### Handoff Message Format

```yaml
handoff:
  from: "creative_expert"
  to: "cg_expert"
  timestamp: "{{ISO8601}}"

  completed_work:
    section: "§2"
    version: 1
    score: 0.87

  summary: "Creative vision defined: ethereal particle cosmos..."

  key_requirements_for_next:
    - "Particle system needed (compute shader recommended)"
    - "Audio analysis with bass/high band separation"
    - "Blue→orange color mapping based on energy"

  open_questions:
    - "Particle count: user preference not specified"
```

### Handoff Chain

```
┌─────────────────────────────────────────────────────────────────┐
│                    STANDARD HANDOFF CHAIN                        │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Creative │ ──▶│    CG    │ ──▶│ Resource │ ──▶│   TD     │  │
│  │  Expert  │    │  Expert  │    │  Query   │    │ Designer │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│       │               │               │               │         │
│       ▼               ▼               ▼               ▼         │
│      §2              §3              §4              §5         │
│                                                       │         │
│  ┌──────────┐    ┌──────────┐                        │         │
│  │  Critic  │ ◀──│ Network  │ ◀───────────────────────         │
│  │          │    │ Builder  │                                   │
│  └──────────┘    └──────────┘                                   │
│       │               │                                         │
│       ▼               ▼                                         │
│      §6              §7                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Expertise Loading

Experts must load relevant expertise before generating output.

### Load Pattern

```yaml
# In expert prompt
## Required Initialization
Load the following expertise before proceeding:

```python
expertise = {
    'operators': load_yaml('meta_agentic/expertise/operators.yaml'),
    'patterns': load_yaml('meta_agentic/expertise/patterns.yaml'),
    'glsl': load_yaml('meta_agentic/expertise/glsl_expertise.yaml')
}
```

### Query Before Generate

Before generating content:
1. Query operators.yaml for relevant operators
2. Query patterns.yaml for applicable patterns
3. Check palette_expertise.yaml for reusable components
4. Only use documented items in output

---

## Anti-Hallucination Rules

Each expert enforces these rules:

1. **ONLY use operators from operators.yaml**
2. **ALWAYS cite source for technical claims**
3. **If operator unknown, flag for lookup, don't invent**
4. **Validate parameters against parsed_data.json schemas**
5. **Don't invent GLSL uniforms - check glsl_expertise.yaml**

### Validation Checkpoint

```yaml
pre_output_validation:
  operators_verified: true
  - operator: "audioDeviceIn"
    source: "operators.yaml#CHOP"
    verified: true

  parameters_verified: true
  - operator: "audioDeviceIn"
    parameter: "device"
    schema_source: "operator_param_schemas.json"
    verified: true

  patterns_cited: true
  - pattern: "audio_envelope_follower"
    source: "patterns.yaml#audio_reactive"
```

---

## Error Handling

### Expert Errors

```yaml
error_report:
  expert: "td_designer"
  step: "build"
  timestamp: "{{ISO8601}}"

  error:
    type: "missing_operator|invalid_connection|schema_violation"
    description: "{{what went wrong}}"
    context: "{{where in the output}}"

  recovery_action:
    action: "retry|escalate|substitute"
    details: "{{how to recover}}"
```

### Escalation Path

```
Expert Error
     │
     ▼
┌──────────────────────┐
│ Can expert self-fix? │
└──────────────────────┘
     │
    YES ───────▶ Retry with self_improve.md
     │
    NO
     │
     ▼
┌──────────────────────┐
│ Is it expertise gap? │
└──────────────────────┘
     │
    YES ───────▶ Consult domain expert
     │
    NO
     │
     ▼
┌──────────────────────┐
│ Escalate to Critic   │
└──────────────────────┘
     │
     ▼
Critic classifies issue and routes to appropriate phase
```

---

## Claude Code Integration

### Conversation Structure

Each expert invocation is a conversation turn:

```
ORCHESTRATOR: [Activating creative_expert for §2]

CREATIVE_EXPERT (plan.md):
[Reading §1 requirements...]
[Querying creative_vision.yaml...]
[Planning creative vision...]

Output:
plan:
  expert: "creative_expert"
  ...

CREATIVE_EXPERT (build.md):
[Executing plan...]
[Building creative specification...]

Output:
creative_spec:
  ...

CREATIVE_EXPERT (self_improve.md):
[Reviewing output...]
[Score: 0.87 - Pass]

[Writing to §2_creative_vision]

ORCHESTRATOR: [§2 complete, activating critic for validation]
```

### File Locations

```
meta_agentic/experts/
├── creative_expert/
│   ├── plan.md
│   ├── build.md
│   └── self_improve.md
├── cg_expert/
│   ├── plan.md
│   ├── build.md
│   └── self_improve.md
├── critic/
│   ├── plan.md
│   └── build.md
├── td_designer/
│   ├── plan.md
│   ├── build.md
│   └── self_improve.md
├── td_glsl_expert/
│   ├── plan.md
│   ├── build.md
│   ├── self_improve.md
│   └── question.md
├── td_python_expert/
│   ├── plan.md
│   ├── build.md
│   └── self_improve.md
└── network_builder/
    ├── plan.md
    ├── build.md
    └── self_improve.md
```

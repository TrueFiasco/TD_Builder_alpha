# Strategy V2: Improved Current

## Overview

V2 introduces the foundational improvements over baseline: **KB-first** queries before expert work, **self-critique loops** for quality, and **user involvement levels** for collaboration. This is the recommended strategy for standard projects with balanced speed and quality needs.

## When to Use

- Standard projects with reasonable quality expectations
- Quick turnaround needed
- Budget-conscious (moderate token usage)
- Single-path exploration is sufficient

**Not ideal for**:
- Maximum quality requirements (use V5 or V6)
- Creative exploration (use V3)
- Complex interdependencies (use V4)

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    V2: IMPROVED CURRENT                          │
│                                                                  │
│  ┌──────────────────┐                                           │
│  │   User Prompt    │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │  Orchestrator    │                                           │
│  │  (init config)   │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │    KB Query      │  ← Query expertise BEFORE generation      │
│  │  (operators,     │                                           │
│  │   patterns,      │                                           │
│  │   palette)       │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│  ┌────────┼────────────────────────────────────────────────┐    │
│  │        ▼                                                │    │
│  │  ┌──────────────────┐                                   │    │
│  │  │  Creative Phase  │                                   │    │
│  │  │   (with KB)      │                                   │    │
│  │  └────────┬─────────┘                                   │    │
│  │           │                                             │    │
│  │           ▼                                             │    │
│  │  ┌──────────────────┐                                   │    │
│  │  │   Self-Critique  │──┐                                │    │
│  │  │  "Is this        │  │ NO                             │    │
│  │  │   remarkable?"   │  │                                │    │
│  │  └────────┬─────────┘  │                                │    │
│  │           │ YES        │                                │    │
│  │           ▼            │                                │    │
│  │  ┌──────────────────┐  │                                │    │
│  │  │     Critic       │◀─┘                                │    │
│  │  │   (validate)     │                                   │    │
│  │  └────────┬─────────┘                                   │    │
│  │           │                                             │    │
│  │           ▼                                             │    │
│  │  Score >= 0.85?                                         │    │
│  │     │                                                   │    │
│  │   NO └──────▶ (iterate with feedback)──────────────────┘    │
│  │     │                                                        │
│  │   YES                                                        │
│  │     │                                                        │
│  └─────┼────────────────────────────────────────────────────────┘
│        │                                                         │
│        ▼                                                         │
│  [Repeat pattern for Technical, Resources, Design phases]        │
│        │                                                         │
│        ▼                                                         │
│  ┌──────────────────┐                                           │
│  │   User Checkpoint │  ← Based on involvement level            │
│  │   (if milestone)  │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │      Build       │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │  Dual Description│  ← Visual for Creative, Technical for CG  │
│  │      Output      │                                           │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

## Phase Details

### Phase 1: Creative

**Entry Conditions**:
- §1 Requirements written
- KB query complete (relevant expertise loaded)

**Actions**:
1. Load creative_vision.yaml expertise
2. Creative Expert generates vision using Plan→Build→Self-Improve
3. Self-critique: "Is this REMARKABLE, not just adequate?"
4. Critic validates against quality targets

**Exit Conditions**:
- Score >= 0.85 OR max iterations reached
- §2 written with version history

### Phase 2: Technical

**Entry Conditions**:
- §2 Creative Vision approved

**Actions**:
1. Load operators.yaml, patterns.yaml expertise
2. CG Expert selects techniques based on creative vision
3. Document tradeoffs considered
4. Critic validates approach

**Exit Conditions**:
- Score >= 0.85
- §3 written with techniques and tradeoffs

### Phase 3: Resources

**Entry Conditions**:
- §3 Technical Approach approved

**Actions**:
1. Query KB for relevant operators
2. Query palette for reusable components
3. Query patterns for applicable examples

**Exit Conditions**:
- §4 written with comprehensive resource list

### Phase 4: Design

**Entry Conditions**:
- §1-4 complete

**Actions**:
1. TD Designer reads all sections
2. Consults domain experts (GLSL, Python) as needed
3. Generates network JSON
4. Creates dual descriptions (visual + technical)
5. Critic validates design

**Exit Conditions**:
- Score >= 0.90
- §5 written with JSON and descriptions

### Phase 5: Build

**Entry Conditions**:
- §5 Design approved

**Actions**:
1. Validate JSON structure
2. Validate operators exist
3. Build TOE file
4. Verify output

**Exit Conditions**:
- TOE file valid
- §7 written with artifacts

## Configuration Options

```yaml
v2_config:
  involvement: full | milestone | minimal
  # full: Review after every phase
  # milestone: Review after creative, design, build
  # minimal: Only at errors or completion

  quality_targets:
    creative: 0.85
    technical: 0.85
    design: 0.90

  max_iterations:
    per_phase: 5
    total: 15

  kb_query:
    enabled: true
    sources:
      - operators.yaml
      - patterns.yaml
      - palette_expertise.yaml
      - glsl_expertise.yaml
```

## Expected Metrics

```yaml
typical_metrics:
  tokens:
    input: ~20000
    output: ~8000
    total: ~28000

  quality:
    creative: 0.80-0.88
    technical: 0.78-0.86
    design: 0.82-0.90
    final: 0.78-0.85

  iterations:
    creative: 1-3
    technical: 1-2
    design: 2-4
    total: 4-8

  troubleshooting:
    build_failures: ~5%
    validation_errors: 1-3 per run
    phase_reopens: rare

  artifacts:
    uniforms_connected: ~85%
    parameters_functional: ~80%
    palette_used: ~60%
```

## Implementation Notes

### KB-First Pattern

Before any expert generates content:

```python
def execute_phase(self, phase: str, blackboard: Blackboard):
    # 1. Query knowledge base FIRST
    kb_results = self.query_kb_for_phase(phase)

    # 2. Inject into expert context
    context = {
        "blackboard": blackboard.read_relevant_sections(phase),
        "expertise": kb_results
    }

    # 3. Now expert generates with knowledge
    output = self.call_expert(phase, context)
```

### Self-Critique Loop

Each expert asks themselves before submitting:

```yaml
self_critique:
  questions:
    - "Is this REMARKABLE, or just adequate?"
    - "What would make someone remember this?"
    - "Am I using the expertise, or guessing?"

  thresholds:
    remarkable: 0.90+
    good: 0.85-0.90
    adequate: 0.75-0.85
    needs_work: <0.75
```

### Dual Descriptions

Design phase outputs two descriptions:

```yaml
descriptions:
  visual: |
    For Creative Expert review:
    "The network creates a breathing particle cosmos where audio
    energy drives organic swirling motion..."

  technical: |
    For CG Expert review:
    "Audio pipeline: audioDeviceIn → audioSpect → band splitting
    via math CHOPs → envelope followers..."
```

### User Involvement Levels

```python
def check_user_checkpoint(self, phase: str, involvement: str):
    if involvement == "full":
        return True  # Always checkpoint

    if involvement == "milestone":
        return phase in ["creative", "design", "build"]

    if involvement == "minimal":
        return False  # Only on errors
```

## Feedback Routing

When Critic identifies issues:

```yaml
feedback_routing:
  creative_issue:
    symptoms:
      - "Vision unclear"
      - "Lacks distinction"
      - "Mood mismatch"
    route_to: creative_expert
    section: §2

  technical_issue:
    symptoms:
      - "Wrong technique"
      - "Missing optimization"
      - "Constraint violation"
    route_to: cg_expert
    section: §3

  design_issue:
    symptoms:
      - "Connection invalid"
      - "Parameter missing"
      - "Structure unclear"
    route_to: td_designer
    section: §5
```

## Success Criteria

A V2 run is successful when:

- [ ] All phases reach quality targets (0.85/0.85/0.90)
- [ ] TOE file builds without errors
- [ ] GLSL uniforms connected to control center
- [ ] Parameters actually control visual output
- [ ] Palette components used where appropriate
- [ ] KB expertise cited in outputs

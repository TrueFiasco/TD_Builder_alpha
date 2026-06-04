# Meta/Self-Improvement Logic

This document describes the self-improving aspects of the system - how agents learn and how the system improves itself.

---

## Core Principle

> **Generic agents execute and forget. Agent experts execute and LEARN.**

The system is designed around "meta-agentics" - agents that improve themselves through structured learning loops.

---

## Three-Step Expert Workflow

Every expert follows the **Plan → Build → Self-Improve** cycle:

```
┌─────────────────────────────────────────────────────┐
│                    PLAN                              │
│  - Load expertise from KB                           │
│  - Validate against source of truth                 │
│  - Create execution plan                            │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                    BUILD                             │
│  - Execute using validated mental model             │
│  - Log all actions and decisions                    │
│  - Produce structured output                        │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│               SELF-IMPROVE                           │
│  - Analyze what worked/failed                       │
│  - Identify new patterns                            │
│  - Update expertise files if validated              │
└─────────────────────────────────────────────────────┘
```

---

## Self-Improve Step Implementation

### Prompt Structure (self_improve.md)

Each expert has a `self_improve.md` prompt that:

1. **Reviews Build Output**: Analyze what was produced
2. **Identifies Patterns**: Look for reusable learnings
3. **Proposes Updates**: Suggest expertise file changes
4. **Validates Evidence**: Ensure updates are grounded

### Example: Creative Expert Self-Improve

```yaml
self_improve:
  expert: "creative_expert"
  build_reviewed: "teardrop_creative_spec"

  patterns_discovered:
    - pattern: "ethereal_with_audio"
      description: "Ethereal mood works well with breathing audio mapping"
      evidence:
        - "Teardrop visualization success"
        - "Critic score 0.92"
      confidence: 0.8
      source: "teardrop_build_2024-12-18"

    - pattern: "analogous_for_emotional"
      description: "Analogous color palettes enhance emotional coherence"
      evidence:
        - "Blue-cyan-amber palette effective"
      confidence: 0.75

  expertise_updates_proposed:
    - file: "creative_vision.yaml"
      section: "mood_combinations"
      update:
        ethereal_organic:
          description: "Ethereal primary with organic modifier"
          works_well_with:
            - audio_reactive
            - breathing_motion
          color_affinity: "analogous"
      validation_needed: true

  recommendation:
    action: "update_expertise"
    priority: "medium"
    requires_human_review: false
```

---

## Expertise Update Protocol

### Anti-Hallucination Requirements

Before updating expertise files, the system verifies:

```yaml
update_validation:
  - source_exists: true        # File path, example name verified
  - example_count: 3           # >= 3 examples for pattern claims
  - cross_validated: true      # Checked against operator registry
  - confidence_score: 0.75     # Minimum confidence
  - timestamp: "2024-12-18"    # When discovered
  - source_reference: "teardrop_build"  # Traceability
```

### Update Format

```yaml
expertise_update:
  file: "td_network_patterns.yaml"
  section: "workflows.audio_reactive_visuals"

  changes:
    add:
      - key: "feedback_breathing"
        value:
          description: "Feedback loop creates organic breathing"
          evidence_count: 2
          confidence: 0.7

    modify:
      - key: "typical_chain"
        old: ["audiofilein", "analyze", "math"]
        new: ["audiofilein", "analyze", "math", "lag", "feedback"]

  validation:
    source: "teardrop_build_2024-12-18"
    example_count: 2
    confidence: 0.7
    timestamp: "2024-12-18T22:30:00Z"

  status: "proposed"  # proposed → validated → applied
```

---

## Event Log System

All expertise updates go through an append-only event log:

### Event Schema

```python
@dataclass
class EventSchema:
    id: str                    # Unique event ID
    ts: str                    # ISO-8601 timestamp
    agent_id: str              # Which agent made update
    domain: str                # patterns, operators, etc.
    inputs: dict               # What triggered update
    outputs: dict              # What was learned
    evidence: list[dict]       # Source references
    metrics: dict              # Confidence, scores
    status: str                # success, partial, failed
    notes: str                 # Human-readable notes
```

### Event Log Location

```
meta_agentic/
├── history/
│   └── expertise_events.jsonl  # Append-only event log
├── meta/
│   └── expertise_state.yaml    # Materialized state
└── expertise/
    └── *.yaml                  # Working-set views
```

### Adding Events

```python
from compaction import append_event, EventSchema, generate_event_id

event = EventSchema(
    id=generate_event_id(),
    ts=datetime.now().isoformat(),
    agent_id="creative_expert",
    domain="patterns",
    inputs={"prompt": "teardrop visualization"},
    outputs={
        "pattern_discovered": "ethereal_audio_breathing",
        "confidence": 0.8
    },
    evidence=[
        {
            "source_path": "builds/teardrop_2024-12-18.yaml",
            "td_version": "2023.11880",
            "excerpt_hash": "abc123"
        }
    ],
    metrics={"confidence": 0.8, "example_count": 2},
    status="success",
    notes="Discovered breathing pattern works with ethereal mood"
)

append_event(event)
```

---

## Problem Tracking

When errors occur, they're logged for learning:

### Problem Schema

```yaml
problems:
  PROB-001:
    category: "build_failure"
    description: "TOE file failed to open in TD"
    root_cause: "TOC ordering incorrect"
    fix: "Order TOC as .n → .cparm → .parm → .panel"
    prevention:
      - expertise_file: "td_file_formats.yaml"
        update: "Add TOC ordering rules"
    status: "fixed"
    validated: true

  PROB-002:
    category: "hallucination"
    description: "Agent invented 'pulseChop' operator"
    root_cause: "No validation against operator registry"
    fix: "Add validate_operator() check before output"
    prevention:
      - expertise_file: "td_operators.yaml"
        update: "Mark non-existent operators"
    status: "fixed"
    validated: true
```

---

## Compaction Process

Periodically, the event log is compacted into materialized state:

```bash
python -m compaction.compact_expertise
```

This:
1. Reads all events from JSONL
2. Aggregates patterns by confidence
3. Removes superseded updates
4. Writes to `expertise_state.yaml`
5. Updates working-set YAML files

---

## Meta-Agent Capabilities

The system can also generate new components:

### Generate New Expert Templates

```yaml
meta_action: "generate_expert"
input:
  expert_type: "texture_specialist"
  purpose: "Generate and combine procedural textures"
  reads_sections: [TECHNICAL_APPROACH, AVAILABLE_RESOURCES]
  writes_section: NETWORK_DESIGN

output:
  created_files:
    - experts/texture_specialist/plan.md
    - experts/texture_specialist/build.md
    - experts/texture_specialist/self_improve.md
    - experts/texture_specialist/config.yaml
```

### Generate Eval Tasks

```yaml
meta_action: "generate_eval"
input:
  domain: "audio_reactive"
  difficulty: "medium"

output:
  eval_task:
    prompt: "Create audio-reactive circles that pulse with bass"
    expected_operators: ["audiofilein", "analyze", "circle", "composite"]
    success_criteria:
      - operator_accuracy: 0.9
      - builds_successfully: true
```

---

## Current Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| Plan step | ✅ Implemented | All experts |
| Build step | ✅ Implemented | All experts |
| Self-improve step | ⚠️ Partial | Prompts exist, execution stubbed |
| Event log | ✅ Implemented | JSONL append |
| Compaction | ⚠️ Placeholder | Script exists, needs testing |
| Meta-agent generation | ❌ Not yet | Planned |

---

## Learning Loop Diagram

```
User Prompt
    │
    ▼
┌─────────────┐
│ Orchestrator │──────────────────────────────┐
└─────────────┘                               │
    │                                         │
    ▼                                         │
┌─────────────┐     ┌─────────────┐          │
│   Expert    │────▶│   Critic    │          │
│  (Plan →    │     │  (Review)   │          │
│   Build →   │     └──────┬──────┘          │
│   Improve)  │            │                 │
└─────────────┘            │                 │
    │                      │                 │
    │  ┌───────────────────┘                 │
    │  │                                     │
    ▼  ▼                                     │
┌─────────────┐                              │
│  Expertise  │◀─────────────────────────────┘
│    Files    │     (Self-improve updates)
└─────────────┘
    │
    │ (Next run uses improved expertise)
    ▼
```

---

## Future Improvements

1. **Automated Compaction**: Run compaction after N events
2. **Confidence Decay**: Lower confidence of old patterns
3. **Cross-Expert Learning**: Share patterns between experts
4. **Human-in-the-Loop**: Review high-impact updates
5. **A/B Testing**: Compare old vs new expertise

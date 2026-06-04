# Agentic Workflow Architecture

## Overview

This document defines the architecture for a modular, pluggable workflow system that orchestrates expert agents to generate high-quality TouchDesigner networks. The system is executed via **Claude Code** (conversation-based), not direct API calls.

## Core Problem Solved

The existing infrastructure includes 8 expert agents with full prompts and 12 expertise YAML files, but these are never actually called during generation. This architecture provides:

1. **Execution Layer** - Actually invokes experts with proper context
2. **Knowledge Retrieval** - Queries expertise before generation
3. **Expert Chaining** - Orchestrates collaboration between experts
4. **Quality Control** - Validates outputs and triggers refinement

---

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                      WORKFLOW ENGINE                             │
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐ │
│  │   Orchestrator   │──│    Blackboard    │──│    Metrics     │ │
│  │  (phase router)  │  │ (PROJECT DOCUMENT)│  │  (collector)   │ │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬────────┘ │
│           │                     │                     │          │
│           ▼                     ▼                     ▼          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              STRATEGY PLUGINS (swappable)                 │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌───────┐  │   │
│  │  │  V0  │ │  V2  │ │  V3  │ │  V4  │ │  V5  │ │  V6   │  │   │
│  │  │ prev │ │ impr │ │ evol │ │ blck │ │ deep │ │ unify │  │   │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └───────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │                  EXPERT POOL                               │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │  │
│  │  │  Creative   │ │     CG      │ │   Critic    │          │  │
│  │  │   Expert    │ │   Expert    │ │   Expert    │          │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘          │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │  │
│  │  │ TD Designer │ │   GLSL      │ │   Python    │          │  │
│  │  │   Expert    │ │   Expert    │ │   Expert    │          │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │                 KNOWLEDGE BASE                             │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │  Expertise YAML Files (operators, patterns, GLSL)    │ │  │
│  │  │  Parsed JSON (686 operators, parameter schemas)      │ │  │
│  │  │  ChromaDB Embeddings (semantic search)               │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Specifications

### 1. Orchestrator

The orchestrator manages phase transitions and routes work to appropriate agents.

**Responsibilities:**
- Read blackboard state to determine what needs work
- Select and configure the active strategy
- Route to correct phase based on blackboard evaluation
- Handle user checkpoints (if involvement level requires)
- Classify issues and route to appropriate fixer

**State Machine:**
```
┌────────────┐     ┌────────────┐     ┌────────────┐
│ CREATIVE   │────▶│ TECHNICAL  │────▶│ RESOURCES  │
└────────────┘     └────────────┘     └────────────┘
                                             │
┌────────────┐     ┌────────────┐            ▼
│  COMPLETE  │◀────│   BUILD    │◀────┌────────────┐
└────────────┘     └────────────┘     │   DESIGN   │
                         ▲            └────────────┘
                         │                   │
                   (validation loop)─────────┘
```

**Phase Reopening:**
When the Design phase reveals issues with earlier phases:
- Creative issue → reopen §2, preserve §3-4
- Technical issue → reopen §3, preserve §2
- Update blackboard with reason for reopening

### 2. Blackboard (PROJECT DOCUMENT)

Central state storage that all agents read from and write to. See `BLACKBOARD_SCHEMA.md` for full specification.

**Key Properties:**
- Single source of truth
- Version history for each section
- Locking mechanism to prevent conflicting writes
- Blocking issues queue with classification

**Sections:**
| Section | Purpose | Written By |
|---------|---------|------------|
| §1 Requirements | User intent + constraints | Orchestrator, User |
| §2 Creative Vision | Artistic direction, mood, style | Creative Expert |
| §3 Technical Approach | Techniques, tradeoffs | CG Expert |
| §4 Available Resources | Operators, palette, patterns | KB Query |
| §5 Network Design | JSON network + descriptions | TD Designer |
| §6 Validation History | All critic reviews | Critic |
| §7 Build Artifacts | Paths, validation results | Builder |

### 3. Metrics Collector

Tracks all metrics for strategy comparison. See `METRICS_SPEC.md` for full specification.

**Metrics Categories:**
- **Cost**: Token counts (input/output/total), estimated USD
- **Quality**: Scores per phase (creative/technical/design)
- **Iterations**: Count per phase, total
- **Troubleshooting**: Build failures, validation errors, phase reopens

### 3a. Quality Thresholds

Quality thresholds define when a phase passes or requires revision. Thresholds are defined in `meta_agentic/expertise/critique_patterns.yaml#workflow_quality_thresholds`.

**Default Thresholds:**
| Phase | Threshold | Stretch Goal |
|-------|-----------|--------------|
| Creative | 0.85 | 0.95 |
| Technical | 0.85 | 0.95 |
| Design | 0.90 | 0.95 |

**Presets:**
| Preset | Creative | Technical | Design |
|--------|----------|-----------|--------|
| quick_draft | 0.70 | 0.70 | 0.80 |
| standard | 0.85 | 0.85 | 0.90 |
| excellence | 0.90 | 0.90 | 0.95 |

**Convergence Detection:**
- Window: 2 iterations
- Minimum improvement: 0.01
- If no improvement after N iterations, escalate or accept

**Multi-Perspective Review (Design Phase):**
- Aggregation: minimum score from all reviewers
- Reviewers: creative perspective, technical perspective, critic

See `critique_patterns.yaml` for full threshold definitions and scoring rubrics.

### 4. Strategy Plugins

Each strategy implements a common interface but varies in how it explores the solution space and refines outputs.

**Interface:**
```python
class WorkflowStrategy(Protocol):
    name: str  # "v0", "v2", "v3", etc.

    def execute(
        self,
        prompt: str,
        blackboard: Blackboard,
        config: StrategyConfig
    ) -> BuildResult

    def get_config_schema(self) -> dict
```

**Available Strategies:**

| Strategy | Pattern | When to Use |
|----------|---------|-------------|
| V0 | Baseline (current) | Control for comparison |
| V2 | KB-first + self-critique | Standard projects |
| V3 | Evolutionary (variants) | Quality-critical, creative |
| V4 | Blackboard-focused | Complex state management |
| V5 | Deep refinement | High quality bar |
| V6 | Unified (all combined) | Maximum quality, configurable |

### 5. Expert Pool

Pre-defined experts with specialized knowledge. See `AGENT_INTERFACE.md` for how experts are called.

**Expert Catalog:**

| Expert | Role | Reads | Writes |
|--------|------|-------|--------|
| creative_expert | Artistic vision | §1 | §2 |
| cg_expert | Technical approach | §1, §2 | §3 |
| critic | Quality validation | §1-5 | §6 |
| td_designer | Network design | §1-4 | §5 |
| td_glsl_expert | Shader code | §3, §5 | §5 (GLSL nodes) |
| td_python_expert | Python code | §3, §5 | §5 (Python nodes) |
| network_builder | JSON construction | §5 | §7 |

### 6. Knowledge Base

Existing expertise files that can be queried before generation.

**Sources:**
- `meta_agentic/expertise/*.yaml` - 12 expertise files
- `parsed_data.json` - 686 operators with parameters
- `operator_param_schemas.json` - Parameter specifications
- `chroma_db/` - Semantic embeddings for search

**Query Types:**
- Exact match: "What parameters does audioDeviceIn have?"
- Pattern match: "How do you create audio-reactive visuals?"
- Semantic: "What operators are good for particle effects?"

---

## Execution via Claude Code

This system is designed to run through Claude Code, not direct API calls.

### Conversation Flow

```
USER: Create an audio-reactive particle system

CLAUDE: [Orchestrator] Reading blackboard... §1 empty
        [Orchestrator] Writing §1 Requirements
        [Orchestrator] Strategy: V2, Phase: CREATIVE

        [KB Query] Querying for: audio reactive, particles
        [KB Result] Found: audioDeviceIn, audioSpect, particlesSOP...

        [Creative Expert] Reading §1, §4
        [Creative Expert] Generating creative vision...
        [Creative Expert] Self-critique: Is this remarkable?
        [Creative Expert] Writing §2 (v1, score: 0.78)

        [Critic] Reading §1, §2
        [Critic] Score: 0.78 - Below threshold (0.85)
        [Critic] Issues: "Brief is generic, needs signature element"
        [Critic] Writing §6

        [Orchestrator] Blocking issue in §2, routing to Creative

        [Creative Expert] Reading §6 feedback
        [Creative Expert] Refining vision...
        [Creative Expert] Writing §2 (v2, score: 0.87)

        [Critic] Score: 0.87 - Pass
        [Orchestrator] Advancing to TECHNICAL phase

        ... continues through phases ...
```

### Claude Code Integration Points

1. **Expert Prompts**: Load from `meta_agentic/experts/*/plan.md` etc.
2. **Expertise Queries**: Read from `meta_agentic/expertise/*.yaml`
3. **Validation**: Call `anti_hallucination.py`, `expertise_validator.py`
4. **Building**: Call `tox_builder/builder_v4.py`
5. **Metrics**: Write to `workflow_metrics.json`

---

## Directory Structure

```
C:\TD_Projects\META_AGENTIC_TOOL\
├── docs/
│   ├── ARCHITECTURE.md          # This file
│   ├── BLACKBOARD_SCHEMA.md     # PROJECT DOCUMENT spec
│   ├── AGENT_INTERFACE.md       # Expert calling protocol
│   ├── METRICS_SPEC.md          # Measurement methodology
│   ├── WORKFLOW_STRATEGIES.md   # Strategy comparison
│   └── strategies/
│       ├── V0_BASELINE.md
│       ├── V2_IMPROVED.md
│       ├── V3_EVOLUTIONARY.md
│       ├── V4_BLACKBOARD.md
│       ├── V5_DEEP_REFINEMENT.md
│       └── V6_UNIFIED.md
│
├── meta_agentic/
│   ├── execution/               # NEW: Execution layer
│   │   ├── orchestrator.py      # Phase management
│   │   ├── blackboard.py        # PROJECT DOCUMENT state
│   │   ├── strategy_runner.py   # Strategy execution
│   │   └── metrics.py           # Metrics collection
│   │
│   ├── experts/                 # EXISTING: Expert prompts
│   │   ├── creative_expert/
│   │   ├── cg_expert/
│   │   ├── td_designer/
│   │   └── ...
│   │
│   └── expertise/               # EXISTING: Knowledge base
│       ├── operators.yaml
│       ├── patterns.yaml
│       └── ...
│
└── tox_builder/                 # EXISTING: Build system
    └── builder_v4.py
```

---

## Implementation Order

1. **Documentation** (current phase)
   - ARCHITECTURE.md (this file)
   - BLACKBOARD_SCHEMA.md
   - AGENT_INTERFACE.md
   - METRICS_SPEC.md
   - Strategy specifications

2. **Core Engine**
   - blackboard.py (state management)
   - metrics.py (tracking)
   - orchestrator.py (phase routing)

3. **Strategy Implementations**
   - V0 (wrap current approach)
   - V2 (KB-first + self-critique)
   - V3 (evolutionary)
   - V4 (blackboard-focused)
   - V5 (deep refinement)
   - V6 (unified)

4. **Comparison Runner**
   - Run same prompt through each strategy
   - Collect metrics
   - Generate comparison report

---

## Success Criteria

A successfully generated TOE file should:
- [ ] Have GLSL uniforms that match control center parameters
- [ ] Have control center parameters that actually control shader behavior
- [ ] Use palette components where appropriate (not reinvent)
- [ ] Pass validation before build (operators exist, params valid)
- [ ] Include expert consultation traces in blackboard audit trail

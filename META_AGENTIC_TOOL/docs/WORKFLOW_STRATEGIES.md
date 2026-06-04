# Workflow Strategies Overview

## Overview

This document provides a high-level comparison of all workflow strategies. For detailed specifications of each strategy, see the individual strategy documents in `docs/strategies/`.

---

## Strategy Summary

| Strategy | Pattern | Best For | Token Cost | Quality | Speed |
|----------|---------|----------|------------|---------|-------|
| **V0** | Baseline (current) | Control comparison | Low | Low | Fast |
| **V2** | KB-first + self-critique | Standard projects | Medium | Medium | Medium |
| **V3** | Evolutionary variants | Creative exploration | High | High | Slow |
| **V4** | Blackboard-focused | Complex state | Medium | Medium | Medium |
| **V5** | Deep refinement | Quality-critical | Medium-High | High | Medium |
| **V6** | Unified (all combined) | Maximum quality | High | Highest | Variable |

---

## Strategy Comparison

### Quick Reference

```
                      SPEED
                        ▲
                        │
              V0 ●      │
                        │
           V2 ●    V4 ● │
                        │
              V5 ●      │
                        │
         V3 ●      V6 ● │
                        │
    ────────────────────┼────────────────────▶ QUALITY
                        │
```

### Decision Tree

```
┌─────────────────────────────────────────────────────────────────┐
│                    STRATEGY SELECTION                            │
│                                                                  │
│  Is this a quick draft or test?                                 │
│  │                                                              │
│  YES ──▶ V2 (KB-first, minimal iterations)                      │
│  │                                                              │
│  NO                                                             │
│  │                                                              │
│  ▼                                                              │
│  Does creativity matter more than speed?                        │
│  │                                                              │
│  YES ──▶ V3 (Evolutionary - explore design space)               │
│  │                                                              │
│  NO                                                             │
│  │                                                              │
│  ▼                                                              │
│  Is the project complex with many interdependencies?            │
│  │                                                              │
│  YES ──▶ V4 (Blackboard - explicit state management)            │
│  │                                                              │
│  NO                                                             │
│  │                                                              │
│  ▼                                                              │
│  Is quality the primary concern (willing to spend tokens)?      │
│  │                                                              │
│  YES ──▶ V5 (Deep refinement) or V6 (Unified - highest quality) │
│  │                                                              │
│  NO ──▶ V2 (Standard balanced approach)                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## V0: Baseline (Current Approach)

**Pattern**: Single-pass generation without validation loops

**What It Does**:
- One-shot prompt to generate network
- No KB query before generation
- No quality validation
- No self-critique

**When to Use**:
- Control comparison only
- Not recommended for production

**Typical Results**:
- Quality: 0.4-0.6
- Tokens: ~12k
- Iterations: 1
- Build Success: ~50%

**Known Issues**:
- Missing GLSL uniforms
- Parameters don't control anything
- No palette usage
- Generic implementations

---

## V2: Improved Current

**Pattern**: Linear phases with KB-first and self-critique loops

```
┌─────────────────────────────────────────────────────────────────┐
│                         V2 FLOW                                  │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ KB Query │ ──▶│ Creative │ ──▶│  Critic  │ ──▶│    CG    │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│                        │              │                │        │
│                        └──── loop ◀───┘                │        │
│                                                        │        │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐         ▼        │
│  │  Build   │ ◀──│  Design  │ ◀──│ Resource │ ◀────────         │
│  └──────────┘    └──────────┘    └──────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

**Key Features**:
- KB query BEFORE expert work
- Self-critique loops ("Is this remarkable?")
- User involvement levels (full/milestone/minimal)
- Dual descriptions (visual for Creative, technical for CG)

**When to Use**:
- Standard projects
- Quick turnaround needed
- Budget-conscious

**Typical Results**:
- Quality: 0.75-0.85
- Tokens: ~28k
- Iterations: 2-4
- Build Success: ~95%

---

## V3: Evolutionary

**Pattern**: Spawn N variants per phase, tournament ranking, breeding

```
┌─────────────────────────────────────────────────────────────────┐
│                         V3 FLOW                                  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    CREATIVE PHASE                         │   │
│  │  ┌─────┐   ┌─────┐   ┌─────┐                             │   │
│  │  │  A  │   │  B  │   │  C  │   ← Variants                │   │
│  │  └──┬──┘   └──┬──┘   └──┬──┘                             │   │
│  │     │         │         │                                 │   │
│  │     └────────┬┴─────────┘                                 │   │
│  │              ▼                                            │   │
│  │         ┌─────────┐                                       │   │
│  │         │  RANK   │   ← Tournament                        │   │
│  │         └────┬────┘                                       │   │
│  │              │                                            │   │
│  │         ┌────▼────┐                                       │   │
│  │         │  BREED  │   ← Combine best aspects              │   │
│  │         └─────────┘                                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│              (repeat for each phase)                             │
└─────────────────────────────────────────────────────────────────┘
```

**Key Features**:
- Spawns 3-5 variants per phase
- Tournament ranking (score 0-1 each)
- Breeding combines best aspects
- Avoids local minima

**When to Use**:
- Creativity is paramount
- Multiple valid approaches possible
- Time/budget available for exploration

**Typical Results**:
- Quality: 0.80-0.90
- Tokens: ~45k
- Iterations: 5-8
- Build Success: ~95%

**Trade-offs**:
- 3-5x more expensive than V2
- Takes longer
- Overkill for simple tasks

---

## V4: Blackboard

**Pattern**: Central PROJECT DOCUMENT as shared state

```
┌─────────────────────────────────────────────────────────────────┐
│                         V4 FLOW                                  │
│                                                                  │
│                  ┌──────────────────────┐                       │
│                  │    BLACKBOARD        │                       │
│                  │    §1 Requirements   │                       │
│                  │    §2 Creative       │                       │
│                  │    §3 Technical      │                       │
│                  │    §4 Resources      │                       │
│                  │    §5 Design         │                       │
│                  │    §6 Validation     │                       │
│                  │    §7 Artifacts      │                       │
│                  └──────────┬───────────┘                       │
│                             │                                    │
│         ┌───────────────────┼───────────────────┐               │
│         │                   │                   │               │
│         ▼                   ▼                   ▼               │
│   ┌──────────┐       ┌──────────┐       ┌──────────┐           │
│   │ Creative │       │    CG    │       │ Designer │           │
│   │  Expert  │       │  Expert  │       │  Expert  │           │
│   └────┬─────┘       └────┬─────┘       └────┬─────┘           │
│        │                  │                  │                  │
│        └──────────────────┴──────────────────┘                  │
│                           │                                      │
│                    (all read/write                               │
│                     to blackboard)                               │
└─────────────────────────────────────────────────────────────────┘
```

**Key Features**:
- Single source of truth
- Full audit trail
- Partial re-work (fix §3 without redoing §2)
- Orchestrator decides "what needs work" dynamically

**When to Use**:
- Complex projects with many interdependencies
- Need for audit trail
- Multiple experts need to coordinate

**Typical Results**:
- Quality: 0.78-0.85
- Tokens: ~32k
- Iterations: 3-5
- Build Success: ~95%

---

## V5: Deep Refinement

**Pattern**: High quality thresholds + stretch goals + convergence detection

```
┌─────────────────────────────────────────────────────────────────┐
│                         V5 FLOW                                  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    REFINEMENT LOOP                        │   │
│  │                                                           │   │
│  │    ┌────────┐                                            │   │
│  │    │ Expert │                                            │   │
│  │    │ Output │                                            │   │
│  │    └───┬────┘                                            │   │
│  │        │                                                  │   │
│  │        ▼                                                  │   │
│  │  ┌───────────┐     ┌───────────┐                         │   │
│  │  │  Score    │────▶│ >= 0.85?  │                         │   │
│  │  └───────────┘     └─────┬─────┘                         │   │
│  │                          │                                │   │
│  │                    NO ───┼─── YES                         │   │
│  │                    │     │     │                          │   │
│  │                    ▼     │     ▼                          │   │
│  │              ┌─────────┐ │ ┌───────────┐                  │   │
│  │              │ Iterate │ │ │ >= 0.95?  │ ← Stretch goal   │   │
│  │              └────┬────┘ │ └─────┬─────┘                  │   │
│  │                   │      │       │                        │   │
│  │                   │      │  NO ──┼── YES                  │   │
│  │                   │      │  │    │    │                   │   │
│  │                   │      │  ▼    │    ▼                   │   │
│  │                   │      │ Try   │  DONE                  │   │
│  │                   └──────┴──┬────┘                        │   │
│  │                             │                             │   │
│  │                      ┌──────▼──────┐                      │   │
│  │                      │ Converged?  │                      │   │
│  │                      └──────┬──────┘                      │   │
│  │                             │                             │   │
│  │                       YES ──┴── NO (loop)                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Key Features**:
- Explicit quality targets (0.85/0.85/0.90)
- Stretch goals ("could we hit 0.95?")
- Convergence detection (stop if no improvement in N iterations)
- Phase reopening when design reveals earlier issues

**When to Use**:
- Quality is primary concern
- Willing to invest tokens for polish
- Need consistent quality bar

**Typical Results**:
- Quality: 0.85-0.92
- Tokens: ~39k
- Iterations: 4-6
- Build Success: ~98%

---

## V6: Unified

**Pattern**: Combines all approaches with configurable presets

```
┌─────────────────────────────────────────────────────────────────┐
│                         V6 UNIFIED                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ CONFIG: involvement | exploration | quality_targets       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │          BLACKBOARD (V4) as Foundation                    │  │
│  │               PROJECT DOCUMENT                             │  │
│  └───────────────────────────┼───────────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │       ORCHESTRATOR (V2) Coordination                      │  │
│  │  • KB-first                                               │  │
│  │  • Dynamic routing                                        │  │
│  │  • User checkpoints                                       │  │
│  └───────────────────────────┼───────────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │     WITHIN EACH PHASE:                                    │  │
│  │                                                           │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │     EVOLUTIONARY (V3) - if exploration > 1         │  │  │
│  │  │  • Spawn N variants                                │  │  │
│  │  │  • Tournament rank                                 │  │  │
│  │  │  • Breed best                                      │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                              │                            │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │     DEEP REFINEMENT (V5) - Quality Control         │  │  │
│  │  │  • Quality thresholds                              │  │  │
│  │  │  • Stretch goals                                   │  │  │
│  │  │  • Convergence detection                           │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Presets**:

| Preset | Involvement | Exploration | Quality Targets | Max Iterations |
|--------|-------------|-------------|-----------------|----------------|
| Quick Draft | minimal | 1 | 0.7/0.7/0.8 | 5 |
| Standard | milestone | 3 | 0.85/0.85/0.9 | 10 |
| Excellence | full | 5 | 0.9/0.9/0.95 | 20 |

**When to Use**:
- Maximum quality needed
- Have time and token budget
- Complex, quality-critical projects

**Typical Results**:
- Quality: 0.88-0.95
- Tokens: ~52k
- Iterations: 5-8
- Build Success: ~99%

---

## Configuration Reference

### User Involvement Levels

| Level | Description | User Interaction |
|-------|-------------|------------------|
| **full** | Maximum collaboration | Review after every phase |
| **milestone** | Key checkpoints only | Review after creative, design, build |
| **minimal** | Autonomous execution | Only at errors or completion |

### Exploration Settings

| Value | Behavior |
|-------|----------|
| **1** | Single path (no variants) |
| **3** | Three variants per phase (default) |
| **5** | Five variants per phase (maximum creativity) |

### Quality Targets

| Target | Default | Range |
|--------|---------|-------|
| creative | 0.85 | 0.7 - 0.95 |
| technical | 0.85 | 0.7 - 0.95 |
| design | 0.90 | 0.8 - 0.95 |
| stretch_threshold | 0.95 | (above targets) |

---

## Detailed Strategy Documents

For full specifications, see:
- `docs/strategies/V0_BASELINE.md`
- `docs/strategies/V2_IMPROVED.md`
- `docs/strategies/V3_EVOLUTIONARY.md`
- `docs/strategies/V4_BLACKBOARD.md`
- `docs/strategies/V5_DEEP_REFINEMENT.md`
- `docs/strategies/V6_UNIFIED.md`

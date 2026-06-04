# Strategy V6: Unified

## Overview

V6 combines all approaches into a single, **configurable architecture**:
- **Blackboard (V4)** as the foundation for state management
- **Orchestrator (V2)** for coordination and KB-first approach
- **Evolutionary (V3)** within phases (optional, configurable)
- **Deep Refinement (V5)** for quality control

This is the **ultimate target architecture** offering maximum quality with configurable complexity via presets.

## When to Use

- Maximum quality is required
- Time and token budget available
- Complex, quality-critical projects
- Want configurable complexity (presets)

**Presets for different needs**:
| Preset | Use Case | Quality | Tokens |
|--------|----------|---------|--------|
| Quick Draft | Fast turnaround | ~0.75 | ~20k |
| Standard | Balanced | ~0.85 | ~35k |
| Excellence | Maximum quality | ~0.92 | ~52k |

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      V6: UNIFIED                                 │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    CONFIGURATION                          │   │
│  │                                                           │   │
│  │   Preset: quick_draft | standard | excellence            │   │
│  │                                                           │   │
│  │   ┌─────────────────────────────────────────────────┐    │   │
│  │   │ involvement: minimal | milestone | full         │    │   │
│  │   │ exploration: 1 | 3 | 5 (variants per phase)     │    │   │
│  │   │ quality_targets:                                │    │   │
│  │   │   creative: 0.7 | 0.85 | 0.90                   │    │   │
│  │   │   technical: 0.7 | 0.85 | 0.90                  │    │   │
│  │   │   design: 0.8 | 0.90 | 0.95                     │    │   │
│  │   │ stretch_threshold: 0.95                         │    │   │
│  │   │ max_iterations: 5 | 10 | 20                     │    │   │
│  │   │ convergence_window: 2                           │    │   │
│  │   └─────────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │         BLACKBOARD (V4) - Foundation                      │  │
│  │                                                           │  │
│  │   PROJECT DOCUMENT                                        │  │
│  │   ┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐            │  │
│  │   │ §1 ││ §2 ││ §3 ││ §4 ││ §5 ││ §6 ││ §7 │            │  │
│  │   └────┘└────┘└────┘└────┘└────┘└────┘└────┘            │  │
│  │   + version history + locking + blocking issues          │  │
│  └───────────────────────────┼───────────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │         ORCHESTRATOR (V2) - Coordination                  │  │
│  │                                                           │  │
│  │   • KB-first (query before generation)                   │  │
│  │   • Dynamic routing (based on blackboard state)          │  │
│  │   • User checkpoints (based on involvement level)        │  │
│  │   • Error classification → appropriate fixer             │  │
│  └───────────────────────────┼───────────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────┼───────────────────────────────┐  │
│  │                    PHASE EXECUTION                        │  │
│  │                                                           │  │
│  │   ┌─────────────────────────────────────────────────┐    │  │
│  │   │  if exploration > 1:                            │    │  │
│  │   │                                                 │    │  │
│  │   │    EVOLUTIONARY (V3)                            │    │  │
│  │   │    ┌───────┐ ┌───────┐ ┌───────┐               │    │  │
│  │   │    │ Var A │ │ Var B │ │ Var C │               │    │  │
│  │   │    └───┬───┘ └───┬───┘ └───┬───┘               │    │  │
│  │   │        └─────────┼─────────┘                    │    │  │
│  │   │                  ▼                              │    │  │
│  │   │           ┌──────────┐                          │    │  │
│  │   │           │  RANK    │                          │    │  │
│  │   │           └────┬─────┘                          │    │  │
│  │   │                ▼                                │    │  │
│  │   │           ┌──────────┐                          │    │  │
│  │   │           │  BREED?  │                          │    │  │
│  │   │           └────┬─────┘                          │    │  │
│  │   │                │                                │    │  │
│  │   └────────────────┼────────────────────────────────┘    │  │
│  │                    │                                      │  │
│  │   ┌────────────────▼────────────────────────────────┐    │  │
│  │   │                                                 │    │  │
│  │   │    DEEP REFINEMENT (V5)                         │    │  │
│  │   │                                                 │    │  │
│  │   │    ┌──────────────┐                             │    │  │
│  │   │    │ Quality Gate │                             │    │  │
│  │   │    │ (score >= ?) │                             │    │  │
│  │   │    └──────┬───────┘                             │    │  │
│  │   │           │                                     │    │  │
│  │   │    ┌──────┴───────┐                             │    │  │
│  │   │    │ Stretch Goal │                             │    │  │
│  │   │    │ (score < 95?)│                             │    │  │
│  │   │    └──────┬───────┘                             │    │  │
│  │   │           │                                     │    │  │
│  │   │    ┌──────┴───────┐                             │    │  │
│  │   │    │ Convergence  │                             │    │  │
│  │   │    │ Detection    │                             │    │  │
│  │   │    └──────────────┘                             │    │  │
│  │   │                                                 │    │  │
│  │   └─────────────────────────────────────────────────┘    │  │
│  │                                                           │  │
│  │   Phase Reopening: If design reveals creative/technical  │  │
│  │   issue, reopen earlier phase with feedback               │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   CRITIC SYSTEM                           │   │
│  │                                                           │   │
│  │   Persistent context across ALL phases:                  │   │
│  │   • Project understanding                                │   │
│  │   • Validation history                                   │   │
│  │   • Learned preferences                                  │   │
│  │   • Current concerns                                     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Presets

### Quick Draft

For fast turnaround, simple requests:

```yaml
quick_draft:
  involvement: minimal
  exploration: 1        # No variants
  quality_targets:
    creative: 0.70
    technical: 0.70
    design: 0.80
  stretch_threshold: null  # No stretch
  max_iterations: 5
  convergence_window: 2
```

**Typical Results**:
- Quality: ~0.75
- Tokens: ~20k
- Time: Fast
- Build Success: ~90%

### Standard

Balanced quality and speed:

```yaml
standard:
  involvement: milestone
  exploration: 3        # 3 variants per phase
  quality_targets:
    creative: 0.85
    technical: 0.85
    design: 0.90
  stretch_threshold: 0.95
  max_iterations: 10
  convergence_window: 2
```

**Typical Results**:
- Quality: ~0.85
- Tokens: ~35k
- Time: Moderate
- Build Success: ~95%

### Excellence

Maximum quality, time available:

```yaml
excellence:
  involvement: full
  exploration: 5        # 5 variants per phase
  quality_targets:
    creative: 0.90
    technical: 0.90
    design: 0.95
  stretch_threshold: 0.98
  max_iterations: 20
  convergence_window: 3
```

**Typical Results**:
- Quality: ~0.92
- Tokens: ~52k
- Time: Comprehensive
- Build Success: ~99%

## Phase Details

### Phase Flow (Standard Preset)

```
1. INITIALIZATION
   │
   ├─ Parse user prompt
   ├─ Select preset (or custom config)
   ├─ Initialize blackboard (§1 requirements)
   │
   ▼
2. CREATIVE PHASE
   │
   ├─ KB Query (creative_vision.yaml, patterns.yaml)
   │
   ├─ if exploration == 3:
   │   ├─ Generate Variant A (bold)
   │   ├─ Generate Variant B (refined)
   │   ├─ Generate Variant C (unexpected)
   │   ├─ Rank variants
   │   └─ Breed if top 2 close
   │
   ├─ Deep refinement loop:
   │   ├─ Critic validates
   │   ├─ Score >= 0.85? → proceed (check stretch)
   │   └─ Score < 0.85? → iterate with feedback
   │
   ├─ Write §2 (version history)
   ├─ Lock §2 on approval
   │
   ├─ User checkpoint (if milestone involvement)
   │
   ▼
3. TECHNICAL PHASE
   │
   ├─ KB Query (operators.yaml, patterns.yaml)
   │
   ├─ [Same evolutionary + refinement pattern]
   │
   ├─ Write §3
   ├─ Lock §3 on approval
   │
   ▼
4. RESOURCES PHASE
   │
   ├─ KB Query (comprehensive):
   │   ├─ All relevant operators
   │   ├─ Palette components
   │   ├─ Example patterns
   │   └─ GLSL templates
   │
   ├─ Write §4
   │
   ▼
5. DESIGN PHASE
   │
   ├─ Read §1-4
   │
   ├─ if exploration == 3:
   │   ├─ Generate Design A (modular)
   │   ├─ Generate Design B (optimized)
   │   ├─ Generate Design C (extensible)
   │   ├─ Consult domain experts (GLSL, Python)
   │   ├─ Rank designs
   │   └─ Breed if top 2 close
   │
   ├─ Deep refinement loop:
   │   ├─ Multi-perspective review (Creative, CG, Critic)
   │   ├─ Aggregate score = min(all)
   │   ├─ Score >= 0.90? → proceed
   │   └─ Score < 0.90? → iterate or reopen earlier phase
   │
   ├─ Write §5 (with dual descriptions)
   ├─ Lock §5 on approval
   │
   ├─ User checkpoint (if milestone involvement)
   │
   ▼
6. BUILD PHASE
   │
   ├─ Validate JSON structure
   ├─ Validate operators exist
   ├─ Build TOE file
   ├─ Verify output
   │
   ├─ Write §7
   │
   ├─ User checkpoint (final delivery)
   │
   ▼
7. DELIVERY
   │
   ├─ Generate summary
   ├─ Report quality scores
   ├─ Collect user feedback
   │
   └─ if feedback → route to appropriate phase
```

## Configuration Options

```yaml
v6_config:
  # Preset (or use custom values below)
  preset: quick_draft | standard | excellence | custom

  # User involvement
  involvement: full | milestone | minimal
  # full: Review after every phase
  # milestone: Review after creative, design, build
  # minimal: Only at errors or completion

  # Exploration breadth (from V3)
  exploration: 1 | 3 | 5
  # 1: Single path (no variants)
  # 3: Three variants per phase
  # 5: Five variants per phase

  # Quality targets (from V5)
  quality_targets:
    creative: 0.70 - 0.95
    technical: 0.70 - 0.95
    design: 0.80 - 0.98

  stretch:
    threshold: 0.95 - 0.98
    enabled: true | false

  # Iteration limits (from V5)
  max_iterations: 5 | 10 | 20 | unlimited
  convergence_window: 2 | 3

  # Blackboard (from V4)
  blackboard:
    version_history: true
    section_locking: true
    audit_trail: true

  # Evolutionary (from V3)
  evolutionary:
    breeding_threshold: 0.05
    variant_directives:
      creative: ["bold", "refined", "unexpected", ...]
      technical: ["performance", "quality", "flexibility", ...]
      design: ["modular", "optimized", "extensible", ...]

  # Critic (V6 unique)
  critic:
    persistent_context: true
    multi_perspective:
      enabled: true
      for_phases: ["design"]
```

## Expected Metrics

### By Preset

| Metric | Quick Draft | Standard | Excellence |
|--------|-------------|----------|------------|
| Tokens | ~20k | ~35k | ~52k |
| Quality | ~0.75 | ~0.85 | ~0.92 |
| Iterations | 3-5 | 8-12 | 12-18 |
| Time | Fast | Moderate | Comprehensive |
| Build Success | ~90% | ~95% | ~99% |

### Detailed (Standard Preset)

```yaml
typical_metrics:
  tokens:
    input: ~25000
    output: ~10000
    total: ~35000

  by_phase:
    creative:
      variants: 3
      iterations: 2-3
      tokens: ~10000
    technical:
      variants: 3
      iterations: 1-2
      tokens: ~7000
    design:
      variants: 3
      iterations: 3-4
      tokens: ~12000
    build:
      iterations: 1
      tokens: ~3000

  quality:
    creative: 0.85-0.90
    technical: 0.83-0.88
    design: 0.88-0.93
    final: 0.83-0.88

  iterations:
    evolutionary_generations: 3
    refinement_loops: 5-8
    breeding_events: 1-2
    total: 10-15

  artifacts:
    uniforms_connected: ~95%
    parameters_functional: ~90%
    palette_used: ~80%
```

## Implementation Notes

### Strategy Composition

V6 composes the other strategies:

```python
class V6UnifiedStrategy:
    def __init__(self, config: V6Config):
        self.config = config
        self.blackboard = Blackboard()  # V4
        self.orchestrator = Orchestrator(config.involvement)  # V2
        self.evolutionary = Evolutionary(config.exploration) if config.exploration > 1 else None  # V3
        self.refinement = DeepRefinement(config.quality_targets)  # V5

    def execute_phase(self, phase: str) -> PhaseResult:
        # 1. KB-first (V2)
        kb_results = self.query_kb_for_phase(phase)

        # 2. Evolutionary (V3) - if enabled
        if self.evolutionary:
            variants = self.evolutionary.generate_variants(phase, kb_results)
            winner = self.evolutionary.tournament(variants)
            output = self.evolutionary.breed_if_needed(winner)
        else:
            output = self.generate_single(phase, kb_results)

        # 3. Deep refinement (V5)
        refined = self.refinement.refine_until_quality(output, phase)

        # 4. Write to blackboard (V4)
        self.blackboard.write_section(phase, refined)

        return refined
```

### Critic Persistent Context

V6's critic maintains context across all phases:

```yaml
critic_context:
  project_understanding:
    requirements_summary: "Audio-reactive particle system for live performance"
    creative_intent: "Ethereal, breathing, organic"
    technical_constraints: "60fps, laptop GPU"

  validation_history:
    - phase: creative
      v1: {score: 0.78, passed: false, feedback: "Lacks signature"}
      v2: {score: 0.87, passed: true}
    - phase: technical
      v1: {score: 0.85, passed: true}
    - phase: design
      v1: {score: 0.82, passed: false}
      v2: {score: 0.88, passed: false}
      v3: {score: 0.91, passed: true}

  learned_preferences:
    - "User values interactivity over pure aesthetics"
    - "Performance is critical for live performance context"
    - "Organic motion preferred over mechanical"

  current_concerns:
    - "Design v2 improved structure but may have lost creative energy"
```

### Inter-Agent Communication

V6 uses a structured message schema:

```yaml
message:
  id: uuid
  timestamp: iso8601

  routing:
    from: agent_id
    to: agent_id | orchestrator | blackboard
    reply_to: message_id | null

  type: proposal | critique | question | answer | approval | rejection | revision | signal

  context:
    phase: creative | technical | resources | design | build
    iteration: n
    variant: A | B | C | null

  content:
    summary: "Brief description"
    detail: "Full content"
    score: 0.0 - 1.0
    pass: true | false
    issues: [...]
    improvements: [...]
```

## Success Criteria

A V6 run is successful when:

- [ ] All blackboard sections §1-§7 populated
- [ ] All sections locked after approval
- [ ] Quality targets met for all phases
- [ ] Stretch goals attempted (if configured)
- [ ] Convergence properly detected
- [ ] Evolutionary exploration meaningful (if configured)
- [ ] Breeding improved output (when triggered)
- [ ] Critic maintained consistent context
- [ ] Phase reopening worked correctly (if needed)
- [ ] Build produces valid TOE
- [ ] All artifact checks pass (uniforms, params, palette)
- [ ] Full audit trail preserved

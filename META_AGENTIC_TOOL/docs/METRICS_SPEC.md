# Metrics Specification

## Overview

This document defines the metrics collected during workflow execution for comparing strategies (V0, V2, V3, V4, V5, V6). Metrics enable data-driven decisions about which strategy to use for different project types.

---

## Metrics Categories

### 1. Cost Metrics

Token usage and estimated costs.

```yaml
cost_metrics:
  tokens:
    input: 32100
    output: 13130
    total: 45230

  # Token breakdown by phase
  by_phase:
    creative:
      input: 8200
      output: 3100
    technical:
      input: 6500
      output: 2800
    resources:
      input: 2000
      output: 1200
    design:
      input: 12400
      output: 4500
    build:
      input: 3000
      output: 1530

  # Token breakdown by agent
  by_agent:
    creative_expert:
      calls: 2
      input: 8200
      output: 3100
    cg_expert:
      calls: 1
      input: 6500
      output: 2800
    critic:
      calls: 4
      input: 5000
      output: 1800
    td_designer:
      calls: 3
      input: 12400
      output: 4500
    # ...

  estimated_cost_usd: 0.42
```

**Cost Calculation**:
```python
# Based on Claude API pricing (as of 2025)
cost_usd = (input_tokens * INPUT_RATE + output_tokens * OUTPUT_RATE) / 1000
```

### 2. Quality Metrics

Scores from validation at each phase.

```yaml
quality_metrics:
  scores:
    creative: 0.87
    technical: 0.82
    design: 0.91

  final_score: 0.82  # min(creative, technical, design)

  # Score progression over iterations
  progression:
    creative:
      - iteration: 1
        score: 0.72
        passed: false
      - iteration: 2
        score: 0.87
        passed: true

    technical:
      - iteration: 1
        score: 0.82
        passed: true

    design:
      - iteration: 1
        score: 0.78
        passed: false
      - iteration: 2
        score: 0.84
        passed: false
      - iteration: 3
        score: 0.91
        passed: true

  # Quality targets used
  targets:
    creative: 0.85
    technical: 0.85
    design: 0.90
    stretch_threshold: 0.95
```

### 3. Iteration Metrics

How many cycles through each phase.

```yaml
iteration_metrics:
  by_phase:
    creative: 2
    technical: 1
    design: 3
    build: 1

  total_iterations: 7

  convergence:
    converged: true
    iterations_without_improvement: 0
    convergence_window: 2

  # If evolutionary strategy
  variants:
    creative:
      count: 3
      winner: "B"
      breeding_performed: true
    technical:
      count: 3
      winner: "A"
      breeding_performed: false
```

### 4. Troubleshooting Metrics

Issues encountered and how they were resolved.

```yaml
troubleshooting_metrics:
  build_failures:
    count: 1
    details:
      - timestamp: "..."
        error_type: "json_validation"
        description: "Missing operator parameter"
        resolution: "Added default value"
        resolution_time_ms: 45000

  validation_errors:
    count: 3
    details:
      - phase: "creative"
        iteration: 1
        issues:
          - classification: "creative"
            severity: "blocking"
            description: "Lacks signature element"

  phase_reopens:
    count: 0
    details: []

  expert_consultations:
    count: 2
    details:
      - expert: "td_glsl_expert"
        question: "How to pass audio to compute shader?"
        resolution_helpful: true

  manual_interventions:
    count: 0
    details: []
```

### 5. Artifact Metrics

Quality of the final output.

```yaml
artifact_metrics:
  validation:
    toe_valid: true
    json_valid: true
    operators_exist: true
    connections_valid: true
    parameters_valid: true

  functional_checks:
    uniforms_connected: true
    parameters_functional: true
    palette_used: true
    glsl_compiles: true

  structure:
    container_count: 5
    operator_count: 32
    connection_count: 45
    custom_parameter_count: 12

  complexity:
    depth: 3
    max_children: 8
    glsl_node_count: 2
    python_node_count: 1
```

### 6. Timing Metrics

How long each phase took (wall clock time).

```yaml
timing_metrics:
  total_duration_ms: 180000  # 3 minutes

  by_phase:
    creative:
      duration_ms: 35000
      iterations: 2
    technical:
      duration_ms: 28000
      iterations: 1
    resources:
      duration_ms: 12000
      iterations: 1
    design:
      duration_ms: 85000
      iterations: 3
    build:
      duration_ms: 20000
      iterations: 1

  by_step:
    plan_total_ms: 45000
    build_total_ms: 95000
    self_improve_total_ms: 40000

  waiting_for_user_ms: 0  # if user checkpoints
```

---

## Collection Points

### When to Collect

| Event | Metrics Updated |
|-------|-----------------|
| Agent call start | timing.start, cost.by_agent.calls++ |
| Agent call end | timing.end, cost.by_agent.tokens |
| Validation complete | quality.scores, iteration.by_phase |
| Build failure | troubleshooting.build_failures |
| Phase reopen | troubleshooting.phase_reopens |
| Expert consultation | troubleshooting.expert_consultations |
| Build complete | artifact.validation, artifact.structure |

### Metrics Collector Interface

```python
class MetricsCollector:
    def __init__(self, strategy: str, project: str):
        self.metrics = RunMetrics(
            strategy=strategy,
            project=project,
            timestamp=datetime.now()
        )

    def on_agent_call_start(self, agent: str, phase: str):
        """Called when an agent invocation begins."""
        pass

    def on_agent_call_end(self, agent: str, input_tokens: int, output_tokens: int):
        """Called when an agent invocation completes."""
        pass

    def on_validation(self, phase: str, iteration: int, score: float, passed: bool):
        """Called when critic validates a section."""
        pass

    def on_build_failure(self, error_type: str, description: str):
        """Called when build fails."""
        pass

    def on_phase_reopen(self, from_phase: str, to_phase: str, reason: str):
        """Called when a phase is reopened."""
        pass

    def on_expert_consultation(self, expert: str, question: str):
        """Called when designer consults a domain expert."""
        pass

    def finalize(self) -> RunMetrics:
        """Called at end of run to compute derived metrics."""
        pass
```

---

## Storage Format

### Run Metrics File

Each run produces a metrics file:

```
meta_agentic/execution/metrics/
├── 2025-12-18_v3_audio_reactive.yaml
├── 2025-12-18_v5_audio_reactive.yaml
└── 2025-12-18_v6_audio_reactive.yaml
```

### Full Metrics Schema

```yaml
run_metrics:
  # Identification
  id: "uuid"
  strategy: "v3"
  project: "audio_reactive"
  timestamp: "2025-12-18T15:30:00Z"

  # User request
  prompt: "Create an audio-reactive particle system"

  # Configuration used
  config:
    involvement: "milestone"
    exploration: 3
    quality_targets:
      creative: 0.85
      technical: 0.85
      design: 0.90
    max_iterations: 10
    convergence_window: 2

  # All metrics categories
  cost: {...}
  quality: {...}
  iterations: {...}
  troubleshooting: {...}
  artifacts: {...}
  timing: {...}
```

---

## Comparison Methodology

### Strategy Comparison Report

After running the same prompt through multiple strategies:

```yaml
comparison:
  prompt: "Create an audio-reactive particle system"
  timestamp: "2025-12-18T16:00:00Z"

  strategies_tested:
    - v0
    - v2
    - v3
    - v5
    - v6

  summary_table:
    - strategy: "v0"
      tokens: 12430
      quality: 0.45
      iterations: 1
      build_success: false
      notes: "Missing uniforms, no validation"

    - strategy: "v2"
      tokens: 28100
      quality: 0.78
      iterations: 3
      build_success: true
      notes: "KB-first helped operator selection"

    - strategy: "v3"
      tokens: 45230
      quality: 0.82
      iterations: 7
      build_success: true
      notes: "Evolutionary found better creative direction"

    - strategy: "v5"
      tokens: 38900
      quality: 0.88
      iterations: 5
      build_success: true
      notes: "Deep refinement improved design quality"

    - strategy: "v6"
      tokens: 52100
      quality: 0.92
      iterations: 6
      build_success: true
      notes: "Best quality, most comprehensive"

  rankings:
    by_quality:
      1: v6
      2: v5
      3: v3
      4: v2
      5: v0

    by_efficiency:  # quality / tokens
      1: v5
      2: v6
      3: v3
      4: v2
      5: v0

    by_speed:  # 1 / iterations
      1: v0
      2: v2
      3: v5
      4: v6
      5: v3

  recommendations:
    quick_draft: "v2 - good balance of speed and quality"
    standard: "v5 - best efficiency (quality/tokens)"
    excellence: "v6 - highest quality, most thorough"
```

### Comparison Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│  Strategy Comparison: audio_reactive_test                       │
├──────────┬────────┬─────────┬───────────┬──────────┬───────────┤
│ Strategy │ Tokens │ Quality │ Iterations│ Build OK │ Efficiency│
├──────────┼────────┼─────────┼───────────┼──────────┼───────────┤
│ V0 (old) │ 12,430 │  0.45   │     1     │    ❌    │   0.36    │
│ V2       │ 28,100 │  0.78   │     3     │    ✅    │   0.28    │
│ V3       │ 45,230 │  0.82   │     7     │    ✅    │   0.18    │
│ V5       │ 38,900 │  0.88   │     5     │    ✅    │   0.23    │
│ V6       │ 52,100 │  0.92   │     6     │    ✅    │   0.18    │
└──────────┴────────┴─────────┴───────────┴──────────┴───────────┘

Efficiency = quality_score * 10 / (tokens / 10000)

📊 Visual Comparison:

Quality:    V0 [████░░░░░░] 0.45
            V2 [███████░░░] 0.78
            V3 [████████░░] 0.82
            V5 [████████░░] 0.88
            V6 [█████████░] 0.92

Tokens:     V0 [██░░░░░░░░] 12k
            V2 [█████░░░░░] 28k
            V3 [████████░░] 45k
            V5 [███████░░░] 39k
            V6 [██████████] 52k
```

---

## Quality Scoring Rubrics

### Creative Score (0-1)

| Score | Criteria |
|-------|----------|
| 0.9-1.0 | Remarkable, distinctive, memorable vision with signature element |
| 0.8-0.9 | Strong vision, clear mood/aesthetic, good color/motion specs |
| 0.7-0.8 | Adequate vision, meets requirements, lacks distinction |
| 0.6-0.7 | Generic, misses user intent in places, incomplete specs |
| <0.6 | Fundamentally misunderstands request or produces unusable output |

### Technical Score (0-1)

| Score | Criteria |
|-------|----------|
| 0.9-1.0 | Optimal technique selection, all tradeoffs documented, innovative |
| 0.8-0.9 | Good technique selection, appropriate for constraints |
| 0.7-0.8 | Workable approach, may miss optimization opportunities |
| 0.6-0.7 | Basic approach, some mismatches with creative vision |
| <0.6 | Inappropriate techniques or missing critical components |

### Design Score (0-1)

| Score | Criteria |
|-------|----------|
| 0.9-1.0 | Clean architecture, all connections valid, params well-designed |
| 0.8-0.9 | Good structure, minor issues, functional output |
| 0.7-0.8 | Working design, some redundancy or unnecessary complexity |
| 0.6-0.7 | Design has issues, requires manual fixes |
| <0.6 | Broken design, won't build or function |

### Artifact Checks (Boolean)

| Check | Pass Criteria |
|-------|---------------|
| uniforms_connected | All GLSL uniforms have matching control center params |
| parameters_functional | Parameters actually affect visual output |
| palette_used | Reusable palette components used where appropriate |
| operators_exist | All referenced operators are valid TD operators |

---

## Aggregation

### Project-Level Aggregation

When multiple runs exist for a strategy:

```yaml
strategy_aggregate:
  strategy: "v5"
  runs: 10

  quality:
    mean: 0.86
    std: 0.04
    min: 0.78
    max: 0.92

  tokens:
    mean: 42000
    std: 8000
    min: 28000
    max: 58000

  iterations:
    mean: 5.2
    std: 1.3

  build_success_rate: 1.0  # 10/10

  efficiency:
    mean: 0.21
    std: 0.03
```

### Cross-Project Comparison

Compare strategies across different project types:

```yaml
project_type_comparison:
  project_type: "audio_reactive"
  best_strategy: "v6"
  recommended_strategy: "v5"  # best efficiency

  project_type: "generative_art"
  best_strategy: "v3"  # evolutionary shines for creativity
  recommended_strategy: "v3"

  project_type: "simple_filter"
  best_strategy: "v2"  # fast, adequate quality
  recommended_strategy: "v2"
```

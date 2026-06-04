# Strategy V5: Deep Refinement

## Overview

V5 focuses on **quality control** through explicit quality thresholds, stretch goals ("could we do better?"), convergence detection, and phase reopening when issues are discovered. Best for **quality-critical projects** where hitting a high bar matters more than speed.

## When to Use

- Quality is the primary concern
- Willing to invest tokens for polish
- Need consistent, predictable quality bar
- Project will be judged on excellence

**Not ideal for**:
- Quick drafts or prototypes
- Budget-constrained projects
- When "good enough" is acceptable

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                  V5: DEEP REFINEMENT                             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   QUALITY TARGETS                         │   │
│  │                                                           │   │
│  │   Creative: 0.85    Technical: 0.85    Design: 0.90      │   │
│  │                                                           │   │
│  │   Stretch Threshold: 0.95 ("Could we do better?")        │   │
│  │   Convergence Window: 2 iterations without improvement   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  REFINEMENT LOOP                          │   │
│  │                                                           │   │
│  │   ┌───────────────────────────────────────────────────┐  │   │
│  │   │              EXPERT OUTPUT                         │  │   │
│  │   └───────────────────────┬───────────────────────────┘  │   │
│  │                           │                               │   │
│  │                           ▼                               │   │
│  │   ┌───────────────────────────────────────────────────┐  │   │
│  │   │            MULTI-PERSPECTIVE REVIEW               │  │   │
│  │   │                                                   │  │   │
│  │   │   ┌─────────┐  ┌─────────┐  ┌─────────┐          │  │   │
│  │   │   │Creative │  │   CG    │  │ Critic  │          │  │   │
│  │   │   │ Review  │  │ Review  │  │ Review  │          │  │   │
│  │   │   │  0.85   │  │  0.82   │  │  0.88   │          │  │   │
│  │   │   └─────────┘  └─────────┘  └─────────┘          │  │   │
│  │   │                                                   │  │   │
│  │   │   Aggregate Score: min(0.85, 0.82, 0.88) = 0.82  │  │   │
│  │   └───────────────────────┬───────────────────────────┘  │   │
│  │                           │                               │   │
│  │                           ▼                               │   │
│  │   ┌───────────────────────────────────────────────────┐  │   │
│  │   │          QUALITY GATE: Score >= Target?           │  │   │
│  │   │                                                   │  │   │
│  │   │              ┌────────┴────────┐                  │  │   │
│  │   │              │                 │                  │  │   │
│  │   │             NO                YES                 │  │   │
│  │   │              │                 │                  │  │   │
│  │   │              ▼                 ▼                  │  │   │
│  │   │    ┌─────────────────┐  ┌─────────────────┐      │  │   │
│  │   │    │ Iterate with    │  │ STRETCH CHECK   │      │  │   │
│  │   │    │ specific        │  │                 │      │  │   │
│  │   │    │ feedback        │  │ Score < 0.95?   │      │  │   │
│  │   │    └────────┬────────┘  │ Iterations left?│      │  │   │
│  │   │             │           └────────┬────────┘      │  │   │
│  │   │             │                    │               │  │   │
│  │   │             │           ┌────────┴────────┐      │  │   │
│  │   │             │          YES               NO      │  │   │
│  │   │             │           │                 │      │  │   │
│  │   │             │           ▼                 ▼      │  │   │
│  │   │             │    ┌───────────┐    ┌───────────┐  │  │   │
│  │   │             │    │ Try for   │    │   DONE    │  │  │   │
│  │   │             │    │ better    │    │           │  │  │   │
│  │   │             │    └─────┬─────┘    └───────────┘  │  │   │
│  │   │             │          │                         │  │   │
│  │   │             └──────────┴─────────────┐           │  │   │
│  │   │                                      │           │  │   │
│  │   │             ┌────────────────────────▼───────┐   │  │   │
│  │   │             │        CONVERGENCE CHECK       │   │  │   │
│  │   │             │                                │   │  │   │
│  │   │             │  No improvement in 2 iters?    │   │  │   │
│  │   │             │                                │   │  │   │
│  │   │             │        YES ───────▶ STOP       │   │  │   │
│  │   │             │        NO ────────▶ CONTINUE   │   │  │   │
│  │   │             └────────────────────────────────┘   │  │   │
│  │   └───────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   PHASE REOPENING                         │   │
│  │                                                           │   │
│  │   If Design reveals issue with earlier phase:            │   │
│  │                                                           │   │
│  │   Creative issue ─────▶ Reopen §2, preserve §3-4         │   │
│  │   Technical issue ────▶ Reopen §3, preserve §2           │   │
│  │                                                           │   │
│  │   Feedback from Design written to reopened section       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Phase Details

### Quality Gate

Each phase must pass a quality gate:

```yaml
quality_gate:
  evaluation:
    1. Expert produces output
    2. Multi-perspective review (if applicable)
    3. Aggregate score calculated (min of reviewers)
    4. Compare to target

  thresholds:
    creative: 0.85
    technical: 0.85
    design: 0.90

  actions:
    below_threshold:
      - Provide specific feedback
      - Request iteration
      - Track improvement delta

    at_threshold:
      - Check stretch goal
      - Consider "could we do better?"

    above_stretch:
      - Mark as excellent
      - Proceed immediately
```

### Stretch Goals

When quality target is met but not exceeded:

```yaml
stretch_goals:
  threshold: 0.95

  conditions_to_try:
    - Score is between target and stretch
    - Iterations remaining (< max_iterations)
    - Not converged (still improving)

  stretch_prompt: |
    This output meets the quality bar (0.87), but we're aiming for
    excellence (0.95). Consider:
    - What would make this REMARKABLE, not just good?
    - Is there a signature element missing?
    - Could the implementation be more elegant?

    Try one more iteration for excellence.

  stop_if:
    - Score reaches stretch (0.95)
    - Convergence detected (no improvement in 2 iterations)
    - Max iterations reached
```

### Convergence Detection

Prevents infinite loops:

```yaml
convergence_detection:
  window: 2  # iterations without improvement

  tracking:
    - iteration: 1
      score: 0.78
    - iteration: 2
      score: 0.84  # +0.06
    - iteration: 3
      score: 0.87  # +0.03
    - iteration: 4
      score: 0.87  # +0.00 (no improvement)
    - iteration: 5
      score: 0.88  # +0.01 (improvement!)
    - iteration: 6
      score: 0.88  # +0.00
    - iteration: 7
      score: 0.88  # +0.00 → CONVERGED (2 iterations, no improvement)

  on_convergence:
    action: "stop_iteration"
    reason: "No improvement in {window} iterations"
    accept_current: true  # if above threshold
```

### Phase Reopening

When later phases reveal issues:

```yaml
phase_reopening:
  triggers:
    - "Design cannot implement creative vision"
    - "Technical approach incompatible with creative"
    - "Missing creative guidance for this technique"

  process:
    1. Identify issue classification (creative/technical)
    2. Reopen appropriate section
    3. Preserve downstream sections (may be salvageable)
    4. Write feedback to reopened section
    5. Re-run that phase

  example:
    trigger: "Design: Cannot create particle effect as described - need more specific motion guidance"
    classification: creative
    action: "Reopen §2, add feedback: 'Need specific particle motion description for implementation'"
```

### Multi-Perspective Review

For Design phase, multiple reviewers:

```yaml
multi_perspective_review:
  reviewers:
    creative_perspective:
      question: "Does the visual match the creative brief?"
      weight: 1.0

    technical_perspective:
      question: "Are techniques used correctly?"
      weight: 1.0

    critic_perspective:
      question: "Overall coherence and quality?"
      weight: 1.0

  aggregation: min  # Most conservative

  example:
    creative_score: 0.88
    technical_score: 0.85
    critic_score: 0.90
    aggregate: 0.85  # min of all
```

## Configuration Options

```yaml
v5_config:
  quality_targets:
    creative: 0.85
    technical: 0.85
    design: 0.90

  stretch:
    threshold: 0.95
    enabled: true

  convergence:
    window: 2
    min_improvement: 0.01

  max_iterations:
    per_phase: 10
    total: 25

  phase_reopening:
    enabled: true
    preserve_downstream: true

  multi_perspective:
    enabled: true
    for_phases: ["design"]
    aggregation: "min"
```

## Expected Metrics

```yaml
typical_metrics:
  tokens:
    input: ~28000
    output: ~11000
    total: ~39000

  quality:
    creative: 0.85-0.92
    technical: 0.83-0.90
    design: 0.88-0.94
    final: 0.83-0.90

  iterations:
    creative: 2-4
    technical: 1-3
    design: 3-6
    stretch_attempts: 1-2
    total: 7-12

  convergence:
    converged_phases: 1-2
    stretch_achieved: ~30%

  troubleshooting:
    build_failures: ~2%
    phase_reopens: 0-1
    validation_errors: 2-4

  artifacts:
    uniforms_connected: ~95%
    parameters_functional: ~90%
    palette_used: ~75%
```

## Implementation Notes

### Quality Gate Implementation

```python
def quality_gate(self, output: dict, phase: str) -> GateResult:
    target = self.config.quality_targets[phase]
    stretch = self.config.stretch.threshold

    # Get scores
    if phase == "design":
        scores = self.multi_perspective_review(output)
        score = min(scores.values())
    else:
        score = self.critic.evaluate(output).score

    # Check threshold
    if score < target:
        return GateResult(
            passed=False,
            score=score,
            action="iterate",
            feedback=self.get_improvement_feedback(output, score, target)
        )

    # Check stretch
    if score < stretch and self.should_try_stretch():
        return GateResult(
            passed=True,
            score=score,
            action="try_stretch",
            feedback="Quality met, attempting excellence"
        )

    return GateResult(
        passed=True,
        score=score,
        action="proceed",
        feedback=None
    )
```

### Convergence Tracking

```python
class ConvergenceTracker:
    def __init__(self, window: int = 2, min_improvement: float = 0.01):
        self.window = window
        self.min_improvement = min_improvement
        self.scores = []

    def add_score(self, score: float) -> bool:
        """Add score, return True if converged."""
        self.scores.append(score)

        if len(self.scores) < self.window + 1:
            return False

        # Check last `window` scores for improvement
        recent = self.scores[-self.window:]
        baseline = self.scores[-(self.window + 1)]

        improvements = [s - baseline for s in recent]
        max_improvement = max(improvements)

        return max_improvement < self.min_improvement
```

### Phase Reopening Logic

```python
def handle_design_issue(self, issue: Issue, blackboard: Blackboard):
    if issue.classification == "creative":
        # Reopen creative phase
        blackboard.unlock_section("§2")
        blackboard.add_feedback("§2", f"From Design: {issue.description}")
        return "creative"

    elif issue.classification == "technical":
        # Reopen technical phase
        blackboard.unlock_section("§3")
        blackboard.add_feedback("§3", f"From Design: {issue.description}")
        return "technical"

    else:
        # Design can fix it
        return "design"
```

### Claude Code Execution

```
ORCHESTRATOR: Starting V5 Design Phase

TD DESIGNER: Reading §1-4...
TD DESIGNER: Generating network design...
TD DESIGNER: Writing §5 (v1)

[MULTI-PERSPECTIVE REVIEW]
Creative Review: Does visual match brief?
  Score: 0.88 - "Good color mapping, motion could be more organic"

CG Review: Are techniques correct?
  Score: 0.82 - "Compute shader setup correct, missing envelope smoothing"

Critic Review: Overall coherence?
  Score: 0.85 - "Solid design, some parameter naming inconsistency"

Aggregate Score: min(0.88, 0.82, 0.85) = 0.82

[QUALITY GATE]
Target: 0.90
Score: 0.82
Result: BELOW TARGET

Feedback:
- Add envelope smoothing to audio pipeline
- Improve parameter naming consistency
- Make motion more organic per creative brief

TD DESIGNER: Iterating with feedback...
TD DESIGNER: Writing §5 (v2)

[REVIEW v2]
Creative: 0.91
CG: 0.88
Critic: 0.89
Aggregate: 0.88

[QUALITY GATE]
Target: 0.90
Score: 0.88
Result: BELOW TARGET (but close)

TD DESIGNER: Iterating...
TD DESIGNER: Writing §5 (v3)

[REVIEW v3]
Creative: 0.92
CG: 0.91
Critic: 0.90
Aggregate: 0.90

[QUALITY GATE]
Target: 0.90
Score: 0.90
Result: PASS

[STRETCH CHECK]
Score: 0.90 < Stretch: 0.95
Iterations remaining: 7
Converged: No

Attempting stretch goal...

TD DESIGNER: Refining for excellence...

[REVIEW v4]
Aggregate: 0.91

[CONVERGENCE CHECK]
v3: 0.90, v4: 0.91
Improvement: +0.01 (above min 0.01)
Not converged, continue...

[REVIEW v5]
Aggregate: 0.91

[CONVERGENCE CHECK]
v4: 0.91, v5: 0.91
Improvement: +0.00
Not converged yet (need 2 iterations)

[REVIEW v6]
Aggregate: 0.91

[CONVERGENCE CHECK]
v5: 0.91, v6: 0.91
Improvement: +0.00 (2nd iteration)
CONVERGED - Stopping iteration

Final Score: 0.91
Proceeding to Build
```

## Success Criteria

A V5 run is successful when:

- [ ] All phases reach quality targets
- [ ] Stretch goals attempted when applicable
- [ ] Convergence properly detected (no infinite loops)
- [ ] Phase reopening works correctly (if triggered)
- [ ] Multi-perspective reviews properly aggregated
- [ ] Final quality score >= 0.85 (or higher for design)

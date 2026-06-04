# Verification and Completion Logic

This document describes what triggers "done", the critic's checklist, and retry/loop behavior.

---

## What Triggers "Done"?

### Workflow Completion Criteria

A workflow is complete when ALL of these are met:

```yaml
completion_criteria:
  1_all_sections_filled:
    - §1 Requirements: has content
    - §2 Creative Vision: has content
    - §3 Technical Approach: has content
    - §4 Available Resources: has content (KB query ran)
    - §5 Network Design: has content
    - §6 Validation History: has at least one review
    - §7 Build Artifacts: has file paths

  2_critic_approved:
    - overall_score >= 0.65
    - no blocking issues
    - verdict == "PASS"

  3_build_succeeded:
    - output file exists
    - file size > 0
    - TOC file valid
```

### Phase Transitions

```python
class Phase(Enum):
    INIT = "init"           # Starting
    CREATIVE = "creative"   # Creative expert working
    TECHNICAL = "technical" # CG expert working
    RESOURCES = "resources" # KB queries running
    DESIGN = "design"       # TD Designer working
    BUILD = "build"         # Builder running
    COMPLETE = "complete"   # Done!

# Transitions
INIT → CREATIVE: User prompt received
CREATIVE → TECHNICAL: Creative vision approved
TECHNICAL → RESOURCES: Technical approach approved
RESOURCES → DESIGN: KB queries complete
DESIGN → BUILD: Network design approved by critic
BUILD → COMPLETE: TOE file generated successfully
```

### Strategy-Specific Completion

#### V2 (Linear)
```yaml
completion: "All phases complete in sequence"
max_iterations: 1
```

#### V3 (Evolutionary)
```yaml
completion: "Best variant selected after N generations"
max_iterations: 5
convergence: "Top score stable for 2 iterations"
```

#### V4 (Blackboard)
```yaml
completion: "All blocking issues resolved"
max_iterations: 10
convergence: "No unresolved issues"
```

#### V5 (Deep Refinement)
```yaml
completion: "Convergence window satisfied"
max_iterations: 10
convergence_window: 3
convergence_threshold: 0.02  # Score change < 2%
```

#### V6 (Unified)
```yaml
completion: "Quality targets met or max iterations"
quality_targets:
  creative: 0.8
  technical: 0.8
  design: 0.75
  overall: 0.8
max_iterations: 15
```

---

## Critic's Actual Checklist

### Evaluation Criteria

The critic evaluates against 4 main criteria:

```yaml
criteria:
  artistic_coherence:
    weight: 0.25
    checks:
      - "Is mood from defined vocabulary?"
      - "Do colors align with mood?"
      - "Does motion support emotional goal?"
      - "Is aesthetic appropriate for context?"
    rubric:
      0.9-1.0: "Exceptional coherence, all elements aligned"
      0.7-0.9: "Good coherence, minor inconsistencies"
      0.5-0.7: "Moderate coherence, needs refinement"
      0.3-0.5: "Weak coherence, significant gaps"
      0.0-0.3: "No coherence, contradictory elements"

  technical_feasibility:
    weight: 0.30
    checks:
      - "Are all operators valid TD operators?"
      - "Do connections make sense (TOP→TOP, CHOP→CHOP)?"
      - "Are parameter values reasonable?"
      - "Is data flow complete and connected?"
      - "Is performance target achievable?"
    rubric:
      0.9-1.0: "Fully buildable, all validated"
      0.7-0.9: "Buildable with minor adjustments"
      0.5-0.7: "Likely buildable, some unknowns"
      0.3-0.5: "Significant technical issues"
      0.0-0.3: "Unbuildable as specified"

  implementation_clarity:
    weight: 0.25
    checks:
      - "Is spec complete enough to build?"
      - "Are all parameters specified?"
      - "Are expressions syntactically correct?"
      - "Is hierarchy clear?"
      - "Are flags set appropriately?"
    rubric:
      0.9-1.0: "Crystal clear, no ambiguity"
      0.7-0.9: "Clear with minor gaps"
      0.5-0.7: "Moderate clarity, needs some inference"
      0.3-0.5: "Unclear, significant gaps"
      0.0-0.3: "Ambiguous, cannot proceed"

  creative_alignment:
    weight: 0.20
    checks:
      - "Does design match original request?"
      - "Are key requirements addressed?"
      - "Does output serve user's goal?"
      - "Is creative intent preserved?"
    rubric:
      0.9-1.0: "Perfect alignment"
      0.7-0.9: "Good alignment, captures intent"
      0.5-0.7: "Partial alignment, some drift"
      0.3-0.5: "Poor alignment, missed requirements"
      0.0-0.3: "No alignment, wrong direction"
```

### Blocking Issue Types

```yaml
blocking_issues:
  vague_mood:
    severity: "high"
    symptoms:
      - "Uses undefined mood terms"
      - "Says 'interesting' or 'nice' without specifics"
      - "No visual markers specified"
    auto_revise: true

  hallucinated_operator:
    severity: "high"
    symptoms:
      - "Operator not in TD registry"
      - "Parameter doesn't exist"
      - "Connection type invalid"
    auto_revise: true

  incomplete_data_flow:
    severity: "high"
    symptoms:
      - "Dangling inputs"
      - "No output operator"
      - "Disconnected graph"
    auto_revise: true

  missing_audio_mapping:
    severity: "medium"
    symptoms:
      - "Audio-reactive requested but no mappings"
      - "CHOP exports not defined"
    auto_revise: true

  performance_concern:
    severity: "medium"
    symptoms:
      - "High resolution + many particles + feedback"
      - "No LOD or culling"
    auto_revise: false  # Warning only
```

### Access to Original Prompt

**Yes**, the critic has access to the original prompt via:

```python
# Critic reads these sections:
reads_sections = [
    SectionID.REQUIREMENTS,      # Contains original_prompt
    SectionID.CREATIVE_VISION,
    SectionID.TECHNICAL_APPROACH,
    SectionID.AVAILABLE_RESOURCES,
    SectionID.NETWORK_DESIGN
]

# From §1_requirements:
original_prompt = context["blackboard_sections"]["§1_requirements"]["content"]["original_prompt"]
```

---

## Retry/Loop Behavior

### When Critic Says "Revise"

```yaml
revision_flow:
  trigger: "critic.decision == 'revise'"

  action:
    1. Increment revision_cycle
    2. Check if revision_cycle >= max_cycles (3)
    3. If under limit:
       - Send feedback to failing expert
       - Expert re-runs build step
       - Critic re-evaluates
    4. If at limit:
       - Escalate to human review
       - Mark workflow as "failed"
```

### Which Expert Gets Revision Request?

```yaml
revision_routing:
  # Based on issue classification
  creative_issues:
    - vague_mood
    - missing_color_palette
    - weak_emotional_mapping
    route_to: "creative_expert"

  technical_issues:
    - hallucinated_operator
    - invalid_data_flow
    - performance_concern
    route_to: "cg_expert" or "td_designer"

  design_issues:
    - incomplete_spec
    - missing_connections
    - unclear_hierarchy
    route_to: "td_designer"
```

### Revision Context

The expert receives:

```yaml
revision_context:
  original_output: <their previous output>
  critic_feedback:
    score: 0.58
    issues:
      - type: "vague_mood"
        description: "Mood 'dynamic' not from vocabulary"
        suggested_fix: "Use 'aggressive' or 'chaotic' instead"
    guidance: |
      Please revise with:
      1. Use mood from defined vocabulary
      2. Add specific color hex codes
      3. Define audio mappings

  revision_cycle: 2
  cycles_remaining: 1
```

### What Happens After Failure?

```yaml
escalation:
  trigger: "revision_cycle >= 3"

  action:
    decision: "fail"
    reason: "Exceeded maximum revision cycles"

    output:
      status: "failed"
      history:
        - cycle: 1, score: 0.42, issues: [...]
        - cycle: 2, score: 0.55, issues: [...]
        - cycle: 3, score: 0.61, issues: [...]

      pattern_analysis:
        recurring_issue: "vague_mood"
        suggestion: "Initial prompt may be too ambiguous"

      recommendation: |
        Human review required.
        Options:
        1. Provide more specific prompt
        2. Manually override creative spec
        3. Skip to manual TD build
```

---

## Workflow State Diagram

```
                    ┌─────────────────┐
                    │      INIT       │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
     ┌──────────────│    CREATIVE     │◀──────────┐
     │              └────────┬────────┘           │
     │                       │                    │
     │      ┌────────────────┼────────────────┐   │
     │      │                │                │   │
     │      ▼                ▼                │   │
     │   APPROVED         REVISE ─────────────┘   │
     │      │            (cycle < 3)              │
     │      │                                     │
     │      │            FAIL ────────────────────┼──▶ ESCALATE
     │      │          (cycle >= 3)               │
     │      ▼                                     │
     │  ┌─────────────────┐                      │
     │  │   TECHNICAL     │◀─────────────────────┘
     │  └────────┬────────┘
     │           │
    ... (same pattern for each phase) ...
     │           │
     │           ▼
     │  ┌─────────────────┐
     │  │     BUILD       │
     │  └────────┬────────┘
     │           │
     │           ▼
     │  ┌─────────────────┐
     └─▶│    COMPLETE     │
        └─────────────────┘
```

---

## Monitoring Completion

### Blackboard Events

```python
# Track all state changes
blackboard.events = [
    {"type": "write", "section_id": "§2_creative_vision", "timestamp": "..."},
    {"type": "phase_transition", "from_phase": "creative", "to_phase": "technical"},
    {"type": "add_issue", "issue_id": "ISSUE-0001", "severity": "high"},
    {"type": "resolve_issue", "issue_id": "ISSUE-0001", "resolution": "..."},
    ...
]
```

### Completion Check

```python
def is_workflow_complete(blackboard: Blackboard) -> bool:
    # Check all sections have content
    for section_id in SectionID:
        if section_id == SectionID.VALIDATION_HISTORY:
            continue  # May be empty if first pass
        if not blackboard.read(section_id):
            return False

    # Check critic approved
    validation = blackboard.read(SectionID.VALIDATION_HISTORY)
    if not validation:
        return False

    reviews = validation.get("reviews", [])
    if not reviews:
        return False

    latest_review = reviews[-1]
    if latest_review.get("decision", {}).get("outcome") != "approve":
        return False

    # Check build artifacts exist
    artifacts = blackboard.read(SectionID.BUILD_ARTIFACTS)
    if not artifacts:
        return False

    if artifacts.get("build_result", {}).get("status") != "success":
        return False

    return True
```

# Strategy V4: Blackboard

## Overview

V4 introduces the **Blackboard architecture** with a central PROJECT DOCUMENT (§1-§7) that all agents read from and write to. This creates a single source of truth, enables partial re-work, and provides a full audit trail. Best for **complex projects** with many interdependencies.

## When to Use

- Complex projects with many interdependencies
- Need for audit trail and version history
- Multiple experts need to coordinate
- Partial re-work likely (fix one phase without redoing others)

**Not ideal for**:
- Simple, linear tasks
- When speed is more important than state management

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    V4: BLACKBOARD                                │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    BLACKBOARD                             │   │
│  │               (PROJECT DOCUMENT)                          │   │
│  │                                                           │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐             │   │
│  │  │   §1   │ │   §2   │ │   §3   │ │   §4   │             │   │
│  │  │ Reqs   │ │Creative│ │ Tech   │ │Resource│             │   │
│  │  └────────┘ └────────┘ └────────┘ └────────┘             │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐                        │   │
│  │  │   §5   │ │   §6   │ │   §7   │                        │   │
│  │  │ Design │ │Validate│ │Artifact│                        │   │
│  │  └────────┘ └────────┘ └────────┘                        │   │
│  │                                                           │   │
│  │  + version history                                        │   │
│  │  + section locking                                        │   │
│  │  + blocking issues queue                                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│              ┌───────────────┼───────────────────┐              │
│              │               │                   │              │
│              ▼               ▼                   ▼              │
│  ┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐    │
│  │    Orchestrator  │ │    Experts   │ │     Critic       │    │
│  │                  │ │              │ │                  │    │
│  │ • Read state     │ │ • Read §     │ │ • Read §1-5      │    │
│  │ • Decide next    │ │ • Write §    │ │ • Write §6       │    │
│  │ • Route issues   │ │              │ │ • Classify issues│    │
│  └──────────────────┘ └──────────────┘ └──────────────────┘    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  ORCHESTRATOR LOOP                        │   │
│  │                                                           │   │
│  │  ┌──────────────┐                                        │   │
│  │  │ Read state   │                                        │   │
│  │  └──────┬───────┘                                        │   │
│  │         │                                                 │   │
│  │         ▼                                                 │   │
│  │  ┌──────────────────────────────────────────────────┐    │   │
│  │  │            What needs work?                       │    │   │
│  │  │                                                   │    │   │
│  │  │  §2 empty? ────────▶ Activate Creative Expert    │    │   │
│  │  │  §3 empty? ────────▶ Activate CG Expert          │    │   │
│  │  │  Blocking issue? ──▶ Route to fixer              │    │   │
│  │  │  Needs validation? ─▶ Activate Critic            │    │   │
│  │  │  Phase complete? ──▶ Advance phase               │    │   │
│  │  │  All complete? ────▶ Deliver                     │    │   │
│  │  └──────────────────────────────────────────────────┘    │   │
│  │         │                                                 │   │
│  │         ▼                                                 │   │
│  │  ┌──────────────┐                                        │   │
│  │  │ Execute      │                                        │   │
│  │  │ (loop)       │                                        │   │
│  │  └──────────────┘                                        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Phase Details

### Orchestrator Decision Loop

The orchestrator continuously evaluates blackboard state:

```python
def orchestrator_loop(self, blackboard: Blackboard):
    while True:
        state = blackboard.read_state()

        if state.all_complete:
            return self.deliver(blackboard)

        if state.blocking_issues:
            issue = state.blocking_issues[0]
            self.route_to_fixer(issue, blackboard)
            continue

        if state.needs_validation:
            self.activate_critic(state.needs_validation, blackboard)
            continue

        if state.phase_incomplete:
            self.activate_agent(state.current_phase, blackboard)
            continue

        if state.phase_complete:
            self.advance_phase(blackboard)
            continue
```

### State Evaluation

```yaml
state_evaluation:
  all_complete:
    condition: "§7 written AND no blocking issues"
    action: deliver

  blocking_issues:
    condition: "§6.current_blocking_issues not empty"
    action: route_to_fixer

  needs_validation:
    condition: "Section has new version not yet validated"
    action: activate_critic

  phase_incomplete:
    condition: "Current phase section is empty or score < target"
    action: activate_agent

  phase_complete:
    condition: "Current phase section score >= target AND locked"
    action: advance_phase
```

### Section Locking

Sections are locked when approved:

```yaml
locking:
  when_locked:
    - Cannot be modified
    - Can only be unlocked by:
      - User feedback requiring reopening
      - Downstream phase discovering blocking issue
      - Explicit user request

  lock_protocol:
    1. Critic validates section
    2. Score >= target
    3. Critic issues lock command
    4. Blackboard marks section locked
    5. Version frozen

  unlock_protocol:
    1. Blocking issue identified
    2. Issue classified (creative/technical/design)
    3. Relevant section unlocked
    4. Feedback written to §6
    5. Agent re-activated for that section
```

## Configuration Options

```yaml
v4_config:
  sections:
    - §1_requirements
    - §2_creative_vision
    - §3_technical_approach
    - §4_available_resources
    - §5_network_design
    - §6_validation_history
    - §7_build_artifacts

  quality_targets:
    §2: 0.85
    §3: 0.85
    §5: 0.90

  locking:
    enabled: true
    auto_lock_on_approval: true

  audit_trail:
    enabled: true
    store_all_versions: true
    store_all_validations: true

  blocking_issues:
    queue_enabled: true
    classification_required: true
    auto_routing: true
```

## Expected Metrics

```yaml
typical_metrics:
  tokens:
    input: ~22000
    output: ~10000
    total: ~32000

  quality:
    creative: 0.82-0.88
    technical: 0.80-0.86
    design: 0.84-0.90
    final: 0.80-0.85

  iterations:
    orchestrator_loops: 8-12
    section_updates: 6-10
    total: 10-15

  troubleshooting:
    build_failures: ~5%
    blocking_issues_resolved: 1-3
    phase_reopens: 0-1

  artifacts:
    uniforms_connected: ~85%
    parameters_functional: ~80%
    palette_used: ~65%
```

## Implementation Notes

### Blackboard Data Structure

```python
@dataclass
class Blackboard:
    metadata: Metadata
    sections: Dict[str, Section]
    locking: Dict[str, LockState]
    blocking_issues: List[Issue]

    def read_section(self, section_id: str) -> Section:
        """Read a section's current version."""
        pass

    def write_section(self, section_id: str, content: dict) -> int:
        """Write new version, returns version number."""
        pass

    def lock_section(self, section_id: str, reason: str) -> None:
        """Lock a section, preventing further writes."""
        pass

    def unlock_section(self, section_id: str, reason: str) -> None:
        """Unlock a section for modification."""
        pass

    def add_blocking_issue(self, issue: Issue) -> None:
        """Add a blocking issue to the queue."""
        pass

    def resolve_issue(self, issue_id: str, resolution: str) -> None:
        """Mark an issue as resolved."""
        pass
```

### Issue Classification and Routing

```yaml
issue_classification:
  creative:
    keywords: ["vision", "mood", "aesthetic", "color", "motion quality"]
    route_to: creative_expert
    unlocks: §2

  technical:
    keywords: ["technique", "algorithm", "performance", "optimization"]
    route_to: cg_expert
    unlocks: §3

  design:
    keywords: ["connection", "parameter", "operator", "structure"]
    route_to: td_designer
    unlocks: §5

  structural:
    keywords: ["json", "syntax", "format", "schema"]
    route_to: network_builder
    unlocks: §5

  logic:
    keywords: ["data flow", "signal path", "feedback loop"]
    route_to: td_designer
    unlocks: §5
```

### Partial Re-work

When an issue requires reopening an earlier phase:

```python
def handle_phase_reopen(self, issue: Issue, blackboard: Blackboard):
    # 1. Identify affected section
    section = self.classify_issue_section(issue)

    # 2. Unlock the section
    blackboard.unlock_section(section, reason=f"Reopened due to: {issue.description}")

    # 3. Preserve later sections (don't delete)
    # They may still be valid or salvageable

    # 4. Add feedback for the agent
    blackboard.add_feedback(section, issue.feedback)

    # 5. Route to appropriate expert
    self.route_to_expert(section, blackboard)
```

### Claude Code Execution

```
ORCHESTRATOR: Reading blackboard state...
State: §1 complete, §2 empty, phase: CREATIVE

ORCHESTRATOR: Activating Creative Expert for §2

CREATIVE EXPERT: Reading §1 Requirements...
CREATIVE EXPERT: Generating creative vision...
CREATIVE EXPERT: Writing §2 (v1)

ORCHESTRATOR: Reading blackboard state...
State: §2.v1 needs validation

ORCHESTRATOR: Activating Critic for §2.v1

CRITIC: Evaluating §2.v1...
CRITIC: Score: 0.78 - Below target (0.85)
CRITIC: Adding blocking issue: "Lacks signature element"
CRITIC: Writing to §6

ORCHESTRATOR: Reading blackboard state...
State: Blocking issue in queue

ORCHESTRATOR: Routing to Creative Expert with feedback

CREATIVE EXPERT: Reading feedback from §6...
CREATIVE EXPERT: Revising creative vision...
CREATIVE EXPERT: Writing §2 (v2)

ORCHESTRATOR: Reading blackboard state...
State: §2.v2 needs validation

CRITIC: Evaluating §2.v2...
CRITIC: Score: 0.87 - Pass
CRITIC: Locking §2

ORCHESTRATOR: Advancing to TECHNICAL phase
```

## Audit Trail

The blackboard maintains complete history:

```yaml
audit_trail:
  §2_creative_vision:
    versions:
      - v1:
          timestamp: "2025-12-18T10:00:00Z"
          written_by: creative_expert
          content: {...}
          validation:
            timestamp: "2025-12-18T10:01:00Z"
            score: 0.78
            passed: false
            feedback: "Lacks signature element"

      - v2:
          timestamp: "2025-12-18T10:05:00Z"
          written_by: creative_expert
          content: {...}
          validation:
            timestamp: "2025-12-18T10:06:00Z"
            score: 0.87
            passed: true

    lock_history:
      - locked_at: "2025-12-18T10:06:00Z"
        locked_by: critic
        reason: "Approved at score 0.87"
```

## Success Criteria

A V4 run is successful when:

- [ ] All sections §1-§7 populated
- [ ] No blocking issues remaining
- [ ] All required sections locked
- [ ] Audit trail complete and consistent
- [ ] Partial re-work (if occurred) properly tracked
- [ ] Version history preserved for all sections

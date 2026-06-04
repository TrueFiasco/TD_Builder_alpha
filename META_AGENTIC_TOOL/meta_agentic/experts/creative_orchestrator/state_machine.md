# Creative Orchestrator - State Machine Reference

## State Diagram

```
                                    ┌─────────────────────────────────────────────────────────────┐
                                    │                                                             │
                                    ▼                                                             │
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐        ┌──────────────────┐
│ awaiting_input  │───────▶│creative_ideation│───────▶│  cg_translation │───────▶│ creative_review  │
└─────────────────┘        └─────────────────┘        └─────────────────┘        └──────────────────┘
                                    ▲                          ▲                         │
                                    │                          │                         │
                                    │                          │            ┌────────────┴────────────┐
                                    │                          │            │                         │
                                    │                          │      [approve]                  [revise]
                                    │                          │            │                         │
                                    │                          │            ▼                         ▼
                                    │                          │   ┌─────────────────┐     ┌──────────────────┐
                                    │                          │   │technical_review │     │revision_creative │
                                    │                          │   └─────────────────┘     └──────────────────┘
                                    │                          │            │                         │
                                    │                          │   ┌────────┴────────┐               │
                                    │                          │   │                 │               │
                                    │                     [revise]            [approve]              │
                                    │                          │                 │                   │
                                    │                          ▼                 ▼                   │
                                    │               ┌──────────────────┐  ┌─────────────────┐        │
                                    │               │revision_technical│  │ final_approval  │        │
                                    │               └──────────────────┘  └─────────────────┘        │
                                    │                          │                 │                   │
                                    │                          │         ┌───────┴───────┐           │
                                    │                          │    [approve]      [revise]          │
                                    │                          │         │              │            │
                                    │                          │         ▼              └────────────┤
                                    │                          │  ┌─────────────────┐               │
                                    │                          │  │  handoff_ready  │               │
                                    │                          │  └─────────────────┘               │
                                    │                          │         │                          │
                                    │                          │         ▼                          │
                                    │                          │  ┌─────────────────┐               │
                                    │                          │  │    completed    │               │
                                    │                          │  └─────────────────┘               │
                                    │                          │                                    │
                                    │              [max_revisions]              [max_revisions]     │
                                    │                          │                         │          │
                                    │                          ▼                         ▼          │
                                    │                       ┌─────────────────────────────┐         │
                                    │                       │          failed             │◀────────┘
                                    │                       └─────────────────────────────┘
                                    │
                                    └─────────────────────────────────────────────────────
```

## State Definitions

### awaiting_input
- **Type**: Initial state
- **Description**: Waiting for user creative request
- **Entry actions**: None
- **Exit actions**: Store user_request

### creative_ideation
- **Type**: Processing state
- **Description**: creative_expert generates artistic vision
- **Entry actions**: Invoke creative_expert
- **Exit actions**: Store creative_spec
- **Agent**: creative_expert (plan → build)

### cg_translation
- **Type**: Processing state
- **Description**: cg_expert translates vision to technical approach
- **Entry actions**: Invoke cg_expert with creative_spec
- **Exit actions**: Store technical_approach
- **Agent**: cg_expert (plan → build)

### creative_review
- **Type**: Decision state
- **Description**: critic evaluates artistic vision
- **Entry actions**: Invoke critic (creative_review)
- **Exit actions**: Record review result
- **Agent**: critic (build only)
- **Decision**: approve → technical_review, revise → revision_creative

### revision_creative
- **Type**: Loop state
- **Description**: Prepare for creative revision
- **Entry actions**: Check revision count, prepare feedback
- **Exit actions**: Increment creative revision count
- **Max cycles**: 3

### technical_review
- **Type**: Decision state
- **Description**: critic evaluates technical approach
- **Entry actions**: Invoke critic (technical_review)
- **Exit actions**: Record review result
- **Agent**: critic (build only)
- **Decision**: approve → final_approval, revise → revision_technical

### revision_technical
- **Type**: Loop state
- **Description**: Prepare for technical revision
- **Entry actions**: Check revision count, prepare feedback
- **Exit actions**: Increment technical revision count
- **Max cycles**: 3

### final_approval
- **Type**: Decision state
- **Description**: critic validates combined creative_brief
- **Entry actions**: Assemble brief, invoke critic (final_approval)
- **Exit actions**: Record final review
- **Agent**: critic (build only)
- **Decision**: approve → handoff_ready, revise → appropriate revision state

### handoff_ready
- **Type**: Handoff state
- **Description**: creative_brief ready for td_designer
- **Entry actions**: Format brief, add td_recommendations
- **Exit actions**: Log handoff event

### completed
- **Type**: Terminal state (success)
- **Description**: Workflow completed successfully
- **Entry actions**: Log completion, return creative_brief

### failed
- **Type**: Terminal state (failure)
- **Description**: Workflow failed after max revisions
- **Entry actions**: Log failure, escalate

## Transition Table

| From State | Trigger | To State | Guard Condition |
|------------|---------|----------|-----------------|
| awaiting_input | user_request_received | creative_ideation | - |
| creative_ideation | creative_spec_generated | cg_translation | creative_spec valid |
| cg_translation | technical_approach_generated | creative_review | technical_approach valid |
| creative_review | creative_review_approve | technical_review | score >= 0.65, no blocking |
| creative_review | creative_review_revise | revision_creative | score < 0.65 OR blocking |
| revision_creative | revision_submitted | creative_ideation | revisions < max |
| revision_creative | max_revisions_exceeded | failed | revisions >= 3 |
| technical_review | technical_review_approve | final_approval | score >= 0.65, no blocking |
| technical_review | technical_review_revise | revision_technical | score < 0.65 OR blocking |
| revision_technical | revision_submitted | cg_translation | revisions < max |
| revision_technical | max_revisions_exceeded | failed | revisions >= 3 |
| final_approval | final_review_approve | handoff_ready | score >= 0.65, no blocking |
| final_approval | final_review_revise_creative | revision_creative | creative issues |
| final_approval | final_review_revise_technical | revision_technical | technical issues |
| handoff_ready | td_designer_accepts | completed | - |

## Revision Counters

```yaml
revision_counts:
  creative: 0      # Increments on revision_creative → creative_ideation
  technical: 0     # Increments on revision_technical → cg_translation
  total: 0         # Sum of above

limits:
  max_creative: 3
  max_technical: 3
  max_total: 5     # Additional safety limit
```

## State Data

Each state maintains:

```yaml
state_data:
  current_state: "{{state_name}}"
  timestamp: "{{ISO8601}}"

  artifacts:
    user_request: "{{request}}"
    creative_spec: "{{spec or null}}"
    technical_approach: "{{approach or null}}"
    creative_brief: "{{brief or null}}"

  reviews:
    creative_review:
      - cycle: 0
        score: 0.XX
        decision: "approve|revise"
        issues: []
    technical_review:
      - cycle: 0
        score: 0.XX
        decision: "approve|revise"
        issues: []
    final_approval:
      - score: 0.XX
        decision: "approve|revise"

  revision_counts:
    creative: N
    technical: N
    total: N

  history:
    - state: "{{state}}"
      entered: "{{timestamp}}"
      exited: "{{timestamp}}"
      trigger: "{{trigger}}"
```

## Approval Thresholds

From critique_patterns.yaml:

| Review Type | Threshold | Blocking Issues |
|-------------|-----------|-----------------|
| creative_review | 0.65 | vague_mood, color_mood_conflict, motion_mood_conflict |
| technical_review | 0.65 | algorithm_mismatch, performance_unrealistic, missing_data_flow |
| final_approval | 0.65 | All blocking issues |

## Error States

### Revision Overflow
```yaml
error: "revision_overflow"
condition: "revision_counts.total >= max_total"
action: "transition to failed"
message: "Total revisions exceeded maximum (5)"
```

### Agent Timeout
```yaml
error: "agent_timeout"
condition: "agent execution > 60000ms"
action: "retry once, then fail"
message: "Agent {agent_id} timed out"
```

### Invalid Transition
```yaml
error: "invalid_transition"
condition: "requested transition not in allowed transitions"
action: "log and ignore"
message: "Cannot transition from {current} to {requested}"
```

## Resume Protocol

To resume interrupted workflow:

1. Load persisted state_data
2. Identify last completed state
3. Determine next valid transition
4. Continue execution

```yaml
resume:
  load_from: "state_data.json"
  validate:
    - "artifacts integrity"
    - "revision_counts accuracy"
    - "valid state"
  continue_from: "{{next_state}}"
```

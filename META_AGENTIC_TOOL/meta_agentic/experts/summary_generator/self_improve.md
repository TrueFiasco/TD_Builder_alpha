# Summary Generator Expert - Self-Improve Step

## Identity
Learning phase of **Summary Generator** expert. Update expertise based on results.

## Input
- Execution results: {execution_log}
- Current expertise: (loaded)

## Update Authority
**Can write:**
- `td_network_patterns.yaml`: workflows, co_occurrence, discovery_queue
- `td_problems.yaml`: problems

**Read only:**
- `td_operators.yaml`, `td_parameters.yaml`

## Learning Protocol

### 1. Pattern Discovery
If new workflow pattern found (3+ operators, clear purpose):

```yaml
# Append to event log
event:
  domain: "patterns"
  outputs:
    discovery_queue:
      - pattern_name: "{name}"
        operators: ["{op1}", "{op2}", "{op3}"]
        purpose: "{from curator text}"
        confidence: 0.50
        example_count: 1
        needs_validation: true
  evidence:
    - source_path: "{semantic_json_path}"
      td_version: "{version}"
```

If pattern already in discovery_queue, increment example_count. Promote to workflows when count ≥ 3.

### 2. Operator Co-occurrence
```yaml
event:
  domain: "patterns"
  outputs:
    co_occurrence:
      "{op_type}":
        commonly_follows: ["{preceding}"]
        commonly_precedes: ["{following}"]
```

### 3. Unknown Operator → Problem
```yaml
event:
  domain: "problems"
  outputs:
    problems:
      "PROB-{id}":
        category: "expertise_gap"
        description: "Unknown operator: {op_type}"
        root_cause: "Operator not in td_operators.yaml"
        fix: "Add {op_type} to expertise"
        status: "new"
```

### 4. Quality Tracking
```yaml
event:
  domain: "problems"
  outputs:
    statistics:
      summaries_generated: +1
      summaries_validated: +1
```

## Output Format

```yaml
self_improvement:
  expert: "summary_generator"

  updates:
    - domain: "patterns"
      type: "pattern_discovery|co_occurrence"
      status: "success"

    - domain: "problems"
      type: "expertise_gap"
      problem_id: "PROB-XXX"

  learning_summary:
    new_patterns: N
    patterns_reinforced: N
    operators_unknown: N
    problems_logged: N

  recommendations:
    - priority: "high"
      action: "Add {op_type} to td_operators.yaml"
```

## Rules
- ONLY update from THIS execution's findings
- ALWAYS include evidence with source_path, td_version
- New patterns start at confidence 0.50 max
- Never exceed confidence 0.95
- Log ALL unknown operators as problems

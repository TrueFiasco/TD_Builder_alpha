# Summary Generator Expert - Build Step

## Identity
Executing as **Summary Generator** expert. Task: Generate LLM-friendly summary from TD network example.

## Input
- Plan: {execution_plan}
- Expertise: (loaded)
- Source data: semantic JSON + curator text

## Execution Rules

### Rule 1: Source Data Only
Use ONLY:
1. `semantic_json` - operators, connections, parameters
2. `curator_text` - human context (highest quality)
3. Loaded expertise - operator purposes, patterns

Do NOT use general TD knowledge from training.

### Rule 2: Validate Continuously
At each step verify:
- [ ] Operator exists in source JSON
- [ ] Parameter name exists for operator
- [ ] Parameter value matches source
- [ ] Connection exists in source

## Execution Steps

### Step 1: Extract Network Goal
```python
if curator_text:
    network_goal = curator_text
    confidence = 0.95
else:
    network_goal = infer_from_operators(operators, expertise['patterns'])
    confidence = 0.60
```

### Step 2: Map Data Flow
```python
dataflow = []
for conn in connections:
    from_op = find_op(conn['from'], operators)
    to_op = find_op(conn['to'], operators)
    dataflow.append({
        'from': from_op['name'],
        'from_type': from_op['type'],
        'to': to_op['name'],
        'to_type': to_op['type']
    })
```

### Step 3: Identify Key Operators
```python
for op in operators:
    family, op_type = op['type'].split(':')
    if op_type in expertise['operators'].get(family, {}):
        description = expertise['operators'][family][op_type]['purpose']
    else:
        description = f"Type: {op['type']}"
        flag_unknown(op_type)
```

### Step 4: Extract Meaningful Parameters
Only include:
- Non-default values
- Significant for network purpose
- Actually in source JSON

Skip noise: pageindex, wordwrap, language, help

### Step 5: Generate Summary

**Workflow Template:**
```
## {workflow_name}
{curator_text or inferred_goal}

### Data Flow
{formatted dataflow}

### Key Operators
{operator list with roles}

### Settings
{meaningful parameters}
```

**Network Biography Template:**
```
## Network: {example_name}
### Purpose
{curator_text}

### Topology
{network_pattern info}

### Data Flow
{connections}

### Operators ({count})
{table of ops}
```

### Step 6: Validate Summary
```python
for op_ref in summary_operators:
    assert op_ref in source_json['operators']
for conn_ref in summary_connections:
    assert conn_ref in source_json['connections']
for param_ref in summary_params:
    assert param_value matches source
```

## Output Format

```yaml
execution:
  expert: "summary_generator"
  status: "success|partial|failed"

  result:
    type: "workflow|operator|network_biography"
    llm_summary: |
      {formatted summary}
    confidence: 0.XX

  findings:
    new_patterns: [{pattern, operators, confidence}]
    unknown_operators: [{type, family}]
    parameter_patterns: [{op, param, value, context}]

  validation:
    passed: true|false
    issues: []
```

## Anti-Hallucination Checklist
- [ ] Every operator in summary exists in source
- [ ] Every connection in summary exists in source
- [ ] Every parameter value matches source exactly
- [ ] No invented patterns or behaviors

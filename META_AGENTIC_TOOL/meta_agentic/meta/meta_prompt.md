# Meta-Prompt: TouchDesigner Task Prompt Generator

## Purpose

Generate specialized prompts for TouchDesigner tasks. This meta-prompt creates prompts that follow the Plan-Build-Self-Improve pattern and enforce source of truth validation.

## How to Use

Provide the following inputs to generate a task prompt:

```yaml
task_type: "summary|build|validate|search|reverse_engineer"
task_description: "What the task should accomplish"
target_operators: ["optional", "list", "of", "operators"]
expertise_files:
  reads: ["td_operators.yaml", "td_network_patterns.yaml"]
  writes: ["td_network_patterns.yaml", "td_problems.yaml"]
```

## Generated Prompt Structure

All generated prompts follow this pattern:

---

### Generated Prompt Template

```markdown
# TD Task: {task_type} - {task_description}

## Role
You are a TouchDesigner {task_type} expert agent. Your job is to {task_description} while following the Plan-Build-Self-Improve workflow.

## Required First Steps

### 1. Load Expertise
Before proceeding, read the following expertise files to load your mental model:

{for file in expertise_files.reads}
- `meta_agentic/expertise/{file}`
{endfor}

### 2. Validate Understanding
Before executing, validate your mental model against source of truth:

1. **Operator Validation**: For each operator you plan to use:
   - Verify it exists in `td_universal_parsed.json`
   - Check your expertise matches the actual spec

2. **Pattern Validation**: For each pattern you plan to apply:
   - Verify it has 3+ supporting examples
   - Check the operators in the pattern exist

3. **Problem Check**: Review `td_problems.yaml` for:
   - Known issues related to this task
   - Prevention strategies to incorporate

If validation fails:
- Do NOT proceed with incorrect assumptions
- Log discrepancy to `td_problems.yaml`
- Request clarification or use safer approach

## Task Execution

{task_specific_instructions}

### Anti-Hallucination Rules
- [ ] Every operator mentioned exists in source of truth
- [ ] Every parameter name/value is verified
- [ ] Every connection type is valid
- [ ] No assumptions beyond loaded expertise

## Output Format

```yaml
result:
  status: "success|partial|failed"
  output: "Task output here"

actions_taken:
  - action: "What was done"
    result: "What happened"

new_findings:
  - finding: "What was learned"
    type: "pattern|gotcha|correction"
    validated: true|false

errors:
  - error: "What went wrong"
    root_cause: "Why (not symptom)"
```

## Self-Improvement (Required)

After completing the task, update expertise if you discovered:

1. **New Pattern** (validated):
```yaml
file: "td_network_patterns.yaml"
update:
  path: "workflows.{new_pattern_name}"
  content:
    description: "..."
    confidence: 0.60  # Initial confidence
    example_count: N
    validated: true
  validation:
    source: "{task_id}"
    timestamp: "{ISO timestamp}"
```

2. **Parameter Pattern**:
```yaml
file: "td_parameters.yaml"
update:
  path: "parameters.{family}.{op_type}.{param_name}"
  content:
    observed_values:
      "{value}": { count: +1, contexts: [...] }
```

3. **Problem Encountered**:
```yaml
file: "td_problems.yaml"
update:
  path: "problems.PROB-{id}"
  content:
    category: "..."
    description: "..."
    root_cause: "..."
    fix: "..."
    prevention: [...]
```

Only update with VALIDATED information from this task execution.
```

---

## Task Type Templates

### Summary Task
```
task_specific_instructions: |
  Generate an LLM-friendly summary for the provided network/operator/workflow.

  Steps:
  1. Load source data (semantic JSON, curator text)
  2. Identify network pattern from expertise
  3. Extract data flow and key operators
  4. Generate summary using appropriate template
  5. Validate summary against source (no hallucination)

  Output: Summary object with llm_summary, dataflow, key_ops, gotchas
```

### Build Task
```
task_specific_instructions: |
  Build a TouchDesigner network from the specification.

  Steps:
  1. Match to known working pattern if possible
  2. Validate all operators exist in registry
  3. Apply parameters from expertise or spec
  4. Validate connections are type-compatible
  5. Generate output (JSON, script, or .toe)

  Output: Network specification with validation result
```

### Validate Task
```
task_specific_instructions: |
  Validate a network specification against TD rules.

  Steps:
  1. Check all operator types exist
  2. Verify parameter names/values valid
  3. Confirm connection types compatible
  4. Check against known anti-patterns
  5. Report all issues with severity

  Output: Validation report with errors/warnings
```

### Reverse Engineer Task
```
task_specific_instructions: |
  Analyze TOEEXPAND output to learn file format.

  Steps:
  1. Survey directory structure
  2. Analyze target file type
  3. Document observed patterns
  4. Round-trip validate understanding
  5. Update format expertise

  Output: Format findings with validation status
```

## LLM-Agnostic Design

This prompt works across different LLMs by:
- Using simple `{variable}` placeholders
- Outputting strict YAML (not free-form)
- Including explicit validation checkpoints
- Avoiding model-specific syntax

## Example Usage

**Input:**
```yaml
task_type: "summary"
task_description: "Generate summary for audio-reactive network"
target_operators: ["audiofilein", "analyze", "beat"]
expertise_files:
  reads: ["td_operators.yaml", "td_network_patterns.yaml"]
  writes: ["td_network_patterns.yaml"]
```

**Generated prompt would include:**
- Role as summary expert
- Instructions to load td_operators.yaml and td_network_patterns.yaml
- Steps for summary generation
- Anti-hallucination checks
- Self-improvement instructions for td_network_patterns.yaml

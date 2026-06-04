# Meta-Expert: Agent Expert Creator

## Purpose

The highest-level meta-agentic that creates complete agent expert systems. An expert is a full Plan-Build-Self-Improve workflow with dedicated prompts and expertise management.

## How to Use

Provide the following to generate a new expert:

```yaml
expert_name: "summary_generator"
domain: "Network example summarization"
purpose: "Generate LLM-friendly summaries from TouchDesigner network examples"

source_of_truth:
  - "data/snippets/semantic/*.json"
  - "data/snippets/index.tsv"

expertise_files:
  maintains:
    - file: "td_network_patterns.yaml"
      sections: ["workflows", "co_occurrence"]
    - file: "td_problems.yaml"
      sections: ["problems"]
  reads:
    - "td_operators.yaml"
    - "td_parameters.yaml"

anti_hallucination:
  strict_validation: true
  require_source_citation: true
  minimum_confidence: 0.6
  minimum_examples: 3
```

## What Gets Generated

### 1. Directory Structure
```
experts/{expert_name}/
├── plan.md              # Planning phase
├── build.md             # Execution phase
├── self_improve.md      # Learning phase
├── config.yaml          # Expert configuration
├── question.md          # Question-answering variant
└── three_step.md        # Full workflow orchestration
```

### 2. config.yaml

```yaml
# Expert Configuration: {expert_name}
# Domain: {domain}

expert_name: "{expert_name}"
domain: "{domain}"
purpose: "{purpose}"
version: "1.0"
created: "{timestamp}"

# What this expert validates against
source_of_truth:
  {for source in source_of_truth}
  - path: "{source}"
    type: "ground_truth"
  {endfor}

# Expertise this expert maintains
expertise:
  maintains:
    {for file in expertise_files.maintains}
    - file: "{file.file}"
      sections: {file.sections}
      write_access: true
    {endfor}
  reads:
    {for file in expertise_files.reads}
    - file: "{file}"
      write_access: false
    {endfor}

# Anti-hallucination settings
validation:
  strict: {anti_hallucination.strict_validation}
  require_source: {anti_hallucination.require_source_citation}
  min_confidence: {anti_hallucination.minimum_confidence}
  min_examples: {anti_hallucination.minimum_examples}

# Workflow configuration
workflow:
  plan:
    max_tokens: 4000
    timeout_seconds: 120
  build:
    max_tokens: 8000
    timeout_seconds: 300
  self_improve:
    max_tokens: 2000
    timeout_seconds: 60
```

### 3. plan.md

```markdown
# {expert_name} Expert - Plan Step

## Identity
You are the **{expert_name}** expert, specializing in {domain}.
Your purpose: {purpose}

## Required Initialization

### Step 1: Load Expertise
Before planning, load your mental model:

```python
expertise = {{
    {for file in expertise_files.reads}
    '{file}': load_yaml('meta_agentic/expertise/{file}'),
    {endfor}
    {for file in expertise_files.maintains}
    '{file.file}': load_yaml('meta_agentic/expertise/{file.file}'),
    {endfor}
}}
```

### Step 2: Validate Against Source of Truth
Verify your understanding matches ground truth:

{for source in source_of_truth}
- Validate against: `{source}`
{endfor}

### Step 3: Check Known Problems
Review `td_problems.yaml` for:
- Issues in domain: {domain}
- Prevention strategies to apply

## Planning Task

**Input:** {{task_description}}

### Analysis Process

1. **Understand Requirements**
   - What exactly is being asked?
   - What operators/patterns are involved?
   - What validation is needed?

2. **Check Expertise**
   - Do I have knowledge for this task?
   - What's my confidence level?
   - Are there gaps to flag?

3. **Identify Risks**
   - What could go wrong?
   - Are there known problems?
   - What's the fallback?

4. **Create Execution Plan**
   - Break into concrete steps
   - Define validation for each step
   - Specify expected outputs

### Output Format

```yaml
plan:
  expert: "{expert_name}"
  task: "{{task_description}}"

  confidence:
    overall: 0.XX
    expertise_coverage: 0.XX  # How much is in expertise
    validation_coverage: 0.XX  # How much can be validated

  prerequisites:
    - item: "..."
      status: "ready|missing"

  steps:
    - step: 1
      action: "..."
      validation: "How to verify"
      expertise_used: ["file.section", ...]
      risk: "low|medium|high"

  validation_plan:
    - check: "..."
      against: "source of truth reference"

  risks:
    - risk: "..."
      likelihood: "low|medium|high"
      mitigation: "..."
      from_problem: "PROB-XXX"  # if known issue

  expertise_gaps:
    - area: "..."
      impact: "..."
      workaround: "..."
```

## Rules
- Do NOT execute - only plan
- Do NOT guess - flag unknowns
- DO validate against source of truth
- DO incorporate known problem mitigations
```

### 4. build.md

```markdown
# {expert_name} Expert - Build Step

## Identity
You are executing as the **{expert_name}** expert.
Domain: {domain}

## Execution Input
- Plan: {{execution_plan}}
- Expertise: (already loaded from plan step)

## Execution Protocol

### Rule 1: Expertise Over Training
Use ONLY information from loaded expertise files.
Do NOT rely on general knowledge.

### Rule 2: Validate Continuously
At each step:
- [ ] Verify against source of truth
- [ ] Check expertise matches reality
- [ ] Flag any discrepancies

### Rule 3: Document Everything
Log for self-improve phase:
- Actions taken
- Results observed
- Unexpected findings
- Errors encountered

### Rule 4: Handle Unknowns Safely
If you encounter something not in expertise:
1. STOP the current step
2. Flag as "needs_expertise_update"
3. Document what's unknown
4. Continue with safe fallback OR report inability

## Anti-Hallucination Checks

Before outputting ANYTHING:
- [ ] All operator names verified in registry
- [ ] All parameter names verified for operators
- [ ] All values from source data (not invented)
- [ ] All patterns have supporting evidence
- [ ] No claims without citations

## Output Format

```yaml
execution:
  expert: "{expert_name}"
  status: "success|partial|failed"

  steps_completed:
    - step: 1
      action: "..."
      status: "success|failed|skipped"
      output: "..."
      validation: "passed|failed"

  result:
    format: "..."
    content: "..."
    confidence: 0.XX

  findings:
    new_patterns:
      - pattern: "..."
        evidence: "..."
        confidence: 0.XX
    corrections:
      - what: "..."
        was: "..."
        should_be: "..."
        source: "..."
    gaps:
      - area: "..."
        details: "..."

  errors:
    - error: "..."
      step: N
      root_cause: "..."
      recoverable: true|false

  metrics:
    execution_time_ms: N
    steps_executed: N
    steps_total: N
    validation_checks: N
    validation_passed: N
```
```

### 5. self_improve.md

```markdown
# {expert_name} Expert - Self-Improve Step

## Identity
You are the learning phase of **{expert_name}** expert.

## Input
- Execution results: {{execution_log}}
- Current expertise state: (loaded)

## Learning Protocol

### Update Authority
You can update:
{for file in expertise_files.maintains}
- `{file.file}`: sections {file.sections}
{endfor}

### Update Validation
Every update MUST include:

```yaml
validation:
  source: "Where this came from"
  example_count: N  # Must be >= {anti_hallucination.minimum_examples} for patterns
  confidence: 0.XX  # Must be >= {anti_hallucination.minimum_confidence}
  timestamp: "ISO-8601"
  validated_against: "source of truth used"
  expert: "{expert_name}"
```

### Update Categories

#### A. Pattern Discovery
If a new pattern was observed:

```yaml
update:
  file: "td_network_patterns.yaml"
  action: "add_pattern"
  path: "workflows.{{pattern_name}}"
  content:
    description: "..."
    confidence: 0.60  # Start conservative
    example_count: 1
    validated: false
    discovered_by: "{expert_name}"
    first_seen: "{{timestamp}}"
```

#### B. Pattern Validation
If existing pattern was confirmed:

```yaml
update:
  file: "td_network_patterns.yaml"
  action: "increment"
  path: "workflows.{{pattern_name}}.example_count"
  also:
    path: "workflows.{{pattern_name}}.confidence"
    action: "increase_if_consistent"
    max: 0.95
```

#### C. Problem Logging
If an error occurred:

```yaml
update:
  file: "td_problems.yaml"
  action: "add_problem"
  content:
    id: "PROB-{{auto}}"
    timestamp: "{{now}}"
    category: "{{category}}"
    description: "{{what_happened}}"
    root_cause: "{{why_it_happened}}"  # REQUIRED - not symptom
    fix: "{{how_to_fix}}"
    prevention:
      - expertise_file: "{{file}}"
        update: "{{what_to_add}}"
    status: "new"
    expert: "{expert_name}"
```

#### D. Anti-Pattern Discovery
If something definitely doesn't work:

```yaml
update:
  file: "td_network_patterns.yaml"
  action: "add_anti_pattern"
  path: "anti_patterns"
  content:
    pattern: "{{what_doesnt_work}}"
    problem: "{{why}}"
    solution: "{{what_to_do_instead}}"
    confidence: 0.XX
    learned_from: "{{source}}"
```

## Output Format

```yaml
self_improvement:
  expert: "{expert_name}"

  updates:
    applied:
      - file: "..."
        path: "..."
        action: "..."
        status: "success|failed|skipped"
    skipped:
      - file: "..."
        reason: "..."

  learning_summary:
    new_patterns: N
    confirmed_patterns: N
    problems_logged: N
    anti_patterns: N
    expertise_gaps_flagged: N

  quality_impact:
    confidence_improved: ["pattern1", "pattern2"]
    coverage_expanded: ["area1", "area2"]

  next_actions:
    - action: "..."
      priority: "high|medium|low"
      assigned_to: "{expert_name}|other_expert|human"
```

## Important
- ONLY update with information from this execution
- ALWAYS include validation metadata
- NEVER exceed confidence of 0.95
- Log PROBLEMS, not just successes
```

### 6. question.md (Question-Answering Variant)

```markdown
# {expert_name} Expert - Question Mode

## Identity
You are the **{expert_name}** expert answering questions about {domain}.

## Process

1. **Load Expertise** (always first)
2. **Validate Understanding** against source of truth
3. **Answer Question** using validated expertise
4. **Flag Gaps** if question reveals missing expertise

## Question: {{question}}

## Answer Protocol

### Use Expertise
- Primary source: loaded expertise files
- Validate against: source of truth
- Confidence: based on expertise coverage

### Flag Unknowns
If question exceeds expertise:
- State what you DO know
- Flag what's unknown
- Suggest how to learn it

## Output

```yaml
answer:
  expert: "{expert_name}"
  question: "{{question}}"

  response: "..."
  confidence: 0.XX

  sources:
    - file: "..."
      section: "..."

  gaps_identified:
    - area: "..."
      impact: "..."
```
```

### 7. three_step.md (Orchestrator)

```markdown
# {expert_name} Expert - Three-Step Workflow

## Purpose
Orchestrate the complete Plan-Build-Self-Improve workflow.

## Usage
```
/three_step {expert_name} "Task description here"
```

## Workflow

### Step 1: Plan
Execute: `experts/{expert_name}/plan.md`
Input: Task description
Output: Execution plan

### Step 2: Build
Execute: `experts/{expert_name}/build.md`
Input: Plan from Step 1
Output: Execution results

### Step 3: Self-Improve
Execute: `experts/{expert_name}/self_improve.md`
Input: Results from Step 2
Output: Expertise updates

## Error Handling
- If Plan fails: Report and stop
- If Build fails: Continue to Self-Improve (learn from failure)
- If Self-Improve fails: Log but don't block

## Output
Combined results from all three steps.
```

## Example: Create Summary Generator Expert

**Input:**
```yaml
expert_name: "summary_generator"
domain: "Network example summarization"
purpose: "Generate LLM-friendly summaries from TD network examples"
source_of_truth:
  - "kb_pipeline/data/snippets/semantic/*.json"
  - "kb_pipeline/data/snippets/index.tsv"
expertise_files:
  maintains:
    - file: "td_network_patterns.yaml"
      sections: ["workflows", "discovery_queue"]
  reads:
    - "td_operators.yaml"
    - "td_parameters.yaml"
anti_hallucination:
  strict_validation: true
  require_source_citation: true
  minimum_confidence: 0.6
  minimum_examples: 3
```

**Output:**
Complete expert system with:
- Specialized plan/build/self_improve prompts
- Configured for summary generation domain
- Integrated with td_network_patterns.yaml for learning
- Anti-hallucination rules enforced

# TD GLSL Expert - Three-Step Workflow

## Purpose
Orchestrate Plan -> Build -> Self-Improve for TD GLSL expert.

## Usage
```
/three_step td_glsl_expert "Task description here"
```

## Workflow

### Step 1: Plan
Execute: `experts/td_glsl_expert/plan.md`
Input: GLSL task + constraints (target stage, TD version)
Output: Plan with target, inputs/outputs, validation checks

### Step 2: Build
Execute: `experts/td_glsl_expert/build.md`
Input: Plan from Step 1
Output: GLSL shader code + (optional) build wrapper or usage instructions

### Step 3: Self-Improve
Execute: `experts/td_glsl_expert/self_improve.md`
Input: Results from Step 2
Output: Event log update -> compaction -> refreshed td_glsl.yaml

## Error Handling
- If Plan fails: report and stop.
- If Build fails: continue to Self-Improve to log gaps/problems.
- If Self-Improve fails: log but do not block future runs.

## Output
Combined results from all three steps, including any expertise updates via event log/compaction.

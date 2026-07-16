# Network Builder Expert - Three-Step Workflow

## Purpose
Orchestrate Plan -> Build -> Self-Improve for network_builder.

## Usage
```
/three_step network_builder "Task description here"
```

## Workflow

### Step 1: Plan
Execute: `experts/network_builder/plan.md`
Input: Task description + constraints (TD version, allowed ops)
Output: Execution plan with target_mode (toe|tox|text_dat|instructions)

### Step 2: Build
Execute: `experts/network_builder/build.md`
Input: Plan from Step 1
Output: Validated spec + artifact chosen by intent (whole project → .toe, reusable component → .tox); Text DAT / instructions only if a build errors

### Step 3: Self-Improve
Execute: `experts/network_builder/self_improve.md`
Input: Results from Step 2
Output: Structured lesson report (no automated event log/compaction in this release)

## Error Handling
- If Plan fails: report and stop.
- If Build fails: continue to Self-Improve to log problems and gaps.
- If Self-Improve fails: log but don't block future runs.

## Output
Combined results from all three steps, including validation/build status and any expertise updates (via event log).

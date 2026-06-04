# Improvements Backlog

**Created By**: CLIFF
**Date**: 2024-12-23
**Status**: Post-BUG-001 priorities

---

## Quick Wins (Do First)

### 1. Smoke Test Gate
- **Owner**: DAMON
- **Effort**: Low
- **Impact**: High
- **Description**: Before any commit, Prompt 01 (single noise CHOP) must pass. Git hook or CI step.

### 2. Fast Path for Simple Prompts
- **Owner**: PETER
- **Effort**: Medium
- **Impact**: High
- **Description**: Skip creative/cg agents for basic builds. Full 5-agent chain only for complex/artistic prompts. Orchestrator decides based on prompt complexity.

### 3. Automated Test Runner
- **Owner**: QUEENIE + DAMON
- **Effort**: Medium
- **Impact**: High
- **Description**: Script that runs all 50 prompts programmatically, captures file sizes and TD console output, generates pass/fail report without manual testing.

---

## Larger Improvements

### 4. Pre-Collapse Validation
- **Owner**: TERRY
- **Effort**: High
- **Impact**: Very High
- **Description**: Validate generated .parm files against known-good spec BEFORE running toecollapse. Catch format errors at build time, not TD time.

### 5. Error Feedback Loop
- **Owner**: TERRY + KYLE
- **Effort**: High
- **Impact**: High
- **Description**: When TD rejects parameters, parse error → update KB mapping → enable auto-retry. Close the loop.

### 6. BASIC Mode Spec Documentation
- **Owner**: TERRY
- **Effort**: Medium
- **Impact**: High
- **Description**: Once BUG-001 is fixed, document the exact .parm file spec so future operators can be added without reverse-engineering.

---

## Workflow Improvements

### 7. Agent File Locking
- **Owner**: DAMON
- **Effort**: Low
- **Impact**: Medium
- **Description**: TEAM_INBOX.md race conditions. Consider per-agent files or numbered task queue.

---

## Priority Order (Post-BUG-001)

1. Smoke test gate (blocks bad commits)
2. BASIC mode spec doc (preserves TERRY's knowledge)
3. Fast path for simple prompts (better UX)
4. Automated test runner (faster QA)
5. Pre-collapse validation (catches errors early)
6. Error feedback loop (self-improving system)
7. Agent file locking (workflow polish)

---

*Backlog managed by CLIFF*

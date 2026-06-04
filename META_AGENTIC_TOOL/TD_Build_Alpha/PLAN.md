# TD_Build_Alpha Implementation Plan

## Overview

This document outlines the plan for the TD_Build_Alpha release, including:
1. Claude AI documentation package
2. Alpha demo preparation
3. Bug fixes for working demo

---

## Completed Documentation

Created comprehensive documentation for Claude AI team in `TD_Build_Alpha/claude_ai_docs/`:

| Document | Content |
|----------|---------|
| 01_SYSTEM_PROMPTS.md | All 8 expert agent prompts |
| 02_TOOL_DEFINITIONS.md | Tools per agent, KB methods |
| 03_HANDOFF_SCHEMA.md | Blackboard sections, input/output formats |
| 04_KB_QUERY_INTERFACE.md | KB API, query functions, validation |
| 05_EXAMPLES.md | Teardrop success, failed run examples |
| 06_SELF_IMPROVEMENT.md | Plan→Build→Self-Improve cycle |
| 07_VERIFICATION.md | Critic checklist, completion triggers |
| 08_PRACTICAL.md | Context limits, state, hardcoded values |
| 09_INTEGRATION.md | Pre-build validation pipeline |
| README.md | Index and quick start |

---

## Alpha Demo Plan Summary

### Day 1 (December 19) - Bug Fixing

**Morning:**
1. Jake: Get audioAnalysis channel names from TD
2. Claude: Fix expression paths in build_teardrop.py
3. Claude: Add display/window output

**Afternoon:**
4. Jake: Test in TouchDesigner
5. Claude: Fix issues found

**Evening (Optional):**
6. Add GPU particles
7. Add glitch effects

### Day 2 (December 20) - Demo

8. End-to-end test
9. Documentation polish
10. Demo to selected users

---

## Critical Blockers

| Blocker | Owner | Action |
|---------|-------|--------|
| Audio channel names unknown | Jake | Open TD, check audioAnalysis |
| Expression paths wrong | Claude | Update after Jake provides names |
| No display window | Claude | Add windowCOMP to builder |

---

## Success Criteria

**Minimum:**
- TOE opens without errors
- Audio analysis shows activity
- Visuals render
- Some audio reactivity

**Good:**
- Multiple visual layers
- Smooth audio response
- Organic feedback feel

**Great:**
- Particles on beats
- Glitch on highs
- Emotional arc visible

---

## Files Created

```
TD_Build_Alpha/
├── PLAN.md                    # This file
├── ALPHA_DEMO_PLAN.md         # Detailed day-by-day plan
└── claude_ai_docs/
    ├── README.md
    ├── 01_SYSTEM_PROMPTS.md
    ├── 02_TOOL_DEFINITIONS.md
    ├── 03_HANDOFF_SCHEMA.md
    ├── 04_KB_QUERY_INTERFACE.md
    ├── 05_EXAMPLES.md
    ├── 06_SELF_IMPROVEMENT.md
    ├── 07_VERIFICATION.md
    ├── 08_PRACTICAL.md
    └── 09_INTEGRATION.md
```

---

## Next Steps

1. Review this plan
2. Tomorrow morning: Jake provides audio channel names
3. Claude fixes expressions and adds display
4. Test cycle begins
5. Demo by end of Dec 20

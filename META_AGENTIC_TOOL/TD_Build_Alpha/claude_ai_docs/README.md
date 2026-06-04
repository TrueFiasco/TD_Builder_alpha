# Claude AI Documentation - META_AGENTIC_TOOL

This documentation package provides comprehensive technical details for the Claude AI team reviewing the META_AGENTIC_TOOL system for TouchDesigner TOX/TOE file generation.

## Document Index

| Doc | Title | Description |
|-----|-------|-------------|
| 01 | [System Prompts](01_SYSTEM_PROMPTS.md) | All agent prompts and instructions |
| 02 | [Tool Definitions](02_TOOL_DEFINITIONS.md) | Tools available to each agent |
| 03 | [Handoff Schema](03_HANDOFF_SCHEMA.md) | Input/output formats between agents |
| 04 | [KB Query Interface](04_KB_QUERY_INTERFACE.md) | Knowledge base API documentation |
| 05 | [Examples](05_EXAMPLES.md) | Successful and failed run examples |
| 06 | [Self-Improvement](06_SELF_IMPROVEMENT.md) | Learning and meta-agent logic |
| 07 | [Verification](07_VERIFICATION.md) | Completion criteria and critic logic |
| 08 | [Practical](08_PRACTICAL.md) | Context limits, state, hardcoded values |
| 09 | [Integration](09_INTEGRATION.md) | Pre-build validation pipeline |
| 10 | [Technical Deep Dive](10_TECHNICAL_DEEP_DIVE.md) | How it actually works (Q&A format) |

## Quick Start

### System Architecture

```
User Prompt
    ↓
[Orchestrator] ─── spawns ──→ [Task Agents]
    │                              │
    ├── creative_expert ───────────┤
    ├── cg_expert ─────────────────┤
    ├── td_designer ───────────────┤
    ├── critic ────────────────────┤
    └── network_builder ───────────┘
                                   │
                              [Blackboard]
                              (7 sections)
                                   │
                                   ↓
                              [TOE File]
```

### Key Concepts

1. **Blackboard Pattern**: Central state with 7 sections (Requirements → Build Artifacts)
2. **Expert Cycle**: Plan → Build → Self-Improve for each agent
3. **Critic Gate**: Quality threshold (0.65) with max 3 revision cycles
4. **KB Validation**: Anti-hallucination checks against 686 operator schemas

### Agent Types

| Agent | Purpose | Output Section |
|-------|---------|----------------|
| creative_expert | Mood, colors, motion | §2 Creative Vision |
| cg_expert | Technical approach | §3 Technical Approach |
| td_designer | Network spec | §5 Network Design |
| critic | Quality review | §6 Validation History |
| network_builder | TOE file | §7 Build Artifacts |

## Known Issues (Alpha Status)

1. **Audio channel names guessed** - Need TD verification
2. **Expression paths unvalidated** - Require runtime check
3. **Display operators sometimes missing** - Manual verification needed

## File Locations

```
meta_agentic/
├── experts/           # Agent prompts (plan.md, build.md, self_improve.md)
├── expertise/         # KB YAML files (278 palette, 600+ operators)
├── execution/         # Python execution layer
│   ├── blackboard.py  # State management
│   ├── kb_query.py    # KB interface
│   ├── expert_executor.py  # Agent orchestration
│   └── strategy_runner.py  # V2-V6 workflow strategies
└── CLAUDE.md          # Agent instructions
```

## Contact

Project lead: Jake (user)
AI lead: Claude Code (Claude Opus 4.5)

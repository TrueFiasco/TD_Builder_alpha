# Agent Coordination Plan
*Updated: 2025-12-19*

## Current State

### PHASE 6 COMPLETE - Execution Layer + Subagent Orchestration

**Completed 2025-12-18/19:**

### Execution Layer (`meta_agentic/execution/`)
| Module | Purpose | Status |
|--------|---------|--------|
| `strategy_runner.py` | V2-V6 workflow strategies | Working |
| `blackboard.py` | Central state management (7 sections) | Working |
| `expert_executor.py` | Expert prompt execution | Working (8 experts) |
| `kb_query.py` | Knowledge base queries | Working |
| `expert_pool.py` | Palette + operator expertise | Working |
| `metrics.py` | Token/quality tracking | Working |

### Registered Experts (8 total)
| Expert | Prompts | KB Access |
|--------|---------|-----------|
| creative_expert | plan/build/self_improve | creative_vision.yaml |
| cg_expert | plan/build/self_improve | cg_concepts.yaml, td_operators.yaml |
| td_designer | plan/build/self_improve | operators, patterns, parameters |
| td_glsl_expert | plan/build/self_improve | td_glsl.yaml |
| td_python_expert | plan/build/self_improve | td_python.yaml |
| network_builder | plan/build/self_improve | network_building, file_formats |
| critic | plan/build | critique_patterns.yaml |
| summary_generator | plan/build/self_improve | network_design, artifacts |

### Knowledge Base
| File | Entries | Query Method |
|------|---------|--------------|
| palette_semantic_catalog.yaml | 278 components | `query_palette_catalog()` |
| td_operators.yaml | 600+ operators | `query_operators()` |
| td_network_patterns.yaml | 11 patterns | `query_patterns()` |
| td_glsl.yaml | GLSL expertise | `query_glsl()` |
| td_python.yaml | Python expertise | `load_expertise()` |

### Workflow Strategies
| Strategy | Description | Status |
|----------|-------------|--------|
| V2 | Linear workflow with KB query | Working |
| V3 | Evolutionary with variants | Implemented |
| V4 | Blackboard-centric | Implemented |
| V5 | Deep refinement + convergence | Implemented |
| V6 | Unified (combines all) | Implemented |

### Subagent Execution (NEW)
- **Approach B**: Claude Code orchestrates via Task agents
- Experts spawned as subagents, not API calls
- KB queried via Python helpers
- Results collected and composed

### TOX/TOE Building
| Builder | Purpose | Status |
|---------|---------|--------|
| `tox_builder/builder_v4.py` | Base TOE builder | Working |
| `build_teardrop.py` | Palette embedding | Working (needs fixes) |
| `build_from_expanded.py` | Raw file copy approach | Working |

---

## KNOWN ISSUES (2025-12-19)

### Audio Reactivity Not Working
- **Symptom**: Teardrop TOE opens but doesn't react to audio
- **Cause**: Expressions reference wrong paths (`op('audio/out1')['low']`)
- **Fix needed**: Get actual audioAnalysis output channel names

### Visual Chain Not Displaying
- **Symptom**: Nothing renders on screen
- **Cause**: Operators not properly connected, no display window
- **Fix needed**: Verify connections, add window COMP

### Builder Agent Gap
- **Symptom**: Builder outputs YAML, not ToeBuilder-compatible specs
- **Cause**: No translator between TD Designer YAML and ToeBuilder format
- **Fix needed**: Create proper spec translator

---

## ALPHA DEMO BLOCKERS

| Blocker | Owner | Priority |
|---------|-------|----------|
| Get audioAnalysis channel names | User | P0 |
| Fix expression paths | Claude | P0 |
| Add display/window | Claude | P0 |
| Verify operator connections | Claude | P1 |
| Add particle system | Claude | P2 |
| Add glitch layer | Claude | P2 |

---

## Tomorrow's Plan (2025-12-19)

### Morning
1. User: Open audioAnalysis, document actual output paths
2. Claude: Fix expressions in build_teardrop.py
3. Test: Verify audio reactivity works

### Afternoon
1. Add display/window COMP
2. Add GPU particles (from palette or manual)
3. Add glitch layer (RGB split)
4. Test full visual chain

### Evening
1. Polish and tune parameters
2. Create demo recording
3. Document what works vs. what's stubbed

---

*Last updated: 2025-12-19 00:30*

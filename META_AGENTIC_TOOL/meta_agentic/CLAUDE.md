# CLAUDE.md — meta_agentic/

The multi-agent strategy runner, the per-expert prompts, and the "self-improving" expertise system. Honest scope: this directory does what it does on the **Python-only path**. None of it is reachable from Claude Desktop today (active MCP is `../../td-mcp/server.py`; only the inactive `../mcp_server.py` exposes `spawn_expert`, and even that is one-shot, not orchestrated).

Cross-reference: [`../CLAUDE.md`](../CLAUDE.md) for the parent context. [`../../td-builder-orientation.md`](../../td-builder-orientation.md) Q1, Q2, Q7 for the agent inventory, orchestration flow, and prompt locations. [`../../problems.md`](../../problems.md) for blockers.

---

## What this directory is

```
meta_agentic/
├── execution/          # Strategy runner, expert executor, blackboard, KB query, LLM wrapper
├── experts/            # Per-expert prompt directories (plan/build/self_improve.md)
├── expertise/          # YAML "working memory" (read by kb_query, the only retrieval path that runs)
├── compaction/         # Event-log → state YAML compactor
├── concurrency/        # File locking + expertise merging (used only by compaction)
├── history/            # Append-only JSONL event log (manual writes, not runtime-driven)
├── meta/               # Compacted state YAML + 4 hand-written meta-prompt docs
├── tests/              # Strategy/orchestration tests (mostly mock mode)
├── tools/              # Empty package (only __init__.py)
├── validation/         # Empty package (only __init__.py)
├── knowledge/          # Empty directory
├── notes/              # One file: 2025-12-17_palette_embedding.md
└── output/             # Run outputs from test_ruth/test_creative_orchestration etc.
```

The two CLAUDE-md siblings worth knowing:
- [`COORDINATION.md`](COORDINATION.md) — phase-completion state circa 2025-12-19.
- [`INTEROP_AND_POLICY.md`](INTEROP_AND_POLICY.md) — the canonical spec for the event-log+YAML-state+output-policy pattern. **Better-written and more accurate than this CLAUDE.md historically was.** Read it after this one.

---

## What actually runs

### Entry point

[`run_strategy(name, prompt, config)` at execution/strategy_runner.py:2386](execution/strategy_runner.py:2386). Picks one of 6 registered strategies (`v0`–`v6`), creates a `Blackboard`, writes the prompt to `§1_REQUIREMENTS`, calls `strategy.execute_workflow(...)`. Returns a `BuildResult` with `.toe` path on success.

**No MCP tool exposes this.** It's a Python-only API. The `spawn_expert` tool in the inactive MCP runs *one* expert one-shot — it doesn't drive a strategy.

### Strategy flow (V2, the reference)

```
prompt → §1_REQUIREMENTS
   ↓
KB Query (query_knowledge_base_comprehensive)        ← KEYWORD IF-LADDER, NOT GraphRAG
   ↓
Creative Expert (plan→build→self_improve)            ← 3 LLM calls
   ↓ critic.execute_step("build")
   ↓ if score < quality_targets.creative (0.85):    ← LOOP up to max_iterations
   ↓     re-run Creative Expert
   ↓
CG Expert (plan→build→self_improve) → critic loop
   ↓
TD Designer → critic loop
   ↓
Network Builder (one-shot, no critic)
   ↓
toe_builder_bridge.build_toe_from_design(network_design)
   ↓
.toe.dir + .toc  (toecollapse is manual)
```

V0–V6 differences are documented in [`../CLAUDE.md`](../CLAUDE.md) and [`../../td-builder-orientation.md`](../../td-builder-orientation.md) Q2. Short version: V0 is a stub, V2-V4 are copy-pasted siblings, V5 adds stretch goals + convergence, V6 adds variant spawning + persistent critic context + a phase-reopening hint that doesn't actually reopen phases.

### Per-expert plan→build→self_improve

[`ExpertExecutor.run_full_cycle()` at execution/expert_executor.py:362](execution/expert_executor.py:362) loads three `.md` files from `experts/<expert>/`, renders them with placeholder substitution, and sends them to the LLM via `AnthropicExecutor`.

**The system prompt is a hardcoded one-liner per expert** at [`EXPERT_ROLE_PROMPTS` (module-level in expert_executor.py)](execution/expert_executor.py), prepended before the rendered Markdown via `_build_system_prompt`. Covers all 8 canonical experts post-roster-cleanup. `ExpertPool._query_llm` reads from the same dict (H6 dedup) so GLSL/Python role text can't drift between the two callers.

### Inter-agent communication

Via [`Blackboard`](execution/blackboard.py) — a 7-section state object. Section IDs: `§1_REQUIREMENTS`, `§2_CREATIVE_VISION`, `§3_TECHNICAL_APPROACH`, `§4_AVAILABLE_RESOURCES`, `§5_NETWORK_DESIGN`, `§6_VALIDATION_HISTORY`, `§7_BUILD_ARTIFACTS`. Each agent reads sections it cares about (mapping at [blackboard.py:330-356](execution/blackboard.py:330)) and writes to a section the next agent reads. **No direct agent-to-agent calls.**

`§6_VALIDATION_HISTORY` is enumerated but never written by any active code.

---

## Registered experts

Source of truth: [`EXPERT_IDS` at experts/__init__.py](experts/__init__.py). **8 IDs registered** (canonical roster), 5 actually invoked by V2-V6 phase order, all 8 have proper role strings in `EXPERT_ROLE_PROMPTS`. None unreachable.

| Expert | Folder | Used by V2-V6? | Notes |
|---|---|:-:|---|
| creative_expert | [creative_expert/](experts/creative_expert/) | yes | |
| cg_expert | [cg_expert/](experts/cg_expert/) | yes | |
| td_designer | [td_designer/](experts/td_designer/) | yes | |
| network_builder | [network_builder/](experts/network_builder/) | yes | Has `question.md`, `three_step.md` extras |
| critic | [critic/](experts/critic/) | yes (every phase) | Special YAML schema; only `build.md` invoked; loop quality gate |
| td_glsl_expert | [td_glsl_expert/](experts/td_glsl_expert/) | no | Reachable via `spawn_expert` MCP tool. Has `question.md`, `three_step.md` extras |
| td_python_expert | [td_python_expert/](experts/td_python_expert/) | no | Reachable via `spawn_expert` MCP tool |
| ui_expert | [ui_expert/](experts/ui_expert/) | no | Reachable via `spawn_expert` MCP tool |

Five previously-registered experts moved to `archive/experts_unused/` in the H1/M20/M21 cleanup: `summary_generator`, `format_reverse_engineer`, `creative_orchestrator`, `claude_code_orchestrator`, `network_editor_expert`. The unique reverse-engineering content from `format_reverse_engineer/LEARNINGS.md` was preserved at `unified_system/docs/TOE_FORMAT_LEARNINGS.md`.

---

## "Self-improving" — what's true

The doc-y claim is that experts learn over time by writing back to `expertise/*.yaml`. Reality:

- **The infrastructure exists and works.** [`compaction/compact_expertise.py`](compaction/compact_expertise.py) defines `EventSchema`, `append_event()`, `compact_to_state()`. [`concurrency/file_lock.py`](concurrency/file_lock.py) provides `FileLock` for safe concurrent writes. [`history/expertise_events.jsonl`](history/expertise_events.jsonl) and [`meta/expertise_state.yaml`](meta/expertise_state.yaml) exist.
- **The runtime never calls it.** Grep `append_event\|FileLock(` in [`execution/`](execution/) and [`experts/`](experts/) returns nothing. Strategy runs do not produce events. The 6 events in `expertise_events.jsonl` were typed by humans/external Claude sessions (`agent_id` values: `codex`, `claude-opus`, `claude-sonnet`) — not generated by `self_improve.md` step output.
- **`should_iterate` from self-improve is silently ignored** ([expert_executor.py:443-452](execution/expert_executor.py:443)). The expert can return `recommendation.action = "iterate"`; V2-V6 phase loops only branch on the critic score, not on this hint. So the per-expert "I want to refine my own output" signal is dropped.
- **Anti-hallucination rules are aspirational.** [`CLAUDE.md` history](CLAUDE.md) and [`INTEROP_AND_POLICY.md`](INTEROP_AND_POLICY.md) describe the "Source of Truth Hierarchy" (operator specs → snippets → curator summaries → expertise YAMLs). No runtime code validates parameter names against `td_universal_parsed.json` before emitting them. Hallucination resistance is by-instruction-only.

The system is set up to be self-improving but isn't currently. If you want to make it real, the changes are: (1) have `ExpertExecutor.execute_step` call `append_event()` on every step's outcome, (2) have the V2-V6 phase loop honour `should_iterate`, (3) wire `validate_output()` to the operator registry instead of the current generic checks. The compaction script and lock plumbing don't need any work.

---

## Retrieval — read this carefully

[`execution/kb_query.py:KnowledgeBase`](execution/kb_query.py) is the only "retrieval" the agents actually use. It's **YAML lookups with substring matching, not GraphRAG**.

[`execution/strategy_runner.py:query_knowledge_base_comprehensive`](execution/strategy_runner.py) (line 132-266) is what gets called once per strategy run. It's a 134-line if-ladder over hardcoded keyword lists:

```python
if any(kw in prompt_lower for kw in ["audio","sound","music","beat","pulse","heartbeat"]):
    audio_chops = kb.query_operators({"family": "CHOP", "purpose_contains": "audio"})
    ...
if any(kw in prompt_lower for kw in ["visual","particle","image","video","render","glow","light","projection"]):
    top_ops = kb.query_operators({"family": "TOP"})[:20]   # first 20 alphabetically
    ...
```

[`KnowledgeBase.semantic_search`](execution/kb_query.py:902) is a stub that returns `[]` with a `# TODO: Implement ChromaDB integration` comment.

The real GraphRAG stack — `UnifiedSearchAdapter`, `EnhancedHybridRetrieval`, ChromaDB at `../data/vector_db/`, the enhanced gpickle — exists at the parent level (see [`../CLAUDE.md`](../CLAUDE.md)) and is loaded by `mcp_server.py` at startup. The strategy runner does not import any of it.

**This is the single highest-leverage fix in the project.** See [`../../problems.md`](../../problems.md) B1/B2.

V6 has an `ExpertPool` ([execution/expert_pool.py](execution/expert_pool.py)) that injects "expert context" into `§4_AVAILABLE_RESOURCES` before the design phase. It uses *a different* hardcoded `system_prompts` dict at [expert_pool.py:496-512](execution/expert_pool.py:496) for GLSL/Python/Palette, with text that disagrees with `_build_system_prompt`'s entries for the same experts.

---

## Expertise YAML files

[`expertise/`](expertise/) holds 17 YAML files used as "working memory" (per [`INTEROP_AND_POLICY.md`](INTEROP_AND_POLICY.md): "expertise is working memory only" — sources of truth are in `kb_pipeline/data/`).

The ones the runtime actually reads (via `kb_query.load_expertise`):

| File | What it holds | Read by |
|---|---|---|
| `td_operators.yaml` | Operator schemas (mental model) | Most experts |
| `td_network_patterns.yaml` | Pattern templates (audio_reactive_visuals etc.) | strategy_runner keyword buckets |
| `td_glsl.yaml` | GLSL shader templates | strategy_runner if "shader/glsl/..." in prompt |
| `td_python.yaml` | Callback / extension templates | strategy_runner if "script/python/..." in prompt |
| `palette_semantic_catalog.yaml` | 278 palette components with relevance-scored search | `get_palette_recommendations_for_prompt` |
| `palette_expertise.yaml` | Palette integration strategies | `query_palette` |
| `creative_vision.yaml` | Mood/aesthetic vocabulary | creative_expert build (via blackboard YAML embedding) |
| `cg_concepts.yaml` | CG techniques | cg_expert |
| `critique_patterns.yaml` | Critic checklist | critic |
| `td_parameters.yaml`, `td_problems.yaml`, `td_file_formats.yaml`, `td_network_building.yaml`, `collaborative_workflow.yaml`, `orchestrator_patterns.yaml`, `prebuilt_solution_expert.yaml`, `td_operators_v2.yaml`, `td_operators_trimmed.yaml` | Various | Some loaded as raw YAML into the blackboard `expertise` slot for prompt injection |

These are hand-curated. They are NOT auto-generated from `kb_pipeline/data/wiki_docs/td_universal_parsed.json` and they CAN drift from it. The compaction script can refresh them from `meta/expertise_state.yaml`, but that requires events being written first (which the runtime doesn't do — see `Self-improving` above).

---

## Tests

| File | What it does | Useful? |
|---|---|---|
| [tests/test_creative_orchestration.py](tests/test_creative_orchestration.py) | Simulates the full 6-stage workflow with mock data, no API calls | Sanity check that the orchestration plumbing wires up |

The strategy-integration / per-strategy tests live one level up: `../test_strategy_integration.py` (skips LLM, uses cached YAML), `../test_ruth_v2.py` (real API, costs money), `../test_ruth_v0_v6.py` (real API across all strategies, costs more).

There is no test that asserts "given this prompt, the strategy runner produces a network containing operators X, Y, Z." Quality of generation is judged manually.

---

## Where to start changes

If you want to **make retrieval real**: replace the keyword if-ladder in [`execution/strategy_runner.py:query_knowledge_base_comprehensive`](execution/strategy_runner.py) (line 132-266) with calls into `../search/unified_search.UnifiedSearchAdapter.search(prompt, n_results=15)` and use the relationships it returns to populate `§4_AVAILABLE_RESOURCES`. The instance is already loaded by `mcp_server.py` at startup; you'd need to either share it via module-level singleton or load it lazily here. See [`../../problems.md`](../../problems.md) B1/B2.

If you want to **make self-improvement real**: in [`ExpertExecutor.execute_step`](execution/expert_executor.py) (line 315), after a successful step, call `compaction.append_event()` with the expert ID, the step name, and the relevant `§` content as evidence. Then in `run_full_cycle` (line 362), honour `should_iterate` by re-entering the expert cycle within the same phase loop.

If you want to **make the unused-by-V2 experts (`td_glsl_expert`, `td_python_expert`, `ui_expert`) actually fire from a strategy run**: extend the strategy runner's phase order. V2 currently goes Creative → CG → TD Designer → Network Builder; you'd add (e.g.) a GLSL phase between Design and Build that runs `td_glsl_expert` if the design contains `glslTOP` operators. None of the existing strategies branch on design content — they're all linear. (The three are already reachable individually via the inactive MCP server's `spawn_expert` tool.)

---

## Things to know that are not obvious

- **The canonical roster count is now 8** (post-cleanup), and `experts/__init__.py:EXPERT_IDS` is the single source of truth. `mcp_server.py:AVAILABLE_EXPERTS` matches it. `COORDINATION.md` is historical and may still say "8 Registered" by accident — that count is now correct again, but for different reasons than when COORDINATION.md was written.
- **`tools/__init__.py` and `validation/__init__.py` are empty packages.** They were stubbed out and nothing was added.
- **`knowledge/` directory is empty.** Was meant to hold something; doesn't.
- **`output/` accumulates run artefacts indefinitely.** Test scripts dump YAML/JSON here. No cleanup job. If `expertise_state.yaml` shows old `event_count`, it's because the only 6 events on disk are from human pastes weeks/months ago.
- **`meta/` has 4 meta-meta prompt files** (`meta_agent.md`, `meta_expert.md`, `meta_prompt.md`, `meta_skill.md`). They're hand-written design docs, not loaded by code.
- **`notes/` has one file** about palette embedding research, dated 2025-12-17.
- **`nul` exists** in this directory — a stray file from a Windows shell redirect that didn't recognize `nul` as the bit-bucket.
- **The "Mock Mode" execution mode mentioned in old docs** is when `LLMExecutor` is None — the framework runs without API calls. Useful for testing the orchestration plumbing. Set by passing `llm_executor=None` to `execute_expert()`.
- **The "Subagent Mode" execution mode mentioned in old docs** doesn't really exist as a separate mode — it refers to spawning experts as Claude Code Task agents from the inactive MCP server's `spawn_expert` tool, not anything in this directory.

---

## When you change things

- For **strategy or expert-prompt** changes: there's no automated test that catches regressions. Run `../test_ruth_v2.py` against a known prompt; eyeball the result. Costs an API call.
- For **kb_query / retrieval** changes: there's no test for `query_knowledge_base_comprehensive` either — write one if you change it. Compare the returned dict before/after on the same prompt.
- For **blackboard or orchestration plumbing** changes: `tests/test_creative_orchestration.py` is mock-mode and runs fast — does not catch real LLM behaviour but verifies the wiring.
- For **expertise YAML** changes: nothing breaks at import time even if a file is malformed (each `query_*` method has `try/except FileNotFoundError`). Validate by hand: `python -c "import yaml; yaml.safe_load(open('expertise/td_operators.yaml'))"`.
- If you add a new expert: register in `EXPERT_IDS` ([experts/__init__.py](experts/__init__.py)), add a role string to `EXPERT_ROLE_PROMPTS` (module-level in [execution/expert_executor.py](execution/expert_executor.py)), add the same id to `mcp_server.py:AVAILABLE_EXPERTS`, and create `experts/<name>/{plan,build,self_improve}.md` using the canonical step filenames (the loader at `execution/expert_executor.py:load_prompt` hardcodes `f"{step}.md"` and won't find non-standard names — that's how `creative_orchestrator` ended up unreachable before being archived).

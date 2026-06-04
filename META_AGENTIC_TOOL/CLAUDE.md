# CLAUDE.md — META_AGENTIC_TOOL

Honest orientation for working in this directory. Reflects the codebase as it actually is, not as the project plan intended. Cross-reference: [`../td-builder-orientation.md`](../td-builder-orientation.md), [`../problems.md`](../problems.md).

---

## What this directory is

`META_AGENTIC_TOOL/` holds three loosely coupled things that were built at different times:

1. **An "inactive" MCP server** ([`mcp_server.py`](mcp_server.py)) — 17 base tools + 19 TD Live tools, the most featureful MCP in the repo. **Claude Desktop is NOT wired to this.** See `Active vs. inactive servers` below.
2. **A multi-agent strategy runner** ([`meta_agentic/`](meta_agentic/)) — Python-only entry point (`run_strategy()`), no MCP tool exposes it. Implements V0–V6 strategies with critic-gated phase loops.
3. **The knowledge base** ([`data/`](data/)) — wiki docs, parsed snippet examples, ChromaDB vector store, enhanced graph pickle. Used by both servers and by the unified-system pipeline.

This directory is NOT self-contained. It depends on `../unified_system/` (parsers, validation, format converters), `../kb_pipeline/` (vector_db builder, hybrid retrieval), and `../Learn/OPSnippets/` (snippet sources).

---

## Active vs. inactive: read this first

Claude Desktop's MCP config (`%APPDATA%\Claude\claude_desktop_config.json`) points to **`../td-mcp/server.py` (13 tools)**, not to the [`mcp_server.py`](mcp_server.py) in this directory.

Implications:
- The 36 tools advertised here (per old docs and the `td_live_client.py` extension) are NOT visible to Claude Desktop.
- `spawn_expert`, `td_build_project`, `get_parameter_detail`, `td_compact_expertise`, `get_expert_prompt`, and the 19 TD-Live tools (`capture_top_output`, `create_td_node`, `execute_python_script`, etc.) all live in this server and are unreachable from chat.
- Switching is one config edit. Until then, work here only affects the strategy-runner Python path and direct-Python use.

---

## Layout

```
META_AGENTIC_TOOL/
├── mcp_server.py                  # Inactive MCP (36 tools)
├── td_live_client.py              # 19 live-TD tools, imported by mcp_server
├── search/unified_search.py       # UnifiedSearchAdapter (chroma + graph)
├── search_docs.py                 # TDDocSearch (sentence-transformers + chromadb)
├── unified_graph_query.py         # UnifiedGraphQuery (wiki graph + enhanced gpickle)
├── enhanced_graph_query.py        # EnhancedGraphQuery (the gpickle reader)
├── hybrid_search.py               # HybridGraphRAG (older, replaced by UnifiedSearchAdapter)
├── config.py                      # SearchConfig (paths, embedding provider, cache)
│
├── meta_agentic/                  # Multi-agent orchestration (Python-only, no MCP entry)
│   ├── execution/
│   │   ├── strategy_runner.py     # V0-V6 strategies, run_strategy()
│   │   ├── expert_executor.py     # ExpertExecutor.run_full_cycle (plan→build→self_improve)
│   │   ├── blackboard.py          # 7-section state object
│   │   ├── kb_query.py            # KnowledgeBase (YAML-only "retrieval")
│   │   ├── llm_executor.py        # AnthropicExecutor wrapper
│   │   ├── toe_builder_bridge.py  # build_toe_from_design() — the actual .toe writer
│   │   ├── orchestrator.py        # WorkflowOrchestrator (DEAD CODE — defined, never used)
│   │   ├── expert_pool.py         # V6 expert consultations
│   │   ├── variant_spawner.py     # V3/V6 variant spawning
│   │   ├── critic_context.py      # V5/V6 cross-phase critic memory
│   │   └── ...
│   │
│   ├── experts/                   # Per-expert prompt directories
│   │   ├── creative_expert/       # plan.md, build.md, self_improve.md, config.yaml
│   │   ├── cg_expert/
│   │   ├── td_designer/
│   │   ├── td_glsl_expert/
│   │   ├── td_python_expert/
│   │   ├── network_builder/
│   │   ├── critic/
│   │   └── ui_expert/             # In EXPERT_IDS (added in roster cleanup)
│   │   # Five experts moved to archive/experts_unused/ during the H1/M20/M21
│   │   # cleanup: summary_generator, format_reverse_engineer,
│   │   # creative_orchestrator, claude_code_orchestrator, network_editor_expert.
│   │
│   ├── expertise/                 # YAML "working memory" files (the only thing kb_query reads)
│   │   ├── td_operators.yaml
│   │   ├── td_network_patterns.yaml
│   │   ├── td_glsl.yaml
│   │   ├── td_python.yaml
│   │   ├── palette_semantic_catalog.yaml
│   │   └── ... (17 total)
│   │
│   ├── tests/                     # Strategy/orchestration tests (mostly mock mode)
│   ├── compaction/                # Event-log → state YAML compaction (per INTEROP_AND_POLICY.md)
│   ├── concurrency/file_lock.py   # File locking for expertise updates
│   └── history/                   # Append-only JSONL event log
│
├── data/                          # Knowledge-base assets (also see ../td_graphrag.json, ../td_knowledge_graph_enhanced.gpickle for root duplicates)
│   ├── wiki_docs/
│   │   ├── td_universal_parsed.json           # 670 operators, ground truth
│   │   ├── td_universal_parsed_enriched.json  # + ground-truth params
│   │   └── td_universal_parsed_with_build_instructions.json  # Loaded by no runtime code
│   ├── td_graphrag.json                       # Wiki chunks + simple op/param graph (56MB)
│   ├── td_knowledge_graph_enhanced.gpickle    # 37,526 nodes, the real GraphRAG graph (dict, NOT networkx)
│   ├── vector_db/                             # ChromaDB + 4 parallel mirrors (.npy/.json/.pkl)
│   ├── snippets/
│   │   ├── semantic/*.json                    # 479 parsed example networks
│   │   ├── lossless_pop/*.json                # 101 POP snippets
│   │   ├── expanded_pop/                      # EMPTY
│   │   └── index.tsv                          # Curator summaries
│   ├── palette_lossless/                      # 264 palette components
│   └── palette_summaries.json
│
├── chroma_db/                     # SECOND ChromaDB (orphan — built by create_embeddings.py, queried by nothing)
├── builders/                      # Single file: json_to_dir_LOSSLESS.py (bit-identical copy of td_builder_workspace's)
├── tox_builder/                   # Stress-test pipeline (test_all_operators.py over 685 ops)
├── tests/basic_builds/            # 5 named-like-pytest scripts with 0 def test_ functions
├── search/__init__.py             # Exports UnifiedSearchAdapter
├── agents/                        # Engineer skill prompts (BIT-IDENTICAL to ../td-mcp/agents/)
└── docs/                          # Misc docs

../td-mcp/                         # ACTIVE MCP server (Claude Desktop wires here)
../unified_system/                 # The bones: parser, registry, validation, format converter, builder
../kb_pipeline/                    # Build pipeline for vector_db + graph
```

---

## How prompts and orchestration actually work

### 1. The strategy runner (when invoked from Python)

Entry: [`run_strategy(name, prompt, config)` at meta_agentic/execution/strategy_runner.py:2386](meta_agentic/execution/strategy_runner.py:2386).

Picks one of `v0`–`v6` from a registry. Each strategy is a copy-pasted variant of the same basic phase order — they are NOT layered or composed:

```
prompt → §1_REQUIREMENTS (blackboard.py)
   ↓
KB Query (query_knowledge_base_comprehensive)  ← keyword if-ladder, NOT GraphRAG
   ↓
Creative Expert (plan→build→self_improve) → §2_CREATIVE_VISION
   ↓ critic gates: while score < 0.85, iterate (max_iterations)
Technical/CG Expert → §3_TECHNICAL_APPROACH
   ↓ critic gates
TD Designer → §5_NETWORK_DESIGN
   ↓ critic gates
Network Builder → §7_BUILD_ARTIFACTS
   ↓
toe_builder_bridge.build_toe_from_design()  ← actually writes .toe.dir
   ↓
toecollapse.exe (manual or via td_fixture_pipeline.py)
   → .toe file
```

Differences across strategies:
- **V0**: Stub. Returns `success=False`. Don't use.
- **V2**: The reference flow. Heavy `RunLogger` instrumentation.
- **V3**: V2 clone with `VariantSpawner` imported but never called. Effectively V2.
- **V4**: V2 clone marketed as "blackboard-centric." Same flow.
- **V5**: V2 + stretch goals (target 0.95) + convergence detection.
- **V6**: V5 + `ExpertPool` consultations + `VariantSpawner` actually wired up when `exploration > 1` + a "phase reopening" branch that only logs a warning.

### 2. Per-expert inner loop

Inside `execute_expert(name, blackboard, metrics)` → `ExpertExecutor.run_full_cycle()` at [expert_executor.py:362](meta_agentic/execution/expert_executor.py:362):

```
plan.md       → 1 LLM call → if validation_errors: bail
build.md      → 1 LLM call → if validation_errors: bail
self_improve.md → 1 LLM call
final_output = self_improve.revised_output OR build.output
```

System prompt is a hardcoded one-liner per expert at [`_build_system_prompt` at expert_executor.py:639-720](meta_agentic/execution/expert_executor.py:639) — covers 7 of 11 registered experts; the rest get `f"You are the {expert_id} expert."`.

### 3. Inter-agent communication

Via the **blackboard**, not direct passing. Each agent reads sections it cares about (mapping at [blackboard.py:330-356](meta_agentic/execution/blackboard.py:330)) and writes to a section the next agent reads. 7 sections:

| Section | Written by | Read by |
|---|---|---|
| `§1_REQUIREMENTS` | user (BaseStrategy.execute) | creative_expert, cg_expert, td_designer |
| `§2_CREATIVE_VISION` | creative_expert | cg_expert, td_designer, critic |
| `§3_TECHNICAL_APPROACH` | cg_expert | td_designer, critic, network_builder |
| `§4_AVAILABLE_RESOURCES` | kb_query, expert_pool | td_designer |
| `§5_NETWORK_DESIGN` | td_designer | network_builder, critic |
| `§6_VALIDATION_HISTORY` | (unused at runtime) | — |
| `§7_BUILD_ARTIFACTS` | network_builder, toe_builder | (terminal) |

---

## Retrieval: what it claims vs. what it does

**Claim (per old project docs):** GraphRAG-powered retrieval combining vector embeddings (80 MB ChromaDB, sentence-transformers `all-MiniLM-L6-v2`, 20,477 chunks) with graph traversal over `td_knowledge_graph_enhanced.gpickle` (37,526 nodes, 40,568 edges).

**Reality at the agent runtime:** [`query_knowledge_base_comprehensive` at strategy_runner.py:132-266](meta_agentic/execution/strategy_runner.py:132) — 134 lines of `if any(kw in prompt.lower() for kw in [...])` against ~47 hardcoded keywords across 6 buckets (audio / visual / geometry / particles / GLSL / Python). It calls `kb.query_operators({"family": "TOP"})` etc. against YAML files only. The vector store and graph are not touched.

**The real GraphRAG stack lives in:**
- [`search/unified_search.py:UnifiedSearchAdapter`](search/unified_search.py) — orchestrates vector + graph.
- [`search_docs.py:TDDocSearch`](search_docs.py) — ChromaDB query (collection `touchdesigner_docs`, but build script creates `td_unified` — name mismatch).
- [`enhanced_graph_query.py:EnhancedGraphQuery`](enhanced_graph_query.py) — pickle-loaded dict-of-nodes, NOT networkx.
- [`unified_graph_query.py:UnifiedGraphQuery`](unified_graph_query.py) — wraps the above + `td_graphrag.json` wiki graph + enriched params.

These are reachable only from `mcp_server.py`'s `hybrid_search` tool. The strategy runner's agents never see them.

`KnowledgeBase.semantic_search` at [meta_agentic/execution/kb_query.py:902](meta_agentic/execution/kb_query.py:902) is a stub returning `[]` with `# TODO: Implement ChromaDB integration`.

---

## How TOE building actually works

The naming is confusing. Two separate code paths:

### Path A: Strategy-runner → `toe_builder_bridge`

Used at the end of every V2-V6 run. [`build_toe_from_design()` at meta_agentic/execution/toe_builder_bridge.py:2170](meta_agentic/execution/toe_builder_bridge.py:2170) reads `§5_NETWORK_DESIGN` and writes `.n` / `.parm` / `.toc` files into `<project>.toe.dir/`. BASIC mode only — no `lossless_data` available because nothing was parsed.

**Known broken**: parameters are written with mode 0 only. Real TouchDesigner expressions need mode 17. Per `multiscene_test/error1.tsv`, BASIC mode produces 55+ "Skipping unrecognized parameter" errors. Use the unified-system path if you can.

### Path B: Unified-system pipeline (the actually-correct one)

`../unified_system/parsers/lossless_parser.py` → `LosslessParser.parse()` → `TDNetwork` with full `lossless_data` → `../unified_system/builders/toe_builder.py:TOEBuilder._build_lossless()` → byte-identical `.toe.dir` + `.toc`.

Round-trip orchestrator: [`../unified_system/cli/td_fixture_pipeline.py`](../unified_system/cli/td_fixture_pipeline.py).

**This is what works**. 100% file preservation against `gpt/bigtest/LorenzAttractor_Yoav.20.toe.dir` (398/398 files) per the v5 fix. Used by `td-validate`, `td-convert`, `td-build` CLI tools and by the active MCP's `td_validate` (which then doesn't actually run the validation, see `problems.md` B5).

### `toecollapse.exe` is a manual step

Neither path invokes `toecollapse` automatically *except* `td_fixture_pipeline.py`. The strategy runner stops at `.toe.dir` and prints `"toecollapse <name>"` for the user.

---

## Tests

| Suite | Where | Real? |
|---|---|---|
| Plumbing pytest (parser, registry, format converter, validation, byte-level round-trip) | [`../unified_system/tests/`](../unified_system/tests/) | **Yes — strict, 55 `def test_*` functions, real fixtures** |
| Operator stress test (685 single-op `.tox` builds) | [`tox_builder/tests/test_all_operators.py`](tox_builder/tests/test_all_operators.py) | Yes |
| Strategy-runner integration smokes | Root `test_*.py` (`test_ruth_v0_v6.py`, `test_critic_fix.py`, `test_strategy_integration.py`) | Mixed — most use cached YAML, some hit the API |
| `tests/basic_builds/test_06...test_10.py` | This dir | **Lie — 0 `def test_` functions, scripts not pytest** |
| KB latency benchmark | `../kb_pipeline/benchmark_phase5.py` | Yes (latency only, no relevance metric) |
| Manual prompt-to-build eval (the only NL-prompt eval) | Was in `Claude code personalities/QA TESTER ... QUEENIE/` (now archived) | Human-graded, last full run 33% pass overall, 0% on Advanced |

There is **no automated end-to-end NL-prompt eval**. "Did the generation work" = a person opens TouchDesigner and looks.

---

## Where to start changes

If you're fixing the highest-impact thing in this directory: **wire `query_knowledge_base_comprehensive` to call the real semantic search**. The infrastructure (`UnifiedSearchAdapter`, `EnhancedHybridRetrieval`, ChromaDB) exists and is loaded by `mcp_server.py` at startup — the strategy runner just doesn't use it. See `../problems.md` B1 / B2.

If you're touching expert prompts: edit the `.md` files in `meta_agentic/experts/<expert>/`, NOT the copies in `agents/` (those are for `spawn_engineer`, a different mechanism) and NOT `TD_Build_Alpha/claude_ai_docs/01_SYSTEM_PROMPTS.md` (that's a stale doc copy).

If you're adding a new strategy: implement in `strategy_runner.py` as a `BaseStrategy` subclass, register in `register_all_strategies()` at [strategy_runner.py:2366](meta_agentic/execution/strategy_runner.py:2366). But strongly consider editing V2 in place rather than copy-pasting it again.

If you're fixing BASIC-mode `.parm` generation: the spec is in `../multiscene_test/error1.tsv` (55 errors) and `../multiscene_test/DELEGATION_PROMPT_*.md`. The fix probably involves making `toe_builder_bridge` write mode-17 for expressions and the right type bits per parameter — reverse-engineer from `gpt/test.4/` working examples.

---

## Things to know that are not obvious

- **Roster cleanup (H1/M20/M21) collapsed three drift-prone registries** — `EXPERT_IDS`, `mcp_server.py:AVAILABLE_EXPERTS`, and the historical CLAUDE.md counts — into a single canonical 8-expert roster. The 5 archived experts live at `archive/experts_unused/`. The previously-unreachable `creative_orchestrator` is gone (its non-standard prompt files made it un-loadable; the workflow it described was redundant with V2's hard-coded phase order).
- **`should_iterate` from self_improve is silently ignored** by the V2-V6 phase loops. Only the critic score gates iteration.
- **`WorkflowOrchestrator` in [orchestrator.py:104](meta_agentic/execution/orchestrator.py:104) is dead code.** Defined, exported, never instantiated outside its docstring.
- **The 50-prompt suite assumes the inactive server.** Many test prompts use `td_build_project` or `spawn_expert` which the active server doesn't expose.
- **`agents/` and `../td-mcp/agents/` are bit-identical** (`diff -q` confirms). Editing one silently diverges from the other. The `_OLD` and `_UPDATED` files in both directories are unreachable scratch.
- **`td_knowledge_graph_enhanced.gpickle` is a dict, not a networkx Graph.** Don't trust scripts (e.g. `../query_graph.py`) that call `G.successors(...)` on it.
- **There are TWO ChromaDBs.** `data/vector_db/` is wired to the runtime; `chroma_db/` (one level up from this file) is orphaned.
- **The "Source of Truth Hierarchy" in `meta_agentic/CLAUDE.md` is aspirational.** No runtime code enforces validation against `td_universal_parsed.json` before emitting parameter names. Hallucination resistance is by-instruction-only.

---

## When you change things

- Run `pytest ../unified_system/tests/` after any parser / format-converter / validator change — that's the only suite that catches regressions automatically.
- For agent-prompt changes, there's no automated test. Run `test_ruth_v2.py` against a known-good prompt and eyeball the result.
- For MCP changes here, remember: **Claude Desktop is on the other server.** Switch the desktop config explicitly (see `../td-builder-orientation.md` Q5) before testing through chat.
- When deleting things, check both copies: `agents/` ↔ `../td-mcp/agents/`, the gpickle at root vs. `data/`, the three `unified_graph_query.py` locations.

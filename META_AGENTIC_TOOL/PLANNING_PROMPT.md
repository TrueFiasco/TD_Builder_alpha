# Meta-Agentic TouchDesigner Builder System — Planning Prompt (v1.1)

## Mission
Design a **self-improving, multi-agent, LLM-agnostic TouchDesigner (TD) builder** that can:
1) retrieve grounded evidence from local KB assets,
2) turn an intent into a validated, buildable network specification,
3) produce build artifacts (Text DAT builder script and/or `.toe/.tox` build pipeline),
4) improve itself over time via safe, measurable feedback loops.

**Core principle**: generic agents execute and forget; **agent experts execute and learn**.

## Non-negotiables
- **No hallucinations**: outputs must be grounded in evidence.
- **Code is the source of truth**: expertise files are working memory, not truth.
- **Validation before action**: any buildable output must pass validation.
- **Multi-LLM compatibility**: Claude Code, Claude API agents, OpenAI agents must share the same expertise formats and protocols.
- **Concurrent access**: multiple agents can read/write expertise safely.

## Clarifying questions (answer these first)
1) Primary deliverable type(s): Text DAT builder script, `.toe/.tox`, or both?
2) Target TD version(s) and Python version constraints?
3) Allowed autonomy:
   - Can agents update only expertise/recipes?
   - Can agents propose code changes but require human approval?
   - Can agents auto-merge code changes if tests + eval pass?
4) “Best builder” success definition: speed, correctness, aesthetics, maintainability, portability, or a weighted mix?

## Source-of-truth inputs (explicit)
The plan must treat these as authoritative and define how they are validated against:
- Operator/parameter truth: `data/wiki_docs\td_universal_parsed.json`
- Real usage truth: semantic networks and curator indexes under `data/snippets\` (+ palette semantic)
- Build/validation truth: `C:\TD_Projects\unified_system\validation\pipeline.py`

## Current systems to integrate (explicit)
- Retrieval: `C:\TD_Projects\kb_pipeline\hybrid_retrieval_enhanced.py` (vector + simple graph)
- Builder/validators: `C:\TD_Projects\unified_system\` (network builder + validation pipeline)
- MCP server(s): `C:\TD_Projects\kb_pipeline\mcp\unified_mcp_server.py`

## Known gap to solve
The KB is weak at **workflows** and **composition**:
- how to layout networks
- what connects to what
- repeatable patterns (recipes, modules, contracts)
- idea → data → control → render → post → output pipelines

The plan must define new data products that close this gap.

---

## Required deliverables (planning output format)
Produce a buildable, phased plan — not an essay.

### A) One-page executive summary
- What we’re building, why it wins vs web-searching, and what “done” means.

### B) System architecture (diagrams encouraged)
- Components: retrieval, workflow/pattern library, planner, builder, validator, evaluator, self-improver.
- Data flow: intent → evidence → spec → build artifact → validation → eval → expertise update.

### C) File and data contracts (must be concrete)
Define:
- Expertise file format(s) (prefer JSON/JSONL/YAML with strict schemas).
- “Evidence pointer” format (path + chunk id + excerpt hash).
- “Workflow recipe” schema (modules, IO contracts, operator chain, key parameters, failure modes).
- “Pattern” schema (subgraph signature + applicability).

### D) Concurrency + safety protocol
Define a real protocol for concurrent updates:
- Append-only event log (e.g., `expertise_events.jsonl`) with atomic writes.
- Periodic compaction into materialized views (`expertise_state.json`).
- Conflict handling + last-writer-wins vs merge-by-key.
- Corruption recovery + rollback.

### E) Autonomy policy
Split changes into tiers:
- Tier 0: add new recipes/patterns/eval cases (auto if validated).
- Tier 1: update prompts/skills (auto if eval improves).
- Tier 2: code changes (only if tests + eval pass; optionally require human approval).

### F) Evaluation harness (must be implemented)
Define offline benchmarks that can run locally:
- Retrieval benchmarks (your 100 query set + workflow tasks).
- Build benchmarks (intent → validated network spec → generated artifact).
- Metrics: groundedness, actionability, validation pass rate, time-to-first-valid-build, regression detection.

### G) Expert loops (Plan → Build → Self-improve)
For each expert domain (retrieval, recipes, builder, validation, deployment):
- What it reads
- What it outputs
- What it updates
- What triggers improvement
- How it proves the update is correct

### H) Phased implementation plan
Give phases with:
- scope
- concrete artifacts
- acceptance criteria
- risk
- rollback plan

---

## Additional design requirements (must be addressed)
- Encode “Professional TD workflow architecture” as enforceable templates:
  - **Standardize** naming and project structure.
  - **Compartmentalize** features into modules.
  - **Decouple** modules via a single “settings interface” per module; no external internal references.
- Explicitly describe how the system supports both:
  - a human dev iterating manually
  - an LLM agent generating and validating networks autonomously

---

## Output constraints
- Prefer specific file paths, schema snippets, and step-by-step protocols.
- Avoid vague recommendations.
- Include a minimal MVP that can be built in days, plus a scale roadmap.

---

*Version: 1.1*
*Date: 2025-12-15*
*Target runtimes: Claude Code (codex), Claude API agents, OpenAI agents*

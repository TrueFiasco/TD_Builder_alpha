# Strategies — using the experts well

How to get reliable results from TD Builder's experts and tools, **with or without** any external
orchestration (this release is key-free and has no automatic multi-agent runner).

## The core loop (works everywhere)
1. **Orient** — `hybrid_search` / `get_operator_info` to understand the operators involved.
2. **Load expertise** — `get_expert_prompt(<expert>)` for the task (design, GLSL, Python, UI, build, critique).
3. **Verify, don't guess** — confirm every operator type + parameter name via the KB tools.
4. **Validate before building** — `td_validate`, fix all errors, then `td_build_project`.
5. **(Live)** — with TD open, `capture_top_output` to see results and iterate.

## Rules / enforcement
- **No invented operators or parameters.** If the KB doesn't confirm it, don't build it — the
  builder's pre-check will reject unknown operator types anyway.
- **Critic gate.** For non-trivial builds, load `get_expert_prompt("critic")` and have the model
  review its own design against requirements before building.
- **Stay key-free.** Don't introduce cloud-API steps; the experts are prompts, not API sub-agents.

## Experts available (`../experts/`)
`td_designer` (network design) · `network_builder` (file generation) · `td_glsl_expert` (shaders) ·
`td_python_expert` (scripting) · `ui_expert` (control panels) · `critic` (review/scoring).

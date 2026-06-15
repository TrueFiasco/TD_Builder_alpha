# Agents — experts, expertise, skills

This folder is the canonical home for TD Builder's agent-facing knowledge. The offline MCP server
reads `experts/` and `expertise/` directly from here (via `TD_BUILDER_ROOT`/this folder).

| Path | What it is | Used by |
|---|---|---|
| `experts/` | 6 expert prompt sets (`td_designer`, `network_builder`, `td_glsl_expert`, `td_python_expert`, `ui_expert`, `critic`). Each has `build.md` / `plan.md` / `self_improve.md`. | the `get_expert_prompt` tool — an LLM loads an expert's prompt to apply its TD knowledge |
| `expertise/` | Hand-curated YAML "working memory" (operator patterns, GLSL/Python templates, build rules, palette catalogs). | **`td_network_building.yaml`** is read by the builder (`td_build_project`) for conversion/build rules; the rest are curated-but-unwired (human reference / pending expert wiring). |
| `td-builder-howto/` | The `SKILL.md` how-to skill. | Claude Code / skill-aware clients |
| `td_network_analysis/` | A skill for analyzing TD networks (+ examples). | Claude Code / skill-aware clients |
| `Strategies/` | Notes on rules/enforcement for using the experts well (with and without orchestration). | humans + prompt authors |

## How to use the experts
There is no automatic multi-agent runner in this release. Instead, an LLM calls
`get_expert_prompt(expert_name="td_glsl_expert")` to fetch that expert's full instructions, then
applies them while using the build/validate tools. This keeps everything **key-free** — the
"experts" are prompts, not API-spawned sub-agents.

> The GLSL expert is `experts/td_glsl_expert/`.

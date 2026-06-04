# skills_expertise/ — skills + expert prompts

## Skills (standalone, client-loadable)
- `td_network_analysis/` — `SKILL.md` + examples
  (explain audio-reactive chains, identify bottlenecks, suggest optimizations).

## Expert prompts (server-coupled — left in place by design)
The 8 canonical experts (`creative_expert`, `cg_expert`, `td_designer`,
`network_builder`, `critic`, `td_glsl_expert`, `td_python_expert`,
`ui_expert`) live at `../META_AGENTIC_TOOL/meta_agentic/experts/<name>/`
(`plan.md` / `build.md` / `self_improve.md` / `config.yaml`).

They are **not** physically moved here: `ExpertExecutor.load_prompt()` and the
`get_expert_prompt` MCP tool read them by `meta_agentic/experts/...` path, so
relocating would break the verified server. Access them at runtime via the
`get_expert_prompt` tool. Consolidating their physical location is a
post-alpha refactor (would require repointing the loader + `get_expert_prompt`).

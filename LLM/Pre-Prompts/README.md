# Pre-Prompts — and when to use them

Reusable primers you paste at the start of an LLM session to get good TD Builder behavior. They tell
the model how to use the tools; the deep domain knowledge comes from `get_expert_prompt` + the KB.

| Pre-prompt | When to use |
|---|---|
| **Builder primer** (below) | Any session where the LLM will design/build TD networks. |
| **GLSL primer** | Shader work — pair with `get_expert_prompt("td_glsl_expert")`. |
| **Live-session primer** | When TouchDesigner is open and you want the model to create/inspect nodes live. |

---

## Builder primer
> You are building TouchDesigner networks with the TD Builder tools. **Always verify before you
> build:** use `get_operator_info` / `get_parameter_detail` / `find_operator_examples` to confirm
> operator types and parameter names — never guess them. Draft the network as a design dict, run
> `td_validate` and fix every error, then `td_build_project`. For complex work, first call
> `get_expert_prompt("network_builder")` (or `td_designer`) and follow it. Everything is key-free.

## GLSL primer
> For shader tasks, first call `get_expert_prompt("td_glsl_expert")` and follow it. Consult the
> `KB/wiki_supplemental/Write_a_GLSL_TOP.md` (and `Write_GLSL_POPs.md`) guides. Always pass output
> color through `TDOutputSwizzle(...)`. Validate the network with `td_validate` before building.

## Live-session primer
> TouchDesigner is open and the `td-builder-live` server is registered. Use `get_td_info` /
> `get_td_nodes` to orient, `create_td_node` / `update_td_node_parameters` to build, and
> `capture_top_output` to *see* the result and iterate. Check `get_cook_errors` after changes.

*(Expand this set as you find prompts that work well. The expert prompts in `Agents/experts/` are a
good source.)*

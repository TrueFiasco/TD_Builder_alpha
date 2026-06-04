# Operating Modes

The system is designed to be useful with **no API key at all**, and to also
support bring-your-own-key agentic flows.

## Mode 1 — No API key (subscription / client-only)

You run an MCP client (ChatGPT Desktop, Claude Desktop, Cursor, …) and register
this MCP server with it. The client's own model drives the tools. **No API
billing, no key needed.**

Available in Mode 1 (everything except the two agentic tools):

- Knowledge: `hybrid_search`, `get_operator_info`, `query_graph`,
  `list_pop_operators`, `find_operator_examples`, `find_operator_combination`,
  `find_parameter_usage`, `find_similar_networks`, `get_parameter_detail`,
  `get_network_patterns`, `get_expert_prompt`.
- Build/validate/convert: `td_build_project`, `td_validate`, `td_convert`,
  `td_compact_expertise`.
- Live TouchDesigner (when TD is running with the WebServer `.tox`): the ~18
  `*_td_*` / `capture_*` tools.

This is the mode used in the live demo and the mode the
[demo walkthrough](docs/DEMO_WALKTHROUGH.md) follows.

## Mode 2 — API key (any provider)

For automated/agentic flows you bring your own provider key. Set it as an
environment variable in the MCP server's `env` block (or your shell):

```jsonc
"env": { "ANTHROPIC_API_KEY": "sk-...", "PYTHONPATH": "..." }
```

`spawn_engineer` and `spawn_expert` use this key. The Python-only multi-agent
strategy runner (`META_AGENTIC_TOOL/meta_agentic/`) is also a Mode-2 surface.

**Graceful fallback:** with no key set, the agentic tools return a clear
"requires API key" message instead of crashing — Mode 1 stays fully functional.

## Portability

The server speaks plain MCP over stdio with JSON-Schema tool inputs — no
client-specific extensions. The hard compatibility target for the alpha is
**ChatGPT Desktop** (a non-Anthropic client); Claude Desktop is the control.
See `docs/SETUP/` for per-client registration.

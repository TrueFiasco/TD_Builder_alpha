# MCP/python/ — MCP server launcher

`server.py` is the alpha entry point. It bootstraps the engine import roots
(`bootstrap.py`) and runs the verified server module
(`../../META_AGENTIC_TOOL/mcp_server.py`) as `__main__`.

The server module stays in `META_AGENTIC_TOOL/` on purpose: it resolves the
consolidated KB bundle via `Path(__file__).parent.parent / "KB"` (→
`<root>/KB`) and dynamically loads its sibling search stack
(`unified_graph_query.py`, `hybrid_search.py`, `search/`) by `__file__`-
relative path. Keeping it in place means those verified resolutions are
unchanged; the launcher only fixes `sys.path` so imports resolve from any cwd.

Register with any MCP client (stdio):

```jsonc
"td-builder-alpha": {
  "command": "C:/Users/Jake/AppData/Local/Python/pythoncore-3.11-64/python.exe",
  "args": ["C:/TD_builder_alpha/MCP/python/server.py"],
  "env": { "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1" }
}
```

Confirm which copy is live with the `get_server_info` tool (returns
`script_path`, `version`, `cwd`, `td_live_enabled`). Mode-2 only: add
`ANTHROPIC_API_KEY` to `env` for `spawn_engineer`/`spawn_expert`.

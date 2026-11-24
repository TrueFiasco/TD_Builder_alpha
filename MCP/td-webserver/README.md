# MCP/td-webserver/ — TouchDesigner-side WebServer asset

This is the component you import **into TouchDesigner** so the live-TD MCP
tools (`get_td_nodes`, `create_td_node`, `capture_op_viewer`,
`execute_python_script`, …) can talk to a running TD instance.

## Files
- `mcp_webserver_base.tox` — the component (import this into your project). It is
  **standalone**: it carries a copy of everything in `modules/`, so the single
  `.tox` works wherever you put it, with nothing beside it.
- `modules/` — the webserver code, as readable files. This is the source; the
  copy inside the `.tox` is generated from it.
- `import_modules.py` — the bootstrap embedded in the `.tox` (finds the modules).
- `build_standalone_tox.py` — regenerates the `.tox` from `modules/`.

## Use
1. Open TouchDesigner (2025+).
2. Drag `mcp_webserver_base.tox` into your project (top level is fine). Copying
   just that one file into a project folder is fine too.
3. Its WebServer DAT listens on `http://127.0.0.1:9981`
   (override via the `TD_API_URL` env var on the MCP server).
4. The live MCP server (`../live_server.py`, registered as `td-builder-live`)
   talks to it; with TD not running the live tools return a clear
   "TouchDesigner not running" message, and the offline server (`../server.py`)
   is unaffected either way.

Every request except the health check (`GET /api/td/server/td`) needs the shared
token; see `MCP/COMM_LAYER.md`.

## Where the code comes from

At start-up the component uses the first of these that exists:

1. a `modules` folder beside the component's External `.tox` file (this repo or
   an install tree — edit the files, restart TouchDesigner, done);
2. the folder named by the `TD_BUILDER_WEBSERVER_MODULES` environment variable
   (the `modules` folder itself, or the folder holding it) — use this to run a
   copy of the `.tox` saved elsewhere against the code in your repo;
3. the copy embedded in the `.tox`.

The textport says which one loaded, e.g.
`[MCP] webserver modules loaded from the copy embedded in the .tox (built from MCP API 1.4.1 @ 1a2b3c4)`.
If nothing loads (a broken module, or an old `.tox` with no embedded copy), every
route answers **503** with a sentence naming each place it looked and the error —
not TouchDesigner's bare 404.

## Regenerating the `.tox`

After changing `modules/` or `import_modules.py`, and at least once per release:

```
py -3.11 MCP/td-webserver/build_standalone_tox.py
```

TouchDesigner does not need to be open (`toecollapse`, which ships with it, does
the packing). Then load the new `.tox` once in TouchDesigner to check it. Without
a regeneration, a repo or install tree still runs the latest code (rule 1 above);
only copies of the `.tox` carried elsewhere run the older embedded copy.

## Before you save a show file: remove the component

The component runs Python sent to it over HTTP. It is a development tool; a show
machine should not carry it. Before saving a project you are going to ship,
delete the component (select it and press Delete), or paste this into the
textport to remove every copy anywhere in the project:

```python
[c.destroy() for c in root.findChildren(type=COMP) if c.op('mpc_webserver') and c.op('import_modules')]
```

To check a project is clean (prints `[]` when it is):

```python
print([c.path for c in root.findChildren(type=COMP) if c.op('mpc_webserver') and c.op('import_modules')])
```

Verified working end-to-end against TD 099.2025.32460 (MCP API 1.4.1).

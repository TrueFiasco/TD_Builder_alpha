# Demo Walkthrough

This mirrors the live demo session: query the knowledge base, build a
TouchDesigner network **offline** as a `.tox`, validate it, and (optionally)
inspect it live in a running TouchDesigner. It is written client-neutral —
works the same from ChatGPT Desktop, Claude Desktop, or Cursor once the server
is registered (see `SETUP/`).

## 0. Sanity check

Ask the client to call **`get_server_info`**. Confirm `script_path` points at
your release tree (e.g. `C:\TD_Builder\...`, or wherever `TD_BUILDER_ROOT`
points). This is the fastest way to know which copy of the server is actually
live.

## 1. Explore the knowledge base (key-free)

Ask the model to use these tools:

- `hybrid_search` — semantic search over TD docs, e.g. *"feedback loop with a
  Feedback TOP and a Level TOP"*.
- `get_operator_info` — exact spec for an operator (e.g. `noiseTOP`).
- `get_parameter_detail` — full parameter description + menu options.
- `find_operator_examples` / `find_operator_combination` — real usage from the
  479 parsed example networks.

Expected: structured results drawn from the canonical KB
(`KB/operators.json` — 663 entries covering 640 of TouchDesigner 2025.32820's 647 operators) — real parameter names, no hallucination.

## 2. Build a network offline as a `.tox`

Use **`td_build_project`** with a small network spec (operators + connections +
parameters). It writes a `<project>.toe.dir/` structure offline — **no running
TouchDesigner required**.

Then validate and convert without TD:

- **`td_validate`** — runs the 7-stage pipeline (schema → semantic → grounding →
  reference → component-source → logical → TD-rules) and reports errors/warnings.
- **`td_convert`** — converts the spec between the Builder ↔ Canonical layers.

CLI equivalents (run with the venv's python from the release root — the install
is deps-only, so there are no `td-*` console commands):

```powershell
python "Tools\offline Builder tools\td_validate.py" network.json --verbose
python "Tools\offline Builder tools\td_convert.py"  network.json --from builder --to canonical --output out.json
python "Tools\offline Builder tools\td_build.py"    network.json --output project.toe --verbose
toecollapse project.toe.toc          # TD's CLI — final .toe.dir -> .toe
```

> Use a LOSSLESS round-trip (parse an existing `.toe`, rebuild) for
> byte-identical output. Building brand-new networks in BASIC mode has known
> parameter-format issues — see README "Known limitations".

## 3. Inspect it live (optional — needs TouchDesigner)

1. Launch TouchDesigner, import
   `MCP\td-webserver\mcp_webserver_base.tox` (WebServer DAT →
   `http://127.0.0.1:9981`).
2. Now the live tools activate. Ask the model to:
   - `get_td_nodes` — list nodes in the live project.
   - `create_td_node` / `update_td_node_parameters` — edit the live network.
   - `capture_op_viewer` / `capture_top_output` — get a rendered image back.
   - `get_td_node_errors` / `get_error_summary` — check for cook errors.

> **Clean-project caveat (acceptance bug #6).** The live-TD prompts assume a
> project with **no pre-existing cook/expression errors**. If `get_error_summary`
> reports errors before you start, they belong to whatever was already loaded in
> TD (e.g. a stray parameter expression), not to these tools. For a clean
> acceptance run, start from an empty/known-good `.toe` (just the imported
> `mcp_webserver_base.tox`) so error-diagnostic prompts read zero at baseline.

If TD is not running, these tools return a clear "TouchDesigner not running —
import mcp_webserver_base.tox, WebServer on 9981" message; the key-free KB/build
tools still work.

## What "success" looks like

- `get_server_info` shows the right `script_path`.
- KB tools return real operators/parameters for a natural-language query.
- `td_build_project` produces a `.toe.dir`; `td_validate` reports on it.
- (If TD running) a `capture_*` tool returns an image of the live network.
- Same flow behaves equivalently in ChatGPT Desktop and Claude Desktop.

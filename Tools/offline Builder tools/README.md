# offline Builder tools (command-line)

These are the **command-line** front-ends to the same engine the `td_validate` / `td_convert` /
`td_build_project` MCP tools use. They run fully offline (no TouchDesigner, no API key).

| Script | Does | Example |
|---|---|---|
| `td_validate.py` | 7-stage validation of a network JSON | `python "Tools/offline Builder tools/td_validate.py" network.json --verbose` |
| `td_convert.py` | Convert between format layers (builder/canonical) | `python "...\td_convert.py" network.json --from builder --to canonical` |
| `td_build.py` | Build a `.toe`/`.tox` (LOSSLESS round-trip or BASIC from-scratch) | `python "...\td_build.py" network.json --output project.toe` |
| `td_validate_expanded.py` | Audit an expanded `.toe/.tox.dir` against its `.toc` — files listed but missing on disk, and extra unlisted files (the pre-`toecollapse` "why won't this collapse" check; the lossless parser silently skips missing files, so nothing else reports this) | `python "...\td_validate_expanded.py" project.toe.dir --strict-extra` |

Each script bootstraps the engine import path and calls into `MCP/engine/cli/`. Run them directly
with `python` as shown above — the install is deps-only (`pyproject.toml` has `packages = []`), so
**no console commands are installed**.

**LOSSLESS vs BASIC:** round-tripping an existing `.toe.dir` uses LOSSLESS mode (byte-identical,
100% fidelity). Building a network from scratch uses BASIC mode (parameters written with safe
defaults; some expression formats are approximate). Collapsing `.toe.dir` → `.toe` is a manual
`toecollapse` step (TouchDesigner's official workflow).

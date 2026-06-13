# Known Issues — V0.1.1

Documented limitations, not blockers. The 21-check acceptance + smoke gate passes; KB search is
local / key-free.

| Area | Issue | Status / workaround |
|---|---|---|
| **Palette embedding** | `td_build_project(design={"palette": …})` is not available. | **Deferred to V0.2.** Planned via **live import** (with TouchDesigner open) or by **referencing an external `.tox` from a `base`/`container` COMP** — not bundled palette JSON, so `KB/sources/` is not shipped. For now, build without the `palette` key; you get a clear "not available in V0.1.1" message. |
| **BASIC-mode build** | Building a network from scratch (no parsed source) emits parameter-format warnings; some expression modes are approximate. | The **LOSSLESS** round-trip (parse an existing `.toe.dir` → rebuild) is byte-accurate — use it when you have a source. |
| `find_similar_networks` | Returns `[]` for many example ids (partial pattern coverage). | All other KB tools are full-fidelity. Deferred. |
| `hybrid_search.relationships` | Some display-name vs graph-key mismatches (e.g. "Feedback TOP") report "not found in graph". | Semantic results are unaffected; graph node-name normalization deferred. |
| `get_network_patterns` | Thin/noisy at high `min_frequency`. | Use a lower `min_frequency`; co-occurrence dedup deferred. |
| Final `.toe` file | The builder emits `.toe.dir` + `.toc`; producing the single `.toe` is a manual `toecollapse` step. | TouchDesigner's official workflow — by design. |
| Live tools | Require TouchDesigner running + `MCP/td-webserver/mcp_webserver_base.tox` imported (port 9981). | Without TD, the 19 `td-builder-live` tools return a clear "not running" message. |

**No API key anywhere** — KB semantic search uses a local embedding model. The first KB-dependent
call warms the knowledge base (~1–2 min, one-time), then every call is fast.

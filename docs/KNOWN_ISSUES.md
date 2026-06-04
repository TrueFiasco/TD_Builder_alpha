# Known Issues (alpha)

These are documented, not blockers. The alpha is demonstrable end-to-end.

## Acceptance run 2026-05-16 — 37/37 tools PASS (namespace-locked, alpha-only)

Bugs found during the certified run and their disposition:

| # | Issue | Status |
|---|---|---|
| 1 | Cold-start KB hang: first KB-dependent tool call paid the ~1–2 min model load on a silent socket and timed out at the client's ~4 min window (worked on retry). | **FIXED** — background KB warm-up kicked at server start (`threading.Thread(_ensure_kb)` in `main()`), thread-safe via `_kb_lock` + double-check; `get_server_info`/live-TD stay instant. |
| 2 | Builder→extended name-drop: name-only operators (`{name,family,type}`) lost their name in `FormatConverter._builder_node_to_operator` (read `path` only) → `string_table[1]=""` → `'' does not match` → duplicate `/` cascade in `td_validate`/`td_convert`. `td_build_project` was unaffected (reads `name`). | **FIXED** — converter now falls back `path → name`. Verified: `[('noise1','/noise1'),('null1','/null1')]`, `VALID: True, 0 errors`. Builder contracts now consistent across validate/convert/build. |
| 3 | `hybrid_search.relationships` returns `"Feedback TOP" → not found in enhanced graph` though the semantic store knows it (display-name vs graph-key normalization). | Documented; post-alpha fix (graph node-name normalization). Semantic results unaffected. |
| 4 | `get_network_patterns` thin at `min_frequency=10` (mostly `DAT:text`/readMe co-occurrence noise). | Documented; data/dedup-signature tuning post-alpha. |
| 5 | `get_top_info` reports `0.0 KB` GPU for a passthrough Out TOP. | Documented; minor — passthrough TOPs allocate no texture, so 0 is largely correct; refine to traverse view-passthrough post-alpha. |
| 6 | Demo TD project shipped `/project1/noise1.amp = 1.5+sin(abstime.second)` (two errors: `sin` unimported, `abstime.second`→`absTime.seconds`). Not a tool bug. | Fixture issue — see note in `DEMO_WALKTHROUGH.md`; live-TD prompts assume a clean project / restore from a known-good `.toe`. |
| 7 | `exec_node_method` on a *property* (e.g. `numChans`) returns `"1 is not a callable method"` (the `1` is the value, not the name). | Documented; cosmetic wording — post-alpha message improvement. Tool behaviour otherwise correct. |

Pre-existing items below remain as previously documented.

| ID | Issue | Impact | Status |
|---|---|---|---|
| G1 | Some legacy builder-schema tests/inputs expect a `nodes` key; the builder export/validate emits `{meta, operators}`. | Affects only those stale tests + hand-written builder JSON using the old shape. `td_validate` pipeline itself runs all 5 stages correctly. | Documented; canonical builder schema to be pinned post-alpha. Tests not shipped. |
| — | BASIC-mode `.toe` build (new networks built from scratch, no parsed source) emits parameter-format warnings. | New-from-scratch builds fragile. LOSSLESS round-trip (parse → rebuild) is byte-accurate and solid. | Pre-existing; LOSSLESS is the recommended path. |
| W5.3 | `find_similar_networks` pattern coverage is partial (returns `[]` for many example ids). | One discovery tool under-returns; all other KB tools full-fidelity. | Deferred (per prior triage). Documented. |
| — | Multi-agent strategy runner (`meta_agentic/`) is Python-only; not exposed as an MCP tool. | Strategies not reachable from chat clients. | Out of scope for alpha (deferred). |
| — | Live-TD tools require TouchDesigner running + `mcp_webserver_base.tox` imported (port 9981). | Without TD, ~19 live tools return a clear "TD not running" message. | By design; graceful fallback verified. |
| — | `spawn_engineer`/`spawn_expert` require an API key (Mode 2). | Without a key they return a clean "requires API key (Mode 2)" envelope. | By design; Mode-1 fully functional without keys. |

No automated test suite ships with the alpha (removed by design). Regression
reference: the pre-packaging baseline was 51 passed / 7 failed (pre-existing
G1) / 12 skipped; dev pytest can still be run from the quarantined
`_out_of_scope/` tree.

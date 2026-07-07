# TD Builder — non-negotiables (canonical single source)

This file is the **canonical statement** of the TD Builder non-negotiables — the
always-on summary the MCP servers deliver. The deep layers (the
`td-builder-howto` skill and the expert prompts) elaborate these rules with
worked detail; what no other surface may do is re-assert a rule in the specific
footgun phrasings **reserved to this file**. `scripts/docs_lint.py` enforces
exactly that — three guarded phrasings, not "no elaboration anywhere" (see
*Drift guard* below).

## The payload (scoped per server)

The block between the two `INSTRUCTIONS` markers is loaded into the MCP servers'
`instructions=` field by `MCP/server_instructions.py` and returned by
`get_server_info`. Each line is tagged for one of two scopes:

- **`[always]`** — delivered by BOTH servers. Grounding + build rules that hold
  whether or not TouchDesigner is running. This is all the **offline** server
  (`td-builder`) ships — and it is the only server Cursor / ChatGPT can reach, so
  its budget stays on-message (offline generation + anti-hallucination grounding).
- **`[live-only]`** — added only by the **live** server (`td-builder-live`): the
  gotchas that only bite while driving a running TD (GLSL info-DAT, save, place,
  flat exec scope).

Each scoped payload is kept **≤ 2 KB** (Claude Code truncates `instructions` at
2 KB) with its **catastrophic/silent rules in the first 512 characters** (OpenAI
asks the first 512 chars be self-contained): the offline payload front-loads the
offline-generation capability + KB-first grounding; the live payload front-loads
the two silent-failure rules (GLSL-invisible, flat-exec-scope). The `[always]`/
`[live-only]` tags are structural markers — the loader strips them before
delivery.

<!-- INSTRUCTIONS:BEGIN -->
[always] td-builder - non-negotiables. Deep detail: "td-builder-howto" skill (SKILL.md).
[always] CAPABILITY: build real, openable .toe/.tox offline via td_build_project - TouchDesigner need NOT be open.
[live-only] GLSL COMPILE ERRORS ARE INVISIBLE to node.errors(). After ANY GLSL TOP/POP edit read op('<n>_info').text for 'ERROR:'/'Compile Failed' AND op('<n>').warnings(); "Compiled Successfully"+warnings = silent no-op (uniform on wrong page reads 0).
[live-only] execute_python_script RUNS IN FLAT exec() SCOPE. No def-inside-def, no comprehensions over outer names (np, loop vars, imports); inline at top level. "name X is not defined" for an imported X = this.
[always] KB-FIRST, MANDATORY. Query the KB for an exemplar (find_operator_examples/get_operator_info) before creating ops, setting params, or GLSL. Never guess params; don't introspect the live op - the KB has them.
[always] MENU/ENUM PARAMS = STRING TOKENS, never int indices: operand="over" not 0, dataformat="rgb" not 1. #1 build failure; looks-numeric is still a token. Unsure -> get_parameter_detail.
[always] EVERY BUILD goes through td_build_project; td_validate first; never shorten the pipeline. Emitting JSON/Python instead of calling the tool = failure.
[live-only] NEVER call project.save() or any ui.* from scripts - a modal Save-As/overwrite dialog freezes TD's single main thread and the live connection, no rescue. SAVE OFTEN: ask the USER to save (Ctrl+S) at milestones; crashes lose unsaved work. The auto pre-mutation restore point copies the last-SAVED .toe only.
[live-only] PLACE EVERY NODE. Set nodeX/nodeY in the creating call; never leave ops at (0,0). Data L->R, control/sidecar below; move docked groups together.
[always] RELATIVE PATHS + LOCAL ASSETS. Reference ops relatively (op('sibling'), ../parent); copy any external .tox/image/model/video into the project folder before referencing. Absolute refs break .tox re-import/portability.
[always] After context COMPACTION, re-read these instructions / call get_server_info before resuming live edits.
<!-- INSTRUCTIONS:END -->

Most of these rules are elaborated with worked examples in the `td-builder-howto`
skill (`Agents/td-builder-howto/SKILL.md`); the menu-token rule and the
build-pipeline rule are covered in depth by the expert prompts
(`get_expert_prompt`). Those are the deep layers; this file is the always-on core.

## How this reaches the model (per-surface delivery)

Delivery of `instructions=` is **client-specific** (the MCP spec makes it an
optional hint). Empirically (see `eval/TD_builder audit/D2_CLIENT_DELIVERY.md`):

| Surface | `instructions=` (push) | Recovery / pull path |
|---|---|---|
| **Claude Code** (CLI, desktop-bundled, cowork) | delivered **verbatim** at session start (or async-injected once the server connects); ≤ 2 KB, front-loaded | re-read after compaction; `get_server_info` |
| **Claude Desktop — chat** | **NOT surfaced** — the push channel does not exist here; tool descriptions are also deferred + truncated until a tool is loaded | `get_server_info` returns the rules; per-tool one-line pointers ride each destructive tool at call time |
| **Cursor** | assume **not surfaced** (docs silent on `instructions`); only reaches the offline `td-builder` server | same pull paths as Desktop chat |
| **ChatGPT / Codex** | documented to consume `instructions` (remote transports only; TD Builder is stdio today); offline server only | first 512 chars are self-contained by design |

**Compaction survival is client-owned.** No server can force re-injection after a
context compaction, so the recovery instruction is baked into the payload itself
(the COMPACTION rule) and `get_server_info` re-serves that server's full scoped
text on demand — that call *is* the recovery path on every surface.

## Single source & drift guard

`scripts/docs_lint.py` (CI `docs-lint` lane, config in
`scripts/docs_lint_rules.json`) fails the build if any of the following
footgun phrasings appears **outside this file**. State the rule here; reference it
elsewhere.

- `Menu parameters NEVER accept integer indices` (the menu-token rule)
- `... MUST call / MUST be processed by ... td_build_project` (the build-pipeline rule)
- `build pipeline ... NEVER shortened` (the build-pipeline rule)

When a rule changes, edit it **here** and let the references stand. The scope tags
do not affect the drift guard — the guarded phrasings are reserved to this file
regardless of `[always]`/`[live-only]`. The three `non_negotiables` entries in
`docs_lint_rules.json` carry `canonical_file: docs/NON_NEGOTIABLES.md`; adding a
new guarded rule means adding an entry there, not restating it across prompts.

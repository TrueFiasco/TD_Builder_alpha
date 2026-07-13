---
name: td-builder-howto
description: Load when working in or with the TD Builder Alpha project — building, editing, or debugging TouchDesigner networks via the td-builder MCP. Triggers on TouchDesigner, TD, .toe, .tox, TouchDesigner operators (POP, TOP, CHOP, SOP, DAT, MAT, COMP), GLSL TOP/POP, compute shader, feedback POP, raymarch, SDF, or any mcp__td-builder__* / mcp__td-builder-live__* tool call. Load BEFORE acting — these are gotchas you cannot recover from by trial and error.
---

# Working in TD Builder Alpha

You are working against a live TouchDesigner instance via the `td-builder-live` MCP (and the offline `td-builder` MCP for build/validate/convert). Read this whole file before your first tool call — most of the failures here are silent or misleading, and the cost of one wrong call is large (TD crashes, lost work, hours debugging the wrong layer).

## The non-negotiables

The always-on ≤2KB summary of these rules is the canonical single source at
[`docs/NON_NEGOTIABLES.md`](../../docs/NON_NEGOTIABLES.md) (also delivered as the
MCP server `instructions=` and by `get_server_info`). This section is the **deep
layer** for most of them — worked detail for the exec-scope, GLSL, save, place,
and relative-path rules (the menu-token and build-pipeline rules live in the
expert prompts). When a rule changes, edit the canonical file; these layers
elaborate, they do not compete as the source.

These are the failure modes that burned hours in prior sessions. Internalize them.

### 1. Exec scope — top-level names are visible everywhere

`execute_python_script` runs your code as a **single module-level namespace** (globals
*is* locals). So comprehensions, generator expressions, and nested `def`s **can** see
names bound at the top level of the same script — imports, loop vars, helper vars:

```python
import numpy as np
arr = [np.zeros(3) for _ in range(4)]    # works — np resolves at module scope

def process():
    return np.sum(arr)                    # works — np and arr are module-level names
```

The rule that remains: **bind the names you use at the top level of the script.** Normal
Python scoping still applies *inside* nested functions (a name defined in one nested
`def` isn't visible in a different one), but anything at the script's top level is global
to the whole script.

Two consequences of the single-namespace model:
- Your script no longer has implicit access to the MCP service module's own globals
  (`os`, `io`, `ast`, …) — `import` what you need explicitly. `td`/`tdu`/`op`/… are still
  injected for you.
- If you still see `name 'X' is not defined`, X is genuinely unbound — a typo or a
  missing top-level `import`, not a scope quirk.

**`time.sleep()` is rejected before your script runs.** It executes on TD's single main
thread and would freeze TD and the live connection for the whole duration with no rescue,
so a static check returns an error naming `time.sleep` (best-effort — it can be
obfuscated, don't rely on it as a sandbox). Split any delay across multiple tool calls.

### 2. GLSL compile errors are invisible via `.errors()`

`get_td_node_errors` (which calls `node.errors()` server-side) **does not surface compute/GLSL shader compile failures**. A broken shader will run as a no-op, the node will look fine via the normal error API, and you will debug the wrong layer for hours.

After ANY edit to a GLSL TOP or GLSL POP, read its info DAT and scan for **both errors and warnings in the same pass**:

```python
info = op('<shader_node>_info').text
errors   = [ln for ln in info.splitlines() if 'ERROR:' in ln or 'Compile Failed' in ln]
warnings = [ln for ln in info.splitlines() if 'WARNING:' in ln]
print(f'errors: {len(errors)}  warnings: {len(warnings)}')
for ln in errors:   print('  E ' + ln)
for ln in warnings: print('  W ' + ln)
```

- `ERROR:` / `Compile Failed` — fatal. The shader is not running. Fix before doing anything else.
- `WARNING:` — informational, NOT fatal, but **read them** — they often surface real problems (uniform unassigned, deprecated feature, type-narrowing) that look fine until they bite later. Surface warnings to the user even when there are no errors.

The info DAT is the source of truth for shader compile status. Always check it after a shader edit.

**The info DAT is necessary but not sufficient.** Also read `op('<node>').warnings()` separately:

```python
node_warnings = op('<shader_node>').warnings()
if node_warnings:
    print('node.warnings():', node_warnings)
```

The info DAT carries GLSL compile output; `op.warnings()` carries TD's runtime parameter/binding warnings on the op itself. The two surfaces report different problem classes. The killer pattern: **"Compiled Successfully" in the info DAT + non-empty `op.warnings()` is a silent failure.** Typical cause: a uniform assigned on the wrong UI page (e.g. Constants instead of Vectors on a GLSL TOP), an unbound sampler, a deprecated feature still allowed but flagged. The shader runs; the uniform you assigned silently reads as 0.

Surface `op.warnings()` content to the user whenever it's populated — even on a "clean" compile.

### 3. Saving: never `project.save()` from scripts — ask the user

TD can crash, sometimes during heavy compute, sometimes for no obvious reason. When it does, you lose every node created since the last save. But do **not** try to checkpoint from scripts:

- **Never call `project.save()` — or any `ui.*` dialog call — from `execute_python_script`.** The live connection is served by a WebServer DAT handler running on TD's **single main thread**. If a save pops a modal dialog (Save-As on a never-saved project, an overwrite prompt on an incrementing save), that dialog blocks the main thread: TD freezes, the live connection hangs with no timeout rescue, and nothing can dismiss the dialog programmatically. One call can kill the whole session.
- **The server takes an automatic pre-mutation restore point** — a pure filesystem copy of the last-saved on-disk `.toe`, once per server process, before the first mutation. Its outcome is in `get_td_info`'s `restorePoint` field: `status: ok` means a rollback copy exists (at `path`); `skipped`/`unavailable` means there is **no rollback point**. Either way it captures **last-saved state only** — unsaved in-session edits are never in it.
- **To checkpoint, ask the user to save manually (Ctrl+S)** at milestones — before any operation you know is heavy (large bakes, big point ops, .tox exports) and every so often during long sessions. Manual saves auto-increment (heart.01.toe, heart.02.toe, …), so user-side checkpointing is free.
- **For a programmatic checkpoint, use the dialog-proof `save_td_project` live tool** (details below) — never a scripted `project.save()`.

**Checkpoint before a risky batch — use `save_td_project`, not a scripted save.** The
`save_td_project` live tool takes a **dialog-proof** filesystem copy of the last-saved
`.toe` (into the project's `Backup/` folder). It never pops a TD save/overwrite dialog,
so it is safe to call unattended — unlike `project.save()` **inside `execute_python_script`**,
which runs on TD's single main thread and hangs the connection (~60 s) if it raises a
modal. Never call `ui.*` or `project.save()` from a script.

`save_td_project` captures **last-manual-save state only** (it copies what is on disk,
not unsaved in-memory edits). The safe fresh-checkpoint recipe before a risky exec batch:

1. Ask the artist to save (Ctrl+S).
2. Call `save_td_project`.
3. **Verify** the returned `source_mtime` advanced vs the prior value (from
   `get_mutation_status.last_snapshot` or a previous receipt). If it did **not** advance,
   the artist did not save — re-ask; do **not** proceed.
4. Proceed. This bounds any rollback loss to the batch itself.

After a client timeout, poll `get_mutation_status` (retry — it queues behind TD's busy
main thread). Rolling back to a snapshot restores last-saved state and loses **every** API
mutation since that save — surface that (`source_mtime` + the seq delta) before recommending it.

### 4. Place every node you create — never leave ops at (0,0)

Every op you create gets an explicit position the same call. If you create three ops without setting `nodeX`/`nodeY`, they all stack at (0,0) and the user has to manually drag them apart. This is the most common visual landmine in agent-built networks.

**Default placement rules:**

- **Downstream of an existing op** (you just wired its input from `upstream`): `new.nodeX = upstream.nodeX + 150`, `new.nodeY = upstream.nodeY`
- **Sibling of an existing op** (parallel chain, no connection): `new.nodeX = sibling.nodeX`, `new.nodeY = sibling.nodeY + 150`
- **First op in an empty container**: start at `(0, 0)`; the next one grows right or down from there
- **Sidecar ops** (Info DATs, callback DATs, helper Text DATs documenting an op): place ~150 below the op they document — they're not part of the data flow

Read direction in TD networks is **left → right** (data) with **control/ancillary ops below**. Don't break that.

**One-shot create + position pattern:**

```python
g = parent().create(td.geometryCOMP, 'jelly_geo')
g.nodeX, g.nodeY = 0, 0

# A live-created geometryCOMP ships with a default torus1 child (render flag ON)
# that gets rendered/instanced alongside your geometry — destroy it FIRST.
# (Live-create only: offline-built .tox geos have no stray torus1. PROB-017.)
if g.op('torus1'):
    g.op('torus1').destroy()

script_sop = g.create(td.scriptSOP, 'build')
script_sop.nodeX, script_sop.nodeY = 0, 0

out_sop = g.create(td.outSOP, 'out1')
out_sop.nodeX, out_sop.nodeY = 200, 0
out_sop.inputConnectors[0].connect(script_sop)

callback_dat = g.create(td.textDAT, 'build_callbacks')
callback_dat.nodeX, callback_dat.nodeY = 0, -150   # sidecar, below
script_sop.par.callbacks = callback_dat.path
```

**Move an op *with* its docked children — they don't follow on their own.**

When an op has docked DATs (GLSL shader/`info`, callback DATs, a Ramp's table, …),
setting the host's `nodeX`/`nodeY` moves **only the host** — the docked children keep
their own positions and visibly separate. TD's network editor moves the group when you
*drag*, but the Python API has **no group-move**: you only get `op.docked` (read the
children) plus per-op `nodeX`/`nodeY`. So the unit of layout is **the op plus its docked
helpers**, and you position it with one primitive:

```python
def place(host, x, y):
    """Position an op AND its docked children as a group (children laid out below)."""
    host.nodeX, host.nodeY = x, y
    for i, child in enumerate(host.docked):   # reads docking live — generic, no per-op data
        child.nodeX, child.nodeY = x + i * 160, y - 120

place(op('glsl1'), 0, 0)     # NOT `glsl1.nodeX = ...` directly when it has docked DATs
```

Prefer creating an op at its final position (the auto-docked children land correctly and
you never move them); use `place()` for any *re-layout* of an existing group. (The offline
builder already positions docked children at `host + offset` at build time — `place()` is
the live-side equivalent.)

**Anti-patterns to refuse:**

- Creating multiple ops in one script without setting positions for any of them
- Creating ops in a loop and giving them all the same position
- Setting `nodeX`/`nodeY` but reversing the data direction (downstream op left of upstream)
- Forgetting sidecar ops — leaving an Info DAT or callback DAT stacked on top of the op it serves
- Setting `host.nodeX/nodeY` directly on an op that has docked children — it strands the children; move the group with `place(host, x, y)`

**On `create_td_node`** (the MCP tool): it doesn't accept a position arg. Immediately follow up with a one-line `execute_python_script` (or batch several creates with positions in a single script) to position what you just created. Better: when creating more than one node, do them all in one `execute_python_script` so positions, connections, and params all land in the same call.

### 5. Always use RELATIVE paths and keep assets local

Two related rules — break either one and the project becomes non-portable.

**A. Use relative paths for every op reference.** Whenever you set a parameter that points at another op (sampler `top` params, GLSL `top` inputs, POP `pop` params, compute DAT refs, `Geo.instanceop`, expressions like `op('foo')`):
- Prefer `op('siblingName')` or `op('../parent/foo')` over `op('/test/p02/foo')`.
- Prefer relative parameter strings (`../cloudSurf`) over absolute (`/test/p02/cloudSurf`).
- When in doubt, use `op('node').relativePath(target)` to derive the right relative string.

**Why this matters specifically:** if a network was built using absolute references and then exported as `.tox`, re-importing it at any other path can break every sampler / compute DAT / POP ref. Building relative-from-the-start sidesteps it entirely.

**B. Copy any external asset into the project folder before referencing it.** If the user points you at a `.tox`, image, model, video, audio file, or any asset that lives outside the current project's folder:
1. Copy the file into the project's own assets folder first (create `assets/`, `tox/`, or similar under the project root if it doesn't exist).
2. Reference it from there with a project-relative path (`assets/foo.png`, not an absolute path like `C:/Users/<name>/Downloads/foo.png`).
3. Tell the user you copied it and where.

This makes the project self-contained: it survives being moved, zipped, shared, or opened on another machine. Hard-coded absolute asset paths break the moment any of those happen.

**Exception:** if the user explicitly says "reference it in place, don't copy" — honor that.

### 6. Execute DAT firing semantics — parexec gotchas

`onValueChange` on a CHOP/DAT/Parameter Execute DAT fires ONLY on UI edits (and certain
internal changes) — it does **NOT** fire on a programmatic `par.val = x` write (including
`update_td_node_parameters` or any script) and does **NOT** fire on a bind-driven change.
If you need code to react to a programmatic change, drive the downstream logic yourself, or
use `onPulse`, which **does** fire on `par.pulse()`.

On the Execute DAT's `op`/`pars` (or channel-scope) parameters: `.` means the DAT itself —
use `..` to watch the parent. An empty `op` or `pars` scope matches nothing and fails
**SILENTLY** (no error, the callback just never fires — don't assume "no error" means
"wired correctly").

The pulse-enable toggle on the Execute DAT is named `onpulse`, not `pulse` — enabling the
wrong-named par leaves `onPulse` dark with no error.

Pulse/callback effects are not visible until the **next frame** — verify with a separate
call/read, not inline in the same script that fired the pulse.

## Tool preferences

Always prefer `td-builder` / `td-builder-live` namespace tools over generic ones. Within that namespace:

| Job | Use | Don't use |
|---|---|---|
| Health check | `get_server_info` | Anything else — this is the only reliable ping |
| Create one op | `create_td_node` | `execute_python_script` to do `parent().create(...)` |
| Set one param | `update_td_node_parameters` | A script |
| Set many params at once | `execute_python_script` (one script, one call) | N separate `update_td_node_parameters` calls |
| Read one param | `get_td_node_parameters` | A script |
| Run anything complex / loops / data | `execute_python_script` | — |
| Render capture | `capture_top_output` (param is `operator_path`, NOT `node_path`) | — |
| Node errors (non-GLSL) | `get_td_node_errors` | — |
| GLSL compile status | Read `op('<node>_info').text` in a script | `get_td_node_errors` (misses GLSL fails) |
| Find operator info | `get_operator_info`, `hybrid_search`, `find_operator_examples` | Guessing |

`capture_top_output` uses parameter name `operator_path` (not `node_path`). Getting this wrong returns "Input validation error".

`create_td_node` auto-suffixes on name collision — if you ask for `cloudSurf_compute` and one exists, you'll get `cloudSurf_compute1` silently. Check the returned name.

### Offline tools — do not forget these

A lot of useful work does not need TD running. Use these whenever you can — they're faster, never time out, and let you inspect or build networks without disturbing the live session:

| Job | Offline tool | Why |
|---|---|---|
| Inspect a `.toe` / `.tox` structure | `toeexpand` CLI (TD's own) → produces `.toe.dir/` with `.n`/`.parm`/`.toc` files | Read the network as plain files instead of guessing from a screenshot |
| Parse + summarise an existing network | `MCP/engine` lossless parser (`parsers/lossless_parser.py`) (Python) — backs the `td_validate.py` / `td_convert.py` launchers | Gives you a `TDNetwork` object you can introspect — node list, params, connections, no TD needed |
| Validate a `.toe.dir` before importing | `python "Tools/offline Builder tools/td_validate.py" <path>` | 5-stage validator; catches mode-0/17 parm issues and orphan refs |
| Convert format (LOSSLESS ↔ BASIC) | `python "Tools/offline Builder tools/td_convert.py"` | Same engine (`MCP/engine`) |
| **Build a `.tox` offline, then import live** | `python "Tools/offline Builder tools/td_build.py"` or `TOEBuilder._build_lossless()` directly → produces `.toe.dir/` → `toecollapse` → `.tox` → drop into the live network | Useful when iterating on a small subnet without thrashing the live project |
| KB lookups (operator info, param names, examples, patterns) | `hybrid_search`, `get_operator_info`, `get_parameter_detail`, `find_operator_examples`, `find_operator_combination`, `find_parameter_usage`, `find_similar_networks`, `get_network_patterns`, `list_pop_operators` | These query the local vector DB / graph — no TD round-trip |

The repo's CLI entry points are in `MCP/engine/cli/` (also exposed as the launchers in `Tools/offline Builder tools/`) and the round-trip pipeline is `td_fixture_pipeline.py`. The 673-operator ground-truth JSON at `KB/operators.json` is the canonical reference if you need to read params directly (paths.py exposes it as `KB_OPERATORS`).

**Default heuristic:** if a task is "look at what's there" or "build something small in isolation", reach for offline tools first. Only go live when you need to see the result rendering or interact with running state.

## KB-first is mandatory, not a recommendation

The KB is the source of truth for per-operator setup — exemplars, parameter defaults, the actual tool calls to create and wire each op. Configuring an op without consulting the KB **first** is a violation, not a shortcut.

Concretely: before you call `create_td_node` for any op type, OR set non-trivial parameters in `execute_python_script`, OR write a shader for a GLSL TOP/POP — you must first run a KB query for an exemplar. Param names are routinely non-obvious (menu params vs custom-name params, sequence counts that gate child params, type fields that silently change how a value is interpreted) and guessing them is the #1 cause of wasted cycles in prior sessions.

**Search order:**
1. `find_operator_examples(operator=...)` — working snippets
2. `find_operator_combination(operator_types=['CHOP:noise', 'TOP:level'])` — multi-op patterns
3. `find_similar_networks(example_id=...)` — broader pattern match
4. `get_operator_info(operator_name=..., compact=True)` — params, families, descriptions
5. `get_parameter_detail(operator_name=..., parameter_name=...)` — defaults, types, valid values for one specific param
6. `hybrid_search(query=...)` — fallback semantic search

Take the exemplar's tool calls and adapt — don't paraphrase from memory.

### Anti-pattern: live introspection instead of KB lookup

If you are about to write any of these in `execute_python_script`, **stop**. The KB has the answer:

- `[p.name for p in op.pars()]` — listing param names → `get_operator_info` returns them
- `dir(op.par)` or `hasattr(op.par, 'thing')` — guessing if a param exists → `get_parameter_detail`
- Creating a "tmp_probe" op just to dump its params → `get_operator_info(compact=True)`
- Looping through candidate names like `['type','wave','wavetype']` until one works → `find_parameter_usage` or `get_operator_info`
- "Let me grep the param names for keywords" → `find_operator_examples` for a working configuration

In a recent session, ~10% of all `execute_python_script` calls were doing one of these. Every one of them was a KB query disguised as live introspection. Don't.

### What to do when the KB tool times out or returns "warming"

KB tools may return `{"status": "kb_warming", "retry_after_seconds": N}` on a fresh session — the vector DB takes 1–2 min to load. If you see this: tell the user, wait the suggested time, and retry. Do **not** fall back to live introspection because the KB is slow — that's how the prior session ended up with zero KB lookups across 729 calls. Wait it out.

### What to do when the KB returns no exemplar

Tell the user explicitly. That's a real KB gap worth filling, not a license to guess. Then proceed cautiously: configure minimally, verify each param read-back, and surface any unexpected behavior immediately. Flag the missing exemplar in your final report so it can be added.

## Reading point data: double-cook flush

`poptoCHOP`:
- Reads its POP via the `pop` parameter (NOT a wired input).
- Needs `attribscope='*'` and `scope='*'` to actually see attributes.

Reading point data **through a Delete POP** returns stale data by one cook. Either:
- Cook twice and read on the second (call `op.cook(force=True)` twice in your script before reading), OR
- Read the upstream POP directly, before the Delete.

Symptom of hitting this: your fix obviously worked (you verified it in the script that set it) but the downstream reader still shows the old value. You're reading stale-by-one-cook data.

## Feedback POPs — drive them yourself, then hand off

Feedback POPs iterate on timeline playback; `cook(force=True)` does not advance the sim. Two phases:

**During the task — you pulse the buttons yourself.** Every feedback POP exposes `init`, `start`, `play` as pulse params. Pulse them via script (`op('fb').par.init.pulse()` etc.), advance frames by nudging the timeline or letting `play` run wall-clock, then verify state with `poptoCHOP`. Do not tell the user to press anything mid-task.

**At hand-off — point the user at the interactive control.** The convention is keys `1`/`2`/`3` → `init`/`start`/`play`. Before telling the user to press them, check whether a keyboard CHOP wired to these pulses already exists in the project. If it does, use the convention. If it doesn't, **search the KB for a feedback POP + keyboard-wiring exemplar** (`find_operator_examples('keyboardinCHOP')`, `find_similar_networks` with the right keywords) — the exemplar is the source of truth for the create-and-wire tool calls. If the KB has no such exemplar, tell the user it's missing rather than improvising, and fall back to telling them how to pulse the params from a Text DAT (`op('fb').par.init.pulse()` etc.). Flag the missing exemplar — it's worth adding to the KB.

You cannot read keyboard input via the MCP. Keys 1/2/3 are for the user after hand-off, not your input channel.

## Error → root cause cheat sheet

| Symptom | Real cause |
|---|---|
| `name 'np' / 'p' / 's' is not defined` | The name is genuinely unbound — a typo or a missing top-level `import` (top-level names ARE visible in comprehensions/nested defs now; the old flat-scope restriction is gone) |
| `time.sleep() is not allowed in execute_python_script` | Static guard rejects `time.sleep()` (freezes TD's main thread) — split the delay across multiple tool calls |
| `'operator_path' Required` | You passed `node_path` to `capture_top_output` — it wants `operator_path` |
| Shader runs but outputs zeros / uniform reads as 0 / custom attr missing downstream | Op-specific setup gotcha — search KB for the exemplar (don't guess at params) |
| Fix verified in-script but downstream sees old value | Reading through Delete POP — needs double-cook flush |
| Feedback sim won't iterate from `cook(force=True)` | Pulse `init`/`start`/`play` params directly via script; nudge frames or wait wall-clock; verify with poptoCHOP |
| `node.errors()` clean but shader is broken | Read `<node>_info.text` — that's where GLSL errors actually live |
| `"Compiled Successfully"` in info DAT + `op.warnings()` populated | Silent failure — typically a uniform assigned on the WRONG UI page (e.g. Constants instead of Vectors on a GLSL TOP). The shader runs; the uniform reads as 0. Check `op.warnings()` separately from the info DAT. |
| GLSL TOP shader compiles but `uPhase` (or any scalar uniform) reads as 0 | TOP does NOT auto-declare Vectors-page uniforms — your shader must include `uniform float uPhase;` explicitly. |
| GLSL POP shader fails: `uPhase already defined` or `uPhase is not defined` | POP auto-declares Arrays-page uniforms as a `float[]`. Use `uLfo[0]`, do NOT redeclare. (TOP and POP differ — symptom flips by op family.) |
| Imported `.tox` from `td_build_project`, file-sync isn't pulling on-disk edits | The builder embeds shader text directly; it does not set `file`/`syncfile`/`loadonstart` on Text DATs holding shader source. After import, manually set those three params on each Text DAT so on-disk edits propagate. |
| Created op with name X but tool returned X1 | Name collision auto-suffix — use the returned name |
| Re-imported `.tox` has all-broken references | Export wrote absolute paths — should have built with relative refs from the start (see rule 5) |
| Project breaks when moved/zipped/opened elsewhere | Asset referenced by absolute path — copy assets into project folder, reference relatively |
| Phase / uniform value won't change | Check `.expr` not just `.val` — an expression binding will override fixed values; clear the expr |
| Execute DAT callback never fires, button looks dead | Programmatic `par.val=` write or bind-driven change — `onValueChange` only fires on UI edits; use `onPulse` + `par.pulse()` to trigger from code |
| Parameter/DAT Execute DAT wired but nothing happens, no error | Empty `op`/`pars` scope matches nothing and fails silently; check `op` (`.`=self, `..`=parent) and `pars` are non-empty |
| Pulse callback silent even though "enabled" | Toggle is named `onpulse`, not `pulse` — check the actual par name |

## Debugging style: data first, eyes second

Eyeballing the viewport will mislead you. When something looks wrong:
1. Dump the data via `poptoCHOP` (centroid, bbox, std, per-point displacement, point count).
2. Compute the answer in Python (compare to expected, check ranges, look for outliers).
3. Then look at the viewport to confirm.

This caught real bugs that visual inspection missed in the prior session: bake corruption (visible via flow magnitudes), bbox clipping mistaken for a topology hole (visible via Z-range vs bake bound), "circulation" being a bake artifact (visible via path-length analysis), scale drift (visible via culled-centroid).

## Key-free — no API key, no modes

This release has no API key and a single mode. Every tool (17 offline + 21 live)
works with no credentials; KB search uses a local embedding model. There are no
agent-spawning tools.

## At session start

Before your first substantive tool call:
1. `get_server_info` to confirm TD is reachable.
2. Note the current project file and frame (so a crash + reload is recoverable).
3. If the user hasn't said which project / network they're working on, ask.

Do not run a `td-preflight` skill if one isn't available — just do these three checks inline.

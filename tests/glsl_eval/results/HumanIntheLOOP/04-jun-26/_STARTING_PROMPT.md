# TD Builder Alpha — Human-in-the-Loop Test Session (paste into Claude Desktop)

You are running a **human-in-the-loop test session** for the **TD Builder
Alpha** MCP server. I will give you prompts (many GLSL-focused). For each, you
build/answer using ONLY `td-builder-alpha` tools, capture exactly what happened,
and save structured results for my review. Goal: surface real bugs — do NOT
paper over failures.

## Session rules

0. **NAMESPACE LOCK.** Multiple TD MCP servers may be connected. Call ONLY
   tools in the **`td-builder-alpha:`** namespace. First call `get_server_info`
   and confirm `script_path` contains `TD_builder_alpha` and `version` is
   `0.1.0-alpha`. If not, STOP and tell me.

1. **MODE.** This is likely Mode 1 (no API key). `spawn_engineer` /
   `spawn_expert` returning `{"ok":false,"error":{"message":"...requires an API
   key (Mode 2)"}}` is EXPECTED, not a failure. Do the work yourself with the
   knowledge / build / validate / live tools.

2. **STUDY THE EXPERTISE FIRST (required for any GLSL request).** Before
   building GLSL, call `get_expert_prompt` with
   `expert_name="td_glsl_expert"`, `phase="build"` and apply it. State which
   guidance is relevant for the specific op (glslTOP vs glslMultiTOP vs
   glslPOP / glslcopyPOP / glslAdvancedPOP / glslSelectPOP vs glslMAT) and the
   shader stage (pixel / vertex / compute). Use `get_operator_info` /
   `get_parameter_detail` for exact params — never invent operators/params.

3. **LIVE TD.** TouchDesigner is on `127.0.0.1:9981`, working base `/test`.
   Build live work under `/test/<case_id>/`. Confirm with `get_td_info`. If TD
   is down, a clear "not running" message is fine — say so.

## Per-prompt workflow

For each prompt I give you, assign a short `case_id` like `p01_red_glsltop`,
then:

1. **Plan** — (GLSL) state the expertise you studied + the operators/params you
   will use.
2. **Build** — offline (`td_build_project`) or live (`create_td_node` +
   `update_td_node_parameters`, `properties=` for params). Note which path.
3. **Capture — honestly:**
   - **Compile log**: read the GLSL op's companion **info DAT**
     (`op('<op>_info').text`) AND `op('<op>').warnings()`. NOTE: a shader
     compile FAILURE shows up as a *warning* + an `ERROR:` line in the info
     DAT — it does **NOT** appear in `errors()` or `get_td_node_errors`
     (those stay empty). Report the actual info-DAT text.
   - **Cook errors / python**: `get_cook_errors`, `get_python_exceptions`.
   - **Render**: capture the output TOP. Then **sanity-check it isn't flat
     white/black** (sample pixels via
     `op('<top>').numpyArray()` → report `mean` and `std`; `std≈0` means a
     flat/blank render — flag it, don't call it a success).
4. **Retry on failure** — if it failed, attempt a fix and rebuild. **Count each
   retry as a fix-iteration.** Cap at 4 attempts, then report the state.
5. **Save artifacts** (next section).
6. **Report** — a short self-assessment + leave `HUMAN VERDICT: ____` blank for
   me.

## Save results

Root: `C:\TD_builder_alpha\tests\glsl_eval\results\HumanIntheLOOP\04-jun-26\`

Create a per-case subfolder `<case_id>\` containing:

- `prompt.txt` — my exact prompt
- `plan.md` — expertise studied + plan + operators/params chosen
- `network.json` (or the built `.tox` path) — what was produced
- `errors.txt` — the info-DAT compile log + `warnings()` + cook errors + python exceptions
- `output.png` — the render (save via `op('<top>').save(r"<path>\output.png")`)
- `result.md` — self-assessment, `fix_iterations: N`, pixel mean/std, and a
  trailing line `HUMAN VERDICT: ____`

Also maintain `LOG.md` in the root folder — append one row per case:
`| case_id | prompt (short) | build path | compiles? | renders(std)? | fix_iterations | self-assessment | HUMAN VERDICT |`

**How to write files:** use `execute_python_script` (TD's Python). Example:
```python
import os
d = r"C:\TD_builder_alpha\tests\glsl_eval\results\HumanIntheLOOP\04-jun-26\p01_red_glsltop"
os.makedirs(d, exist_ok=True)
open(os.path.join(d, "errors.txt"), "w", encoding="utf-8").write(log_text)
op("/test/p01_red_glsltop/glsl1").save(os.path.join(d, "output.png"))
```

## Honesty contract

Report exactly what the tools return. An unhandled exception / traceback is a
**failure** — record it, don't smooth it over. Never claim a render matches the
request — that's my call (the `HUMAN VERDICT` line). A white/blank render with
"Compiled Successfully" in the info DAT is a real finding worth flagging.

---

When ready, reply with one line:
`TD Builder Alpha ready — <version> @ <script_path>; TD <up/down>; expertise loader OK`
then wait for my first test prompt.

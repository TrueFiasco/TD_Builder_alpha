# Revision 002 — GLSL expert docs must cover LIVE GLSL-TOP creation (auto-DAT model)

Status: PROPOSED (not applied — `td_glsl_expert/` is outside the write boundary)

## Gap

`td_glsl_expert/build.md` (§"GLSL Code Storage (BUG-D)") documents only the
**offline / builder-JSON** model:

> Text DAT created BEFORE GLSL TOP in operator list … GLSL TOP `pixeldat`
> param references Text DAT name.

That order is correct for offline `.tox` building. But when an agent creates a
GLSL TOP **live** (`create_td_node` / `comp.create(glslTOP, …)`), TouchDesigner
**auto-creates the companion child DATs itself** and auto-binds them:

- `glsl1_pixel`  (pixel-shader Text DAT) — `par.pixeldat` already points here
- `glsl1_info`   (Info DAT — the compile log; see Revision 001)
- `glsl1_compute`(compute-shader Text DAT)

Following the offline doc's advice live — *create a Text DAT, then point
`pixeldat` at it* — produces a **name collision**: the new DAT is renamed
`glsl1_pixel1`, `par.pixeldat` stays bound to TD's empty default `glsl1_pixel`,
and the TOP renders **solid white with NO error** (compile is "clean" because
the default passthrough compiles fine). This is silent and hard to diagnose.

Verified live this session (2026-06-04): creating a `glslTOP` yielded children
`glsl1, glsl1_info, glsl1_pixel, glsl1_compute`; a second `glsl1_pixel` was
renamed `glsl1_pixel1`; binding to the default DAT rendered white
(`numpyArray()` mean=1.0 std=0.0); writing into `par.pixeldat.eval().text`
rendered the intended shader (std>0).

## Where

`C:\TD_builder_alpha\META_AGENTIC_TOOL\meta_agentic\experts\td_glsl_expert\build.md`
(and the mirror in `meta_agentic/expertise/td_glsl.yaml` if it duplicates the
storage guidance).

Add a new section alongside §"GLSL Code Storage (BUG-D)" distinguishing the two
creation paths.

## Proposed change

Add to `build.md`:

```markdown
## Live creation vs offline build — opposite DAT order (BUG-021)

The Text-DAT-before-GLSL-TOP rule above is for OFFLINE builder JSON only.
When creating a GLSL TOP LIVE in a running project, TD auto-creates the
companion DATs for you:

  glsl1_pixel   (pixel shader) — par.pixeldat already bound to it
  glsl1_info    (Info DAT — compile log, see Revision 001 / BUG-D)
  glsl1_compute (compute shader)

CORRECT (live): write into the DAT TD already made —
    pix = glsl.par.pixeldat.eval()
    pix.text = shader_source
    pix.par.language = 'glsl'

WRONG (live): create a second Text DAT named 'glsl1_pixel'. The name
collision renames it 'glsl1_pixel1'; par.pixeldat stays bound to TD's empty
default DAT; the TOP renders SOLID WHITE with no error (the default
passthrough compiles cleanly). Symptom: white output, errors() empty.
```

Also cross-link Revision 001 + the compile-error reading rule (it is a
*warning*, not an error; full log in `<op>_info.text`; `errors()` and
`get_td_node_errors` report clean — read `warnings()` + the Info DAT, treat any
`ERROR:` line as failure; format matches the Dec-2024 `glsl9errors.txt`).

## Verify

1. Live-create a `glslTOP`; confirm children `*_pixel/*_info/*_compute` auto-exist.
2. Write a solid-colour shader into `par.pixeldat.eval().text`; `cook(force=True)`;
   `numpyArray().std() > 0` (real render, not white).
3. Repeat but create a *second* `glsl1_pixel` Text DAT → confirm it is renamed
   `glsl1_pixel1`, the TOP stays white, and `errors()` is empty (the trap).
4. Write a type-mismatch shader (`vec2 b = someVec3;`); confirm `errors()` is
   empty but `warnings()` flags compile errors and `<op>_info.text` carries the
   `ERROR: … cannot convert from vec3 to vec2` line.

## Related (separate — do NOT bundle)

- Revision 001 — offline builder must emit the `<op>_info` Info DAT.
- `uTime` is not a TD built-in: standalone GLSL TOP shaders must declare
  `uniform float uTime;` (or use `uTDOutputInfo`) or they fail to compile.
  Candidate for a build.md anti-hallucination checklist item.

# Revision 001 — Offline builder must emit the `<op>_info` Info DAT for GLSL TOPs

Status: PROPOSED (not applied — alpha is outside the write boundary)

## Gap

A real TD-exported GLSL TOP carries companion child nodes
`<op>_pixel`, `<op>_compute`, `<op>_info` (verified via `toeexpand` of
hand-built reference toxes). The offline builder emits **only** the operators
present in `network.operators` and has **no GLSL-TOP companion-node logic** —
so a builder-produced GLSL TOP tox is missing the `<op>_info` Info DAT.
(Per user: this is the *only* structural gap; the offline tox is otherwise
fine. Do **not** generalize other "defects" from the butterfly artifact.)

The Info DAT matters because GLSL compile status is read from it (plus
`warnings(recurse=True)`); without it the component doesn't match a real
export and compile results aren't introspectable.

## Where

`C:\TD_builder_alpha\unified_system\builders\toe_builder.py`

- `_build_basic()` — lines ~140–153: loops `self.network.operators` →
  `_write_basic_operator(op)`. Purely model-driven; nothing is synthesized.
- `_write_basic_operator()` — lines ~343+: writes `.n`/`.parm`/`.panel`/
  `.text`; no per-family GLSL handling.

## Proposed change

The tool (not the caller / not a test recipe) should synthesize the Info DAT.
Recommended: a single synthesis pass so the model API is unchanged.

In `_build_basic()`, after the operator loop, add:

```python
# Synthesize the companion Info DAT every real GLSL-TOP export carries.
for op in list(self.network.operators):
    if op.op_type == "TOP:glsl":
        info_path = f"{op.path}_info"
        if not any(o.path == info_path for o in self.network.operators):
            info = Operator(
                path=info_path,
                name=f"{op.name}_info",
                family=OperatorFamily.DAT,
                type="info",
                parent=op.parent,
                parameters={"op": op.name},   # relative sibling ref
            )
            self._write_basic_operator(info)
```

Notes:
- `op` param value is the **relative sibling name** (matches how `pixeldat`
  is written as `proc_pixel`, not an absolute path).
- Idempotent: skip if an `<op>_info` already exists in the model.
- Same pattern would later extend to `<op>_pixel` / `<op>_compute` if those
  are ever synthesized too (separate revision; out of scope here).

## Verify

1. Build a GLSL-TOP tox from scratch (must also include the root container
   operator: `add_operator(root, "COMP", "base", parent=None)` with
   `root_comp=root` — that is caller-correct usage, not a builder bug).
2. `toecollapse <out>.tox.toc`.
3. Import into live TD via the **externaltox** mechanism
   (`c.par.externaltox=<path>; c.par.enableexternaltox=True;
   c.par.enableexternaltoxpulse.pulse(); c.cook(force=True)`) — NOT
   `comp.loadTox()`.
4. Confirm a `<op>_info` `DAT:info` child exists, `info.par.op` resolves to
   the GLSL TOP, and `info` reports the compile result; COMP/TOP
   `warnings(recurse=True)` and `errors()` are clean.

(Behaviour above was confirmed achievable end-to-end during investigation;
this revision moves that synthesis into the tool instead of a test wrapper.)

## Related (separate proposals — do NOT bundle here)

- `set_parameter` registry-gating drops GLSL sequence value params
  (`vec`, `vec0valuex/y/z/w`) → "Parameter does not exist for TOP:glsl";
  known BASIC param-fidelity issue, distinct from this structural fix.
- `<op>_pixel` / `<op>_compute` companion DAT synthesis (if desired to fully
  mirror exports rather than a separate sibling shader DAT).

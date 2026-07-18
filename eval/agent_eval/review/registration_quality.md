# Registration quality ledger

Every `summary` / `use_cases` / `parameter_descriptions` the model authored
during a `register_component` scenario run, beside what the component
actually is. Score by eye against [RUBRIC.md](RUBRIC.md) — 0–2 on each axis,
one-word verdict. **Generated** by `review/extract_registrations.py --render`;
the scoring lines are yours to fill in and keep.

Entries: **3**

---

## knotgen — s19_register_search_roundtrip
<sub>s19-21-cap1</sub>

**Authored** (what the model wrote)

> **summary** — Procedural 3D knot-curve generator (POP) that samples mathematical knot paths — trefoil, figure-eight, torus (2,3), or circle — as a point cloud with controllable point count and XYZ scale.
>
> **use_cases**
> - Animate a ribbon or tube geometry along a looping 3D knot trajectory as a motion-graphics centerpiece
> - Feed a mathematically precise closed-loop point path into particle systems or instancing for generative art or live-visual installations
> - Prototype topology-aware looping curves by switching knot types from a menu without writing any custom GLSL

| parameter | authored description | actual (from skeleton) |
|---|---|---|
| `Numpoints` | Number of points sampled along the knot curve (range 16–2000) | `Numpoints` — default 200; range 16..2000 |
| `Scale` | XYZ scale factors applied uniformly to the generated knot geometry | `Scale` — default 1, 1, 1 |
| `Knottype` | Which knot shape to generate: trefoil, figure8, torus, or circle | `Knottype` — menu: trefoil\|figure8\|torus\|circle; default trefoil |

**Actual I/O** — in: none · out: ['out1'] · 6 inner ops (DAT:info, DAT:text, POP:circle, POP:glsl, POP:out)

<sub>committed: retrievable=True · chunks=3 · shadows_shipped=False</sub>

`Specificity: 2/2   Correctness: 2/2   Searchability: 2/2   → verdict: __6/6__`

---

## wisp — s20_register_exact_name
<sub>s19-21-cap1</sub>

**Authored** (what the model wrote)

> **summary** — POP-based knot generator that outputs parametric 3-D closed-curve geometry (trefoil, figure-eight, torus (2,3), or circle) as a point cloud, distinct from flat or procedural mesh shape generators by its selectable closed-curve topology.
>
> **use_cases**
> - Drive ribbon or trail geometry along a mathematically defined knot path for abstract motion-graphics loops.
> - Seed a particle system with structured, closed-curve initial positions by switching Knot Type at runtime.
> - Morph between topologically distinct knot shapes live by animating the Knot Type and Scale parameters.

| parameter | authored description | actual (from skeleton) |
|---|---|---|
| `Numpoints` | Number of evenly-spaced points sampled along the knot curve (range 16–2000). | `Numpoints` — default 200; range 16..2000 |
| `Scale` | XYZ scale factors applied uniformly to the generated knot geometry. | `Scale` — default 1, 1, 1 |
| `Knottype` | Selects the knot curve formula; menu tokens: trefoil, figure8, torus, circle. | `Knottype` — menu: trefoil\|figure8\|torus\|circle; default trefoil |

**Actual I/O** — in: none · out: ['out1'] · 6 inner ops (DAT:info, DAT:text, POP:circle, POP:glsl, POP:out)

<sub>committed: retrievable=True · chunks=3 · shadows_shipped=False</sub>

`Specificity: 2/2   Correctness: 2/2   Searchability: 2/2   → verdict: 6/6`

---

## knotgen — s21_register_hit_parity
<sub>s19-21-cap1</sub>

**Authored** (what the model wrote)

> **summary** — Procedural torus-knot point-cloud generator (trefoil, figure-eight, torus 2,3, or plain circle) computed in GLSL inside a POP network — distinct from SOP-based or noise-driven shape generators.
>
> **use_cases**
> - Generate a parameterized knot curve as SOP-ready point geometry for ribbon or tube rendering
> - Drive animated strand effects by keyframing Num Points or Scale over time
> - Switch between knot topologies at runtime via the Knot Type menu without rebuilding the network

| parameter | authored description | actual (from skeleton) |
|---|---|---|
| `Numpoints` | Total number of evenly-spaced points sampled along the knot curve (range 16–2000). | `Numpoints` — default 200; range 16..2000 |
| `Scale` | XYZ scale multiplier applied to the generated knot geometry. | `Scale` — default 1, 1, 1 |
| `Knottype` | Selects the knot formula: trefoil, figure-eight, torus (2,3), or plain circle. | `Knottype` — menu: trefoil\|figure8\|torus\|circle; default trefoil |

**Actual I/O** — in: none · out: ['out1'] · 6 inner ops (DAT:info, DAT:text, POP:circle, POP:glsl, POP:out)

<sub>committed: retrievable=True · chunks=3 · shadows_shipped=False</sub>

`Specificity: 2/2   Correctness: 2/2   Searchability: 2/2   → verdict: 6/6`

---

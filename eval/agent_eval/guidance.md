<!--
Canonical Lane-M guidance (design §2, owner decision D-C 2026-07-04).
Source: distilled from Agents/td-builder-howto/SKILL.md (the shipped skill) —
offline-server sections only; live-TD sections dropped because the eval surface
is the 17-tool offline server. Content ownership: 3b/D2 — when their distilled
guidance lands, swap this file's body; the sha256 of THIS FILE is in every
result's identity block, so a swap forces a visible re-capture (never silent).
Injected verbatim via --append-system-prompt (gate config = "guided").
-->

# Working with the TD Builder offline MCP

You are working with the `td-builder` offline MCP server. It has 17 tools: KB
retrieval (hybrid_search, get_operator_info, query_graph, list_pop_operators,
find_operator_examples, find_operator_combination, find_parameter_usage,
find_similar_networks, get_parameter_detail, get_network_patterns), offline
build/validation (td_build_project, td_build_status, td_validate, td_convert,
expand_toe_file), and contract tools (get_server_info, get_expert_prompt).
TouchDesigner itself is NOT running — everything happens offline against the
knowledge base and the offline builder.

## KB-first is mandatory, not a recommendation

The KB is the source of truth for per-operator setup. Before you build any op
type or set non-trivial parameters, look it up. Param names are routinely
non-obvious (menu params, sequence counts, codes that differ from labels) and
guessing them is the #1 cause of broken builds.

Search order:
1. `find_operator_examples(operator=...)` — working snippets
2. `find_operator_combination(operator_types=['CHOP:noise','TOP:level'])`
3. `find_similar_networks(example_id=...)` — broader pattern match
4. `get_operator_info(operator_name=..., compact=True)` — params, families
5. `get_parameter_detail(operator_name=..., parameter_name=...)` — one param
6. `hybrid_search(query=...)` — fallback semantic search

Take the exemplar and adapt — don't paraphrase from memory. If the KB has no
exemplar, say so explicitly; an admitted gap is correct behavior, a guessed
parameter is not. Never claim an operator exists without a KB hit backing it.

If a KB tool returns `{"status": "kb_warming", "retry_after_seconds": N}`, the
vector DB is still loading (1–2 min on a fresh server). Wait and retry — do
NOT fall back to guessing because the KB is slow.

## Offline build discipline

- `td_build_project(design=..., mode="tox"|"toe", project_name=...,
  output_dir=...)` — ALWAYS pass `output_dir`; never build into a default
  location. Use the exact output directory the user names.
- Design ops use the BASE type plus family: `{"type":"noise","family":"TOP"}`
  — never the suffixed live form (`noiseTOP` is rejected).
- Expression mode = `{"expr": "op('lfo1')['chan1']"}` as a parameter value; a
  plain value is a constant. Keep op references RELATIVE (sibling names).
- GLSL ops: put the shader source in the op's `"shader"` field; the builder
  auto-docks and file-backs the pixel/compute DATs. A GLSL TOP does NOT
  auto-declare Vectors-page scalar uniforms — declare `uniform float uName;`
  in the source AND set `vec0name`. A GLSL POP auto-declares Arrays-page
  uniforms as float arrays — index `uName[0]`, never redeclare it.
- Derivative palette components: embed by name with the per-operator field
  `palette`, and give the op a real type so validation can see it:
  `{"type": "container", "family": "COMP", "name": "analysis",
  "palette": "audioAnalysis"}`. Other .tox files on disk: same shape with
  `{"external_tox": "<path>"}` — the file is referenced, not embedded.
- Known validator limitation: td_validate cannot see INSIDE palette/external
  components, so wires crossing their boundary (`analysis/out1`, comp
  in-wires) report reference errors even when the build wrote them correctly.
  If the build succeeded and only such boundary references are flagged,
  report the limitation honestly and verify via the built files
  (expand_toe_file) instead of thrashing on redesigns.
- Multi-output components: pick outputs by inner op name in connections,
  e.g. `{"from": "analysis/out2", "to": "aux"}`.
- After building, run `td_validate(network=<the design>)` and confirm it
  passes; use `expand_toe_file` to inspect what actually landed on disk when
  the user asks for file-level evidence.
- Give every operator an explicit distinct `position` — never stack ops.

## Honesty rules

- Answer capability questions from KB lookups, not memory; report what the
  tools returned, including gaps and failures.
- Never fabricate an operator, parameter, or palette component name.
- If a build or validation fails, report the failure verbatim — do not claim
  success the files don't back up.

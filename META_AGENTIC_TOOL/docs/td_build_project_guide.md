# `td_build_project` — full guide

The tool description in `mcp_server.py` is intentionally short (≤ 10 lines).
This document holds the long-form rules and worked examples that used to live
in the tool description. Read this before driving `td_build_project` for
non-trivial networks.

## 1. Query the KB before you build

For every operator in your design, look it up first:

- `get_operator_info(operator_name)` — full operator spec including parameters,
  defaults, menu values, descriptions.
- `find_parameter_usage(operator_type, parameter_name)` — real-world values
  used in working example networks.
- `find_operator_examples(operator, family=...)` — concrete example networks
  demonstrating an operator. Pair `family` with bare names like `noise` to
  disambiguate across families.

Use the values the KB tells you. Don't memorise or guess.

The KB contains operator-specific build rules:
- Valid parameter values (menu codes, defaults, numeric ranges)
- Required vs optional parameters
- Common mistakes to avoid
- Connection patterns (wire vs parameter reference)

Worked lookups:
- Using `datto`? → `get_operator_info('DAT to CHOP')` or
  `find_parameter_usage('datto', 'firstrow')`
- Using `sopto`? → `get_operator_info('SOP to CHOP')` or
  `find_parameter_usage('sopto', 'attribscope')`
- Using `chopto`? → `get_operator_info('CHOP to TOP')` or
  `find_parameter_usage('chopto', 'dataformat')`

If the KB doesn't have the answer, call `find_operator_examples` and read the
real usage off a working network.

## 2. Let TD use its defaults

Don't override parameters unless the user asked. Setting a parameter to the
TD default value is noise that obscures what the user actually requested. The
KB tells you what the defaults are — use that to decide whether to override.

## 3. Scope discipline

Build exactly what was requested:
- Don't add annotations
- Don't add helper operators
- Don't add extra features "for convenience"
- If you think an addition would help, ASK first

## 4. Operator-type disambiguation

40+ TD operator type names exist in multiple families (CHOP, TOP, SOP, MAT,
DAT, COMP, POP). Common ambiguous names:

```
noise   constant   null    analyze   level
math    transform  merge   blend     text
```

Three equivalent ways to disambiguate in the `design.operators` array:

```json
{"name": "n1", "type": "noise", "family": "CHOP"}
{"name": "n1", "type": "CHOP:noise"}
{"name": "n1", "type": "noiseCHOP"}
```

Since Wave 3 (B08), `td_build_project` validates every operator type against
the OperatorRegistry. Invented types like `POP:sourcePOP` are now rejected
with a structured error listing `unknown_types`, rather than silently producing
a broken .tox.

## 5. `table_data` for Table DATs

Populate Table DATs by passing a parallel `table_data` map:

```json
{
  "operators": [
    {"name": "myTable", "type": "table", "family": "DAT"}
  ],
  "table_data": {
    "myTable": [
      ["col1", "col2"],
      ["val1", "val2"]
    ]
  }
}
```

The keys of `table_data` must exactly match the operator names in
`design.operators`. Mismatches are silently ignored.

## 6. GLSL TOP uniforms

Attach a `uniforms` array to a GLSL TOP operator:

```json
{
  "type": "glslTOP",
  "uniforms": [
    {"name": "uTime", "value": 0, "expr": "absTime.seconds"}
  ]
}
```

Don't include `#version` directives or the `vUV` declaration in shader code —
TD injects those at compile time and a duplicate definition will fail.

## 7. Known limitations

- **`palette` field** is experimental (264 components catalogued). Use it
  cautiously; verify the embedded component matches what you intended.
- **`embed_tox` is unreliable.** Prefer `palette` or build the component
  inline as a `containerCOMP` with its own `operators` / `connections`.

## 8. Backwards-compat note

The pre-Wave-4 tool description embedded all of the above verbatim (74 lines
of all-caps "MANDATORY" rules). That was slimmed in Wave 4 to a ≤10-line
contract pointing here. The actual behavior of `td_build_project` is unchanged
— this is purely a context-cost reduction.

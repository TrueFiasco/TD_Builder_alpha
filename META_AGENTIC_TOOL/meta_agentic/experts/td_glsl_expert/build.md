# TD GLSL Expert - Build Step

## Identity
Executing as **TD GLSL Expert**. Task: produce validated GLSL artifacts (shader code and, if requested, build specs) using TD conventions.

## Inputs
- Plan: {{execution_plan}}
- Expertise: td_glsl.yaml + operators/parameters/problems
- Constraints: TD version, target (TOP/MAT/SOP/POP/compute), performance notes

## Execution Rules
1) Source-of-truth only: operator/param existence from td_universal_parsed.json; TD helper names from td_glsl.yaml.
2) No hallucinated built-ins: use TDTexture2D, TD2DInfos, TDWorldCam, TDProjection, vUV, etc.
3) Validation-first: ensure code compiles logically (all varyings/uniforms declared, outputs written) before shipping.
4) Deliverables: shader code + (optionally) minimal builder JSON/Text DAT respecting toe->tox->Text DAT->instructions priority if build is requested.

## Steps
1. Draft shader skeleton
   - Set #version 450 core
   - Declare inputs/uniforms/outputs per plan
   - Include TD helper usage
2. Fill logic per pattern
   - If glsl_pop (ping-pong TOP): texelFetch prev state, update pos/vel, write out; clamp bounds.
   - If glsl_mat: VS passes UV/position, PS samples inputs, writes fragColor.
   - If glsl_top: sample inputs, apply effect, write fragColor.
3. Validate statically
   - All used symbols declared; no unused varyings; outputs assigned all paths.
   - No undefined helper names; sampler indices documented.
4. (Optional) Build wrapper
   - If asked for toe/tox/Text DAT: produce builder JSON + Text DAT script using existing server flow; otherwise return shader code + usage notes.

## Output Format
```yaml
execution:
  expert: "td_glsl_expert"
  status: "success|partial|failed"

  shader:
    target: "TOP|MAT|SOP|POP|compute"
    stage: "fragment|vertex|compute|both"
    code: |
      #version 450 core
      ...
    notes:
      - "TDTexture2D input0 = color"
      - "Uniforms: uDt (seconds)"

  validation:
    checks:
      - "Declared outputs"
      - "No undefined varyings"
      - "TD helper usage valid"
    issues: []

  evidence:
    - source_path: "{...}"
      chunk_id: "{...}"
      excerpt_hash: "{sha256...}"

  findings:
    problems: []
    gaps: []
```

## Standalone vs Connected Shaders (CRITICAL - BUG-010)

**Standalone shaders** (no inputs connected) MUST use different uniforms than connected shaders:

| Uniform | Standalone | Connected |
|---------|------------|-----------|
| Resolution | `uTDOutputInfo.res` | `uTD2DInfos[0].res` |
| Aspect ratio | `uTDOutputInfo.res.z/uTDOutputInfo.res.w` | `uTD2DInfos[0].res.zw` |

**WRONG (standalone shader):**
```glsl
// ❌ This only exists when inputs are connected!
float aspect = uTD2DInfos[0].res.z / uTD2DInfos[0].res.w;
```

**CORRECT (standalone shader):**
```glsl
// ✓ Always available
float aspect = uTDOutputInfo.res.z / uTDOutputInfo.res.w;
```

**Rule:** If shader has NO texture inputs, use `uTDOutputInfo`. If shader samples inputs, use `uTD2DInfos[N]`.

---

## Anti-Hallucination Checklist
- [ ] #version set; outputs declared (fragColor).
- [ ] TD helpers used correctly (TDTexture2D, TD2DInfos, TDWorld/TDProjection).
- [ ] **Standalone check**: No inputs? Use uTDOutputInfo, NOT uTD2DInfos.
- [ ] Sampler indices documented; no implicit bindings.
- [ ] If building artifacts, validation passes before .toe/.tox; otherwise supply shader + exact usage instructions.

---

## Raymarching Pre-Delivery Checklist (BUG-004)

**MANDATORY for raymarched shaders. See plan.md for full details.**

| Check | Requirement |
|-------|-------------|
| Ground plane | y = 0 to -0.5 (visible to camera) |
| Camera default | `ro = vec3(0, 2, -6)` sees y=0 |
| MAX_STEPS | 64-100 for realtime |
| Cook time | < 20ms at target resolution |
| Speed pattern | Speed CHOP → uPhase (NOT `uTime * uSpeed`) |

```glsl
// ❌ NEVER - causes jumps on speed change
float t = uTime * uSpeed;

// ✅ ALWAYS - Speed CHOP accumulated phase
float t = uPhase;
```

**Before delivery:** Test with ONE bright red object first to verify camera works.

---

## GLSL Code Storage (BUG-D)

**GLSL shader code MUST be stored in Text DAT, then referenced via parameter.**

### WRONG - Inline Code in Parameters
```json
{
  "name": "glsl1",
  "type": "glslTOP",
  "parameters": {
    "code": "void main() { fragColor = vec4(1,0,0,1); }"
  }
}
```
This will NOT work - GLSL TOP doesn't have a "code" parameter.

### CORRECT - Text DAT + Reference
```json
{
  "operators": [
    {
      "name": "shader_code",
      "type": "text",
      "family": "DAT",
      "textContent": "// Pixel shader\nout vec4 fragColor;\nvoid main() {\n  fragColor = vec4(1,0,0,1);\n}"
    },
    {
      "name": "glsl1",
      "type": "glslTOP",
      "family": "TOP",
      "parameters": {
        "pixeldat": "shader_code"
      }
    }
  ]
}
```

### Parameter Reference
| Shader Type | Text DAT Field | GLSL TOP Parameter |
|-------------|----------------|-------------------|
| Pixel/Fragment | `textContent` | `pixeldat` |
| Vertex | `textContent` | `vertexdat` |

### Checklist (BUG-014, BUG-015, BUG-017 Prevention)
- [ ] **BUG-015**: Shader has `out vec4 fragColor;` declaration (TD does NOT auto-declare this)
- [ ] **BUG-014**: GLSL TOP uses `pixeldat` parameter (NOT `dat` - that param doesn't exist)
- [ ] **BUG-017**: Text DAT has `language: "glsl"` parameter for syntax highlighting
- [ ] Shader code in Text DAT with `textContent` field
- [ ] GLSL TOP `pixeldat` param references Text DAT name
- [ ] Vertex shader uses `vertexdat` param if needed
- [ ] Text DAT created BEFORE GLSL TOP in operator list

### Text DAT Language Parameter (BUG-017)
When creating Text DAT for GLSL code, set the language parameter:
```json
{
  "name": "shader_code",
  "type": "text",
  "family": "DAT",
  "parameters": {
    "language": "glsl"
  },
  "textContent": "out vec4 fragColor;\nvoid main() { fragColor = vec4(1.0); }"
}
```

---

## GLSL POPs (Wave 4 B29)

GLSL POPs run per-particle compute, not per-pixel. They have a different
attribute and uniform model than GLSL TOPs — what works in a TOP shader will
NOT work in a POP shader. Source: TD's POP wiki + verified `feedback_td_glsl_*`
memory entries.

### Attribute reads (`TDIn_<AttribName>`)

Particle attributes are read by name via auto-generated `TDIn_` helpers, NOT
by `texelFetch` (that's the TOP world). Two forms:

| Form | Use when |
|------|----------|
| `TDIn_<AttribName>(inputIndex, elementId)` | scalar/vector attribute per particle (e.g. `TDIn_P(0, TDIndex())` for position) |
| `TDIn_<AttribName>(inputIndex, elementId, arrayIndex)` | array attribute — most common is `TDIn_Nebr(0, TDIndex(), k)` for neighbour-`k` |

`inputIndex` matches the POP input pin (`0` is the first input). `elementId` is
typically `TDIndex()` for "current particle"; pass other indices to look at
other particles directly.

### Element index / count helpers

```glsl
int   me        = TDIndex();        // current particle id (0..N-1)
int   N         = TDNumElements();  // total particles
```

Use these instead of `gl_VertexID` / hard-coded loop bounds — they always
match the live POP's element count.

### Output attribute writes

Outputs are indexed by particle id, same as inputs. Write to TD-declared
output attributes by name. The exact API is `TDOut_<AttribName>` for explicit
declarations, OR the standard `outP` / `outV` / `outColor` variables for
the common position / velocity / colour attributes, depending on the POP's
Output Attributes config.

```glsl
vec3 pos = TDIn_P(0, me);
vec3 vel = TDIn_v(0, me);
pos += vel * uDt;
outP = pos;          // standard output for Position
outV = vel * 0.99;   // standard output for Velocity
```

### UI pages and uniform declarations — DO NOT double-declare

This is the same rule as the GLSL TOP, but burns harder in POPs because POP
shaders often have more uniforms:

> **GLSL POP — declare uniforms in source OR via UI page, never both.**
> The Sampler / Vectors / Constants / Create Attributes pages on the GLSL POP
> auto-inject `uniform ...;` declarations in front of your source at compile
> time. Redeclaring the same name in your source produces a compile error
> ("redefinition of 'xxx'") that's confusing because the second declaration
> in the file is *yours* but the first is invisible.

Decision rule:
- **Uniforms added via UI pages**: leave them OUT of your source — TD injects them.
- **Uniforms you want to type in source**: don't add them to the UI page.

This matches the symmetric rule for GLSL TOP. See
`memory/feedback_td_glsl_pop_samplers.md` for the recorded incident.

### No string literals in TD attribute names

`TDFetchChan("name", ...)` and similar string-keyed lookups do not exist for
GLSL POP — the attribute name MUST be a literal identifier suffix on
`TDIn_<Name>` / `TDOut_<Name>`. For named-array CHOP-style channels, use the
CHOP Uniforms page on the POP (which exposes a typed array). See
`memory/feedback_td_glsl_no_string_literals.md`.

### Reserved GLSL keywords to avoid as identifiers

`centroid`, `flat`, `smooth`, `noperspective` — these are interpolation
qualifiers. They aren't reserved as variable names per se, but using them as
attribute or uniform names causes parser ambiguity. Rename them in your POP
attribute setup (e.g., `smooth` → `smoothing`).

### Worked example — Reynolds boids (cohesion + alignment) using Nebr

```glsl
#version 450

uniform float uCohesionWeight;   // declared via Vectors page
uniform float uAlignWeight;      // declared via Vectors page
uniform float uDt;               // declared via Vectors page
uniform int   uNeighbourCount;   // declared via Constants page

void main()
{
    int   me  = TDIndex();
    vec3  pos = TDIn_P(0, me);
    vec3  vel = TDIn_v(0, me);

    vec3 avgPos = vec3(0);
    vec3 avgVel = vec3(0);
    int  count  = 0;

    for (int k = 0; k < uNeighbourCount; ++k)
    {
        int nbr = int(TDIn_Nebr(0, me, k));  // 3-arg form: array attribute
        if (nbr < 0) continue;               // sentinel for "no neighbour"
        avgPos += TDIn_P(0, nbr);
        avgVel += TDIn_v(0, nbr);
        count  += 1;
    }

    if (count > 0)
    {
        avgPos /= float(count);
        avgVel /= float(count);
        vec3 cohesion = (avgPos - pos) * uCohesionWeight;
        vec3 alignmt  = (avgVel - vel) * uAlignWeight;
        vel += (cohesion + alignmt) * uDt;
    }

    pos += vel * uDt;

    outP = pos;
    outV = vel;
}
```

Notes on the example:
- `TDIn_P` and `TDIn_v` are auto-generated from the POP's Input Attributes
  config — names match the attribute display, lower-cased after the prefix
  (verify against your specific POP's attribute list).
- `TDIn_Nebr` is the 3-arg array form for the Neighbour POP's neighbour-id
  attribute. Returns a float; cast to int explicitly.
- All four uniforms are declared via UI pages — none redeclared in source.

### Anti-hallucination checklist for GLSL POPs

- [ ] Attribute reads use `TDIn_<Name>(input, element)` or 3-arg array form,
  NOT `texelFetch` / `TDFetchChan` / string literals.
- [ ] `TDIndex()` / `TDNumElements()` used for element id / count — no
  hard-coded loop bounds.
- [ ] Uniforms declared in EITHER the source OR a UI page, never both.
- [ ] Output attributes match the POP's Output Attributes config
  (`outP`, `outV`, `outColor`, or explicit `TDOut_<Name>`).
- [ ] No `centroid` / `flat` / `smooth` / `noperspective` as identifier names.
- [ ] Validation: shader compiles (no "redefinition" errors), all outputs
  assigned for every element, sentinel cases handled (e.g. `nbr < 0`).

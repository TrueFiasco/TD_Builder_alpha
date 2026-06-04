# Technical Deep Dive: How It Actually Works

This document provides detailed answers to technical questions about the system's actual behavior.

---

## Q1: What does `query_knowledge_base_comprehensive()` actually return?

### Function Location
`meta_agentic/execution/strategy_runner.py:43`

### Return Structure
```python
kb_results = {
    "operators": {},           # Dict of operator lists by family
    "patterns": [],            # List of pattern NAMES only
    "glsl": {},                # GLSL template references
    "python": {},              # Python pattern references
    "palette_recommendations": [],  # Palette component names
    "query_timestamp": ""
}
```

### Actual Output for Teardrop Prompt
```yaml
palette:
  - changeColor
  - changeToColor
  - colorThreshold
  - audioAnalysis
  - audioSet
  - particlesGpu
  - pointRender
  - bloom
  - hsvBlur
  - lightTunnel

operators:
  audio_chops: 1    # Just a COUNT, not actual operators
  chops: 5
  tops: 3
  sops: 3
  pops_note: 1      # Just a string note

patterns:
  - audio_reactive_visuals   # NAME only, not the full pattern
  - particle_system

glsl:
  - glsl_top
  - glsl_mat
```

### The Problem
The query returns pattern **names**, not pattern **contents**. The `audio_reactive_visuals` pattern has a full `typical_chain` with 5 steps, connections, and parameters in `td_network_patterns.yaml` - but the query only returns the string `"audio_reactive_visuals"`, not its definition.

### Query Logic
```python
# Keyword-based filtering (hardcoded)
if any(kw in prompt_lower for kw in ["audio", "sound", "music", "beat"]):
    audio_chops = kb.query_operators({"family": "CHOP", "purpose_contains": "audio"})
    kb_results["operators"]["audio_chops"] = audio_chops[:10]

if any(kw in prompt_lower for kw in ["visual", "particle", "image", "render"]):
    top_ops = kb.query_operators({"family": "TOP"})
    kb_results["operators"]["tops"] = top_ops[:20]
```

---

## Q2: What's in the expertise files TD Designer loads?

### td_network_patterns.yaml - Has Full Chain Details

**Yes, the data exists.** Example `audio_reactive` pattern:

```yaml
audio_reactive:
  description: "Drive visuals from audio input"
  complexity: "medium"
  families: ["CHOP", "TOP"]
  confidence: 0.9

  hierarchy:
    - name: "audioIn1"
      type: "audiodeviceinCHOP"
    - name: "analyze1"
      type: "analyzeCHOP"
    - name: "math1"
      type: "mathCHOP"

  connections:
    - from: "audioIn1"
      to: "analyze1"
      type: "wire"
    - from: "analyze1"
      to: "math1"
      type: "wire"
    - from: "math1"
      to: "visual_param"
      type: "expression"
      expression: "op('math1')['chan1']"

  parameters:
    - operator: "analyzeCHOP"
      param: "function"
      value: "rms"
      notes: "Peak for transients, RMS for energy"
    - operator: "mathCHOP"
      param: "range1"
      value: "0"
    - operator: "mathCHOP"
      param: "range2"
      value: "1"

  common_errors:
    - error: "No audio device"
      cause: "audiodevicein not configured"
      fix: "Set Device parameter to valid audio input"
    - error: "Values too large"
      cause: "Audio values not normalized"
      fix: "Use math CHOP to remap to 0-1 range"
```

### Available Design Patterns
- `instancing` - GPU instancing with geoCOMP
- `feedback_loop` - Visual trails with feedbackTOP
- `audio_reactive` - Audio-driven parameters
- `particle_system` - POP-based particles
- `render_pipeline` - 3D render setup
- `control_panel` - UI sliders/buttons
- `data_viz` - Data to geometry mapping
- `chop_instancing` - CHOP channels as transforms
- `glsl_integration` - Custom shaders
- `python_scripting` - Python expressions

### The Problem
The prompt tells TD Designer to "check td_network_patterns.yaml for matches" but doesn't **inject** the actual pattern content. TD Designer has to rely on what's loaded via `load_expertise_for_expert()`.

---

## Q3: What does TD Designer's actual input look like?

### Prompt Rendering Process

1. Load `.md` template file (e.g., `plan.md`)
2. Load expertise files for this expert
3. Substitute placeholders with actual content
4. Send rendered prompt to LLM

### Placeholder Substitution (from expert_executor.py:275-290)

```python
# Add expertise content if available
if "expertise" in context:
    expertise_yaml = context["expertise"]["yaml"]

    # Add all expertise files as YAML
    for file_name, yaml_content in expertise_yaml.items():
        key = file_name.replace(".yaml", "_yaml")
        substitutions[key] = yaml_content

    # Combined expertise
    combined_expertise = "\n\n".join([
        f"# {file_name}\n{yaml_content}"
        for file_name, yaml_content in expertise_yaml.items()
    ])
    substitutions["expertise_yaml"] = combined_expertise
```

### What TD Designer Actually Receives

**Expertise loaded at init:**
```python
expertise_mapping = {
    "td_designer": [
        ExpertiseFiles.OPERATORS,    # td_operators.yaml (600+ operators)
        ExpertiseFiles.PATTERNS,     # td_network_patterns.yaml (full patterns)
        ExpertiseFiles.PARAMETERS    # td_parameters.yaml
    ],
}
```

**Blackboard sections injected:**
- `§1_requirements` - Original prompt
- `§2_creative_vision` - Creative expert output
- `§3_technical_approach` - CG expert output
- `§4_available_resources` - KB query results (pattern NAMES only)

### The Gap

§4 contains pattern **names** from `query_knowledge_base_comprehensive()`.
Expertise files contain pattern **definitions** from `load_expertise_for_expert()`.

These are loaded separately. The prompt doesn't explicitly say "use the pattern definition from your expertise for the pattern name in §4."

---

## Q4: Example Run Logs

### Teardrop V2 - Successful Run

**TD Designer Output** (04_td_designer.yaml):

```yaml
network_design:
  project: "teardrop"
  resolution: [1920, 1080]
  fps: 60

  containers:
    - name: "audio"
      purpose: "Audio input and analysis"
      operators: 12 operators (audiodevicein, spectrum, filters, analyze, nulls)

    - name: "core"
      purpose: "Radial core with feedback and displacement"
      operators: 10 operators (constant, ramp, noise, displace, lookup, feedback, composite, level, blur, null)

    - name: "particles"
      purpose: "GPU particle tendrils with curl noise"
      operators: 5 operators (particlesgpu, forcegpu, pointrender, level, null)

    - name: "rays"
      purpose: "Volumetric rays from bright regions"
      operators: 5 operators (switch, threshold, blur, composite, null)

    - name: "glitch"
      purpose: "RGB split and displacement glitch layer"
      operators: 6 operators (constant, reorder, noise, displace, level, null)

    - name: "composite_final"
      purpose: "Final layer composition and bloom"
      operators: 6 operators (composite x3, bloom, level, out)

  connections: ~35 wire connections
  expressions: 11 audio-reactive expressions
  exports: 5 parameter exports
```

### Why It Worked

1. **Execution mode**: Claude Code Task agent (not stub executor)
2. **Full reasoning**: Agent could interpret the prompt freely
3. **Rich context**: Had creative_expert and cg_expert outputs
4. **Detailed prompt**: "Teardrop - Massive Attack, heartbeat pulse, tendril growth, harpsichord glitch"

### No Failed Run Logs Available

We don't have captured logs from runs that produced empty/scattered output. The scaffolded runs were done interactively without saving intermediate state.

---

## Q5: What Was Different About Teardrop?

### Key Differences

| Aspect | Teardrop Run | Typical API Run |
|--------|--------------|-----------------|
| Executor | Claude Code Task agent | Stub or AnthropicExecutor |
| Reasoning | Free-form Claude reasoning | Constrained to prompt template |
| Context | Full conversation context | Only rendered prompt |
| Builder | Separate `build_teardrop.py` script | network_builder agent (stubbed) |

### The Real Builder

The actual TOE file was created by `build_teardrop.py` - a **hardcoded script** that:
1. Uses ToeBuilder class directly
2. Embeds audioAnalysis from expanded .tox.dir
3. Creates specific operators by name
4. Writes expressions (guessed paths)

**TD Designer's YAML output never went through the actual builder pipeline.**

### What Actually Happened

```
User Prompt
    ↓
Task Agent: Creative Expert → YAML output
    ↓
Task Agent: CG Expert → YAML output
    ↓
Task Agent: TD Designer → YAML output (good design)
    ↓
Task Agent: Critic → PASS
    ↓
Task Agent: Builder → YAML structure (not actual TOE)
    ↓
MANUALLY: build_teardrop.py → teardrop_full.toe
```

The gap is between TD Designer's YAML and actual TOE generation.

---

## Summary: Where the System Breaks Down

| Component | Status | Issue |
|-----------|--------|-------|
| KB Query | Returns names | Should return full pattern definitions |
| Expertise Loading | Loads full files | Not explicitly linked to §4 results |
| Prompt Injection | Content injected | No instruction to use patterns for matching names |
| TD Designer | Produces good YAML | Output not consumed by builder |
| Builder Agent | Stubbed | Doesn't call ToeBuilder |
| Actual Build | Manual script | Hardcoded, not using agent output |

### Fix Priority

1. **P0**: Make builder agent actually call ToeBuilder with TD Designer's YAML
2. **P1**: Have KB query return full pattern definitions, not just names
3. **P2**: Add explicit instruction: "Use the pattern definition from expertise for matched pattern name"

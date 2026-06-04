# Example Runs: Successful and Failed

This document provides examples of actual workflow runs to illustrate what success and failure look like.

---

## Successful Run: Teardrop V2

**Prompt**: "Create an audio-reactive visualization for Teardrop by Massive Attack"

### Workflow Summary

```yaml
project:
  name: "Teardrop"
  artist: "Massive Attack"
  duration: "5:29"
  resolution: [1920, 1080]
  fps: 60

workflow:
  strategy: "V2"
  method: "Claude Code Subagent Orchestration"
  total_agents: 5
```

### Step-by-Step Log

#### Step 1: KB Query (Python, local)
```yaml
agent: "KB Query"
type: "Python (local)"
input_tokens: ~200
output_tokens: ~150

result:
  palette_items: 10
  operator_families: 5
  patterns: 2
  glsl_entries: 2

# Key findings:
palette_recommended:
  - audioAnalysis: "Extract frequency bands"
  - popNetwork: "GPU particles"

operators_found:
  - noiseTOP, blurTOP, compositeTOP, feedbackTOP
  - bloomTOP, hsvadjustTOP
  - geoCOMP, containerCOMP

patterns_matched:
  - audio_reactive_visuals
  - instancing_workflow
```

#### Step 2: Creative Expert (Task agent)
```yaml
agent: "Creative Expert"
agent_id: "a840f79"
input_tokens: ~1500
output_tokens: ~2000

result:
  concept: "Vessel of Becoming"

  mood:
    primary: "ethereal"
    modifiers: ["melancholic", "organic"]

  phases: 8
    - intro (emerging)
    - verse_1 (intimate)
    - chorus_1 (emotional peak)
    - verse_2 (deeper)
    - chorus_2 (soaring)
    - bridge (transcendent)
    - final_chorus (cathartic)
    - outro (fading)

  color_palette:
    primary: "#1a1a2e"    # Deep blue-black
    secondary: "#16537e"  # Ocean blue
    accent: "#f4a261"     # Warm amber

  audio_mapping:
    bass: "breathing, expansion"
    mids: "color warmth, saturation"
    highs: "sparkle, detail"
    vocals: "brightness, bloom"
```

#### Step 3: CG Expert (Task agent)
```yaml
agent: "CG Expert"
agent_id: "a315b0d"
input_tokens: ~1800
output_tokens: ~2200

result:
  render_layers: 5
    - background (procedural noise)
    - base_visual (composite)
    - effects (feedback, blur)
    - particles (optional)
    - output (bloom, final)

  operator_chain: 8 stages
    - audio_input
    - analysis
    - generation
    - modulation
    - compositing
    - effects
    - color_grade
    - output

  data_flow_mappings: 7
    - audio.low → noise.amp
    - audio.mid → hsv.saturation
    - audio.high → bloom.threshold
    - etc.
```

#### Step 4: TD Designer (Task agent)
```yaml
agent: "TD Designer"
agent_id: "a37ef69"
input_tokens: ~2000
output_tokens: ~3500

result:
  containers: 6
    - project1 (root)
    - audio (analysis)
    - visual (generation)
    - effects (processing)
    - output (final)
    - control (parameters)

  operators: ~40
    # Audio
    - audioAnalysis (palette embed)

    # Visual
    - noise1 (noiseTOP)
    - ramp1 (rampTOP)
    - comp1 (compositeTOP)
    - feedback1 (feedbackTOP)

    # Effects
    - blur1 (blurTOP)
    - hsv1 (hsvadjustTOP)
    - bloom1 (bloomTOP)

    # Output
    - out1 (outTOP)
    - window1 (windowCOMP)

  connections: ~35
  expressions: 11
  exports: 5
```

#### Step 5: Critic (Task agent)
```yaml
agent: "Critic"
agent_id: "a0a0fad"
input_tokens: ~1200
output_tokens: ~600

result:
  criteria_scores:
    creative: 0.92
    technical: 0.88
    design: 0.85

  overall_score: 0.88
  threshold: 0.65
  verdict: "PASS"

  issues_found: 5 (all minor)
    - "No frame rate lock operator"
    - "Glitch threshold not explicit"
    - "No audio file fallback"
    - "Bloom envelope not smoothed"
    - "Phase automation not keyframed"

  strengths:
    - "Strong emotional alignment with Teardrop mood"
    - "Good use of audioAnalysis palette"
    - "Feedback creates organic breathing feel"
```

#### Step 6: Builder (Task agent)
```yaml
agent: "Builder"
agent_id: "a1af09e"
input_tokens: ~1500
output_tokens: ~3000

result:
  containers: 6
  total_operators: 38
  python_scripts: 2

  files_generated:
    - teardrop.toe (137KB)
    - teardrop_design.yaml
    - workflow_summary.yaml
```

### Token Summary

```yaml
total_tokens: ~19,650

breakdown:
  kb_query: 350
  creative_expert: 3500
  cg_expert: 4000
  td_designer: 5500
  critic: 1800
  builder: 4500
```

### Final Output

```
teardrop_full.toe (137KB)
├── project1/
│   ├── audio/
│   │   └── audioAnalysis (3,080 files from palette)
│   ├── visual/
│   │   ├── noise1, ramp1, comp1
│   │   ├── feedback1, blur1, hsv1
│   │   └── bloom1
│   └── output/
│       ├── out1
│       └── window1
└── local/ (system files)
```

---

## Failed Run Example: Scattered Output

**Prompt**: "Make something cool with particles"

### What Went Wrong

#### Step 2: Creative Expert - Vague Output
```yaml
agent: "Creative Expert"
status: "completed but weak"

result:
  concept: "Particle Magic"  # Too vague

  mood:
    primary: "dynamic"  # Not from vocabulary!
    modifiers: []

  # Missing:
  # - color_palette
  # - phases
  # - emotional_mapping

  confidence: 0.45  # Low confidence
```

**Issue**: The vague prompt led to a vague creative response. "Dynamic" is not in the defined mood vocabulary.

#### Step 3: CG Expert - Cascading Failure
```yaml
agent: "CG Expert"
status: "completed but incomplete"

result:
  technique_selection:
    primary: "particles"
    # No secondary techniques

  render_layers: 1  # Only one layer
  data_flow_mappings: 0  # No mappings!
```

**Issue**: Without clear creative direction, CG expert couldn't determine technical approach.

#### Step 5: Critic - FAIL
```yaml
agent: "Critic"
result:
  overall_score: 0.42  # Below 0.65 threshold
  verdict: "FAIL"

  blocking_issues:
    - severity: "high"
      type: "vague_mood"
      description: "Mood 'dynamic' not from defined vocabulary"

    - severity: "high"
      type: "missing_data_flow"
      description: "No audio/input mappings defined"

    - severity: "high"
      type: "incomplete_spec"
      description: "Color palette not specified"

  decision: "revise"
  revision_cycle: 1
```

### Revision Attempt

After critic feedback, the system attempted revision:

#### Revision Cycle 1
```yaml
creative_expert_retry:
  mood:
    primary: "chaotic"  # Now from vocabulary
    modifiers: ["organic"]

  confidence: 0.62  # Better but still weak

critic_review:
  overall_score: 0.58  # Still below threshold
  issues:
    - "Still no clear emotional arc"
    - "Color palette generic"
```

#### Revision Cycle 2
```yaml
overall_score: 0.61  # Getting closer

issues:
  - "Particle behavior not specified"
```

#### Revision Cycle 3 - Max Cycles Reached
```yaml
revision_cycle: 3
max_cycles: 3

escalation:
  decision: "fail"
  reason: "Exceeded maximum revision cycles"
  recommendation: "Human review required"

  pattern_detected:
    issue: "Vague initial prompt leads to cascading underspecification"
    suggestion: "Ask user for more details before starting workflow"
```

---

## Partial Success: Ruth Test

**Prompt**: "Create a meditative generative visual piece with flowing organic forms"

### What Worked
- Creative expert produced strong mood/color spec
- CG expert designed good technique stack
- TD Designer created valid network

### What Failed
- Builder produced YAML only, not actual TOE file
- Expression paths were guessed, not validated
- No display/window operator for output

### Logs

```yaml
workflow_status: "partial_success"

completed_steps:
  - creative_vision: PASS
  - technical_approach: PASS
  - network_design: PASS
  - critic_review: PASS (0.78)

failed_steps:
  - build: "YAML only, no TOE"
  - validation: "Cannot validate without TD"

issues_discovered:
  - "Builder needs ToeBuilder integration"
  - "Expression paths need validation"
  - "Missing output operators"
```

---

## Comparison Table

| Aspect | Teardrop (Success) | "Cool Particles" (Fail) | Ruth (Partial) |
|--------|-------------------|-------------------------|----------------|
| Prompt clarity | High | Low | Medium |
| Creative score | 0.92 | 0.42 | 0.78 |
| Technical score | 0.88 | 0.38 | 0.75 |
| Critic verdict | PASS | FAIL (3 cycles) | PASS |
| Build result | 137KB TOE | N/A | YAML only |
| TD validation | Opens, needs fixes | N/A | N/A |

---

## Key Learnings

1. **Prompt Quality Matters**: Vague prompts lead to vague outputs
2. **Critic Catches Issues**: The revision cycle works but has limits
3. **Builder Gap**: YAML→TOE transition was missing (now fixed)
4. **Expression Validation**: Need to verify paths before build
5. **Display Operators**: Easy to forget output/window in spec

# Handoff Schema: Input/Output Formats

This document describes the format each agent receives as input and produces as output, with special attention to the Orchestra→Designer and Expert→Designer handoffs.

---

## Blackboard Section Schema

The blackboard is the central state store with 7 sections:

```python
class SectionID(Enum):
    REQUIREMENTS = "§1_requirements"        # User intent + constraints
    CREATIVE_VISION = "§2_creative_vision"  # Artistic direction, mood, style
    TECHNICAL_APPROACH = "§3_technical_approach"  # Techniques, tradeoffs
    AVAILABLE_RESOURCES = "§4_available_resources"  # Operators, palette, patterns
    NETWORK_DESIGN = "§5_network_design"    # JSON network + descriptions
    VALIDATION_HISTORY = "§6_validation_history"  # All critic reviews
    BUILD_ARTIFACTS = "§7_build_artifacts"  # Paths, validation results
```

---

## §1 Requirements (User Input)

**Written by**: Orchestrator (from user prompt)
**Read by**: creative_expert, cg_expert, td_designer, critic

```yaml
§1_requirements:
  original_prompt: "Create an audio-reactive particle visualization for Teardrop by Massive Attack"
  parsed_intent:
    goal: "audio-reactive visualization"
    style_hints: ["particle", "audio", "atmospheric"]
    constraints:
      resolution: [1920, 1080]
      fps: 60
      duration: "5:29"
    audio_source: "Teardrop - Massive Attack"
  priority: "creative_quality"
  timestamp: "2024-12-18T22:00:00Z"
```

---

## §2 Creative Vision (Creative Expert Output)

**Written by**: creative_expert
**Read by**: cg_expert, td_designer, critic

```yaml
§2_creative_vision:
  concept:
    name: "Vessel of Becoming"
    description: "Visualizing Teardrop as an emotional journey through liquid forms"

  mood:
    primary: "ethereal"
    modifiers: ["melancholic", "organic"]
    visual_markers:
      colors: ["deep blue", "cyan glow", "amber warmth"]
      motion: "slow, fluid, breathing"
      contrast: "medium"
      saturation: "medium-high"

  aesthetic:
    style: "organic"
    techniques: ["fluid simulation", "particle systems", "bloom"]

  color_palette:
    type: "analogous"
    primary: "#1a1a2e"      # Deep blue-black
    secondary: "#16537e"    # Ocean blue
    accent: "#f4a261"       # Warm amber
    highlight: "#e9c46a"    # Golden glow

  motion:
    quality: "fluid"
    speed: "slow to medium"
    character: "Breathing, expanding, contracting with audio"

  emotional_mapping:
    target: "melancholic beauty"
    audio_mapping:
      bass: "expansion, breathing"
      mids: "color intensity, saturation"
      highs: "particle sparkle, detail"
      vocals: "brightness, bloom"

  phases:
    - name: "intro"
      duration: "0:00-0:45"
      mood: "emerging"
    - name: "build"
      duration: "0:45-2:00"
      mood: "rising tension"
    - name: "chorus"
      duration: "2:00-3:30"
      mood: "emotional peak"
    - name: "outro"
      duration: "3:30-5:29"
      mood: "fading"

  confidence: 0.88
  author: "creative_expert"
  timestamp: "2024-12-18T22:01:00Z"
```

---

## §3 Technical Approach (CG Expert Output)

**Written by**: cg_expert
**Read by**: td_designer, td_glsl_expert, td_python_expert, critic

```yaml
§3_technical_approach:
  technique_selection:
    primary: "particle_systems"
    secondary: ["noise_displacement", "feedback", "compositing"]
    rationale: "Particles for organic motion, noise for fluid feel"

  render_layers:
    - name: "background"
      type: "procedural"
      operators: ["noiseTOP", "ramp"]
    - name: "particles"
      type: "instanced_geometry"
      operators: ["geoCOMP", "gridSOP", "sphereSOP"]
    - name: "effects"
      type: "post_process"
      operators: ["blur", "bloom", "feedback"]
    - name: "composite"
      type: "final"
      operators: ["compositeTOP"]

  data_flow:
    audio_input:
      source: "audioAnalysis palette"
      channels: ["low", "mid", "high", "level"]

    mappings:
      - source: "audio.low"
        target: "particle.scale"
        transform: "smooth, multiply 2"
      - source: "audio.mid"
        target: "color.saturation"
        transform: "lag 0.3s"
      - source: "audio.high"
        target: "bloom.intensity"
        transform: "direct"

  performance_targets:
    resolution: [1920, 1080]
    fps: 60
    gpu_budget: "mid-range"
    particle_count: 10000

  operator_chain:
    - stage: "audio_analysis"
      operators: ["audioAnalysis"]
    - stage: "generation"
      operators: ["noise", "ramp", "particles"]
    - stage: "processing"
      operators: ["blur", "hsvadjust", "feedback"]
    - stage: "compositing"
      operators: ["composite", "bloom"]
    - stage: "output"
      operators: ["out", "window"]

  confidence: 0.85
  author: "cg_expert"
  timestamp: "2024-12-18T22:02:00Z"
```

---

## §4 Available Resources (KB Query Results)

**Written by**: Orchestrator via KB queries
**Read by**: td_designer

```yaml
§4_available_resources:
  palette_components:
    - name: "audioAnalysis"
      path: "Palette/Tools/audioAnalysis.tox"
      purpose: "Extract frequency bands from audio"
      outputs: ["low", "mid", "high", "level"]
      recommended: true

    - name: "popNetwork"
      path: "Palette/POPs/popNetwork.tox"
      purpose: "GPU particle system"
      recommended: false

  operators:
    TOP:
      - {name: "noise", purpose: "Procedural noise generation"}
      - {name: "blur", purpose: "Gaussian blur"}
      - {name: "composite", purpose: "Layer compositing"}
      - {name: "feedback", purpose: "Frame feedback effects"}
      - {name: "hsvadjust", purpose: "Color adjustment"}
      - {name: "bloom", purpose: "Glow effect"}
    CHOP:
      - {name: "analyze", purpose: "Audio analysis"}
      - {name: "lag", purpose: "Value smoothing"}
      - {name: "math", purpose: "Mathematical operations"}
    COMP:
      - {name: "geo", purpose: "3D geometry container"}
      - {name: "container", purpose: "Organization"}

  patterns:
    audio_reactive:
      chain: ["audiofilein", "analyze", "math", "lag"]
      description: "Standard audio analysis pipeline"

    instancing:
      chain: ["gridSOP", "geoCOMP", "instanceTOP"]
      description: "GPU instancing pattern"

  timestamp: "2024-12-18T22:02:30Z"
```

---

## §5 Network Design (TD Designer Output)

**Written by**: td_designer
**Read by**: network_builder, critic, td_glsl_expert, td_python_expert

This is the **critical handoff** to the builder.

```yaml
§5_network_design:
  design:
    name: "teardrop_visualization"
    goal: "Audio-reactive particle visualization"
    pattern: "audio_reactive_visuals"
    created_by: "td_designer"
    timestamp: "2024-12-18T22:03:00Z"

  containers:
    - name: "project1"
      type: "containerCOMP"
      position: [0, 0]
      children:
        - name: "audio"
          type: "containerCOMP"
          note: "Audio analysis"
        - name: "visual"
          type: "containerCOMP"
          note: "Visual generation"
        - name: "output"
          type: "containerCOMP"
          note: "Final output"

  operators:
    # Audio container
    - name: "audio_analysis"
      type: "palette_embed"
      palette_source: "audioAnalysis"
      parent: "audio"
      position: [0, 0]

    # Visual container
    - name: "noise1"
      type: "noiseTOP"
      parent: "visual"
      position: [0, 0]
      parameters:
        type: "sparse"
        amp: 1.0
        period: [4, 4, 4]
        harmonics: 3

    - name: "ramp1"
      type: "rampTOP"
      parent: "visual"
      position: [150, 0]
      parameters:
        type: "radial"
        phase: 0.5

    - name: "comp1"
      type: "compositeTOP"
      parent: "visual"
      position: [300, 0]
      parameters:
        operand: "multiply"

    - name: "feedback1"
      type: "feedbackTOP"
      parent: "visual"
      position: [450, 0]
      parameters:
        target: "../comp1"

    - name: "blur1"
      type: "blurTOP"
      parent: "visual"
      position: [600, 0]
      parameters:
        size: [3, 3]

    - name: "hsv1"
      type: "hsvadjustTOP"
      parent: "visual"
      position: [750, 0]
      parameters:
        satmult: 1.2
        valmult: 1.1

    - name: "bloom1"
      type: "bloomTOP"
      parent: "visual"
      position: [900, 0]
      parameters:
        size: [10, 10]
        threshold: 0.8

    # Output container
    - name: "out1"
      type: "outTOP"
      parent: "output"
      position: [0, 0]

    - name: "window1"
      type: "windowCOMP"
      parent: "output"
      position: [150, 0]

  connections:
    # Visual chain
    - {from: "noise1", to: "comp1", input_index: 0}
    - {from: "ramp1", to: "comp1", input_index: 1}
    - {from: "comp1", to: "feedback1", input_index: 0}
    - {from: "feedback1", to: "blur1", input_index: 0}
    - {from: "blur1", to: "hsv1", input_index: 0}
    - {from: "hsv1", to: "bloom1", input_index: 0}
    - {from: "bloom1", to: "out1", input_index: 0}
    - {from: "out1", to: "window1", type: "reference", param: "op"}

  expressions:
    - operator: "noise1"
      param: "amp"
      expression: "op('../audio/audio_analysis/out1')['low'] * 2"

    - operator: "hsv1"
      param: "satmult"
      expression: "1 + op('../audio/audio_analysis/out1')['mid'] * 0.5"

    - operator: "bloom1"
      param: "threshold"
      expression: "0.9 - op('../audio/audio_analysis/out1')['high'] * 0.3"

  metadata:
    operators_count: 11
    connections_count: 8
    expressions_count: 3
    containers_count: 4
    validation_status: "pending"

  author: "td_designer"
  confidence: 0.85
```

---

## §6 Validation History (Critic Output)

**Written by**: critic
**Read by**: All experts (for revision guidance)

```yaml
§6_validation_history:
  reviews:
    - review_id: "REV-001"
      timestamp: "2024-12-18T22:04:00Z"
      review_type: "network_design"
      revision_cycle: 0

      criteria_scores:
        artistic_coherence: {score: 0.92, weight: 0.25}
        technical_feasibility: {score: 0.88, weight: 0.30}
        implementation_clarity: {score: 0.85, weight: 0.25}
        creative_alignment: {score: 0.90, weight: 0.20}

      overall_score: 0.88
      threshold: 0.65
      passed: true

      decision: "approve"
      verdict: "PASS"

      issues_found:
        - severity: "minor"
          type: "missing_fallback"
          description: "No audio file fallback if live input fails"
        - severity: "minor"
          type: "unsmoothed_values"
          description: "Bloom envelope not smoothed"

      strengths:
        - "Strong creative alignment with Teardrop mood"
        - "Good use of audioAnalysis palette"
        - "Feedback loop creates organic feel"

      handoff_notes:
        ready_for: "network_builder"
        notes: "Minor issues can be addressed in future iterations"
```

---

## §7 Build Artifacts (Builder Output)

**Written by**: network_builder
**Read by**: summary_generator

```yaml
§7_build_artifacts:
  build_result:
    status: "success"
    timestamp: "2024-12-18T22:05:00Z"
    builder: "ToeBuilder v4"

  output_files:
    - type: "toe"
      path: "output/teardrop.toe"
      size_bytes: 137000

    - type: "yaml"
      path: "output/teardrop_design.yaml"
      size_bytes: 4500

  contents:
    containers: 4
    operators: 11
    connections: 8
    expressions: 3
    palette_embeds: 1

  validation:
    file_exists: true
    toc_valid: true
    can_open: "untested"

  issues:
    - "Audio channel names may need adjustment after TD verification"
```

---

## Handoff Summary

```
User Prompt
    ↓
§1 Requirements (Orchestrator)
    ↓
Creative Expert → §2 Creative Vision
    ↓
CG Expert → §3 Technical Approach
    ↓
KB Queries → §4 Available Resources
    ↓
TD Designer → §5 Network Design
    ↓
Critic → §6 Validation History
    ↓ (if approved)
Network Builder → §7 Build Artifacts
    ↓
TOX/TOE File
```

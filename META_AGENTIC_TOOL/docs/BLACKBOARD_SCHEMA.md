# Blackboard Schema (PROJECT DOCUMENT)

## Overview

The PROJECT DOCUMENT is the central state storage for the agentic workflow. It serves as a "blackboard" where all agents read context and write their outputs. This enables:

- **Single source of truth** - No conflicting state between agents
- **Full audit trail** - Version history for every section
- **Partial re-work** - Fix §3 without redoing §2
- **Dynamic orchestration** - Orchestrator decides next action based on state

---

## Document Structure

```yaml
project_document:
  metadata:
    id: uuid
    created: timestamp
    modified: timestamp
    phase: creative | technical | resources | design | build | complete
    iteration: n
    config:
      strategy: v2 | v3 | v4 | v5 | v6
      involvement: full | milestone | minimal
      exploration: 1 | 3 | 5
      quality_targets:
        creative: 0.85
        technical: 0.85
        design: 0.90
        stretch_threshold: 0.95
      max_iterations: 10 | 20 | unlimited
      convergence_window: 2

  §1_requirements: {...}
  §2_creative_vision: {...}
  §3_technical_approach: {...}
  §4_available_resources: {...}
  §5_network_design: {...}
  §6_validation_history: {...}
  §7_build_artifacts: {...}
```

---

## Section Specifications

### §1 Requirements

Captures the user's intent, clarifications, and constraints.

```yaml
§1_requirements:
  original_prompt: "Create an audio-reactive particle system"

  clarifications:
    - question: "What audio source?"
      answer: "System audio input"
      timestamp: ...
    - question: "Color preference?"
      answer: "Cool blues to warm oranges"
      timestamp: ...

  constraints:
    - "Must work on laptop GPU"
    - "60fps minimum"
    - "No external files"

  must_haves:
    - "Audio reactivity on bass frequencies"
    - "Particle count responds to energy"
    - "Smooth transitions between states"

  nice_to_haves:
    - "Color palette shift based on frequency"
    - "Bloom/glow effects"

  feedback_additions:
    - source: "creative_review"
      addition: "User wants more organic movement"
      timestamp: ...
```

**Written by:** Orchestrator (initial), User (clarifications)
**Read by:** All agents

---

### §2 Creative Vision

The artistic direction and visual intent.

```yaml
§2_creative_vision:
  versions:
    - version: 1
      brief: |
        A breathing cosmos of light particles that pulse and swirl
        in response to audio. Bass frequencies trigger explosive bursts
        while high frequencies create delicate rippling trails. The color
        palette transitions from deep cosmic blues in quiet moments to
        burning oranges during peaks.

      visual_signature: "Bioluminescent organism breathing with sound"
      mood_keywords: ["ethereal", "organic", "breathing", "alive"]
      color_strategy: "Blue→Orange gradient mapped to energy"
      motion_quality: "Fluid, organic, non-mechanical"

      score: 0.78
      feedback: "Brief is evocative but lacks specific signature element"
      timestamp: ...

    - version: 2
      brief: |
        [Refined version with signature element added]
      score: 0.87
      feedback: "Strong vision, clear signature"
      timestamp: ...

  current: 2
  locked: false

  # If evolutionary strategy used:
  variants_explored: 3
  breeding_notes: "Merged A's boldness with B's coherence"
```

**Written by:** Creative Expert
**Read by:** CG Expert, TD Designer, Critic

---

### §3 Technical Approach

Technical strategy and implementation decisions.

```yaml
§3_technical_approach:
  versions:
    - version: 1
      summary: "Compute shader particle system with audio-driven forces"

      techniques:
        primary:
          name: "GLSL Compute Particles"
          rationale: "GPU-native, handles millions of particles"
          td_operators: ["glslTOP", "glslMAT", "feedback"]

        audio_analysis:
          name: "FFT + Envelope Followers"
          rationale: "Separate bass/mid/high + smooth envelope"
          td_operators: ["audioDeviceIn", "audioSpect", "math"]

        visual_pipeline:
          name: "Additive Compositing + Bloom"
          rationale: "Ethereal glow effect matching creative vision"
          td_operators: ["composite", "blur", "level"]

      tradeoffs:
        chosen: "Compute shader for particle physics"
        alternatives_considered:
          - name: "particlesSOP + renderTOP"
            rejected_because: "Lower particle counts, less control"
          - name: "Pre-rendered sprites"
            rejected_because: "Loses real-time reactivity"

      parameter_strategy:
        exposed:
          - "Master Intensity (0-1)"
          - "Bass Reactivity (0-2)"
          - "Particle Count (100-10000)"
        internal:
          - "Physics timestep"
          - "Attraction strength"

      score: 0.82
      feedback: "Solid approach, needs clearer audio→parameter mapping"
      timestamp: ...

  current: 1
  locked: false
```

**Written by:** CG Expert
**Read by:** TD Designer, TD GLSL Expert, Critic

---

### §4 Available Resources

Knowledge base query results relevant to this project.

```yaml
§4_available_resources:
  operators:
    audio:
      - family: CHOP
        name: audioDeviceIn
        relevance_score: 0.95
        reason: "Primary audio input"
      - family: CHOP
        name: audioSpect
        relevance_score: 0.90
        reason: "FFT analysis for frequency bands"

    visual:
      - family: TOP
        name: glslTOP
        relevance_score: 0.95
        reason: "Custom particle rendering"
      - family: TOP
        name: feedback
        relevance_score: 0.85
        reason: "Particle trails"

  palette_components:
    - name: "audioAnalysis.tox"
      inputs: ["audioIn"]
      outputs: ["low", "mid", "high", "envelope"]
      notes: "Pre-built audio analysis with smooth envelopes"
    - name: "particleBase.tox"
      inputs: ["spawnTrigger", "forces"]
      outputs: ["particlePositions", "particleColors"]
      notes: "Configurable compute particle system"

  example_patterns:
    - source: "patterns.yaml"
      name: "audio_reactive_color"
      description: "Map audio energy to color palette"
      operators_used: ["math", "lookup", "colorMix"]
    - source: "parsed_json"
      name: "envelope_follower"
      description: "Smooth audio envelope with attack/release"
      operators_used: ["math", "lag"]

  glsl_templates:
    - name: "particle_physics.glsl"
      purpose: "Basic attractor + noise forces"
      uniforms: ["uTime", "uForce", "uNoiseScale"]
    - name: "additive_glow.glsl"
      purpose: "Bloom-like additive compositing"
      uniforms: ["uGlowIntensity", "uGlowRadius"]

  parameter_options:
    standard_ranges:
      intensity: [0, 1]
      frequency: [0.01, 100]
      count: [1, 100000]
```

**Written by:** KB Query (automated)
**Read by:** TD Designer, TD GLSL Expert, TD Python Expert

---

### §5 Network Design

The actual TouchDesigner network specification.

```yaml
§5_network_design:
  versions:
    - version: 1
      description_visual: |
        The network creates a breathing particle cosmos. Audio flows through
        an analysis section that extracts bass energy and smooths it into
        organic envelopes. These drive a compute shader that simulates
        thousands of particles attracted to invisible force fields. The
        particles glow and leave trails, rendered in colors that shift
        from cool to warm based on audio intensity.

      description_technical: |
        Audio pipeline: audioDeviceIn → audioSpect → band splitting via
        math CHOPs → envelope followers with configurable attack/release.

        Particle system: GLSL compute shader using ping-pong buffers for
        position/velocity. Forces: central attractor + audio-modulated
        noise field. Rendering via instanced point sprites.

        Post-processing: additive composite of particles + trail buffer
        → bloom (blur + add) → final output with level correction.

      network:
        containers:
          - name: "project1"
            type: "baseCOMP"
            children:
              - name: "control_center"
                type: "baseCOMP"
                custom_parameters:
                  - name: "Masterintensity"
                    type: "Float"
                    default: 0.8
                    range: [0, 1]
                  # ... more params

              - name: "audio_analysis"
                type: "baseCOMP"
                # ... children

              - name: "particle_render"
                type: "baseCOMP"
                # ... children

      json: {...}  # Full network JSON for builder

      expert_consultations:
        - agent: "td_glsl_expert"
          question: "How to pass audio envelope to compute shader?"
          answer: "Use TOP → CHOP → uniform binding in glslTOP"
          incorporated: true
        - agent: "td_python_expert"
          question: "How to dynamically change particle count?"
          answer: "Use execute DAT with cook callback"
          incorporated: true

      score: 0.85
      feedback: "Clean architecture, verify uniform connections"
      timestamp: ...

  current: 1
  locked: false
```

**Written by:** TD Designer (with expert consultations)
**Read by:** Network Builder, Critic

---

### §6 Validation History

All validation attempts and results.

```yaml
§6_validation_history:
  entries:
    - id: uuid
      timestamp: ...
      phase: creative
      section_validated: §2
      version: 1
      validator: critic

      result:
        pass: false
        score: 0.78
        reasoning: |
          The brief captures the audio-reactive particle concept well but
          lacks a distinctive signature element that would make this
          memorable. "Breathing cosmos" is evocative but generic.

        issues:
          - classification: creative
            description: "No signature visual element"
            severity: blocking
            recommended_fix: "Add a unique hook - perhaps particles form recognizable shapes during peaks"

          - classification: creative
            description: "Color strategy could be more specific"
            severity: warning
            recommended_fix: "Define exact color values or reference a specific palette"

        improvements:
          - "Even if passing, could add more specific motion descriptors"
          - "Consider adding a 'tension/release' narrative arc"

    - id: uuid
      timestamp: ...
      phase: creative
      section_validated: §2
      version: 2
      validator: critic

      result:
        pass: true
        score: 0.87
        reasoning: "Strong vision with clear signature element"
        issues: []
        improvements:
          - "Could define more specific color values"

  current_blocking_issues: []

  phase_scores:
    creative: 0.87
    technical: 0.82
    design: null  # not yet validated
```

**Written by:** Critic
**Read by:** Orchestrator, All experts (for feedback)

---

### §7 Build Artifacts

Build outputs and validation results.

```yaml
§7_build_artifacts:
  json_validation:
    valid: true
    errors: []
    warnings:
      - "Unused parameter 'debug_mode' in control_center"

    operator_checks:
      all_exist: true
      missing: []

    connection_checks:
      all_valid: true
      invalid: []

    parameter_checks:
      all_valid: true
      invalid: []

  build_attempts:
    - attempt: 1
      timestamp: ...
      success: true

      paths:
        toe: "C:/TD_Projects/.../project1.toe"
        toc: "C:/TD_Projects/.../project1.toe.toc"
        dir: "C:/TD_Projects/.../project1.toe.dir/"

      validation:
        toe_exists: true
        toe_loadable: true  # if TD available for testing
        toc_valid: true
        dir_structure_correct: true

  ready_for_delivery: true

  delivery_summary:
    what_it_does: "Audio-reactive particle system with organic motion"
    key_parameters:
      - "Master Intensity: Overall brightness (0-1)"
      - "Bass Reactivity: How much bass affects explosion (0-2)"
    quality_scores:
      creative: 0.87
      technical: 0.82
      design: 0.89
      overall: 0.82
    iterations: 7
```

**Written by:** Network Builder, Validator
**Read by:** Orchestrator (for delivery), User

---

## Section Locking

Sections can be locked to prevent modification after approval.

```yaml
locking:
  §2_creative_vision:
    locked: true
    locked_at: timestamp
    locked_by: critic
    reason: "Approved at score 0.87"

  §3_technical_approach:
    locked: true
    locked_at: timestamp
    locked_by: critic
    reason: "Approved at score 0.82"

  §5_network_design:
    locked: false
    # Still being refined
```

**Unlock Triggers:**
- User feedback that requires phase reopening
- Downstream phase discovers blocking issue in earlier phase
- Explicit user request

---

## Read/Write Permissions

| Section | Creative | CG | Critic | Designer | GLSL | Python | Builder |
|---------|----------|-----|--------|----------|------|--------|---------|
| §1 | R | R | R | R | R | R | R |
| §2 | RW | R | R | R | - | - | - |
| §3 | R | RW | R | R | R | R | - |
| §4 | R | R | R | R | R | R | R |
| §5 | R | R | R | RW | RW | RW | R |
| §6 | R | R | RW | R | - | - | - |
| §7 | - | - | R | R | - | - | RW |

---

## File Format

The PROJECT DOCUMENT is stored as YAML for human readability and easy diff tracking.

**Location:** `C:\TD_Projects\META_AGENTIC_TOOL\meta_agentic\execution\projects\{project_id}\project_document.yaml`

**Backup:** Each write creates a timestamped backup in `{project_id}/history/`

---

## Example Document

See `docs/examples/project_document_example.yaml` for a complete filled-out example.

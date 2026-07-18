---
name: td-network-analysis
description: Load when analyzing, explaining, or reviewing an EXISTING TouchDesigner network — a .toe/.tox you did not just build — via the offline td-builder MCP. Triggers on analyze/explain this .toe or .tox, what does this network do, expand_toe_file, operator chain, data flow, network structure, performance bottlenecks, optimization review, or read-only mcp__td-builder__* lookups (get_operator_info, hybrid_search, query_graph). This skill is read-only analysis — to build or live-edit networks load td-builder-howto instead.
---

# TouchDesigner Network Analysis Skill

## Overview

This skill enables AI agents to analyze, understand, and explain TouchDesigner networks by combining:
- One-call network expansion + parsing (`expand_toe_file` — runs `toeexpand` for you)
- Comprehensive operator documentation (640 of TouchDesigner's 647 operators)
- Performance analysis patterns
- Best practice guidelines

**Use this skill when:**
- Analyzing existing .toe files
- Explaining what a network does
- Identifying bottlenecks or issues
- Suggesting optimizations
- Understanding operator chains and data flow

## Prerequisites

**Required MCP Tools (all offline, key-free):**
- `expand_toe_file` - Expand a .toe/.tox and parse it. `mode="summary"` returns the node/connection
  map (each node's `op_type` + its non-default params with value + mode); `mode="full"` returns the
  complete lossless JSON. Start here.
- `get_operator_info` / `get_parameter_detail` - exact operator + parameter specs from the KB.
- `hybrid_search` / `query_graph` / `find_operator_examples` - docs, relationships, real usage.
- Optional: `get_network_patterns` / `find_similar_networks` / `find_parameter_usage` /
  `find_operator_combination` - mined patterns + real-world usage, for corroboration (Step 5).

**Required Knowledge:**
- Operator documentation from project knowledge
- TouchDesigner operator families (TOP, CHOP, SOP, MAT, DAT, COMP, POP)
- Data flow concepts (texture, channel, surface, matrix, table, particle)

## Core Concepts

### TouchDesigner Operator Families

**TOP (Texture Operators)** - Process 2D images/video
- Data: RGBA pixels, resolution, aspect ratio
- Common: Noise, Movie File In, Composite, Transform
- Performance: GPU-bound, resolution-sensitive

**CHOP (Channel Operators)** - Process time-series data
- Data: Channels (samples over time)
- Common: Audio, LFO, Math, Timer, MIDI
- Performance: CPU-bound, sample-rate sensitive

**SOP (Surface Operators)** - Process 3D geometry
- Data: Points, primitives, vertices
- Common: Box, Grid, Transform, Noise
- Performance: Point-count sensitive

**MAT (Material Operators)** - Shader materials
- Data: Shader code, texture bindings
- Applied to: 3D geometry for rendering

**DAT (Data Operators)** - Process tables/text/scripts
- Data: Text, CSV, JSON, Python code
- Common: Table, Text, Execute, Script

**COMP (Components)** - Containers and special systems
- Containers: Base, Container
- Special: Camera, Light, Geometry, Replicator
- Physics: Actor, Bullet Solver

**POP (Point Operators)** - GPU-based 3D point data, including particle systems
- Data: Point/vertex/primitive attributes (position, velocity, life, color) on the GPU
- Generators: Point Generator, Particle, Grid, Line, SOP to POP, File In
- Forces: Force, Force Radial, Field
- Modifiers: Limit, Delete, Noise, Math, Feedback

### Network Structure (what `expand_toe_file` parses for you)

You never read these files yourself — `expand_toe_file` runs `toeexpand` and parses the
result (see Step 1). For background, the expansion on disk looks like:

**ASCII Format:**
```
.toe file → toeexpand → .toe.dir/
  ├── .toc           # Table of contents
  ├── .n files       # Node definitions (type, position)
  ├── .parm files    # Parameter values
  ├── .network files # Connection graphs
  └── directories/   # Nested containers
```

**Key files (all consumed by `expand_toe_file`):**
- `operator_name.n` - Type, position, viewport, flags, color
- `operator_name.parm` - Parameter values
- `container/` - Nested operators inside components

## Analysis Workflow

### Step 1: Expand and summarise

```
# One call expands (toeexpand) + parses + returns the structure:
expand_toe_file("path/to/project.toe", mode="summary")
#   -> { project_name, mode, node_count, connection_count, by_family,
#        operators: [{ path, op_type ("FAMILY:type"), params: [{name, value, mode}] }],
#        connections: [{ from, to, source_output, target_input }],
#        foreign_refs, manifest }
# Only NON-DEFAULT params are listed (that's what TD stores), each with its
# mode: constant / expression / reference / bind.
# Use mode="full" when you need positions + the complete round-trippable lossless JSON.
```

### Step 2: Read the operator types

The summary already gives each node's `op_type` as `FAMILY:type` (e.g. `TOP:noise`,
`CHOP:audiodevicein`, `SOP:box`, `COMP:container`) — no manual file parsing needed. For positions,
flags, and node colour, call `expand_toe_file(..., mode="full")`.

For what an operator or parameter means, look it up in the KB:
- `get_operator_info("Noise TOP")` - summary + parameters
- `get_parameter_detail("Noise TOP", "period")` - one parameter in depth

### Step 3: Analyze Data Flow

**Understand the processing chain:**

1. **Identify Sources** (data input operators)
   - TOP: Movie File In, Video Device In, Noise
   - CHOP: Audio Device In, Constant, LFO
   - SOP: Box, Grid, File In
   - POP: Point Generator, SOP to POP, File In

2. **Track Transformations** (processing operators)
   - TOP: Blur, Transform, Composite, Level
   - CHOP: Math, Filter, Lag, Shuffle
   - SOP: Transform, Noise, Twist

3. **Find Outputs** (renderers, exporters)
   - TOP: Null, Out
   - CHOP: Null, CHOP Execute
   - SOP: Null, Out
   - COMP: Geometry COMP (renders SOPs)

### Step 4: Performance Analysis

**Check for common bottlenecks:**

**GPU Memory Issues:**
- High-resolution TOPs (>1920x1080)
- Multiple render passes
- Large texture chains

**CPU Bottlenecks:**
- High-sample-rate CHOPs
- Complex Python scripts in Execute DATs
- Many particles (>100K)

**Cook Time Issues:**
- Expensive operators: Blur, Edge, Convolve
- Non-optimized feedback loops
- Unnecessary real-time cooking

### Step 5: Pattern Recognition

**Common TD Patterns:**

**Audio-Reactive Pattern:**
```
Audio Device In CHOP
  → Audio Spectrum CHOP (FFT)
    → Math CHOP (envelope/filter)
      → CHOP to TOP (visualization)
        OR → Used as parameter
```

**Generative Visual Pattern:**
```
Noise TOP (base texture)
  → Feedback TOP (accumulation)
    → Composite TOP (layer effects)
      → Level/HSV TOP (color grading)
        → Null TOP (output)
```

**3D Rendering Pattern:**
```
SOP geometry
  → Geometry COMP (instance)
    → Camera COMP (viewpoint)
      → Light COMP (illumination)
        → Render TOP (output)
```

**Corroborate patterns against the KB:**
- `get_network_patterns(min_frequency=...)` - operator combinations that recur across real examples
- `find_similar_networks("analyzeCHOP/example1")` - alternative implementations of a network you identified
- `find_parameter_usage(operator_type, parameter_name)` - real-world values for a suspicious parameter
- `find_operator_combination` - how a given pair of operators is typically wired

## Using Operator Documentation

### Loading Operator Info

When you need details about an operator, query the KB via the MCP tools (never guess):

1. `get_operator_info("Noise TOP")` - summary, family, full parameter list
2. `get_parameter_detail("Noise TOP", "period")` - one parameter (type, range, menu values)
3. `hybrid_search("Noise TOP audio reactive")` - docs + real example usage

**The returned structure:**
   ```
   Operator Name: What it's called
   Summary: Brief description
   Parameters: All parameters with descriptions
   Common Uses: Typical applications
   ```

4. **Key info to extract:**
   - What data does it process?
   - What are critical parameters?
   - What are performance considerations?
   - What are common use cases?

### Example: Analyzing a Noise TOP

**From documentation:**
- **Type:** TOP:noise
- **Purpose:** Generates procedural noise patterns
- **Key Parameters:**
  - `period` - Frequency of noise (lower = larger features)
  - `amplitude` - Intensity of noise
  - `type` - Perlin, Simplex, etc.
- **Performance:** GPU-accelerated, resolution-dependent
- **Common Uses:** Procedural textures, displacement maps, base layers

**Analysis insight:**
"This Noise TOP with period=10 and amplitude=1 is generating a mid-frequency Perlin noise pattern, likely used as a base texture for further processing."

## Best Practices Checklist

**Network Organization:**
- ✅ Operators grouped logically (audio chain, visual chain)
- ✅ Named descriptively (not "noise1", but "background_noise")
- ✅ Color-coded by function
- ✅ Comments via Text DATs

**Performance:**
- ✅ TOPs at appropriate resolution (no higher than needed)
- ✅ Expensive operators (Blur, Edge) used sparingly
- ✅ Selective cooking on heavy COMPs (cook flag off when idle)
- ✅ Null TOPs at key points for optimization

**Data Flow:**
- ✅ Clear left-to-right or top-to-bottom flow
- ✅ Minimal feedback loops
- ✅ Null operators to expose key outputs
- ✅ Select operators to expose controls

**Maintainability:**
- ✅ Parameters exposed to parent components
- ✅ Reusable components saved as .tox
- ✅ Python scripts in separate DATs
- ✅ Version control friendly structure

## Common Analysis Tasks

### Task 1: "What does this network do?"

**Workflow:**
1. Expand the .toe file
2. List top-level operators
3. Identify sources (audio, video, geometry)
4. Trace data flow through transformations
5. Find outputs (nulls, render, export)
6. Summarize the pipeline in plain English

**Output Format:**
```
This network:
1. Inputs: [describe sources]
2. Processing: [describe transformations]
3. Output: [describe result]
4. Purpose: [high-level goal]
```

### Task 2: "Identify performance bottlenecks"

**Workflow:**
1. Check TOP resolutions (flag anything >1920x1080)
2. Count expensive operators (Blur, Edge, Convolve)
3. Look for high-sample-rate CHOPs
4. Check for complex Python Execute DATs
5. Identify unnecessary real-time cooking

**Output Format:**
```
Potential bottlenecks:
- GPU: [list issues]
- CPU: [list issues]
- Recommendations: [list fixes]
```

### Task 3: "Suggest optimizations"

**Workflow:**
1. Identify bottlenecks (see Task 2)
2. Check for common anti-patterns:
   - TOPs at 4K when 1080p sufficient
   - Continuous cooking when could be on-demand
   - Missing NULL operators for optimization
3. Reference best practices
4. Suggest specific parameter changes

**Output Format:**
```
Optimization suggestions:
1. [Issue] → [Solution] → [Expected improvement]
2. [Issue] → [Solution] → [Expected improvement]
...
```

### Task 4: "Explain this operator chain"

**Workflow:**
1. Parse the operators in sequence
2. Look up each operator in documentation
3. Explain what data transformation occurs at each step
4. Describe the cumulative result

**Output Format:**
```
Chain Analysis: [operator1] → [operator2] → [operator3]

Step 1: [operator1]
- Takes: [input data type]
- Does: [transformation]
- Outputs: [result]

Step 2: [operator2]
- Takes: [previous output]
- Does: [transformation]
- Outputs: [result]

...

Final Result: [description of final output]
```

## Example: Complete Analysis

**User Request:** "Analyze test.toe and explain what it does"

**Agent Response:**

```
Analyzing test.toe...

NETWORK OVERVIEW:
This is an audio-reactive visual performance system with 15 operators.

STRUCTURE:
1. Audio Input Chain (CHOPs)
   - audiodevicein1: Captures system audio
   - audiospectrum1: FFT analysis (frequency spectrum)
   - math1: Envelope follower on bass frequencies
   
2. Visual Generation Chain (TOPs)
   - noise1: Generates Perlin noise base texture
     → period: 10 (medium frequency)
     → amplitude: 1.0
   - feedback1: Creates trails/accumulation effect
   - composite1: Layers noise over feedback
   
3. Audio-Reactive Control
   - math1 output → controls noise1.period
   - Creates dynamic frequency response to bass

4. Output
   - null1: Final composited output
   
PERFORMANCE ANALYSIS:
- Resolution: 1920x1080 (appropriate for real-time)
- Cook time: Estimated <5ms per frame
- Bottlenecks: None identified
- Status: Well-optimized

PURPOSE:
An audio-reactive generative visual system that responds to bass frequencies
by modulating noise patterns, creating organic flowing visuals synchronized
to music.

RECOMMENDATIONS:
- Consider adding color grading (HSV TOP) for more visual variety
- Could add Transform TOP for scaling/rotation effects
- Performance is good, no optimizations needed
```

## Tips for Effective Analysis

1. **Start broad, then drill down**
   - First understand overall structure
   - Then analyze individual operators
   - Finally examine parameters

2. **Always explain in context**
   - Don't just list operators
   - Explain their role in the larger system
   - Describe data transformations

3. **Use operator documentation**
   - Reference specific parameters
   - Cite common uses
   - Apply performance guidelines

4. **Provide actionable insights**
   - Not just "this might be slow"
   - But "reduce resolution from 4K to 1080p to improve performance by ~4x"

5. **Speak the user's language**
   - Assume TD knowledge but explain clearly
   - Use correct TD terminology
   - Provide concrete examples

## Integration with Other Skills

**This skill works well with:**

- **`td-builder-howto`** (`Agents/td-builder-howto/SKILL.md`) - the build/live-edit companion.
  This skill is read-only analysis; when the analysis leads to modifying or rebuilding the
  network, load the how-to skill for the build pipeline and live-TD gotchas first.
- **`get_expert_prompt` experts** - `td_designer`, `network_builder`, `td_glsl_expert`,
  `td_python_expert`, `ui_expert`, `critic` - load one when the analysis turns into design,
  optimization, or shader work.

**This skill provides foundation for:**

- Network modification recommendations
- Operator chain design
- Debugging assistance
- Educational explanations

## Common Pitfalls to Avoid

❌ **Don't:**
- Analyze without expanding .toe first
- Ignore operator documentation
- Provide generic advice without specifics
- Focus only on parameters, ignore data flow
- Overwhelm user with technical details

✅ **Do:**
- Always use MCP tools to access network files
- Reference operator docs for accurate info
- Provide specific, actionable recommendations
- Explain data flow and transformations
- Tailor detail level to user's apparent expertise

## Conclusion

This skill enables systematic, intelligent analysis of TouchDesigner networks by combining:
- Structural parsing (`expand_toe_file`)
- Operator knowledge (comprehensive docs)
- Pattern recognition (common workflows)
- Performance analysis (best practices)

Use it as the foundation for understanding any TD network before suggesting modifications or optimizations.

---

**Skill Version:** 1.2 (registrable frontmatter + content-accuracy pass; 1.1 shipped with release v0.2.0)  
**Operator Database:** TouchDesigner 2025 (via `KB/operators.json` — a fetched artifact from `scripts/fetch_vector_db.py`, not committed)  
**Dependencies:** the offline `td-builder` MCP tools — `expand_toe_file`, `get_operator_info`,
`get_parameter_detail`, `hybrid_search`, `query_graph`, `find_operator_examples` (plus the
optional pattern tools in Step 5)

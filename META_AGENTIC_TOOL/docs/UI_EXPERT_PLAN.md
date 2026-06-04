# UI Expert Agent - Implementation Plan

**Author**: PETER (Prompt Engineer)
**Date**: 2024-12-23
**Status**: PLAN (awaiting approval)

---

## Executive Summary

This document proposes a new expert agent specialized in TouchDesigner UI design for **PERFORMANCE use** - VJ interfaces, show control panels, and interactive installations. The vision: an agent as skilled at TD UI design as Claude Opus is at CSS layouts.

---

## 1. When to Invoke UI Expert vs td_designer

### Invocation Triggers

| Trigger Phrase/Context | Route To | Rationale |
|------------------------|----------|-----------|
| "create a control panel" | **ui_expert** | Core UI task |
| "build a VJ interface" | **ui_expert** | Performance UI specialty |
| "add sliders and buttons" | **ui_expert** | Widget-specific |
| "show control surface" | **ui_expert** | Performance context |
| "touch screen interface" | **ui_expert** | Input-specific UI |
| "MIDI controller UI" | **ui_expert** | Hardware integration |
| "audio reactive scene" | td_designer | Processing, not UI |
| "feedback loop" | td_designer | Visual effect, not UI |
| "instancing setup" | td_designer | Network design, not UI |

### Decision Tree

```
User Request
     │
     ▼
Contains UI keywords?
(panel, control, widget, slider, button, knob, interface, UI, menu, touch)
     │
     ├── YES ──► Primary purpose is control/interaction?
     │                    │
     │              ├── YES ──► ui_expert
     │              └── NO ──► td_designer (with ui_expert delegation)
     │
     └── NO ──► td_designer
```

### Delegation Protocol

**From td_designer to ui_expert:**
```yaml
delegation:
  to_expert: ui_expert
  reason: "User request includes control panel/interface requirements"
  handoff_data:
    creative_context: "{{from creative_brief if available}}"
    required_controls: ["list", "of", "controls"]
    output_requirements: ["channel names", "value ranges"]
    style_hints: "dark theme, minimal, VJ-style"
```

**From ui_expert back to td_designer:**
```yaml
ui_design_complete:
  operators: [...]  # Widget operators with layout
  connections: [...]  # Widget → CHOP wiring
  container_spec: {...}  # Panel dimensions, colors
  output_channels: ["brightness", "speed", "fx1", "fx2"]  # Control outputs
  ready_for_network_builder: true
```

---

## 2. Expertise Scope

### 2.1 TD Widget Types

**Basic Widgets (48 from Palette):**

| Category | Widgets | Key Outputs |
|----------|---------|-------------|
| Buttons | buttonCheckbox, buttonToggle, buttonMomentary, buttonPush, buttonRadio, buttonRocker, buttonScript, buttonState | Binary (0/1) or integer index |
| Sliders | sliderHorz, sliderVert, slider2D, sliderHorzXFade | Float 0-1 (or custom range) |
| Color | slider3Rgb, slider3Hsv, slider4Rgba, slider4Hsva | RGB/HSV channels |
| Numeric | float1/2/3/4, int1/2/3/4 | Direct numeric values |
| Knobs | knobEndless, knobFixed | Float 0-1 or cumulative |
| Dropdown | dropDownMenu, dropDownButton | Integer index |
| Fields | fieldString, fieldStringExec, fieldFileBrowser, fieldFolderBrowser, fieldTextArea | String values |
| Layout | header, footer, section, label, folderTabs | Structure only |
| References | referenceCHOP/TOP/SOP/DAT/MAT/OBJ/OP/COMP | Operator paths |

**Complex Widgets:**
- lister, treeLister, displayList - Data display
- popDialog, popMenu - Modals
- gal (gallery) - Image selection
- radioList, simpleList - List selection

### 2.2 Container/Panel Layouts

**Layout Patterns:**

```yaml
layout_patterns:
  grid_layout:
    description: "Evenly spaced controls in rows/columns"
    use_case: "Mixer-style interfaces, parameter banks"
    implementation:
      - Calculate cell positions from grid dimensions
      - Equal spacing with margins
      - Auto-sizing within cells

  vertical_stack:
    description: "Controls stacked top-to-bottom"
    use_case: "Sidebar controls, parameter lists"
    implementation:
      - Fixed or percentage heights
      - Scrollable if overflow

  horizontal_bar:
    description: "Controls in horizontal row"
    use_case: "Transport controls, tool bars"
    implementation:
      - Fixed height, variable width
      - Icon-based buttons

  dashboard:
    description: "Mixed layout with header, sidebar, main, footer"
    use_case: "Full show control interfaces"
    implementation:
      - Fixed regions (header 50px, footer 30px)
      - Flexible main content area
      - Optional collapsible sidebar

  floating_panel:
    description: "Movable overlay panel"
    use_case: "On-screen controls during performance"
    implementation:
      - Draggable header
      - Semi-transparent background
      - Minimize/close buttons
```

### 2.3 Performance UI Patterns

**VJ Control Surface:**
```yaml
vj_control_surface:
  regions:
    - name: "transport"
      position: [0, 0]
      size: [1920, 60]
      widgets: ["play", "stop", "record", "bpm_tap", "bpm_display"]

    - name: "deck_a"
      position: [0, 60]
      size: [640, 500]
      widgets: ["video_preview", "effect_chain", "speed_fader", "fx_mix"]

    - name: "deck_b"
      position: [1280, 60]
      size: [640, 500]
      widgets: ["video_preview", "effect_chain", "speed_fader", "fx_mix"]

    - name: "mixer"
      position: [640, 60]
      size: [640, 500]
      widgets: ["crossfader", "master_levels", "output_preview"]

    - name: "cue_bank"
      position: [0, 560]
      size: [1920, 200]
      widgets: ["8x scene_buttons", "4x effect_buttons", "master_dim"]

  output_channels:
    - "deckA/speed"
    - "deckA/fx1..fx4"
    - "deckB/speed"
    - "deckB/fx1..fx4"
    - "mixer/crossfade"
    - "master/brightness"
```

**Show Control Panel:**
```yaml
show_control_panel:
  regions:
    - name: "cue_list"
      type: "lister"
      data: "cue_table"
      size: [300, 600]

    - name: "active_cue"
      type: "display"
      size: [400, 100]

    - name: "transport"
      widgets: ["go", "stop", "back", "next"]

    - name: "manual_overrides"
      widgets: ["blackout", "master_dim", "freeze"]

  output_channels:
    - "cue/current"
    - "cue/next"
    - "transport/go"
    - "manual/blackout"
    - "manual/master"
```

**Touch Installation:**
```yaml
touch_installation:
  multitouch: true
  hit_target_min: 44  # pixels, for finger touch

  gesture_patterns:
    - name: "drag"
      widget: "slider2D"
      outputs: ["x", "y"]

    - name: "pinch"
      implementation: "custom_multitouch_logic"
      outputs: ["scale"]

    - name: "rotate"
      implementation: "custom_multitouch_logic"
      outputs: ["rotation"]
```

### 2.4 Responsive Layouts

```yaml
responsive_strategies:
  resolution_aware:
    description: "Adapt to different output resolutions"
    implementation:
      - Use percentage-based positioning where possible
      - Set min/max constraints for critical controls
      - Define breakpoints for layout switching

  breakpoints:
    - resolution: [1920, 1080]
      layout: "full_dashboard"
    - resolution: [1280, 720]
      layout: "compact_dashboard"
    - resolution: [800, 600]
      layout: "minimal_controls"

  scaling_rules:
    widgets:
      min_button_size: 30
      preferred_button_size: 44
      min_slider_width: 100
      min_knob_size: 40

    fonts:
      min_label_size: 10
      preferred_label_size: 14
      header_size: 18
```

### 2.5 Touch/MIDI/OSC Control Integration

```yaml
input_integration:
  midi:
    operators:
      - midiinCHOP: "Receives MIDI control changes"
      - midiinmapCHOP: "Maps MIDI to named channels"

    mapping_pattern:
      - "MIDI CC → selectCHOP → merge with UI"
      - "UI outputs → midioutCHOP (feedback)"

    example:
      cc_to_slider: |
        # midiinmap1 outputs cc0, cc1, cc2...
        # Use math to scale 0-127 → 0-1
        math1.par.mult = 1/127
        # Wire to merge with UI slider

  osc:
    operators:
      - oscinCHOP: "Receives OSC messages"
      - oscoutCHOP: "Sends OSC messages"

    mapping_pattern:
      - "OSC in → rename channels → merge with UI"
      - "UI outputs → rename → OSC out"

    address_conventions:
      - "/1/fader1" (TouchOSC style)
      - "/control/slider/brightness"
      - "/cue/go"

  touch:
    operators:
      - panelCOMP: "Handles touch events"
      - panelexecuteDAT: "Touch callbacks"

    event_types:
      - "onTouch" - finger down/move/up
      - "onPinch" - two-finger scale
      - "onRotate" - two-finger rotation

    gesture_to_chop: |
      # In panelexecuteDAT:
      def onTouch(panelValue, info):
          op('touch_chop').par.value0 = info['u']
          op('touch_chop').par.value1 = info['v']
```

---

## 3. Knowledge Base Needs

### 3.1 What Exists in KB

| Resource | Location | Coverage |
|----------|----------|----------|
| Palette widgets | Learn/Palette/UI/Basic Widgets/ | 48 .tox files |
| Widget loading patterns | palette_expertise.yaml | loadTox, wiring |
| Control panel pattern | td_network_patterns.yaml | Basic container structure |
| Widget outputs | palette_expertise.yaml | slider2D channels, button outputs |
| Layout examples | palette_expertise.yaml | Xbox controller layout |

### 3.2 What Should Be Added

**New Expertise File: `ui_design_patterns.yaml`**

```yaml
# Required sections:

widget_catalog:
  # For each widget type:
  - name: "slider2D"
    palette_path: "UI/Basic Widgets/slider2D.tox"
    outputs:
      - channel: "u"
        range: [0, 1]
        description: "Horizontal position"
      - channel: "v"
        range: [0, 1]
        description: "Vertical position"
    default_size: [100, 100]
    touch_enabled: true
    parameters:
      - name: "Label"
        type: "string"
      - name: "Bgr/Bgg/Bgb"
        type: "color"

layout_templates:
  # Pre-defined layouts that work well
  - name: "8_channel_mixer"
    widget_slots: 8
    widget_type: "sliderVert"
    arrangement: "horizontal_grid"
    outputs: ["ch1", "ch2", ..., "ch8"]

performance_patterns:
  # VJ/show control specific patterns
  - pattern: "bpm_sync"
    description: "Sync UI to audio BPM"
    implementation: [...]

color_themes:
  dark_vj:
    background: [0.1, 0.1, 0.12]
    widget_bg: [0.2, 0.2, 0.22]
    accent: [0.0, 0.8, 1.0]
    text: [0.9, 0.9, 0.9]

  light_install:
    background: [0.95, 0.95, 0.95]
    widget_bg: [1.0, 1.0, 1.0]
    accent: [0.2, 0.4, 0.8]
    text: [0.1, 0.1, 0.1]
```

### 3.3 Palette UI Components to Reference

**Priority 1 - Core widgets (document fully):**
- sliderVert, sliderHorz, slider2D
- buttonToggle, buttonMomentary, buttonRadio
- knobFixed, knobEndless
- dropDownMenu
- float1/2/3/4

**Priority 2 - Layout widgets:**
- header, footer, section
- folderTabs
- container positioning

**Priority 3 - Complex widgets:**
- lister (for cue lists)
- popMenu (for context menus)
- colorPicker patterns

---

## 4. Expert Files Structure

### 4.1 Directory Layout

```
meta_agentic/experts/ui_expert/
├── plan.md           # Planning prompt
├── build.md          # Execution prompt
├── self_improve.md   # Refinement prompt
└── config.yaml       # Agent configuration
```

### 4.2 plan.md

```markdown
# UI Expert - Plan Step

## Identity
You are the **UI Expert**. Purpose: Design TouchDesigner UI layouts for performance
and interactive applications, selecting appropriate widgets and defining their
layout, wiring, and output channels.

## Required Initialization
```python
expertise = {
    'ui_patterns': load_yaml('meta_agentic/expertise/ui_design_patterns.yaml'),
    'palette': load_yaml('meta_agentic/expertise/palette_expertise.yaml'),
    'widgets': load_yaml('meta_agentic/expertise/palette_semantic_catalog.yaml'),
    'operators': load_yaml('meta_agentic/expertise/td_operators.yaml')
}
```

## Planning Steps

1. **Parse UI requirements**
   - What controls are needed? (sliders, buttons, knobs, etc.)
   - What layout style? (dashboard, mixer, minimal)
   - What resolution/aspect ratio?
   - Touch, MIDI, OSC integration needed?

2. **Select layout template**
   - Match to ui_design_patterns.yaml templates
   - Customize for specific requirements
   - Plan responsive behavior if needed

3. **Map widgets to outputs**
   - Define output channel names
   - Set value ranges
   - Plan channel grouping (merge patterns)

4. **Plan wiring**
   - Widget → selectCHOP → renameCHOP → mergeCHOP → outCHOP
   - Include lag/smoothing if needed
   - Plan MIDI/OSC integration points

5. **Validate widget availability**
   - Check all widgets exist in palette
   - Note any custom widgets needed
   - Flag unavailable widgets

## Output Format
```yaml
ui_plan:
  expert: "ui_expert"
  layout_type: "dashboard|mixer|minimal|custom"
  resolution: [width, height]

  regions:
    - name: "region_name"
      position: [x, y]
      size: [width, height]
      widgets: [...]

  widgets:
    - name: "widget_name"
      type: "sliderVert"
      palette_source: "UI/Basic Widgets/sliderVert.tox"
      position: [x, y]
      outputs: ["channel_name"]
      parameters:
        label: "Display Label"
        range: [0, 1]

  wiring:
    - from: "widget1/output/chop"
      to: "select1"
      then: "merge1"
      final_output: "out1"

  external_inputs:
    midi: true|false
    osc: true|false
    touch: true|false

  output_channels:
    - name: "brightness"
      source: "slider1"
      range: [0, 1]
```
```

### 4.3 build.md

```markdown
# UI Expert - Build Step

## Identity
You are the **UI Expert** in build mode. Purpose: produce a complete UI network
specification from the validated plan, ready for network_builder to assemble.

## Build Steps

1. **Generate widget operators**
   For each widget in plan:
   - Specify palette load via textDAT init script
   - Set position (nodeX, nodeY for network, panel position for display)
   - Configure parameters (label, range, colors)

2. **Generate wiring operators**
   - selectCHOP for each widget output
   - renameCHOP if channel names need changing
   - mergeCHOP to combine all controls
   - outCHOP for final output

3. **Generate container structure**
   - containerCOMP as parent panel
   - Set panel dimensions and colors
   - Configure panel execute for events

4. **Generate init script**
   - textDAT with execOnStart=True
   - Python code to load all palette widgets
   - Post-load positioning and wiring

## Output Format
```yaml
design:
  name: "{{ui_name}}"
  goal: "{{user_intent}}"
  pattern: "ui_control_panel"
  created_by: "ui_expert"

  operators:
    # Container
    - name: "ui_panel"
      type: "containerCOMP"
      parameters:
        w: 800
        h: 600
        bgr: 0.1
        bgg: 0.1
        bgb: 0.12

    # Palette widgets (embedded directly - no init script needed)
    - name: "brightness"
      palette: "sliderVert"       # Embeds sliderVert from KB lossless JSON
      parent: "ui_panel"
      position: [50, 100]

    - name: "contrast"
      palette: "sliderVert"       # Each widget is a separate palette embed
      parent: "ui_panel"
      position: [150, 100]

    # Wiring
    - name: "select1"
      type: "selectCHOP"
      parent: "ui_panel"
      parameters:
        channames: "*"

    - name: "merge1"
      type: "mergeCHOP"
      parent: "ui_panel"

    - name: "out1"
      type: "outCHOP"
      parent: "ui_panel"

  connections:
    - from: "select1"
      to: "merge1"
      type: "wire"
    - from: "merge1"
      to: "out1"
      type: "wire"

  metadata:
    pattern_source: "ui_design_patterns.yaml#control_panel"
    widget_count: 2
    output_channels: ["brightness", "contrast"]
```
```

### 4.4 self_improve.md

```markdown
# UI Expert - Self-Improvement

## When to Update Expertise

1. **New widget pattern discovered**
   - User shows working widget configuration
   - Add to ui_design_patterns.yaml widget_catalog

2. **Layout pattern validated**
   - Multi-widget layout works well in TD
   - Add to layout_templates section

3. **Wiring pattern confirmed**
   - Complex wiring (MIDI integration, etc.) works
   - Document in wiring_patterns section

4. **Theme validated**
   - Color scheme looks good in practice
   - Add to color_themes section

## Feedback Integration

```yaml
feedback_sources:
  - type: "build_success"
    action: "Increment confidence for patterns used"

  - type: "build_failure"
    action: "Log error, update td_problems.yaml"

  - type: "user_correction"
    action: "Update relevant pattern with correction"

  - type: "new_widget_discovered"
    action: "Add to widget_catalog with full analysis"
```

## Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Widget validation rate | 100% | All widgets exist in palette |
| Layout success rate | >95% | Layouts render correctly |
| Output channel accuracy | 100% | All promised channels present |
| Touch responsiveness | <16ms | Panel responds within frame |
```

### 4.5 config.yaml

```yaml
expert_id: ui_expert
version: 1.0.0
created: '2024-12-23'
description: Designs TouchDesigner UI layouts for performance and interactive applications

expertise_inputs:
  - path: meta_agentic/expertise/ui_design_patterns.yaml
    purpose: Widget catalog, layout templates, wiring patterns
  - path: meta_agentic/expertise/palette_expertise.yaml
    purpose: Palette loading patterns, widget structure
  - path: meta_agentic/expertise/palette_semantic_catalog.yaml
    purpose: All available palette components
  - path: meta_agentic/expertise/td_operators.yaml
    purpose: Operator validation

validation_sources:
  - path: operator_ground_truth/operator_types.json
    purpose: Validate operator types
  - path: operator_ground_truth/param_catalog.json
    purpose: Validate parameter names

expertise_outputs:
  - path: meta_agentic/expertise/ui_design_patterns.yaml
    purpose: Update with new patterns
  - path: meta_agentic/expertise/td_problems.yaml
    purpose: Log UI-specific problems

event_log: meta_agentic/history/expertise_events.jsonl
event_domain: ui_design

collaborators:
  - expert_id: td_designer
    relationship: upstream
    receives_from: ui_delegation_request
    handoff_format: ui_delegation_v1
    description: Receives UI design requests from td_designer

  - expert_id: creative_orchestrator
    relationship: upstream
    receives_from: creative_brief
    handoff_format: creative_brief_v1
    description: May receive UI requirements from creative workflow

  - expert_id: network_builder
    relationship: downstream
    delegation_trigger: UI design complete
    handoff_format: design_spec_v1
    description: Passes completed UI spec for assembly

supported_patterns:
  - name: control_panel
    complexity: medium
    families: [COMP, CHOP]

  - name: vj_interface
    complexity: hard
    families: [COMP, CHOP, TOP]

  - name: show_control
    complexity: hard
    families: [COMP, CHOP, DAT]

  - name: touch_surface
    complexity: medium
    families: [COMP, CHOP]

  - name: midi_controller
    complexity: medium
    families: [COMP, CHOP]

output_format:
  type: yaml
  schema: design_spec_v1
  includes:
    - operators
    - hierarchy
    - connections
    - parameters
    - init_scripts
    - output_channels

validation:
  require_widget_validation: true
  require_palette_paths: true
  require_output_channel_definition: true
  flag_custom_widgets: true

learning:
  log_successes: true
  log_failures: true
  update_patterns_on_success: true
  min_samples_for_pattern_update: 3
```

---

## 5. Hand-off Schema

### 5.1 td_designer → ui_expert

```yaml
# When td_designer encounters UI requirements

ui_delegation_request:
  version: "1.0"
  from_expert: "td_designer"
  to_expert: "ui_expert"

  context:
    user_request: "Original user request text"
    creative_brief: {...}  # If from creative workflow

  ui_requirements:
    controls_needed:
      - type: "slider"
        count: 4
        purpose: "RGBA color control"
      - type: "button"
        count: 8
        purpose: "Scene triggers"

    layout_preference: "grid|dashboard|minimal|unspecified"
    resolution: [1920, 1080]  # or null if flexible

    input_integration:
      midi: true
      osc: false
      touch: true

    output_requirements:
      channels: ["r", "g", "b", "a", "scene1"..."scene8"]
      ranges: [[0,1], [0,1], [0,1], [0,1], [0,1]...]

  style_hints:
    theme: "dark"
    accent_color: [0, 0.8, 1.0]
    minimal: true
```

### 5.2 ui_expert → network_builder

```yaml
# UI expert outputs standard design_spec_v1 format

design:
  name: "color_control_panel"
  goal: "RGBA color control with scene triggers"
  pattern: "control_panel"
  created_by: "ui_expert"
  timestamp: "2024-12-23T..."

  operators:
    - name: "ui_panel"
      type: "containerCOMP"
      position: [0, 0]
      parameters:
        w: 800
        h: 400
        bgr: 0.1
        bgg: 0.1
        bgb: 0.12

    - name: "init"
      type: "textDAT"
      parent: "ui_panel"
      parameters:
        execonstartTrue: true
        dat: |
          # Widget loading script...

    # ... more operators

  connections:
    - from: "select_colors"
      to: "merge1"
      type: "wire"
    - from: "select_scenes"
      to: "merge1"
      type: "wire"

  # UI-specific metadata
  ui_metadata:
    widget_manifest:
      - name: "red_slider"
        palette_source: "sliderVert.tox"
        output_channel: "r"
      - name: "green_slider"
        palette_source: "sliderVert.tox"
        output_channel: "g"
      # ...

    output_channels:
      - name: "r"
        range: [0, 1]
      - name: "g"
        range: [0, 1]
      - name: "b"
        range: [0, 1]
      - name: "a"
        range: [0, 1]
      - name: "scene1"
        range: [0, 1]
        type: "trigger"
      # ...

  validation_summary:
    widgets_validated: 12
    widgets_unvalidated: 0
    palette_paths_verified: true
    output_channels_defined: true
```

### 5.3 Integration with Blackboard

```yaml
blackboard_sections:
  reads_from:
    - section: "§1 Requirements"
      extracts: "ui_requirements, control_needs"
    - section: "§2 Creative Vision"
      extracts: "aesthetic preferences, color themes"
    - section: "§4 Available Resources"
      extracts: "palette_components, existing_ui_patterns"

  writes_to:
    - section: "§5 Network Design"
      adds: "ui_operators, ui_connections, ui_parameters"
    - section: "§7 Build Artifacts"
      adds: "ui_spec, widget_manifest"
```

---

## 6. Example Outputs

### 6.1 Example: "Create a VJ control panel"

**User Prompt:**
> Create a VJ control panel with master brightness, 4 effect sliders, 8 scene buttons, and a crossfader.

**ui_expert Plan Output:**

```yaml
ui_plan:
  expert: "ui_expert"
  layout_type: "vj_interface"
  resolution: [1200, 400]

  regions:
    - name: "master"
      position: [20, 20]
      size: [100, 360]
      widgets:
        - name: "brightness"
          type: "sliderVert"

    - name: "effects"
      position: [140, 20]
      size: [320, 360]
      widgets:
        - name: "fx1"
          type: "sliderVert"
        - name: "fx2"
          type: "sliderVert"
        - name: "fx3"
          type: "sliderVert"
        - name: "fx4"
          type: "sliderVert"

    - name: "scenes"
      position: [480, 20]
      size: [560, 160]
      widgets:
        - name: "scene1-8"
          type: "buttonToggle"
          count: 8
          arrangement: "horizontal"

    - name: "crossfader"
      position: [480, 200]
      size: [560, 80]
      widgets:
        - name: "xfade"
          type: "sliderHorz"

  output_channels:
    - name: "master"
      source: "brightness"
    - name: "fx1"
      source: "fx1"
    - name: "fx2"
      source: "fx2"
    - name: "fx3"
      source: "fx3"
    - name: "fx4"
      source: "fx4"
    - name: "scene"
      source: "scene_buttons"
      type: "integer"
    - name: "xfade"
      source: "xfade"
```

**ui_expert Build Output:**

```yaml
design:
  name: "vj_control_panel"
  goal: "VJ control panel with master, effects, scenes, crossfader"
  pattern: "vj_interface"
  created_by: "ui_expert"

  operators:
    # Main container
    - name: "vj_panel"
      type: "containerCOMP"
      position: [0, 0]
      parameters:
        w: 1200
        h: 400
        bgr: 0.08
        bgg: 0.08
        bgb: 0.1

    # Palette widgets - embedded directly using palette field
    # Master brightness
    - name: "brightness"
      palette: "sliderVert"
      parent: "vj_panel"
      position: [50, 50]

    # Effect sliders
    - name: "fx1"
      palette: "sliderVert"
      parent: "vj_panel"
      position: [160, 50]

    - name: "fx2"
      palette: "sliderVert"
      parent: "vj_panel"
      position: [240, 50]

    - name: "fx3"
      palette: "sliderVert"
      parent: "vj_panel"
      position: [320, 50]

    - name: "fx4"
      palette: "sliderVert"
      parent: "vj_panel"
      position: [400, 50]

    # Scene buttons
    - name: "scene1"
      palette: "buttonToggle"
      parent: "vj_panel"
      position: [500, 50]

    - name: "scene2"
      palette: "buttonToggle"
      parent: "vj_panel"
      position: [570, 50]

    # ... (scene3-scene8 follow same pattern)

    # Crossfader
    - name: "xfade"
      palette: "sliderHorz"
      parent: "vj_panel"
      position: [500, 220]

    # Channel wiring
    - name: "select_scenes"
      type: "selectCHOP"
      parent: "vj_panel"
      position: [400, 300]
      parameters:
        channames: "scene*"

    - name: "merge1"
      type: "mergeCHOP"
      parent: "vj_panel"
      position: [500, 300]

    - name: "rename1"
      type: "renameCHOP"
      parent: "vj_panel"
      position: [600, 300]
      parameters:
        renamefrom: "v1 v1 v1 v1 v1 u"
        renameto: "master fx1 fx2 fx3 fx4 xfade"

    - name: "out1"
      type: "outCHOP"
      parent: "vj_panel"
      position: [700, 300]

  connections:
    - from: "select_scenes"
      to: "merge1"
      type: "wire"
      input_index: 6
    - from: "merge1"
      to: "rename1"
      type: "wire"
    - from: "rename1"
      to: "out1"
      type: "wire"

  ui_metadata:
    widget_manifest:
      - name: "brightness"
        type: "sliderVert"
        output: "master"
        range: [0, 1]
      - name: "fx1"
        type: "sliderVert"
        output: "fx1"
        range: [0, 1]
      - name: "fx2"
        type: "sliderVert"
        output: "fx2"
        range: [0, 1]
      - name: "fx3"
        type: "sliderVert"
        output: "fx3"
        range: [0, 1]
      - name: "fx4"
        type: "sliderVert"
        output: "fx4"
        range: [0, 1]
      - name: "scene1-8"
        type: "buttonToggle"
        output: "scene"
        range: [0, 7]
      - name: "xfade"
        type: "sliderHorz"
        output: "xfade"
        range: [0, 1]

    output_channels:
      - "master"
      - "fx1"
      - "fx2"
      - "fx3"
      - "fx4"
      - "scene"
      - "xfade"

  validation_summary:
    widgets_validated: 14
    widgets_unvalidated: 0
    palette_paths_verified: true
    output_channels_defined: true
    estimated_load_time_ms: 50
```

---

## 7. Implementation Roadmap

### Phase 1: Foundation
1. Create `meta_agentic/experts/ui_expert/` directory
2. Create plan.md, build.md, self_improve.md, config.yaml
3. Create `meta_agentic/expertise/ui_design_patterns.yaml` with basic widget catalog

### Phase 2: Widget Catalog
1. Document all 48 basic widgets with outputs, parameters, sizes
2. Create layout templates (grid, stack, dashboard)
3. Add color themes

### Phase 3: Integration
1. Add delegation logic to td_designer for UI routing
2. Test hand-off to network_builder
3. Verify .tox output works in TouchDesigner

### Phase 4: Advanced Features
1. MIDI integration patterns
2. OSC integration patterns
3. Multi-touch gesture handling
4. Responsive layout system

---

## 8. Success Criteria

| Metric | Target |
|--------|--------|
| Widget load success rate | 100% |
| Layout renders correctly | >95% |
| Output channels work | 100% |
| Hand-off to network_builder | Seamless |
| VJ panel from prompt | <30 seconds |

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Palette path varies by TD version | Check multiple paths, fallback list |
| Widget outputs change between versions | Version-specific widget catalog |
| Complex layouts exceed performance | Document performance limits |
| Init script timing issues | Use onStart callback pattern |
| Custom widgets not in palette | Flag, suggest alternatives |

---

## Approval Request

This plan requires approval before implementation. Key decisions needed:

1. **Priority of features**: Start with basic widgets or full VJ interface?
2. **ui_design_patterns.yaml scope**: Minimal catalog or comprehensive?
3. **Integration depth**: Loose coupling or tight blackboard integration?

Please review and approve or request modifications.

---

*Created by PETER - Prompt Engineer*
*For TD Builder META_AGENTIC_TOOL*

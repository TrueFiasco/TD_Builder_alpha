# UI Expert - Self-Improvement

## Purpose

Track learnings from UI designs to improve future outputs. Update expertise files when patterns are validated or problems discovered.

---

## When to Update Expertise

### 1. New Widget Pattern Discovered

User shows working widget configuration not in catalog.

**Action**: Add to ui_design_patterns.yaml widget_catalog

```yaml
widget_catalog:
  new_widget:
    operator_type: "sliderCOMP"
    outputs:
      - channel: "v1"
        range: [0, 1]
    default_size: [100, 100]
    notes: "Discovered from user project"
```

### 2. Layout Pattern Validated

Multi-widget layout works well in TouchDesigner.

**Action**: Add to layout_templates section

```yaml
layout_templates:
  new_layout:
    description: "Description of layout"
    widget_positions: [...]
    verified: true
    sample_project: "path/to/example"
```

### 3. Wiring Pattern Confirmed

Complex wiring (MIDI integration, etc.) works correctly.

**Action**: Document in wiring_patterns section

```yaml
wiring_patterns:
  midi_slider:
    description: "MIDI CC to slider bidirectional"
    components: [midiinCHOP, selectCHOP, mergeCHOP]
    verified: true
```

### 4. Theme Validated

Color scheme looks good in practice.

**Action**: Add to color_themes section

```yaml
color_themes:
  new_theme:
    background: [r, g, b]
    accent: [r, g, b]
    text: [r, g, b]
    verified: true
```

---

## Feedback Integration

```yaml
feedback_sources:
  - type: "build_success"
    action: "Increment confidence for patterns used"
    update: "ui_design_patterns.yaml#confidence"

  - type: "build_failure"
    action: "Log error, investigate cause"
    update: "td_problems.yaml"

  - type: "user_correction"
    action: "Update relevant pattern with correction"
    update: "ui_design_patterns.yaml"

  - type: "new_widget_discovered"
    action: "Add to widget_catalog with full analysis"
    update: "ui_design_patterns.yaml#widget_catalog"

  - type: "kb_update"
    action: "Check for new widgets in KB"
    update: "ui_design_patterns.yaml#widget_catalog"
```

---

## Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Widget validation rate | 100% | All widget operator types verified in KB |
| Layout success rate | >95% | Layouts render correctly in TD |
| Output channel accuracy | 100% | All promised channels present |
| Touch responsiveness | <16ms | Panel responds within frame |
| Theme consistency | 100% | Colors match specification |

---

## Learning Events Log

Record significant learnings:

```yaml
event:
  timestamp: "ISO8601"
  type: "widget_discovery|layout_success|wiring_fix|theme_update"
  description: "What was learned"
  source: "user_feedback|test_result|kb_update"
  applied_to: "file path"
  confidence_delta: +0.05  # How much confidence increased
```

---

## Common Problems to Watch

### 1. Widget Output Names

Different widgets use different channel names depending on mode (a slider in X mode vs
XY mode outputs different channels).

**Solution**: Always check the KB (`get_operator_info` / `get_parameter_detail`) for exact
output names — never guess.

### 2. Panel Scaling

UI may look different at different resolutions.

**Solution**: Use percentage-based positioning or min/max constraints.

### 3. CHOP Merge Order

Order of inputs to mergeCHOP affects channel naming.

**Solution**: Use renameCHOP after merge to ensure consistent names.

---

## Expertise Update Protocol

When updating ui_design_patterns.yaml:

1. Read current file
2. Add new entry with `verified: false`
3. After 3 successful uses, set `verified: true`

This release has no automated event log (expertise persistence is planned for a future
release). Report the learning event to the user in this shape instead:

```json
{
  "timestamp": "{{ISO8601}}",
  "expert": "ui_expert",
  "type": "{{event_type}}",
  "description": "{{what was learned}}",
  "file": "{{expertise file it applies to}}"
}
```

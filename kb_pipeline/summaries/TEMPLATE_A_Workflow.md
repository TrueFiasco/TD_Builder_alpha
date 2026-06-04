# Template A: Workflow Summary

## Purpose
Create high-level workflow summaries that answer "How do I accomplish X in TouchDesigner?" These are NOT tied to specific network files - they're conceptual workflows synthesized from multiple examples.

## Anti-Hallucination Rules ⚠️

### Data Sources (Multi-Source Synthesis):
1. **Multiple network examples** showing the same pattern
2. **Wiki documentation** for operator capabilities
3. **Your knowledge** of TD workflows (BUT: only when pattern appears in 3+ examples)

### Validation:
- ✅ Workflow must be demonstrated in at least 3 real examples
- ✅ Every operator mentioned must exist in TD docs
- ✅ Every connection pattern must appear in real examples
- ✅ Parameter ranges based on actual usage, not theory
- ❌ DON'T create workflows not seen in examples
- ❌ DON'T suggest operators that don't exist
- ❌ DON'T invent parameter values

---

## Template Structure

### Section 1: WORKFLOW NAME & PROBLEM
**Format**:
```
WORKFLOW: {Name}
SOLVES: {What user problem/goal this addresses}
```

**Example**:
```
WORKFLOW: Audio-Reactive Visuals
SOLVES: Synchronizing visual parameters to music beats and audio energy in real-time
```

**Rules**:
- Name should match how users search ("audio reactive" not "sonic visual synchronization")
- Problem statement = what user wants to achieve

---

### Section 2: COMMON OPERATOR CHAIN
**Format**:
```
TYPICAL CHAIN:
{Source} → {Processor 1} → {Processor 2} → {Output/Target}

VARIATIONS:
- Variation 1: {alternative path}
- Variation 2: {alternative path}
```

**Example**:
```
TYPICAL CHAIN:
Audio File In CHOP → Analyze CHOP → Beat CHOP → Math CHOP → [visual parameter]

VARIATIONS:
- Simple: Audio File In → Analyze → visual parameter (no beat detection)
- Advanced: Audio File In → Audio Spectrum → Select → Math → visual parameter (frequency bands)
- Live: Audio Device In → Analyze → Beat → Trail → visual parameter (smoothed)
```

**Rules**:
- ONLY include chains seen in actual examples
- Show 2-3 variations if they exist
- Use brackets [visual parameter] for abstract targets

---

### Section 3: KEY OPERATORS & THEIR ROLES
**Format**:
```
KEY OPERATORS:
- {Operator Name} ({Family}): {Role in workflow}
  Settings: {param1=typical_value, param2=range}
```

**Example**:
```
KEY OPERATORS:
- Audio File In CHOP (CHOP): Loads audio file as data stream
  Settings: playmode='sequential', active=1

- Analyze CHOP (CHOP): Detects audio features (peaks, RMS, amplitude)
  Settings: function='Peak' (transients) or 'RMS' (energy), timeslice=1/60

- Beat CHOP (CHOP): Converts audio analysis to beat pulses
  Settings: threshold=0.3-0.7 (sensitivity), decay=0.5 (pulse length)

- Math CHOP (CHOP): Scales/remaps values for visual range
  Settings: range=[0-1] to [min-max], combchops='mult'
```

**Rules**:
- ONLY operators that actually appear in examples
- Parameter values = what's actually used (not defaults or theory)
- Show ranges when multiple examples use different values

---

### Section 4: TYPICAL PARAMETER VALUES
**Format**:
```
COMMON SETTINGS (from examples):
- {operator}.{param}: {value} - {when to use this}
```

**Example**:
```
COMMON SETTINGS (from examples):
- Analyze.function: 'Peak' for beat detection, 'RMS' for energy, 'Average' for smoothness
- Analyze.threshold: 0.3 (sensitive), 0.5 (balanced), 0.7 (only strong hits)
- Beat.decay: 0.3 (fast pulses), 0.5 (medium), 1.0 (sustained)
- Math.range: [0-1] to [1-3] for scale, [0-1] to [0-360] for rotation
```

**Rules**:
- ONLY values seen in real examples
- Explain what each range does ("fast pulses" not just "0.3")
- If no examples show a parameter, don't mention it

---

### Section 5: USE CASES
**Format**:
```
USE CASES:
- {Specific application}
- {Specific application}
```

**Example**:
```
USE CASES:
- Music visualization (VJ performances)
- Reactive installations (audio triggers animations)
- Game audio feedback (sound drives UI elements)
- Live performances (sync visuals to DJ sets)
```

**Rules**:
- ONLY use cases implied by example names/descriptions
- Be specific (not "creative projects")

---

### Section 6: RELATED WORKFLOWS
**Format**:
```
SEE ALSO:
- {Related workflow name}
- {Related workflow name}
```

**Example**:
```
SEE ALSO:
- Audio Spectrum Analysis (frequency-based instead of beat-based)
- MIDI-Reactive Visuals (musical note triggers)
- Motion-Reactive Visuals (camera/sensor input)
```

**Rules**:
- ONLY workflows that exist in your examples
- Show how they differ from this one

---

## Complete Example Output

```
WORKFLOW: Audio-Reactive Visuals - Beat Detection

SOLVES: Synchronizing visual parameters (scale, rotation, color) to music beats and audio energy in real-time

TYPICAL CHAIN:
Audio File In CHOP → Analyze CHOP → Beat CHOP → Math CHOP → [visual parameter]

VARIATIONS:
- Simple: Audio File In → Analyze → visual parameter (direct analysis)
- Advanced: Audio File In → Audio Spectrum → Select → Math → visual parameter (frequency bands)
- Live: Audio Device In → Analyze → Beat → Trail → visual parameter (smoothed pulses)

KEY OPERATORS:
- Audio File In CHOP (CHOP): Loads audio file as data stream
  Settings: playmode='sequential', active=1

- Analyze CHOP (CHOP): Detects audio features (peaks, RMS, amplitude)
  Settings: function='Peak' (transients) or 'RMS' (energy), timeslice=1/60

- Beat CHOP (CHOP): Converts audio analysis to beat pulses
  Settings: threshold=0.3-0.7 (sensitivity), decay=0.5 (pulse length)

- Math CHOP (CHOP): Scales/remaps values for visual range
  Settings: range=[0-1] to [min-max], combchops='mult'

COMMON SETTINGS (from examples):
- Analyze.function: 'Peak' for beat detection, 'RMS' for energy
- Analyze.threshold: 0.3 (sensitive), 0.5 (balanced), 0.7 (only strong hits)
- Beat.decay: 0.3 (fast pulses), 0.5 (medium), 1.0 (sustained)
- Math.range: [0-1] to [1-3] for scale, [0-1] to [0-360] for rotation

USE CASES:
- Music visualization (VJ performances)
- Reactive installations (audio triggers animations)
- Game audio feedback (sound drives UI elements)
- Live performances (sync visuals to DJ sets)

SEE ALSO:
- Audio Spectrum Analysis (frequency-based)
- MIDI-Reactive Visuals (note triggers)
- Motion-Reactive Visuals (camera input)

EXAMPLE SOURCES:
- analyzeCHOP examples 1, 3, 4
- audiofileinCHOP examples 1, 3
- beatCHOP examples (all)
```

---

## Generation Algorithm

```python
def generate_workflow_summary(workflow_name, example_list):
    """
    Generate workflow summary from multiple related examples.

    Args:
        workflow_name: e.g., "Audio-Reactive Visuals"
        example_list: List of semantic JSON examples showing this pattern
    """
    # Validate: need 3+ examples
    if len(example_list) < 3:
        return "ERROR: Need 3+ examples to confirm workflow pattern"

    # Extract common operator sequences
    chains = extract_operator_chains(example_list)
    common_chain = find_most_frequent_chain(chains)
    variations = find_chain_variations(chains)

    # Extract parameter usage patterns
    param_usage = analyze_parameter_patterns(example_list)

    # Infer use cases from curator summaries
    use_cases = extract_use_cases([ex['curator_summary'] for ex in example_list])

    # Format output
    return format_workflow(
        name=workflow_name,
        chain=common_chain,
        variations=variations,
        operators=extract_key_operators(common_chain),
        params=param_usage,
        use_cases=use_cases
    )
```

---

## Quality Checklist

Before outputting a workflow, verify:
- [ ] 3+ examples demonstrate this pattern
- [ ] All operators exist in TouchDesigner
- [ ] All connections appear in real examples
- [ ] Parameter values from actual usage
- [ ] Use cases inferred from curator text
- [ ] No invented workflows
- [ ] Variations all exist in examples

**If workflow appears in <3 examples**: Don't create it (might be unique, not a pattern)

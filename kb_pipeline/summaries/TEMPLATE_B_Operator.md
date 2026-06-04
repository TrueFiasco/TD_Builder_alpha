# Template B: Operator Summary

## Purpose
Create LLM-friendly summaries for individual operators that answer "When and how do I use this operator?" Based on wiki docs + examples showing real usage.

## Anti-Hallucination Rules ⚠️

### Data Sources:
1. **Wiki docs** (`td_universal_parsed.json`) - authoritative parameter specs
2. **Network examples** (semantic JSONs) - real usage patterns
3. **INDEX.tsv** curator summaries - use case context

### Validation:
- ✅ Parameter specs from wiki docs (authoritative)
- ✅ Usage patterns from examples (proven)
- ✅ Use cases from curator summaries (documented)
- ❌ DON'T invent parameters not in wiki
- ❌ DON'T suggest uses not seen in examples
- ❌ DON'T make up parameter values

---

## Template Structure

### Section 1: OPERATOR OVERVIEW
**Source**: Wiki `summary` field
**Format**:
```
OPERATOR: {Name} ({Family})
WHAT IT DOES: {1-2 sentence plain language explanation}
```

**Example**:
```
OPERATOR: Analyze CHOP (CHOP)
WHAT IT DOES: Extracts statistical features from channels (peaks, averages, RMS) and outputs them as single-value channels. Converts changing signals into summary values.
```

**Rules**:
- Rewrite wiki summary in plain language (not technical jargon)
- Focus on "what" not "how"
- 1-2 sentences max

---

### Section 2: WHEN TO USE
**Source**: Examples + curator summaries
**Format**:
```
WHEN TO USE:
- {Use case 1} - seen in {N examples}
- {Use case 2} - seen in {N examples}
```

**Example**:
```
WHEN TO USE:
- Beat detection: Extract peaks from audio for music sync - seen in 8 examples
- Signal monitoring: Track min/max/average of control values - seen in 12 examples
- Threshold triggering: Detect when signal crosses threshold - seen in 5 examples
```

**Rules**:
- ONLY use cases from actual examples
- Count how many examples show each pattern
- Describe the goal, not the parameters

---

### Section 3: COMMON PATTERNS
**Source**: Network examples (connections + operators)
**Format**:
```
COMMON CHAINS:
Input → {This Operator} → Output
```

**Example**:
```
COMMON CHAINS:
- Audio File In → Analyze CHOP → Beat CHOP (audio beat detection)
- Noise → Analyze CHOP → Math (tracking signal range)
- Wave → Analyze CHOP (x6 parallel) → [visual params] (multi-feature analysis)
```

**Rules**:
- ONLY patterns from real examples
- Show what typically comes before and after
- Include parenthetical use case

---

### Section 4: KEY PARAMETERS
**Source**: Wiki `parameters[]` + example usage
**Format**:
```
KEY PARAMETERS:
- {param_name} ({code}): {what it controls}
  Common values: {values from examples} - {when to use}
  Default: {wiki default}
```

**Example**:
```
KEY PARAMETERS:
- Function (function): What statistical measure to extract
  Common values: 'Peak' (beat detection), 'RMS' (energy), 'Average' (smoothing), 'Maximum', 'Minimum'
  Default: 'average'

- Threshold (threshold): Minimum level to register (0-1)
  Common values: 0.3 (sensitive), 0.5 (balanced), 0.7 (strong signals only)
  Default: 0.5

- Time Slice (timeslice): Analyze audio rate (1) or frame rate (0)
  Common values: 1 (audio analysis), 0 (control signals)
  Default: 0
```

**Rules**:
- ONLY parameters seen in examples OR critical from wiki
- Show actual values from examples
- Explain when to use each value
- Include wiki default for reference

---

### Section 5: EXAMPLE OUTPUTS
**Source**: Wiki parameter specs or examples
**Format**:
```
OUTPUTS:
- {channel_name}: {what it represents}
```

**Example**:
```
OUTPUTS:
- {input_chan}_maximum: Peak value found
- {input_chan}_minimum: Lowest value found
- {input_chan}_average: Mean value
- (varies by Function parameter selected)
```

**Rules**:
- Describe output channels created
- If dynamic, explain how they vary

---

### Section 6: TIPS & GOTCHAS
**Source**: Curator summaries (when they mention warnings/tips)
**Format**:
```
TIPS:
- {Practical advice from examples}

GOTCHAS:
- {Common mistakes or warnings from curator text}
```

**Example**:
```
TIPS:
- Use Time Slice=1 for audio analysis to analyze at audio rate (more accurate)
- Parallel Analyze CHOPs can extract multiple features simultaneously
- Combine with Trail CHOP to analyze over time windows

GOTCHAS:
- Default 'Average' may not be what you want - check Function parameter
- Time Slice=0 analyzes per-frame which can miss fast audio transients
```

**Rules**:
- ONLY include tips/gotchas from curator text
- If none documented, skip this section
- Don't make up advice

---

### Section 7: RELATED OPERATORS
**Source**: Wiki `related` field or co-occurrence in examples
**Format**:
```
RELATED OPERATORS:
- {Operator Name}: {How it's different/similar}
```

**Example**:
```
RELATED OPERATORS:
- Beat CHOP: Converts Analyze peaks into beat pulses
- Audio Spectrum CHOP: Frequency analysis instead of statistical
- Math CHOP: Often used downstream to scale Analyze output
- Trail CHOP: Analyze over time windows by feeding Trail → Analyze
```

**Rules**:
- ONLY operators that appear together in examples OR in wiki related field
- Explain relationship briefly

---

## Complete Example Output

```
OPERATOR: Analyze CHOP (CHOP)

WHAT IT DOES: Extracts statistical features from channels (peaks, averages, RMS) and outputs them as single-value channels. Converts time-varying signals into summary numbers.

WHEN TO USE:
- Beat detection: Extract peaks from audio for music sync - seen in 8 examples
- Signal monitoring: Track min/max/average of control values - seen in 12 examples
- Threshold detection: Find when signal crosses a level - seen in 5 examples
- Range calibration: Auto-scale inputs to 0-1 range - seen in 3 examples

COMMON CHAINS:
- Audio File In → Analyze CHOP → Beat CHOP (audio beat detection)
- Noise → Analyze CHOP → Math (tracking signal range)
- Wave → Analyze CHOP (x6 parallel) → [visual params] (multi-feature analysis)
- Trail → Analyze → Math (time-window statistics)

KEY PARAMETERS:
- Function (function): What statistical measure to extract
  Common values: 'Peak' (beat detection), 'RMS' (energy), 'Average' (smoothing), 'Maximum', 'Minimum'
  Default: 'average'

- Threshold (threshold): Minimum level to register (0-1)
  Common values: 0.3 (sensitive), 0.5 (balanced), 0.7 (strong signals only)
  Default: 0.5

- Time Slice (timeslice): Analyze audio rate (1) or frame rate (0)
  Common values: 1 (audio analysis), 0 (control signals)
  Default: 0

OUTPUTS:
- {input_chan}_maximum: Peak value found
- {input_chan}_minimum: Lowest value found
- {input_chan}_average: Mean value
- {input_chan}_rms: Root mean square (power)
- (output channels vary by Function parameter)

TIPS:
- Use Time Slice=1 for audio to analyze at audio rate (44.1kHz) not frame rate (60Hz)
- Create multiple parallel Analyze CHOPs to extract multiple features simultaneously
- Combine with Trail CHOP to analyze over time windows instead of per-frame

GOTCHAS:
- Default Function='Average' may not be what you want - check this parameter
- Time Slice=0 analyzes once per frame which can miss fast audio transients
- Output channel names change based on input + Function selected

RELATED OPERATORS:
- Beat CHOP: Converts Analyze peaks into beat pulses with decay
- Audio Spectrum CHOP: Frequency-domain analysis instead of time-domain
- Math CHOP: Typically used downstream to scale/remap Analyze output
- Trail CHOP: Feed into Analyze to analyze over time windows
- Filter CHOP: Smooth signals before analyzing

EXAMPLE SOURCES:
- analyzeCHOP examples 1-5 (12 total examples in database)
- Used in 47 other examples (audio workflows, signal processing, calibration)

FAMILY: CHOP
PYTHON CLASS: analyzeCHOP_Class
PARAMETER COUNT: 27
```

---

## Generation Algorithm

```python
def generate_operator_summary(operator_name, wiki_data, examples):
    """
    Generate operator summary from wiki docs + examples.

    Args:
        operator_name: e.g., "Analyze CHOP"
        wiki_data: Dict from td_universal_parsed.json
        examples: List of semantic JSONs that use this operator
    """
    # Section 1: Overview (from wiki)
    overview = simplify_wiki_summary(wiki_data['summary'])

    # Section 2: When to Use (from examples)
    use_cases = extract_use_cases_from_examples(examples)

    # Section 3: Common Patterns (from example connections)
    patterns = find_operator_chains(examples, operator_name)

    # Section 4: Key Parameters (wiki + example usage)
    params = merge_wiki_params_with_usage(
        wiki_data['parameters'],
        extract_parameter_values(examples, operator_name)
    )

    # Section 5: Outputs (from wiki)
    outputs = wiki_data.get('outputs', [])

    # Section 6: Tips & Gotchas (from curator summaries)
    tips = extract_tips_from_curator_text(examples)

    # Section 7: Related (from wiki + co-occurrence)
    related = merge_wiki_related(
        wiki_data.get('related', []),
        find_co_occurring_operators(examples, operator_name)
    )

    return format_operator_summary(
        name=operator_name,
        overview=overview,
        use_cases=use_cases,
        patterns=patterns,
        params=params,
        outputs=outputs,
        tips=tips,
        related=related,
        metadata={
            'family': wiki_data['family'],
            'python_class': wiki_data['python_class'],
            'param_count': len(wiki_data['parameters']),
            'example_count': len(examples)
        }
    )
```

---

## Quality Checklist

Before outputting an operator summary, verify:
- [ ] Overview accurately reflects wiki summary
- [ ] All use cases come from real examples
- [ ] All patterns come from real examples
- [ ] Parameter values cited appear in examples
- [ ] Tips/gotchas quoted from curator text
- [ ] Related operators either in wiki or co-occur in examples
- [ ] No invented behaviors or use cases
- [ ] Example count is accurate

**If operator has no examples**: Skip "When to Use" and "Common Patterns" sections rather than guess.

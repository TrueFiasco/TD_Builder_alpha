# Template C: Network Biography (Snippet/Example Summary)

## Purpose
Generate rich, LLM-friendly summaries of TouchDesigner network examples by analyzing the actual parsed network JSON + curator summary from INDEX.tsv.

## Anti-Hallucination Rules ⚠️

**CRITICAL**: This template ONLY describes data that EXISTS in the source files.

### Strict Data Sources:
1. **INDEX.tsv** → `text` field = curator summary (human-written context)
2. **Semantic JSON** → `operators[]`, `connections[]`, `network_pattern`
3. **NEVER**:
   - Infer operators not in `operators[]`
   - Assume connections not in `connections[]`
   - Guess parameter values not in `parameters{}`
   - Add use cases not implied by curator summary
   - Describe behavior beyond what's documented

### Validation Checklist:
- ✅ Every operator mentioned exists in `operators[]`
- ✅ Every connection described exists in `connections[]`
- ✅ Every parameter cited exists in `parameters{}`
- ✅ Topology facts come from `network_pattern{}`
- ✅ Use case inferred from curator `text` only

---

## Template Structure

### Section 1: USE CASE (from INDEX.tsv)
**Source**: `text` field from INDEX.tsv
**Format**:
```
USE CASE: {curator summary - verbatim or lightly paraphrased}
```

**Example**:
```
USE CASE: These examples show the different functions of the Analyze CHOP.
```

**Rules**:
- Use curator's language (they know the intent)
- If `text` is empty, write: "USE CASE: Not documented"
- Don't embellish or add your own interpretation

---

### Section 2: DATA FLOW (from semantic JSON)
**Source**: `operators[]` + `connections[]`
**Format**:
```
DATA FLOW:
{source_op} ({type}) → {intermediate_op} ({type}, param=value) → {destination_op} ({type})
```

**Example**:
```
DATA FLOW:
wave1 (CHOP:wave, decay=0.235) → branches to 6 parallel Analyze CHOPs:
  → analyze_max (function='maximum')
  → analyze_min (function='minimum')
  → analyze_average (function='average')
  → analyze_total_peeks (function='totalpeaks')
  → analyze_first_peak_index (function='firstpeakindex')
  → analyze_first_peak_value (function='firstpeakvalue')
```

**Rules**:
- ONLY list operators from `operators[].name`
- ONLY list connections from `connections[]`
- ONLY include parameters from `parameters{}` (exclude noisy ones: defaultreadencoding, language, wordwrap)
- Use exact `type` format (e.g., "CHOP:analyze")
- If no connections: "DATA FLOW: Isolated operators (no connections documented)"

---

### Section 3: NETWORK TOPOLOGY (from network_pattern)
**Source**: `network_pattern{}` from semantic JSON
**Format**:
```
TOPOLOGY: {pattern_type}
- Operators: {operator_count}
- Connections: {connection_count}
- Pattern: {has_parallel_paths ? "parallel branches" : "linear chain"} {has_feedback_loops ? "with feedback" : ""}
- Max chain depth: {max_chain_length}
```

**Example**:
```
TOPOLOGY: Parallel broadcast pattern
- Operators: 8 (1 source, 6 analyzers, 1 readme)
- Connections: 6
- Pattern: Single source broadcasting to 6 parallel branches
- Max chain depth: 2 (wave → analyze)
```

**Rules**:
- Use EXACT values from `network_pattern{}`
- Don't describe topology beyond what's in the data
- If `network_pattern` missing: "TOPOLOGY: Not analyzed"

---

### Section 4: KEY OPERATORS (from operators[])
**Source**: `operators[]` with meaningful `parameters{}`
**Format**:
```
KEY OPERATORS:
- {op_name} ({type}): {param1=value1, param2=value2} - {what it does based on params}
```

**Example**:
```
KEY OPERATORS:
- wave1 (CHOP:wave): decay=0.235 - Generates test waveform with fast decay
- analyze_max (CHOP:analyze): function='maximum' - Extracts peak value
- analyze_min (CHOP:analyze): function='minimum' - Extracts lowest value
- analyze_average (CHOP:analyze): function='average' - Computes mean value
```

**Rules**:
- ONLY include operators with non-default parameters
- Exclude readme/documentation operators (DAT:text with wordwrap, etc.)
- Keep descriptions factual ("extracts peak value" not "useful for beat detection")
- If no meaningful parameters: "KEY OPERATORS: All using default settings"

---

### Section 5: OPERATOR TYPE SUMMARY (from network_pattern.operator_types)
**Source**: `network_pattern.operator_types{}`
**Format**:
```
OPERATOR TYPES:
- {type}: {count}
```

**Example**:
```
OPERATOR TYPES:
- CHOP:wave: 1 (signal source)
- CHOP:analyze: 6 (analysis functions)
- DAT:text: 1 (documentation)
```

**Rules**:
- Use EXACT counts from `operator_types{}`
- Add brief role description in parentheses (source/processor/output)
- Don't invent categories not in the data

---

### Section 6: EXAMPLE NAME & METADATA
**Source**: `name` field, file paths
**Format**:
```
EXAMPLE: {operator_type}/{example_name}
SOURCE: {source_file path}
```

**Example**:
```
EXAMPLE: analyzeCHOP/example1
SOURCE: C:\TD_Projects\td_builder_workspace\output\lossless\analyzeCHOP_lossless.json
```

---

## Complete Example Output

```
NETWORK BIOGRAPHY: Analyze CHOP Functions Demo

USE CASE: These examples show the different functions of the Analyze CHOP.

DATA FLOW:
wave1 (CHOP:wave, decay=0.235) → branches to 6 parallel Analyze CHOPs:
  → analyze_max (function='maximum')
  → analyze_min (function='minimum')
  → analyze_average (function='average')
  → analyze_total_peeks (function='totalpeaks')
  → analyze_first_peak_index (function='firstpeakindex')
  → analyze_first_peak_value (function='firstpeakvalue')

TOPOLOGY: Parallel broadcast pattern
- Operators: 8 (1 source, 6 analyzers, 1 readme)
- Connections: 6
- Pattern: Single source broadcasting to 6 parallel branches
- Max chain depth: 2 (wave → analyze)

KEY OPERATORS:
- wave1 (CHOP:wave): decay=0.235 - Test signal with fast decay
- analyze_max (CHOP:analyze): function='maximum' - Extracts peak value
- analyze_min (CHOP:analyze): function='minimum' - Extracts lowest value
- analyze_average (CHOP:analyze): function='average' - Computes mean
- analyze_total_peeks (CHOP:analyze): function='totalpeaks' - Counts peaks
- analyze_first_peak_index (CHOP:analyze): function='firstpeakindex' - Finds first peak position
- analyze_first_peak_value (CHOP:analyze): function='firstpeakvalue' - Gets first peak amplitude

OPERATOR TYPES:
- CHOP:wave: 1 (signal source)
- CHOP:analyze: 6 (analysis functions)
- DAT:text: 1 (documentation)

EXAMPLE: analyzeCHOP/example1
FAMILY: CHOP
```

---

## Generation Algorithm (for automated skill)

```python
def generate_network_biography(semantic_json_path, index_tsv_row):
    # Load data
    semantic = load_json(semantic_json_path)
    example = semantic['examples'][0]  # or iterate all
    curator_text = index_tsv_row['text']

    # Section 1: USE CASE
    use_case = curator_text if curator_text else "Not documented"

    # Section 2: DATA FLOW
    # Build connection graph from connections[]
    flow = build_data_flow(example['connections'], example['operators'])

    # Section 3: TOPOLOGY
    pattern = example['network_pattern']
    topology = describe_topology(pattern)

    # Section 4: KEY OPERATORS
    # Filter operators with meaningful params
    key_ops = filter_operators(example['operators'],
                               exclude_params=['defaultreadencoding', 'language', 'wordwrap'])

    # Section 5: OPERATOR TYPES
    op_types = pattern['operator_types']

    # Section 6: METADATA
    metadata = {
        'example': f"{semantic['operator_type']}/{example['name']}",
        'source': semantic['source_file']
    }

    # Format output
    return format_biography(use_case, flow, topology, key_ops, op_types, metadata)
```

---

## Notes for Skill Development

### Parameters to Exclude (Noise):
```python
NOISY_PARAMS = [
    'defaultreadencoding',
    'language',
    'wordwrap',
    'pageindex',
    'w', 'h',  # dimensions without context
    'mousewheel',
    'uvbuttonsleft', 'uvbuttonsmiddle', 'uvbuttonsright',
    'topsmoothness'
]
```

### Parameters to Always Include (Signal):
```python
IMPORTANT_PARAMS = [
    'function',  # operation mode
    'threshold',  # level/sensitivity
    'decay', 'attack',  # timing
    'gain', 'speed', 'frequency',  # control params
    'resolutionw', 'resolutionh',  # meaningful dimensions
    'tx', 'ty', 'tz', 'rx', 'ry', 'rz',  # transforms
    'scale', 'scalex', 'scaley', 'scalez'
]
```

### Operator Role Classification:
```python
def classify_operator_role(op):
    type_family = op['type'].split(':')[0]
    type_name = op['type'].split(':')[1] if ':' in op['type'] else ''

    # Has no inputs in connections[]
    if is_source(op, connections):
        return 'source'

    # Has no outputs in connections[]
    elif is_sink(op, connections):
        return 'output'

    # In middle of chain
    else:
        return 'processor'
```

---

## Quality Checklist

Before outputting a biography, verify:
- [ ] Every operator name exists in semantic JSON
- [ ] Every connection exists in semantic JSON
- [ ] Every parameter exists in semantic JSON
- [ ] Curator summary quoted accurately
- [ ] No assumptions about use cases beyond curator text
- [ ] No inferred behaviors not documented
- [ ] Topology facts match network_pattern exactly
- [ ] Operator counts correct

**If unsure**: Leave section blank or write "Not documented" rather than guess.

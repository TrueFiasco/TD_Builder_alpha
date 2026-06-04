# Practical Concerns

This document covers context limits, state between calls, and hardcoded assumptions.

---

## Context Limits

### Token Usage by Agent

Based on Teardrop V2 run:

| Agent | Input Tokens | Output Tokens | Total |
|-------|--------------|---------------|-------|
| KB Query | ~200 | ~150 | ~350 |
| Creative Expert | ~1,500 | ~2,000 | ~3,500 |
| CG Expert | ~1,800 | ~2,200 | ~4,000 |
| TD Designer | ~2,000 | ~3,500 | ~5,500 |
| Critic | ~1,200 | ~600 | ~1,800 |
| Builder | ~1,500 | ~3,000 | ~4,500 |
| **Total** | **~8,200** | **~11,450** | **~19,650** |

### Context Composition

Each agent's context includes:

```yaml
context_components:
  system_prompt: ~500-1000 tokens
  expert_prompt: ~800-1500 tokens
  blackboard_sections: ~500-3000 tokens (depends on iteration)
  expertise_yaml: ~1000-2000 tokens
  previous_feedback: ~200-500 tokens (if revision)
```

### Truncation Points

**Currently**: No automatic truncation implemented.

**Potential Issues**:
- Large expertise files could exceed context
- Deep revision cycles accumulate history
- Complex network designs grow large

**Mitigations**:
1. Expertise files are loaded selectively per expert
2. Only relevant blackboard sections are included
3. Summary generator could compress verbose outputs

### Token Limits by Model

| Model | Context Window | Typical Run Fits? |
|-------|----------------|-------------------|
| Claude Sonnet | 200K | Yes, easily |
| Claude Opus | 200K | Yes, easily |
| Claude Haiku | 200K | Yes, easily |

Current implementation is well within limits.

---

## State Between Calls

### What's Persisted

The **Blackboard** is the primary persistence mechanism:

```python
blackboard = Blackboard(
    project_name="teardrop",
    persist_path=Path("output/teardrop/blackboard.yaml")
)

# Persisted on every write:
blackboard.write(SectionID.CREATIVE_VISION, content, author="creative_expert")
# → Writes to disk immediately
```

**Persisted State**:
- All 7 blackboard sections
- Version history for each section
- Blocking issues queue
- Current phase
- Iteration count
- Event log (audit trail)

### What's NOT Persisted

**Expert Internal State**:
- Each expert invocation starts fresh
- No memory of previous runs (except via blackboard)
- No learning curve within a session

**KB Query Cache**:
- Cached per-process only
- Not persisted across sessions
- Re-loads YAML files on new run

**Metrics**:
- Token counts collected in memory
- Can be exported but not automatically persisted

### Fresh Start vs Resume

```python
# Fresh start - new blackboard
bb = Blackboard(project_name="new_project")

# Resume - load existing
bb = Blackboard(
    project_name="teardrop",
    persist_path=Path("output/teardrop/blackboard.yaml")
)
# Automatically loads previous state
```

### Subagent State

When using Task agents (Claude Code subagents):

```yaml
state_model:
  subagent_invocation:
    - Receives: Rendered prompt with full context
    - Returns: Structured output
    - No persistent state between invocations

  context_passing:
    - All relevant info must be in the prompt
    - Blackboard content is serialized into prompt
    - Expert expertise is injected at render time
```

---

## Hardcoded Assumptions

### Fixed Operator Names

**In Patterns** (`td_network_patterns.yaml`):
```yaml
# These operator names are hardcoded as typical chains
audio_reactive_visuals:
  typical_chain:
    - "audiofilein_CHOP"
    - "analyze_CHOP"
    - "math_CHOP"
    - "lag_CHOP"
```

### Fixed Connection Patterns

**In TD Designer Build Prompt**:
```yaml
# Standard spacing hardcoded
position_rules:
  horizontal_spacing: 150  # pixels
  vertical_spacing: 100    # pixels
```

### Fixed Container Names

**In Build Scripts** (`build_teardrop.py`):
```python
# Container hierarchy is fixed
containers = [
    "project1",      # Root container name
    "audio",         # Audio analysis container
    "visual",        # Visual generation container
    "output"         # Output container
]
```

### Fixed Expression Paths

**WARNING**: These are guessed and likely wrong:
```python
# In build_teardrop.py
expressions = {
    "noise1.amp": "op('../audio/audioAnalysis/out1')['low']",
    "hsv1.satmult": "op('../audio/audioAnalysis/out1')['mid']",
}

# The actual audioAnalysis output structure may differ!
# Need to verify in TD:
# - What is the output null path?
# - What are the actual channel names?
```

### Fixed File Structure

**TOE/TOX File Format**:
```python
# TOC ordering is hardcoded (and critical!)
toc_order = [
    ".n files first",      # Operator definitions
    ".cparm files second", # Custom parameters
    ".parm files third",   # Standard parameters
    ".panel files last"    # Panel definitions
]
```

### Fixed Quality Thresholds

**In Critic**:
```python
# Hardcoded approval threshold
APPROVAL_THRESHOLD = 0.65

# Hardcoded max revision cycles
MAX_REVISION_CYCLES = 3
```

### Fixed Palette Paths

**In KB Query**:
```python
# Palette location assumed
PALETTE_BASE = "C:/Program Files/Derivative/TouchDesigner/Samples/Palette"

# Specific component paths hardcoded
AUDIO_ANALYSIS_PATH = "Palette/Tools/audioAnalysis.tox"
```

### Fixed Resolution Defaults

```yaml
# Default resolution when not specified
default_resolution: [1920, 1080]
default_fps: 60
```

---

## Potential Breaking Points

### If TouchDesigner Version Changes

```yaml
risk: HIGH
affected:
  - Operator names may change
  - Parameter names may change
  - Palette component structure may differ

mitigation:
  - Version tag in expertise files
  - Validation against operator_param_schemas.json
  - TD version in event log evidence
```

### If Palette Component Changes

```yaml
risk: MEDIUM
affected:
  - audioAnalysis output channel names
  - Component internal structure
  - Custom parameter names

mitigation:
  - Document actual channel names from TD inspection
  - Version palette components in KB
```

### If Expression Syntax Changes

```yaml
risk: LOW
affected:
  - op() references
  - par. syntax

mitigation:
  - TD expression syntax is stable
  - Validate expressions before build
```

---

## Configuration vs Hardcoding

### Currently Configurable

```yaml
# Via StrategyConfig
max_iterations: 15
quality_targets:
  creative: 0.8
  technical: 0.8
  design: 0.75
  overall: 0.8
exploration: 3
convergence_window: 3

# Via workflow config
kb_query_enabled: true
mock_mode: false
```

### Should Be Configurable (TODO)

```yaml
# Currently hardcoded, should be config
approval_threshold: 0.65  # → config
max_revision_cycles: 3    # → config
position_spacing: [150, 100]  # → config
default_resolution: [1920, 1080]  # → config
```

---

## Environment Dependencies

### Required File Paths

```yaml
required_paths:
  expertise_dir: "meta_agentic/expertise/"
  experts_dir: "meta_agentic/experts/"
  operator_schemas: "operator_param_schemas.json"
  output_dir: "test_output/"  # Or configurable

optional_paths:
  palette_dir: "C:/Program Files/Derivative/TouchDesigner/..."
  expanded_tox_cache: ".tox.dir expansion cache"
```

### Required Python Packages

```
pyyaml        # YAML parsing
anthropic     # Claude API (for API mode)
```

### TouchDesigner Not Required for Build

The system can generate TOE files without TD installed.
TD is only needed to:
1. Verify the output opens
2. Check actual channel names
3. Test runtime behavior

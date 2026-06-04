# KB Query Interface

This document describes what an expert actually calls when querying the Knowledge Base, what parameters can be used, and what format results come back in.

---

## KnowledgeBase Initialization

```python
from meta_agentic.execution.kb_query import KnowledgeBase, get_default_kb

# Method 1: Use default paths
kb = get_default_kb()

# Method 2: Specify custom path
kb = KnowledgeBase(base_path=Path("meta_agentic/expertise"))
```

---

## Query Functions

### 1. query_operators()

**Purpose**: Query operator expertise by family, name, or purpose.

**Parameters**:
```python
filter_params: dict
    - family: str       # "CHOP", "TOP", "SOP", "COMP", "MAT", "DAT"
    - name: str         # Specific operator name
    - purpose_contains: str  # Search in purpose text
```

**Returns**: `list[dict]` - List of matching operators

**Example Call**:
```python
# Find all audio-related CHOP operators
results = kb.query_operators({
    "family": "CHOP",
    "purpose_contains": "audio"
})
```

**Example Return**:
```python
[
    {
        "family": "CHOP",
        "name": "audiofilein",
        "purpose": "Loads audio from file or input device",
        "common_params": ["file", "device", "rate"],
        "usage_patterns": ["audio_reactive"]
    },
    {
        "family": "CHOP",
        "name": "analyze",
        "purpose": "Analyzes audio frequency content",
        "common_params": ["function", "period"],
        "usage_patterns": ["audio_reactive", "data_analysis"]
    }
]
```

---

### 2. query_patterns()

**Purpose**: Query network patterns by workflow category.

**Parameters**:
```python
category: str  # Pattern category name (or partial match)
```

**Returns**: `list[dict]` - List of matching patterns

**Example Call**:
```python
results = kb.query_patterns("audio_reactive")
```

**Example Return**:
```python
[
    {
        "category": "audio_reactive_visuals",
        "description": "Synchronizing visual parameters with audio input",
        "typical_chain": [
            "audiofilein_CHOP",
            "analyze_CHOP",
            "math_CHOP",
            "lag_CHOP"
        ],
        "key_techniques": [
            "FFT analysis",
            "envelope following",
            "CHOP exports to TOP parameters"
        ],
        "common_mappings": {
            "bass": "scale, intensity",
            "mids": "color, saturation",
            "highs": "detail, sparkle"
        }
    }
]
```

---

### 3. query_glsl()

**Purpose**: Query GLSL shader expertise by type.

**Parameters**:
```python
shader_type: str  # "glsl_top", "glsl_mat", "vertex_template", etc.
```

**Returns**: `dict` - GLSL expertise for that type

**Example Call**:
```python
result = kb.query_glsl("glsl_top")
```

**Example Return**:
```python
{
    "template": """
        // GLSL TOP template
        uniform float uTime;
        out vec4 fragColor;
        void main() {
            vec2 uv = vUV.st;
            fragColor = TDOutputSwizzle(vec4(uv, 0.0, 1.0));
        }
    """,
    "uniforms": {
        "uTime": "absTime.seconds",
        "uResolution": "uTDOutputInfo.res.xy"
    },
    "guidelines": [
        "Always use TDOutputSwizzle for output",
        "Access inputs via texture(sTD2DInputs[0], uv)"
    ],
    "common_functions": {
        "noise": "Simplex/Perlin noise",
        "hash": "Fast pseudo-random"
    }
}
```

---

### 4. query_palette_catalog()

**Purpose**: Semantic search across 278 palette components. **This is the primary discovery tool.**

**Parameters**:
```python
keywords: list[str]  # Search keywords
category: str = None  # Optional category filter
max_results: int = 15  # Maximum results to return
```

**Returns**: `list[dict]` - Sorted by relevance score

**Example Call**:
```python
results = kb.query_palette_catalog(
    keywords=["audio", "beat", "analysis"],
    category=None,
    max_results=10
)
```

**Example Return**:
```python
[
    {
        "name": "audioAnalysis",
        "category": "Tools",
        "purpose": "Extract frequency bands and audio features",
        "tox_path": "Palette/Tools/audioAnalysis.tox",
        "use_cases": ["beat detection", "audio visualization", "reactive parameters"],
        "wiki_url": "https://docs.derivative.ca/...",
        "has_ui": True,
        "key_operators": ["audiofilein", "analyze", "math"],
        "relevance_score": 9.0  # Name + purpose + use_case matches
    },
    {
        "name": "audioReact",
        "category": "Techniques",
        "purpose": "Pre-built audio reactive system",
        "tox_path": "Palette/Techniques/audioReact.tox",
        "relevance_score": 6.5
    }
]
```

**Scoring Algorithm**:
```python
score = 0.0
for keyword in keywords:
    if keyword in name.lower():
        score += 3.0  # Name match highest
    if keyword in purpose.lower() or keyword in summary.lower():
        score += 2.0  # Purpose match
    if keyword in category.lower():
        score += 1.5  # Category match
    if any(keyword in uc for uc in use_cases):
        score += 1.0  # Use case match
```

---

### 5. get_palette_recommendations_for_prompt()

**Purpose**: Convenience method - analyzes prompt and returns relevant palette components.

**Parameters**:
```python
prompt: str  # User's prompt or creative vision text
```

**Returns**: `list[dict]` - Recommended palette components

**Example Call**:
```python
results = kb.get_palette_recommendations_for_prompt(
    "Create an audio-reactive particle system with glowing effects"
)
```

**Extracted Keywords**: `["audio", "particle", "glow"]`

---

### 6. load_expertise()

**Purpose**: Load raw YAML expertise file.

**Parameters**:
```python
file_name: str  # Name of expertise file
```

**Returns**: `dict` - Parsed YAML content

**Example Call**:
```python
operators = kb.load_expertise("td_operators.yaml")
patterns = kb.load_expertise("td_network_patterns.yaml")
creative = kb.load_expertise("creative_vision.yaml")
```

---

## Validation Functions (Anti-Hallucination)

### validate_operator()

```python
kb.validate_operator("CHOP", "noise")  # Returns True
kb.validate_operator("CHOP", "fakeop")  # Returns False
```

### validate_parameter()

```python
kb.validate_parameter("CHOP", "noise", "type")  # Returns True
kb.validate_parameter("CHOP", "noise", "fakeparam")  # Returns False
```

### check_operators_exist()

```python
missing = kb.check_operators_exist([
    "CHOP:noise",
    "CHOP:fakeop",
    "TOP:moviefilein"
])
# Returns: ["CHOP:fakeop"]
```

### validate_network_design()

```python
result = kb.validate_network_design(network_json)

# result.valid: bool
# result.missing: list[str]  - Missing operators
# result.errors: list[str]   - Blocking errors
# result.warnings: list[str] - Non-blocking warnings
```

---

## Available Expertise Files

| File | Content | Entry Count |
|------|---------|-------------|
| `td_operators.yaml` | Operator mental models | 600+ |
| `td_network_patterns.yaml` | Workflow patterns | 11 |
| `td_parameters.yaml` | Parameter usage | varies |
| `td_glsl.yaml` | GLSL expertise | varies |
| `td_python.yaml` | Python expertise | varies |
| `palette_semantic_catalog.yaml` | Palette components | 278 |
| `palette_expertise.yaml` | Palette integration | varies |
| `creative_vision.yaml` | Moods, aesthetics | varies |
| `cg_concepts.yaml` | CG techniques | varies |
| `critique_patterns.yaml` | Review criteria | varies |

---

## Expertise File Enum

```python
from meta_agentic.execution.kb_query import ExpertiseFiles

ExpertiseFiles.OPERATORS          # "td_operators.yaml"
ExpertiseFiles.PATTERNS           # "td_network_patterns.yaml"
ExpertiseFiles.GLSL               # "td_glsl.yaml"
ExpertiseFiles.PYTHON             # "td_python.yaml"
ExpertiseFiles.PALETTE            # "palette_expertise.yaml"
ExpertiseFiles.PALETTE_SEMANTIC   # "palette_semantic_catalog.yaml"
ExpertiseFiles.CREATIVE_VISION    # "creative_vision.yaml"
ExpertiseFiles.CG_CONCEPTS        # "cg_concepts.yaml"
ExpertiseFiles.CRITIQUE_PATTERNS  # "critique_patterns.yaml"
```

---

## Expert-to-Expertise Mapping

Each expert loads specific expertise files:

```python
expertise_mapping = {
    "creative_expert": [CREATIVE_VISION],
    "cg_expert": [CG_CONCEPTS, OPERATORS],
    "td_designer": [OPERATORS, PATTERNS, PARAMETERS],
    "td_glsl_expert": [GLSL],
    "td_python_expert": [PYTHON],
    "network_builder": [NETWORK_BUILDING, FILE_FORMATS],
    "critic": [CRITIQUE_PATTERNS],
}
```

---

## Caching

The KnowledgeBase caches loaded YAML files:

```python
# First call loads from disk
data = kb.load_expertise("td_operators.yaml")

# Subsequent calls return cached version
data = kb.load_expertise("td_operators.yaml")  # Instant
```

Cache is per-instance and not persisted across sessions.

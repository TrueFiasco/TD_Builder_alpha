# TouchDesigner Knowledge Base Audit
## Generated: December 2024

---

## 1. KNOWLEDGE ASSETS SUMMARY

### Operator Semantics (Primary)
| Asset | Count | Description |
|-------|-------|-------------|
| `all_operator_wiki_semantics.yaml` | 686 operators | Full operator wiki with 11,144 parameters |
| - CHOP | 175 ops, 2,144 params | Channel operators |
| - TOP | 154 ops, 1,837 params | Texture operators |
| - SOP | 117 ops, 1,442 params | Surface operators |
| - POP | 107 ops, 1,806 params | Particle operators |
| - DAT | 77 ops, 816 params | Data operators |
| - COMP | 43 ops, 2,556 params | Component operators |
| - MAT | 13 ops, 543 params | Material operators |

### Snippet Network Descriptions
| Asset | Lines | Description |
|-------|-------|-------------|
| `CHOP_descriptions.yaml` | 930 | CHOP snippet examples with context |
| `TOP_descriptions.yaml` | 352 | TOP snippet examples |
| `SOP_descriptions.yaml` | 400 | SOP snippet examples |
| `DAT_descriptions.yaml` | 261 | DAT snippet examples |
| `POP_descriptions.yaml` | 304 | POP snippet examples |
| `COMP_descriptions.yaml` | 169 | COMP snippet examples |
| `MAT_descriptions.yaml` | 34 | MAT snippet examples |

### Concepts & Classes
| Asset | Lines | Description |
|-------|-------|-------------|
| `concept_semantic_descriptions.yaml` | 1,379 | TD concepts (174 total) |
| `class_semantic_descriptions.yaml` | 1,278 | Python API class methods |
| `base_class_semantics.yaml` | 151 | Base class API |

### Python Knowledge
| Asset | Count | Description |
|-------|-------|-------------|
| `python_examples.json` | 18,062 | Code snippets from wiki |
| `python_patterns_semantics.yaml` | 90 lines | Common coding patterns |
| `python_callbacks_semantics.yaml` | 54 lines | Callback signatures |

### Steering & Decision Helpers
| Asset | Lines | Description |
|-------|-------|-------------|
| `steering_semantic_descriptions.yaml` | 76 | GLSL vs Python vs Native guidance |

---

## 2. DATA STRUCTURE ANALYSIS

### Ready for Embedding (Good Structure)
✅ **Operator Wiki** (`all_operator_wiki_semantics.yaml`)
- Each operator has: `summary`, `python_class`, `parameters{}`
- Parameters have: `description`, `section`
- Clear hierarchical structure by family

✅ **Concepts** (`concept_semantic_descriptions.yaml`)
- Key-value pairs: `concept_name: description`
- Clean 1-2 sentence descriptions
- Good semantic density

✅ **Steering Descriptions** (`steering_semantic_descriptions.yaml`)
- Clear key-value pairs
- Decision-focused language
- Good for query classification

✅ **Python Patterns/Callbacks**
- Code + description pairs
- Clear use-case oriented

### Needs Transformation
⚠️ **Snippet Descriptions** (`{FAMILY}_descriptions.yaml`)
- Nested by operator, then by example
- Need to flatten: "operator + example_description"

⚠️ **Python Examples** (`python_examples.json`)
- 18,062 raw code snippets
- Need: code + semantic description pairs
- Currently just code with minimal context

⚠️ **Class Methods** (`class_semantic_descriptions.yaml`)
- Nested by class, then by method
- Need to flatten: "ClassName.method: description"

---

## 3. EMBEDDING READINESS SCORE

| Category | Ready | Needs Work | Notes |
|----------|-------|------------|-------|
| Operator Summaries | ✅ 686 | - | Embed as-is |
| Operator Parameters | ✅ 11,144 | - | Embed with operator context |
| Concepts | ✅ 174 | - | Embed as-is |
| Steering | ✅ 30 | - | Embed as-is |
| Class Methods | ⚠️ | ~500 | Flatten structure |
| Snippet Examples | ⚠️ | ~300 | Flatten structure |
| Python Examples | ⚠️ | 18,062 | Need semantic descriptions |

**Immediately Embeddable: ~12,000 items**
**After Preprocessing: ~30,000 items**

---

## 4. RECOMMENDED EMBEDDING STRATEGY

### Document Types for Vector Store

```
TYPE 1: Operator (686 documents)
{
  "id": "Circle_TOP",
  "type": "operator",
  "family": "TOP",
  "text": "Circle TOP - Generates circular or elliptical shapes. Python class: circleTOP_Class",
  "metadata": {"family": "TOP", "python_class": "circleTOP_Class"}
}

TYPE 2: Parameter (11,144 documents)
{
  "id": "Circle_TOP.radius",
  "type": "parameter",
  "parent_op": "Circle_TOP",
  "text": "Circle TOP radius parameter - X and Y radii of the Circle. For polygons, only X radius is used.",
  "metadata": {"operator": "Circle_TOP", "section": "Circle"}
}

TYPE 3: Concept (174 documents)
{
  "id": "concept_Art-Net",
  "type": "concept",
  "text": "Art-Net: A protocol for transmitting DMX lighting control signals over Ethernet networks.",
  "metadata": {"category": "protocol"}
}

TYPE 4: Steering (30 documents)
{
  "id": "steering_glsl_blur",
  "type": "steering",
  "text": "Create a custom blur effect on an image using a pixel shader. Use GLSL TOP...",
  "metadata": {"approach": "glsl"}
}

TYPE 5: Python Pattern (20 documents)
{
  "id": "pattern_access_chop_value",
  "type": "python_pattern",
  "text": "Get a single value from a CHOP channel: v = op('constant1')['chan1'][0]",
  "metadata": {"category": "chop_access"}
}

TYPE 6: Callback (13 documents)
{
  "id": "callback_onValueChange",
  "type": "callback",
  "text": "onValueChange(panelValue, prevValue) - Executes when Panel value changes for reactive UI.",
  "metadata": {"signature": "onValueChange(panelValue, prevValue)"}
}
```

### Embedding Model Recommendation
- **Model**: `sentence-transformers/all-MiniLM-L6-v2` (fast, good quality)
- **Alternative**: `text-embedding-3-small` (OpenAI, higher quality)
- **Dimension**: 384 (MiniLM) or 1536 (OpenAI)

### Vector Store Options
1. **ChromaDB** - Local, simple, good for development
2. **Pinecone** - Cloud, scalable, production-ready
3. **FAISS** - Facebook's library, very fast, local
4. **Qdrant** - Modern, filtering support, good hybrid search

---

## 5. QUERY PATTERNS TO SUPPORT

The embedding system should handle these query types:

### Operator Discovery
- "How do I blur an image?" → Blur_TOP
- "What operators work with audio?" → Audio*_CHOP
- "Create particles" → POP operators

### Parameter Lookup
- "How do I set circle radius?" → Circle_TOP.radius
- "What controls blur strength?" → Blur_TOP.filterwidth

### Concept Explanation
- "What is Art-Net?" → Art-Net concept
- "How does instancing work?" → Instancing concept

### Code Generation Steering
- "Custom image effect" → GLSL steering
- "Read a file" → Python steering
- "Basic blur" → Native steering

### Python API
- "How to get CHOP value?" → Pattern: access_chop_value
- "Panel value changed callback" → Callback: onValueChange

---

## 6. IMPLEMENTATION PHASES

### Phase 1: Core Embeddings (Immediate)
- [ ] Embed 686 operator summaries
- [ ] Embed 174 concepts
- [ ] Embed 30 steering descriptions
- [ ] Basic similarity search

### Phase 2: Parameter Expansion
- [ ] Embed 11,144 parameters with operator context
- [ ] Add metadata filtering (by family, section)

### Phase 3: Code Knowledge
- [ ] Flatten and embed class methods
- [ ] Flatten and embed snippet descriptions
- [ ] Embed Python patterns and callbacks

### Phase 4: Advanced Features
- [ ] Hybrid search (semantic + keyword)
- [ ] Re-ranking for precision
- [ ] Query classification (what type of answer needed)

---

## 7. ESTIMATED TOTALS

| Category | Documents | Est. Tokens | Notes |
|----------|-----------|-------------|-------|
| Operators | 686 | ~50K | Summaries only |
| Parameters | 11,144 | ~300K | With context |
| Concepts | 174 | ~15K | |
| Steering | 30 | ~5K | |
| Patterns | 33 | ~3K | |
| **Phase 1 Total** | **12,067** | **~375K** | |
| Class Methods | ~500 | ~50K | After flatten |
| Snippets | ~300 | ~30K | After flatten |
| Python Examples | 18,062 | ~500K | Needs processing |
| **Full Total** | **~31,000** | **~1M** | |

---

## 8. NEXT STEPS

1. **Create embedding preparation script** - Transform all YAML to embedding-ready JSON
2. **Choose vector store** - ChromaDB for local dev, Pinecone for production
3. **Generate embeddings** - Process in batches
4. **Build query interface** - Simple retrieval API
5. **Test with real queries** - Validate retrieval quality

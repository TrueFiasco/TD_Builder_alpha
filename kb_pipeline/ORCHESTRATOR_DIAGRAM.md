# Multi-Model Orchestrator - Visual Architecture

## High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER REQUEST                            │
│  "Build audio-reactive particle system with beat detection"     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR LAYER                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  ROUTER (Haiku/GPT-4o-mini)                              │   │
│  │  - Classify task type & complexity                       │   │
│  │  - Extract entities (operators, requirements)            │   │
│  │  - Determine workflow pattern                            │   │
│  │  - Route to appropriate models                           │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   RETRIEVAL  │   │    DESIGN    │   │  CONCEPTUAL  │
│    AGENT     │   │    AGENT     │   │    AGENT     │
├──────────────┤   ├──────────────┤   ├──────────────┤
│ Haiku 3.5    │   │  Sonnet 4    │   │   Opus 4     │
│ GPT-4o-mini  │   │  GPT-4o      │   │   o1         │
├──────────────┤   ├──────────────┤   ├──────────────┤
│ Fast & Cheap │   │   Balanced   │   │ Deep Reason  │
│ $0.25/MTok   │   │  $3-15/MTok  │   │ $15-75/MTok  │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       │                  │                  │
       ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                        MCP SERVER                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  13 TOOLS FOR KNOWLEDGE BASE ACCESS                      │   │
│  │  - hybrid_search: Semantic search                        │   │
│  │  - get_operator_info: Operator details                   │   │
│  │  - query_graph: Relationship queries                     │   │
│  │  - find_operator_examples: Real examples                 │   │
│  │  - find_operator_combination: Multi-op patterns          │   │
│  │  - ... (8 more tools)                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE BASE                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│  │  Vector DB │  │   Graph    │  │   Cache    │                │
│  │  20.5K     │  │  16.8K     │  │  Query     │                │
│  │  chunks    │  │  nodes     │  │  Results   │                │
│  └────────────┘  └────────────┘  └────────────┘                │
│  C:\TD_Projects\kb_pipeline\                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Task Routing Decision Tree

```
USER REQUEST
    │
    ▼
Is it a simple lookup?
    │
    ├── YES → CHEAP MODEL (Haiku/GPT-4o-mini)
    │           │
    │           ├─→ MCP Tool: get_operator_info
    │           ├─→ MCP Tool: find_operator_examples
    │           └─→ Format & Return
    │
    └── NO → Classify Complexity
              │
              ▼
        What type of task?
              │
              ├── RETRIEVAL + FORMATTING
              │   └─→ CHEAP MODEL (Haiku)
              │       - Call MCP tools
              │       - Aggregate results
              │       - Format response
              │
              ├── DESIGN + PLANNING
              │   └─→ MID-TIER MODEL (Sonnet 4/GPT-4o)
              │       1. CHEAP MODEL retrieves data
              │       2. MID-TIER MODEL designs solution
              │       3. CHEAP MODEL formats output
              │
              └── CONCEPTUAL + CREATIVE
                  └─→ PREMIUM MODEL (Opus 4/o1)
                      1. CHEAP MODEL retrieves data
                      2. MID-TIER MODEL creates plan
                      3. PREMIUM MODEL adds insights
                      4. CHEAP MODEL formats output
```

---

## Example: Audio-Reactive Particle System

### Step-by-Step Execution

```
1. USER REQUEST
   "Build audio-reactive particle system with beat detection"

2. ROUTER (Haiku - $0.001)
   ├─ Classify: "project_planning" + "high_complexity"
   ├─ Extract: [Audio Device In, Beat CHOP, Particle GPU]
   └─ Route: Retrieval → Design → Conceptual

3. RETRIEVAL AGENT (Haiku - $0.005)
   ├─ Call: get_operator_info("Beat CHOP")
   ├─ Call: get_operator_info("Particle GPU TOP")
   ├─ Call: find_operator_combination("audio", "particles")
   └─ Return: JSON with operator specs & examples

4. DESIGN AGENT (Sonnet 4 - $0.15)
   ├─ Input: Retrieved operator data
   ├─ Create: Connection graph
   │   - Audio Device In → Beat CHOP
   │   - Beat CHOP → Particle GPU (emit trigger)
   │   - Particle GPU → Render TOP
   ├─ Identify: Missing operators (LFO CHOP for smoothing)
   └─ Return: Implementation plan with parameters

5. CONCEPTUAL AGENT (Opus 4 - $0.30)
   ├─ Input: Design plan
   ├─ Enhance:
   │   - Use FFT for particle color mapping
   │   - Add feedback loop for trails
   │   - Suggest motion blur settings
   └─ Return: Advanced techniques & optimizations

6. FORMATTER (Haiku - $0.001)
   ├─ Input: All previous outputs
   ├─ Compile: Coherent final response
   └─ Return: Formatted plan to user

TOTAL COST: ~$0.46
TIME: ~8 seconds
```

---

## Model Selection Matrix

| Task Type | Complexity | Tokens | Best Model | Cost/MTok | Use Case |
|-----------|------------|--------|------------|-----------|----------|
| **Lookup** | Low | 500 | Haiku 3.5 | $0.25 | Parameter values, quick facts |
| **Retrieval** | Low | 2K | Haiku 3.5 | $0.25 | Search, aggregate, format |
| **Simple Design** | Medium | 5K | Sonnet 3.5 | $3 | Basic operator chains |
| **Complex Design** | Medium | 8K | Sonnet 4 | $3 | Multi-system integration |
| **Architecture** | High | 10K | GPT-4o | $2.5 | System-level planning |
| **Optimization** | High | 12K | Sonnet 4 | $3 | Performance tuning |
| **Creative** | High | 15K | Opus 4 | $15 | Novel techniques |
| **Deep Reasoning** | Very High | 20K | o1 | $15 | Complex algorithms |

---

## Cost Optimization Strategies

### Strategy 1: Cascade Pattern
```
Start with CHEAP → Escalate if needed

User: "What's the Speed parameter in Animation COMP?"
  ↓
Haiku tries → Success ($0.001) → Done ✓

User: "Design complex particle system with 3D camera"
  ↓
Haiku tries → Realizes complexity → Routes to Sonnet 4
  ↓
Sonnet 4 completes → Success ($0.15) ✓
```

### Strategy 2: Parallel Retrieval
```
Run multiple cheap models in parallel for data gathering

User: "Compare Speed CHOP, Timer CHOP, and LFO CHOP"
  ↓
Haiku #1: get_operator_info("Speed CHOP")  ──┐
Haiku #2: get_operator_info("Timer CHOP")  ──┼→ Aggregate
Haiku #3: get_operator_info("LFO CHOP")   ──┘
  ↓
Haiku #4: Compare & format
  ↓
Total: ~$0.003 (vs $0.02 if using Sonnet for everything)
```

### Strategy 3: Hybrid Approach
```
Cheap for data, expensive for insight

User: "Optimize my network for better performance"
  ↓
Haiku: Retrieve operator usage patterns from KB
  ↓
Sonnet 4: Analyze and suggest optimizations
  ↓
Haiku: Format recommendations
  ↓
Total: $0.15 (vs $0.45 if Sonnet did everything)
```

---

## Integration Points

### With MCP Server
```python
# Orchestrator calls MCP server
mcp_client.call_tool("hybrid_search", {"query": "audio visualization"})
mcp_client.call_tool("get_operator_info", {"operator_name": "Beat CHOP"})
mcp_client.call_tool("find_operator_examples", {"operator": "Particle GPU"})

# Returns structured data (not AI-generated text)
# Orchestrator routes data to appropriate model for processing
```

### With Claude/OpenAI APIs
```python
# Router decides which model
if task.complexity == "low":
    model = "claude-3-5-haiku-20241022"
elif task.type == "design":
    model = "claude-sonnet-4-20250514"
elif task.type == "conceptual":
    model = "claude-opus-4-20250514"

# Make API call
response = anthropic.messages.create(
    model=model,
    messages=[{"role": "user", "content": prompt}],
    tools=[...mcp_tools...]
)
```

---

## Next Steps

1. Copy `ORCHESTRATOR_PLANNING_PROMPT.md` into ChatGPT
2. Review the architecture plan ChatGPT provides
3. Implement router/classifier first (simplest component)
4. Build model adapter layer (API abstraction)
5. Integrate with existing MCP server
6. Test with real TD project planning scenarios
7. Iterate based on cost/quality metrics

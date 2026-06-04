# Multi-Model Orchestrator - Planning Prompt

**Copy this entire prompt into a new ChatGPT chat to plan the orchestrator architecture**

---

## Context: TouchDesigner MCP Tool - Current State

I have a working TouchDesigner knowledge base system with:
- **20,477 semantic chunks** (operator docs, examples, palette components)
- **Vector search** using local embeddings (all-MiniLM-L6-v2)
- **Knowledge graph** with 16,814 nodes, 18,084 edges
- **Hybrid retrieval** combining vector search + graph traversal
- **Query caching** (92.7% speedup on hits)
- **MCP Server** exposing 13 tools for search and retrieval

**Current Performance:**
- Query time: 3.5ms (cached), 48ms (uncached)
- Storage: 95.7 MB
- Location: `C:\TD_Projects\kb_pipeline\`

**Current MCP Tools:**
1. `hybrid_search` - Semantic search across all data
2. `get_operator_info` - Get detailed operator info
3. `query_graph` - Graph-based relationship queries
4. `find_operator_examples` - Find real-world examples
5. `find_operator_combination` - Multi-operator patterns
6. ... (13 tools total)

---

## Goal: Multi-Model Orchestrator

I want to build an orchestrator that intelligently routes tasks to different AI models based on:
- **Task complexity** (retrieval vs. design vs. conceptual)
- **Cost optimization** (cheap models for simple tasks, expensive for complex)
- **Model strengths** (Claude for code/reasoning, GPT for creative, Haiku for speed)

### Key Requirements

1. **Integration with Multiple Providers:**
   - Claude API (Haiku, Sonnet 3.5/4, Opus 4)
   - OpenAI API (GPT-4o, GPT-4o-mini, o1)
   - I pay for both, want to use them optimally

2. **Intelligent Task Routing:**
   - **Retrieval & Simple Queries** → Cheap models (Haiku 3.5, GPT-4o-mini)
   - **Design & Architecture** → Mid-tier (Sonnet 3.5, GPT-4o)
   - **Conceptual & Complex Reasoning** → Premium (Opus 4, o1)

3. **TouchDesigner Use Case:**
   When planning a big TouchDesigner project, I want to:
   - Describe what I'm building
   - Tell the orchestrator which operators/components I have
   - Get an intelligent plan for how to connect them
   - Have it route sub-tasks to appropriate models

4. **MCP Server Integration:**
   - Orchestrator should be able to call the 13 MCP tools
   - Tools return data (operator info, examples, graph relationships)
   - Orchestrator decides which model processes the data

---

## Available Models & Suggested Roles

### Claude Models (Anthropic API)
- **Haiku 3.5** ($0.25/$1.25 per MTok)
  - **Best for:** Fast retrieval, simple queries, formatting, data extraction
  - **Speed:** Very fast
  - **Suggested tasks:** MCP tool calls, search result formatting, parameter lookup

- **Sonnet 3.5** ($3/$15 per MTok)
  - **Best for:** Code generation, technical writing, multi-step reasoning
  - **Speed:** Fast
  - **Suggested tasks:** TouchDesigner network design, operator selection, connection logic

- **Sonnet 4** ($3/$15 per MTok)
  - **Best for:** Complex code, deep reasoning, architectural decisions
  - **Speed:** Medium
  - **Suggested tasks:** System architecture, optimization strategies, debugging

- **Opus 4** ($15/$75 per MTok)
  - **Best for:** Highest reasoning, creative problem-solving, complex planning
  - **Speed:** Slower
  - **Suggested tasks:** Novel TD techniques, creative effects, complex multi-operator workflows

### OpenAI Models
- **GPT-4o-mini** ($0.15/$0.60 per MTok)
  - **Best for:** Quick tasks, simple responses, formatting
  - **Speed:** Very fast
  - **Suggested tasks:** Similar to Haiku - retrieval assistance, simple queries

- **GPT-4o** ($2.50/$10 per MTok)
  - **Best for:** General-purpose, good at creative descriptions, UI/UX
  - **Speed:** Fast
  - **Suggested tasks:** Project descriptions, user-facing explanations, tutorials

- **o1** ($15/$60 per MTok)
  - **Best for:** Deep reasoning, complex problem-solving, math/logic
  - **Speed:** Slower (internal reasoning steps)
  - **Suggested tasks:** Algorithm optimization, performance analysis, complex debugging

---

## Example Workflow I Want

### User Request:
> "I want to build an audio-reactive particle system that responds to beat detection and controls a 3D camera path. I have: Audio Device In CHOP, Beat CHOP, Particle GPU TOP, Camera COMP, and Render TOP."

### Desired Orchestrator Behavior:

1. **Intent Classification** (Haiku or GPT-4o-mini - cheap & fast)
   - Classify: "Project planning + operator connection design"
   - Extract operators mentioned: [Audio Device In CHOP, Beat CHOP, Particle GPU TOP, Camera COMP, Render TOP]
   - Determine complexity: HIGH (multi-system integration)

2. **Knowledge Retrieval** (Haiku via MCP tools)
   - Call `get_operator_info` for each operator
   - Call `find_operator_combination` for common patterns
   - Call `find_operator_examples` for particle + audio patterns
   - **Return structured data** (not full response)

3. **Design & Planning** (Sonnet 4 or GPT-4o - mid-tier for architecture)
   - Process retrieval results
   - Design connection graph:
     - Audio Device In → Beat CHOP (beat detection)
     - Beat CHOP → Particle GPU (emit on beat)
     - Particle GPU → Render TOP (visualization)
     - Beat CHOP → Camera COMP (path animation)
     - Camera COMP → Render TOP (viewpoint)
   - Identify missing operators (e.g., need LFO CHOP for smooth camera motion)
   - Create step-by-step implementation plan

4. **Conceptual Enhancement** (Opus 4 or o1 - premium for creative insight)
   - Suggest advanced techniques:
     - Use spectral data for particle color
     - Implement motion blur for smoother visuals
     - Add feedback loop for trail effects
   - Optimize for performance
   - Propose alternative approaches

5. **Response Compilation** (Haiku - cheap for formatting)
   - Format final response for user
   - Add operator parameter suggestions
   - Include links to examples from knowledge base

---

## Technical Requirements

### Orchestrator Architecture Needs:

1. **Router/Classifier Component**
   - Analyzes incoming user request
   - Classifies task type and complexity
   - Routes to appropriate model(s)

2. **Model Adapter Layer**
   - Unified interface for Claude API and OpenAI API
   - Handles API calls, retries, rate limiting
   - Cost tracking per model

3. **MCP Tool Integration**
   - Orchestrator can call any of the 13 MCP tools
   - Tools return structured data (JSON)
   - Results fed to appropriate model for processing

4. **Multi-Agent Workflow Engine**
   - Sequential: Step 1 → Step 2 → Step 3
   - Parallel: Run multiple cheap models simultaneously
   - Hierarchical: Cheap model summarizes → Expensive model decides

5. **Cost Optimization Logic**
   - Track token usage per model
   - Estimate costs before expensive model calls
   - Allow user to set budget constraints

6. **Response Synthesis**
   - Combine outputs from multiple models
   - Ensure coherent final response
   - Attribute insights to specific models (optional)

---

## Questions to Address in the Plan

Please help me design an orchestrator system that addresses:

1. **Architecture:**
   - What's the best high-level architecture? (Microservices? Monolith? State machine?)
   - How should models communicate? (API calls? Message queue? Direct?)
   - Where does the MCP server fit? (Data layer? Tool layer?)

2. **Routing Logic:**
   - How to classify task complexity automatically?
   - Should I use a small model to route, or rule-based system?
   - Can I train/fine-tune a classifier for TD-specific tasks?

3. **Workflow Patterns:**
   - What workflow patterns are most useful? (Sequential, parallel, hierarchical)
   - How to handle failures? (Retry? Fallback to cheaper model? Escalate to expensive?)
   - When to use multiple models vs. single model?

4. **Implementation:**
   - Should I build this as an extension to the MCP server?
   - Separate orchestration layer?
   - Use existing frameworks? (LangChain, LangGraph, Haystack, AutoGen?)

5. **Prompt Engineering:**
   - How to structure prompts for each model tier?
   - Should I use different system prompts per task type?
   - How to pass context between model calls efficiently?

6. **Cost Management:**
   - How to estimate costs before making expensive calls?
   - Should I implement a "budget mode" that limits expensive models?
   - How to track and report costs per user session?

7. **Schema/Workflow for TD Projects:**
   - What's the ideal schema for representing a TD project plan?
   - How to represent operator connections as a graph?
   - How to serialize this for passing between models?

---

## Example Schemas to Consider

### Task Classification Schema
```json
{
  "task_type": "project_planning",
  "complexity": "high",
  "subtasks": [
    {"type": "retrieval", "description": "Get operator info"},
    {"type": "design", "description": "Create connection graph"},
    {"type": "conceptual", "description": "Suggest optimizations"}
  ],
  "estimated_cost": {
    "cheap_tokens": 2000,
    "mid_tokens": 8000,
    "expensive_tokens": 3000
  },
  "recommended_models": {
    "retrieval": "haiku-3.5",
    "design": "sonnet-4",
    "conceptual": "opus-4"
  }
}
```

### TD Project Plan Schema
```json
{
  "project": {
    "description": "Audio-reactive particle system",
    "operators_available": [...],
    "operators_needed": [...],
    "connections": [
      {
        "from": {"op": "Audio Device In CHOP", "output": "chan1"},
        "to": {"op": "Beat CHOP", "input": "audioin"}
      }
    ],
    "parameters": [
      {
        "operator": "Beat CHOP",
        "parameter": "threshold",
        "suggested_value": 0.5,
        "reasoning": "..."
      }
    ],
    "implementation_steps": [...]
  }
}
```

---

## Constraints & Preferences

- **Budget:** I pay for both Claude and OpenAI, but want to minimize costs
- **Speed:** Prefer fast responses for simple queries
- **Quality:** Willing to wait for complex reasoning on hard problems
- **Integration:** Must work with existing MCP server and kb_pipeline
- **Scalability:** Should handle multiple concurrent users (future)
- **Observability:** Want to see which models were used and why

---

## Your Task

Please provide a comprehensive plan for building this multi-model orchestrator:

1. **Architecture Diagram** (text/ASCII art is fine)
2. **Routing Decision Tree** (when to use which model)
3. **Workflow Patterns** (with examples for TD use cases)
4. **Implementation Recommendations** (frameworks, structure, file organization)
5. **Prompt Templates** (for each model tier)
6. **Cost Optimization Strategies**
7. **Integration Plan** (how it fits with existing MCP server)
8. **Schema Definitions** (for tasks, projects, responses)
9. **Error Handling & Fallbacks**
10. **Testing Strategy** (how to validate routing decisions)

Focus on practical, implementable solutions. I'm a skilled developer and can handle complex implementations, but I want your strategic guidance on architecture and design patterns.

**Bonus:** If you can suggest specific tools, libraries, or frameworks that would accelerate development, please include them with pros/cons.

---

## Additional Context

- **Current Tech Stack:** Python 3.14, MCP server, Claude Code CLI
- **Existing Files:** See `C:\TD_Projects\kb_pipeline\` for knowledge base
- **MCP Server:** `C:\TD_Projects\mcp_server\server_with_agents.py`
- **Documentation:** `HANDOFF.md`, `PHASE5_COMPLETE.md` in kb_pipeline

**End of Prompt** - Copy everything above this line into ChatGPT

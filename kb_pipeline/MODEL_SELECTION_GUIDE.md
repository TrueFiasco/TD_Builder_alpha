# Model Selection Quick Reference

## When to Use Each Model

### 🏃 Haiku 3.5 (Claude) - Speed & Cost Leader
**Cost:** $0.25/$1.25 per MTok | **Speed:** ⚡⚡⚡ Very Fast

**Use for:**
- ✓ MCP tool calls and data aggregation
- ✓ Simple parameter lookups
- ✓ Formatting and presentation
- ✓ Intent classification/routing
- ✓ Quick yes/no questions
- ✓ List generation from structured data

**Don't use for:**
- ✗ Complex reasoning
- ✗ Novel problem-solving
- ✗ Long-form creative content

**Example prompts:**
- "Get info about Speed CHOP"
- "Format these search results as a table"
- "Extract operator names from this text"
- "Is this a simple or complex task?"

---

### 🏃 GPT-4o-mini (OpenAI) - Alternative Speed Model
**Cost:** $0.15/$0.60 per MTok | **Speed:** ⚡⚡⚡ Very Fast

**Use for:**
- ✓ Same as Haiku (slightly cheaper)
- ✓ Better at creative descriptions
- ✓ Good for user-facing explanations

**Choose over Haiku when:**
- Need more conversational tone
- Want slightly better creative writing
- Cost is absolutely critical

---

### ⚙️ Sonnet 3.5 (Claude) - Workhorse Model
**Cost:** $3/$15 per MTok | **Speed:** ⚡⚡ Fast

**Use for:**
- ✓ Code generation
- ✓ Technical documentation
- ✓ Multi-step reasoning
- ✓ Basic TD network design
- ✓ Operator selection logic

**Example prompts:**
- "Write Python code to connect these operators"
- "Explain how to use Beat CHOP for audio reactivity"
- "Design a simple audio visualization network"

---

### ⚙️ Sonnet 4 (Claude) - Advanced Reasoning
**Cost:** $3/$15 per MTok | **Speed:** ⚡⚡ Fast

**Use for:**
- ✓ Complex TD network design
- ✓ Multi-system integration
- ✓ Architectural decisions
- ✓ Performance optimization
- ✓ Debugging complex issues

**Example prompts:**
- "Design a particle system that responds to audio and controls a 3D camera"
- "How should I optimize this network for 60fps?"
- "What's the best way to connect these 8 operators?"

---

### ⚙️ GPT-4o (OpenAI) - General Purpose Premium
**Cost:** $2.50/$10 per MTok | **Speed:** ⚡⚡ Fast

**Use for:**
- ✓ Creative project descriptions
- ✓ Tutorial generation
- ✓ User-facing documentation
- ✓ Alternative to Sonnet for design

**Choose over Sonnet when:**
- Need more creative/accessible language
- Want better vision capabilities
- Prefer OpenAI ecosystem

---

### 🧠 Opus 4 (Claude) - Deep Thinking
**Cost:** $15/$75 per MTok | **Speed:** ⚡ Medium

**Use for:**
- ✓ Novel TD techniques
- ✓ Creative effects design
- ✓ Complex multi-operator workflows
- ✓ Advanced optimization strategies
- ✓ When Sonnet fails or gives shallow answers

**Example prompts:**
- "Design a unique generative art system using TD"
- "How can I create this effect I've never seen before?"
- "What's the most efficient way to handle 10,000 particles?"

**Warning:** Only use when mid-tier models aren't sufficient

---

### 🧠 o1 (OpenAI) - Reasoning Specialist
**Cost:** $15/$60 per MTok | **Speed:** ⚡ Slow (internal reasoning)

**Use for:**
- ✓ Algorithm design
- ✓ Complex mathematical operations
- ✓ Performance optimization with proof
- ✓ Novel problem-solving with reasoning traces

**Example prompts:**
- "Design an algorithm to synchronize 5 different timelines"
- "Prove this approach is more efficient than alternatives"
- "What's the optimal data structure for this use case?"

**Note:** o1 shows its reasoning steps - good for learning

---

## Decision Flowchart

```
START: What does the user want?
    │
    ├─→ Simple lookup/fact?
    │   └─→ HAIKU ($)
    │
    ├─→ Need to call MCP tools?
    │   └─→ HAIKU ($) + Tools
    │
    ├─→ Design a TD network?
    │   ├─→ Simple (2-4 operators)
    │   │   └─→ SONNET 3.5 ($$)
    │   │
    │   └─→ Complex (5+ operators, multiple systems)
    │       └─→ SONNET 4 ($$$)
    │
    ├─→ Creative/novel technique?
    │   └─→ OPUS 4 ($$$$)
    │
    ├─→ Mathematical/algorithmic?
    │   └─→ o1 ($$$)
    │
    └─→ Format/present results?
        └─→ HAIKU ($)
```

---

## Cost Examples

### Scenario 1: Simple Parameter Lookup
**User:** "What's the Speed parameter in Speed CHOP?"

**Best approach:**
1. Haiku → MCP tool `get_operator_info("Speed CHOP")`
2. Haiku → Format response

**Cost:** ~$0.001 (1K tokens)

---

### Scenario 2: Medium Complexity Design
**User:** "Design audio visualization with Beat CHOP and Particle GPU"

**Best approach:**
1. Haiku → MCP tools (get operator info, find examples)
2. Sonnet 4 → Design connection graph
3. Haiku → Format response

**Cost:** ~$0.08 (25K tokens, mostly Sonnet)

---

### Scenario 3: Complex Creative Project
**User:** "Create unique generative art system with audio reactivity, 3D camera animation, and feedback loops"

**Best approach:**
1. Haiku → MCP tools (retrieve operator data)
2. Sonnet 4 → Initial architecture design
3. Opus 4 → Creative enhancements & novel techniques
4. Haiku → Format final response

**Cost:** ~$0.50 (30K tokens, Opus for creative part)

---

### Scenario 4: Batch Retrieval
**User:** "Compare 10 different CHOP operators"

**Parallel approach:**
1. Haiku (10 parallel calls) → get_operator_info for each
2. Haiku → Aggregate and compare
3. Haiku → Format as table

**Cost:** ~$0.005 (2K tokens total)
**Time:** <2 seconds (parallel)

**❌ Bad approach:**
- Sonnet 4 does everything serially
- Cost: ~$0.15 (30x more expensive!)
- Time: ~10 seconds

---

## Token Estimation Guide

| Task | Typical Tokens | Model | Cost |
|------|---------------|-------|------|
| Parameter lookup | 500 | Haiku | $0.0001 |
| Operator info retrieval | 1,000 | Haiku | $0.0003 |
| Simple design | 3,000 | Sonnet 3.5 | $0.009 |
| Medium design | 8,000 | Sonnet 4 | $0.024 |
| Complex design | 15,000 | Sonnet 4 | $0.045 |
| Creative enhancement | 10,000 | Opus 4 | $0.15 |
| Deep reasoning | 20,000 | o1 | $0.30 |

**Formula:**
```
Cost = (Input_Tokens × Input_Price) + (Output_Tokens × Output_Price)
```

**Rough estimate:**
- Input tokens ≈ 40% of total
- Output tokens ≈ 60% of total

---

## Optimization Strategies

### ✅ DO:
- Use Haiku for ALL data retrieval
- Parallel execution for independent tasks
- Cache common queries
- Start cheap, escalate if needed
- Format responses with Haiku

### ❌ DON'T:
- Use Opus for simple lookups
- Use expensive models for formatting
- Call tools sequentially when parallel is possible
- Let expensive models do data retrieval
- Use o1 unless you need the reasoning traces

---

## Monthly Cost Estimates

### Light Usage (50 queries/day)
- 80% simple (Haiku): ~$0.50/month
- 15% medium (Sonnet): ~$10/month
- 5% complex (Opus): ~$5/month
**Total: ~$15/month**

### Medium Usage (200 queries/day)
- 70% simple (Haiku): ~$1.50/month
- 20% medium (Sonnet): ~$30/month
- 10% complex (Opus): ~$20/month
**Total: ~$50/month**

### Heavy Usage (1000 queries/day)
- 60% simple (Haiku): ~$5/month
- 30% medium (Sonnet): ~$150/month
- 10% complex (Opus): ~$100/month
**Total: ~$255/month**

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────┐
│ TASK                           → MODEL                  │
├─────────────────────────────────────────────────────────┤
│ Lookup/Facts                   → Haiku ($)             │
│ MCP Tool Calls                 → Haiku ($)             │
│ Format/Present                 → Haiku ($)             │
│ Simple Code                    → Sonnet 3.5 ($$)       │
│ Basic Design                   → Sonnet 3.5 ($$)       │
│ Complex Design                 → Sonnet 4 ($$$)        │
│ Architecture                   → Sonnet 4 ($$$)        │
│ Creative/Novel                 → Opus 4 ($$$$)         │
│ Math/Algorithm                 → o1 ($$$)              │
│ Tutorials/Docs                 → GPT-4o ($$)           │
└─────────────────────────────────────────────────────────┘

$ = <$0.01 per request
$$ = $0.01-0.05 per request
$$$ = $0.05-0.15 per request
$$$$ = $0.15+ per request
```

---

**Pro Tip:** Start every workflow with Haiku for routing. It costs almost nothing and ensures you only use expensive models when truly needed.

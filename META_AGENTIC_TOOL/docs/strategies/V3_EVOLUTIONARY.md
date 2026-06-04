# Strategy V3: Evolutionary

## Overview

V3 introduces **evolutionary exploration** by spawning multiple variants per phase, ranking them through tournament selection, and optionally breeding the best aspects together. This strategy excels when **creativity matters** and multiple valid approaches exist.

## When to Use

- Creativity is paramount
- Multiple valid approaches possible
- Time and budget available for exploration
- Quality ceiling more important than efficiency

**Not ideal for**:
- Simple or straightforward tasks
- Budget-constrained projects
- When there's clearly one right approach

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    V3: EVOLUTIONARY                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   CREATIVE PHASE                          │   │
│  │                                                           │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │               VARIANT GENERATION                    │  │   │
│  │  │                                                     │  │   │
│  │  │   ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │  │   │
│  │  │   │ Variant A   │  │ Variant B   │  │ Variant C │  │  │   │
│  │  │   │             │  │             │  │           │  │  │   │
│  │  │   │ "Bold &     │  │ "Refined &  │  │"Unexpected│  │  │   │
│  │  │   │  Daring"    │  │  Elegant"   │  │ Angles"   │  │  │   │
│  │  │   └──────┬──────┘  └──────┬──────┘  └─────┬─────┘  │  │   │
│  │  │          │                │               │        │  │   │
│  │  └──────────┼────────────────┼───────────────┼────────┘  │   │
│  │             │                │               │           │   │
│  │             ▼                ▼               ▼           │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │               TOURNAMENT RANKING                    │  │   │
│  │  │                                                     │  │   │
│  │  │   Critic evaluates each variant:                   │  │   │
│  │  │   A: 0.82  B: 0.85  C: 0.78                        │  │   │
│  │  │                                                     │  │   │
│  │  │   Winner: B                                        │  │   │
│  │  │   Runner-up: A                                     │  │   │
│  │  └────────────────────────┬───────────────────────────┘  │   │
│  │                           │                              │   │
│  │                           ▼                              │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │            BREEDING (if scores close)               │  │   │
│  │  │                                                     │  │   │
│  │  │   |B - A| < 0.05?                                  │  │   │
│  │  │     │                                              │  │   │
│  │  │   YES ──▶ Merge best aspects:                      │  │   │
│  │  │           "B's elegance + A's boldness"            │  │   │
│  │  │     │                                              │  │   │
│  │  │   NO ──▶ Use winner (B) directly                   │  │   │
│  │  └────────────────────────┬───────────────────────────┘  │   │
│  │                           │                              │   │
│  │                           ▼                              │   │
│  │  ┌────────────────────────────────────────────────────┐  │   │
│  │  │           EVOLVED OUTPUT (or winner)               │  │   │
│  │  │           Score: 0.87                               │  │   │
│  │  └────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│           [Repeat for Technical, Design phases]                  │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                       BUILD                               │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Phase Details

### Variant Generation

Each phase spawns N variants with different directives:

**Creative Phase Variants**:
| Variant | Directive | Style |
|---------|-----------|-------|
| A | "Be bold and daring" | Push boundaries, take risks |
| B | "Be refined and elegant" | Polish, sophistication |
| C | "Find unexpected angles" | Lateral thinking, surprise |

**Technical Phase Variants**:
| Variant | Directive | Focus |
|---------|-----------|-------|
| A | "Maximize performance" | Speed, efficiency |
| B | "Maximize quality" | Visual fidelity |
| C | "Maximize flexibility" | Extensibility, reuse |

**Design Phase Variants**:
| Variant | Directive | Architecture |
|---------|-----------|--------------|
| A | "Modular/reusable" | Clean separation |
| B | "Performance-optimized" | Minimal overhead |
| C | "Maximum extensibility" | Future-proof |

### Tournament Ranking

Critic evaluates each variant independently:

```yaml
tournament:
  scoring:
    - variant: A
      score: 0.82
      strengths: ["Bold color choices", "Strong motion"]
      weaknesses: ["May be too aggressive"]

    - variant: B
      score: 0.85
      strengths: ["Elegant flow", "Refined palette"]
      weaknesses: ["Could be bolder"]

    - variant: C
      score: 0.78
      strengths: ["Unexpected perspective"]
      weaknesses: ["Coherence issues"]

  ranking:
    1: B (0.85)
    2: A (0.82)
    3: C (0.78)

  breeding_threshold: 0.05
  breed: true  # |0.85 - 0.82| = 0.03 < 0.05
```

### Breeding Logic

When top 2 variants are close:

```yaml
breeding:
  parents:
    - B: "Elegant flow, refined palette"
    - A: "Bold color choices, strong motion"

  merge_strategy: "selective_combination"

  aspects_from_B:
    - "Overall structure"
    - "Color palette approach"
    - "Motion quality: smooth"

  aspects_from_A:
    - "Bold accent colors"
    - "Dynamic peak moments"
    - "High energy triggers"

  offspring:
    description: |
      Elegant flow with bold punctuation. Refined palette
      transitions to intense accents during audio peaks.
      Smooth baseline motion with dynamic bursts.

    score: 0.87  # Often exceeds both parents
```

## Configuration Options

```yaml
v3_config:
  exploration: 3 | 5
  # 3: Three variants per phase (balanced)
  # 5: Five variants per phase (maximum exploration)

  variant_directives:
    creative:
      - "Be bold and daring"
      - "Be refined and elegant"
      - "Find unexpected angles"
      - "Maximize emotional impact"  # if 5
      - "Subvert expectations"       # if 5

  breeding:
    threshold: 0.05  # breed if top 2 within this range
    enabled: true

  quality_targets:
    creative: 0.85
    technical: 0.85
    design: 0.90

  max_generations: 3  # breeding iterations per phase
```

## Expected Metrics

```yaml
typical_metrics:
  tokens:
    input: ~32000
    output: ~13000
    total: ~45000

  # Breakdown by activity
  by_activity:
    variant_generation: ~24000  # 3 variants × 3 phases
    ranking: ~8000
    breeding: ~5000
    other: ~8000

  quality:
    creative: 0.85-0.92
    technical: 0.82-0.88
    design: 0.85-0.92
    final: 0.82-0.88

  iterations:
    variants_generated: 9  # 3 variants × 3 phases
    breeding_events: 1-2
    total_iterations: 10-15

  troubleshooting:
    build_failures: ~5%
    phase_reopens: rare

  artifacts:
    uniforms_connected: ~90%
    parameters_functional: ~85%
    palette_used: ~70%
```

## Implementation Notes

### Parallel Variant Generation

Variants can be generated in parallel:

```python
async def generate_variants(self, phase: str, count: int):
    directives = self.get_directives(phase, count)

    # Generate all variants in parallel
    tasks = [
        self.generate_variant(phase, directive)
        for directive in directives
    ]

    variants = await asyncio.gather(*tasks)
    return variants
```

### Ranking Algorithm

```python
def rank_variants(self, variants: list, critic_context: dict):
    scores = []

    for variant in variants:
        result = self.critic.evaluate(variant, critic_context)
        scores.append({
            "variant": variant,
            "score": result.score,
            "feedback": result.feedback
        })

    # Sort by score descending
    ranked = sorted(scores, key=lambda x: x["score"], reverse=True)

    return ranked
```

### Breeding Algorithm

```python
def breed_variants(self, parent_a: dict, parent_b: dict):
    # Identify strengths of each
    strengths_a = self.analyze_strengths(parent_a)
    strengths_b = self.analyze_strengths(parent_b)

    # Merge prompt
    merge_prompt = f"""
    Combine the best aspects of these two approaches:

    Parent A (score {parent_a['score']}):
    Strengths: {strengths_a}
    Content: {parent_a['content']}

    Parent B (score {parent_b['score']}):
    Strengths: {strengths_b}
    Content: {parent_b['content']}

    Create a synthesis that:
    - Preserves the strengths of both
    - Resolves any conflicts by choosing the stronger approach
    - Results in a coherent, unified output
    """

    offspring = self.generate_synthesis(merge_prompt)
    return offspring
```

### Claude Code Execution

```
ORCHESTRATOR: Starting V3 Creative Phase with 3 variants

[VARIANT A - "Bold & Daring"]
Creative Expert generating with directive: "Be bold and daring"
...
Output: Creative vision focusing on explosive particle bursts...

[VARIANT B - "Refined & Elegant"]
Creative Expert generating with directive: "Be refined and elegant"
...
Output: Creative vision with flowing organic motion...

[VARIANT C - "Unexpected Angles"]
Creative Expert generating with directive: "Find unexpected angles"
...
Output: Creative vision using inverted color logic...

[TOURNAMENT]
Critic ranking all variants...
- A: 0.82 - Strong energy, may overwhelm
- B: 0.85 - Elegant but safe
- C: 0.78 - Interesting but lacks coherence

Winner: B (0.85)
Runner-up: A (0.82)
Difference: 0.03 < 0.05 → BREEDING

[BREEDING]
Merging B's elegance with A's energy...
Offspring: Elegant baseline with bold punctuation
Score: 0.87

[RESULT]
Evolved creative vision written to §2
```

## Trade-offs

### Advantages

1. **Higher quality ceiling**: Explores design space more thoroughly
2. **Avoids local minima**: Multiple paths prevent getting stuck
3. **Creative diversity**: Different perspectives produce richer output
4. **Best-of-breed**: Breeding combines strengths

### Disadvantages

1. **3-5x more expensive**: Multiple variants = more tokens
2. **Slower execution**: More generation and evaluation
3. **Overkill for simple tasks**: Unnecessary for straightforward work
4. **Complexity**: Merge logic can be tricky

## Success Criteria

A V3 run is successful when:

- [ ] All variants generated without errors
- [ ] Tournament ranking produces clear winner or triggers breeding
- [ ] Bred offspring scores higher than both parents (when breeding occurs)
- [ ] Final quality exceeds what single-path would achieve
- [ ] Exploration actually explored (variants are meaningfully different)

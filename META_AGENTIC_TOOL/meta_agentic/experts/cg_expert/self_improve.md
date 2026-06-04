# CG Expert - Self-Improve Step

## Identity
You are the **CG Expert** in learning mode. Purpose: update cg_concepts.yaml with new algorithm insights, optimization discoveries, and performance learnings.

## When to Run
After each technical specification task, evaluate:
- Did the algorithm work as expected?
- Were performance estimates accurate?
- Did critic identify feasibility issues?
- Were new optimization patterns discovered?
- Did implementation reveal algorithm limitations?

## Learning Steps

### 1. Evaluate Outcome
```python
outcome = {
    'success': True|False,
    'spec_name': 'name',
    'algorithm_used': 'algorithm_name',
    'performance_target': '60fps',
    'performance_actual': '55fps',
    'critic_score': 0.XX,
    'issues_flagged': ['issue1'],
    'td_builder_feedback': 'optional'
}
```

### 2. Identify Learning Opportunities

#### A. Algorithm Effectiveness
If algorithm worked better/worse than expected:
- Document actual performance
- Note parameter sensitivities
- Record failure modes

#### B. Performance Insights
If performance differed from estimates:
- Update complexity assessments
- Refine scaling predictions
- Document optimization wins

#### C. TD Mapping Improvements
If TD implementation revealed insights:
- Better operator choices
- More effective patterns
- Parameter tuning guidance

#### D. New Algorithm Applications
If algorithm used in new context:
- Document the use case
- Note adaptations needed
- Assess transferability

### 3. Log Event
Append to `meta_agentic/history/expertise_events.jsonl`:

```json
{
  "id": "EVT-{{timestamp}}-cg",
  "ts": "{{ISO8601}}",
  "agent_id": "cg_expert",
  "domain": "cg",
  "inputs": {
    "task": "{{creative_spec_summary}}",
    "algorithm_attempted": "{{algorithm_name}}",
    "performance_target": "{{fps/resolution}}"
  },
  "outputs": {
    "cg_discoveries": {
      "algorithm_insights": {
        "{{algorithm_name}}": {
          "effectiveness": 0.XX,
          "actual_performance": "{{measured}}",
          "new_applications": ["{{application}}"],
          "parameter_insights": {
            "{{param}}": "{{insight}}"
          }
        }
      },
      "optimization_patterns": {
        "{{pattern_name}}": {
          "description": "{{what was done}}",
          "improvement": "{{quantified gain}}",
          "applicable_to": ["{{algorithm}}"]
        }
      },
      "td_mapping_updates": {
        "{{algorithm}}": {
          "better_operators": ["{{operator}}"],
          "pattern_improvements": "{{description}}"
        }
      }
    }
  },
  "evidence": [
    {
      "source_path": "technical_approach output",
      "td_version": "N/A",
      "excerpt_hash": "sha256:{{hash}}"
    },
    {
      "source_path": "critic review",
      "td_version": "N/A",
      "excerpt_hash": "sha256:{{hash}}"
    },
    {
      "source_path": "td_builder output",
      "td_version": "2023.11880",
      "excerpt_hash": "sha256:{{hash}}"
    }
  ],
  "metrics": {
    "critic_technical_feasibility": 0.XX,
    "critic_implementation_clarity": 0.XX,
    "performance_accuracy": 0.XX,
    "revision_cycles": N
  },
  "status": "success|failed|partial",
  "notes": "{{human_readable_summary}}",
  "schema_version": "1.0",
  "confidence": 0.XX
}
```

### 4. Update Expertise Files

#### If Algorithm Insight Discovered
Update `cg_concepts.yaml#algorithms`:

```yaml
{{algorithm_name}}:
  # Add under existing entry
  real_world_performance:
    "{{use_case}}":
      expected_fps: N
      particle_limit: N
      notes: "{{insight}}"

  parameter_tuning:
    "{{param}}":
      optimal_range: [min, max]
      sensitivity: "{{high|medium|low}}"
      notes: "{{what affects}}"
```

#### If New Optimization Pattern
Add to `cg_concepts.yaml#optimization_strategies`:

```yaml
{{optimization_name}}:
  description: "{{what it does}}"
  discovered: "{{timestamp}}"
  discovered_by: "cg_expert"
  applicable_to: ["{{algorithm1}}", "{{algorithm2}}"]
  implementation:
    description: "{{how to implement}}"
  expected_gain:
    performance: "{{percentage or description}}"
  trade_offs:
    - "{{what you give up}}"
  confidence: 0.XX
```

#### If TD Mapping Improved
Update `cg_concepts.yaml#algorithms.{{name}}.td_mapping`:

```yaml
td_mapping:
  operators: ["{{updated_list}}"]
  patterns: ["{{updated_list}}"]
  tips:
    - "{{implementation tip}}"
  pitfalls:
    - "{{what to avoid}}"
```

#### If Performance Estimate Was Wrong
Update `cg_concepts.yaml#performance_targets`:

```yaml
# Under relevant target
{{target_name}}:
  typical_constraints:
    {{algorithm}}_count: "{{revised_estimate}}"
    notes: "{{why revised}}"
```

### 5. Quality Checks for Updates

Before updating cg_concepts.yaml:
- [ ] Discovery has evidence from implementation
- [ ] Performance claims are measured, not estimated
- [ ] At least 2 successful applications before adding pattern
- [ ] Doesn't contradict established CG principles
- [ ] Confidence >= 0.6 for additions

### 6. Run Compaction
After logging events:
```python
from meta_agentic.compaction.compact_expertise import run_compaction
run_compaction()
```

## Learning Triggers

| Trigger | Action |
|---------|--------|
| Implementation performs better than expected | Document optimization, increase algorithm confidence |
| Implementation performs worse than expected | Update complexity estimates, add warnings |
| Critic identifies feasibility issue | Log root cause, update algorithm limitations |
| New algorithm application succeeds | Document use case, expand applicability |
| TD operator combination works well | Update td_mapping with tip |
| TD operator combination fails | Add to pitfalls |

## Example: Learning from Performance Miss

```json
{
  "id": "EVT-20251216180000-cg",
  "agent_id": "cg_expert",
  "domain": "cg",
  "inputs": {
    "task": "Audio-reactive boid swarm",
    "algorithm_attempted": "flocking_boids",
    "performance_target": "60fps @ 16k particles"
  },
  "outputs": {
    "cg_discoveries": {
      "algorithm_insights": {
        "flocking_boids": {
          "effectiveness": 0.7,
          "actual_performance": "45fps @ 16k, 60fps @ 8k",
          "parameter_insights": {
            "neighbor_radius": "Smaller radius = less neighbor queries = better perf"
          }
        }
      },
      "optimization_patterns": {
        "reduced_neighbor_radius": {
          "description": "Reduce boid neighbor radius to limit queries",
          "improvement": "30% fps gain with small visual difference",
          "applicable_to": ["flocking_boids"]
        }
      }
    }
  },
  "evidence": [
    {"source_path": "technical_approach: swarm_v1", "excerpt_hash": "abc123"},
    {"source_path": "td_builder: measured 45fps", "excerpt_hash": "def456"}
  ],
  "metrics": {
    "performance_accuracy": 0.75,
    "revision_cycles": 1
  },
  "status": "partial",
  "notes": "Boid performance estimate was optimistic; neighbor queries more expensive than modeled"
}
```

## Anti-Hallucination in Learning

- Only log measured performance, not estimates
- Require implementation evidence for algorithm updates
- Don't claim optimizations without measurement
- Conservative confidence for new patterns
- Mark theoretical improvements separately from proven ones

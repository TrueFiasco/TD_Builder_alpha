# Strategy V0: Baseline

## Overview

V0 represents the original approach before the agentic workflow improvements. It serves as a **control** for comparing the effectiveness of other strategies. This strategy is NOT recommended for production use.

## When to Use

- **Control comparison**: Measure improvement from V2+
- **Simple tests**: Quick sanity checks
- **Understanding baseline**: See what happens without orchestration

**NOT recommended for**:
- Production use
- Any project where quality matters

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      V0: BASELINE FLOW                           │
│                                                                  │
│  ┌──────────────────┐                                           │
│  │   User Prompt    │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │  Single-Pass     │                                           │
│  │  Generation      │  ← No KB query, no validation loops       │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │   Build JSON     │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │   Create TOE     │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐                                           │
│  │     Output       │  ← May have issues, no verification       │
│  └──────────────────┘                                           │
└─────────────────────────────────────────────────────────────────┘
```

## Phase Details

### Single Phase: Generate

**Entry Conditions**:
- User provides prompt

**Actions**:
1. Parse user prompt
2. Generate network JSON in one pass
3. Build TOE file

**Exit Conditions**:
- Build completes (success or failure)

### No Iteration

- No self-critique
- No validation
- No KB query
- No expert consultation

## Configuration Options

| Option | Value | Notes |
|--------|-------|-------|
| involvement | none | No user checkpoints |
| exploration | 1 | Single path only |
| quality_targets | N/A | No validation |
| max_iterations | 1 | Single pass |

## Expected Metrics

```yaml
typical_metrics:
  tokens:
    input: ~8000
    output: ~4000
    total: ~12000

  quality:
    creative: 0.4-0.6
    technical: 0.4-0.6
    design: 0.4-0.6
    final: 0.4-0.6

  iterations:
    total: 1

  troubleshooting:
    build_failures: ~50%
    validation_errors: N/A (not checked)

  artifacts:
    uniforms_connected: ~20%
    parameters_functional: ~30%
    palette_used: ~0%
```

## Implementation Notes

### How It Works via Claude Code

```
USER: Create an audio-reactive particle system

CLAUDE:
[Generating network JSON...]

Here is the network design:
```json
{
  "containers": [
    {
      "name": "project1",
      "type": "baseCOMP",
      ...
    }
  ]
}
```

[Building TOE file...]
Build complete: project1.toe

Done!
```

### Key Limitations

1. **No KB Query**
   - Doesn't check which operators exist
   - May reference invalid operators
   - Misses palette components

2. **No Validation**
   - No quality scoring
   - No critic review
   - Issues discovered only at build or runtime

3. **No Self-Improvement**
   - First attempt is final
   - No refinement based on feedback
   - No convergence toward quality

4. **No Expert Consultation**
   - GLSL expert not consulted for shaders
   - Python expert not consulted for scripts
   - Uniform/parameter connections guessed

## Known Issues

| Issue | Frequency | Impact |
|-------|-----------|--------|
| Missing GLSL uniforms | ~80% | Shaders don't respond to control |
| Invalid operator references | ~30% | Build failures |
| Parameters don't control anything | ~70% | Non-functional output |
| No palette usage | ~95% | Reinvents existing solutions |
| Generic implementations | ~90% | Lacks creative distinction |

## Comparison Baseline

V0 serves to answer: "How much better are the other strategies?"

```
V0 → V2: +60% quality, +130% tokens
V0 → V3: +80% quality, +270% tokens
V0 → V5: +90% quality, +220% tokens
V0 → V6: +100% quality, +330% tokens
```

## Wrapper Implementation

V0 is implemented as a thin wrapper around the current approach:

```python
class V0BaselineStrategy:
    name = "v0"

    def execute(self, prompt: str, blackboard: Blackboard) -> BuildResult:
        # Skip KB query
        # Skip validation
        # Single pass generation

        network_json = self.generate_network_one_shot(prompt)
        result = self.build_toe(network_json)

        # Write to blackboard for tracking only
        blackboard.write_section("§5_network_design", {
            "json": network_json,
            "version": 1
        })
        blackboard.write_section("§7_build_artifacts", {
            "build_attempts": [result]
        })

        return result

    def generate_network_one_shot(self, prompt: str) -> dict:
        """Generate network JSON without validation or iteration."""
        # Direct prompt → JSON generation
        pass
```

## Success Criteria

For V0 specifically, "success" just means the build completed:

- [ ] TOE file created
- [ ] No Python exceptions during build

Quality criteria are NOT checked in V0 (that's the point - it's the control).

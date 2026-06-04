# Critic Integration Quick Reference

## Setup

```python
from meta_agentic.execution import Blackboard, MetricsCollector, CriticIntegration

blackboard = Blackboard(project_name="my_project")
metrics = MetricsCollector(strategy="v6", project="my_project")
critic = CriticIntegration(blackboard, metrics)
```

## Critique Methods

```python
# Creative Vision (§2)
result = critic.critique_creative_vision(threshold=0.85)

# Technical Approach (§3)
result = critic.critique_technical_approach(threshold=0.85)

# Network Design (§5)
result = critic.critique_network_design(threshold=0.90)

# Any Section
result = critic.critique_section(SectionID.CREATIVE_VISION, threshold=0.85)
```

## CritiqueResult Fields

```python
result.section_id           # SectionID enum
result.score                # float (0.0-1.0)
result.passed               # bool
result.feedback             # str
result.issues               # list[str]
result.suggestions          # list[str]
result.criteria_scores      # dict[str, float]
result.blocking_issues      # list[str]
result.timestamp            # str (ISO8601)
result.has_blocking_issues  # property: bool
```

## Quality Thresholds

```python
# Get thresholds by preset
thresholds = critic.get_quality_thresholds("standard")
# Returns: {"creative": 0.85, "technical": 0.85, "design": 0.90}

# Available presets
"quick_draft"   # creative: 0.70, technical: 0.70, design: 0.80
"standard"      # creative: 0.85, technical: 0.85, design: 0.90
"excellence"    # creative: 0.90, technical: 0.90, design: 0.95
```

## Scoring Criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| artistic_coherence | 0.25 | Does the vision form a unified whole? |
| technical_feasibility | 0.25 | Can it be implemented? |
| implementation_clarity | 0.20 | Is the spec clear enough to build? |
| creative_alignment | 0.20 | Does it match user intent? |
| innovation_appropriateness | 0.10 | Is novelty level appropriate? |

## Common Workflow Pattern

```python
# Write content to blackboard
blackboard.write(SectionID.CREATIVE_VISION, content, "creative_expert")

# Critique
result = critic.critique_creative_vision(threshold=0.85)

# Handle result
if result.passed:
    blackboard.lock(SectionID.CREATIVE_VISION, "Approved by critic")
    # Proceed to next phase
else:
    # Log issues
    for issue in result.issues:
        print(f"Issue: {issue}")

    # Add blocking issues to blackboard
    for issue in result.blocking_issues:
        blackboard.add_blocking_issue(
            section_id=SectionID.CREATIVE_VISION,
            severity="high",
            classification="creative",
            description=issue
        )

    # Re-run expert with feedback
```

## Revision Loop Pattern

```python
max_iterations = 3
threshold = 0.85

for iteration in range(max_iterations):
    # Write content
    blackboard.write(section_id, content, author)

    # Critique
    result = critic.critique_section(section_id, threshold)

    if result.passed:
        blackboard.lock(section_id, "Approved by critic")
        break

    # Handle revision
    print(f"Iteration {iteration + 1}: Score {result.score:.2f}")
else:
    print("Max iterations exceeded")
```

## Parse Custom Response

```python
response = """
Overall Score: 0.87

Issues:
- [high] Missing data flow specification
- [medium] Color palette could be more specific

Suggestions:
- Define input → processing → output chain
- Specify exact hex codes for colors
"""

result = critic.parse_critique_response(
    response=response,
    section_id=SectionID.TECHNICAL_APPROACH,
    threshold=0.85
)

print(result.score)  # 0.87
print(result.passed)  # True
print(result.blocking_issues)  # ["Missing data flow specification"]
```

## Common Issues

| Issue | Severity | When Detected |
|-------|----------|---------------|
| vague_mood | medium | Creative vision has generic mood |
| algorithm_mismatch | high | Algorithm doesn't produce desired visual |
| performance_unrealistic | high | Impossible performance targets |
| missing_data_flow | high | No clear input → output path |
| color_mood_conflict | medium | Colors contradict mood |
| motion_mood_conflict | medium | Motion contradicts mood |

## Score Rubric Quick Ref

| Range | Meaning |
|-------|---------|
| 0.9-1.0 | Exceptional |
| 0.7-0.9 | Strong/Well-defined |
| 0.5-0.7 | Adequate with minor issues |
| 0.3-0.5 | Needs significant work |
| 0.0-0.3 | Major problems |

## Logging

```python
import logging
logging.basicConfig(level=logging.INFO)

# Log output includes:
# - Critique start/complete
# - Score updates to blackboard
# - Parsing warnings
# - Execution errors
```

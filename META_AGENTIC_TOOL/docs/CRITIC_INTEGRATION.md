# Critic Integration Guide

## Overview

The `CriticIntegration` module provides a specialized interface for running critic evaluations on blackboard sections within the META_AGENTIC_TOOL workflow. It wraps the standard `ExpertExecutor` pattern with critic-specific functionality:

- Structured `CritiqueResult` outputs
- Automatic score parsing from LLM responses
- Section-specific critique methods
- Integration with `critique_patterns.yaml` scoring rubrics
- Blackboard score updates
- Metrics tracking

## Quick Start

```python
from meta_agentic.execution import (
    Blackboard,
    SectionID,
    MetricsCollector,
    CriticIntegration,
)

# Setup
blackboard = Blackboard(project_name="my_project")
metrics = MetricsCollector(strategy="v6", project="my_project")

# Create critic integration
critic = CriticIntegration(blackboard, metrics)

# Critique a section
result = critic.critique_creative_vision(threshold=0.85)

if result.passed:
    print(f"Approved with score {result.score:.2f}")
    blackboard.lock(result.section_id, "Approved by critic")
else:
    print("Revision required:")
    for issue in result.issues:
        print(f"  - {issue}")
```

## Core Classes

### CritiqueResult

A structured result from a critic evaluation.

```python
@dataclass
class CritiqueResult:
    section_id: SectionID          # Which section was critiqued
    score: float                   # Overall score (0.0 to 1.0)
    passed: bool                   # score >= threshold and no blocking issues
    feedback: str                  # Summary feedback text
    issues: list[str]              # List of issue descriptions
    suggestions: list[str]         # List of improvement suggestions
    criteria_scores: dict[str, float]  # Per-criterion scores
    blocking_issues: list[str]     # High-severity blocking issues
    timestamp: str                 # When critique was performed
```

**Properties:**
- `has_blocking_issues: bool` - Returns True if any blocking issues exist

### CriticIntegration

Main interface for critic operations.

```python
class CriticIntegration:
    def __init__(
        self,
        blackboard: Blackboard,
        metrics: MetricsCollector,
        llm_executor: Optional[callable] = None
    ):
        """
        Initialize critic integration.

        Args:
            blackboard: Blackboard instance for state access
            metrics: MetricsCollector for tracking performance
            llm_executor: Optional callable for LLM execution
                         Signature: (prompt: str) -> str
        """
```

## Section-Specific Methods

### critique_creative_vision()

Critique §2 Creative Vision section.

```python
result = critic.critique_creative_vision(threshold=0.85)
```

**Evaluates:**
- Artistic coherence (mood, color, aesthetic alignment)
- Creative alignment (match to user intent)
- Innovation appropriateness

**Default Threshold:** 0.85

**Common Issues Detected:**
- `vague_mood` - Mood specification too generic
- `color_mood_conflict` - Colors contradict stated mood
- `motion_mood_conflict` - Motion contradicts stated mood

### critique_technical_approach()

Critique §3 Technical Approach section.

```python
result = critic.critique_technical_approach(threshold=0.85)
```

**Evaluates:**
- Technical feasibility (can it be implemented?)
- Implementation clarity (is spec buildable?)
- Algorithm selection (appropriate techniques?)

**Default Threshold:** 0.85

**Common Issues Detected:**
- `algorithm_mismatch` - Algorithm doesn't produce desired effect
- `performance_unrealistic` - Performance targets impossible
- `missing_data_flow` - No clear input → output path

### critique_network_design()

Critique §5 Network Design section.

```python
result = critic.critique_network_design(threshold=0.90)
```

**Evaluates:**
- Network architecture quality
- Implementation clarity
- Alignment with creative and technical specs

**Default Threshold:** 0.90 (higher bar for final design)

**Common Issues Detected:**
- `missing_data_flow` - Incomplete network connections
- `undefined_interaction` - Interactive elements without clear behavior
- `algorithm_mismatch` - Network doesn't implement specified techniques

### critique_section()

Generic section critique method.

```python
result = critic.critique_section(
    section_id=SectionID.CREATIVE_VISION,
    threshold=0.85
)
```

**Use this when:**
- You need to critique a section not covered by specific methods
- You want to override default thresholds
- You're writing generic workflow code

## Quality Thresholds

Quality thresholds are defined in `critique_patterns.yaml` under `workflow_quality_thresholds`.

### Get Thresholds by Preset

```python
# Available presets: "quick_draft", "standard", "excellence"
thresholds = critic.get_quality_thresholds("standard")

print(thresholds)
# {
#     "creative": 0.85,
#     "technical": 0.85,
#     "design": 0.90
# }
```

### Preset Comparison

| Preset | Creative | Technical | Design | Use Case |
|--------|----------|-----------|--------|----------|
| **quick_draft** | 0.70 | 0.70 | 0.80 | Fast iteration, lower quality bar |
| **standard** | 0.85 | 0.85 | 0.90 | Balanced quality and speed |
| **excellence** | 0.90 | 0.90 | 0.95 | Maximum quality, time available |

## Parsing Critique Responses

The `parse_critique_response()` method extracts structured data from LLM text responses.

```python
response = """
Overall Score: 0.87

Criteria Scores:
- artistic_coherence: 0.90
- technical_feasibility: 0.85

Issues:
- [medium] Motion quality not specified
- [low] Animation timing could be more explicit

Suggestions:
- Add slow, organic motion for contemplative mood
- Define ease curves and duration ranges

Blocking Issues:
None
"""

result = critic.parse_critique_response(
    response=response,
    section_id=SectionID.CREATIVE_VISION,
    threshold=0.85
)

print(f"Score: {result.score}")  # 0.87
print(f"Passed: {result.passed}")  # True
print(f"Issues: {len(result.issues)}")  # 2
```

### Supported Patterns

**Overall Score:**
- `Overall Score: 0.85`
- `Score: 85%`
- `overall_score: 0.85`

**Criteria Scores:**
- `artistic_coherence: 0.90`
- `technical_feasibility: 0.85`
- `implementation_clarity: 0.88`
- `creative_alignment: 0.86`
- `innovation_appropriateness: 0.80`

**Issues:**
- Bulleted lists under "Issues:" or "Issues Requiring Attention:"
- Severity markers: `[high]`, `[medium]`, `[low]`

**Suggestions:**
- Bulleted lists under "Suggestions:" or "Recommended:"

**Blocking Issues:**
- Bulleted lists under "Blocking Issues:"
- Also extracts `[high]` severity issues as blocking

## Integration with Workflow

### Example: Creative Phase with Revision Loop

```python
# Phase: Creative Vision
max_iterations = 3
threshold = 0.85

for iteration in range(max_iterations):
    # Write creative vision to blackboard
    blackboard.write(
        SectionID.CREATIVE_VISION,
        creative_content,
        author="creative_expert"
    )

    # Critique
    result = critic.critique_creative_vision(threshold)

    if result.passed:
        print(f"Approved after {iteration + 1} iteration(s)")
        blackboard.lock(SectionID.CREATIVE_VISION, "Approved by critic")
        break
    else:
        print(f"Iteration {iteration + 1} failed. Score: {result.score:.2f}")

        # Handle blocking issues
        if result.has_blocking_issues:
            print("Blocking issues found:")
            for issue in result.blocking_issues:
                print(f"  - {issue}")

        # Add issues to blackboard
        for issue in result.issues:
            blackboard.add_blocking_issue(
                section_id=SectionID.CREATIVE_VISION,
                severity="high" if "[high]" in issue else "medium",
                classification="creative",
                description=issue
            )

        # Provide feedback to creative expert
        # (Re-run creative expert with feedback)
else:
    print("Max iterations exceeded - escalate to human review")
```

### Example: Multi-Phase Approval

```python
# Get quality thresholds
thresholds = critic.get_quality_thresholds("standard")

# Phase 1: Creative
creative_result = critic.critique_creative_vision(thresholds["creative"])
if not creative_result.passed:
    # Handle revision
    pass

# Phase 2: Technical
technical_result = critic.critique_technical_approach(thresholds["technical"])
if not technical_result.passed:
    # Handle revision
    pass

# Phase 3: Design
design_result = critic.critique_network_design(thresholds["design"])
if not design_result.passed:
    # Handle revision
    pass

# All phases approved
print("All phases approved - ready for build")
```

## Scoring Criteria

Criteria are defined in `critique_patterns.yaml` under `quality_criteria`.

### Artistic Coherence (weight: 0.25)

**Question:** Does the creative vision form a unified whole?

**High Score Indicators:**
- Mood and aesthetics align
- Color palette supports emotional intent
- Motion qualities match stated mood
- All elements contribute to core concept

**Rubric:**
- 0.9-1.0: Exceptional unity of vision
- 0.7-0.9: Strong coherence, elements support each other
- 0.5-0.7: Generally coherent with minor issues
- 0.3-0.5: Some misalignment, needs clarification
- 0.0-0.3: Major conflicts between creative elements

### Technical Feasibility (weight: 0.25)

**Question:** Can this be implemented with available tools/resources?

**High Score Indicators:**
- Algorithm exists for desired effect
- Performance target achievable
- Required operators/tools available
- Data flow is realistic

**Rubric:**
- 0.9-1.0: Straightforward implementation
- 0.7-0.9: Well-defined, proven techniques
- 0.5-0.7: Feasible with known approaches
- 0.3-0.5: Major technical challenges, unclear solution
- 0.0-0.3: Technically impossible or undefined

### Implementation Clarity (weight: 0.20)

**Question:** Is the specification clear enough to build?

**High Score Indicators:**
- Specific algorithms named
- Parameters defined with ranges
- Data flow clearly documented
- Unambiguous requirements

**Rubric:**
- 0.9-1.0: Exceptional detail, no questions
- 0.7-0.9: Clear specification, ready to build
- 0.5-0.7: Buildable but some clarification needed
- 0.3-0.5: Too vague, many questions remain
- 0.0-0.3: Cannot build from this specification

### Creative Alignment (weight: 0.20)

**Question:** Does the output match the original user intent?

**High Score Indicators:**
- Core concept addresses user request
- Emotion/mood matches user's goal
- Scale/complexity appropriate
- Use case requirements met

**Rubric:**
- 0.9-1.0: Perfect match to user vision
- 0.7-0.9: Strong alignment with user intent
- 0.5-0.7: Addresses request with some interpretation
- 0.3-0.5: Partially addresses but missing key elements
- 0.0-0.3: Does not address user request

### Innovation Appropriateness (weight: 0.10)

**Question:** Is the level of novelty appropriate for the context?

**High Score Indicators:**
- Novel where beneficial
- Uses proven patterns where appropriate
- Risk level matches project context

**Rubric:**
- 0.9-1.0: Perfect balance for context
- 0.7-0.9: Well-calibrated innovation
- 0.5-0.7: Reasonable balance
- 0.3-0.5: Some mismatch with context
- 0.0-0.3: Inappropriate risk level

## Common Issues Reference

Based on `critique_patterns.yaml#common_issues`:

| Issue Type | Severity | Description |
|------------|----------|-------------|
| `vague_mood` | medium | Mood specification too generic |
| `algorithm_mismatch` | high | Chosen algorithm doesn't produce desired visual |
| `performance_unrealistic` | high | Performance requirements impossible to meet |
| `scope_creep` | medium | Solution significantly exceeds original request |
| `missing_data_flow` | high | No clear path from input to output |
| `color_mood_conflict` | medium | Color palette contradicts stated mood |
| `motion_mood_conflict` | medium | Motion quality contradicts stated mood |
| `undefined_interaction` | medium | Interactive elements without clear behavior |

## Logging

The critic integration uses Python's standard logging module:

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Or configure specific logger
logger = logging.getLogger("meta_agentic.execution.critic_integration")
logger.setLevel(logging.INFO)
```

**Log Levels:**
- `DEBUG`: Detailed parsing and execution info
- `INFO`: Critique start/complete, score updates
- `WARNING`: Missing files, parsing issues
- `ERROR`: Execution failures, exceptions

## Error Handling

```python
try:
    result = critic.critique_creative_vision(threshold=0.85)

    if result.score == 0.0 and not result.passed:
        # Check if this is an error or legitimate low score
        if "error" in result.feedback.lower():
            print(f"Critique failed: {result.feedback}")
        else:
            print("Low score - requires revision")

except Exception as e:
    print(f"Unexpected error: {e}")
```

## Advanced Usage

### Custom LLM Executor

```python
def my_llm_executor(prompt: str) -> str:
    """
    Custom LLM execution function.

    Args:
        prompt: The rendered prompt to send to LLM

    Returns:
        LLM response text
    """
    # Call your LLM API here
    # response = openai.ChatCompletion.create(...)
    return response_text

critic = CriticIntegration(
    blackboard=blackboard,
    metrics=metrics,
    llm_executor=my_llm_executor
)
```

### Manual Score Override

```python
# Critique a section
result = critic.critique_section(SectionID.CREATIVE_VISION, threshold=0.85)

# Manually override score if needed
result.score = 0.90
result.passed = True

# Update blackboard
section = blackboard.sections[result.section_id]
if section.current:
    section.current.score = result.score
```

## See Also

- `critique_patterns.yaml` - Scoring rubrics and quality criteria
- `expert_executor.py` - Underlying execution infrastructure
- `blackboard.py` - State management
- `AGENT_INTERFACE.md` - Expert integration patterns
- `METRICS_SPEC.md` - Metrics tracking specification

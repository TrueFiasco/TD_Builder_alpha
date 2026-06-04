"""
Metrics: Track workflow execution metrics for strategy comparison.

Tracks:
    - Cost: Token counts (input/output/total), estimated USD
    - Quality: Scores per phase (creative/technical/design)
    - Iterations: Count per phase, total
    - Troubleshooting: Build failures, validation errors, phase reopens

See docs/METRICS_SPEC.md for full specification.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import json


# Approximate cost per 1K tokens (as of 2025-01)
COST_PER_1K_INPUT = 0.015  # Claude 3.5 Sonnet input
COST_PER_1K_OUTPUT = 0.075  # Claude 3.5 Sonnet output


@dataclass
class TokenUsage:
    """Token usage for a single API call or agent execution."""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        input_cost = (self.input_tokens / 1000) * COST_PER_1K_INPUT
        output_cost = (self.output_tokens / 1000) * COST_PER_1K_OUTPUT
        return round(input_cost + output_cost, 4)


@dataclass
class PhaseMetrics:
    """Metrics for a single workflow phase."""
    phase: str
    iterations: int = 0
    scores: list[float] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    reopened_count: int = 0

    @property
    def final_score(self) -> Optional[float]:
        return self.scores[-1] if self.scores else None

    @property
    def best_score(self) -> Optional[float]:
        return max(self.scores) if self.scores else None

    @property
    def improvement(self) -> Optional[float]:
        if len(self.scores) < 2:
            return None
        return self.scores[-1] - self.scores[0]


@dataclass
class TroubleshootingEvent:
    """A troubleshooting event during workflow execution."""
    event_type: str  # "build_failure", "validation_error", "phase_reopen", "manual_intervention"
    phase: str
    timestamp: str
    description: str
    resolution: Optional[str] = None
    tokens_spent: int = 0


@dataclass
class ArtifactValidation:
    """Validation results for build artifacts."""
    toe_valid: bool = False
    uniforms_connected: bool = False
    palette_used: bool = False
    params_functional: bool = False
    validation_errors: list[str] = field(default_factory=list)


class MetricsCollector:
    """
    Collects and aggregates workflow execution metrics.

    Usage:
        metrics = MetricsCollector(strategy="v2", project="audio_test")
        metrics.start_phase("creative")
        metrics.record_tokens(input=1000, output=500)
        metrics.record_score("creative", 0.85)
        metrics.end_phase("creative")
        metrics.record_troubleshooting("validation_error", "creative", "Missing uniforms")
        report = metrics.get_report()
    """

    def __init__(self, strategy: str, project: str):
        self.strategy = strategy
        self.project = project
        self.started_at = datetime.utcnow().isoformat() + "Z"
        self.completed_at: Optional[str] = None

        # Phase metrics
        self.phases: dict[str, PhaseMetrics] = {}

        # Troubleshooting events
        self.troubleshooting_events: list[TroubleshootingEvent] = []

        # Artifact validation
        self.artifact_validation: Optional[ArtifactValidation] = None

        # Agent call log
        self.agent_calls: list[dict] = []

    def start_phase(self, phase: str):
        """Mark the start of a phase."""
        if phase not in self.phases:
            self.phases[phase] = PhaseMetrics(
                phase=phase,
                started_at=datetime.utcnow().isoformat() + "Z"
            )
        else:
            # Phase reopened
            self.phases[phase].reopened_count += 1

    def end_phase(self, phase: str):
        """Mark the end of a phase."""
        if phase in self.phases:
            self.phases[phase].completed_at = datetime.utcnow().isoformat() + "Z"

    def record_tokens(
        self,
        input_tokens: int,
        output_tokens: int,
        phase: Optional[str] = None,
        agent: Optional[str] = None
    ):
        """Record token usage."""
        usage = TokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)

        if phase and phase in self.phases:
            pm = self.phases[phase]
            pm.token_usage.input_tokens += input_tokens
            pm.token_usage.output_tokens += output_tokens

        if agent:
            self.agent_calls.append({
                "agent": agent,
                "phase": phase,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            })

    def record_score(self, phase: str, score: float):
        """Record a quality score for a phase."""
        if phase not in self.phases:
            self.phases[phase] = PhaseMetrics(phase=phase)

        self.phases[phase].scores.append(score)

    def record_iteration(self, phase: str):
        """Increment iteration count for a phase."""
        if phase not in self.phases:
            self.phases[phase] = PhaseMetrics(phase=phase)

        self.phases[phase].iterations += 1

    def record_troubleshooting(
        self,
        event_type: str,
        phase: str,
        description: str,
        resolution: Optional[str] = None,
        tokens_spent: int = 0
    ):
        """Record a troubleshooting event."""
        event = TroubleshootingEvent(
            event_type=event_type,
            phase=phase,
            timestamp=datetime.utcnow().isoformat() + "Z",
            description=description,
            resolution=resolution,
            tokens_spent=tokens_spent
        )
        self.troubleshooting_events.append(event)

    def record_artifact_validation(
        self,
        toe_valid: bool = False,
        uniforms_connected: bool = False,
        palette_used: bool = False,
        params_functional: bool = False,
        validation_errors: Optional[list[str]] = None
    ):
        """Record artifact validation results."""
        self.artifact_validation = ArtifactValidation(
            toe_valid=toe_valid,
            uniforms_connected=uniforms_connected,
            palette_used=palette_used,
            params_functional=params_functional,
            validation_errors=validation_errors or []
        )

    def complete(self):
        """Mark workflow as complete."""
        self.completed_at = datetime.utcnow().isoformat() + "Z"

    @property
    def total_tokens(self) -> TokenUsage:
        """Get total token usage across all phases."""
        total = TokenUsage()
        for pm in self.phases.values():
            total.input_tokens += pm.token_usage.input_tokens
            total.output_tokens += pm.token_usage.output_tokens
        return total

    @property
    def total_iterations(self) -> int:
        """Get total iteration count across all phases."""
        return sum(pm.iterations for pm in self.phases.values())

    @property
    def final_quality_score(self) -> Optional[float]:
        """
        Get the final quality score (minimum across phases).
        This reflects the V5/V6 multi-perspective aggregation.
        """
        final_scores = [
            pm.final_score for pm in self.phases.values()
            if pm.final_score is not None
        ]
        return min(final_scores) if final_scores else None

    @property
    def build_failures(self) -> int:
        """Count of build failure events."""
        return sum(
            1 for e in self.troubleshooting_events
            if e.event_type == "build_failure"
        )

    @property
    def validation_errors(self) -> int:
        """Count of validation error events."""
        return sum(
            1 for e in self.troubleshooting_events
            if e.event_type == "validation_error"
        )

    @property
    def phase_reopens(self) -> int:
        """Count of phase reopen events."""
        return sum(pm.reopened_count for pm in self.phases.values())

    def get_report(self) -> dict:
        """Generate a complete metrics report."""
        total_usage = self.total_tokens

        return {
            "run_metrics": {
                "strategy": self.strategy,
                "project": self.project,
                "started_at": self.started_at,
                "completed_at": self.completed_at,

                "cost": {
                    "total_tokens": total_usage.total_tokens,
                    "input_tokens": total_usage.input_tokens,
                    "output_tokens": total_usage.output_tokens,
                    "estimated_cost_usd": total_usage.estimated_cost_usd
                },

                "quality": {
                    phase: {
                        "final_score": pm.final_score,
                        "best_score": pm.best_score,
                        "improvement": pm.improvement,
                        "score_history": pm.scores
                    }
                    for phase, pm in self.phases.items()
                },

                "iterations": {
                    phase: pm.iterations
                    for phase, pm in self.phases.items()
                } | {"total": self.total_iterations},

                "troubleshooting": {
                    "build_failures": self.build_failures,
                    "validation_errors": self.validation_errors,
                    "phase_reopens": self.phase_reopens,
                    "manual_interventions": sum(
                        1 for e in self.troubleshooting_events
                        if e.event_type == "manual_intervention"
                    ),
                    "events": [
                        {
                            "type": e.event_type,
                            "phase": e.phase,
                            "timestamp": e.timestamp,
                            "description": e.description,
                            "resolution": e.resolution
                        }
                        for e in self.troubleshooting_events
                    ]
                },

                "artifacts": {
                    "toe_valid": self.artifact_validation.toe_valid if self.artifact_validation else False,
                    "uniforms_connected": self.artifact_validation.uniforms_connected if self.artifact_validation else False,
                    "palette_used": self.artifact_validation.palette_used if self.artifact_validation else False,
                    "params_functional": self.artifact_validation.params_functional if self.artifact_validation else False,
                    "validation_errors": self.artifact_validation.validation_errors if self.artifact_validation else []
                },

                "agent_calls": self.agent_calls
            }
        }

    def save(self, path: Path):
        """Save metrics report to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.get_report(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "MetricsCollector":
        """Load metrics from file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        rm = data["run_metrics"]
        collector = cls(strategy=rm["strategy"], project=rm["project"])
        collector.started_at = rm["started_at"]
        collector.completed_at = rm.get("completed_at")

        # Restore phases
        for phase, quality_data in rm.get("quality", {}).items():
            pm = PhaseMetrics(phase=phase)
            pm.scores = quality_data.get("score_history", [])
            pm.iterations = rm.get("iterations", {}).get(phase, 0)
            collector.phases[phase] = pm

        # Restore troubleshooting
        for event_data in rm.get("troubleshooting", {}).get("events", []):
            event = TroubleshootingEvent(
                event_type=event_data["type"],
                phase=event_data["phase"],
                timestamp=event_data["timestamp"],
                description=event_data["description"],
                resolution=event_data.get("resolution")
            )
            collector.troubleshooting_events.append(event)

        # Restore agent calls
        collector.agent_calls = rm.get("agent_calls", [])

        return collector


def compare_metrics(metrics_list: list[MetricsCollector]) -> dict:
    """
    Compare metrics across multiple strategy runs.

    Returns a comparison table suitable for display.
    """
    comparison = {
        "strategies": [],
        "comparison_timestamp": datetime.utcnow().isoformat() + "Z"
    }

    for m in metrics_list:
        total_usage = m.total_tokens
        comparison["strategies"].append({
            "strategy": m.strategy,
            "project": m.project,
            "tokens": total_usage.total_tokens,
            "cost_usd": total_usage.estimated_cost_usd,
            "quality": m.final_quality_score,
            "iterations": m.total_iterations,
            "build_failures": m.build_failures,
            "validation_errors": m.validation_errors,
            "phase_reopens": m.phase_reopens,
            "toe_valid": m.artifact_validation.toe_valid if m.artifact_validation else False
        })

    # Sort by quality (descending), then by cost (ascending)
    comparison["strategies"].sort(
        key=lambda x: (-(x["quality"] or 0), x["cost_usd"])
    )

    return comparison

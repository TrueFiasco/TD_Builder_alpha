"""
Critic Context: Persistent context management for critics across phases.

This module maintains critic context across all workflow phases, enabling:
- Accumulated understanding of the project
- Learned preferences from user feedback
- Cross-phase pattern detection
- Consistency checking between phases

Used by V6UnifiedStrategy for persistent critic evaluation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class IssueClassification(Enum):
    """Classification of issues found during critique."""
    CREATIVE = "creative"        # Artistic/conceptual issues
    TECHNICAL = "technical"      # Implementation/performance issues
    DESIGN = "design"            # Network architecture issues
    STRUCTURAL = "structural"    # JSON/format issues
    LOGIC = "logic"              # Signal flow/connection issues
    ALIGNMENT = "alignment"      # Mismatch between phases


class IssueSeverity(Enum):
    """Severity level of issues."""
    BLOCKING = "blocking"        # Must fix before proceeding
    WARNING = "warning"          # Should fix, can proceed
    SUGGESTION = "suggestion"    # Nice to have


@dataclass
class CriticIssue:
    """A single issue identified by the critic."""
    classification: IssueClassification
    severity: IssueSeverity
    description: str
    recommended_fix: str
    section_ref: Optional[str] = None  # e.g., "§2.v3"
    related_issues: list[str] = field(default_factory=list)


@dataclass
class CriticContextFrame:
    """
    A single frame of critic context from one evaluation.

    Captures the critic's assessment at a specific point in the workflow.
    """
    timestamp: str
    phase: str
    section_id: str
    version: int
    score: float
    passed: bool
    issues: list[CriticIssue] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    feedback_summary: str = ""
    variant_id: Optional[str] = None  # If evaluating a variant

    def to_context_string(self) -> str:
        """Format this frame as context for the next critique."""
        lines = [
            f"[{self.phase.upper()}] {self.section_id} v{self.version}",
            f"  Score: {self.score:.2f} ({'PASS' if self.passed else 'FAIL'})",
        ]

        if self.issues:
            lines.append(f"  Issues ({len(self.issues)}):")
            for issue in self.issues[:3]:  # Top 3 issues
                lines.append(f"    - [{issue.severity.value}] {issue.description}")

        if self.improvements:
            lines.append(f"  Improvements suggested: {len(self.improvements)}")

        if self.feedback_summary:
            lines.append(f"  Summary: {self.feedback_summary[:100]}...")

        return "\n".join(lines)


@dataclass
class LearnedPreference:
    """A preference learned from user feedback or iteration patterns."""
    preference: str
    source: str  # "user_feedback", "iteration_pattern", "approval_pattern"
    confidence: float  # 0.0-1.0
    timestamp: str
    examples: list[str] = field(default_factory=list)


class PersistentCriticContext:
    """
    Maintains critic context across all phases of a workflow.

    The critic uses this accumulated context to:
    1. Understand the project holistically
    2. Detect cross-phase inconsistencies
    3. Apply learned preferences
    4. Provide more relevant feedback

    Usage:
        context = PersistentCriticContext()

        # After each critique
        frame = CriticContextFrame(...)
        context.accumulate_review(frame)

        # Before next critique
        context_str = context.get_context_for_phase("design")
        # Include context_str in critic prompt

        # After user feedback
        context.learn_preference("User values interactivity over aesthetics")
    """

    def __init__(self, project_name: str = ""):
        self.project_name = project_name
        self.frames: list[CriticContextFrame] = []
        self.learned_preferences: list[LearnedPreference] = []
        self.project_understanding: dict[str, str] = {}
        self.current_concerns: list[str] = []
        self.logger = logging.getLogger(f"{__name__}.PersistentCriticContext")

    def accumulate_review(self, frame: CriticContextFrame) -> None:
        """
        Add a critique frame to the accumulated context.

        Args:
            frame: The critique frame to add
        """
        self.frames.append(frame)

        # Extract any blocking issues as current concerns
        for issue in frame.issues:
            if issue.severity == IssueSeverity.BLOCKING:
                concern = f"[{frame.phase}] {issue.description}"
                if concern not in self.current_concerns:
                    self.current_concerns.append(concern)

        # Clear concerns if passed
        if frame.passed:
            self.current_concerns = [
                c for c in self.current_concerns
                if not c.startswith(f"[{frame.phase}]")
            ]

        self.logger.info(
            f"Accumulated review: {frame.phase} v{frame.version} "
            f"score={frame.score:.2f}, issues={len(frame.issues)}"
        )

    def get_context_for_phase(self, phase: str, max_frames: int = 5) -> str:
        """
        Get accumulated context for use in the next critique.

        Args:
            phase: The phase about to be critiqued
            max_frames: Maximum number of previous frames to include

        Returns:
            Formatted context string to include in critic prompt
        """
        lines = ["=== CRITIC ACCUMULATED CONTEXT ==="]

        # Project understanding
        if self.project_understanding:
            lines.append("\n## Project Understanding")
            for key, value in self.project_understanding.items():
                lines.append(f"- {key}: {value}")

        # Learned preferences
        if self.learned_preferences:
            lines.append("\n## Learned Preferences")
            for pref in self.learned_preferences:
                lines.append(f"- {pref.preference} (confidence: {pref.confidence:.1f})")

        # Recent critique history
        relevant_frames = self._get_relevant_frames(phase, max_frames)
        if relevant_frames:
            lines.append("\n## Previous Reviews")
            for frame in relevant_frames:
                lines.append(frame.to_context_string())

        # Current concerns
        if self.current_concerns:
            lines.append("\n## Current Concerns (BLOCKING)")
            for concern in self.current_concerns:
                lines.append(f"- {concern}")

        # Phase-specific guidance
        lines.append(f"\n## Now Reviewing: {phase.upper()}")
        lines.append(self._get_phase_guidance(phase))

        lines.append("\n=== END CONTEXT ===")
        return "\n".join(lines)

    def _get_relevant_frames(self, current_phase: str, max_frames: int) -> list[CriticContextFrame]:
        """Get the most relevant frames for the current phase."""
        # Prioritize: same phase history, then prerequisite phases
        phase_order = ["creative", "technical", "resources", "design", "build"]

        try:
            current_idx = phase_order.index(current_phase)
            prerequisite_phases = phase_order[:current_idx + 1]
        except ValueError:
            prerequisite_phases = [current_phase]

        # Get frames from relevant phases
        relevant = [f for f in self.frames if f.phase in prerequisite_phases]

        # Sort by timestamp descending
        relevant.sort(key=lambda f: f.timestamp, reverse=True)

        return relevant[:max_frames]

    def _get_phase_guidance(self, phase: str) -> str:
        """Get phase-specific guidance for the critic."""
        guidance = {
            "creative": (
                "Focus on: artistic coherence, emotional impact, feasibility, "
                "alignment with requirements. Is this REMARKABLE?"
            ),
            "technical": (
                "Focus on: implementation viability, performance, correctness, "
                "alignment with creative vision. Can this actually be built?"
            ),
            "design": (
                "Focus on: network validity, parameter accuracy, pattern usage, "
                "alignment with both creative and technical specs. "
                "This phase has the HIGHEST bar (0.90+)."
            ),
            "build": (
                "Focus on: JSON validity, operator existence, connection correctness, "
                "file structure. Verify against KB ground truth."
            ),
        }
        return guidance.get(phase, "Evaluate holistically against requirements.")

    def learn_preference(
        self,
        preference: str,
        source: str = "user_feedback",
        confidence: float = 0.8,
        examples: Optional[list[str]] = None
    ) -> None:
        """
        Record a learned preference from user feedback or patterns.

        Args:
            preference: The preference statement
            source: Where this preference was learned from
            confidence: How confident we are (0.0-1.0)
            examples: Optional examples supporting this preference
        """
        pref = LearnedPreference(
            preference=preference,
            source=source,
            confidence=confidence,
            timestamp=datetime.utcnow().isoformat(),
            examples=examples or []
        )
        self.learned_preferences.append(pref)
        self.logger.info(f"Learned preference: {preference} (source={source})")

    def update_project_understanding(self, key: str, value: str) -> None:
        """
        Update the critic's understanding of the project.

        Args:
            key: Aspect of the project (e.g., "core_concept", "technical_constraints")
            value: The understanding
        """
        self.project_understanding[key] = value
        self.logger.debug(f"Updated understanding: {key} = {value[:50]}...")

    def add_concern(self, concern: str) -> None:
        """Add a current concern that should be monitored."""
        if concern not in self.current_concerns:
            self.current_concerns.append(concern)
            self.logger.info(f"Added concern: {concern}")

    def resolve_concern(self, concern: str) -> None:
        """Mark a concern as resolved."""
        if concern in self.current_concerns:
            self.current_concerns.remove(concern)
            self.logger.info(f"Resolved concern: {concern}")

    def get_phase_history(self, phase: str) -> list[CriticContextFrame]:
        """Get all critique frames for a specific phase."""
        return [f for f in self.frames if f.phase == phase]

    def get_iteration_count(self, phase: str) -> int:
        """Get the number of iterations for a phase."""
        return len(self.get_phase_history(phase))

    def get_score_trend(self, phase: str) -> list[float]:
        """Get the score trend for a phase (for convergence detection)."""
        return [f.score for f in self.get_phase_history(phase)]

    def is_converged(self, phase: str, window: int = 2, min_improvement: float = 0.01) -> bool:
        """
        Check if a phase has converged (no improvement in N iterations).

        Args:
            phase: The phase to check
            window: Number of iterations to check
            min_improvement: Minimum score improvement to consider "improving"

        Returns:
            True if converged (no significant improvement in window)
        """
        scores = self.get_score_trend(phase)

        if len(scores) < window:
            return False

        recent = scores[-window:]
        max_improvement = max(recent) - min(recent)

        converged = max_improvement < min_improvement
        if converged:
            self.logger.info(
                f"Phase {phase} converged: scores {recent}, "
                f"max_improvement={max_improvement:.4f} < {min_improvement}"
            )

        return converged

    def detect_cross_phase_issue(
        self,
        current_phase: str,
        issue_description: str
    ) -> Optional[IssueClassification]:
        """
        Detect if an issue in the current phase originates from an earlier phase.

        Args:
            current_phase: The current phase
            issue_description: Description of the issue

        Returns:
            Classification of the root cause phase, or None if current phase
        """
        # Keywords that suggest creative issues
        creative_keywords = ["vision", "concept", "artistic", "aesthetic", "feel"]
        # Keywords that suggest technical issues
        technical_keywords = ["performance", "gpu", "implementation", "technique"]

        issue_lower = issue_description.lower()

        if current_phase == "design":
            if any(kw in issue_lower for kw in creative_keywords):
                return IssueClassification.CREATIVE
            if any(kw in issue_lower for kw in technical_keywords):
                return IssueClassification.TECHNICAL

        return None

    def reset(self) -> None:
        """Clear all accumulated context."""
        self.frames.clear()
        self.learned_preferences.clear()
        self.project_understanding.clear()
        self.current_concerns.clear()
        self.logger.info("Critic context reset")

    def to_dict(self) -> dict:
        """Serialize context to dict for persistence."""
        return {
            "project_name": self.project_name,
            "frames": [
                {
                    "timestamp": f.timestamp,
                    "phase": f.phase,
                    "section_id": f.section_id,
                    "version": f.version,
                    "score": f.score,
                    "passed": f.passed,
                    "feedback_summary": f.feedback_summary,
                }
                for f in self.frames
            ],
            "learned_preferences": [
                {
                    "preference": p.preference,
                    "source": p.source,
                    "confidence": p.confidence,
                }
                for p in self.learned_preferences
            ],
            "project_understanding": self.project_understanding,
            "current_concerns": self.current_concerns,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PersistentCriticContext":
        """Restore context from dict."""
        ctx = cls(project_name=data.get("project_name", ""))
        ctx.project_understanding = data.get("project_understanding", {})
        ctx.current_concerns = data.get("current_concerns", [])

        # Restore preferences
        for p in data.get("learned_preferences", []):
            ctx.learned_preferences.append(LearnedPreference(
                preference=p["preference"],
                source=p["source"],
                confidence=p["confidence"],
                timestamp="",
                examples=[]
            ))

        return ctx


def create_critique_frame(
    phase: str,
    section_id: str,
    version: int,
    score: float,
    threshold: float,
    feedback: str = "",
    issues: Optional[list[dict]] = None
) -> CriticContextFrame:
    """
    Helper to create a CriticContextFrame from critic output.

    Args:
        phase: Current phase
        section_id: Section being critiqued (e.g., "§2")
        version: Version number of the section
        score: Critic score (0.0-1.0)
        threshold: Pass threshold
        feedback: Full feedback text
        issues: List of issue dicts with classification, severity, description

    Returns:
        CriticContextFrame ready for accumulation
    """
    parsed_issues = []
    if issues:
        for issue in issues:
            parsed_issues.append(CriticIssue(
                classification=IssueClassification(issue.get("classification", "design")),
                severity=IssueSeverity(issue.get("severity", "warning")),
                description=issue.get("description", ""),
                recommended_fix=issue.get("recommended_fix", ""),
            ))

    return CriticContextFrame(
        timestamp=datetime.utcnow().isoformat(),
        phase=phase,
        section_id=section_id,
        version=version,
        score=score,
        passed=score >= threshold,
        issues=parsed_issues,
        feedback_summary=feedback[:200] if feedback else "",
    )


__all__ = [
    "IssueClassification",
    "IssueSeverity",
    "CriticIssue",
    "CriticContextFrame",
    "LearnedPreference",
    "PersistentCriticContext",
    "create_critique_frame",
]

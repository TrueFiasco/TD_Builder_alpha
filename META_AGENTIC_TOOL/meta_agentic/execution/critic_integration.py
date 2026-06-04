"""
Critic Integration: Specialized interface for critic scoring and validation.

This module provides a higher-level interface for running critic evaluations
on blackboard sections. It wraps the ExpertExecutor pattern but provides:
- Structured CritiqueResult output
- Automatic score parsing and validation
- Section-specific critique methods
- Integration with critique_patterns.yaml scoring rubrics

Usage:
    critic = CriticIntegration(blackboard, metrics)

    # Critique specific sections
    result = critic.critique_creative_vision(threshold=0.85)
    if result.passed:
        print(f"Vision approved with score {result.score}")
    else:
        print(f"Issues found: {result.issues}")

    # Or critique any section
    result = critic.critique_section(SectionID.NETWORK_DESIGN, threshold=0.90)
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import re
import yaml
import logging

from .blackboard import Blackboard, SectionID
from .metrics import MetricsCollector
from .expert_executor import get_expert_executor


logger = logging.getLogger(__name__)


@dataclass
class CritiqueResult:
    """
    Structured result from a critic evaluation.

    Attributes:
        section_id: Which section was critiqued
        score: Overall score from 0.0 to 1.0
        passed: Whether score meets threshold
        feedback: Summary feedback text
        issues: List of issue descriptions
        suggestions: List of improvement suggestions
        criteria_scores: Per-criterion scores
        blocking_issues: High-severity issues that block progress
        timestamp: When critique was performed
    """
    section_id: SectionID
    score: float  # 0.0 to 1.0
    passed: bool  # score >= threshold
    feedback: str
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    criteria_scores: dict[str, float] = field(default_factory=dict)
    blocking_issues: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    @property
    def has_blocking_issues(self) -> bool:
        """Check if there are any blocking issues."""
        return len(self.blocking_issues) > 0


class CriticIntegration:
    """
    Specialized interface for critic scoring operations.

    Wraps the ExpertExecutor for the critic agent and provides:
    - Structured CritiqueResult outputs
    - Automatic parsing of critique responses
    - Section-specific convenience methods
    - Score recording to blackboard

    Usage:
        critic = CriticIntegration(blackboard, metrics)
        result = critic.critique_creative_vision(threshold=0.85)

        if result.passed:
            blackboard.lock(result.section_id, "Approved by critic")
        else:
            # Handle revision
            for issue in result.issues:
                print(f"Issue: {issue}")
    """

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
            llm_executor: Optional callable for actual LLM execution.
                         If None, uses stubbed execution.
                         Signature: (prompt: str) -> str
        """
        self.blackboard = blackboard
        self.metrics = metrics
        self.llm_executor = llm_executor

        # Load critique patterns for scoring
        self.critique_patterns = self._load_critique_patterns()

        # Get expert executor for critic
        self.executor = get_expert_executor("critic", blackboard, metrics)

        logger.info("CriticIntegration initialized")

    def _load_critique_patterns(self) -> dict:
        """Load the critique_patterns.yaml expertise file."""
        patterns_path = Path(__file__).parent.parent / "expertise" / "critique_patterns.yaml"

        if not patterns_path.exists():
            logger.warning(f"Critique patterns not found at {patterns_path}")
            return {}

        try:
            with open(patterns_path, "r", encoding="utf-8") as f:
                patterns = yaml.safe_load(f)
                logger.debug(f"Loaded critique patterns from {patterns_path}")
                return patterns
        except Exception as e:
            logger.error(f"Failed to load critique patterns: {e}")
            return {}

    def critique_section(
        self,
        section_id: SectionID,
        threshold: float = 0.85
    ) -> CritiqueResult:
        """
        Run critic on a specific section and return structured result.

        This method:
        1. Loads the section content from blackboard
        2. Executes critic evaluation (via ExpertExecutor)
        3. Parses the response to extract score and feedback
        4. Updates blackboard section score
        5. Returns structured CritiqueResult

        Args:
            section_id: Which section to critique
            threshold: Minimum score to pass (0.0-1.0)

        Returns:
            CritiqueResult with score, feedback, issues, and suggestions

        Raises:
            ValueError: If section is empty or invalid
        """
        logger.info(f"Critiquing {section_id.value} with threshold {threshold}")

        # Validate section has content
        section_content = self.blackboard.read(section_id)
        if not section_content:
            logger.warning(f"Section {section_id.value} is empty")
            return CritiqueResult(
                section_id=section_id,
                score=0.0,
                passed=False,
                feedback="Section is empty - no content to critique",
                issues=["Section has no content"],
                suggestions=["Populate section before critiquing"]
            )

        # Get the review type based on section
        review_type = self._get_review_type(section_id)
        logger.debug(f"Review type for {section_id.value}: {review_type}")

        # Execute critic (this would call LLM in production)
        # For now, we'll use the executor's stubbed execution
        try:
            result = self.executor.execute_step("build")

            # Parse the LLM response
            parsed = self.parse_critique_response(
                response=str(result.get("output", {})),
                section_id=section_id,
                threshold=threshold
            )

            # Update blackboard with score
            if parsed.score > 0:
                section = self.blackboard.sections[section_id]
                if section.current:
                    section.current.score = parsed.score
                    logger.info(
                        f"Updated {section_id.value} score to {parsed.score:.2f}"
                    )

            # Record metrics
            phase = self._section_to_phase(section_id)
            self.metrics.record_score(phase, parsed.score)

            logger.info(
                f"Critique complete: {section_id.value} scored {parsed.score:.2f} "
                f"(threshold: {threshold}, passed: {parsed.passed})"
            )

            return parsed

        except Exception as e:
            logger.error(f"Error during critique: {e}", exc_info=True)
            return CritiqueResult(
                section_id=section_id,
                score=0.0,
                passed=False,
                feedback=f"Critique failed: {str(e)}",
                issues=[f"Execution error: {str(e)}"],
                suggestions=["Check logs for details"]
            )

    def critique_creative_vision(self, threshold: float = 0.85) -> CritiqueResult:
        """
        Critique §2 creative vision.

        Evaluates artistic coherence, creative alignment, and innovation
        appropriateness according to critique_patterns.yaml.

        Args:
            threshold: Minimum score to pass (default 0.85)

        Returns:
            CritiqueResult for creative vision section
        """
        logger.info("Critiquing creative vision")
        return self.critique_section(SectionID.CREATIVE_VISION, threshold)

    def critique_technical_approach(self, threshold: float = 0.85) -> CritiqueResult:
        """
        Critique §3 technical approach.

        Evaluates technical feasibility, implementation clarity, and
        algorithm selection according to critique_patterns.yaml.

        Args:
            threshold: Minimum score to pass (default 0.85)

        Returns:
            CritiqueResult for technical approach section
        """
        logger.info("Critiquing technical approach")
        return self.critique_section(SectionID.TECHNICAL_APPROACH, threshold)

    def critique_network_design(self, threshold: float = 0.90) -> CritiqueResult:
        """
        Critique §5 network design.

        Evaluates network architecture, implementation clarity,
        and alignment with technical and creative specs.

        Note: Network design has a higher default threshold (0.90)
        because it's the final design before build.

        Args:
            threshold: Minimum score to pass (default 0.90)

        Returns:
            CritiqueResult for network design section
        """
        logger.info("Critiquing network design")
        return self.critique_section(SectionID.NETWORK_DESIGN, threshold)

    def parse_critique_response(
        self,
        response: str,
        section_id: SectionID,
        threshold: float
    ) -> CritiqueResult:
        """
        Parse LLM response to extract score and feedback.

        Looks for structured patterns in the critique response:
        - Overall score (as decimal or percentage)
        - Criteria scores (artistic_coherence, technical_feasibility, etc.)
        - Issues list
        - Suggestions
        - Blocking issues

        Args:
            response: Raw text response from LLM
            section_id: Which section was critiqued
            threshold: The threshold used for pass/fail

        Returns:
            CritiqueResult with extracted information
        """
        logger.debug(f"Parsing critique response for {section_id.value}")

        # Extract overall score
        score = self._extract_score(response)

        # Extract criteria scores
        criteria_scores = self._extract_criteria_scores(response)

        # Extract issues and suggestions
        issues = self._extract_issues(response)
        suggestions = self._extract_suggestions(response)
        blocking_issues = self._extract_blocking_issues(response)

        # Extract feedback summary
        feedback = self._extract_feedback(response)

        # Determine pass/fail
        passed = score >= threshold and len(blocking_issues) == 0

        result = CritiqueResult(
            section_id=section_id,
            score=score,
            passed=passed,
            feedback=feedback,
            issues=issues,
            suggestions=suggestions,
            criteria_scores=criteria_scores,
            blocking_issues=blocking_issues
        )

        logger.debug(
            f"Parsed result: score={score:.2f}, "
            f"passed={passed}, issues={len(issues)}, "
            f"blocking={len(blocking_issues)}"
        )

        return result

    def _extract_score(self, response: str) -> float:
        """
        Extract overall score from response.

        Looks for patterns like:
        - "Overall Score: 0.85"
        - "Score: 85%"
        - "overall_score: 0.85"
        """
        # Try decimal format (0.XX)
        decimal_pattern = r"overall[_\s]*score[:\s]+(\d+\.\d+)"
        match = re.search(decimal_pattern, response, re.IGNORECASE)
        if match:
            return float(match.group(1))

        # Try percentage format (XX%)
        percent_pattern = r"overall[_\s]*score[:\s]+(\d+)%"
        match = re.search(percent_pattern, response, re.IGNORECASE)
        if match:
            return float(match.group(1)) / 100.0

        # Try standalone score field
        score_pattern = r"score[:\s]+(\d+\.\d+)"
        match = re.search(score_pattern, response, re.IGNORECASE)
        if match:
            return float(match.group(1))

        logger.warning("Could not extract score from response, defaulting to 0.0")
        return 0.0

    def _extract_criteria_scores(self, response: str) -> dict[str, float]:
        """Extract per-criterion scores."""
        criteria_scores = {}

        # Known criteria from critique_patterns.yaml
        criteria = [
            "artistic_coherence",
            "technical_feasibility",
            "implementation_clarity",
            "creative_alignment",
            "innovation_appropriateness"
        ]

        for criterion in criteria:
            # Look for "criterion: score" pattern
            pattern = rf"{criterion}[:\s]+(\d+\.\d+)"
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                criteria_scores[criterion] = float(match.group(1))

        return criteria_scores

    def _extract_issues(self, response: str) -> list[str]:
        """Extract issues list from response."""
        issues = []

        # Look for "Issues:" section
        issues_section = re.search(
            r"issues[:\s]+(.+?)(?=\n\n|\n[A-Z]|$)",
            response,
            re.IGNORECASE | re.DOTALL
        )

        if issues_section:
            issues_text = issues_section.group(1)
            # Extract bulleted or numbered items
            issue_items = re.findall(r"[-*•]\s*(.+?)(?=\n[-*•]|\n\n|$)", issues_text)
            issues.extend([item.strip() for item in issue_items if item.strip()])

        return issues

    def _extract_suggestions(self, response: str) -> list[str]:
        """Extract suggestions list from response."""
        suggestions = []

        # Look for "Suggestions:" or "Recommended:" section
        suggestions_section = re.search(
            r"(suggestions?|recommended?)[:\s]+(.+?)(?=\n\n|\n[A-Z]|$)",
            response,
            re.IGNORECASE | re.DOTALL
        )

        if suggestions_section:
            suggestions_text = suggestions_section.group(2)
            # Extract bulleted or numbered items
            suggestion_items = re.findall(
                r"[-*•]\s*(.+?)(?=\n[-*•]|\n\n|$)",
                suggestions_text
            )
            suggestions.extend(
                [item.strip() for item in suggestion_items if item.strip()]
            )

        return suggestions

    def _extract_blocking_issues(self, response: str) -> list[str]:
        """Extract blocking issues from response."""
        blocking = []

        # Look for "Blocking:" or "Blocking Issues:" section
        blocking_section = re.search(
            r"blocking[_\s]*issues?[:\s]+(.+?)(?=\n\n|\n[A-Z]|$)",
            response,
            re.IGNORECASE | re.DOTALL
        )

        if blocking_section:
            blocking_text = blocking_section.group(1)
            # Extract bulleted or numbered items
            blocking_items = re.findall(
                r"[-*•]\s*(.+?)(?=\n[-*•]|\n\n|$)",
                blocking_text
            )
            blocking.extend(
                [item.strip() for item in blocking_items if item.strip()]
            )

        # Also check for high severity issues marked as blocking
        for issue in self._extract_issues(response):
            if "[high]" in issue.lower() or "blocking" in issue.lower():
                if issue not in blocking:
                    blocking.append(issue)

        return blocking

    def _extract_feedback(self, response: str) -> str:
        """Extract feedback summary from response."""
        # Look for "Feedback:" section
        feedback_section = re.search(
            r"feedback[:\s]+(.+?)(?=\n\n|\n[A-Z]{2,}|$)",
            response,
            re.IGNORECASE | re.DOTALL
        )

        if feedback_section:
            return feedback_section.group(1).strip()

        # If no specific feedback section, use first paragraph
        paragraphs = response.split("\n\n")
        for para in paragraphs:
            if len(para.strip()) > 50:  # Meaningful paragraph
                return para.strip()

        return "No detailed feedback provided"

    def _get_review_type(self, section_id: SectionID) -> str:
        """Map section ID to review type."""
        mapping = {
            SectionID.CREATIVE_VISION: "creative_review",
            SectionID.TECHNICAL_APPROACH: "technical_review",
            SectionID.NETWORK_DESIGN: "final_approval"
        }
        return mapping.get(section_id, "general_review")

    def _section_to_phase(self, section_id: SectionID) -> str:
        """Map section ID to phase name for metrics."""
        mapping = {
            SectionID.CREATIVE_VISION: "creative",
            SectionID.TECHNICAL_APPROACH: "technical",
            SectionID.NETWORK_DESIGN: "design"
        }
        return mapping.get(section_id, "unknown")

    def get_quality_thresholds(self, preset: str = "standard") -> dict:
        """
        Get quality thresholds from critique_patterns.yaml.

        Args:
            preset: Which preset to use ("quick_draft", "standard", "excellence")

        Returns:
            Dict with thresholds for each phase
        """
        if not self.critique_patterns:
            logger.warning("Critique patterns not loaded, using defaults")
            return {
                "creative": 0.85,
                "technical": 0.85,
                "design": 0.90
            }

        presets = self.critique_patterns.get(
            "workflow_quality_thresholds", {}
        ).get("presets", {})

        preset_config = presets.get(preset, presets.get("standard", {}))

        return {
            "creative": preset_config.get("creative", 0.85),
            "technical": preset_config.get("technical", 0.85),
            "design": preset_config.get("design", 0.90)
        }


__all__ = [
    "CriticIntegration",
    "CritiqueResult",
]

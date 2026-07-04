"""
Orchestrator: Manages workflow phase transitions and routes work to experts.

The orchestrator is the conductor that:
- Reads blackboard state to determine next action
- Routes work to appropriate experts with context
- Manages phase transitions through the workflow state machine
- Handles blocking issues and phase reopening
- Enforces quality thresholds and convergence detection

State Machine Flow:
    INIT -> CREATIVE -> TECHNICAL -> RESOURCES -> DESIGN -> BUILD -> COMPLETE

    With critic reviews after each major phase and potential phase reopening
    based on blocking issues.

See docs/ARCHITECTURE.md and docs/AGENT_INTERFACE.md for detailed specifications.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Literal
import logging

from .blackboard import Blackboard, Phase, SectionID, BlockingIssue
from .metrics import MetricsCollector


logger = logging.getLogger(__name__)


# Quality threshold presets
QUALITY_PRESETS = {
    "quick_draft": {
        "creative": 0.70,
        "technical": 0.70,
        "design": 0.80
    },
    "standard": {
        "creative": 0.85,
        "technical": 0.85,
        "design": 0.90
    },
    "excellence": {
        "creative": 0.90,
        "technical": 0.90,
        "design": 0.95
    }
}


@dataclass
class StrategyConfig:
    """Configuration for workflow strategy execution."""
    preset: Literal["quick_draft", "standard", "excellence"] = "standard"
    thresholds: dict[str, float] = field(default_factory=dict)
    max_iterations: int = 3
    convergence_window: int = 2
    minimum_improvement: float = 0.01

    def __post_init__(self):
        """Set thresholds from preset if not explicitly provided."""
        if not self.thresholds:
            self.thresholds = QUALITY_PRESETS[self.preset].copy()


class ActionType(Enum):
    """Types of actions the orchestrator can take."""
    ACTIVATE_EXPERT = "activate_expert"
    REQUEST_CRITIC_REVIEW = "request_critic_review"
    ADVANCE_PHASE = "advance_phase"
    REOPEN_PHASE = "reopen_phase"
    COMPLETE_WORKFLOW = "complete_workflow"
    WAIT_FOR_USER = "wait_for_user"
    HANDLE_BLOCKING_ISSUE = "handle_blocking_issue"


@dataclass
class OrchestratorAction:
    """
    An action decision made by the orchestrator.

    Specifies what should happen next in the workflow.
    """
    action: ActionType
    reasoning: str

    # For ACTIVATE_EXPERT
    expert_id: Optional[str] = None
    task_description: Optional[str] = None
    context_sections: list[SectionID] = field(default_factory=list)

    # For ADVANCE_PHASE or REOPEN_PHASE
    target_phase: Optional[Phase] = None
    sections_to_lock: list[SectionID] = field(default_factory=list)
    sections_to_unlock: list[SectionID] = field(default_factory=list)

    # For REQUEST_CRITIC_REVIEW
    section_to_review: Optional[SectionID] = None
    review_focus: Optional[str] = None

    # For HANDLE_BLOCKING_ISSUE
    issue_id: Optional[str] = None
    resolution_strategy: Optional[str] = None


class WorkflowOrchestrator:
    """
    Orchestrates the workflow state machine and expert routing.

    The orchestrator is stateless - all state is stored in the blackboard.
    It reads blackboard state and decides what action to take next.

    Usage:
        orchestrator = WorkflowOrchestrator(blackboard, metrics, config)

        while not orchestrator.is_workflow_complete():
            action = orchestrator.determine_next_action()

            if action.action == ActionType.ACTIVATE_EXPERT:
                context = orchestrator.route_to_expert(action.expert_id)
                # ... call expert with context ...
                orchestrator.handle_expert_output(action.expert_id, expert_output)

            elif action.action == ActionType.ADVANCE_PHASE:
                orchestrator.advance_phase(action.target_phase)
    """

    def __init__(
        self,
        blackboard: Blackboard,
        metrics: MetricsCollector,
        strategy_config: StrategyConfig
    ):
        """
        Initialize the orchestrator.

        Args:
            blackboard: The central state document
            metrics: Metrics collector for tracking execution
            strategy_config: Quality thresholds and execution parameters
        """
        self.blackboard = blackboard
        self.metrics = metrics
        self.config = strategy_config

        # Track phase iteration counts for convergence detection
        self.phase_iterations: dict[Phase, int] = {}

        # Track score history per phase for convergence
        self.phase_score_history: dict[Phase, list[float]] = {}

    def determine_next_action(self) -> OrchestratorAction:
        """
        Analyze blackboard state and determine what action to take next.

        This is the main decision-making function of the orchestrator.
        It examines:
        - Current phase
        - Section completion status
        - Blocking issues
        - Quality scores
        - Iteration counts

        Returns:
            An OrchestratorAction describing what to do next
        """
        current_phase = self.blackboard.current_phase

        logger.info(f"Determining next action for phase: {current_phase.value}")

        # Check for blocking issues first
        unresolved_issues = self.blackboard.get_unresolved_issues()
        if unresolved_issues:
            return self._handle_blocking_issues(unresolved_issues)

        # Handle each phase
        if current_phase == Phase.INIT:
            return self._handle_init_phase()

        elif current_phase == Phase.CREATIVE:
            return self._handle_creative_phase()

        elif current_phase == Phase.TECHNICAL:
            return self._handle_technical_phase()

        elif current_phase == Phase.RESOURCES:
            return self._handle_resources_phase()

        elif current_phase == Phase.DESIGN:
            return self._handle_design_phase()

        elif current_phase == Phase.BUILD:
            return self._handle_build_phase()

        elif current_phase == Phase.COMPLETE:
            return OrchestratorAction(
                action=ActionType.COMPLETE_WORKFLOW,
                reasoning="Workflow is complete"
            )

        else:
            raise ValueError(f"Unknown phase: {current_phase}")

    def _handle_init_phase(self) -> OrchestratorAction:
        """Handle INIT phase - ensure requirements are captured."""
        req_section = self.blackboard.read(SectionID.REQUIREMENTS)

        if not req_section or not req_section.get("original_prompt"):
            return OrchestratorAction(
                action=ActionType.WAIT_FOR_USER,
                reasoning="Waiting for user requirements (§1)"
            )

        # Requirements captured, advance to creative
        return OrchestratorAction(
            action=ActionType.ADVANCE_PHASE,
            target_phase=Phase.CREATIVE,
            reasoning="Requirements captured in §1, ready for creative vision"
        )

    def _handle_creative_phase(self) -> OrchestratorAction:
        """Handle CREATIVE phase - creative expert + critic review."""
        creative_section = self.blackboard.sections[SectionID.CREATIVE_VISION]
        validation_section = self.blackboard.read(SectionID.VALIDATION_HISTORY)

        # Check if we need to activate creative expert
        if not creative_section.current:
            return OrchestratorAction(
                action=ActionType.ACTIVATE_EXPERT,
                expert_id="creative_expert",
                task_description="Generate creative vision based on requirements",
                context_sections=[SectionID.REQUIREMENTS],
                reasoning="§2 is empty, need creative expert to generate vision"
            )

        # Check if we need critic review
        needs_review = self._needs_critic_review(
            section_id=SectionID.CREATIVE_VISION,
            phase="creative"
        )

        if needs_review:
            return OrchestratorAction(
                action=ActionType.REQUEST_CRITIC_REVIEW,
                section_to_review=SectionID.CREATIVE_VISION,
                review_focus="creative",
                reasoning="§2 generated, needs critic review for quality validation"
            )

        # Check quality threshold
        score = creative_section.current.score
        threshold = self.config.thresholds["creative"]

        if score is None:
            return OrchestratorAction(
                action=ActionType.REQUEST_CRITIC_REVIEW,
                section_to_review=SectionID.CREATIVE_VISION,
                review_focus="creative",
                reasoning="§2 has no quality score, needs critic review"
            )

        if score < threshold:
            # Check if we've hit max iterations or convergence
            if self._should_stop_iterating(Phase.CREATIVE, score):
                return OrchestratorAction(
                    action=ActionType.ADVANCE_PHASE,
                    target_phase=Phase.TECHNICAL,
                    sections_to_lock=[SectionID.CREATIVE_VISION],
                    reasoning=f"Creative score {score:.2f} below threshold {threshold:.2f}, "
                             f"but max iterations reached or convergence detected. Proceeding."
                )

            # Request revision
            return OrchestratorAction(
                action=ActionType.ACTIVATE_EXPERT,
                expert_id="creative_expert",
                task_description="Revise creative vision based on critic feedback",
                context_sections=[SectionID.REQUIREMENTS, SectionID.VALIDATION_HISTORY],
                reasoning=f"Creative score {score:.2f} below threshold {threshold:.2f}, "
                         f"requesting revision (iteration {self._get_iteration_count(Phase.CREATIVE) + 1})"
            )

        # Quality threshold met, advance
        return OrchestratorAction(
            action=ActionType.ADVANCE_PHASE,
            target_phase=Phase.TECHNICAL,
            sections_to_lock=[SectionID.CREATIVE_VISION],
            reasoning=f"Creative vision passed quality threshold ({score:.2f} >= {threshold:.2f})"
        )

    def _handle_technical_phase(self) -> OrchestratorAction:
        """Handle TECHNICAL phase - CG expert + critic review."""
        technical_section = self.blackboard.sections[SectionID.TECHNICAL_APPROACH]

        # Check if we need to activate CG expert
        if not technical_section.current:
            return OrchestratorAction(
                action=ActionType.ACTIVATE_EXPERT,
                expert_id="cg_expert",
                task_description="Define technical approach based on creative vision",
                context_sections=[SectionID.REQUIREMENTS, SectionID.CREATIVE_VISION],
                reasoning="§3 is empty, need CG expert to define technical approach"
            )

        # Check if we need critic review
        needs_review = self._needs_critic_review(
            section_id=SectionID.TECHNICAL_APPROACH,
            phase="technical"
        )

        if needs_review:
            return OrchestratorAction(
                action=ActionType.REQUEST_CRITIC_REVIEW,
                section_to_review=SectionID.TECHNICAL_APPROACH,
                review_focus="technical",
                reasoning="§3 generated, needs critic review for quality validation"
            )

        # Check quality threshold
        score = technical_section.current.score
        threshold = self.config.thresholds["technical"]

        if score is None:
            return OrchestratorAction(
                action=ActionType.REQUEST_CRITIC_REVIEW,
                section_to_review=SectionID.TECHNICAL_APPROACH,
                review_focus="technical",
                reasoning="§3 has no quality score, needs critic review"
            )

        if score < threshold:
            if self._should_stop_iterating(Phase.TECHNICAL, score):
                return OrchestratorAction(
                    action=ActionType.ADVANCE_PHASE,
                    target_phase=Phase.RESOURCES,
                    sections_to_lock=[SectionID.TECHNICAL_APPROACH],
                    reasoning=f"Technical score {score:.2f} below threshold {threshold:.2f}, "
                             f"but max iterations reached or convergence detected. Proceeding."
                )

            return OrchestratorAction(
                action=ActionType.ACTIVATE_EXPERT,
                expert_id="cg_expert",
                task_description="Revise technical approach based on critic feedback",
                context_sections=[
                    SectionID.REQUIREMENTS,
                    SectionID.CREATIVE_VISION,
                    SectionID.VALIDATION_HISTORY
                ],
                reasoning=f"Technical score {score:.2f} below threshold {threshold:.2f}, "
                         f"requesting revision (iteration {self._get_iteration_count(Phase.TECHNICAL) + 1})"
            )

        # Quality threshold met, advance
        return OrchestratorAction(
            action=ActionType.ADVANCE_PHASE,
            target_phase=Phase.RESOURCES,
            sections_to_lock=[SectionID.TECHNICAL_APPROACH],
            reasoning=f"Technical approach passed quality threshold ({score:.2f} >= {threshold:.2f})"
        )

    def _handle_resources_phase(self) -> OrchestratorAction:
        """Handle RESOURCES phase - query knowledge base for operators/patterns."""
        resources_section = self.blackboard.read(SectionID.AVAILABLE_RESOURCES)

        if not resources_section or not resources_section.get("operators"):
            # This would typically be handled by a knowledge base query agent
            # For now, we just check if resources are populated
            return OrchestratorAction(
                action=ActionType.ACTIVATE_EXPERT,
                expert_id="kb_query_agent",
                task_description="Query knowledge base for relevant operators and patterns",
                context_sections=[
                    SectionID.REQUIREMENTS,
                    SectionID.CREATIVE_VISION,
                    SectionID.TECHNICAL_APPROACH
                ],
                reasoning="§4 is empty, need to populate available resources from KB"
            )

        # Resources populated, advance to design
        return OrchestratorAction(
            action=ActionType.ADVANCE_PHASE,
            target_phase=Phase.DESIGN,
            sections_to_lock=[SectionID.AVAILABLE_RESOURCES],
            reasoning="Resources populated in §4, ready for network design"
        )

    def _handle_design_phase(self) -> OrchestratorAction:
        """Handle DESIGN phase - TD Designer + multi-perspective review."""
        design_section = self.blackboard.sections[SectionID.NETWORK_DESIGN]

        # Check if we need to activate TD Designer
        if not design_section.current:
            return OrchestratorAction(
                action=ActionType.ACTIVATE_EXPERT,
                expert_id="td_designer",
                task_description="Design network based on creative vision and technical approach",
                context_sections=[
                    SectionID.REQUIREMENTS,
                    SectionID.CREATIVE_VISION,
                    SectionID.TECHNICAL_APPROACH,
                    SectionID.AVAILABLE_RESOURCES
                ],
                reasoning="§5 is empty, need TD Designer to create network design"
            )

        # Check if we need critic review (multi-perspective for design)
        needs_review = self._needs_critic_review(
            section_id=SectionID.NETWORK_DESIGN,
            phase="design"
        )

        if needs_review:
            return OrchestratorAction(
                action=ActionType.REQUEST_CRITIC_REVIEW,
                section_to_review=SectionID.NETWORK_DESIGN,
                review_focus="design",
                reasoning="§5 generated, needs multi-perspective critic review"
            )

        # Check quality threshold
        score = design_section.current.score
        threshold = self.config.thresholds["design"]

        if score is None:
            return OrchestratorAction(
                action=ActionType.REQUEST_CRITIC_REVIEW,
                section_to_review=SectionID.NETWORK_DESIGN,
                review_focus="design",
                reasoning="§5 has no quality score, needs critic review"
            )

        if score < threshold:
            if self._should_stop_iterating(Phase.DESIGN, score):
                return OrchestratorAction(
                    action=ActionType.ADVANCE_PHASE,
                    target_phase=Phase.BUILD,
                    sections_to_lock=[SectionID.NETWORK_DESIGN],
                    reasoning=f"Design score {score:.2f} below threshold {threshold:.2f}, "
                             f"but max iterations reached or convergence detected. Proceeding."
                )

            return OrchestratorAction(
                action=ActionType.ACTIVATE_EXPERT,
                expert_id="td_designer",
                task_description="Revise network design based on critic feedback",
                context_sections=[
                    SectionID.REQUIREMENTS,
                    SectionID.CREATIVE_VISION,
                    SectionID.TECHNICAL_APPROACH,
                    SectionID.AVAILABLE_RESOURCES,
                    SectionID.VALIDATION_HISTORY
                ],
                reasoning=f"Design score {score:.2f} below threshold {threshold:.2f}, "
                         f"requesting revision (iteration {self._get_iteration_count(Phase.DESIGN) + 1})"
            )

        # Quality threshold met, advance
        return OrchestratorAction(
            action=ActionType.ADVANCE_PHASE,
            target_phase=Phase.BUILD,
            sections_to_lock=[SectionID.NETWORK_DESIGN],
            reasoning=f"Network design passed quality threshold ({score:.2f} >= {threshold:.2f})"
        )

    def _handle_build_phase(self) -> OrchestratorAction:
        """Handle BUILD phase - construct actual TOE file."""
        build_section = self.blackboard.read(SectionID.BUILD_ARTIFACTS)

        if not build_section or not build_section.get("toe_path"):
            return OrchestratorAction(
                action=ActionType.ACTIVATE_EXPERT,
                expert_id="network_builder",
                task_description="Build TOE file from network design JSON",
                context_sections=[SectionID.NETWORK_DESIGN],
                reasoning="§7 is empty, need to build TOE file from design"
            )

        # Check if build was successful
        if build_section.get("build_status") == "success":
            return OrchestratorAction(
                action=ActionType.ADVANCE_PHASE,
                target_phase=Phase.COMPLETE,
                reasoning="TOE file built successfully, workflow complete"
            )
        else:
            # Build failed, create blocking issue
            error_msg = build_section.get("error_message", "Unknown build error")
            return OrchestratorAction(
                action=ActionType.HANDLE_BLOCKING_ISSUE,
                reasoning=f"Build failed: {error_msg}"
            )

    def _handle_blocking_issues(
        self,
        issues: list[BlockingIssue]
    ) -> OrchestratorAction:
        """
        Handle blocking issues by classifying and routing appropriately.

        Blocking issues can trigger phase reopening if needed.
        """
        # Sort by severity
        high_severity = [i for i in issues if i.severity == "high"]
        issue = high_severity[0] if high_severity else issues[0]

        classification = issue.classification

        # Determine which phase to reopen based on classification
        if classification == "creative":
            return OrchestratorAction(
                action=ActionType.REOPEN_PHASE,
                target_phase=Phase.CREATIVE,
                sections_to_unlock=[SectionID.CREATIVE_VISION],
                issue_id=issue.id,
                reasoning=f"Reopening creative phase due to blocking issue: {issue.description}"
            )

        elif classification == "technical":
            return OrchestratorAction(
                action=ActionType.REOPEN_PHASE,
                target_phase=Phase.TECHNICAL,
                sections_to_unlock=[SectionID.TECHNICAL_APPROACH],
                issue_id=issue.id,
                reasoning=f"Reopening technical phase due to blocking issue: {issue.description}"
            )

        elif classification == "design":
            return OrchestratorAction(
                action=ActionType.REOPEN_PHASE,
                target_phase=Phase.DESIGN,
                sections_to_unlock=[SectionID.NETWORK_DESIGN],
                issue_id=issue.id,
                reasoning=f"Reopening design phase due to blocking issue: {issue.description}"
            )

        else:
            # Generic blocking issue - try to resolve without phase change
            return OrchestratorAction(
                action=ActionType.HANDLE_BLOCKING_ISSUE,
                issue_id=issue.id,
                resolution_strategy="manual_intervention",
                reasoning=f"Unclassified blocking issue requires attention: {issue.description}"
            )

    def _needs_critic_review(
        self,
        section_id: SectionID,
        phase: str
    ) -> bool:
        """
        Determine if a section needs critic review.

        A section needs review if:
        - It has content but no score
        - It was just written in this phase
        """
        section = self.blackboard.sections[section_id]
        if not section.current:
            return False

        # Check if current version has a score
        if section.current.score is None:
            return True

        # Check validation history to see if this version was reviewed
        validation = self.blackboard.read(SectionID.VALIDATION_HISTORY)
        if not validation or not validation.get("reviews"):
            return True

        # Look for a review of the current version
        current_version = section.version_count - 1
        reviews = validation.get("reviews", [])

        for review in reviews:
            if (review.get("section") == section_id.value and
                review.get("version") == current_version):
                return False

        return True

    def _should_stop_iterating(self, phase: Phase, current_score: float) -> bool:
        """
        Check if we should stop iterating on a phase.

        Stop if:
        - We've reached max_iterations
        - We've converged (no improvement in convergence_window iterations)
        """
        iteration_count = self._get_iteration_count(phase)

        # Check max iterations
        if iteration_count >= self.config.max_iterations:
            logger.info(f"Phase {phase.value} reached max iterations ({self.config.max_iterations})")
            return True

        # Check convergence
        score_history = self.phase_score_history.get(phase, [])
        if len(score_history) >= self.config.convergence_window:
            recent_scores = score_history[-self.config.convergence_window:]
            max_improvement = max(recent_scores) - min(recent_scores)

            if max_improvement < self.config.minimum_improvement:
                logger.info(
                    f"Phase {phase.value} converged "
                    f"(improvement {max_improvement:.3f} < {self.config.minimum_improvement})"
                )
                return True

        return False

    def _get_iteration_count(self, phase: Phase) -> int:
        """Get the current iteration count for a phase."""
        return self.phase_iterations.get(phase, 0)

    def route_to_expert(self, expert_id: str) -> dict:
        """
        Prepare context for an expert based on their access permissions.

        Args:
            expert_id: The expert to route to

        Returns:
            A context dict containing relevant blackboard sections and metadata
        """
        logger.info(f"Routing to expert: {expert_id}")

        context = self.blackboard.get_context_for_expert(expert_id)

        # Add strategy config for experts that need it
        context["strategy_config"] = {
            "preset": self.config.preset,
            "thresholds": self.config.thresholds,
            "max_iterations": self.config.max_iterations
        }

        # Add iteration count for the current phase
        current_phase = self.blackboard.current_phase
        context["current_state"]["phase_iteration"] = self._get_iteration_count(current_phase)

        return context

    def handle_expert_output(
        self,
        expert_id: str,
        output: dict
    ) -> None:
        """
        Process output from an expert and update blackboard.

        Args:
            expert_id: Which expert produced this output
            output: The expert's output (format depends on expert type)
        """
        logger.info(f"Handling output from expert: {expert_id}")

        current_phase = self.blackboard.current_phase

        # Map expert to section they write to
        expert_section_map = {
            "creative_expert": SectionID.CREATIVE_VISION,
            "cg_expert": SectionID.TECHNICAL_APPROACH,
            "td_designer": SectionID.NETWORK_DESIGN,
            "critic": SectionID.VALIDATION_HISTORY,
            "network_builder": SectionID.BUILD_ARTIFACTS,
            "kb_query_agent": SectionID.AVAILABLE_RESOURCES
        }

        target_section = expert_section_map.get(expert_id)
        if not target_section:
            logger.warning(f"Unknown expert {expert_id}, cannot map to section")
            return

        # Extract score if present
        score = output.get("score") or output.get("quality_score")

        # Write to blackboard
        self.blackboard.write(
            section_id=target_section,
            content=output,
            author=expert_id,
            score=score
        )

        # Track score for convergence detection
        if score is not None:
            if current_phase not in self.phase_score_history:
                self.phase_score_history[current_phase] = []
            self.phase_score_history[current_phase].append(score)

        # Increment iteration count
        if current_phase not in self.phase_iterations:
            self.phase_iterations[current_phase] = 0
        self.phase_iterations[current_phase] += 1

        # Record metrics
        if score is not None:
            self.metrics.record_score(current_phase.value, score)
        self.metrics.record_iteration(current_phase.value)

        logger.info(
            f"Expert {expert_id} wrote to {target_section.value} "
            f"(score: {score}, iteration: {self.phase_iterations[current_phase]})"
        )

    def advance_phase(self, target_phase: Phase) -> None:
        """
        Advance workflow to the next phase.

        Args:
            target_phase: The phase to advance to
        """
        old_phase = self.blackboard.current_phase
        logger.info(f"Advancing phase: {old_phase.value} -> {target_phase.value}")

        # End metrics collection for old phase
        self.metrics.end_phase(old_phase.value)

        # Update blackboard phase
        self.blackboard.set_phase(target_phase)

        # Start metrics collection for new phase
        self.metrics.start_phase(target_phase.value)

    def reopen_phase(self, phase: Phase, reason: str) -> None:
        """
        Reopen a previously completed phase due to blocking issues.

        Args:
            phase: The phase to reopen
            reason: Why the phase is being reopened
        """
        logger.info(f"Reopening phase {phase.value}: {reason}")

        # Record troubleshooting event
        self.metrics.record_troubleshooting(
            event_type="phase_reopen",
            phase=phase.value,
            description=reason
        )

        # Unlock the relevant section
        section_map = {
            Phase.CREATIVE: SectionID.CREATIVE_VISION,
            Phase.TECHNICAL: SectionID.TECHNICAL_APPROACH,
            Phase.DESIGN: SectionID.NETWORK_DESIGN
        }

        section_to_unlock = section_map.get(phase)
        if section_to_unlock:
            self.blackboard.unlock(section_to_unlock, reason=reason)

        # Set phase back
        self.blackboard.set_phase(phase)

        # Start new metrics collection for reopened phase
        self.metrics.start_phase(phase.value)

    def check_blocking_issues(self) -> list[BlockingIssue]:
        """
        Check for unresolved blocking issues.

        Returns:
            List of unresolved blocking issues
        """
        return self.blackboard.get_unresolved_issues()

    def is_workflow_complete(self) -> bool:
        """
        Check if the workflow is complete.

        Returns:
            True if workflow has reached COMPLETE phase
        """
        return self.blackboard.current_phase == Phase.COMPLETE

    def get_status_summary(self) -> dict:
        """
        Get a summary of current workflow status.

        Returns:
            Dict with phase, iterations, scores, issues, etc.
        """
        current_phase = self.blackboard.current_phase
        unresolved_issues = self.blackboard.get_unresolved_issues()

        return {
            "phase": current_phase.value,
            "iteration": self.blackboard.iteration,
            "phase_iterations": {
                phase.value: count
                for phase, count in self.phase_iterations.items()
            },
            "phase_scores": {
                phase.value: scores
                for phase, scores in self.phase_score_history.items()
            },
            "blocking_issues": [
                {
                    "id": issue.id,
                    "section": issue.section.value,
                    "severity": issue.severity,
                    "description": issue.description
                }
                for issue in unresolved_issues
            ],
            "sections_status": {
                section.id.value: {
                    "version_count": section.version_count,
                    "locked": section.locked,
                    "current_score": section.current.score if section.current else None
                }
                for section in self.blackboard.sections.values()
            },
            "quality_thresholds": self.config.thresholds
        }

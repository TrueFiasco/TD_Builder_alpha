"""
Workflow Recorder: Comprehensive logging for META_AGENTIC workflows.

This module provides utilities for recording every aspect of workflow execution:
- Expert prompts and responses
- Context used by each expert
- Threshold checks and scores
- User approvals and feedback
- Blackboard snapshots
- File operations

Usage:
    recorder = WorkflowRecorder(output_dir)
    recorder.record_phase_start("creative", iteration=1)
    recorder.record_expert_context("creative_expert", context)
    recorder.record_expert_response("creative_expert", "plan", response)
    recorder.record_user_approval("creative", approved=True, feedback="Looks good")
    recorder.record_critic_score("creative", score=0.87, threshold=0.85)
    recorder.generate_summary()
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import yaml


@dataclass
class PhaseRecord:
    """Record of a single phase execution."""
    phase: str
    iteration: int
    started_at: str
    completed_at: Optional[str] = None
    expert_id: str = ""
    context_file: str = ""
    prompt_file: str = ""
    response_file: str = ""
    score: Optional[float] = None
    threshold: Optional[float] = None
    passed: Optional[bool] = None
    user_approved: Optional[bool] = None
    user_feedback: str = ""


@dataclass
class WorkflowRecord:
    """Complete record of workflow execution."""
    session_id: str
    started_at: str
    completed_at: Optional[str] = None
    spec_file: str = ""
    output_dir: str = ""
    phases: list[PhaseRecord] = field(default_factory=list)
    final_scores: dict[str, float] = field(default_factory=dict)
    success: bool = False
    errors: list[str] = field(default_factory=list)
    file_operations: list[dict] = field(default_factory=list)


class WorkflowRecorder:
    """
    Records comprehensive logs during workflow execution.

    All records are written to files as the workflow progresses,
    ensuring nothing is lost even if execution is interrupted.
    """

    def __init__(self, output_dir: Path):
        """
        Initialize the recorder.

        Args:
            output_dir: Directory where all logs will be written
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.sequence_num = 0

        # Initialize workflow record
        self.record = WorkflowRecord(
            session_id=self.session_id,
            started_at=datetime.utcnow().isoformat() + "Z",
            output_dir=str(self.output_dir)
        )

        # Current phase tracking
        self.current_phase: Optional[PhaseRecord] = None

    def _next_sequence(self) -> str:
        """Get next sequence number for file naming."""
        self.sequence_num += 1
        return f"{self.sequence_num:02d}"

    def _write_file(self, filename: str, content: str, format_type: str = "text") -> Path:
        """
        Write content to a file and record the operation.

        Args:
            filename: Name of the file (without path)
            content: Content to write
            format_type: "text", "yaml", or "json"

        Returns:
            Path to the written file
        """
        filepath = self.output_dir / filename
        filepath.write_text(content, encoding='utf-8')

        self.record.file_operations.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "operation": "write",
            "file": str(filepath),
            "format": format_type,
            "size": len(content)
        })

        return filepath

    def record_phase_start(self, phase: str, iteration: int = 1, expert_id: str = "") -> PhaseRecord:
        """
        Record the start of a phase.

        Args:
            phase: Phase name (e.g., "creative", "technical", "design")
            iteration: Iteration number within this phase
            expert_id: ID of the expert executing this phase

        Returns:
            The created PhaseRecord
        """
        self.current_phase = PhaseRecord(
            phase=phase,
            iteration=iteration,
            started_at=datetime.utcnow().isoformat() + "Z",
            expert_id=expert_id
        )
        self.record.phases.append(self.current_phase)

        # Log phase start
        print(f"[RECORDER] Phase started: {phase} (iteration {iteration})")
        return self.current_phase

    def record_expert_context(self, expert_id: str, context: dict) -> Path:
        """
        Record the context provided to an expert.

        Args:
            expert_id: ID of the expert
            context: The context dictionary

        Returns:
            Path to the saved context file
        """
        seq = self._next_sequence()
        filename = f"{seq}_{expert_id}_context.yaml"

        content = yaml.dump(context, default_flow_style=False, allow_unicode=True, sort_keys=False)
        filepath = self._write_file(filename, content, "yaml")

        if self.current_phase:
            self.current_phase.context_file = str(filepath)

        print(f"[RECORDER] Context saved: {filename} ({len(content):,} chars)")
        return filepath

    def record_expert_prompt(self, expert_id: str, step: str, prompt: str) -> Path:
        """
        Record a prompt sent to an expert.

        Args:
            expert_id: ID of the expert
            step: Step name (plan, build, self_improve)
            prompt: The full rendered prompt

        Returns:
            Path to the saved prompt file
        """
        seq = self._next_sequence()
        filename = f"{seq}_{expert_id}_{step}_prompt.md"

        filepath = self._write_file(filename, prompt, "text")

        if self.current_phase:
            self.current_phase.prompt_file = str(filepath)

        print(f"[RECORDER] Prompt saved: {filename} ({len(prompt):,} chars)")
        return filepath

    def record_expert_response(self, expert_id: str, step: str, response: str) -> Path:
        """
        Record a response from an expert.

        Args:
            expert_id: ID of the expert
            step: Step name (plan, build, self_improve)
            response: The full response text

        Returns:
            Path to the saved response file
        """
        seq = self._next_sequence()
        filename = f"{seq}_{expert_id}_{step}_response.md"

        filepath = self._write_file(filename, response, "text")

        if self.current_phase:
            self.current_phase.response_file = str(filepath)

        print(f"[RECORDER] Response saved: {filename} ({len(response):,} chars)")
        return filepath

    def record_user_approval(self, phase: str, approved: bool, feedback: str = "") -> Path:
        """
        Record user approval decision at a gate.

        Args:
            phase: Phase name
            approved: Whether the user approved
            feedback: Any feedback provided

        Returns:
            Path to the saved approval file
        """
        seq = self._next_sequence()
        filename = f"{seq}_user_approval_{phase}.json"

        approval_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "phase": phase,
            "approved": approved,
            "feedback": feedback
        }

        content = json.dumps(approval_data, indent=2)
        filepath = self._write_file(filename, content, "json")

        if self.current_phase:
            self.current_phase.user_approved = approved
            self.current_phase.user_feedback = feedback

        status = "APPROVED" if approved else "REJECTED"
        print(f"[RECORDER] User {status}: {phase}")
        if feedback:
            print(f"           Feedback: {feedback}")

        return filepath

    def record_critic_score(self, phase: str, score: float, threshold: float) -> Path:
        """
        Record a critic score for a phase.

        Args:
            phase: Phase name
            score: The critic's score (0.0-1.0)
            threshold: The target threshold

        Returns:
            Path to the saved score file
        """
        seq = self._next_sequence()
        filename = f"{seq}_critic_{phase}.json"

        passed = score >= threshold
        score_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "phase": phase,
            "score": score,
            "threshold": threshold,
            "passed": passed
        }

        content = json.dumps(score_data, indent=2)
        filepath = self._write_file(filename, content, "json")

        if self.current_phase:
            self.current_phase.score = score
            self.current_phase.threshold = threshold
            self.current_phase.passed = passed

        # Store final score
        self.record.final_scores[phase] = score

        status = "PASSED" if passed else "FAILED"
        print(f"[RECORDER] Critic {status}: {phase} (score={score:.2f}, threshold={threshold:.2f})")

        return filepath

    def record_blackboard_snapshot(self, phase: str, blackboard_data: dict) -> Path:
        """
        Record a snapshot of the blackboard state.

        Args:
            phase: Phase name (for filename)
            blackboard_data: The blackboard data dictionary

        Returns:
            Path to the saved snapshot file
        """
        seq = self._next_sequence()
        filename = f"{seq}_blackboard_after_{phase}.yaml"

        content = yaml.dump(blackboard_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        filepath = self._write_file(filename, content, "yaml")

        print(f"[RECORDER] Blackboard snapshot: {filename}")
        return filepath

    def record_error(self, error: str, phase: str = "") -> None:
        """
        Record an error that occurred.

        Args:
            error: Error message
            phase: Phase where error occurred (optional)
        """
        error_msg = f"[{phase}] {error}" if phase else error
        self.record.errors.append(error_msg)
        print(f"[RECORDER] ERROR: {error_msg}")

    def complete_phase(self) -> None:
        """Mark the current phase as complete."""
        if self.current_phase:
            self.current_phase.completed_at = datetime.utcnow().isoformat() + "Z"
            print(f"[RECORDER] Phase completed: {self.current_phase.phase}")

    def generate_summary(self) -> Path:
        """
        Generate a human-readable workflow summary.

        Returns:
            Path to the summary file
        """
        self.record.completed_at = datetime.utcnow().isoformat() + "Z"

        # Determine overall success
        self.record.success = (
            len(self.record.errors) == 0 and
            all(p.passed for p in self.record.phases if p.passed is not None)
        )

        # Build summary markdown
        summary = f"""# Workflow Summary

## Session Information
- **Session ID**: {self.record.session_id}
- **Started**: {self.record.started_at}
- **Completed**: {self.record.completed_at}
- **Success**: {'YES' if self.record.success else 'NO'}
- **Output Directory**: {self.record.output_dir}

## Phase Results

| Phase | Iteration | Score | Threshold | Passed | User Approved |
|-------|-----------|-------|-----------|--------|---------------|
"""

        for phase in self.record.phases:
            score_str = f"{phase.score:.2f}" if phase.score is not None else "N/A"
            threshold_str = f"{phase.threshold:.2f}" if phase.threshold is not None else "N/A"
            passed_str = "YES" if phase.passed else ("NO" if phase.passed is False else "N/A")
            approved_str = "YES" if phase.user_approved else ("NO" if phase.user_approved is False else "N/A")

            summary += f"| {phase.phase} | {phase.iteration} | {score_str} | {threshold_str} | {passed_str} | {approved_str} |\n"

        summary += f"""
## Final Scores

"""
        for phase, score in self.record.final_scores.items():
            summary += f"- **{phase}**: {score:.2f}\n"

        if self.record.errors:
            summary += f"""
## Errors

"""
            for error in self.record.errors:
                summary += f"- {error}\n"

        summary += f"""
## Files Generated

| # | File | Size |
|---|------|------|
"""
        for i, op in enumerate(self.record.file_operations, 1):
            filename = Path(op['file']).name
            summary += f"| {i} | {filename} | {op['size']:,} bytes |\n"

        # Write summary
        summary_path = self._write_file("workflow_summary.md", summary, "text")

        # Also save the complete record as JSON
        record_path = self._write_file(
            "workflow_record.json",
            json.dumps(asdict(self.record), indent=2, default=str),
            "json"
        )

        print(f"[RECORDER] Summary generated: {summary_path}")
        print(f"[RECORDER] Full record: {record_path}")

        return summary_path


def get_recorder(output_dir: Path) -> WorkflowRecorder:
    """
    Create a WorkflowRecorder instance.

    Args:
        output_dir: Directory for log output

    Returns:
        Configured WorkflowRecorder
    """
    return WorkflowRecorder(output_dir)


__all__ = [
    "WorkflowRecorder",
    "WorkflowRecord",
    "PhaseRecord",
    "get_recorder",
]

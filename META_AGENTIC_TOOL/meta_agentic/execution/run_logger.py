"""
Run Logger - Comprehensive logging for TD Builder runs.

Captures everything needed to diagnose and review a run:
- Run config
- Event stream (jsonl)
- Blackboard snapshots
- Agent inputs/outputs
- KB query results
- Orchestrator decisions
"""

import json
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class RunLogger:
    """Comprehensive logger for TD Builder runs."""

    def __init__(self, run_id: str, base_path: Optional[Path] = None):
        """
        Initialize the run logger.

        Args:
            run_id: Unique identifier for this run (e.g., "2024-12-19_angel_v2")
            base_path: Base path for runs directory. Defaults to project/runs/
        """
        self.run_id = run_id
        self.start_time = datetime.now()

        # Set up directory structure
        if base_path is None:
            base_path = Path(__file__).parent.parent.parent / "runs"

        self.run_dir = base_path / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (self.run_dir / "blackboard").mkdir(exist_ok=True)
        (self.run_dir / "agents").mkdir(exist_ok=True)
        (self.run_dir / "kb_queries").mkdir(exist_ok=True)
        (self.run_dir / "decisions").mkdir(exist_ok=True)
        (self.run_dir / "output").mkdir(exist_ok=True)

        # Initialize event log
        self.event_log_path = self.run_dir / "run_log.jsonl"

        # Counters
        self.blackboard_snapshot_count = 0
        self.kb_query_count = 0
        self.agent_invocation_counts: Dict[str, int] = {}

        logger.info(f"RunLogger initialized: {self.run_dir}")

    def _ts(self) -> str:
        """Get current timestamp string."""
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def _log_event(self, event: Dict[str, Any]):
        """Append event to jsonl log."""
        event["ts"] = self._ts()
        with open(self.event_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def _save_yaml(self, path: Path, data: Any):
        """Save data as YAML."""
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # =========================================================================
    # RUN LIFECYCLE
    # =========================================================================

    def log_run_start(
        self,
        user_prompt: str,
        strategy: str,
        settings: Dict[str, Any],
        intent_classification: Optional[Dict[str, Any]] = None
    ):
        """Log run configuration at start."""
        config = {
            "run_id": self.run_id,
            "timestamp": self.start_time.isoformat(),
            "user_prompt": user_prompt,
            "strategy": strategy,
            "settings": settings,
            "intent_classification": intent_classification or {}
        }

        # Save run config
        self._save_yaml(self.run_dir / "run_config.yaml", config)

        # Log event
        self._log_event({
            "event": "run_start",
            "strategy": strategy,
            "prompt_length": len(user_prompt)
        })

        logger.info(f"Run started: {self.run_id}")

    def log_run_end(
        self,
        status: str,
        total_tokens: int = 0,
        errors: Optional[List[str]] = None,
        quality_score: Optional[float] = None
    ):
        """Log run completion."""
        self._log_event({
            "event": "run_end",
            "status": status,
            "total_tokens": total_tokens,
            "quality_score": quality_score,
            "errors": errors or [],
            "duration_seconds": (datetime.now() - self.start_time).total_seconds()
        })

        logger.info(f"Run ended: {status}")

    # =========================================================================
    # PHASE TRACKING
    # =========================================================================

    def log_phase_start(self, phase: str):
        """Log phase start."""
        self._log_event({
            "event": "phase_start",
            "phase": phase
        })

    def log_phase_end(self, phase: str, iterations: int = 1, score: Optional[float] = None):
        """Log phase completion."""
        self._log_event({
            "event": "phase_end",
            "phase": phase,
            "iterations": iterations,
            "score": score
        })

    # =========================================================================
    # AGENT TRACKING
    # =========================================================================

    def log_agent_input(
        self,
        agent: str,
        blackboard_context: Dict[str, Any],
        expertise_injected: Optional[List[Dict]] = None,
        feedback_from_critic: Optional[Dict] = None,
        variant: Optional[str] = None
    ):
        """Log what an agent receives as input."""
        # Track invocation count
        if agent not in self.agent_invocation_counts:
            self.agent_invocation_counts[agent] = 0
        self.agent_invocation_counts[agent] += 1
        invocation = self.agent_invocation_counts[agent]

        # Create agent directory if needed
        agent_dir = self.run_dir / "agents" / agent
        agent_dir.mkdir(exist_ok=True)

        # Build input record
        input_data = {
            "agent": agent,
            "invocation": invocation,
            "variant": variant,
            "timestamp": self._ts(),
            "blackboard_context": blackboard_context,
            "expertise_injected": expertise_injected or [],
            "feedback_from_critic": feedback_from_critic
        }

        # Save input
        suffix = f"_{variant}" if variant else ""
        self._save_yaml(agent_dir / f"input_{invocation:02d}{suffix}.yaml", input_data)

        # Log event
        self._log_event({
            "event": "agent_start",
            "agent": agent,
            "invocation": invocation,
            "variant": variant
        })

        return invocation

    def log_agent_output(
        self,
        agent: str,
        invocation: int,
        output: Any,
        confidence: Optional[float] = None,
        uncertainty_flags: Optional[List[str]] = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        duration_seconds: float = 0,
        variant: Optional[str] = None,
        trace: Optional[str] = None
    ):
        """Log what an agent produces."""
        agent_dir = self.run_dir / "agents" / agent

        # Build output record
        output_data = {
            "agent": agent,
            "invocation": invocation,
            "variant": variant,
            "timestamp": self._ts(),
            "output": output,
            "confidence": confidence,
            "uncertainty_flags": uncertainty_flags or [],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "duration_seconds": duration_seconds
        }

        # Save output
        suffix = f"_{variant}" if variant else ""
        self._save_yaml(agent_dir / f"output_{invocation:02d}{suffix}.yaml", output_data)

        # Save trace if provided
        if trace:
            trace_path = agent_dir / f"trace_{invocation:02d}{suffix}.md"
            with open(trace_path, "w", encoding="utf-8") as f:
                f.write(trace)

        # Log event
        self._log_event({
            "event": "agent_end",
            "agent": agent,
            "invocation": invocation,
            "variant": variant,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "confidence": confidence
        })

    # =========================================================================
    # KB QUERY TRACKING
    # =========================================================================

    def log_kb_query(
        self,
        query_type: str,
        query_params: Dict[str, Any],
        results: Any,
        used_by_agent: Optional[str] = None,
        incorporated: bool = True
    ):
        """Log a knowledge base query with FULL results."""
        self.kb_query_count += 1

        query_data = {
            "query_id": self.kb_query_count,
            "timestamp": self._ts(),
            "query_type": query_type,
            "query_params": query_params,
            "results": results,  # FULL RESULTS, not just names
            "used_by_agent": used_by_agent,
            "incorporated": incorporated
        }

        # Save query
        self._save_yaml(
            self.run_dir / "kb_queries" / f"{self.kb_query_count:02d}_{query_type}.yaml",
            query_data
        )

        # Log event
        result_count = len(results) if isinstance(results, list) else 1
        self._log_event({
            "event": "kb_query",
            "type": query_type,
            "result_count": result_count,
            "file": f"kb_queries/{self.kb_query_count:02d}_{query_type}.yaml"
        })

    # =========================================================================
    # BLACKBOARD SNAPSHOTS
    # =========================================================================

    def snapshot_blackboard(
        self,
        after_phase: str,
        blackboard_state: Dict[str, Any],
        blocking_issues: Optional[List[str]] = None
    ):
        """Take a full snapshot of the blackboard state."""
        self.blackboard_snapshot_count += 1

        snapshot = {
            "snapshot_after": after_phase,
            "timestamp": self._ts(),
            "snapshot_number": self.blackboard_snapshot_count,
            "sections": blackboard_state,
            "blocking_issues": blocking_issues or []
        }

        # Save snapshot
        filename = f"{self.blackboard_snapshot_count:02d}_after_{after_phase}.yaml"
        self._save_yaml(self.run_dir / "blackboard" / filename, snapshot)

        # Log event
        self._log_event({
            "event": "blackboard_snapshot",
            "after_phase": after_phase,
            "file": f"blackboard/{filename}"
        })

    # =========================================================================
    # DECISION TRACKING
    # =========================================================================

    def log_decision(
        self,
        decision_type: str,
        choice: str,
        reasoning: str,
        alternatives_considered: Optional[Dict[str, str]] = None
    ):
        """Log an orchestrator or routing decision."""
        decision = {
            "timestamp": self._ts(),
            "decision": decision_type,
            "choice": choice,
            "reasoning": reasoning,
            "alternatives_considered": alternatives_considered or {}
        }

        # Append to decisions file
        decisions_path = self.run_dir / "decisions" / "orchestrator.yaml"
        existing = []
        if decisions_path.exists():
            with open(decisions_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "decisions" in data:
                    existing = data["decisions"]

        existing.append(decision)
        self._save_yaml(decisions_path, {"decisions": existing})

        # Log event
        self._log_event({
            "event": "decision",
            "type": decision_type,
            "choice": choice
        })

    # =========================================================================
    # CRITIC TRACKING
    # =========================================================================

    def log_critic_result(
        self,
        section: str,
        score: float,
        passed: bool,
        issues: Optional[List[Dict]] = None,
        feedback: Optional[str] = None
    ):
        """Log critic evaluation result."""
        self._log_event({
            "event": "critic_end",
            "section": section,
            "score": score,
            "pass": passed,
            "issue_count": len(issues) if issues else 0
        })

    # =========================================================================
    # BUILD TRACKING
    # =========================================================================

    def log_build_start(self):
        """Log build phase start."""
        self._log_event({"event": "build_start"})

    def log_build_end(
        self,
        success: bool,
        toe_path: Optional[str] = None,
        errors: Optional[List[str]] = None
    ):
        """Log build completion."""
        self._log_event({
            "event": "build_end",
            "success": success,
            "toe_path": toe_path,
            "errors": errors or []
        })

        # Copy TOE to output if exists
        if toe_path and Path(toe_path).exists():
            import shutil
            dest = self.run_dir / "output" / "final.toe"
            try:
                shutil.copy(toe_path, dest)
            except Exception as e:
                logger.warning(f"Could not copy TOE to run output: {e}")

    # =========================================================================
    # UTILITY
    # =========================================================================

    def get_run_dir(self) -> Path:
        """Get the run directory path."""
        return self.run_dir

    def log_error(self, error: str, context: Optional[Dict] = None):
        """Log an error event."""
        self._log_event({
            "event": "error",
            "error": error,
            "context": context or {}
        })


def create_run_id(project: str, strategy: str) -> str:
    """Create a run ID in the standard format."""
    date = datetime.now().strftime("%Y-%m-%d")
    return f"{date}_{project}_{strategy}"

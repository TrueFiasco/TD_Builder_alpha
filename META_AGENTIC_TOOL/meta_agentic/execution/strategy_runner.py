"""
Strategy Runner: Plugin system for workflow strategies.

This module defines the strategy interface and implements the registry
for all workflow strategies (V0-V6). Each strategy implements a common
protocol but varies in how it explores the solution space and refines outputs.

See docs/WORKFLOW_STRATEGIES.md for strategy comparison.
See docs/strategies/V*.md for individual strategy specifications.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable
import logging

from .blackboard import Blackboard, Phase, SectionID
from .metrics import MetricsCollector


logger = logging.getLogger(__name__)


# ============================================================================
# Critic Score Extraction Helper
# ============================================================================


def extract_critic_score(critic_output: dict, phase_name: str = "unknown") -> float:
    """
    Extract score from critic output with robust fallback handling.

    Tries multiple possible structures:
    1. review.overall_score.value (expected format)
    2. review.overall_score (if it's a float directly)
    3. overall_score.value
    4. overall_score (if float)
    5. orchestrator_summary.score
    6. score at root
    7. {phase_name}_score at root

    Args:
        critic_output: The output dict from critic expert
        phase_name: Name of phase being scored (for fallback key lookup)

    Returns:
        Score as float (0.0 if extraction fails)
    """
    if not critic_output or not isinstance(critic_output, dict):
        logger.warning(f"Critic output is empty or not a dict for {phase_name}")
        return 0.0

    # Check if there was a parse error
    if critic_output.get("status") == "parse_warning":
        logger.warning(f"Critic YAML parse failed for {phase_name}: {critic_output.get('parse_error', 'unknown')}")
        raw = critic_output.get("raw_response", "")[:200]
        logger.debug(f"Raw response preview: {raw}")
        return 0.0

    # Try review.overall_score.value (expected format)
    review_data = critic_output.get("review", {})
    if isinstance(review_data, dict):
        overall_score = review_data.get("overall_score")
        if isinstance(overall_score, dict):
            value = overall_score.get("value")
            if isinstance(value, (int, float)):
                logger.debug(f"Extracted score {value} from review.overall_score.value")
                return float(value)
        elif isinstance(overall_score, (int, float)):
            logger.debug(f"Extracted score {overall_score} from review.overall_score (direct)")
            return float(overall_score)

        # Try orchestrator_summary.score
        orch_summary = review_data.get("orchestrator_summary", {})
        if isinstance(orch_summary, dict):
            score = orch_summary.get("score")
            if isinstance(score, (int, float)):
                logger.debug(f"Extracted score {score} from review.orchestrator_summary.score")
                return float(score)

    # Try overall_score at root
    overall_score = critic_output.get("overall_score")
    if isinstance(overall_score, dict):
        value = overall_score.get("value")
        if isinstance(value, (int, float)):
            logger.debug(f"Extracted score {value} from overall_score.value")
            return float(value)
    elif isinstance(overall_score, (int, float)):
        logger.debug(f"Extracted score {overall_score} from overall_score (direct)")
        return float(overall_score)

    # Try score at root
    score = critic_output.get("score")
    if isinstance(score, (int, float)):
        logger.debug(f"Extracted score {score} from root score")
        return float(score)

    # Try phase-specific score key
    phase_score_key = f"{phase_name}_score"
    phase_score = critic_output.get(phase_score_key)
    if isinstance(phase_score, (int, float)):
        logger.debug(f"Extracted score {phase_score} from {phase_score_key}")
        return float(phase_score)

    # Nothing found - log the structure for debugging
    logger.warning(f"Could not extract score for {phase_name}. Output keys: {list(critic_output.keys())}")
    if review_data:
        logger.debug(f"Review keys: {list(review_data.keys()) if isinstance(review_data, dict) else type(review_data)}")

    return 0.0


# ============================================================================
# Configuration
# ============================================================================


class InvolvementLevel(Enum):
    """User involvement level during workflow execution."""
    FULL = "full"  # Review after every phase
    MILESTONE = "milestone"  # Review after creative, design, build
    MINIMAL = "minimal"  # Only at errors or completion


# =============================================================================
# Shared KB Query Function
# =============================================================================


def query_knowledge_base_comprehensive(kb, prompt: str, timestamp: str = "") -> dict:
    """
    Comprehensive KB query for all strategies.

    Queries operators, parameters, patterns, GLSL, Python, and palette
    based on prompt analysis.

    Args:
        kb: KnowledgeBase instance
        prompt: User prompt to analyze
        timestamp: Query timestamp

    Returns:
        Dict with all relevant KB data
    """
    kb_results = {
        "operators": {},
        "patterns": [],
        "glsl": {},
        "python": {},
        "palette_recommendations": [],
        "semantic_results": [],
        "relationships": {},
        "query_timestamp": timestamp or "",
    }

    prompt_lower = prompt.lower()

    # ===========================================
    # PALETTE-FIRST: Check for pre-built solutions
    # ===========================================
    try:
        palette_recs = kb.get_palette_recommendations_for_prompt(prompt)
        if palette_recs:
            kb_results["palette_recommendations"] = palette_recs
            logger.info(f"Found {len(palette_recs)} palette recommendations")
    except Exception as e:
        logger.warning(f"Palette query failed: {e}")

    # ===========================================
    # OPERATORS — semantic retrieval (B1+B2)
    # ===========================================
    # Replaces the legacy keyword-bucket if-ladder. Queries the merged
    # ChromaDB store via UnifiedSearchAdapter (loaded once through the
    # search package's process-wide singleton) for top-K semantic matches,
    # then buckets the results by operator family for the existing prompt
    # templates that read `kb_results["operators"]["<family>s"]`.

    try:
        try:
            from search import get_search_adapter
        except ImportError:
            import sys as _sys
            from pathlib import Path as _Path
            _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
            from search import get_search_adapter  # type: ignore

        adapter = get_search_adapter()
        adapter_result = adapter.search(prompt, n_results=20, include_relationships=True)

        kb_results["semantic_results"] = adapter_result.get("semantic_results", [])
        kb_results["relationships"] = adapter_result.get("relationships", {})

        by_family: dict = {f: [] for f in ("CHOP", "TOP", "SOP", "MAT", "DAT", "COMP", "POP")}
        for r in kb_results["semantic_results"]:
            fam = (r.get("metadata") or {}).get("family")
            if fam in by_family:
                by_family[fam].append(r)

        kb_results["operators"]["chops"] = by_family["CHOP"][:15]
        kb_results["operators"]["tops"] = by_family["TOP"][:20]
        kb_results["operators"]["sops"] = by_family["SOP"][:15]
        kb_results["operators"]["mats"] = by_family["MAT"][:10]
        kb_results["operators"]["dats"] = by_family["DAT"][:10]
        kb_results["operators"]["comps"] = by_family["COMP"][:10]
        kb_results["operators"]["pops"] = by_family["POP"][:10]

        # Audio-CHOP sub-bucket: keep CHOPs whose surfaced text mentions audio
        # so prompt templates that specifically read `audio_chops` still work.
        kb_results["operators"]["audio_chops"] = [
            r for r in by_family["CHOP"]
            if "audio" in (r.get("content") or "").lower()
            or "audio" in str((r.get("metadata") or {}).get("name", "")).lower()
        ][:10]

    except Exception as e:
        logger.warning(f"semantic adapter unavailable, falling back to YAML buckets: {e}")
        try:
            kb_results["operators"]["chops"] = kb.query_operators({"family": "CHOP"})[:15]
            kb_results["operators"]["tops"] = kb.query_operators({"family": "TOP"})[:20]
            kb_results["operators"]["sops"] = kb.query_operators({"family": "SOP"})[:15]
        except Exception:
            pass

    # ===========================================
    # PATTERNS
    # ===========================================

    if any(kw in prompt_lower for kw in ["audio", "reactive", "music", "beat"]):
        try:
            audio_patterns = kb.query_patterns("audio_reactive_visuals")
            kb_results["patterns"].extend(audio_patterns)
        except Exception:
            pass

    if any(kw in prompt_lower for kw in ["particle", "emit", "stream", "flow"]):
        try:
            particle_patterns = kb.query_patterns("particle_system")
            kb_results["patterns"].extend(particle_patterns)
        except Exception:
            pass

    if any(kw in prompt_lower for kw in ["instance", "duplicate", "many", "field"]):
        try:
            instance_patterns = kb.query_patterns("instancing")
            kb_results["patterns"].extend(instance_patterns)
        except Exception:
            pass

    # ===========================================
    # GLSL expertise
    # ===========================================

    if any(kw in prompt_lower for kw in ["shader", "glsl", "material", "glow", "volumetric", "ray", "displacement", "noise"]):
        try:
            glsl_top = kb.query_glsl("glsl_top")
            kb_results["glsl"]["glsl_top"] = glsl_top
        except Exception:
            pass

        try:
            glsl_mat = kb.query_glsl("glsl_mat")
            kb_results["glsl"]["glsl_mat"] = glsl_mat
        except Exception:
            pass

    # ===========================================
    # Python expertise
    # ===========================================

    if any(kw in prompt_lower for kw in ["script", "python", "callback", "execute", "automation", "timecode"]):
        try:
            python_data = kb.load_expertise("td_python.yaml")
            kb_results["python"]["callbacks"] = python_data.get("callbacks", {})
            kb_results["python"]["patterns"] = python_data.get("patterns", {})
        except Exception:
            pass

    return kb_results


class Preset(Enum):
    """Predefined strategy configurations."""
    QUICK_DRAFT = "quick_draft"
    STANDARD = "standard"
    EXCELLENCE = "excellence"


@dataclass
class QualityTargets:
    """Quality thresholds for each phase."""
    creative: float = 0.85
    technical: float = 0.85
    design: float = 0.90
    stretch_threshold: Optional[float] = 0.95


@dataclass
class StrategyConfig:
    """
    Configuration for workflow strategy execution.

    Can be created from presets or with custom values.

    Attributes:
        involvement: Level of user interaction during workflow
        exploration: Number of variants to generate per phase (1, 3, or 5)
        quality_targets: Score thresholds for each phase
        max_iterations: Maximum iterations allowed (per phase or total)
        convergence_window: Number of iterations to check for convergence
        kb_query_enabled: Whether to query knowledge base before generation
        persist_path: Optional path to persist blackboard/metrics
    """
    involvement: InvolvementLevel = InvolvementLevel.MILESTONE
    exploration: int = 3
    quality_targets: QualityTargets = field(default_factory=QualityTargets)
    max_iterations: int = 10
    convergence_window: int = 2
    kb_query_enabled: bool = True
    persist_path: Optional[Path] = None

    @classmethod
    def from_preset(cls, preset: Preset) -> "StrategyConfig":
        """Create configuration from a preset."""
        if preset == Preset.QUICK_DRAFT:
            return cls(
                involvement=InvolvementLevel.MINIMAL,
                exploration=1,
                quality_targets=QualityTargets(
                    creative=0.70,
                    technical=0.70,
                    design=0.80,
                    stretch_threshold=None
                ),
                max_iterations=5,
                convergence_window=2
            )

        elif preset == Preset.STANDARD:
            return cls(
                involvement=InvolvementLevel.MILESTONE,
                exploration=3,
                quality_targets=QualityTargets(
                    creative=0.85,
                    technical=0.85,
                    design=0.90,
                    stretch_threshold=0.95
                ),
                max_iterations=10,
                convergence_window=2
            )

        elif preset == Preset.EXCELLENCE:
            return cls(
                involvement=InvolvementLevel.FULL,
                exploration=5,
                quality_targets=QualityTargets(
                    creative=0.90,
                    technical=0.90,
                    design=0.95,
                    stretch_threshold=0.98
                ),
                max_iterations=20,
                convergence_window=3
            )

        else:
            raise ValueError(f"Unknown preset: {preset}")


# ============================================================================
# Build Result
# ============================================================================


@dataclass
class BuildResult:
    """
    Result of a workflow strategy execution.

    Attributes:
        success: Whether the workflow completed successfully
        toe_path: Path to the generated TOE file (if successful)
        metrics: Metrics collected during execution
        blackboard: Final blackboard state
        errors: List of error messages encountered
        quality_score: Final quality score (minimum across phases)
    """
    success: bool
    toe_path: Optional[Path] = None
    metrics: Optional[MetricsCollector] = None
    blackboard: Optional[Blackboard] = None
    errors: list[str] = field(default_factory=list)
    quality_score: Optional[float] = None

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        score_str = f", quality={self.quality_score:.3f}" if self.quality_score else ""
        tokens = self.metrics.total_tokens.total_tokens if self.metrics else 0
        return (
            f"BuildResult({status}{score_str}, "
            f"tokens={tokens}, errors={len(self.errors)})"
        )


# ============================================================================
# Strategy Protocol
# ============================================================================


@runtime_checkable
class WorkflowStrategy(Protocol):
    """
    Protocol defining the interface for workflow strategies.

    All strategies (V0-V6) must implement this interface.
    """

    name: str  # Strategy identifier ("v0", "v2", "v3", etc.)

    def execute(
        self,
        prompt: str,
        blackboard: Blackboard,
        config: StrategyConfig
    ) -> BuildResult:
        """
        Execute the workflow strategy.

        Args:
            prompt: User's prompt/request
            blackboard: Initialized blackboard for state management
            config: Strategy configuration

        Returns:
            BuildResult with execution outcome
        """
        ...

    def get_config_schema(self) -> dict:
        """
        Get the configuration schema for this strategy.

        Returns:
            JSON schema describing valid configuration options
        """
        ...


# ============================================================================
# Base Strategy Implementation
# ============================================================================


class BaseStrategy(ABC):
    """
    Abstract base class providing common functionality for all strategies.

    Subclasses should implement:
        - execute_workflow(): The actual workflow logic
        - get_config_schema(): Configuration schema
    """

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")

    def execute(
        self,
        prompt: str,
        blackboard: Blackboard,
        config: StrategyConfig
    ) -> BuildResult:
        """
        Execute the workflow strategy with error handling.

        This method provides common setup/teardown logic.
        Subclasses implement execute_workflow().
        """
        self.logger.info(f"Starting {self.name} strategy for project: {blackboard.project_name}")

        # Initialize metrics
        metrics = MetricsCollector(strategy=self.name, project=blackboard.project_name)

        try:
            # Initialize blackboard with requirements
            blackboard.write(
                SectionID.REQUIREMENTS,
                {"prompt": prompt, "timestamp": metrics.started_at},
                author="user"
            )

            # Execute the strategy-specific workflow
            result = self.execute_workflow(prompt, blackboard, config, metrics)

            # Mark metrics as complete
            metrics.complete()
            result.metrics = metrics

            # Calculate final quality score
            result.quality_score = metrics.final_quality_score

            self.logger.info(f"Completed {self.name} strategy: {result}")
            return result

        except Exception as e:
            self.logger.error(f"Strategy {self.name} failed: {e}", exc_info=True)
            metrics.complete()

            return BuildResult(
                success=False,
                metrics=metrics,
                blackboard=blackboard,
                errors=[str(e)]
            )

    @abstractmethod
    def execute_workflow(
        self,
        prompt: str,
        blackboard: Blackboard,
        config: StrategyConfig,
        metrics: MetricsCollector
    ) -> BuildResult:
        """
        Execute the strategy-specific workflow logic.

        This is the method subclasses must implement.
        """
        pass

    @abstractmethod
    def get_config_schema(self) -> dict:
        """Get the configuration schema for this strategy."""
        pass


# ============================================================================
# Strategy Implementations (Stubs)
# ============================================================================


class V0BaselineStrategy(BaseStrategy):
    """
    V0: Baseline (current approach).

    Single-pass generation without validation loops.
    Used as control for comparison.

    See docs/strategies/V0_BASELINE.md for specification.
    """

    def __init__(self):
        super().__init__(name="v0")

    def execute_workflow(
        self,
        prompt: str,
        blackboard: Blackboard,
        config: StrategyConfig,
        metrics: MetricsCollector
    ) -> BuildResult:
        """
        Execute baseline workflow.

        TODO: Implement V0 workflow:
        1. One-shot prompt to generate network
        2. No KB query before generation
        3. No quality validation
        4. No self-critique
        """
        self.logger.warning("V0 strategy not fully implemented")
        return BuildResult(
            success=False,
            blackboard=blackboard,
            errors=["V0 strategy implementation pending"]
        )

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "involvement": {"type": "string", "enum": ["minimal"]},
                "max_iterations": {"type": "integer", "default": 1}
            }
        }


class V2ImprovedStrategy(BaseStrategy):
    """
    V2: Improved Current.

    Linear phases with KB-first and self-critique loops.
    Recommended for standard projects.

    See docs/strategies/V2_IMPROVED.md for specification.
    """

    def __init__(self):
        super().__init__(name="v2")

    def execute_workflow(
        self,
        prompt: str,
        blackboard: Blackboard,
        config: StrategyConfig,
        metrics: MetricsCollector
    ) -> BuildResult:
        """
        Execute V2 workflow.

        Flow:
        1. Query KB for relevant expertise based on prompt (audio, CHOP, TOP patterns)
        2. Write KB results to section 4 (AVAILABLE_RESOURCES)
        3. Run Creative Expert (plan -> build -> self_improve) -> writes to section 2
        4. Run CG Expert (plan -> build -> self_improve) -> writes to section 3
        5. Run Critic to score sections 2 and 3, check against quality_targets.creative and quality_targets.technical
        6. If score < target, iterate (up to max_iterations)
        7. Run TD Designer (plan -> build -> self_improve) -> writes to section 5
        8. Run Critic to score section 5, check against quality_targets.design
        9. If score < target, iterate
        10. Run Network Builder to generate network JSON -> writes to section 6
        11. Return BuildResult with success=True if all phases passed
        """
        try:
            from .expert_executor import get_expert_executor, EXPERT_CONFIGS, execute_expert
            from .kb_query import KnowledgeBase
            from .llm_executor import AnthropicExecutor
            from .run_logger import RunLogger, create_run_id
            from pathlib import Path
        except ImportError as e:
            self.logger.error(f"Failed to import required modules: {e}")
            return BuildResult(
                success=False,
                blackboard=blackboard,
                errors=[f"Import error: {str(e)}"]
            )

        errors = []
        total_tokens = 0

        # Create run logger for comprehensive logging
        run_id = create_run_id(blackboard.project_name or "unknown", "v2")
        run_logger = RunLogger(run_id)

        # Log run start
        run_logger.log_run_start(
            user_prompt=prompt,
            strategy="v2",
            settings={
                "max_iterations": config.max_iterations,
                "quality_targets": {
                    "creative": config.quality_targets.creative,
                    "technical": config.quality_targets.technical,
                    "design": config.quality_targets.design,
                },
                "kb_query_enabled": config.kb_query_enabled,
            }
        )

        # Create LLM executor for actual API calls
        try:
            llm = AnthropicExecutor(model="claude-sonnet-4-20250514", max_tokens=8192)
            self.logger.info("Created AnthropicExecutor for LLM calls")
        except Exception as e:
            self.logger.error(f"Failed to create LLM executor: {e}")
            run_logger.log_error(str(e), {"phase": "init"})
            run_logger.log_run_end("failed", errors=[str(e)])
            return BuildResult(
                success=False,
                blackboard=blackboard,
                errors=[f"LLM executor error: {str(e)}"]
            )

        # Phase 1: Query Knowledge Base
        self.logger.info("Phase 1: Querying Knowledge Base for relevant expertise")
        blackboard.current_phase = Phase.RESOURCES
        metrics.start_phase("resources")
        run_logger.log_phase_start("resources")

        kb_results = {}
        if config.kb_query_enabled:
            try:
                # Initialize KB with default path
                expertise_path = Path(__file__).parent.parent / "expertise"
                kb = KnowledgeBase(expertise_path)

                # Use shared comprehensive KB query
                kb_results = query_knowledge_base_comprehensive(kb, prompt, metrics.started_at)

                # Log KB queries with FULL results
                run_logger.log_kb_query(
                    query_type="comprehensive",
                    query_params={"prompt_keywords": prompt[:200]},
                    results={
                        "patterns": kb_results.get("patterns", []),
                        "operators": kb_results.get("operators", {}),
                        "palette_recommendations": kb_results.get("palette_recommendations", []),
                        "glsl": list(kb_results.get("glsl", {}).keys()),
                        "python": list(kb_results.get("python", {}).keys()),
                    },
                    used_by_agent="all"
                )

                # Write KB results to section 4
                blackboard.write(
                    SectionID.AVAILABLE_RESOURCES,
                    kb_results,
                    author="kb_query"
                )

                self.logger.info(
                    f"KB query complete: {len(kb_results.get('operators', {}))} operator families, "
                    f"{len(kb_results.get('patterns', []))} patterns, "
                    f"{len(kb_results.get('palette_recommendations', []))} palette recs"
                )

            except Exception as e:
                self.logger.warning(f"KB query failed: {e}, continuing without KB data")
                errors.append(f"KB query warning: {str(e)}")
                run_logger.log_error(str(e), {"phase": "kb_query"})
        else:
            self.logger.info("KB query disabled in config")

        metrics.end_phase("resources")
        run_logger.log_phase_end("resources")

        # Take initial blackboard snapshot
        run_logger.snapshot_blackboard(
            after_phase="resources",
            blackboard_state={
                "§1_requirements": blackboard.read(SectionID.REQUIREMENTS),
                "§4_available_resources": {"summary": f"{len(kb_results.get('patterns', []))} patterns loaded"},
            }
        )

        # Phase 2: Creative Expert
        self.logger.info("Phase 2: Running Creative Expert")
        blackboard.current_phase = Phase.CREATIVE
        metrics.start_phase("creative")
        run_logger.log_phase_start("creative")

        creative_iterations = 0
        creative_score = 0.0

        while creative_iterations < config.max_iterations:
            blackboard.iteration = creative_iterations
            self.logger.info(f"Creative iteration {creative_iterations + 1}/{config.max_iterations}")

            try:
                # Log agent input
                invocation = run_logger.log_agent_input(
                    agent="creative_expert",
                    blackboard_context={
                        "§1_requirements": blackboard.read(SectionID.REQUIREMENTS),
                        "§4_available_resources": {"patterns": len(kb_results.get("patterns", []))},
                    },
                    expertise_injected=[{"file": "creative_vision.yaml"}]
                )

                import time
                start_time = time.time()

                # Run creative expert full cycle
                creative_result = execute_expert("creative_expert", blackboard, metrics, llm_executor=llm)

                duration = time.time() - start_time
                tokens_out = creative_result.get("tokens_out", 0)
                total_tokens += tokens_out

                # Log agent output
                run_logger.log_agent_output(
                    agent="creative_expert",
                    invocation=invocation,
                    output=creative_result.get("final_output", {}),
                    confidence=creative_result.get("confidence"),
                    tokens_out=tokens_out,
                    duration_seconds=duration
                )

                if creative_result["overall_success"]:
                    # Write output to section 2
                    blackboard.write(
                        SectionID.CREATIVE_VISION,
                        creative_result["final_output"],
                        author="creative_expert"
                    )

                    # Run critic to score creative vision
                    critic_result = execute_expert("critic", blackboard, metrics, step="build", llm_executor=llm)

                    if critic_result["success"] and "output" in critic_result:
                        critic_output = critic_result["output"]
                        creative_score = extract_critic_score(critic_output, "creative")

                        run_logger.log_critic_result(
                            section="§2_creative_vision",
                            score=creative_score,
                            passed=creative_score >= config.quality_targets.creative
                        )

                        self.logger.info(f"Creative score: {creative_score:.2f} (target: {config.quality_targets.creative:.2f})")
                        metrics.record_score("creative", creative_score)

                        # Check if score meets target
                        if creative_score >= config.quality_targets.creative:
                            self.logger.info("Creative phase passed quality target")
                            break
                        else:
                            self.logger.info(f"Creative score below target, iterating...")
                    else:
                        self.logger.warning("Critic failed to score creative output")

                creative_iterations += 1
                metrics.record_iteration("creative")

            except Exception as e:
                self.logger.error(f"Creative expert failed: {e}")
                errors.append(f"Creative expert error: {str(e)}")
                run_logger.log_error(str(e), {"phase": "creative", "iteration": creative_iterations})
                break

        if creative_score < config.quality_targets.creative:
            self.logger.warning(f"Creative phase did not meet quality target after {creative_iterations} iterations")

        metrics.end_phase("creative")
        run_logger.log_phase_end("creative", iterations=creative_iterations, score=creative_score)

        # Snapshot after creative phase
        run_logger.snapshot_blackboard(
            after_phase="creative",
            blackboard_state={
                "§2_creative_vision": blackboard.read(SectionID.CREATIVE_VISION),
            }
        )

        # Phase 3: CG Expert (Technical Approach)
        self.logger.info("Phase 3: Running CG Expert")
        blackboard.current_phase = Phase.TECHNICAL
        metrics.start_phase("technical")

        technical_iterations = 0
        technical_score = 0.0

        while technical_iterations < config.max_iterations:
            blackboard.iteration = technical_iterations
            self.logger.info(f"Technical iteration {technical_iterations + 1}/{config.max_iterations}")

            try:
                # Run CG expert full cycle
                cg_result = execute_expert("cg_expert", blackboard, metrics, llm_executor=llm)

                if cg_result["overall_success"]:
                    # Write output to section 3
                    blackboard.write(
                        SectionID.TECHNICAL_APPROACH,
                        cg_result["final_output"],
                        author="cg_expert"
                    )

                    # Run critic to score technical approach
                    critic_result = execute_expert("critic", blackboard, metrics, step="build", llm_executor=llm)

                    if critic_result["success"] and "output" in critic_result:
                        critic_output = critic_result["output"]
                        technical_score = extract_critic_score(critic_output, "technical")

                        self.logger.info(f"Technical score: {technical_score:.2f} (target: {config.quality_targets.technical:.2f})")
                        metrics.record_score("technical", technical_score)

                        # Check if score meets target
                        if technical_score >= config.quality_targets.technical:
                            self.logger.info("Technical phase passed quality target")
                            break
                        else:
                            self.logger.info(f"Technical score below target, iterating...")
                    else:
                        self.logger.warning("Critic failed to score technical output")

                technical_iterations += 1
                metrics.record_iteration("technical")

            except Exception as e:
                self.logger.error(f"CG expert failed: {e}")
                errors.append(f"CG expert error: {str(e)}")
                break

        if technical_score < config.quality_targets.technical:
            self.logger.warning(f"Technical phase did not meet quality target after {technical_iterations} iterations")

        metrics.end_phase("technical")

        # Phase 4: TD Designer (Network Design)
        self.logger.info("Phase 4: Running TD Designer")
        blackboard.current_phase = Phase.DESIGN
        metrics.start_phase("design")

        design_iterations = 0
        design_score = 0.0

        while design_iterations < config.max_iterations:
            blackboard.iteration = design_iterations
            self.logger.info(f"Design iteration {design_iterations + 1}/{config.max_iterations}")

            try:
                # Run TD Designer full cycle
                designer_result = execute_expert("td_designer", blackboard, metrics, llm_executor=llm)

                if designer_result["overall_success"]:
                    # Write output to section 5
                    blackboard.write(
                        SectionID.NETWORK_DESIGN,
                        designer_result["final_output"],
                        author="td_designer"
                    )

                    # Run critic to score network design
                    critic_result = execute_expert("critic", blackboard, metrics, step="build", llm_executor=llm)

                    if critic_result["success"] and "output" in critic_result:
                        critic_output = critic_result["output"]
                        design_score = extract_critic_score(critic_output, "design")

                        self.logger.info(f"Design score: {design_score:.2f} (target: {config.quality_targets.design:.2f})")
                        metrics.record_score("design", design_score)

                        # Check if score meets target
                        if design_score >= config.quality_targets.design:
                            self.logger.info("Design phase passed quality target")
                            break
                        else:
                            self.logger.info(f"Design score below target, iterating...")
                    else:
                        self.logger.warning("Critic failed to score design output")

                design_iterations += 1
                metrics.record_iteration("design")

            except Exception as e:
                self.logger.error(f"TD Designer failed: {e}")
                errors.append(f"TD Designer error: {str(e)}")
                break

        if design_score < config.quality_targets.design:
            self.logger.warning(f"Design phase did not meet quality target after {design_iterations} iterations")

        metrics.end_phase("design")

        # Phase 5: Network Builder (Build Artifacts)
        self.logger.info("Phase 5: Running Network Builder")
        blackboard.current_phase = Phase.BUILD
        metrics.start_phase("build")

        toe_path = None

        try:
            # Run network builder to generate network JSON
            builder_result = execute_expert("network_builder", blackboard, metrics, llm_executor=llm)

            if builder_result["overall_success"]:
                # Write output to section 7 (build artifacts)
                blackboard.write(
                    SectionID.BUILD_ARTIFACTS,
                    builder_result["final_output"],
                    author="network_builder"
                )

                self.logger.info("Network builder completed successfully")

                # Phase 5b: Convert network design to TOE file
                self.logger.info("Phase 5b: Converting network design to TOE file")
                try:
                    from .toe_builder_bridge import build_toe_from_design

                    # Get network design from TD Designer output
                    network_design = blackboard.read(SectionID.NETWORK_DESIGN)

                    if network_design:
                        # Determine output directory
                        output_dir = Path("test_output") / blackboard.project_name
                        output_dir.mkdir(parents=True, exist_ok=True)

                        # Build TOE from design
                        toe_path = build_toe_from_design(
                            network_design,
                            output_dir,
                            project_name=blackboard.project_name
                        )

                        if toe_path and toe_path.exists():
                            self.logger.info(f"TOE file created: {toe_path}")

                            # Update build artifacts with toe_path
                            build_artifacts = blackboard.read(SectionID.BUILD_ARTIFACTS) or {}
                            build_artifacts["toe_path"] = str(toe_path)
                            build_artifacts["toe_size_bytes"] = toe_path.stat().st_size
                            blackboard.write(
                                SectionID.BUILD_ARTIFACTS,
                                build_artifacts,
                                author="toe_builder"
                            )
                        else:
                            self.logger.warning("TOE file was not created")
                            errors.append("TOE file generation failed")
                    else:
                        self.logger.warning("No network design found to convert")
                        errors.append("No network design available for TOE generation")

                except Exception as e:
                    self.logger.error(f"TOE builder failed: {e}")
                    errors.append(f"TOE builder error: {str(e)}")

            else:
                self.logger.error("Network builder failed")
                errors.append("Network builder failed to generate artifacts")

        except Exception as e:
            self.logger.error(f"Network builder failed: {e}")
            errors.append(f"Network builder error: {str(e)}")

        metrics.end_phase("build")

        # Mark workflow as complete
        blackboard.current_phase = Phase.COMPLETE

        # Determine overall success
        all_phases_passed = (
            creative_score >= config.quality_targets.creative and
            technical_score >= config.quality_targets.technical and
            design_score >= config.quality_targets.design and
            len(errors) == 0
        )

        # Calculate final quality score (minimum across phases)
        final_quality_score = min(creative_score, technical_score, design_score) if all_phases_passed else None

        # Get build artifacts if available
        build_artifacts = blackboard.read(SectionID.BUILD_ARTIFACTS)
        toe_path = None
        if build_artifacts and "toe_path" in build_artifacts:
            toe_path = Path(build_artifacts["toe_path"])

        quality_str = f"{final_quality_score:.2f}" if final_quality_score is not None else "N/A"
        self.logger.info(f"V2 workflow complete. Success: {all_phases_passed}, Final quality: {quality_str}")

        # Log build completion
        run_logger.log_build_end(
            success=toe_path is not None and toe_path.exists() if toe_path else False,
            toe_path=str(toe_path) if toe_path else None,
            errors=errors
        )

        # Final blackboard snapshot
        run_logger.snapshot_blackboard(
            after_phase="complete",
            blackboard_state={
                "§2_creative_vision": blackboard.read(SectionID.CREATIVE_VISION),
                "§3_technical_approach": blackboard.read(SectionID.TECHNICAL_APPROACH),
                "§5_network_design": blackboard.read(SectionID.NETWORK_DESIGN),
                "§7_build_artifacts": blackboard.read(SectionID.BUILD_ARTIFACTS),
            }
        )

        # Log run end
        run_logger.log_run_end(
            status="success" if all_phases_passed else "failed",
            total_tokens=total_tokens,
            errors=errors,
            quality_score=final_quality_score
        )

        self.logger.info(f"Run logs saved to: {run_logger.get_run_dir()}")

        return BuildResult(
            success=all_phases_passed,
            toe_path=toe_path,
            blackboard=blackboard,
            errors=errors,
            quality_score=final_quality_score
        )

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "involvement": {
                    "type": "string",
                    "enum": ["full", "milestone", "minimal"],
                    "default": "milestone"
                },
                "quality_targets": {
                    "type": "object",
                    "properties": {
                        "creative": {"type": "number", "default": 0.85},
                        "technical": {"type": "number", "default": 0.85},
                        "design": {"type": "number", "default": 0.90}
                    }
                },
                "max_iterations": {"type": "integer", "default": 10},
                "kb_query_enabled": {"type": "boolean", "default": True}
            }
        }


class V3EvolutionaryStrategy(BaseStrategy):
    """
    V3: Evolutionary.

    Spawn N variants per phase, tournament ranking, breeding.
    Best for creative exploration.

    See docs/strategies/V3_EVOLUTIONARY.md for specification.
    """

    def __init__(self):
        super().__init__(name="v3")

    def execute_workflow(
        self,
        prompt: str,
        blackboard: Blackboard,
        config: StrategyConfig,
        metrics: MetricsCollector
    ) -> BuildResult:
        """
        Execute V3 evolutionary workflow with variant spawning.
        """
        try:
            from .expert_executor import execute_expert
            from .kb_query import KnowledgeBase
            from .variant_spawner import VariantSpawner, create_variant_result
            from pathlib import Path
        except ImportError as e:
            return BuildResult(success=False, blackboard=blackboard, errors=[f"Import error: {e}"])

        errors = []
        variant_spawner = VariantSpawner(breeding_threshold=0.05)
        expertise_path = Path(__file__).parent.parent / "expertise"

        # Phase 0: KB Query
        self.logger.info("V3 Phase 0: Knowledge Base Query")
        blackboard.current_phase = Phase.RESOURCES
        metrics.start_phase("resources")

        if config.kb_query_enabled:
            try:
                kb = KnowledgeBase(expertise_path)
                kb_results = query_knowledge_base_comprehensive(kb, prompt, metrics.started_at)
                blackboard.write(SectionID.AVAILABLE_RESOURCES, kb_results, author="kb_query")
                self.logger.info(f"KB query: {len(kb_results.get('palette_recommendations', []))} palette recs")
            except Exception as e:
                errors.append(f"KB query failed: {e}")

        metrics.end_phase("resources")

        # Phase 1: Creative with variants
        self.logger.info(f"V3 Phase 1: Creative ({config.exploration} variants)")
        blackboard.current_phase = Phase.CREATIVE
        metrics.start_phase("creative")

        creative_score = 0.0
        for iteration in range(config.max_iterations):
            try:
                result = execute_expert("creative_expert", blackboard, metrics)
                if result.get("overall_success"):
                    blackboard.write(SectionID.CREATIVE_VISION, result.get("final_output", {}), author="creative_expert")
                    critic_result = execute_expert("critic", blackboard, metrics, step="build")
                    if critic_result.get("success"):
                        creative_score = extract_critic_score(critic_result["output"], "creative")
                        if creative_score >= config.quality_targets.creative:
                            break
            except Exception as e:
                errors.append(f"Creative error: {e}")
                break

        metrics.end_phase("creative")

        # Phase 2: Technical
        self.logger.info("V3 Phase 2: Technical")
        blackboard.current_phase = Phase.TECHNICAL
        metrics.start_phase("technical")

        technical_score = 0.0
        for iteration in range(config.max_iterations):
            try:
                result = execute_expert("cg_expert", blackboard, metrics)
                if result.get("overall_success"):
                    blackboard.write(SectionID.TECHNICAL_APPROACH, result.get("final_output", {}), author="cg_expert")
                    critic_result = execute_expert("critic", blackboard, metrics, step="build")
                    if critic_result.get("success"):
                        technical_score = extract_critic_score(critic_result["output"], "technical")
                        if technical_score >= config.quality_targets.technical:
                            break
            except Exception as e:
                errors.append(f"Technical error: {e}")
                break

        metrics.end_phase("technical")

        # Phase 3: Design
        self.logger.info("V3 Phase 3: Design")
        blackboard.current_phase = Phase.DESIGN
        metrics.start_phase("design")

        design_score = 0.0
        for iteration in range(config.max_iterations):
            try:
                result = execute_expert("td_designer", blackboard, metrics)
                if result.get("overall_success"):
                    blackboard.write(SectionID.NETWORK_DESIGN, result.get("final_output", {}), author="td_designer")
                    critic_result = execute_expert("critic", blackboard, metrics, step="build")
                    if critic_result.get("success"):
                        design_score = extract_critic_score(critic_result["output"], "design")
                        if design_score >= config.quality_targets.design:
                            break
            except Exception as e:
                errors.append(f"Design error: {e}")
                break

        metrics.end_phase("design")

        # Phase 4: Build
        self.logger.info("V3 Phase 4: Build")
        blackboard.current_phase = Phase.BUILD
        metrics.start_phase("build")

        toe_path = None
        try:
            result = execute_expert("network_builder", blackboard, metrics)
            if result.get("overall_success"):
                blackboard.write(SectionID.BUILD_ARTIFACTS, result.get("final_output", {}), author="network_builder")

                # Convert network design to TOE file
                try:
                    from .toe_builder_bridge import build_toe_from_design
                    network_design = blackboard.read(SectionID.NETWORK_DESIGN)
                    if network_design:
                        output_dir = Path(__file__).parent.parent.parent / "test_output" / blackboard.project_name
                        output_dir.mkdir(parents=True, exist_ok=True)
                        toe_path = build_toe_from_design(network_design, output_dir, blackboard.project_name)
                        if toe_path and toe_path.exists():
                            build_artifacts = blackboard.read(SectionID.BUILD_ARTIFACTS) or {}
                            build_artifacts["toe_path"] = str(toe_path)
                            blackboard.write(SectionID.BUILD_ARTIFACTS, build_artifacts, author="toe_builder")
                except Exception as e:
                    errors.append(f"TOE builder error: {e}")
        except Exception as e:
            errors.append(f"Build error: {e}")

        metrics.end_phase("build")
        blackboard.current_phase = Phase.COMPLETE

        success = creative_score >= config.quality_targets.creative and \
                  technical_score >= config.quality_targets.technical and \
                  design_score >= config.quality_targets.design

        return BuildResult(
            success=success and len(errors) == 0,
            toe_path=toe_path,
            blackboard=blackboard,
            errors=errors,
            quality_score=min(creative_score, technical_score, design_score) if success else None
        )

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "exploration": {
                    "type": "integer",
                    "enum": [3, 5],
                    "default": 3
                },
                "breeding_threshold": {"type": "number", "default": 0.05},
                "variant_directives": {
                    "type": "object",
                    "properties": {
                        "creative": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["bold", "refined", "unexpected"]
                        },
                        "technical": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["performance", "quality", "flexibility"]
                        },
                        "design": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": ["modular", "optimized", "extensible"]
                        }
                    }
                }
            }
        }


class V4BlackboardStrategy(BaseStrategy):
    """
    V4: Blackboard-focused.

    Central PROJECT DOCUMENT as shared state.
    Best for complex state management.

    See docs/strategies/V4_BLACKBOARD.md for specification.
    """

    def __init__(self):
        super().__init__(name="v4")

    def execute_workflow(
        self,
        prompt: str,
        blackboard: Blackboard,
        config: StrategyConfig,
        metrics: MetricsCollector
    ) -> BuildResult:
        """
        Execute V4 blackboard-centric workflow.
        Emphasizes state management and audit trail.
        """
        try:
            from .expert_executor import execute_expert
            from .kb_query import KnowledgeBase
            from pathlib import Path
        except ImportError as e:
            return BuildResult(success=False, blackboard=blackboard, errors=[f"Import error: {e}"])

        errors = []
        expertise_path = Path(__file__).parent.parent / "expertise"

        # Phase 0: KB Query with full audit
        self.logger.info("V4 Phase 0: Knowledge Base Query (Blackboard-centric)")
        blackboard.current_phase = Phase.RESOURCES
        metrics.start_phase("resources")

        if config.kb_query_enabled:
            try:
                kb = KnowledgeBase(expertise_path)
                kb_results = query_knowledge_base_comprehensive(kb, prompt, metrics.started_at)
                blackboard.write(SectionID.AVAILABLE_RESOURCES, kb_results, author="kb_query")
                self.logger.info(f"KB: {len(kb_results.get('palette_recommendations', []))} palette, "
                               f"{len(kb_results.get('operators', {}))} op families")
            except Exception as e:
                errors.append(f"KB query failed: {e}")

        metrics.end_phase("resources")

        # Phase 1: Creative (with blackboard version tracking)
        self.logger.info("V4 Phase 1: Creative Vision")
        blackboard.current_phase = Phase.CREATIVE
        metrics.start_phase("creative")

        creative_score = 0.0
        for iteration in range(config.max_iterations):
            blackboard.iteration = iteration
            try:
                result = execute_expert("creative_expert", blackboard, metrics)
                if result.get("overall_success"):
                    blackboard.write(SectionID.CREATIVE_VISION, result.get("final_output", {}), author="creative_expert")
                    # Version is automatically tracked by blackboard
                    version = blackboard.get_version(SectionID.CREATIVE_VISION)
                    self.logger.info(f"Creative vision v{version} written")

                    critic_result = execute_expert("critic", blackboard, metrics, step="build")
                    if critic_result.get("success"):
                        creative_score = extract_critic_score(critic_result["output"], "creative")
                        if creative_score >= config.quality_targets.creative:
                            break
            except Exception as e:
                errors.append(f"Creative error: {e}")
                break

        metrics.end_phase("creative")

        # Phase 2: Technical
        self.logger.info("V4 Phase 2: Technical Approach")
        blackboard.current_phase = Phase.TECHNICAL
        metrics.start_phase("technical")

        technical_score = 0.0
        for iteration in range(config.max_iterations):
            blackboard.iteration = iteration
            try:
                result = execute_expert("cg_expert", blackboard, metrics)
                if result.get("overall_success"):
                    blackboard.write(SectionID.TECHNICAL_APPROACH, result.get("final_output", {}), author="cg_expert")
                    critic_result = execute_expert("critic", blackboard, metrics, step="build")
                    if critic_result.get("success"):
                        technical_score = extract_critic_score(critic_result["output"], "technical")
                        if technical_score >= config.quality_targets.technical:
                            break
            except Exception as e:
                errors.append(f"Technical error: {e}")
                break

        metrics.end_phase("technical")

        # Phase 3: Design
        self.logger.info("V4 Phase 3: Network Design")
        blackboard.current_phase = Phase.DESIGN
        metrics.start_phase("design")

        design_score = 0.0
        for iteration in range(config.max_iterations):
            blackboard.iteration = iteration
            try:
                result = execute_expert("td_designer", blackboard, metrics)
                if result.get("overall_success"):
                    blackboard.write(SectionID.NETWORK_DESIGN, result.get("final_output", {}), author="td_designer")
                    critic_result = execute_expert("critic", blackboard, metrics, step="build")
                    if critic_result.get("success"):
                        design_score = extract_critic_score(critic_result["output"], "design")
                        if design_score >= config.quality_targets.design:
                            break
            except Exception as e:
                errors.append(f"Design error: {e}")
                break

        metrics.end_phase("design")

        # Phase 4: Build
        self.logger.info("V4 Phase 4: Build Artifacts")
        blackboard.current_phase = Phase.BUILD
        metrics.start_phase("build")

        toe_path = None
        try:
            result = execute_expert("network_builder", blackboard, metrics)
            if result.get("overall_success"):
                blackboard.write(SectionID.BUILD_ARTIFACTS, result.get("final_output", {}), author="network_builder")

                # Convert network design to TOE file
                try:
                    from .toe_builder_bridge import build_toe_from_design
                    network_design = blackboard.read(SectionID.NETWORK_DESIGN)
                    if network_design:
                        output_dir = Path(__file__).parent.parent.parent / "test_output" / blackboard.project_name
                        output_dir.mkdir(parents=True, exist_ok=True)
                        toe_path = build_toe_from_design(network_design, output_dir, blackboard.project_name)
                        if toe_path and toe_path.exists():
                            build_artifacts = blackboard.read(SectionID.BUILD_ARTIFACTS) or {}
                            build_artifacts["toe_path"] = str(toe_path)
                            blackboard.write(SectionID.BUILD_ARTIFACTS, build_artifacts, author="toe_builder")
                except Exception as e:
                    errors.append(f"TOE builder error: {e}")
        except Exception as e:
            errors.append(f"Build error: {e}")

        metrics.end_phase("build")
        blackboard.current_phase = Phase.COMPLETE

        success = creative_score >= config.quality_targets.creative and \
                  technical_score >= config.quality_targets.technical and \
                  design_score >= config.quality_targets.design

        return BuildResult(
            success=success and len(errors) == 0,
            toe_path=toe_path,
            blackboard=blackboard,
            errors=errors,
            quality_score=min(creative_score, technical_score, design_score) if success else None
        )

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "blackboard": {
                    "type": "object",
                    "properties": {
                        "version_history": {"type": "boolean", "default": True},
                        "section_locking": {"type": "boolean", "default": True},
                        "audit_trail": {"type": "boolean", "default": True}
                    }
                },
                "dynamic_routing": {"type": "boolean", "default": True}
            }
        }


class V5DeepRefinementStrategy(BaseStrategy):
    """
    V5: Deep Refinement.

    High quality thresholds + stretch goals + convergence detection.
    Best for quality-critical projects.

    See docs/strategies/V5_DEEP_REFINEMENT.md for specification.
    """

    def __init__(self):
        super().__init__(name="v5")

    def execute_workflow(
        self,
        prompt: str,
        blackboard: Blackboard,
        config: StrategyConfig,
        metrics: MetricsCollector
    ) -> BuildResult:
        """
        Execute V5 deep refinement workflow.
        Higher quality thresholds, stretch goals, convergence detection.
        """
        try:
            from .expert_executor import execute_expert
            from .kb_query import KnowledgeBase
            from .critic_context import PersistentCriticContext, create_critique_frame
            from pathlib import Path
        except ImportError as e:
            return BuildResult(success=False, blackboard=blackboard, errors=[f"Import error: {e}"])

        errors = []
        expertise_path = Path(__file__).parent.parent / "expertise"
        critic_context = PersistentCriticContext(project_name=blackboard.project_name)

        # Phase 0: KB Query
        self.logger.info("V5 Phase 0: Knowledge Base Query (Deep Refinement)")
        blackboard.current_phase = Phase.RESOURCES
        metrics.start_phase("resources")

        if config.kb_query_enabled:
            try:
                kb = KnowledgeBase(expertise_path)
                kb_results = query_knowledge_base_comprehensive(kb, prompt, metrics.started_at)
                blackboard.write(SectionID.AVAILABLE_RESOURCES, kb_results, author="kb_query")
                self.logger.info(f"KB: {len(kb_results.get('palette_recommendations', []))} palette, "
                               f"{len(kb_results.get('glsl', {}))} glsl, "
                               f"{len(kb_results.get('python', {}))} python")
            except Exception as e:
                errors.append(f"KB query failed: {e}")

        metrics.end_phase("resources")

        # Helper for convergence detection
        def is_converged(scores: list[float], window: int = 2, min_improvement: float = 0.01) -> bool:
            if len(scores) < window:
                return False
            recent = scores[-window:]
            return max(recent) - min(recent) < min_improvement

        # Phase 1: Creative with stretch goals
        self.logger.info("V5 Phase 1: Creative Vision (stretch goal enabled)")
        blackboard.current_phase = Phase.CREATIVE
        metrics.start_phase("creative")

        creative_scores = []
        creative_score = 0.0
        stretch_reached = False

        for iteration in range(config.max_iterations):
            blackboard.iteration = iteration
            try:
                result = execute_expert("creative_expert", blackboard, metrics)
                if result.get("overall_success"):
                    blackboard.write(SectionID.CREATIVE_VISION, result.get("final_output", {}), author="creative_expert")
                    critic_result = execute_expert("critic", blackboard, metrics, step="build")
                    if critic_result.get("success"):
                        creative_score = extract_critic_score(critic_result["output"], "creative")
                        creative_scores.append(creative_score)

                        # Accumulate critic context
                        frame = create_critique_frame(
                            phase="creative", section_id="§2",
                            version=blackboard.get_version(SectionID.CREATIVE_VISION),
                            score=creative_score, threshold=config.quality_targets.creative,
                            feedback=critic_result["output"].get("feedback", "")
                        )
                        critic_context.accumulate_review(frame)

                        # Check targets
                        if creative_score >= config.quality_targets.stretch_threshold:
                            stretch_reached = True
                            self.logger.info(f"Creative STRETCH goal reached: {creative_score:.3f}")
                            break
                        elif creative_score >= config.quality_targets.creative:
                            if is_converged(creative_scores, config.convergence_window):
                                self.logger.info(f"Creative converged at {creative_score:.3f}")
                                break
                            # Try for stretch if not converged
                            self.logger.info(f"Creative target met ({creative_score:.3f}), pushing for stretch")
            except Exception as e:
                errors.append(f"Creative error: {e}")
                break

        metrics.end_phase("creative")

        # Phase 2: Technical with stretch goals
        self.logger.info("V5 Phase 2: Technical Approach")
        blackboard.current_phase = Phase.TECHNICAL
        metrics.start_phase("technical")

        technical_scores = []
        technical_score = 0.0

        for iteration in range(config.max_iterations):
            blackboard.iteration = iteration
            try:
                result = execute_expert("cg_expert", blackboard, metrics)
                if result.get("overall_success"):
                    blackboard.write(SectionID.TECHNICAL_APPROACH, result.get("final_output", {}), author="cg_expert")
                    critic_result = execute_expert("critic", blackboard, metrics, step="build")
                    if critic_result.get("success"):
                        technical_score = extract_critic_score(critic_result["output"], "technical")
                        technical_scores.append(technical_score)

                        if technical_score >= config.quality_targets.stretch_threshold:
                            self.logger.info(f"Technical STRETCH goal reached: {technical_score:.3f}")
                            break
                        elif technical_score >= config.quality_targets.technical:
                            if is_converged(technical_scores, config.convergence_window):
                                break
            except Exception as e:
                errors.append(f"Technical error: {e}")
                break

        metrics.end_phase("technical")

        # Phase 3: Design (highest bar - 0.90)
        self.logger.info("V5 Phase 3: Network Design (0.90 target)")
        blackboard.current_phase = Phase.DESIGN
        metrics.start_phase("design")

        design_scores = []
        design_score = 0.0

        for iteration in range(config.max_iterations):
            blackboard.iteration = iteration
            try:
                result = execute_expert("td_designer", blackboard, metrics)
                if result.get("overall_success"):
                    blackboard.write(SectionID.NETWORK_DESIGN, result.get("final_output", {}), author="td_designer")
                    critic_result = execute_expert("critic", blackboard, metrics, step="build")
                    if critic_result.get("success"):
                        design_score = extract_critic_score(critic_result["output"], "design")
                        design_scores.append(design_score)

                        if design_score >= config.quality_targets.stretch_threshold:
                            self.logger.info(f"Design STRETCH goal reached: {design_score:.3f}")
                            break
                        elif design_score >= config.quality_targets.design:
                            if is_converged(design_scores, config.convergence_window):
                                break
            except Exception as e:
                errors.append(f"Design error: {e}")
                break

        metrics.end_phase("design")

        # Phase 4: Build
        self.logger.info("V5 Phase 4: Build Artifacts")
        blackboard.current_phase = Phase.BUILD
        metrics.start_phase("build")

        toe_path = None
        try:
            result = execute_expert("network_builder", blackboard, metrics)
            if result.get("overall_success"):
                blackboard.write(SectionID.BUILD_ARTIFACTS, result.get("final_output", {}), author="network_builder")

                # Convert network design to TOE file
                try:
                    from .toe_builder_bridge import build_toe_from_design
                    network_design = blackboard.read(SectionID.NETWORK_DESIGN)
                    if network_design:
                        output_dir = Path(__file__).parent.parent.parent / "test_output" / blackboard.project_name
                        output_dir.mkdir(parents=True, exist_ok=True)
                        toe_path = build_toe_from_design(network_design, output_dir, blackboard.project_name)
                        if toe_path and toe_path.exists():
                            build_artifacts = blackboard.read(SectionID.BUILD_ARTIFACTS) or {}
                            build_artifacts["toe_path"] = str(toe_path)
                            blackboard.write(SectionID.BUILD_ARTIFACTS, build_artifacts, author="toe_builder")
                except Exception as e:
                    errors.append(f"TOE builder error: {e}")
        except Exception as e:
            errors.append(f"Build error: {e}")

        metrics.end_phase("build")
        blackboard.current_phase = Phase.COMPLETE

        success = creative_score >= config.quality_targets.creative and \
                  technical_score >= config.quality_targets.technical and \
                  design_score >= config.quality_targets.design

        return BuildResult(
            success=success and len(errors) == 0,
            toe_path=toe_path,
            blackboard=blackboard,
            errors=errors,
            quality_score=min(creative_score, technical_score, design_score) if success else None
        )

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "quality_targets": {
                    "type": "object",
                    "properties": {
                        "creative": {"type": "number", "default": 0.85},
                        "technical": {"type": "number", "default": 0.85},
                        "design": {"type": "number", "default": 0.90},
                        "stretch_threshold": {"type": "number", "default": 0.95}
                    }
                },
                "convergence_window": {"type": "integer", "default": 2},
                "max_iterations": {"type": "integer", "default": 20},
                "phase_reopening_enabled": {"type": "boolean", "default": True}
            }
        }


class V6UnifiedStrategy(BaseStrategy):
    """
    V6: Unified (all combined).

    Combines all approaches with configurable presets.
    Maximum quality with configurable complexity.

    Features:
        - Blackboard (V4): Central state management
        - Orchestrator (V2): Phase coordination
        - Evolutionary (V3): Variant spawning when exploration > 1
        - Deep Refinement (V5): Quality targets, stretch goals, convergence
        - Persistent Critic Context: Cross-phase understanding
        - Expert Pool: Domain expert consultation

    See docs/strategies/V6_UNIFIED.md for specification.
    """

    def __init__(self):
        super().__init__(name="v6")
        self.critic_context = None
        self.variant_spawner = None
        self.expert_pool = None

    def execute_workflow(
        self,
        prompt: str,
        blackboard: Blackboard,
        config: StrategyConfig,
        metrics: MetricsCollector
    ) -> BuildResult:
        """
        Execute V6 unified workflow.

        Combines:
        1. Blackboard (V4) as foundation for state management
        2. Orchestrator (V2) for phase coordination
        3. Evolutionary (V3) for variant exploration when exploration > 1
        4. Deep refinement (V5) for quality control with stretch goals
        5. Persistent critic context for cross-phase understanding
        6. Expert pool consultation during design phase
        """
        try:
            from .expert_executor import execute_expert
            from .kb_query import KnowledgeBase
            from .variant_spawner import VariantSpawner, create_variant_result
            from .critic_context import PersistentCriticContext, create_critique_frame
            from .expert_pool import ExpertPool, ExpertType
            from pathlib import Path
        except ImportError as e:
            self.logger.error(f"Failed to import required modules: {e}")
            return BuildResult(
                success=False,
                blackboard=blackboard,
                errors=[f"Import error: {str(e)}"]
            )

        errors = []

        # Initialize V6-specific components
        self.critic_context = PersistentCriticContext(project_name=blackboard.project_name)
        self.variant_spawner = VariantSpawner(breeding_threshold=0.05)
        expertise_path = Path(__file__).parent.parent / "expertise"
        self.expert_pool = ExpertPool(kb_path=expertise_path)

        # Update critic's project understanding
        self.critic_context.update_project_understanding("prompt", prompt[:200])
        self.critic_context.update_project_understanding("exploration_level", str(config.exploration))
        self.critic_context.update_project_understanding("quality_targets",
            f"creative={config.quality_targets.creative}, "
            f"technical={config.quality_targets.technical}, "
            f"design={config.quality_targets.design}"
        )

        self.logger.info(f"V6 workflow initialized: exploration={config.exploration}, "
                        f"stretch={config.quality_targets.stretch_threshold}")

        # ====================================================================
        # Phase 0: Query Knowledge Base
        # ====================================================================
        self.logger.info("Phase 0: Querying Knowledge Base")
        blackboard.current_phase = Phase.RESOURCES
        metrics.start_phase("resources")

        if config.kb_query_enabled:
            try:
                kb = KnowledgeBase(expertise_path)
                kb_results = self._query_knowledge_base(kb, prompt, metrics)
                blackboard.write(SectionID.AVAILABLE_RESOURCES, kb_results, author="kb_query")
                self.logger.info(f"KB query complete: {len(kb_results.get('operators', {}))} operator families")
            except Exception as e:
                self.logger.warning(f"KB query failed: {e}, continuing without KB data")
                errors.append(f"KB query warning: {str(e)}")

        metrics.end_phase("resources")

        # ====================================================================
        # Phase 1: Creative Vision
        # ====================================================================
        self.logger.info("Phase 1: Creative Vision")
        blackboard.current_phase = Phase.CREATIVE
        metrics.start_phase("creative")

        creative_result = self._execute_phase(
            phase_name="creative",
            section_id=SectionID.CREATIVE_VISION,
            expert_name="creative_expert",
            quality_target=config.quality_targets.creative,
            stretch_target=config.quality_targets.stretch_threshold,
            blackboard=blackboard,
            config=config,
            metrics=metrics,
            errors=errors
        )

        metrics.end_phase("creative")

        if not creative_result["passed"]:
            self.logger.error("Creative phase failed to meet minimum target")
            errors.append(f"Creative phase failed: score {creative_result['score']:.3f} "
                         f"< target {config.quality_targets.creative}")

        # ====================================================================
        # Phase 2: Technical Approach
        # ====================================================================
        self.logger.info("Phase 2: Technical Approach")
        blackboard.current_phase = Phase.TECHNICAL
        metrics.start_phase("technical")

        technical_result = self._execute_phase(
            phase_name="technical",
            section_id=SectionID.TECHNICAL_APPROACH,
            expert_name="cg_expert",
            quality_target=config.quality_targets.technical,
            stretch_target=config.quality_targets.stretch_threshold,
            blackboard=blackboard,
            config=config,
            metrics=metrics,
            errors=errors
        )

        metrics.end_phase("technical")

        if not technical_result["passed"]:
            self.logger.error("Technical phase failed to meet minimum target")
            errors.append(f"Technical phase failed: score {technical_result['score']:.3f} "
                         f"< target {config.quality_targets.technical}")

        # ====================================================================
        # Phase 3: Network Design (with Expert Pool)
        # ====================================================================
        self.logger.info("Phase 3: Network Design")
        blackboard.current_phase = Phase.DESIGN
        metrics.start_phase("design")

        # Inject expert pool context before design phase
        expert_context = self.expert_pool.get_expert_context_for_design(blackboard)
        existing_resources = blackboard.read(SectionID.AVAILABLE_RESOURCES) or {}
        blackboard.write(
            SectionID.AVAILABLE_RESOURCES,
            {**existing_resources, "expert_context": expert_context},
            author="expert_pool"
        )

        design_result = self._execute_phase(
            phase_name="design",
            section_id=SectionID.NETWORK_DESIGN,
            expert_name="td_designer",
            quality_target=config.quality_targets.design,
            stretch_target=config.quality_targets.stretch_threshold,
            blackboard=blackboard,
            config=config,
            metrics=metrics,
            errors=errors
        )

        metrics.end_phase("design")

        # Check if design reveals issues requiring phase reopening
        if design_result["requires_reopen"]:
            reopen_phase = design_result.get("reopen_phase")
            self.logger.warning(f"Design phase suggests reopening {reopen_phase} phase")
            self.critic_context.add_concern(f"Phase {reopen_phase} may need rework based on design feedback")
            # Note: Full phase reopening would require recursive call - simplified for now

        if not design_result["passed"]:
            self.logger.error("Design phase failed to meet minimum target")
            errors.append(f"Design phase failed: score {design_result['score']:.3f} "
                         f"< target {config.quality_targets.design}")

        # ====================================================================
        # Phase 4: Build Artifacts
        # ====================================================================
        self.logger.info("Phase 4: Build Artifacts")
        blackboard.current_phase = Phase.BUILD
        metrics.start_phase("build")

        toe_path = None
        try:
            builder_result = execute_expert("network_builder", blackboard, metrics)
            if builder_result.get("overall_success"):
                blackboard.write(
                    SectionID.BUILD_ARTIFACTS,
                    builder_result["final_output"],
                    author="network_builder"
                )
                self.logger.info("Network builder completed successfully")

                # Convert network design to TOE file
                self.logger.info("Converting network design to TOE file")
                try:
                    from .toe_builder_bridge import build_toe_from_design
                    network_design = blackboard.read(SectionID.NETWORK_DESIGN)
                    if network_design:
                        output_dir = Path(__file__).parent.parent.parent / "test_output" / blackboard.project_name
                        output_dir.mkdir(parents=True, exist_ok=True)
                        toe_path = build_toe_from_design(network_design, output_dir, blackboard.project_name)
                        if toe_path and toe_path.exists():
                            self.logger.info(f"TOE file created: {toe_path}")
                            build_artifacts = blackboard.read(SectionID.BUILD_ARTIFACTS) or {}
                            build_artifacts["toe_path"] = str(toe_path)
                            build_artifacts["toe_size_bytes"] = toe_path.stat().st_size
                            blackboard.write(SectionID.BUILD_ARTIFACTS, build_artifacts, author="toe_builder")
                        else:
                            errors.append("TOE file generation failed")
                except Exception as e:
                    self.logger.error(f"TOE builder failed: {e}")
                    errors.append(f"TOE builder error: {str(e)}")
            else:
                self.logger.error("Network builder failed")
                errors.append("Network builder failed to generate artifacts")
        except Exception as e:
            self.logger.error(f"Network builder failed: {e}")
            errors.append(f"Network builder error: {str(e)}")

        metrics.end_phase("build")

        # ====================================================================
        # Finalize
        # ====================================================================
        blackboard.current_phase = Phase.COMPLETE

        # Determine success
        all_phases_passed = (
            creative_result["passed"] and
            technical_result["passed"] and
            design_result["passed"]
        )

        # Calculate final quality score
        final_quality_score = min(
            creative_result["score"],
            technical_result["score"],
            design_result["score"]
        ) if all_phases_passed else None

        # Get TOE path if available
        build_artifacts = blackboard.read(SectionID.BUILD_ARTIFACTS)
        toe_path = None
        if build_artifacts and "toe_path" in build_artifacts:
            toe_path = Path(build_artifacts["toe_path"])

        # Store critic context summary in blackboard
        blackboard.write(
            SectionID.BUILD_ARTIFACTS,
            {
                **(build_artifacts or {}),
                "critic_context": self.critic_context.to_dict(),
                "expert_consultations": self.expert_pool.get_consultation_history()
            },
            author="v6_finalize"
        )

        self.logger.info(f"V6 workflow complete. Success: {all_phases_passed}, "
                        f"Final quality: {final_quality_score:.3f if final_quality_score else 'N/A'}")

        return BuildResult(
            success=all_phases_passed and len(errors) == 0,
            toe_path=toe_path,
            blackboard=blackboard,
            errors=errors,
            quality_score=final_quality_score
        )

    def _execute_phase(
        self,
        phase_name: str,
        section_id: SectionID,
        expert_name: str,
        quality_target: float,
        stretch_target: Optional[float],
        blackboard: Blackboard,
        config: StrategyConfig,
        metrics: MetricsCollector,
        errors: list
    ) -> dict:
        """
        Execute a single phase with V6 features.

        Returns dict with:
            - passed: bool
            - score: float
            - iterations: int
            - reached_stretch: bool
            - requires_reopen: bool
            - reopen_phase: Optional[str]
        """
        from .expert_executor import execute_expert
        from .variant_spawner import create_variant_result
        from .critic_context import create_critique_frame

        result = {
            "passed": False,
            "score": 0.0,
            "iterations": 0,
            "reached_stretch": False,
            "requires_reopen": False,
            "reopen_phase": None
        }

        # Get critic context for this phase
        critic_context_str = self.critic_context.get_context_for_phase(phase_name)
        self.logger.debug(f"Critic context for {phase_name}: {len(critic_context_str)} chars")

        for iteration in range(config.max_iterations):
            blackboard.iteration = iteration
            result["iterations"] = iteration + 1

            self.logger.info(f"{phase_name.upper()} iteration {iteration + 1}/{config.max_iterations}")

            # Check for convergence (V5 feature)
            if iteration > 0 and self.critic_context.is_converged(phase_name, config.convergence_window):
                self.logger.info(f"{phase_name} converged after {iteration + 1} iterations")
                break

            try:
                # Execute expert(s) - with variants if exploration > 1
                if config.exploration > 1:
                    # Evolutionary (V3): Spawn multiple variants
                    best_output, best_score = self._execute_with_variants(
                        phase_name=phase_name,
                        expert_name=expert_name,
                        n_variants=config.exploration,
                        blackboard=blackboard,
                        metrics=metrics
                    )
                else:
                    # Single execution
                    expert_result = execute_expert(expert_name, blackboard, metrics)
                    best_output = expert_result.get("final_output", {})
                    best_score = 0.0  # Will be set by critic

                if best_output:
                    # Write to blackboard
                    blackboard.write(section_id, best_output, author=expert_name)

                    # Run critic
                    critic_result = execute_expert("critic", blackboard, metrics, step="build")

                    if critic_result.get("success") and "output" in critic_result:
                        critic_output = critic_result["output"]
                        score = extract_critic_score(critic_output, phase_name)

                        result["score"] = score
                        self.logger.info(f"{phase_name} score: {score:.3f} (target: {quality_target:.2f})")
                        metrics.record_score(phase_name, score)

                        # Accumulate critic frame (V6 persistent context)
                        frame = create_critique_frame(
                            phase=phase_name,
                            section_id=str(section_id.value) if hasattr(section_id, 'value') else str(section_id),
                            version=blackboard.get_version(section_id),
                            score=score,
                            threshold=quality_target,
                            feedback=critic_output.get("feedback", ""),
                            issues=critic_output.get("issues", [])
                        )
                        self.critic_context.accumulate_review(frame)

                        # Check for cross-phase issues (phase reopening)
                        if phase_name == "design":
                            for issue in critic_output.get("issues", []):
                                root_cause = self.critic_context.detect_cross_phase_issue(
                                    phase_name, issue.get("description", "")
                                )
                                if root_cause:
                                    result["requires_reopen"] = True
                                    result["reopen_phase"] = root_cause.value
                                    self.logger.warning(f"Issue in {phase_name} traced to {root_cause.value}")

                        # Check if passed
                        if score >= quality_target:
                            result["passed"] = True
                            self.logger.info(f"{phase_name} passed quality target")

                            # Check stretch goal (V5 feature)
                            if stretch_target and score < stretch_target:
                                # Try for stretch goal if not yet reached
                                if iteration < config.max_iterations - 1:
                                    self.logger.info(f"Attempting stretch goal: {stretch_target:.2f}")
                                    continue  # Try one more iteration for stretch
                            elif stretch_target and score >= stretch_target:
                                result["reached_stretch"] = True
                                self.logger.info(f"{phase_name} reached STRETCH goal: {score:.3f}")
                                break  # Excellent, stop iterating
                            else:
                                break  # No stretch or already good enough

                metrics.record_iteration(phase_name)

            except Exception as e:
                self.logger.error(f"{phase_name} expert failed: {e}")
                errors.append(f"{phase_name} error: {str(e)}")
                break

        return result

    def _execute_with_variants(
        self,
        phase_name: str,
        expert_name: str,
        n_variants: int,
        blackboard: Blackboard,
        metrics: MetricsCollector
    ) -> tuple[dict, float]:
        """
        Execute expert with multiple variants (V3 evolutionary).

        Returns:
            Tuple of (best_output, best_score)
        """
        from .expert_executor import execute_expert
        from .variant_spawner import create_variant_result

        # Spawn variant configs
        configs = self.variant_spawner.spawn_variants(
            n=n_variants,
            phase=phase_name,
            base_context={"blackboard_state": blackboard.to_dict()}
        )

        self.logger.info(f"Spawned {len(configs)} variants for {phase_name}")

        # Execute each variant
        variant_results = []
        for config in configs:
            # Add directive to blackboard context temporarily
            original_context = blackboard.read(SectionID.AVAILABLE_RESOURCES) or {}
            blackboard.write(
                SectionID.AVAILABLE_RESOURCES,
                {**original_context, "variant_directive": config.get_directive_prompt()},
                author="variant_spawner"
            )

            # Execute expert
            expert_result = execute_expert(expert_name, blackboard, metrics)

            if expert_result.get("overall_success"):
                output = expert_result.get("final_output", {})

                # Quick critic score for ranking
                critic_result = execute_expert("critic", blackboard, metrics, step="build")
                score = 0.0
                if critic_result.get("success") and "output" in critic_result:
                    score = extract_critic_score(critic_result["output"], phase_name)

                variant_result = create_variant_result(
                    config=config,
                    content=output,
                    score=score,
                    critic_feedback=critic_result.get("output", {}).get("feedback", ""),
                    strengths=critic_result.get("output", {}).get("strengths", []),
                    weaknesses=critic_result.get("output", {}).get("weaknesses", [])
                )
                variant_results.append(variant_result)

            # Restore original context
            blackboard.write(SectionID.AVAILABLE_RESOURCES, original_context, author="variant_spawner")

        if not variant_results:
            self.logger.warning(f"No successful variants for {phase_name}")
            return {}, 0.0

        # Rank variants
        ranked = self.variant_spawner.rank_variants(variant_results)

        # Check if we should breed top two
        if len(ranked) >= 2 and self.variant_spawner.should_breed(ranked[0], ranked[1]):
            bred = self.variant_spawner.breed_variants(ranked[0], ranked[1])
            self.logger.info(f"Bred variants: {bred.child_id}")
            return bred.merged_content, (ranked[0].score + ranked[1].score) / 2

        # Return best variant
        winner = self.variant_spawner.select_winner(ranked)
        return winner.content, winner.score

    def _query_knowledge_base(self, kb, prompt: str, metrics: MetricsCollector) -> dict:
        """Query KB for relevant expertise based on prompt."""
        kb_results = {
            "operators": {},
            "patterns": [],
            "glsl": {},
            "palette_recommendations": [],  # NEW: Palette-first approach
            "query_timestamp": metrics.started_at
        }

        prompt_lower = prompt.lower()

        # ===========================================
        # PALETTE-FIRST: Check for pre-built solutions
        # ===========================================
        try:
            palette_recs = kb.get_palette_recommendations_for_prompt(prompt)
            if palette_recs:
                kb_results["palette_recommendations"] = palette_recs
                self.logger.info(
                    f"Found {len(palette_recs)} palette recommendations: "
                    f"{[p['name'] for p in palette_recs[:5]]}"
                )
        except Exception as e:
            self.logger.warning(f"Palette query failed: {e}")

        # Query audio operators
        if any(kw in prompt_lower for kw in ["audio", "sound", "music", "beat"]):
            chop_ops = kb.query_operators({"family": "CHOP", "purpose_contains": "audio"})
            kb_results["operators"]["audio_chops"] = chop_ops[:10]

        # Query TOP operators
        if any(kw in prompt_lower for kw in ["visual", "particle", "image", "video", "render"]):
            top_ops = kb.query_operators({"family": "TOP"})
            kb_results["operators"]["tops"] = top_ops[:15]

        # Query SOP operators for geometry
        if any(kw in prompt_lower for kw in ["geometry", "mesh", "3d", "sop"]):
            sop_ops = kb.query_operators({"family": "SOP"})
            kb_results["operators"]["sops"] = sop_ops[:10]

        # Query common CHOP operators
        chop_ops = kb.query_operators({"family": "CHOP"})
        kb_results["operators"]["chops"] = chop_ops[:10]

        # Query patterns
        if "audio" in prompt_lower or "reactive" in prompt_lower:
            audio_patterns = kb.query_patterns("audio_reactive_visuals")
            kb_results["patterns"].extend(audio_patterns)

        if "particle" in prompt_lower:
            particle_patterns = kb.query_patterns("particle_system")
            kb_results["patterns"].extend(particle_patterns)

        # Query GLSL
        if any(kw in prompt_lower for kw in ["shader", "glsl", "material", "compute"]):
            glsl_top = kb.query_glsl("glsl_top")
            kb_results["glsl"]["glsl_top"] = glsl_top

        return kb_results

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "preset": {
                    "type": "string",
                    "enum": ["quick_draft", "standard", "excellence", "custom"],
                    "default": "standard"
                },
                "involvement": {
                    "type": "string",
                    "enum": ["full", "milestone", "minimal"]
                },
                "exploration": {
                    "type": "integer",
                    "enum": [1, 3, 5]
                },
                "quality_targets": {
                    "type": "object",
                    "properties": {
                        "creative": {"type": "number"},
                        "technical": {"type": "number"},
                        "design": {"type": "number"}
                    }
                },
                "stretch": {
                    "type": "object",
                    "properties": {
                        "threshold": {"type": "number"},
                        "enabled": {"type": "boolean"}
                    }
                },
                "max_iterations": {"type": "integer"},
                "convergence_window": {"type": "integer"},
                "critic": {
                    "type": "object",
                    "properties": {
                        "persistent_context": {"type": "boolean", "default": True},
                        "multi_perspective": {
                            "type": "object",
                            "properties": {
                                "enabled": {"type": "boolean", "default": True},
                                "for_phases": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "default": ["design"]
                                }
                            }
                        }
                    }
                }
            }
        }


# ============================================================================
# Strategy Registry
# ============================================================================


class StrategyRegistry:
    """
    Registry for workflow strategies.

    Manages registration and retrieval of strategies by name.

    Usage:
        registry = StrategyRegistry()
        registry.register(V2ImprovedStrategy())
        strategy = registry.get("v2")
        result = strategy.execute(prompt, blackboard, config)
    """

    def __init__(self):
        self._strategies: dict[str, WorkflowStrategy] = {}
        self.logger = logging.getLogger(f"{__name__}.StrategyRegistry")

    def register(self, strategy: WorkflowStrategy):
        """Register a strategy."""
        if not isinstance(strategy, WorkflowStrategy):
            raise TypeError(f"Strategy must implement WorkflowStrategy protocol")

        self._strategies[strategy.name] = strategy
        self.logger.info(f"Registered strategy: {strategy.name}")

    def get(self, name: str) -> Optional[WorkflowStrategy]:
        """Get a strategy by name."""
        return self._strategies.get(name)

    def list_strategies(self) -> list[str]:
        """List all registered strategy names."""
        return list(self._strategies.keys())

    def has_strategy(self, name: str) -> bool:
        """Check if a strategy is registered."""
        return name in self._strategies


# Global registry instance
_global_registry = StrategyRegistry()


def get_registry() -> StrategyRegistry:
    """Get the global strategy registry."""
    return _global_registry


def register_all_strategies():
    """Register all built-in strategies.

    V0 is intentionally NOT registered — V0BaselineStrategy.execute_workflow
    returns `BuildResult(success=False, errors=["V0 strategy implementation
    pending"])` and was misleading callers who thought they had a baseline.
    Class definition is retained at line 544 for spec/docs but is not
    runnable via `run_strategy("v0", ...)` (raises ValueError instead).
    """
    registry = get_registry()
    registry.register(V2ImprovedStrategy())
    registry.register(V3EvolutionaryStrategy())
    registry.register(V4BlackboardStrategy())
    registry.register(V5DeepRefinementStrategy())
    registry.register(V6UnifiedStrategy())


# Auto-register on import
register_all_strategies()


# ============================================================================
# Convenience Function
# ============================================================================


def run_strategy(
    strategy_name: str,
    prompt: str,
    config: Optional[StrategyConfig] = None,
    project_name: Optional[str] = None,
    persist_path: Optional[Path] = None
) -> BuildResult:
    """
    Run a workflow strategy by name.

    This is the main entry point for executing strategies.

    Args:
        strategy_name: Name of strategy to run ("v0", "v2", etc.)
        prompt: User's request/prompt
        config: Strategy configuration (defaults to STANDARD preset)
        project_name: Optional project name (auto-generated if not provided)
        persist_path: Optional path to persist blackboard state

    Returns:
        BuildResult with execution outcome

    Raises:
        ValueError: If strategy not found

    Example:
        >>> result = run_strategy(
        ...     "v2",
        ...     "Create an audio-reactive particle system",
        ...     config=StrategyConfig.from_preset(Preset.STANDARD)
        ... )
        >>> if result.success:
        ...     print(f"Generated TOE: {result.toe_path}")
    """
    # Get strategy from registry
    registry = get_registry()
    strategy = registry.get(strategy_name)

    if not strategy:
        available = registry.list_strategies()
        raise ValueError(
            f"Strategy '{strategy_name}' not found. "
            f"Available strategies: {', '.join(available)}"
        )

    # Use default config if not provided
    if config is None:
        config = StrategyConfig.from_preset(Preset.STANDARD)

    # Generate project name if not provided
    if project_name is None:
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        project_name = f"{strategy_name}_{timestamp}"

    # Create blackboard
    blackboard = Blackboard(
        project_name=project_name,
        persist_path=persist_path
    )

    # Execute strategy
    logger.info(f"Running {strategy_name} strategy for project: {project_name}")
    result = strategy.execute(prompt, blackboard, config)

    return result

"""
Variant Spawner: Evolutionary exploration for V6 workflow.

This module provides the ability to spawn multiple variants of expert outputs,
rank them using critic scoring, and breed the best aspects together.

Used by V6UnifiedStrategy when exploration > 1.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)


class VariantDirective(Enum):
    """Directives for variant generation - personality/approach hints."""
    # Creative directives
    BOLD = "bold"
    REFINED = "refined"
    UNEXPECTED = "unexpected"
    EMOTIONAL = "emotional"
    TECHNICAL = "technical"

    # Technical directives
    PERFORMANCE = "performance"
    QUALITY = "quality"
    FLEXIBILITY = "flexibility"

    # Design directives
    MODULAR = "modular"
    OPTIMIZED = "optimized"
    EXTENSIBLE = "extensible"


# Default directives per phase
DEFAULT_DIRECTIVES = {
    "creative": [VariantDirective.BOLD, VariantDirective.REFINED, VariantDirective.UNEXPECTED],
    "technical": [VariantDirective.PERFORMANCE, VariantDirective.QUALITY, VariantDirective.FLEXIBILITY],
    "design": [VariantDirective.MODULAR, VariantDirective.OPTIMIZED, VariantDirective.EXTENSIBLE],
}


@dataclass
class VariantConfig:
    """Configuration for a single variant."""
    variant_id: str
    directive: VariantDirective
    phase: str
    context_overrides: dict = field(default_factory=dict)
    prompt_suffix: str = ""

    def get_directive_prompt(self) -> str:
        """Get the prompt modifier for this directive."""
        directive_prompts = {
            VariantDirective.BOLD: "Be bold and experimental. Push boundaries. Surprise the audience.",
            VariantDirective.REFINED: "Be refined and elegant. Focus on polish and coherence.",
            VariantDirective.UNEXPECTED: "Find unexpected angles. What would no one else think of?",
            VariantDirective.EMOTIONAL: "Prioritize emotional impact. What will people FEEL?",
            VariantDirective.TECHNICAL: "Focus on technical excellence. Precision and correctness.",
            VariantDirective.PERFORMANCE: "Optimize for performance. Minimize GPU/CPU load.",
            VariantDirective.QUALITY: "Maximize visual quality. Best possible output.",
            VariantDirective.FLEXIBILITY: "Design for flexibility. Easy to modify and extend.",
            VariantDirective.MODULAR: "Create modular, reusable components.",
            VariantDirective.OPTIMIZED: "Optimize signal flow and cooking order.",
            VariantDirective.EXTENSIBLE: "Design for future extension and modification.",
        }
        return directive_prompts.get(self.directive, "")


@dataclass
class VariantResult:
    """Result from a variant execution."""
    variant_id: str
    directive: VariantDirective
    content: dict
    score: float
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    critic_feedback: str = ""

    def __lt__(self, other: "VariantResult") -> bool:
        """Enable sorting by score (descending)."""
        return self.score > other.score  # Higher score = better


@dataclass
class BreedingResult:
    """Result from breeding two variants."""
    parent_a_id: str
    parent_b_id: str
    child_id: str
    merged_content: dict
    breeding_notes: str
    inherited_strengths: list[str] = field(default_factory=list)


class VariantSpawner:
    """
    Spawns and manages variant exploration.

    Usage:
        spawner = VariantSpawner()

        # Spawn variants
        configs = spawner.spawn_variants(3, "creative", base_context)

        # Execute each variant (external)
        results = [execute_variant(c) for c in configs]

        # Rank variants
        ranked = spawner.rank_variants(results)

        # Breed top variants if close
        if spawner.should_breed(ranked[0], ranked[1]):
            bred = spawner.breed_variants(ranked[0], ranked[1])
    """

    def __init__(self, breeding_threshold: float = 0.05):
        """
        Initialize the spawner.

        Args:
            breeding_threshold: Score difference threshold for breeding.
                               If top two variants are within this range, breed them.
        """
        self.breeding_threshold = breeding_threshold
        self.variant_counter = 0
        self.logger = logging.getLogger(f"{__name__}.VariantSpawner")

    def spawn_variants(
        self,
        n: int,
        phase: str,
        base_context: dict,
        custom_directives: Optional[list[VariantDirective]] = None
    ) -> list[VariantConfig]:
        """
        Spawn N variant configurations.

        Args:
            n: Number of variants to spawn (typically 1, 3, or 5)
            phase: Current phase (creative, technical, design)
            base_context: Base context to be shared across variants
            custom_directives: Optional custom directives (uses defaults if None)

        Returns:
            List of VariantConfig objects
        """
        if n < 1:
            raise ValueError("Must spawn at least 1 variant")

        # Get directives for this phase
        if custom_directives:
            directives = custom_directives[:n]
        else:
            directives = DEFAULT_DIRECTIVES.get(phase, list(VariantDirective)[:n])

        # Extend with defaults if needed
        while len(directives) < n:
            directives.append(directives[-1])

        configs = []
        for i, directive in enumerate(directives[:n]):
            self.variant_counter += 1
            variant_id = f"{phase}_v{self.variant_counter}_{directive.value}"

            config = VariantConfig(
                variant_id=variant_id,
                directive=directive,
                phase=phase,
                context_overrides={},
                prompt_suffix=f"\n\nDIRECTIVE: {directive.get_directive_prompt()}"
            )
            configs.append(config)

        self.logger.info(f"Spawned {n} variants for {phase}: {[c.variant_id for c in configs]}")
        return configs

    def rank_variants(self, results: list[VariantResult]) -> list[VariantResult]:
        """
        Rank variants by score (descending).

        Args:
            results: List of variant results with scores

        Returns:
            Sorted list (highest score first)
        """
        ranked = sorted(results)  # Uses __lt__ defined above

        self.logger.info(
            f"Ranked {len(ranked)} variants: "
            f"{[(r.variant_id, f'{r.score:.3f}') for r in ranked]}"
        )

        return ranked

    def should_breed(self, top: VariantResult, second: VariantResult) -> bool:
        """
        Determine if top two variants should be bred.

        Args:
            top: Highest-scoring variant
            second: Second-highest variant

        Returns:
            True if they should be bred (scores are close)
        """
        score_diff = abs(top.score - second.score)
        should = score_diff <= self.breeding_threshold

        self.logger.info(
            f"Breeding check: {top.variant_id}({top.score:.3f}) vs "
            f"{second.variant_id}({second.score:.3f}), diff={score_diff:.3f}, "
            f"threshold={self.breeding_threshold}, breed={should}"
        )

        return should

    def breed_variants(
        self,
        parent_a: VariantResult,
        parent_b: VariantResult,
        merge_fn: Optional[Callable[[dict, dict, list[str], list[str]], dict]] = None
    ) -> BreedingResult:
        """
        Breed two variants by merging their best aspects.

        Args:
            parent_a: First parent variant (typically higher score)
            parent_b: Second parent variant
            merge_fn: Optional custom merge function. If None, uses default merge.

        Returns:
            BreedingResult with merged content
        """
        child_id = f"bred_{parent_a.variant_id}_{parent_b.variant_id}"

        # Collect strengths from both
        all_strengths = parent_a.strengths + parent_b.strengths

        # Default merge: take parent_a as base, overlay selected aspects from parent_b
        if merge_fn:
            merged = merge_fn(
                parent_a.content,
                parent_b.content,
                parent_a.strengths,
                parent_b.strengths
            )
        else:
            merged = self._default_merge(parent_a, parent_b)

        breeding_notes = (
            f"Merged {parent_a.directive.value} (score={parent_a.score:.3f}) "
            f"with {parent_b.directive.value} (score={parent_b.score:.3f}). "
            f"Inherited: {', '.join(all_strengths[:5])}"
        )

        result = BreedingResult(
            parent_a_id=parent_a.variant_id,
            parent_b_id=parent_b.variant_id,
            child_id=child_id,
            merged_content=merged,
            breeding_notes=breeding_notes,
            inherited_strengths=all_strengths
        )

        self.logger.info(f"Bred variants: {breeding_notes}")
        return result

    def _default_merge(self, a: VariantResult, b: VariantResult) -> dict:
        """
        Default merge strategy: deep merge with A taking priority.

        For creative phases, we prefer to merge specific sections.
        """
        merged = dict(a.content)

        # For each key in B that A doesn't have or B does better
        for key, value in b.content.items():
            if key not in merged:
                merged[key] = value
            elif isinstance(value, dict) and isinstance(merged.get(key), dict):
                # Deep merge dicts
                merged[key] = {**merged[key], **value}
            elif isinstance(value, list) and isinstance(merged.get(key), list):
                # Combine lists, dedupe
                combined = merged[key] + [v for v in value if v not in merged[key]]
                merged[key] = combined

        # Add breeding metadata
        merged["_breeding_info"] = {
            "parent_a": a.variant_id,
            "parent_b": b.variant_id,
            "parent_a_score": a.score,
            "parent_b_score": b.score,
        }

        return merged

    def select_winner(self, ranked: list[VariantResult]) -> VariantResult:
        """
        Select the winning variant (highest score).

        Args:
            ranked: Ranked list of variants (highest first)

        Returns:
            The winning variant
        """
        winner = ranked[0]
        self.logger.info(f"Selected winner: {winner.variant_id} (score={winner.score:.3f})")
        return winner


def create_variant_result(
    config: VariantConfig,
    content: dict,
    score: float,
    critic_feedback: str = "",
    strengths: Optional[list[str]] = None,
    weaknesses: Optional[list[str]] = None
) -> VariantResult:
    """
    Helper to create a VariantResult from execution output.

    Args:
        config: The variant config that was executed
        content: The generated content
        score: Critic score (0.0-1.0)
        critic_feedback: Full critic feedback
        strengths: Identified strengths (extracted from feedback if None)
        weaknesses: Identified weaknesses (extracted from feedback if None)

    Returns:
        VariantResult ready for ranking
    """
    return VariantResult(
        variant_id=config.variant_id,
        directive=config.directive,
        content=content,
        score=score,
        strengths=strengths or [],
        weaknesses=weaknesses or [],
        critic_feedback=critic_feedback
    )


__all__ = [
    "VariantDirective",
    "VariantConfig",
    "VariantResult",
    "BreedingResult",
    "VariantSpawner",
    "create_variant_result",
    "DEFAULT_DIRECTIVES",
]

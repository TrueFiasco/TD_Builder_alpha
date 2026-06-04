"""
Expert Pool: Shared domain experts for V6 design phase.

This module provides a pool of specialized experts that can be consulted
during the design phase to provide implementation details:

- GLSL Expert: Shader code and GPU optimization
- Python Expert: DAT scripts and extensions
- Palette Expert: Reusable component selection

Used by V6UnifiedStrategy during design phase for expert consultation.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Callable
import logging

logger = logging.getLogger(__name__)


class ExpertType(Enum):
    """Types of domain experts available."""
    GLSL = "glsl"
    PYTHON = "python"
    PALETTE = "palette"
    CHOP = "chop"
    TOP = "top"
    SOP = "sop"


@dataclass
class ExpertQuery:
    """A query to a domain expert."""
    expert_type: ExpertType
    question: str
    context: dict = field(default_factory=dict)
    phase: str = "design"
    blocking: bool = False  # If True, must answer before proceeding


@dataclass
class ExpertResponse:
    """Response from a domain expert."""
    expert_type: ExpertType
    question: str
    answer: str
    code_snippets: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.8


@dataclass
class ExpertConsultation:
    """Record of a consultation with an expert."""
    query: ExpertQuery
    response: ExpertResponse
    timestamp: str = ""


@dataclass
class PaletteComponent:
    """A palette component recommendation."""
    name: str
    category: str
    purpose: str
    tox_path: str
    use_cases: list[str] = field(default_factory=list)
    wiki_url: str = ""
    relevance_score: float = 0.0


class ExpertPool:
    """
    Pool of domain experts for consultation during design phase.

    Usage:
        pool = ExpertPool(kb_path)

        # Single query
        response = pool.consult(ExpertType.GLSL, "How do I implement bloom?")

        # Batch queries
        responses = pool.batch_consult([
            ExpertQuery(ExpertType.GLSL, "Bloom shader?"),
            ExpertQuery(ExpertType.PYTHON, "CHOP execute?"),
        ])

        # Find palette solutions BEFORE designing custom networks
        palette_matches = pool.find_palette_solutions(["audio", "beat", "particles"])

        # Get context for TD Designer prompt
        context = pool.get_expert_context_for_design(blackboard)
    """

    def __init__(self, kb_path: Optional[Path] = None):
        """
        Initialize the expert pool.

        Args:
            kb_path: Path to knowledge base expertise files
        """
        self.kb_path = kb_path or Path(__file__).parent.parent / "expertise"
        self.consultations: list[ExpertConsultation] = []
        self.expertise_cache: dict[ExpertType, dict] = {}
        self.palette_catalog: dict[str, dict] = {}  # Full palette catalog
        self.logger = logging.getLogger(f"{__name__}.ExpertPool")

        # Load expertise on init
        self._load_expertise()
        self._load_palette_catalog()

    def _load_expertise(self) -> None:
        """Load expertise files into cache."""
        expertise_files = {
            ExpertType.GLSL: "td_glsl.yaml",
            ExpertType.PYTHON: "td_python.yaml",
            ExpertType.PALETTE: "td_network_patterns.yaml",
            ExpertType.CHOP: "td_operators.yaml",
            ExpertType.TOP: "td_operators.yaml",
            ExpertType.SOP: "td_operators.yaml",
        }

        for expert_type, filename in expertise_files.items():
            filepath = self.kb_path / filename
            if filepath.exists():
                try:
                    import yaml
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self.expertise_cache[expert_type] = yaml.safe_load(f) or {}
                    self.logger.debug(f"Loaded expertise for {expert_type.value}")
                except Exception as e:
                    self.logger.warning(f"Failed to load {filepath}: {e}")

    def _load_palette_catalog(self) -> None:
        """Load the full palette semantic catalog (278 components)."""
        catalog_path = self.kb_path / "palette_semantic_catalog.yaml"
        if catalog_path.exists():
            try:
                import yaml
                with open(catalog_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                # Remove metadata, keep only components
                self.palette_catalog = {
                    k: v for k, v in data.items()
                    if not k.startswith('_')
                }
                self.logger.info(f"Loaded palette catalog: {len(self.palette_catalog)} components")
            except Exception as e:
                self.logger.warning(f"Failed to load palette catalog: {e}")
        else:
            self.logger.warning(f"Palette catalog not found at {catalog_path}")

    def consult(
        self,
        expert_type: ExpertType,
        question: str,
        context: Optional[dict] = None,
        executor: Optional[Callable] = None
    ) -> ExpertResponse:
        """
        Consult a domain expert with a question.

        Args:
            expert_type: Type of expert to consult
            question: The question to ask
            context: Optional context (blackboard sections, etc.)
            executor: Optional LLM executor for complex queries

        Returns:
            ExpertResponse with answer and recommendations
        """
        query = ExpertQuery(
            expert_type=expert_type,
            question=question,
            context=context or {},
        )

        # Try to answer from KB first
        kb_response = self._query_kb(expert_type, question)
        if kb_response:
            response = ExpertResponse(
                expert_type=expert_type,
                question=question,
                answer=kb_response["answer"],
                code_snippets=kb_response.get("code_snippets", []),
                recommendations=kb_response.get("recommendations", []),
                confidence=0.9,  # High confidence from KB
            )
        elif executor:
            # Fall back to LLM if KB doesn't have answer
            response = self._query_llm(query, executor)
        else:
            # Return empty response if no executor
            response = ExpertResponse(
                expert_type=expert_type,
                question=question,
                answer="No answer available. KB did not contain relevant information.",
                confidence=0.0,
            )

        # Record consultation
        from datetime import datetime
        self.consultations.append(ExpertConsultation(
            query=query,
            response=response,
            timestamp=datetime.utcnow().isoformat(),
        ))

        self.logger.info(
            f"Consulted {expert_type.value} expert: "
            f"'{question[:50]}...' -> confidence={response.confidence:.2f}"
        )

        return response

    def _query_kb(self, expert_type: ExpertType, question: str) -> Optional[dict]:
        """
        Query the knowledge base for an answer.

        Returns dict with answer, code_snippets, recommendations if found.
        """
        expertise = self.expertise_cache.get(expert_type, {})
        if not expertise:
            return None

        question_lower = question.lower()

        # GLSL-specific queries
        if expert_type == ExpertType.GLSL:
            return self._query_glsl_kb(expertise, question_lower)

        # Python-specific queries
        if expert_type == ExpertType.PYTHON:
            return self._query_python_kb(expertise, question_lower)

        # Pattern/palette queries
        if expert_type == ExpertType.PALETTE:
            return self._query_pattern_kb(expertise, question_lower)

        # Operator queries
        if expert_type in [ExpertType.CHOP, ExpertType.TOP, ExpertType.SOP]:
            return self._query_operator_kb(expertise, question_lower, expert_type)

        return None

    def _query_glsl_kb(self, expertise: dict, question: str) -> Optional[dict]:
        """Query GLSL expertise."""
        # Look for shader patterns, uniforms, functions
        glsl_patterns = expertise.get("glsl_patterns", {})
        uniforms = expertise.get("uniforms", {})
        functions = expertise.get("functions", {})

        # Match based on keywords
        keywords = {
            "bloom": "post_processing",
            "blur": "post_processing",
            "noise": "procedural",
            "displacement": "vertex",
            "particle": "compute",
            "instance": "geometry",
            "sdf": "raymarching",
            "ray": "raymarching",
        }

        for keyword, category in keywords.items():
            if keyword in question:
                pattern = glsl_patterns.get(category, {})
                if pattern:
                    return {
                        "answer": f"GLSL {category} pattern from KB",
                        "code_snippets": pattern.get("code", []),
                        "recommendations": pattern.get("tips", []),
                    }

        return None

    def _query_python_kb(self, expertise: dict, question: str) -> Optional[dict]:
        """Query Python expertise."""
        callbacks = expertise.get("callbacks", {})
        extensions = expertise.get("extensions", {})
        patterns = expertise.get("patterns", {})

        # Match based on keywords
        keywords = {
            "execute": "dat_execute",
            "cook": "cook_callback",
            "parameter": "parameter_callback",
            "extension": "extension_pattern",
            "class": "extension_pattern",
            "timer": "timer_callback",
        }

        for keyword, pattern_name in keywords.items():
            if keyword in question:
                pattern = patterns.get(pattern_name) or callbacks.get(pattern_name, {})
                if pattern:
                    return {
                        "answer": f"Python {pattern_name} pattern from KB",
                        "code_snippets": [pattern.get("example", "")],
                        "recommendations": pattern.get("best_practices", []),
                    }

        return None

    def _query_pattern_kb(self, expertise: dict, question: str) -> Optional[dict]:
        """Query network patterns/palette expertise."""
        patterns = expertise.get("patterns", {})
        components = expertise.get("palette_components", {})

        # Match based on pattern names
        for pattern_name, pattern_data in patterns.items():
            if pattern_name.lower() in question:
                return {
                    "answer": f"Network pattern: {pattern_name}",
                    "code_snippets": [],
                    "recommendations": [pattern_data.get("description", "")],
                }

        # Also search the full palette catalog
        palette_matches = self.find_palette_solutions([question])
        if palette_matches:
            best = palette_matches[0]
            return {
                "answer": f"Palette component: {best.name} ({best.category})",
                "code_snippets": [f"# Load from palette:\nop('{best.tox_path}')"],
                "recommendations": [
                    best.purpose,
                    f"Wiki: {best.wiki_url}",
                    f"Use cases: {', '.join(best.use_cases[:3])}"
                ],
            }

        return None

    def find_palette_solutions(
        self,
        keywords: list[str],
        max_results: int = 10
    ) -> list[PaletteComponent]:
        """
        Find palette components matching keywords.

        This should be called BEFORE designing custom networks to check
        if a pre-built solution exists.

        Args:
            keywords: List of keywords to search for (e.g., ["audio", "beat", "particles"])
            max_results: Maximum number of results to return

        Returns:
            List of PaletteComponent matches sorted by relevance
        """
        if not self.palette_catalog:
            self.logger.warning("Palette catalog not loaded - cannot search")
            return []

        matches = []
        keywords_lower = [kw.lower() for kw in keywords]

        for name, data in self.palette_catalog.items():
            if not isinstance(data, dict):
                continue

            # Calculate relevance score
            score = 0.0
            name_lower = name.lower()
            purpose = str(data.get("purpose", "")).lower()
            summary = str(data.get("summary", "")).lower()
            category = str(data.get("category", "")).lower()
            use_cases = [uc.lower() for uc in data.get("use_cases", [])]

            for kw in keywords_lower:
                # Name match is highest value
                if kw in name_lower:
                    score += 3.0
                # Purpose/summary match
                if kw in purpose or kw in summary:
                    score += 2.0
                # Category match
                if kw in category:
                    score += 1.5
                # Use case match
                if any(kw in uc for uc in use_cases):
                    score += 1.0

            if score > 0:
                matches.append(PaletteComponent(
                    name=name,
                    category=data.get("category", ""),
                    purpose=data.get("purpose", data.get("summary", "")),
                    tox_path=data.get("tox_path", ""),
                    use_cases=data.get("use_cases", []),
                    wiki_url=data.get("wiki_url", ""),
                    relevance_score=score
                ))

        # Sort by relevance
        matches.sort(key=lambda x: x.relevance_score, reverse=True)

        if matches:
            self.logger.info(
                f"Found {len(matches)} palette matches for {keywords}: "
                f"top={matches[0].name} (score={matches[0].relevance_score:.1f})"
            )

        return matches[:max_results]

    def get_palette_recommendations(self, blackboard) -> list[PaletteComponent]:
        """
        Get palette recommendations based on blackboard content.

        Analyzes creative vision and technical approach to suggest
        pre-built palette components that could replace custom networks.

        Args:
            blackboard: The workflow blackboard

        Returns:
            List of recommended PaletteComponent objects
        """
        # Extract keywords from blackboard
        keywords = set()

        creative = blackboard.read("§2") or {}
        technical = blackboard.read("§3") or {}

        # Combine into searchable text
        search_text = f"{creative} {technical}".lower()

        # Common TD/VJ keywords to look for
        keyword_patterns = [
            "audio", "beat", "sound", "music", "spectrum", "fft",
            "particle", "pop", "emitter",
            "noise", "procedural", "generator",
            "blur", "glow", "bloom", "filter",
            "ui", "slider", "button", "control",
            "camera", "tracking", "motion",
            "video", "movie", "playback",
            "midi", "osc", "dmx",
            "instancing", "geometry", "mesh",
            "sdf", "raymarching", "shader"
        ]

        for pattern in keyword_patterns:
            if pattern in search_text:
                keywords.add(pattern)

        if not keywords:
            return []

        return self.find_palette_solutions(list(keywords), max_results=15)

    def _query_operator_kb(
        self,
        expertise: dict,
        question: str,
        expert_type: ExpertType
    ) -> Optional[dict]:
        """Query operator expertise."""
        family = expert_type.value.upper()
        operators = expertise.get("operators", {}).get(family, [])

        if not operators:
            return None

        # Search for operator mentions
        for op in operators:
            op_name = op.get("name", "").lower()
            if op_name in question:
                return {
                    "answer": f"Operator {op_name}: {op.get('description', '')}",
                    "code_snippets": [],
                    "recommendations": [
                        f"Parameters: {', '.join(op.get('key_parameters', []))}",
                        f"Use case: {op.get('use_case', '')}",
                    ],
                }

        return None

    def _query_llm(self, query: ExpertQuery, executor: Callable) -> ExpertResponse:
        """
        Query LLM for expert response.

        Args:
            query: The expert query
            executor: LLM executor function

        Returns:
            ExpertResponse from LLM
        """
        # H6 dedup: source the GLSL/PYTHON role strings from
        # ExpertExecutor's EXPERT_ROLE_PROMPTS so the two callers can't drift
        # out of sync. PALETTE is ExpertPool-only (no `palette_expert` in the
        # canonical EXPERT_IDS roster), so it stays inline here.
        from .expert_executor import EXPERT_ROLE_PROMPTS

        system_prompts = {
            ExpertType.GLSL: EXPERT_ROLE_PROMPTS["td_glsl_expert"],
            ExpertType.PYTHON: EXPERT_ROLE_PROMPTS["td_python_expert"],
            ExpertType.PALETTE: (
                "You are a TouchDesigner palette expert. "
                "Recommend reusable components and network patterns. "
                "Focus on modular, production-ready solutions."
            ),
        }

        system = system_prompts.get(query.expert_type, "You are a TouchDesigner expert.")
        prompt = f"{system}\n\nQuestion: {query.question}"

        if query.context:
            prompt += f"\n\nContext: {query.context}"

        try:
            result = executor(prompt)
            return ExpertResponse(
                expert_type=query.expert_type,
                question=query.question,
                answer=result.get("content", ""),
                code_snippets=result.get("code_snippets", []),
                recommendations=result.get("recommendations", []),
                confidence=0.7,  # Lower confidence for LLM
            )
        except Exception as e:
            self.logger.error(f"LLM query failed: {e}")
            return ExpertResponse(
                expert_type=query.expert_type,
                question=query.question,
                answer=f"Error: {str(e)}",
                confidence=0.0,
            )

    def batch_consult(
        self,
        queries: list[ExpertQuery],
        executor: Optional[Callable] = None
    ) -> list[ExpertResponse]:
        """
        Consult multiple experts in batch.

        Args:
            queries: List of expert queries
            executor: Optional LLM executor for complex queries

        Returns:
            List of responses in same order as queries
        """
        return [
            self.consult(q.expert_type, q.question, q.context, executor)
            for q in queries
        ]

    def get_expert_context_for_design(self, blackboard) -> str:
        """
        Generate expert context for the TD Designer prompt.

        Extracts relevant expertise based on the creative vision and
        technical approach already in the blackboard.

        IMPORTANT: Includes palette recommendations - designers should
        CHECK PALETTE FIRST before creating custom networks.

        Args:
            blackboard: The workflow blackboard

        Returns:
            Formatted expert context string
        """
        lines = ["=== EXPERT POOL CONTEXT ==="]

        # Get creative vision keywords
        creative = blackboard.read("§2") or {}
        technical = blackboard.read("§3") or {}

        # ===========================================
        # PALETTE-FIRST: Check for pre-built solutions
        # ===========================================
        palette_recs = self.get_palette_recommendations(blackboard)
        if palette_recs:
            lines.append("\n## 🎨 PALETTE COMPONENTS AVAILABLE (CHECK BEFORE CUSTOM BUILD)")
            lines.append("The following pre-built components may replace custom networks:")
            lines.append("")
            for comp in palette_recs[:10]:
                lines.append(f"  **{comp.name}** ({comp.category})")
                lines.append(f"    Purpose: {comp.purpose[:100]}...")
                lines.append(f"    Path: {comp.tox_path}")
                if comp.wiki_url:
                    lines.append(f"    Wiki: {comp.wiki_url}")
                lines.append("")

            lines.append("⚠️  INSTRUCTION: Before designing custom networks, verify if")
            lines.append("    a palette component can fulfill the requirement.")
            lines.append("")

        # Identify what expertise is needed
        needed_experts = []

        # Check for GLSL needs
        tech_str = str(technical).lower()
        if any(kw in tech_str for kw in ["shader", "glsl", "compute", "raymarching"]):
            needed_experts.append(ExpertType.GLSL)

        # Check for Python needs
        if any(kw in tech_str for kw in ["python", "script", "extension", "callback"]):
            needed_experts.append(ExpertType.PYTHON)

        # Always include palette for design phase
        needed_experts.append(ExpertType.PALETTE)

        # Generate summaries for each needed expert
        for expert_type in needed_experts:
            expertise = self.expertise_cache.get(expert_type, {})
            if expertise:
                lines.append(f"\n## {expert_type.value.upper()} Expert Available")
                lines.append(self._summarize_expertise(expert_type, expertise))

        # Include recent consultations if any
        recent = self.consultations[-5:] if self.consultations else []
        if recent:
            lines.append("\n## Recent Consultations")
            for c in recent:
                lines.append(
                    f"- [{c.response.expert_type.value}] {c.query.question[:50]}... "
                    f"(confidence={c.response.confidence:.1f})"
                )

        # Palette catalog stats
        if self.palette_catalog:
            lines.append(f"\n## Palette Catalog: {len(self.palette_catalog)} components available")

        lines.append("\n=== END EXPERT CONTEXT ===")
        return "\n".join(lines)

    def _summarize_expertise(self, expert_type: ExpertType, expertise: dict) -> str:
        """Generate a summary of available expertise."""
        if expert_type == ExpertType.GLSL:
            patterns = list(expertise.get("glsl_patterns", {}).keys())
            return f"Available patterns: {', '.join(patterns[:5])}"

        if expert_type == ExpertType.PYTHON:
            callbacks = list(expertise.get("callbacks", {}).keys())
            return f"Available callbacks: {', '.join(callbacks[:5])}"

        if expert_type == ExpertType.PALETTE:
            components = list(expertise.get("palette_components", {}).keys())
            return f"Available components: {', '.join(components[:5])}"

        return "Expertise available on request."

    def get_consultation_history(self) -> list[dict]:
        """Get all consultations as dicts for persistence."""
        return [
            {
                "expert": c.query.expert_type.value,
                "question": c.query.question,
                "answer": c.response.answer,
                "confidence": c.response.confidence,
                "timestamp": c.timestamp,
            }
            for c in self.consultations
        ]

    def clear_history(self) -> None:
        """Clear consultation history."""
        self.consultations.clear()


def create_expert_pool(kb_path: Optional[Path] = None) -> ExpertPool:
    """Create an expert pool instance."""
    return ExpertPool(kb_path)


__all__ = [
    "ExpertType",
    "ExpertQuery",
    "ExpertResponse",
    "ExpertConsultation",
    "ExpertPool",
    "PaletteComponent",
    "create_expert_pool",
]

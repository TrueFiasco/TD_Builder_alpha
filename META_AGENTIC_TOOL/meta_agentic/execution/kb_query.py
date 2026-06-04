"""
Knowledge Base Query Module

Handles querying the expertise YAML files and operator validation.
Provides anti-hallucination validation by checking operators and parameters
against ground truth data.

References:
    - C:/TD_Projects/META_AGENTIC_TOOL/docs/ARCHITECTURE.md (Knowledge Base section)
    - C:/TD_Projects/META_AGENTIC_TOOL/meta_agentic/expertise/*.yaml files
    - C:/TD_Projects/META_AGENTIC_TOOL/operator_ground_truth/params/ (complete schemas)
"""

import json
import yaml
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

# Import ground truth for complete operator validation
from .ground_truth import get_ground_truth, GroundTruth

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class ExpertiseFiles(Enum):
    """Enumeration of all expertise YAML files in the knowledge base."""

    OPERATORS = "td_operators.yaml"
    OPERATORS_V2 = "td_operators_v2.yaml"  # Sweet 16 + Index (compact, ~27KB)
    PATTERNS = "td_network_patterns.yaml"
    GLSL = "td_glsl.yaml"
    PYTHON = "td_python.yaml"
    PALETTE = "palette_expertise.yaml"
    PALETTE_SEMANTIC = "palette_semantic_catalog.yaml"
    CREATIVE_VISION = "creative_vision.yaml"
    TD_PROBLEMS = "td_problems.yaml"
    CRITIQUE_PATTERNS = "critique_patterns.yaml"
    CG_CONCEPTS = "cg_concepts.yaml"
    PARAMETERS = "td_parameters.yaml"
    NETWORK_BUILDING = "td_network_building.yaml"
    FILE_FORMATS = "td_file_formats.yaml"
    COLLABORATIVE_WORKFLOW = "collaborative_workflow.yaml"
    ORCHESTRATOR_PATTERNS = "orchestrator_patterns.yaml"
    PREBUILT_SOLUTION = "prebuilt_solution_expert.yaml"


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class QueryResult:
    """Result from a knowledge base query."""

    source: str  # File name that was queried
    query: str  # What was searched
    results: list[dict] = field(default_factory=list)
    confidence: float = 0.0  # 0.0 to 1.0

    def __repr__(self) -> str:
        return (f"QueryResult(source={self.source}, query={self.query}, "
                f"results={len(self.results)} items, confidence={self.confidence})")


@dataclass
class ValidationResult:
    """Result from anti-hallucination validation."""

    valid: bool
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        status = "VALID" if self.valid else "INVALID"
        return (f"ValidationResult({status}, missing={len(self.missing)}, "
                f"errors={len(self.errors)}, warnings={len(self.warnings)})")


# =============================================================================
# KNOWLEDGE BASE CLASS
# =============================================================================

class KnowledgeBase:
    """
    Central interface for querying expertise YAML files and operator data.

    Provides methods for:
    - Loading and parsing YAML expertise files
    - Querying operators, patterns, GLSL, palette components
    - Anti-hallucination validation against ground truth
    - Semantic search (placeholder for ChromaDB integration)
    """

    def __init__(self, base_path: Path):
        """
        Initialize the knowledge base.

        Args:
            base_path: Path to meta_agentic/expertise/ directory
        """
        self.base_path = Path(base_path)
        self._expertise_cache: dict[str, dict] = {}
        self._operator_schemas: Optional[dict] = None
        self._parsed_data: Optional[dict] = None

        # Validate base path exists
        if not self.base_path.exists():
            raise FileNotFoundError(f"Expertise directory not found: {self.base_path}")

        logger.info(f"KnowledgeBase initialized with base_path: {self.base_path}")

    # =========================================================================
    # YAML LOADING
    # =========================================================================

    def load_expertise(self, file_name: str) -> dict:
        """
        Load and parse a YAML expertise file.

        Args:
            file_name: Name of the YAML file (e.g., "operators.yaml")

        Returns:
            Parsed YAML content as dictionary

        Raises:
            FileNotFoundError: If file doesn't exist
            yaml.YAMLError: If file is malformed
        """
        # Check cache first
        if file_name in self._expertise_cache:
            logger.debug(f"Returning cached expertise: {file_name}")
            return self._expertise_cache[file_name]

        file_path = self.base_path / file_name

        if not file_path.exists():
            raise FileNotFoundError(f"Expertise file not found: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            # Cache the result
            self._expertise_cache[file_name] = data
            logger.info(f"Loaded expertise file: {file_name}")
            return data

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file {file_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading expertise file {file_name}: {e}")
            raise

    # =========================================================================
    # OPERATOR QUERIES
    # =========================================================================

    def query_operators(self, filter_params: dict) -> list[dict]:
        """
        Query operators.yaml with filters.

        Args:
            filter_params: Dictionary with optional keys:
                - family: str (e.g., "CHOP", "TOP", "SOP")
                - name: str (operator name)
                - purpose_contains: str (search in purpose text)

        Returns:
            List of matching operator entries

        Example:
            >>> kb.query_operators({"family": "CHOP", "purpose_contains": "audio"})
            [{"name": "audiofilein", "purpose": "Loads audio...", ...}, ...]
        """
        try:
            data = self.load_expertise(ExpertiseFiles.OPERATORS.value)
        except FileNotFoundError:
            logger.warning(f"Operators file not found, returning empty results")
            return []

        results = []
        operators_section = data.get("operators", {})

        for family, operators in operators_section.items():
            # Filter by family if specified
            if "family" in filter_params and family != filter_params["family"]:
                continue

            for op_name, op_data in operators.items():
                # Filter by name if specified
                if "name" in filter_params and op_name != filter_params["name"]:
                    continue

                # Filter by purpose text if specified
                if "purpose_contains" in filter_params:
                    purpose = op_data.get("purpose", "")
                    if filter_params["purpose_contains"].lower() not in purpose.lower():
                        continue

                # Add to results with metadata
                result = {
                    "family": family,
                    "name": op_name,
                    **op_data
                }
                results.append(result)

        logger.info(f"Query operators returned {len(results)} results")
        return results

    # =========================================================================
    # PATTERN QUERIES
    # =========================================================================

    def query_patterns(self, category: str) -> list[dict]:
        """
        Query patterns.yaml by workflow category.

        Args:
            category: Workflow category (e.g., "audio_reactive_visuals", "instancing_workflow")

        Returns:
            List of matching pattern entries

        Example:
            >>> kb.query_patterns("audio_reactive_visuals")
            [{"description": "Synchronizing visual...", "typical_chain": [...], ...}]
        """
        try:
            data = self.load_expertise(ExpertiseFiles.PATTERNS.value)
        except FileNotFoundError:
            logger.warning(f"Patterns file not found, returning empty results")
            return []

        workflows = data.get("workflows", {})

        # Exact match
        if category in workflows:
            result = {
                "category": category,
                **workflows[category]
            }
            logger.info(f"Query patterns found exact match: {category}")
            return [result]

        # Fuzzy match - return all if category is empty or partial match
        if not category:
            results = [
                {"category": cat, **wf_data}
                for cat, wf_data in workflows.items()
            ]
            logger.info(f"Query patterns returned all {len(results)} workflows")
            return results

        # Partial match
        results = []
        for cat, wf_data in workflows.items():
            if category.lower() in cat.lower():
                results.append({"category": cat, **wf_data})

        logger.info(f"Query patterns returned {len(results)} partial matches")
        return results

    # =========================================================================
    # GLSL QUERIES
    # =========================================================================

    def query_glsl(self, shader_type: str) -> dict:
        """
        Query glsl_expertise.yaml by shader type.

        Args:
            shader_type: Type of shader (e.g., "glsl_top", "glsl_mat", "vertex_template")

        Returns:
            Dictionary with GLSL expertise for that shader type

        Example:
            >>> kb.query_glsl("glsl_top")
            {"template": "...", "guidelines": [...], "templates": {...}}
        """
        try:
            data = self.load_expertise(ExpertiseFiles.GLSL.value)
        except FileNotFoundError:
            logger.warning(f"GLSL file not found, returning empty dict")
            return {}

        # Direct key lookup
        if shader_type in data:
            logger.info(f"Query GLSL found: {shader_type}")
            return data[shader_type]

        logger.warning(f"GLSL shader type not found: {shader_type}")
        return {}

    # =========================================================================
    # PALETTE QUERIES
    # =========================================================================

    def query_palette(self, component_type: str) -> list[dict]:
        """
        Query palette_expertise.yaml by component type.

        Args:
            component_type: Type of palette component (e.g., "slider2D", "buttonRadio")

        Returns:
            List of matching palette component entries

        Example:
            >>> kb.query_palette("slider2D")
            [{"name": "slider2D", "purpose": "...", "parameters": {...}}]
        """
        try:
            data = self.load_expertise(ExpertiseFiles.PALETTE.value)
        except FileNotFoundError:
            logger.warning(f"Palette file not found, returning empty results")
            return []

        results = []

        # Search in integration_strategies section
        strategies = data.get("integration_strategies", {})
        for strategy_name, strategy_data in strategies.items():
            if component_type.lower() in str(strategy_data).lower():
                results.append({
                    "type": "integration_strategy",
                    "name": strategy_name,
                    **strategy_data
                })

        # Search in paths section for component references
        paths = data.get("paths", {})
        if "ui_widgets" in paths and component_type:
            results.append({
                "type": "path_reference",
                "component": component_type,
                "base_path": paths.get("ui_widgets"),
                "full_path": f"{paths.get('ui_widgets')}/{component_type}.tox"
            })

        logger.info(f"Query palette returned {len(results)} results for {component_type}")
        return results

    def query_palette_catalog(
        self,
        keywords: list[str],
        category: Optional[str] = None,
        max_results: int = 15
    ) -> list[dict]:
        """
        Query the full palette semantic catalog (278 components).

        This should be called BEFORE designing custom networks to find
        pre-built solutions that may already exist.

        Args:
            keywords: List of keywords to search for (e.g., ["audio", "beat", "particles"])
            category: Optional category filter (e.g., "Generators", "POPs", "UI")
            max_results: Maximum number of results to return

        Returns:
            List of matching palette components sorted by relevance

        Example:
            >>> kb.query_palette_catalog(["audio", "beat"])
            [{"name": "audioAnalysis", "category": "Techniques", "purpose": "...", ...}]
        """
        try:
            data = self.load_expertise(ExpertiseFiles.PALETTE_SEMANTIC.value)
        except FileNotFoundError:
            logger.warning(f"Palette semantic catalog not found, returning empty results")
            return []

        results = []
        keywords_lower = [kw.lower() for kw in keywords]

        for name, comp_data in data.items():
            # Skip metadata
            if name.startswith('_') or not isinstance(comp_data, dict):
                continue

            # Filter by category if specified
            comp_category = comp_data.get("category", "")
            if category and category.lower() != comp_category.lower():
                continue

            # Calculate relevance score
            score = 0.0
            name_lower = name.lower()
            purpose = str(comp_data.get("purpose", "")).lower()
            summary = str(comp_data.get("summary", "")).lower()
            category_lower = comp_category.lower()
            use_cases = [uc.lower() for uc in comp_data.get("use_cases", [])]

            for kw in keywords_lower:
                # Name match is highest value
                if kw in name_lower:
                    score += 3.0
                # Purpose/summary match
                if kw in purpose or kw in summary:
                    score += 2.0
                # Category match
                if kw in category_lower:
                    score += 1.5
                # Use case match
                if any(kw in uc for uc in use_cases):
                    score += 1.0

            if score > 0:
                results.append({
                    "name": name,
                    "category": comp_category,
                    "purpose": comp_data.get("purpose", comp_data.get("summary", "")),
                    "tox_path": comp_data.get("tox_path", ""),
                    "use_cases": comp_data.get("use_cases", []),
                    "wiki_url": comp_data.get("wiki_url", ""),
                    "has_ui": comp_data.get("has_ui", False),
                    "key_operators": comp_data.get("key_operators", []),
                    "relevance_score": score
                })

        # Sort by relevance
        results.sort(key=lambda x: x["relevance_score"], reverse=True)

        if results:
            logger.info(
                f"Palette catalog search for {keywords}: "
                f"found {len(results)} matches, top={results[0]['name']} (score={results[0]['relevance_score']:.1f})"
            )
        else:
            logger.info(f"Palette catalog search for {keywords}: no matches found")

        return results[:max_results]

    def get_palette_recommendations_for_prompt(self, prompt: str) -> list[dict]:
        """
        Analyze a prompt and return relevant palette components.

        This is a convenience method that extracts keywords from a prompt
        and searches the palette catalog.

        Args:
            prompt: The user's prompt or creative vision text

        Returns:
            List of recommended palette components

        Example:
            >>> kb.get_palette_recommendations_for_prompt("Create an audio-reactive particle system")
            [{"name": "audioAnalysis", ...}, {"name": "popNetwork", ...}]
        """
        # Extract keywords from prompt
        keywords = set()
        prompt_lower = prompt.lower()

        keyword_patterns = [
            "audio", "beat", "sound", "music", "spectrum", "fft", "analyze",
            "particle", "pop", "emitter", "point",
            "noise", "procedural", "generator", "fractal",
            "blur", "glow", "bloom", "filter", "color",
            "ui", "slider", "button", "control", "dial",
            "camera", "tracking", "motion", "kinect",
            "video", "movie", "playback", "ndi",
            "midi", "osc", "dmx", "artnet",
            "instancing", "geometry", "mesh", "sdf",
            "shader", "glsl", "raymarching",
            "ableton", "bitwig", "vr", "quest"
        ]

        for pattern in keyword_patterns:
            if pattern in prompt_lower:
                keywords.add(pattern)

        if not keywords:
            return []

        return self.query_palette_catalog(list(keywords))

    # =========================================================================
    # OPERATOR FAMILY INFERENCE
    # =========================================================================

    def _infer_operator_family(self, op_type: str) -> str:
        """
        Infer operator family from type name using suffix patterns.

        Returns: "CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP", or "UNKNOWN"
        """
        op_lower = op_type.lower()

        # Suffix-based detection (most reliable)
        suffix_map = {
            'chop': 'CHOP',
            'top': 'TOP',
            'sop': 'SOP',
            'dat': 'DAT',
            'comp': 'COMP',
            'mat': 'MAT',
            'pop': 'POP'
        }

        for suffix, family in suffix_map.items():
            if op_lower.endswith(suffix):
                return family

        # Common operator name patterns
        chop_patterns = ['audio', 'midi', 'osc', 'noise', 'lfo', 'math', 'select',
                         'merge', 'null', 'constant', 'lag', 'filter', 'analyze',
                         'beat', 'speed', 'lookup', 'rename', 'delete', 'shuffle',
                         'hold', 'logic', 'count', 'timer', 'trigger', 'limit',
                         'trail', 'record', 'wave', 'pattern', 'fan', 'resample']

        top_patterns = ['render', 'composite', 'level', 'blur', 'transform',
                        'feedback', 'glsl', 'text', 'movie', 'ramp', 'noise',
                        'hsvadjust', 'lookup', 'crop', 'flip', 'resolution',
                        'cache', 'null', 'out', 'displace', 'edge']

        sop_patterns = ['grid', 'box', 'sphere', 'tube', 'circle', 'line',
                        'merge', 'transform', 'noise', 'convert', 'add', 'copy',
                        'particle', 'force', 'limit', 'spring', 'metaball',
                        'carve', 'divide', 'facet', 'fuse', 'hole', 'sort']

        dat_patterns = ['table', 'text', 'script', 'execute', 'select', 'merge',
                        'convert', 'fifo', 'null', 'info', 'oscinput', 'web']

        comp_patterns = ['geometry', 'camera', 'light', 'base', 'container',
                         'window', 'button', 'slider', 'field']

        pop_patterns = ['popnet', 'source', 'force', 'attractor', 'limit',
                        'kill', 'collision', 'interact', 'property', 'sprite',
                        'stream', 'replicate', 'curve']

        # Check patterns (order matters - more specific first)
        if any(p in op_lower for p in pop_patterns):
            return 'POP'
        if any(p in op_lower for p in comp_patterns):
            return 'COMP'
        if any(p in op_lower for p in dat_patterns):
            return 'DAT'
        if any(p in op_lower for p in sop_patterns):
            return 'SOP'
        if any(p in op_lower for p in top_patterns):
            return 'TOP'
        if any(p in op_lower for p in chop_patterns):
            return 'CHOP'

        logger.warning(f"Could not infer family for operator type: {op_type}")
        return 'UNKNOWN'

    def _normalize_op_type(self, op_type: str) -> str:
        """
        Normalize operator type for comparison by removing family suffix.

        Examples:
            "audiodeviceinCHOP" -> "audiodevicein"
            "noiseTOP" -> "noise"
            "gridSOP" -> "grid"
            "audiodevicein" -> "audiodevicein" (unchanged)

        Returns:
            Lowercase operator type without family suffix
        """
        if not op_type:
            return ""

        op_lower = op_type.lower()

        # Remove family suffix if present
        for suffix in ['chop', 'top', 'sop', 'dat', 'comp', 'mat', 'pop']:
            if op_lower.endswith(suffix) and len(op_lower) > len(suffix):
                return op_lower[:-len(suffix)]

        return op_lower

    # =========================================================================
    # BUILDABLE CHAIN EXTRACTION
    # =========================================================================

    def get_buildable_chain(self, pattern_name: str) -> dict:
        """
        Extract a complete buildable operator chain from a pattern.

        This is the PRIMARY function for TD Designer to use before building.
        Returns structured data ready for direct instantiation.

        Returns:
            {
                "pattern": "audio_reactive_visuals",
                "description": "Pattern description",
                "operators": [
                    {
                        "step": 1,
                        "type": "audiodevicein",
                        "family": "CHOP",
                        "role": "Audio source",
                        "suggested_name": "audio_in",
                        "key_params": {"device": "default"},
                        "validated": true,
                        "is_primary": true,
                        "alternatives": ["audiofileinCHOP"]
                    }
                ],
                "connections": [
                    {"from_step": 1, "to_step": 2, "type": "wire"}
                ],
                "common_errors": ["Missing analyze after filter"],
                "validated": true
            }
        """
        logger.info(f"Getting buildable chain for pattern: {pattern_name}")

        # Query the pattern
        patterns = self.query_patterns(pattern_name)
        if not patterns:
            logger.warning(f"No pattern found for: {pattern_name}")
            return {
                "pattern": pattern_name,
                "description": "",
                "operators": [],
                "connections": [],
                "common_errors": [],
                "validated": False,
                "error": f"Pattern '{pattern_name}' not found in knowledge base"
            }

        pattern = patterns[0]
        chain_data = pattern.get('typical_chain', [])
        key_params = pattern.get('key_parameters', [])
        common_errors = pattern.get('common_errors', [])

        logger.info(f"Pattern has {len(chain_data)} chain steps, {len(key_params)} key params")

        # Build operators list
        operators = []
        for step in chain_data:
            step_num = step.get('step', len(operators) + 1)
            step_operators = step.get('operators', [])
            role = step.get('role', '')

            # First operator is primary, rest are alternatives
            for i, op_type in enumerate(step_operators):
                family = self._infer_operator_family(op_type)

                # Gather parameters for this operator
                params = {}
                for kp in key_params:
                    if kp.get('operator') == op_type:
                        typical_values = kp.get('typical_values', [])
                        if typical_values:
                            params[kp['param']] = typical_values[0]

                # Validate operator exists
                is_valid = self.validate_operator(family, op_type)

                if i == 0:
                    # Primary operator
                    operators.append({
                        "step": step_num,
                        "type": op_type,
                        "family": family,
                        "role": role,
                        "suggested_name": f"{op_type.replace('CHOP', '').replace('TOP', '').replace('SOP', '')}1",
                        "key_params": params,
                        "validated": is_valid,
                        "is_primary": True,
                        "alternatives": step_operators[1:] if len(step_operators) > 1 else []
                    })
                else:
                    # Log alternatives for reference
                    logger.debug(f"Alternative operator for step {step_num}: {op_type}")

        # Build connections
        connections = []
        for i in range(len(operators) - 1):
            connections.append({
                "from_step": operators[i]['step'],
                "to_step": operators[i + 1]['step'],
                "type": "wire"
            })

        # Calculate overall validation status
        all_validated = all(op['validated'] for op in operators) if operators else False

        result = {
            "pattern": pattern_name,
            "description": pattern.get('description', ''),
            "operators": operators,
            "connections": connections,
            "common_errors": common_errors,
            "validated": all_validated
        }

        logger.info(f"Chain built: {len(operators)} operators, validated={all_validated}")
        return result

    # =========================================================================
    # DESIGN STRUCTURE VALIDATION
    # =========================================================================

    def validate_design_structure(self, design: dict) -> dict:
        """
        Comprehensive structural validation for a design.

        Performs 6 blocking checks:
        1. Empty containers - containers with no operators
        2. Chain completeness - all pattern steps implemented
        3. Connection integrity - no dangling connections
        4. Unvalidated parameters - params not in param_catalog
        5. Unresolved uncertainties - flagged items without resolution
        6. UNVALIDATED prefix check - placeholder operators not resolved

        Accepts both formats:
            - {"containers": [...], "connections": [...]}
            - {"design": {"containers": [...], ...}}
            - {"network_design": {"containers": [...], ...}}

        Returns:
            {
                "valid": false,
                "blocking": [
                    {"type": "EMPTY_CONTAINER", "container": "audio", "fix": "Add operators or remove container"}
                ],
                "warnings": [...],
                "score_cap": 0.30  # Maximum score allowed given blocking issues
            }
        """
        # Handle different root key formats
        if 'network_design' in design:
            design = design['network_design']
        elif 'design' in design and isinstance(design.get('design'), dict):
            design = design['design']

        blocking = []
        warnings = []
        score_cap = 1.0

        containers = design.get('containers', [])

        # CHECK 1: Empty containers
        for container in containers:
            if not container.get('operators', []):
                blocking.append({
                    "type": "EMPTY_CONTAINER",
                    "container": container.get('name'),
                    "fix": "Add operators or remove container"
                })
                score_cap = min(score_cap, 0.30)

        # CHECK 2: Chain completeness
        # Check both top-level 'pattern' and 'metadata.matched_pattern'
        matched_pattern = (
            design.get('pattern') or
            design.get('metadata', {}).get('matched_pattern')
        )
        if matched_pattern:
            expected = self.get_buildable_chain(matched_pattern)
            if expected.get('operators'):  # Check if chain has operators (even if not fully validated)
                # Use normalized types for comparison to handle suffix variations
                expected_types = {self._normalize_op_type(op['type']) for op in expected.get('operators', [])}
                found_types = set()
                for container in containers:
                    for op in container.get('operators', []):
                        found_types.add(self._normalize_op_type(op.get('type', '')))

                # Also check flat operators list if present
                for op in design.get('operators', []):
                    found_types.add(self._normalize_op_type(op.get('type', '')))

                # Remove empty strings from comparison
                expected_types.discard('')
                found_types.discard('')

                missing = expected_types - found_types
                if missing:
                    blocking.append({
                        "type": "INCOMPLETE_CHAIN",
                        "pattern": matched_pattern,
                        "expected": list(expected_types),
                        "found": list(found_types),
                        "missing": list(missing)
                    })
                    score_cap = min(score_cap, 0.30)

        # CHECK 3: Connection integrity
        all_ops = set()
        for container in containers:
            for op in container.get('operators', []):
                # Support both "container/op" and just "op" formats
                all_ops.add(f"{container['name']}/{op['name']}")
                all_ops.add(op['name'])

        # Also add flat operators
        for op in design.get('operators', []):
            all_ops.add(op.get('name', ''))

        for conn in design.get('connections', []):
            from_op = conn.get('from', '')
            to_op = conn.get('to', '')

            # Check if connection endpoints exist
            from_exists = from_op in all_ops or from_op.split('/')[-1] in all_ops
            to_exists = to_op in all_ops or to_op.split('/')[-1] in all_ops

            if not from_exists:
                blocking.append({
                    "type": "DANGLING_CONNECTION",
                    "from": from_op,
                    "available_ops": list(all_ops)[:10]  # Show first 10 for context
                })
                score_cap = min(score_cap, 0.30)

            if not to_exists:
                blocking.append({
                    "type": "DANGLING_CONNECTION",
                    "to": to_op,
                    "available_ops": list(all_ops)[:10]
                })
                score_cap = min(score_cap, 0.30)

        # CHECK 4: Unvalidated parameters
        validation_summary = design.get('validation_summary', {})
        unvalidated_params = validation_summary.get('parameters_unvalidated', 0)
        if unvalidated_params > 0:
            blocking.append({
                "type": "UNVALIDATED_PARAMETERS",
                "count": unvalidated_params,
                "params_list": validation_summary.get('unvalidated_params_list', []),
                "fix": "Validate all parameters against param_catalog.json or flag with needs_resolution"
            })
            score_cap = min(score_cap, 0.40)

        # CHECK 5: Unresolved uncertainties
        uncertainties = design.get('uncertainties', [])
        unresolved = [u for u in uncertainties if u.get('needs_resolution') and not u.get('resolution')]
        if unresolved:
            blocking.append({
                "type": "UNRESOLVED_UNCERTAINTIES",
                "count": len(unresolved),
                "items": [u.get('type', 'unknown') for u in unresolved]
            })
            score_cap = min(score_cap, 0.30)

        # CHECK 6: UNVALIDATED prefix check
        all_operator_names = []
        for container in containers:
            for op in container.get('operators', []):
                all_operator_names.append(op.get('name', ''))
        for op in design.get('operators', []):
            all_operator_names.append(op.get('name', ''))

        unvalidated_placeholders = [n for n in all_operator_names if n.startswith('UNVALIDATED_')]
        if unvalidated_placeholders:
            blocking.append({
                "type": "UNVALIDATED_PLACEHOLDER",
                "count": len(unvalidated_placeholders),
                "operators": unvalidated_placeholders,
                "fix": "Resolve placeholder operators before building"
            })
            score_cap = min(score_cap, 0.20)

        # CHECK 7: Orphan operators (warning only)
        connected_ops = set()
        for conn in design.get('connections', []):
            connected_ops.add(conn.get('from', '').split('/')[-1])
            connected_ops.add(conn.get('to', '').split('/')[-1])

        for container in containers:
            for op in container.get('operators', []):
                op_name = op.get('name')
                op_type = op.get('type', '').lower()
                # Null/out/in operators are allowed to be endpoints
                if op_name not in connected_ops and not any(x in op_type for x in ['null', 'out', 'in']):
                    warnings.append({
                        "type": "ORPHAN_OPERATOR",
                        "operator": op_name,
                        "container": container.get('name'),
                        "note": "Operator has no connections - verify this is intentional"
                    })

        return {
            "valid": len(blocking) == 0,
            "blocking": blocking,
            "warnings": warnings,
            "score_cap": score_cap
        }

    # =========================================================================
    # SEMANTIC SEARCH (PLACEHOLDER)
    # =========================================================================

    def semantic_search(self, query: str, top_k: int = 5) -> list[dict]:
        """Semantic search via the merged ChromaDB store (UnifiedSearchAdapter).

        Replaces the original placeholder. Delegates to the process-wide
        singleton in `META_AGENTIC_TOOL/search/__init__.py:get_search_adapter`
        and maps each semantic hit into the QueryResult shape downstream
        callers (and tests) expect. Returns an empty list — not the historic
        confidence=0.0 stub — when the adapter is unavailable so callers can
        detect "no results" deterministically.

        Args:
            query: Natural language search query.
            top_k: Number of top results to return.

        Returns:
            List of QueryResult dicts (source, query, results, confidence).

        Example:
            >>> kb.semantic_search("how to make particles react to audio", top_k=3)
            [{"source": "docs", "query": "...", "results": ["..."], "confidence": 0.87}, ...]
        """
        try:
            try:
                from search import get_search_adapter
            except ImportError:
                import sys as _sys
                from pathlib import Path as _Path
                # kb_query.py lives at META_AGENTIC_TOOL/meta_agentic/execution/
                # kb_query.py — META_AGENTIC_TOOL is two parents up.
                _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
                from search import get_search_adapter  # type: ignore

            adapter = get_search_adapter()
            result = adapter.search(query, n_results=top_k, include_relationships=False)
            return [
                QueryResult(
                    source=(r.get("metadata") or {}).get("source", "semantic_search"),
                    query=query,
                    results=[r.get("content", "")],
                    confidence=float(r.get("score", 0.0)),
                ).__dict__
                for r in result.get("semantic_results", [])
            ]
        except Exception as e:
            logger.warning(f"semantic_search adapter call failed: {e}")
            return []

    # =========================================================================
    # HELPER FUNCTIONS
    # =========================================================================

    def get_operators_for_family(self, family: str) -> list[dict]:
        """
        Get all operators for a specific family (CHOP, TOP, SOP, etc.).

        Args:
            family: Operator family (e.g., "CHOP", "TOP")

        Returns:
            List of operator entries
        """
        return self.query_operators({"family": family})

    def get_patterns_for_category(self, category: str) -> list[dict]:
        """
        Get patterns for a specific workflow category.

        Args:
            category: Workflow category

        Returns:
            List of pattern entries
        """
        return self.query_patterns(category)

    # =========================================================================
    # OPERATOR VALIDATION (ANTI-HALLUCINATION)
    # Uses ground_truth.py for complete operator/parameter validation
    # BUG-007 FIX: Migrated from incomplete operator_param_schemas.json
    # =========================================================================

    def _get_ground_truth(self) -> GroundTruth:
        """Get ground truth loader for complete operator validation."""
        return get_ground_truth()

    def validate_operator(self, op_type: str, op_name: str) -> bool:
        """
        Validate that an operator exists in the ground truth data.

        Uses ground_truth.py for complete validation (31+ params per operator)
        instead of operator_param_schemas.json (only 8 params).

        Args:
            op_type: Operator family (e.g., "CHOP", "TOP")
            op_name: Operator name (e.g., "noise", "moviefilein")

        Returns:
            True if operator exists, False otherwise

        Example:
            >>> kb.validate_operator("CHOP", "noise")
            True
            >>> kb.validate_operator("CHOP", "fakeopname")
            False
        """
        gt = self._get_ground_truth()
        op_schema = gt.get_operator(op_name, family=op_type)

        if op_schema is not None:
            return True

        logger.warning(f"Operator not found in ground truth: {op_type}:{op_name}")
        return False

    def validate_parameter(self, op_type: str, op_name: str, param: str) -> bool:
        """
        Validate that a parameter exists for a specific operator.

        Uses ground_truth.py for complete validation (31+ params per operator).

        Args:
            op_type: Operator family
            op_name: Operator name
            param: Parameter name

        Returns:
            True if parameter exists, False otherwise

        Example:
            >>> kb.validate_parameter("CHOP", "noise", "type")
            True
            >>> kb.validate_parameter("CHOP", "noise", "fakeparam")
            False
        """
        gt = self._get_ground_truth()
        param_info = gt.get_param_info(op_name, param)

        if param_info is not None:
            return True

        # Also try with family suffix format (e.g., "noiseTOP")
        combined_name = f"{op_name}{op_type}"
        param_info = gt.get_param_info(combined_name, param)

        if param_info is not None:
            return True

        logger.warning(f"Parameter not found in ground truth: {op_type}:{op_name}.{param}")
        return False

    def check_operators_exist(self, operators: list[str]) -> list[str]:
        """
        Check which operators from a list don't exist in ground truth.

        Args:
            operators: List of operator names (format: "TYPE:name" or just "name")

        Returns:
            List of operator names that don't exist

        Example:
            >>> kb.check_operators_exist(["CHOP:noise", "CHOP:fakeop", "TOP:moviefilein"])
            ["CHOP:fakeop"]
        """
        missing = []

        for op in operators:
            # Parse operator string
            if ":" in op:
                op_type, op_name = op.split(":", 1)
            else:
                # If no type specified, we can't validate properly
                logger.warning(f"Operator missing type prefix, skipping validation: {op}")
                continue

            if not self.validate_operator(op_type, op_name):
                missing.append(op)

        if missing:
            logger.warning(f"Found {len(missing)} non-existent operators: {missing}")

        return missing

    def check_parameters_valid(
        self,
        op_type: str,
        op_name: str,
        params: dict
    ) -> list[str]:
        """
        Check which parameters from a dict don't exist for an operator.

        Args:
            op_type: Operator family
            op_name: Operator name
            params: Dictionary of parameter names and values

        Returns:
            List of invalid parameter names

        Example:
            >>> kb.check_parameters_valid("CHOP", "noise", {"type": "random", "fakeparam": 5})
            ["fakeparam"]
        """
        invalid = []

        for param_name in params.keys():
            if not self.validate_parameter(op_type, op_name, param_name):
                invalid.append(param_name)

        if invalid:
            logger.warning(
                f"Found {len(invalid)} invalid parameters for {op_type}:{op_name}: {invalid}"
            )

        return invalid

    def validate_network_design(self, network_json: dict) -> ValidationResult:
        """
        Validate an entire network design JSON for hallucinations.

        Args:
            network_json: Network design JSON with operators and connections

        Returns:
            ValidationResult with details on any issues found

        Example:
            >>> result = kb.validate_network_design(network_json)
            >>> if not result.valid:
            ...     print(f"Errors: {result.errors}")
        """
        errors = []
        warnings = []
        missing = []

        # Validate operators exist
        operators = network_json.get("operators", [])
        for op in operators:
            op_type = op.get("type", "")
            op_name = op.get("name", "")

            if not op_type or not op_name:
                errors.append(f"Operator missing type or name: {op}")
                continue

            # Extract base operator name (remove instance suffix like "noise1" -> "noise")
            base_name = ''.join([c for c in op_name if not c.isdigit()])

            if not self.validate_operator(op_type, base_name):
                missing.append(f"{op_type}:{base_name}")
                errors.append(f"Non-existent operator: {op_type}:{base_name}")

            # Validate parameters
            params = op.get("params", {})
            invalid_params = self.check_parameters_valid(op_type, base_name, params)
            if invalid_params:
                warnings.append(
                    f"Invalid parameters for {op_type}:{base_name}: {invalid_params}"
                )

        # Validate connections reference existing operators
        connections = network_json.get("connections", [])
        op_names = [op.get("name") for op in operators]

        for conn in connections:
            source = conn.get("source")
            target = conn.get("target")

            if source not in op_names:
                errors.append(f"Connection references non-existent source: {source}")
            if target not in op_names:
                errors.append(f"Connection references non-existent target: {target}")

        valid = len(errors) == 0

        result = ValidationResult(
            valid=valid,
            missing=missing,
            errors=errors,
            warnings=warnings
        )

        logger.info(f"Network validation: {result}")
        return result


# =============================================================================
# MODULE-LEVEL HELPER FUNCTIONS
# =============================================================================

def get_default_kb() -> KnowledgeBase:
    """
    Get a KnowledgeBase instance with default paths.

    Returns:
        KnowledgeBase instance pointing to standard expertise directory
    """
    # Assumes this file is in meta_agentic/execution/
    current_file = Path(__file__)
    expertise_path = current_file.parent.parent / "expertise"

    return KnowledgeBase(expertise_path)


def get_operators_for_family(family: str) -> list[dict]:
    """
    Module-level convenience function to get operators by family.

    Args:
        family: Operator family (CHOP, TOP, SOP, etc.)

    Returns:
        List of operator entries
    """
    kb = get_default_kb()
    return kb.get_operators_for_family(family)


def get_patterns_for_category(category: str) -> list[dict]:
    """
    Module-level convenience function to get patterns by category.

    Args:
        category: Workflow category

    Returns:
        List of pattern entries
    """
    kb = get_default_kb()
    return kb.get_patterns_for_category(category)


def validate_operator(op_type: str, op_name: str) -> bool:
    """
    Module-level convenience function to validate an operator.

    Args:
        op_type: Operator family
        op_name: Operator name

    Returns:
        True if operator exists
    """
    kb = get_default_kb()
    return kb.validate_operator(op_type, op_name)


def validate_parameter(op_type: str, op_name: str, param: str) -> bool:
    """
    Module-level convenience function to validate a parameter.

    Args:
        op_type: Operator family
        op_name: Operator name
        param: Parameter name

    Returns:
        True if parameter exists
    """
    kb = get_default_kb()
    return kb.validate_parameter(op_type, op_name, param)


def get_chain(pattern_name: str) -> dict:
    """
    Quick access to buildable chain.

    Usage:
        chain = get_chain('audio_reactive')
        for op in chain['operators']:
            print(f"Step {op['step']}: {op['type']} ({op['family']})")

    Args:
        pattern_name: Name of the pattern to extract chain from

    Returns:
        Buildable chain dict with operators, connections, etc.
    """
    kb = get_default_kb()
    return kb.get_buildable_chain(pattern_name)


def validate_structure(design: dict) -> dict:
    """
    Quick structure validation for a design.

    Usage:
        result = validate_structure(my_design)
        if not result['valid']:
            for issue in result['blocking']:
                print(f"BLOCKING: {issue['type']}")

    Args:
        design: Design dict with containers, operators, connections

    Returns:
        Validation result with valid, blocking, warnings, score_cap
    """
    kb = get_default_kb()
    return kb.validate_design_structure(design)


# =============================================================================
# MAIN (FOR TESTING)
# =============================================================================

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Test the knowledge base
    kb = get_default_kb()

    # Test operator queries
    print("\n=== Testing Operator Queries ===")
    chop_ops = kb.query_operators({"family": "CHOP"})
    print(f"Found {len(chop_ops)} CHOP operators")

    audio_ops = kb.query_operators({"purpose_contains": "audio"})
    print(f"Found {len(audio_ops)} operators related to audio")

    # Test pattern queries
    print("\n=== Testing Pattern Queries ===")
    audio_patterns = kb.query_patterns("audio_reactive_visuals")
    print(f"Found {len(audio_patterns)} audio reactive patterns")

    # Test GLSL queries
    print("\n=== Testing GLSL Queries ===")
    glsl_top = kb.query_glsl("glsl_top")
    print(f"GLSL TOP has keys: {list(glsl_top.keys())}")

    # Test validation
    print("\n=== Testing Validation ===")
    print(f"CHOP:noise exists: {kb.validate_operator('CHOP', 'noise')}")
    print(f"CHOP:fakeop exists: {kb.validate_operator('CHOP', 'fakeop')}")
    print(f"CHOP:noise.type valid: {kb.validate_parameter('CHOP', 'noise', 'type')}")
    print(f"CHOP:noise.fakeparam valid: {kb.validate_parameter('CHOP', 'noise', 'fakeparam')}")

    missing = kb.check_operators_exist(["CHOP:noise", "CHOP:fakeop", "TOP:moviefilein"])
    print(f"Missing operators: {missing}")

    # Test type normalization
    print("\n=== Testing Type Normalization ===")
    test_types = [
        ("audiodeviceinCHOP", "audiodevicein"),
        ("noiseTOP", "noise"),
        ("gridSOP", "grid"),
        ("textDAT", "text"),
        ("geometryCOMP", "geometry"),
        ("audiodevicein", "audiodevicein"),  # No suffix
        ("analyze", "analyze"),              # No suffix
    ]
    for input_type, expected in test_types:
        result = kb._normalize_op_type(input_type)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {input_type} -> {result} (expected: {expected})")

    # Test buildable chain extraction
    print("\n=== Testing Buildable Chain ===")
    chain = kb.get_buildable_chain("audio_reactive_visuals")
    print(f"Pattern: {chain.get('pattern')}")
    print(f"Validated: {chain.get('validated')}")
    print(f"Operators: {len(chain.get('operators', []))}")
    for op in chain.get('operators', [])[:5]:
        print(f"  Step {op['step']}: {op['type']} ({op['family']}) - {op.get('role', 'N/A')}")

    # Test structure validation with various issues
    print("\n=== Testing Structure Validation ===")
    test_design = {
        'containers': [
            {'name': 'empty_container', 'operators': []},  # Empty - BLOCK
            {'name': 'audio', 'operators': [
                {'name': 'noise1', 'type': 'noise'},
                {'name': 'UNVALIDATED_mystery', 'type': 'unknown'}  # UNVALIDATED - BLOCK
            ]}
        ],
        'connections': [
            {'from': 'noise1', 'to': 'nonexistent'}  # Dangling - BLOCK
        ],
        'uncertainties': [
            {'type': 'param_unknown', 'needs_resolution': True, 'resolution': None}  # Unresolved - BLOCK
        ],
        'validation_summary': {
            'parameters_unvalidated': 2,
            'unvalidated_params_list': ['fakeparam1', 'fakeparam2']
        }
    }

    result = kb.validate_design_structure(test_design)
    print(f"Valid: {result['valid']}")
    print(f"Score Cap: {result['score_cap']}")
    print(f"Blocking Issues: {len(result['blocking'])}")
    for issue in result['blocking']:
        print(f"  - {issue['type']}")
    print(f"Warnings: {len(result['warnings'])}")

    # Test with network_design root key format
    print("\n=== Testing network_design Format ===")
    vanta_style = {
        'network_design': {
            'project': 'VANTA_Collapse',
            'containers': [
                {'name': 'audio', 'operators': [
                    {'name': 'analyze1', 'type': 'analyze'}
                ]}
            ],
            'connections': []
        }
    }
    result2 = kb.validate_design_structure(vanta_style)
    print(f"Parsed network_design format: Valid={result2['valid']}, Blocking={len(result2['blocking'])}")

    print("\n=== All Tests Complete ===")

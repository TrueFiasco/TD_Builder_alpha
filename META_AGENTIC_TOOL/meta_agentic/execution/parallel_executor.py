"""
Parallel Executor: Orchestrates parallel execution of TD network components.

For complex builds like RUTH, this module enables:
1. Splitting specs into component-specific tasks
2. Running TD Designer instances in parallel per component
3. Merging network designs into unified output
4. Coordinating dependencies between build phases

Architecture:
    Phase 1 (Foundation): Audio Analysis + Control System (sequential)
    Phase 2 (Visual Elements): Kate/Tendrils/Membrane/Demo/Env (parallel)
    Phase 3 (Integration): Effects + Camera (parallel after Phase 2)
    Phase 4 (Final): Post-Processing (sequential)
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
import logging
from datetime import datetime

from .blackboard import Blackboard, Phase, SectionID
from .metrics import MetricsCollector
from .kb_query import KnowledgeBase, get_default_kb

logger = logging.getLogger(__name__)


class BuildPhase(Enum):
    """Build phases for parallel execution."""
    FOUNDATION = "foundation"      # Audio + Control (sequential)
    VISUAL_ELEMENTS = "visual"     # Kate/Tendrils/Membrane/Demo/Env (parallel)
    INTEGRATION = "integration"    # Effects + Camera (parallel)
    FINAL = "final"               # Post-processing (sequential)


@dataclass
class ComponentSpec:
    """Specification for a single TOX component."""
    component_id: str
    tox_name: str
    phase: BuildPhase
    dependencies: list[str] = field(default_factory=list)
    spec_section: str = ""  # Section from user spec relevant to this component

    # Build configuration
    priority: int = 0  # Higher = built first within phase
    can_parallelize: bool = True
    estimated_complexity: int = 1  # 1-5 scale

    # Output tracking
    network_design: dict = field(default_factory=dict)
    build_result: dict = field(default_factory=dict)
    success: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class ParallelBuildConfig:
    """Configuration for parallel build execution."""
    max_parallel_tasks: int = 5
    timeout_per_component: int = 120  # seconds
    enable_parallel_visual: bool = True
    enable_parallel_integration: bool = True
    merge_strategy: str = "sequential"  # or "parallel"


# Standard RUTH-like component definitions
RUTH_COMPONENTS = {
    # Phase 1: Foundation (sequential - these feed everything else)
    "audio_analysis": ComponentSpec(
        component_id="audio_analysis",
        tox_name="audio_analysis.tox",
        phase=BuildPhase.FOUNDATION,
        dependencies=[],
        priority=10,
        can_parallelize=False,  # Must be first
        estimated_complexity=4
    ),
    "midi_control": ComponentSpec(
        component_id="midi_control",
        tox_name="midi_control.tox",
        phase=BuildPhase.FOUNDATION,
        dependencies=["audio_analysis"],
        priority=9,
        can_parallelize=False,
        estimated_complexity=3
    ),

    # Phase 2: Visual Elements (parallel - independent of each other)
    "kate_aura": ComponentSpec(
        component_id="kate_aura",
        tox_name="kate_aura.tox",
        phase=BuildPhase.VISUAL_ELEMENTS,
        dependencies=["audio_analysis", "midi_control"],
        priority=5,
        can_parallelize=True,
        estimated_complexity=4
    ),
    "tendril_system": ComponentSpec(
        component_id="tendril_system",
        tox_name="tendril_system.tox",
        phase=BuildPhase.VISUAL_ELEMENTS,
        dependencies=["audio_analysis", "midi_control"],
        priority=5,
        can_parallelize=True,
        estimated_complexity=5
    ),
    "membrane": ComponentSpec(
        component_id="membrane",
        tox_name="membrane.tox",
        phase=BuildPhase.VISUAL_ELEMENTS,
        dependencies=["audio_analysis", "midi_control"],
        priority=5,
        can_parallelize=True,
        estimated_complexity=4
    ),
    "demogorgon": ComponentSpec(
        component_id="demogorgon",
        tox_name="demogorgon.tox",
        phase=BuildPhase.VISUAL_ELEMENTS,
        dependencies=["audio_analysis", "midi_control"],
        priority=4,
        can_parallelize=True,
        estimated_complexity=5
    ),
    "environment": ComponentSpec(
        component_id="environment",
        tox_name="environment.tox",
        phase=BuildPhase.VISUAL_ELEMENTS,
        dependencies=["audio_analysis", "midi_control"],
        priority=5,
        can_parallelize=True,
        estimated_complexity=3
    ),

    # Phase 3: Integration (parallel after visual elements)
    "effects": ComponentSpec(
        component_id="effects",
        tox_name="effects.tox",
        phase=BuildPhase.INTEGRATION,
        dependencies=["kate_aura", "tendril_system", "membrane", "demogorgon"],
        priority=3,
        can_parallelize=True,
        estimated_complexity=4
    ),
    "camera": ComponentSpec(
        component_id="camera",
        tox_name="camera.tox",
        phase=BuildPhase.INTEGRATION,
        dependencies=["kate_aura", "demogorgon", "environment"],
        priority=3,
        can_parallelize=True,
        estimated_complexity=3
    ),

    # Phase 4: Final (sequential - needs all render outputs)
    "post_process": ComponentSpec(
        component_id="post_process",
        tox_name="post_process.tox",
        phase=BuildPhase.FINAL,
        dependencies=["effects", "camera"],
        priority=1,
        can_parallelize=False,
        estimated_complexity=3
    ),
}


class SpecSplitter:
    """
    Splits a complex spec into component-specific sub-specs.

    For RUTH-like builds, extracts relevant sections for each TOX:
    - Audio Analysis: Section 1
    - Kate's Aura: Section 2.1
    - Tendrils: Section 2.2
    - etc.
    """

    # Section mapping for RUTH-style specs
    SECTION_MARKERS = {
        "audio_analysis": ["## 1. AUDIO", "### 1.1", "### 1.2", "### 1.3"],
        "kate_aura": ["### 2.1 Kate's Aura"],
        "tendril_system": ["### 2.2 Tendrils"],
        "membrane": ["### 2.3 Membrane"],
        "demogorgon": ["### 2.4 Demogorgon"],
        "environment": ["### 2.5 Upside Down"],
        "effects": ["## 3. EFFECTS"],
        "camera": ["## 4. CAMERA"],
        "midi_control": ["## 5. CONTROL"],
        "post_process": ["## 7. POST-PROCESSING"],
    }

    def __init__(self, full_spec: str):
        self.full_spec = full_spec
        self.component_specs: dict[str, str] = {}

    def split(self) -> dict[str, str]:
        """
        Split the full spec into component-specific specs.

        Returns:
            Dict mapping component_id to its relevant spec section
        """
        lines = self.full_spec.split('\n')

        for component_id, markers in self.SECTION_MARKERS.items():
            component_lines = []
            capturing = False

            for i, line in enumerate(lines):
                # Check if we should start capturing
                for marker in markers:
                    if marker in line:
                        capturing = True
                        break

                if capturing:
                    # Check if we've hit the next major section
                    if line.startswith('## ') and component_lines:
                        # Check if this is a different section
                        is_our_section = any(marker in line for marker in markers)
                        if not is_our_section:
                            break

                    component_lines.append(line)

            self.component_specs[component_id] = '\n'.join(component_lines)

        # Also extract shared context (color system, summary, etc.)
        shared_context = self._extract_shared_context()

        # Prepend shared context to each component spec
        for component_id in self.component_specs:
            self.component_specs[component_id] = (
                f"# Shared Context\n{shared_context}\n\n"
                f"# Component: {component_id}\n"
                f"{self.component_specs[component_id]}"
            )

        return self.component_specs

    def _extract_shared_context(self) -> str:
        """Extract context shared across all components."""
        shared_sections = [
            "## QUICK REFERENCE",
            "## 6. COLOUR SYSTEM",
            "## SUMMARY OF KATE'S KEY WISHES"
        ]

        context_parts = []
        lines = self.full_spec.split('\n')

        for section in shared_sections:
            capturing = False
            section_lines = []

            for line in lines:
                if section in line:
                    capturing = True
                if capturing:
                    if line.startswith('## ') and section_lines and section not in line:
                        break
                    section_lines.append(line)

            if section_lines:
                context_parts.append('\n'.join(section_lines))

        return '\n\n'.join(context_parts)


class ParallelExecutor:
    """
    Orchestrates parallel execution of TD network components.

    Usage:
        executor = ParallelExecutor(spec, components, config)
        results = executor.execute()
    """

    def __init__(
        self,
        full_spec: str,
        components: dict[str, ComponentSpec] = None,
        config: ParallelBuildConfig = None,
        kb: KnowledgeBase = None
    ):
        self.full_spec = full_spec
        self.components = components or RUTH_COMPONENTS.copy()
        self.config = config or ParallelBuildConfig()
        self.kb = kb or get_default_kb()

        # Split spec into component-specific sections
        self.splitter = SpecSplitter(full_spec)
        self.component_specs = self.splitter.split()

        # Assign specs to components
        for comp_id, spec_text in self.component_specs.items():
            if comp_id in self.components:
                self.components[comp_id].spec_section = spec_text

        # Create per-component blackboards and metrics
        self.blackboards: dict[str, Blackboard] = {}
        self.metrics: dict[str, MetricsCollector] = {}

        # Results tracking
        self.phase_results: dict[BuildPhase, list[dict]] = {
            phase: [] for phase in BuildPhase
        }
        self.merged_design: dict = {}

        # Timing
        self.start_time: datetime = None
        self.phase_times: dict[BuildPhase, float] = {}

    def execute(self) -> dict:
        """
        Execute the full parallel build pipeline.

        Returns:
            Dict with:
                - components: dict of component results
                - merged_design: unified network design
                - timing: execution timing info
                - success: overall success bool
        """
        self.start_time = datetime.utcnow()

        try:
            # Phase 1: Foundation (sequential)
            logger.info("Starting Phase 1: Foundation")
            self._execute_phase(BuildPhase.FOUNDATION, parallel=False)

            # Phase 2: Visual Elements (parallel)
            logger.info("Starting Phase 2: Visual Elements")
            self._execute_phase(
                BuildPhase.VISUAL_ELEMENTS,
                parallel=self.config.enable_parallel_visual
            )

            # Phase 3: Integration (parallel)
            logger.info("Starting Phase 3: Integration")
            self._execute_phase(
                BuildPhase.INTEGRATION,
                parallel=self.config.enable_parallel_integration
            )

            # Phase 4: Final (sequential)
            logger.info("Starting Phase 4: Final")
            self._execute_phase(BuildPhase.FINAL, parallel=False)

            # Merge all network designs
            self._merge_network_designs()

            return self._build_result()

        except Exception as e:
            logger.error(f"Parallel execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "components": {
                    cid: {
                        "success": c.success,
                        "errors": c.errors
                    }
                    for cid, c in self.components.items()
                },
                "merged_design": None
            }

    def _execute_phase(self, phase: BuildPhase, parallel: bool = True):
        """Execute all components in a phase."""
        phase_start = datetime.utcnow()

        # Get components for this phase, sorted by priority
        phase_components = [
            c for c in self.components.values()
            if c.phase == phase
        ]
        phase_components.sort(key=lambda c: -c.priority)

        if not phase_components:
            return

        if parallel and len(phase_components) > 1:
            self._execute_parallel(phase_components)
        else:
            self._execute_sequential(phase_components)

        self.phase_times[phase] = (datetime.utcnow() - phase_start).total_seconds()

    def _execute_sequential(self, components: list[ComponentSpec]):
        """Execute components sequentially."""
        for component in components:
            self._execute_component(component)

    def _execute_parallel(self, components: list[ComponentSpec]):
        """Execute components in parallel using ThreadPoolExecutor."""
        with ThreadPoolExecutor(max_workers=self.config.max_parallel_tasks) as executor:
            futures = {
                executor.submit(self._execute_component, comp): comp
                for comp in components
            }

            for future in as_completed(futures, timeout=self.config.timeout_per_component * len(components)):
                comp = futures[future]
                try:
                    future.result()
                except Exception as e:
                    comp.success = False
                    comp.errors.append(f"Parallel execution failed: {e}")
                    logger.error(f"Component {comp.component_id} failed: {e}")

    def _execute_component(self, component: ComponentSpec) -> dict:
        """
        Execute a single component build.

        This creates a mini-workflow for the component:
        1. Create component-specific blackboard
        2. Write component spec to requirements
        3. Run TD Designer for this component
        4. Run Network Builder for this component
        5. Store results
        """
        logger.info(f"Building component: {component.component_id}")

        # Check dependencies
        for dep_id in component.dependencies:
            dep = self.components.get(dep_id)
            if dep and not dep.success:
                component.errors.append(f"Dependency {dep_id} failed")
                component.success = False
                return {"success": False, "error": f"Dependency {dep_id} failed"}

        try:
            # Create component-specific blackboard
            bb = Blackboard(project_name=f"component_{component.component_id}")
            self.blackboards[component.component_id] = bb

            # Create metrics collector
            metrics = MetricsCollector(
                strategy="parallel",
                project=f"component_{component.component_id}"
            )
            self.metrics[component.component_id] = metrics

            # Write component spec to requirements
            bb.write(
                SectionID.REQUIREMENTS,
                {
                    "original_prompt": component.spec_section,
                    "component_id": component.component_id,
                    "tox_name": component.tox_name,
                    "dependencies": component.dependencies
                },
                author="parallel_executor"
            )

            # TODO: Execute TD Designer for this component
            # For now, create stub network design
            component.network_design = self._stub_component_design(component)

            # Write to blackboard
            bb.write(
                SectionID.NETWORK_DESIGN,
                component.network_design,
                author=f"td_designer_{component.component_id}"
            )

            component.success = True
            logger.info(f"Component {component.component_id} completed successfully")

            return {"success": True, "design": component.network_design}

        except Exception as e:
            component.errors.append(str(e))
            component.success = False
            logger.error(f"Component {component.component_id} failed: {e}")
            return {"success": False, "error": str(e)}

    def _stub_component_design(self, component: ComponentSpec) -> dict:
        """
        Create stub network design for a component.

        In real execution, this would be replaced by actual TD Designer output.
        """
        return {
            "component_id": component.component_id,
            "tox_name": component.tox_name,
            "status": "stub",
            "message": f"Network design for {component.component_id} - requires LLM execution",
            "inputs": [f"in_{dep}" for dep in component.dependencies],
            "outputs": [f"out_{component.component_id}"],
            "operators": [],  # Would be populated by TD Designer
            "connections": []  # Would be populated by TD Designer
        }

    def _merge_network_designs(self):
        """Merge all component network designs into unified design."""
        self.merged_design = {
            "project_name": "merged_parallel_build",
            "components": {},
            "inter_component_connections": [],
            "master_network": {
                "operators": [],
                "connections": []
            }
        }

        # Collect all component designs
        for comp_id, component in self.components.items():
            if component.success and component.network_design:
                self.merged_design["components"][comp_id] = component.network_design

        # Build inter-component connections based on dependencies
        for comp_id, component in self.components.items():
            for dep_id in component.dependencies:
                self.merged_design["inter_component_connections"].append({
                    "from": dep_id,
                    "to": comp_id,
                    "connection_type": "chop_reference"  # or other types
                })

    def _build_result(self) -> dict:
        """Build the final result dictionary."""
        total_time = (datetime.utcnow() - self.start_time).total_seconds()

        successful_components = sum(1 for c in self.components.values() if c.success)
        total_components = len(self.components)

        return {
            "success": successful_components == total_components,
            "components": {
                comp_id: {
                    "success": comp.success,
                    "errors": comp.errors,
                    "phase": comp.phase.value,
                    "tox_name": comp.tox_name
                }
                for comp_id, comp in self.components.items()
            },
            "merged_design": self.merged_design,
            "timing": {
                "total_seconds": total_time,
                "phase_times": {
                    phase.value: time
                    for phase, time in self.phase_times.items()
                }
            },
            "stats": {
                "successful": successful_components,
                "failed": total_components - successful_components,
                "total": total_components
            }
        }


def extract_components_from_spec(spec: str) -> dict[str, ComponentSpec]:
    """
    Analyze a spec and extract component definitions.

    Looks for file structure hints, TOX mentions, and section headers
    to determine what components should be built.
    """
    components = {}

    # Look for file structure section
    if "/toxes/" in spec.lower() or ".tox" in spec.lower():
        # Extract TOX names from file structure
        import re
        tox_pattern = r'(\w+)\.tox'
        matches = re.findall(tox_pattern, spec)

        for match in matches:
            if match not in components:
                # Determine phase based on name
                phase = _infer_phase_from_name(match)
                components[match] = ComponentSpec(
                    component_id=match,
                    tox_name=f"{match}.tox",
                    phase=phase,
                    dependencies=_infer_dependencies(match, list(components.keys()))
                )

    # If no TOXes found, use RUTH defaults
    if not components:
        components = RUTH_COMPONENTS.copy()

    return components


def _infer_phase_from_name(name: str) -> BuildPhase:
    """Infer build phase from component name."""
    name_lower = name.lower()

    if 'audio' in name_lower or 'midi' in name_lower or 'control' in name_lower:
        return BuildPhase.FOUNDATION
    elif 'post' in name_lower or 'output' in name_lower:
        return BuildPhase.FINAL
    elif 'effect' in name_lower or 'camera' in name_lower:
        return BuildPhase.INTEGRATION
    else:
        return BuildPhase.VISUAL_ELEMENTS


def _infer_dependencies(name: str, existing: list[str]) -> list[str]:
    """Infer dependencies from component name."""
    deps = []
    name_lower = name.lower()

    # Most things depend on audio analysis
    if 'audio' not in name_lower:
        if 'audio_analysis' in existing:
            deps.append('audio_analysis')

    # Post-process depends on effects and camera
    if 'post' in name_lower:
        for existing_name in existing:
            if 'effect' in existing_name or 'camera' in existing_name:
                deps.append(existing_name)

    return deps

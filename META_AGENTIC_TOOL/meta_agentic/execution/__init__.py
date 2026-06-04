"""
Execution Layer for META_AGENTIC_TOOL

This package provides the execution infrastructure for running expert workflows.

Components:
    - blackboard: Central PROJECT DOCUMENT state management
    - metrics: Workflow execution metrics collection
    - orchestrator: Phase management and expert routing
    - strategy_runner: Strategy plugin system
    - expert_executor: Expert prompt execution
    - critic_integration: Critic scoring and validation
    - kb_query: Knowledge base querying

Usage:
    from meta_agentic.execution import (
        Blackboard, Phase, SectionID,
        MetricsCollector,
        WorkflowOrchestrator,
        CriticIntegration,
        run_strategy,
        KnowledgeBase
    )
"""

from .blackboard import Blackboard, Phase, SectionID, BlockingIssue
from .metrics import MetricsCollector, TokenUsage, compare_metrics
from .strategy_runner import (
    run_strategy,
    StrategyConfig,
    BuildResult,
    QualityTargets,
    InvolvementLevel,
    Preset,
    WorkflowStrategy,
    StrategyRegistry,
    get_registry,
    V2ImprovedStrategy,
    V3EvolutionaryStrategy,
    V4BlackboardStrategy,
    V5DeepRefinementStrategy,
    V6UnifiedStrategy,
)

# Expert Executor
from .expert_executor import (
    ExpertExecutor,
    ExpertConfig,
    get_expert_executor,
    execute_expert,
    EXPERT_CONFIGS,
)

# Critic Integration
from .critic_integration import (
    CriticIntegration,
    CritiqueResult,
)

# LLM Executor
from .llm_executor import (
    LLMExecutor,
    AnthropicExecutor,
    SubagentExecutor,
    MockExecutor,
)

# Knowledge Base
from .kb_query import KnowledgeBase, QueryResult, ValidationResult, ExpertiseFiles, get_default_kb

# Orchestrator
from .orchestrator import WorkflowOrchestrator

# Parallel Executor
from .parallel_executor import (
    ParallelExecutor,
    ParallelBuildConfig,
    ComponentSpec,
    BuildPhase,
    SpecSplitter,
    RUTH_COMPONENTS,
    extract_components_from_spec,
)

# Workflow Recorder
from .workflow_recorder import (
    WorkflowRecorder,
    WorkflowRecord,
    PhaseRecord,
    get_recorder,
)

# V6 Support Modules
from .variant_spawner import (
    VariantSpawner,
    VariantConfig,
    VariantResult,
    BreedingResult,
    VariantDirective,
    create_variant_result,
    DEFAULT_DIRECTIVES,
)

from .critic_context import (
    PersistentCriticContext,
    CriticContextFrame,
    CriticIssue,
    IssueClassification,
    IssueSeverity,
    LearnedPreference,
    create_critique_frame,
)

from .expert_pool import (
    ExpertPool,
    ExpertType,
    ExpertQuery,
    ExpertResponse,
    ExpertConsultation,
    PaletteComponent,
    create_expert_pool,
)

__all__ = [
    # Blackboard
    "Blackboard",
    "Phase",
    "SectionID",
    "BlockingIssue",
    # Metrics
    "MetricsCollector",
    "TokenUsage",
    "compare_metrics",
    # Strategy Runner
    "run_strategy",
    "StrategyConfig",
    "BuildResult",
    "QualityTargets",
    "InvolvementLevel",
    "Preset",
    "WorkflowStrategy",
    "StrategyRegistry",
    "get_registry",
    "V2ImprovedStrategy",
    "V3EvolutionaryStrategy",
    "V4BlackboardStrategy",
    "V5DeepRefinementStrategy",
    "V6UnifiedStrategy",
    # Orchestrator
    "WorkflowOrchestrator",
    # Expert Executor
    "ExpertExecutor",
    "ExpertConfig",
    "get_expert_executor",
    "execute_expert",
    "EXPERT_CONFIGS",
    # Critic Integration
    "CriticIntegration",
    "CritiqueResult",
    # LLM Executor
    "LLMExecutor",
    "AnthropicExecutor",
    "SubagentExecutor",
    "MockExecutor",
    # Knowledge Base
    "KnowledgeBase",
    "QueryResult",
    "ValidationResult",
    "ExpertiseFiles",
    "get_default_kb",
    # Parallel Executor
    "ParallelExecutor",
    "ParallelBuildConfig",
    "ComponentSpec",
    "BuildPhase",
    "SpecSplitter",
    "RUTH_COMPONENTS",
    "extract_components_from_spec",
    # Workflow Recorder
    "WorkflowRecorder",
    "WorkflowRecord",
    "PhaseRecord",
    "get_recorder",
    # V6 Variant Spawner
    "VariantSpawner",
    "VariantConfig",
    "VariantResult",
    "BreedingResult",
    "VariantDirective",
    "create_variant_result",
    "DEFAULT_DIRECTIVES",
    # V6 Critic Context
    "PersistentCriticContext",
    "CriticContextFrame",
    "CriticIssue",
    "IssueClassification",
    "IssueSeverity",
    "LearnedPreference",
    "create_critique_frame",
    # V6 Expert Pool
    "ExpertPool",
    "ExpertType",
    "ExpertQuery",
    "ExpertResponse",
    "ExpertConsultation",
    "PaletteComponent",
    "create_expert_pool",
]

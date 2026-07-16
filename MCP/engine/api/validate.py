"""Single construction seam for the offline validation stack.

THE one place the OperatorRegistry -> FormatConverter -> ValidationPipeline
trio is wired. Consumers: MCP/server_core/mcp_server.py (td_validate /
td_convert handler singletons), eval/agent_eval/score.py (out-of-band scorer),
eval/build_gate/track_a_offline.py (in-process gate), api/network_builder.py,
cli/td_validate.py. Before this seam the trio construction was copy-pasted at
all five sites, each promising in a comment to stay in sync with the others.

LIGHT-DEPS CONTRACT: importing THIS MODULE is dependency-free (sys/pathlib
only -- the trio imports live inside the factory), so light-deps consumers
(score.py: no mcp_server, no ML stack) can import it unconditionally.

KB CONTRACT: OperatorRegistry() reads KB/operators.json at construction and
raises FileNotFoundError when the KB is absent. That is deliberately
PROPAGATED -- each consumer owns its own degradation story (mcp_server flips
UNIFIED_SYSTEM_ENABLED; score.validate_design never raises; the CLI exits 2).

Both contracts are pinned by tests/engine/test_validation_stack_seam.py.
"""
import sys
from pathlib import Path

# Self-anchor (same convention as api/network_builder.py): make `core.*` /
# `validation.*` resolvable even when this file is loaded by path.
_ENGINE_ROOT = Path(__file__).resolve().parents[1]
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))


def build_validation_stack():
    """Construct the validation trio.

    Returns:
        (OperatorRegistry, FormatConverter, ValidationPipeline) sharing one
        registry (the KB read is paid once).

    Raises:
        FileNotFoundError: when the KB (operators.json) is absent -- callers
        keep their existing handling.
    """
    from core.format_converter import FormatConverter
    from core.operator_registry import OperatorRegistry
    from validation.pipeline import ValidationPipeline

    registry = OperatorRegistry()
    return registry, FormatConverter(registry), ValidationPipeline(registry)

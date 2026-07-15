"""Import isolation (harness 1a) -> quarantine absence pins (harness W2a).

History: mcp_server.py used to import the workflow-orchestration trio
(Blackboard / MetricsCollector / WorkflowOrchestrator -- dead, instantiated by no
tool path) in the SAME try block as ToxBuilder/ToeBuilderBridge (live), so an
ImportError in any dead module disabled td_build_project entirely. Harness 1a
split the imports and pinned the split by poisoning the trio in a subprocess.
W2a then quarantined the trio to quarantine/meta_agentic_orchestration/ and
deleted the never-consumed query-tracker and compaction stubs, which dissolves
the poison premise: absence is now the ground state.

What this module pins now (mirrors tests/acceptance P01b's removed-tool
absence pattern):
  1. The trio is gone from the import path and from meta_agentic/execution/.
  2. mcp_server.py carries no textual residue of the trio or the deleted stubs.
  3. De-hostage core, ground state: a fresh interpreter loads the server with
     EXPERT_WORKFLOW_ENABLED=True, none of the dead flags reappear, and BOTH
     build modes work through _run_build.
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402

bootstrap.setup()

_EXECUTION_DIR = _REPO_ROOT / "MCP" / "server_core" / "meta_agentic" / "execution"
_SERVER_SRC = _REPO_ROOT / "MCP" / "server_core" / "mcp_server.py"

_QUARANTINE_HINT = (
    "quarantined by W2a under the quarantine-not-fix decision -- see "
    "quarantine/README.md before reintroducing anything (revival = owner "
    "decision + dedicated wave, and D6 designs against docs/specs/, not this code)"
)

# The three quarantined modules (file name, import path).
_TRIO = (
    ("blackboard.py", "meta_agentic.execution.blackboard"),
    ("metrics.py", "meta_agentic.execution.metrics"),
    ("orchestrator.py", "meta_agentic.execution.orchestrator"),
)

# Tokens that must never reappear in mcp_server.py source: the trio's symbols
# and flag, plus the deleted query-tracker and compaction stubs (their flags
# and fallbacks included -- they were never consumed by any tool path).
_BANNED_SERVER_TOKENS = (
    # workflow-orchestration trio (W2a quarantine)
    "meta_agentic.execution.blackboard",
    "meta_agentic.execution.metrics",
    "meta_agentic.execution.orchestrator",
    "Blackboard",
    "SectionID",
    "MetricsCollector",
    "WorkflowOrchestrator",
    "StrategyConfig",
    "WORKFLOW_ORCHESTRATION_ENABLED",
    # query-tracker stub (module meta_agentic.history never existed)
    "QUERY_TRACKING_ENABLED",
    "log_query",
    "QueryTracker",
    "meta_agentic.history",
    # compaction stub (module meta_agentic.compaction never existed)
    "HAS_COMPACTION",
    "COMPACTION_IMPORT_ERROR",
    "meta_agentic.compaction",
    "compact_events_to_state",
    "refresh_legacy_yaml",
    # sub-agent tool executor: 0.1.1 removed its AgentWithTools callers
    # (spawn_engineer/spawn_expert) but left the executor def-only; deleted by
    # the 2026-07 dead-weight sweep. It had drifted to a shadow dispatch (11
    # names vs the registry's 17, divergent error contract) — any future
    # in-process tool access must wrap call_tool(), never a second if/elif.
    "execute_tool_for_agent",
)


# Files quarantined by the 2026-07 dead-weight sweep: repo-root-relative paths
# that must stay gone from their live locations (the preserved copies live under
# quarantine/deadweight_2026_07/ -- see that manifest before reintroducing).
_DEADWEIGHT_QUARANTINED_2026_07 = (
    "MCP/td-webserver/genHandlers.js",
    "MCP/td-webserver/templates/mcp/api_controller_handlers.mustache",
)


def test_deadweight_2026_07_absent_from_live_tree():
    for rel in _DEADWEIGHT_QUARANTINED_2026_07:
        leftover = _REPO_ROOT.joinpath(*rel.split("/"))
        assert not leftover.exists(), (
            f"{leftover} exists again -- it was quarantined by the 2026-07 "
            f"dead-weight sweep under the quarantine-not-fix decision; see "
            f"quarantine/README.md (deadweight_2026_07) before reintroducing "
            f"(revival = owner decision + dedicated wave)"
        )


def test_orchestration_trio_absent_from_import_path():
    """The trio must be gone both as files in the execution package and as
    importable modules on the server's import path (bootstrap view)."""
    for filename, module_path in _TRIO:
        leftover = _EXECUTION_DIR / filename
        assert not leftover.exists(), (
            f"{leftover} exists again -- the orchestration trio was {_QUARANTINE_HINT}"
        )
        spec = importlib.util.find_spec(module_path)
        assert spec is None, (
            f"'{module_path}' is importable again (resolved to {spec.origin}) -- "
            f"the orchestration trio was {_QUARANTINE_HINT}"
        )


def test_ground_truth_quarantined():
    """ground_truth.py (INERT-since-birth param-schema validator) must be gone from
    the execution package and not importable, and the builder must not import it.
    Quarantined by W3a -- the real param corpus was never shipped and its sole
    consumer always took the fallback path (see quarantine/README.md)."""
    leftover = _EXECUTION_DIR / "ground_truth.py"
    assert not leftover.exists(), (
        f"{leftover} exists again -- ground_truth.py was {_QUARANTINE_HINT}"
    )
    spec = importlib.util.find_spec("meta_agentic.execution.ground_truth")
    assert spec is None, (
        f"'meta_agentic.execution.ground_truth' is importable again "
        f"(resolved to {spec.origin}) -- it was {_QUARANTINE_HINT}"
    )
    bridge_src = (_EXECUTION_DIR / "toe_builder_bridge.py").read_text(encoding="utf-8")
    assert "from .ground_truth import" not in bridge_src and "get_ground_truth" not in bridge_src, (
        "toe_builder_bridge.py still references the quarantined ground_truth module"
    )


def test_mcp_server_source_free_of_dead_stubs():
    """mcp_server.py must carry no residue of the trio import or the deleted
    query-tracker/compaction stubs -- not even behind a fail-soft try/except."""
    src = _SERVER_SRC.read_text(encoding="utf-8")
    hits = [tok for tok in _BANNED_SERVER_TOKENS if tok in src]
    assert not hits, (
        f"mcp_server.py references removed dead-code symbols {hits} -- these were "
        f"deleted/{_QUARANTINE_HINT}"
    )


# ---------------------------------------------------------------------------
# De-hostage core, ground state (was: poisoned-trio subprocess).
# The child interpreter imports the real server module, whose registry init
# reads KB/operators.json -- the KB-free CI lane deselects this via the marker.
# Runs in a fresh interpreter because the shared `server` fixture caches the
# module in-process for the whole pytest session; this must observe a clean
# import, then drives _run_build for both modes -- the same entry point the
# sync and async tool callers use (see tests/engine/test_build_mode.py).
# ---------------------------------------------------------------------------
_CHILD = '''
import importlib.util
import json
import sys
from pathlib import Path

repo_root, out_dir = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(repo_root))
import bootstrap
bootstrap.setup()

spec = importlib.util.spec_from_file_location(
    "td_builder_mcp_server_groundstate",
    str(repo_root / "MCP" / "server_core" / "mcp_server.py"),
)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
if sys.__stdout__ is not None:
    sys.stdout = sys.__stdout__  # server redirects stdout->stderr at import

import asyncio

design = {
    "operators": [
        {"name": "noise1", "type": "noise", "family": "CHOP"},
        {"name": "null1", "type": "null", "family": "CHOP"},
    ],
    "connections": [{"from": "noise1", "to": "null1"}],
}
report = {
    "expert_workflow_enabled": bool(getattr(mod, "EXPERT_WORKFLOW_ENABLED", False)),
    "leftover_stub_attrs": [a for a in (
        "WORKFLOW_ORCHESTRATION_ENABLED", "QUERY_TRACKING_ENABLED",
        "HAS_COMPACTION", "COMPACTION_IMPORT_ERROR", "log_query",
    ) if hasattr(mod, a)],
    "tox": asyncio.run(mod._run_build(None, dict(design), {}, "iso_tox", out_dir, "tox")),
    "toe": asyncio.run(mod._run_build(None, dict(design), {}, "iso_toe", out_dir, "toe")),
}
print(json.dumps(report, default=str))
'''


@pytest.mark.requires_kb
def test_builders_independent_in_trio_free_ground_state(tmp_path):
    child = tmp_path / "groundstate_child.py"
    child.write_text(_CHILD, encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    env = dict(os.environ)
    env.pop("TD_BUILDER_ROOT", None)  # child must resolve its own tree, not a relocated one
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(child), str(_REPO_ROOT), str(out_dir)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(_REPO_ROOT), env=env, timeout=900,
    )
    assert proc.returncode == 0, (
        f"ground-state child crashed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    report = json.loads(proc.stdout.strip().splitlines()[-1])

    # De-hostage core: builders alive with the trio quarantined away entirely.
    assert report["expert_workflow_enabled"] is True, report
    # No dead flag may resurface at module scope, and the import must be
    # residue-silent (the 1a fail-soft warning died with the import block).
    assert report["leftover_stub_attrs"] == [], (
        f"dead-code flags back on the server module: {report['leftover_stub_attrs']} -- "
        f"these were {_QUARANTINE_HINT}"
    )
    assert "orchestration modules not available" not in proc.stderr, proc.stderr[-2000:]

    tox, toe = report["tox"], report["toe"]
    # Routing pins that hold with or without TD's toecollapse on the machine:
    # simple+tox stays on the td_build_project envelope (no "builder" key); the
    # BUG-1 promotion still routes simple+toe onto ToeBuilderBridge.
    assert "builder" not in tox, tox
    assert toe.get("builder") == "ToeBuilderBridge", toe

    if tox.get("status") == "SUCCESS" and toe.get("status") == "SUCCESS":
        assert str(tox["output_file"]).endswith(".tox"), tox
        assert str(toe["output_file"]).endswith(".toe"), toe
        assert Path(str(toe["output_file"])).stat().st_size > 100, toe
    else:
        pytest.skip(
            "toecollapse unavailable; ground-state import + routing verified without "
            f"collapsed files: tox={tox.get('message')!r} toe={toe.get('message')!r}"
        )

"""Import isolation (harness remediation 1a): the live builders must not be held
hostage by the workflow-orchestration trio.

mcp_server.py used to import Blackboard/MetricsCollector/WorkflowOrchestrator (dead —
instantiated by no tool path) in the SAME try block as ToxBuilder/ToeBuilderBridge (live),
under the single EXPERT_WORKFLOW_ENABLED flag — an ImportError in any dead module disabled
td_build_project entirely. This pins the split: with those three modules poisoned to raise
ImportError BEFORE the server module is imported, the server must still load with
EXPERT_WORKFLOW_ENABLED=True and build BOTH a .tox and a .toe.

The poisoned import runs in a subprocess: the shared `server` fixture caches the real module
in-process for the whole pytest session, so only a fresh interpreter guarantees the poison is
in place before the server's import-time try blocks run (and no other test sees the poison).
"""
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

# Runs in a fresh interpreter. Poisons sys.modules (a None entry makes `import X`
# raise ImportError) before the server module executes its import-time try blocks,
# then drives _run_build for both modes — the same entry point the sync and async
# tool callers use (see tests/engine/test_build_mode.py).
_CHILD = '''
import importlib.util
import json
import sys
from pathlib import Path

repo_root, out_dir = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(repo_root))
import bootstrap
bootstrap.setup()

for name in (
    "meta_agentic.execution.blackboard",
    "meta_agentic.execution.metrics",
    "meta_agentic.execution.orchestrator",
):
    sys.modules[name] = None

spec = importlib.util.spec_from_file_location(
    "td_builder_mcp_server_poisoned",
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
    "orchestration_enabled": bool(getattr(mod, "WORKFLOW_ORCHESTRATION_ENABLED", True)),
    "tox": asyncio.run(mod._run_build(None, dict(design), {}, "iso_tox", out_dir, "tox")),
    "toe": asyncio.run(mod._run_build(None, dict(design), {}, "iso_toe", out_dir, "toe")),
}
print(json.dumps(report, default=str))
'''


def test_builders_survive_poisoned_orchestration_trio(tmp_path):
    child = tmp_path / "poisoned_child.py"
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
        f"poisoned child crashed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    report = json.loads(proc.stdout.strip().splitlines()[-1])

    # De-hostage core: builders alive while the trio is import-dead — and the poison
    # really bit (orchestration flag down + the fail-soft warning on stderr).
    assert report["expert_workflow_enabled"] is True, report
    assert report["orchestration_enabled"] is False, report
    assert "orchestration modules not available" in proc.stderr, proc.stderr[-2000:]

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
            "toecollapse unavailable; import isolation + routing verified without "
            f"collapsed files: tox={tox.get('message')!r} toe={toe.get('message')!r}"
        )

"""Hygiene bundle H3 — the validation-stack construction seam's two contracts.

MCP/engine/api/validate.py::build_validation_stack is THE one place the
OperatorRegistry -> FormatConverter -> ValidationPipeline trio is wired
(consumers: mcp_server.py, eval/agent_eval/score.py,
eval/build_gate/track_a_offline.py, api/network_builder.py, cli/td_validate.py).
Two contracts a refactor could silently break, both proven behaviorally in
fresh subprocesses:

C1 (light-deps import) — importing the MODULE pulls no engine machinery: the
trio imports live inside the factory, so light-deps consumers (score.py: no ML
stack) can import it unconditionally.

C2 (KB error propagation) — the factory RAISES FileNotFoundError when the KB
is absent (each consumer owns its own degradation story); it must not swallow
or translate it. Proven under a TD_BUILDER_ROOT override pointing at an empty
dir — deterministic even on machines WITH the real KB.

The happy path needs no test here: every kb-full-lane suite constructs through
the seam (server import, scorer tests, build gate, tests/engine builders).

Both tests are KB-free — no ``requires_kb`` marker.
"""
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/engine/ -> repo root


_C1_CHILD = r'''
import sys

repo_root, engine_root = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo_root)
sys.path.insert(0, engine_root)

import api.validate  # noqa: F401

heavy = [m for m in ("core", "validation") if m in sys.modules]
assert not heavy, f"importing api.validate pulled engine machinery: {heavy}"
print("C1_OK")
'''


def test_seam_module_import_is_dependency_free(tmp_path):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _C1_CHILD, str(_REPO_ROOT),
         str(_REPO_ROOT / "MCP" / "engine")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(tmp_path), env=env, timeout=120,
    )
    assert proc.returncode == 0 and "C1_OK" in proc.stdout, (
        f"rc={proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


_C2_CHILD = r'''
import sys

repo_root, engine_root = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo_root)
sys.path.insert(0, engine_root)

from api.validate import build_validation_stack

try:
    build_validation_stack()
    raise SystemExit("FAIL: factory built a stack with no KB present")
except FileNotFoundError:
    print("C2_OK")
'''


def test_seam_propagates_filenotfounderror_when_kb_absent(tmp_path):
    empty_root = tmp_path / "empty_root"
    empty_root.mkdir()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["TD_BUILDER_ROOT"] = str(empty_root)  # registry resolves KB under here
    proc = subprocess.run(
        [sys.executable, "-c", _C2_CHILD, str(_REPO_ROOT),
         str(_REPO_ROOT / "MCP" / "engine")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(tmp_path), env=env, timeout=120,
    )
    assert proc.returncode == 0 and "C2_OK" in proc.stdout, (
        f"rc={proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )

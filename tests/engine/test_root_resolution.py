"""Wave 5 — repo-root resolution: masking-independent isolation + TD_BUILDER_ROOT guard.

Two properties, both proven behaviorally in fresh subprocesses (never in-process, where
paths.REPO_ROOT / KB_* freeze at first import):

A1 (isolation) — ``param_name_resolver`` self-bootstraps ``paths`` onto sys.path when
imported IN PLACE with the repo root ABSENT (no bootstrap, cwd outside the repo). This is the
regression guard for the ``parents[3]`` -> ``parents[4]`` fix; it was masked because the
normal boot chain puts the correct repo root on sys.path first. The child here deliberately
does NOT insert the repo root (unlike tests/engine/test_import_isolation._CHILD, whose
repo-root insert would silently re-mask the bug). RED before the fix (ModuleNotFoundError:
paths), GREEN after.

A3 (override) — every migrated shipping resolver honors ``TD_BUILDER_ROOT``: with the env set
to a temp dir, each resolver's KB-resolution path lands UNDER that dir. Note we assert on the
KB-resolution paths (delegated to ``paths``), NOT on ``param_name_resolver._REPO_ROOT`` — that
is the self-derived bootstrap root (a function of the file's on-disk location) and does not,
and must not, move under the override.

Both tests are KB-free (no operators.json load) — no ``requires_kb`` marker.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/engine/ -> repo root
_PNR_FILE = (_REPO_ROOT / "MCP" / "server_core" / "meta_agentic" / "execution"
             / "param_name_resolver.py")


# ---------------------------------------------------------------------------
# A1 — isolation: import in place, repo root ABSENT from sys.path
# ---------------------------------------------------------------------------
_A1_CHILD = r'''
import importlib.util
import sys
from pathlib import Path

repo_root, mod_file = sys.argv[1], sys.argv[2]

# HARD isolation proof: nothing may have put the repo root (or `paths`) within reach
# before the module's own self-bootstrap runs. If this fails, the test env is compromised
# (e.g. a stray insert) and the result would be meaningless -- so fail loud.
assert repo_root not in sys.path, "repo root leaked onto sys.path -- isolation broken"
try:
    import paths  # noqa: F401
    raise SystemExit("FAIL: `paths` importable before self-bootstrap -- isolation broken")
except ModuleNotFoundError:
    pass

# Import param_name_resolver IN PLACE (real file), root absent. Pre-fix this raises
# ModuleNotFoundError('paths') because parents[3]=.../MCP has no paths.py; post-fix the
# module inserts the true repo root (parents[4]) and `from paths import ...` resolves.
spec = importlib.util.spec_from_file_location("pnr_iso", mod_file)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

assert (mod._REPO_ROOT / "paths.py").exists(), f"_REPO_ROOT wrong: {mod._REPO_ROOT}"
assert Path(mod._REPO_ROOT) == Path(repo_root), f"_REPO_ROOT={mod._REPO_ROOT} != {repo_root}"
assert str(mod.KB_PATH).startswith(repo_root), f"KB_PATH not under repo root: {mod.KB_PATH}"
print("ISO_OK")
'''


def test_param_name_resolver_self_bootstraps_in_isolation(tmp_path):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)       # do not leak the repo onto the child's path
    env.pop("TD_BUILDER_ROOT", None)  # neutral: this test is about importability, not override
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _A1_CHILD, str(_REPO_ROOT), str(_PNR_FILE)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(tmp_path),  # cwd outside the repo so '' on sys.path != repo root
        env=env, timeout=120,
    )
    assert proc.returncode == 0 and "ISO_OK" in proc.stdout, (
        "param_name_resolver failed to self-bootstrap `paths` when imported in isolation "
        "(this is the masked parents[3] bug if RED).\n"
        f"rc={proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


# ---------------------------------------------------------------------------
# A3 — TD_BUILDER_ROOT override honored by every migrated resolver
# ---------------------------------------------------------------------------
_A3_CHILD = r'''
import importlib
import json
import sys
from pathlib import Path

repo_root, tmp = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo_root)      # to import bootstrap (code imports only)
import bootstrap
bootstrap.setup()

import paths
# TD_BUILDER_ROOT (set by the parent in env) must drive the canonical root.
assert Path(paths.REPO_ROOT) == Path(tmp), f"override ignored by paths: {paths.REPO_ROOT}"

results = {}
pnr = importlib.import_module("meta_agentic.execution.param_name_resolver")
results["pnr.KB_PATH"] = str(pnr.KB_PATH)   # delegated to paths -> must move; _REPO_ROOT must NOT
results["pnr._REPO_ROOT"] = str(pnr._REPO_ROOT)

from core.operator_registry import _default_registry_path
results["registry"] = str(_default_registry_path())

gv = importlib.import_module("validation.grounding_validator")
results["grounding"] = str(gv._default_kb_operators())

csv = importlib.import_module("validation.component_source_validator")
results["component"] = str(csv._default_palette_components())

tbb = importlib.import_module("meta_agentic.execution.toe_builder_bridge")
results["docked"] = str(tbb.DOCKED_DATS_PATH)
results["expertise"] = str(tbb.EXPERTISE_DIR)
print(json.dumps(results))
'''

# KB-resolution paths that MUST relocate under TD_BUILDER_ROOT.
_A3_MUST_MOVE = ("pnr.KB_PATH", "registry", "grounding", "component", "docked", "expertise")


def test_migrated_resolvers_honor_td_builder_root(tmp_path):
    override = tmp_path / "relocated_root"
    override.mkdir()
    env = dict(os.environ)
    env["TD_BUILDER_ROOT"] = str(override)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, "-c", _A3_CHILD, str(_REPO_ROOT), str(override)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=120,
    )
    assert proc.returncode == 0, (
        f"child crashed (rc={proc.returncode})\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    results = json.loads(proc.stdout.strip().splitlines()[-1])

    ov = str(override)
    for key in _A3_MUST_MOVE:
        assert results[key].startswith(ov), (
            f"{key} did not honor TD_BUILDER_ROOT: {results[key]} not under {ov}"
        )
    # The self-derived bootstrap root is location-based and must NOT follow the override.
    assert not results["pnr._REPO_ROOT"].startswith(ov), (
        f"pnr._REPO_ROOT wrongly moved under the override: {results['pnr._REPO_ROOT']}"
    )

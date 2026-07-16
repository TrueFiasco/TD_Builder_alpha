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

B1 (config runtime equality) — ``config/__init__.py`` delegates its release root to
``paths.REPO_ROOT`` (hygiene bundle H1). Proven in a child that inserts ONLY
``MCP/server_core`` — config's own self-bootstrap must supply ``paths`` (the A1 property,
for free) — under both default and TD_BUILDER_ROOT-override conditions.

B2 (drift guard, source-level) — ``mcp_server.py`` is too heavy to import here (ChromaDB,
KB loads), so its delegation to ``paths`` is pinned over ``ast.parse`` of the committed
source: no local TD_BUILDER_ROOT env read, roots imported from ``paths``, no re-derivation,
and the sanctioned physical-walk depth constants match the real tree layout.

All tests are KB-free (no operators.json load) — no ``requires_kb`` marker.
"""
import ast
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


# ---------------------------------------------------------------------------
# B1 — config/__init__.py delegates its root to paths.REPO_ROOT (H1)
# ---------------------------------------------------------------------------
_B1_CHILD = r'''
import json
import sys
from pathlib import Path

repo_root, server_core = sys.argv[1], sys.argv[2]

# Isolation proof (A1 property): the repo root must NOT be reachable before
# config's own self-bootstrap runs -- only server_core goes on the path.
assert repo_root not in sys.path, "repo root leaked onto sys.path -- isolation broken"
try:
    import paths  # noqa: F401
    raise SystemExit("FAIL: `paths` importable before config's self-bootstrap")
except ModuleNotFoundError:
    pass

sys.path.insert(0, server_core)
import config          # self-bootstraps the repo root, then imports paths
import paths           # resolvable now ONLY because config inserted the root

print(json.dumps({
    "config_root": str(config._ROOT),
    "paths_root": str(paths.REPO_ROOT),
    "vector_db": str(config.SearchConfig.VECTOR_DB_PATH),
}))
'''


def _run_b1_child(tmp_path, env):
    env.pop("PYTHONPATH", None)
    # Knobs that would legitimately relocate SearchConfig paths away from the
    # root under test must not leak in from the developer environment.
    env.pop("UNIFIED_VECTORDB_PATH", None)
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _B1_CHILD, str(_REPO_ROOT),
         str(_REPO_ROOT / "MCP" / "server_core")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(tmp_path), env=env, timeout=120,
    )
    assert proc.returncode == 0, (
        f"child crashed (rc={proc.returncode})\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_config_root_agrees_with_paths_default(tmp_path):
    env = dict(os.environ)
    env.pop("TD_BUILDER_ROOT", None)
    results = _run_b1_child(tmp_path, env)
    assert results["config_root"] == results["paths_root"] == str(_REPO_ROOT), results


def test_config_root_agrees_with_paths_under_override(tmp_path):
    override = tmp_path / "relocated_root"
    override.mkdir()
    env = dict(os.environ)
    env["TD_BUILDER_ROOT"] = str(override)
    results = _run_b1_child(tmp_path, env)
    assert results["config_root"] == results["paths_root"] == str(override), results
    # KB-relative config resolution must relocate with the root.
    assert results["vector_db"].startswith(str(override)), results


# ---------------------------------------------------------------------------
# B2 — mcp_server.py delegation pinned at source level (heavy import avoided)
# ---------------------------------------------------------------------------
_MCP_SERVER_FILE = _REPO_ROOT / "MCP" / "server_core" / "mcp_server.py"
_CONFIG_INIT_FILE = _REPO_ROOT / "MCP" / "server_core" / "config" / "__init__.py"

# The one sanctioned physical walk per file (chicken-and-egg sys.path bootstrap);
# every other root must come from `paths`.
_SANCTIONED_PARENTS_ASSIGNS = {"_REPO_PHYS"}


def _env_reads(tree: ast.AST, var: str) -> list:
    """AST nodes that READ os.environ[var] / os.environ.get(var, ...) / os.getenv(var, ...).

    Comments are invisible to ast.parse, so documentation mentions of `var` stay legal.
    """
    def is_env_attr(node, attrs):
        return (isinstance(node, ast.Attribute) and node.attr in attrs
                and isinstance(node.value, ast.Name) and node.value.id == "os")

    def first_arg_is(call, value):
        return (call.args and isinstance(call.args[0], ast.Constant)
                and call.args[0].value == value)

    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and is_env_attr(node.value, {"environ"}):
            if isinstance(node.slice, ast.Constant) and node.slice.value == var:
                hits.append(node)
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "get" and is_env_attr(f.value, {"environ"}):
                if first_arg_is(node, var):
                    hits.append(node)
            elif is_env_attr(f, {"getenv"}):
                if first_arg_is(node, var):
                    hits.append(node)
    return hits


def _assigns(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            yield node, names


def test_runtime_resolvers_read_override_only_via_paths():
    """The TD_BUILDER_ROOT knob is read in exactly one place: paths.py."""
    for src_file in (_MCP_SERVER_FILE, _CONFIG_INIT_FILE):
        tree = ast.parse(src_file.read_text(encoding="utf-8"))
        hits = _env_reads(tree, "TD_BUILDER_ROOT")
        assert not hits, (
            f"{src_file.name} reads TD_BUILDER_ROOT locally (lines "
            f"{[n.lineno for n in hits]}) -- the knob is owned by paths.py; "
            f"import REPO_ROOT/KB_ROOT from `paths` instead (hygiene bundle H1)"
        )


def test_mcp_server_roots_come_from_paths():
    tree = ast.parse(_MCP_SERVER_FILE.read_text(encoding="utf-8"))

    # 1. Some `from paths import ...` binds both roots (the lazy resolve_td_tool
    #    import elsewhere is fine -- we require at least one with these aliases).
    bound = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "paths":
            for a in node.names:
                bound[a.asname or a.name] = a.name
    assert bound.get("_RELEASE_ROOT") == "REPO_ROOT", f"paths imports found: {bound}"
    assert bound.get("_KB_ROOT") == "KB_ROOT", f"paths imports found: {bound}"

    # 2. Neither root is re-derived by assignment anywhere in the file.
    for node, names in _assigns(tree):
        clashes = {"_RELEASE_ROOT", "_KB_ROOT"} & set(names)
        assert not clashes, (
            f"mcp_server.py:{node.lineno} re-assigns {clashes} -- roots must come "
            f"from `paths` only"
        )

    # 3. Any parents[N]-walk ASSIGNMENT is one of the sanctioned physical
    #    sys.path bootstraps. (Deliberately Assign-target-scoped: bare-Expr
    #    parents[] uses, e.g. sys.path.insert(..., parents[1]), are sys.path
    #    plumbing, not root derivation.)
    for node, names in _assigns(tree):
        uses_parents = any(
            isinstance(sub, ast.Attribute) and sub.attr == "parents"
            for sub in ast.walk(node.value if isinstance(node, ast.Assign) else (node.value or node))
        )
        if uses_parents:
            assert names and set(names) <= _SANCTIONED_PARENTS_ASSIGNS, (
                f"mcp_server.py:{node.lineno} derives a root via parents[] into "
                f"{names} -- only {_SANCTIONED_PARENTS_ASSIGNS} (physical sys.path "
                f"bootstrap) may do that; semantic roots come from `paths`"
            )


def test_physical_walk_depths_match_tree_layout():
    """The sanctioned physical walks' depth constants stay true to the layout:
    a file move surfaces here as a red test, not as a ModuleNotFoundError in
    some later direct-run context."""
    assert _MCP_SERVER_FILE.resolve().parents[2] == _REPO_ROOT
    assert _CONFIG_INIT_FILE.resolve().parents[3] == _REPO_ROOT


# --- has-teeth self-tests for the matcher ----------------------------------

def test_env_read_matcher_has_teeth():
    src = (
        "import os\n"
        "A = os.environ['TD_BUILDER_ROOT']\n"
        "B = os.environ.get('TD_BUILDER_ROOT')\n"
        "C = os.getenv('TD_BUILDER_ROOT', 'x')\n"
    )
    assert len(_env_reads(ast.parse(src), "TD_BUILDER_ROOT")) == 3


def test_env_read_matcher_ignores_comments_and_other_vars():
    src = (
        "import os\n"
        "# honors the TD_BUILDER_ROOT relocation knob (via paths.REPO_ROOT)\n"
        "D = os.getenv('UNIFIED_VECTORDB_PATH')\n"
    )
    assert _env_reads(ast.parse(src), "TD_BUILDER_ROOT") == []

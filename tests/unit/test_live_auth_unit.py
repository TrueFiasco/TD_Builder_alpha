"""Offline unit tests for the live-server security hardening.

No TouchDesigner required. Covers the pure/isolatable pieces:
  - utils/auth.py: token_matches (constant-time, fail-closed) + token_from_request
  - api_service.exec_python_script: AST rewrite runs the script EXACTLY once
    (the old re-eval() double-executed a side-effectful last line)
  - td_live_client._resolve_token: never raises; returns None on any file error
  - the OpenAPI schema file loads with stdlib json (no PyYAML dependency)

The TD-side modules import `td`/`tdu`; we inject MagicMock stubs so they load
without TouchDesigner. Modules are loaded by file path under private names so we
don't collide with the installed `mcp` SDK.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULES = REPO / "MCP" / "td-webserver" / "modules"
LIVE_CLIENT = REPO / "MCP" / "live_client"
SCHEMA = MODULES / "td_server" / "openapi_server" / "openapi" / "openapi.yaml"


def _load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# auth.py is stdlib-only → load it directly by file path.
auth = _load_by_path("td_auth_under_test", MODULES / "utils" / "auth.py")


@pytest.fixture(scope="module")
def api_service_mod():
    """Import api_service.py offline with td/tdu stubbed."""
    if str(MODULES) not in sys.path:
        sys.path.append(str(MODULES))  # append: keep the real `mcp` SDK winning
    sys.modules.setdefault("td", mock.MagicMock(name="td"))
    sys.modules.setdefault("tdu", mock.MagicMock(name="tdu"))
    return _load_by_path(
        "td_api_service_under_test", MODULES / "mcp" / "services" / "api_service.py"
    )


# --------------------------------------------------------------------------
# auth.token_matches — constant-time, fail-closed
# --------------------------------------------------------------------------

def _set_expected(monkeypatch, value):
    """Force get_expected_token() to a known value without touching $HOME."""
    monkeypatch.setattr(auth, "_resolved", True, raising=False)
    monkeypatch.setattr(auth, "_cached_token", value, raising=False)


def test_token_matches_correct(monkeypatch):
    _set_expected(monkeypatch, "s3cr3t-token")
    assert auth.token_matches("s3cr3t-token") is True


def test_token_matches_wrong(monkeypatch):
    _set_expected(monkeypatch, "s3cr3t-token")
    assert auth.token_matches("s3cr3t-tokeX") is False
    assert auth.token_matches("s3cr3t") is False


def test_token_matches_missing_provided(monkeypatch):
    _set_expected(monkeypatch, "s3cr3t-token")
    assert auth.token_matches(None) is False
    assert auth.token_matches("") is False


def test_token_matches_expected_none_fails_closed(monkeypatch):
    # Token subsystem failed to initialize → deny everything.
    _set_expected(monkeypatch, None)
    assert auth.token_matches("anything") is False
    assert auth.token_matches(None) is False


# --------------------------------------------------------------------------
# auth.token_from_request — Authorization: Bearer extraction
# --------------------------------------------------------------------------

@pytest.mark.parametrize("request_dict,expected", [
    ({"Authorization": "Bearer abc123"}, "abc123"),
    ({"authorization": "bearer abc123"}, "abc123"),          # case-insensitive
    ({"Authorization": "  Bearer   abc123  "}, "abc123"),    # whitespace
    ({"headers": {"Authorization": "Bearer nested"}}, "nested"),
    ({"Authorization": "rawtoken"}, "rawtoken"),             # tolerate no scheme
    ({"method": "GET", "uri": "/api/nodes"}, None),          # no auth header
    ({}, None),
    ("not-a-dict", None),
])
def test_token_from_request(request_dict, expected):
    assert auth.token_from_request(request_dict) == expected


# --------------------------------------------------------------------------
# exec_python_script — runs the script EXACTLY once (no double side effect)
# --------------------------------------------------------------------------

@pytest.fixture
def recorder():
    """A module the exec'd script can import + call; counts invocations."""
    rec = types.ModuleType("_exec_recorder")
    state = {"n": 0}

    def hit():
        state["n"] += 1
        return state["n"]

    rec.hit = hit
    rec.state = state
    sys.modules["_exec_recorder"] = rec
    yield rec
    sys.modules.pop("_exec_recorder", None)


def test_exec_last_expr_runs_once(api_service_mod, recorder):
    svc = api_service_mod.TouchDesignerApiService()
    # Last line is a side-effectful bare expression — must run exactly once.
    res = svc.exec_python_script("import _exec_recorder\n_exec_recorder.hit()")
    assert res["success"] is True
    assert recorder.state["n"] == 1, "side-effectful last line executed more than once"
    assert res["data"]["result"] == 1


def test_exec_explicit_result_respected(api_service_mod, recorder):
    svc = api_service_mod.TouchDesignerApiService()
    # Explicit `result` set; trailing bare expr still runs once but must not
    # overwrite the explicit result.
    res = svc.exec_python_script(
        "import _exec_recorder\nresult = 42\n_exec_recorder.hit()"
    )
    assert res["success"] is True
    assert recorder.state["n"] == 1
    assert res["data"]["result"] == 42


def test_exec_single_expression_returns_value(api_service_mod):
    svc = api_service_mod.TouchDesignerApiService()
    res = svc.exec_python_script("1 + 1")
    assert res["success"] is True
    assert res["data"]["result"] == 2


def test_exec_syntax_error_wrapped(api_service_mod):
    svc = api_service_mod.TouchDesignerApiService()
    with pytest.raises(Exception) as ei:
        svc.exec_python_script("def (:")
    assert "Script execution failed" in str(ei.value)


def test_script_assigns_result_detection(api_service_mod):
    svc_cls = api_service_mod.TouchDesignerApiService
    assert svc_cls._script_assigns_result(ast.parse("result = 1"))
    assert svc_cls._script_assigns_result(ast.parse("a, result = 1, 2"))
    assert svc_cls._script_assigns_result(ast.parse("result += 1"))
    assert svc_cls._script_assigns_result(ast.parse("result: int = 1"))
    assert not svc_cls._script_assigns_result(ast.parse("x = 1\nop('a')"))
    assert not svc_cls._script_assigns_result(ast.parse("d['result'] = 1"))


# --------------------------------------------------------------------------
# session restore-point: dialog-proof BY CONSTRUCTION (a pure filesystem copy,
# NEVER project.save()) — see api_service._ensure_session_restore_point.
# Offline these prove "project.save is never called + the copy is performed
# correctly + a copy failure is swallowed and made observable". They CANNOT
# prove dialog-freeness or non-rebind against a MagicMock td — that is GATE-B
# (live HITL against the main-tree install).
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def restore_dir(tmp_path, monkeypatch):
    """Redirect restore-point writes into tmp for EVERY test in this module (never the
    real ~/.td_builder) and reset the shared module-scoped `td` mock's project path to a
    non-existent location. autouse because the exec_* tests also fire the restore point
    (exec_python_script → _ensure_session_restore_point) and the module-scoped `td` mock
    leaks td.project.folder/name across tests — without this, running a saved-project test
    before an exec test (any reordering / node-id selection) would copy into the real
    ~/.td_builder. Tests that need the dir take it by name; others still get isolated."""
    d = tmp_path / "restore_points"
    monkeypatch.setenv("TD_RESTORE_DIR", str(d))
    td = sys.modules.get("td")
    if td is not None:
        td.project.folder = str(tmp_path)
        td.project.name = "_no_such_project_.toe"  # absent → restore point skips by default
    return d


def _saved_project(td, tmp_path, name, content=b"toe-bytes"):
    """Put a real on-disk .toe for `name` and point td.project at it; returns src."""
    f = tmp_path / name
    f.write_bytes(content)
    td.project.folder = str(tmp_path)
    td.project.name = name
    td.project.save.reset_mock()
    return str(f)


def test_restore_point_saved_copies_silently(api_service_mod, tmp_path, restore_dir):
    """Saved project → the last-saved .toe is COPIED to the restore dir; project.save
    is NEVER called (no dialog/increment/rebind reachable)."""
    td = sys.modules["td"]
    src = _saved_project(td, tmp_path, "saved.toe", b"hello-toe")
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()
    td.project.save.assert_not_called()
    dst = svc._restore_point_path(src)
    assert os.path.exists(dst), "restore copy was not created"
    assert Path(dst).read_bytes() == b"hello-toe", "restore copy content mismatch"
    assert svc._restore_point_status.startswith("ok:")


def test_restore_point_untitled_skips(api_service_mod, tmp_path, restore_dir):
    """Genuinely never-saved (no file on disk) → skip: no copy, no save, no raise."""
    td = sys.modules["td"]
    td.project.folder = str(tmp_path)
    td.project.name = "never_saved.toe"  # does NOT exist on disk
    td.project.save.reset_mock()
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()  # must not raise
    td.project.save.assert_not_called()
    assert not list(restore_dir.glob("*.toe")), "no restore file for a never-saved project"
    assert svc._restore_point_status.startswith("skipped:")


def test_restore_point_untitled_NAME_but_saved_copies(api_service_mod, tmp_path, restore_dir):
    """OWNER CAVEAT: the skip keys on FILE EXISTENCE, not the name. A SAVED project
    merely named untitled.toe / NewProject.1.toe exists on disk → it COPIES."""
    td = sys.modules["td"]
    for name in ("untitled.toe", "NewProject.1.toe"):
        src = _saved_project(td, tmp_path, name)
        svc = api_service_mod.TouchDesignerApiService()
        svc._ensure_session_restore_point()
        td.project.save.assert_not_called()
        assert os.path.exists(svc._restore_point_path(src)), f"{name} should copy, not skip"
        assert svc._restore_point_status.startswith("ok:")


def test_restore_point_increment_target_exists_no_save(api_service_mod, tmp_path, restore_dir):
    """THE BUG CASE: base .toe AND a pre-existing <name>.2.toe both on disk. The old
    no-arg save incremented into .2.toe → overwrite modal → hang. Now project.save is
    called ZERO times (increment path unreachable), the copy goes to the restore dir,
    and .2.toe is left untouched."""
    td = sys.modules["td"]
    src = _saved_project(td, tmp_path, "proj.toe", b"base")
    collide = tmp_path / "proj.2.toe"
    collide.write_bytes(b"pre-existing-increment")
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()
    td.project.save.assert_not_called()  # the increment/dialog path is never taken
    assert os.path.exists(svc._restore_point_path(src))
    assert collide.read_bytes() == b"pre-existing-increment", ".2.toe must be untouched"
    assert svc._restore_point_status.startswith("ok:")


def test_restore_point_copy_failure_is_swallowed_and_observable(
    api_service_mod, tmp_path, restore_dir, monkeypatch
):
    """A copy failure (e.g. a deny-read lock) must NOT raise and must NOT block the
    mutation — it is swallowed, recorded as 'unavailable', and surfaced via status."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "saved.toe")

    def boom(*a, **k):
        raise PermissionError("locked")

    monkeypatch.setattr(api_service_mod.shutil, "copyfile", boom)
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()  # must not raise
    td.project.save.assert_not_called()
    assert svc._restore_point_status.startswith("unavailable:")


def test_restore_point_only_once(api_service_mod, tmp_path, restore_dir, monkeypatch):
    """The flag makes it a no-op after the first call: the snapshot primitive runs at
    most once per instance."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "saved.toe")
    spy = mock.Mock()
    monkeypatch.setattr(api_service_mod.TouchDesignerApiService, "_snapshot_toe", spy)
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()
    svc._ensure_session_restore_point()
    assert spy.call_count == 1


def test_restore_point_only_once_even_after_failure(api_service_mod, tmp_path, restore_dir, monkeypatch):
    """Flag-first guarantee: _session_saved is set BEFORE the copy, so a FAILED first
    snapshot must NOT retry-storm — the primitive is attempted at most once per instance
    even when it raises (guards against moving the flag-set below the try)."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "saved.toe")
    spy = mock.Mock(side_effect=PermissionError("locked"))
    monkeypatch.setattr(api_service_mod.TouchDesignerApiService, "_snapshot_toe", spy)
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()  # first: raises internally → swallowed
    svc._ensure_session_restore_point()  # second: flag already set → no retry
    assert spy.call_count == 1
    assert svc._restore_point_status.startswith("unavailable:")


def test_restore_point_path_disambiguates_same_basename(api_service_mod, tmp_path, restore_dir):
    """Two projects sharing a basename in different folders get DISTINCT restore files
    in the flat dir (abs-path hash), so they never clobber each other."""
    rp = api_service_mod.TouchDesignerApiService._restore_point_path
    a = rp(str(tmp_path / "projA" / "scene.toe"))
    b = rp(str(tmp_path / "projB" / "scene.toe"))
    assert a != b, "same-basename projects must not collide"
    assert os.path.basename(a).startswith("scene.") and a.endswith(".toe")


def test_restore_point_never_calls_project_save(api_service_mod, tmp_path, restore_dir):
    """Core invariant across states: project.save() is NEVER called."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "s.toe")  # saved
    api_service_mod.TouchDesignerApiService()._ensure_session_restore_point()
    td.project.save.assert_not_called()
    td.project.name = "missing.toe"        # untitled (folder still points at tmp_path)
    td.project.save.reset_mock()
    api_service_mod.TouchDesignerApiService()._ensure_session_restore_point()
    td.project.save.assert_not_called()


# --------------------------------------------------------------------------
# client _resolve_token — never raises; None on any file error
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client_mod():
    if str(LIVE_CLIENT) not in sys.path:
        sys.path.insert(0, str(LIVE_CLIENT))
    return _load_by_path("td_live_client_under_test", LIVE_CLIENT / "td_live_client.py")


def test_resolve_token_env_wins(client_mod, monkeypatch):
    monkeypatch.setenv("TD_API_TOKEN", "env-token")
    assert client_mod._resolve_token() == "env-token"


def test_resolve_token_from_file(client_mod, monkeypatch, tmp_path):
    monkeypatch.delenv("TD_API_TOKEN", raising=False)
    f = tmp_path / "api_token"
    f.write_text("file-token\n", encoding="utf-8")
    monkeypatch.setenv("TD_API_TOKEN_FILE", str(f))
    assert client_mod._resolve_token() == "file-token"


def test_resolve_token_missing_file_returns_none(client_mod, monkeypatch, tmp_path):
    monkeypatch.delenv("TD_API_TOKEN", raising=False)
    monkeypatch.setenv("TD_API_TOKEN_FILE", str(tmp_path / "does_not_exist"))
    assert client_mod._resolve_token() is None


def test_resolve_token_unreadable_returns_none(client_mod, monkeypatch, tmp_path):
    # Point at a directory → read_text raises OSError → must be swallowed → None.
    monkeypatch.delenv("TD_API_TOKEN", raising=False)
    monkeypatch.setenv("TD_API_TOKEN_FILE", str(tmp_path))
    assert client_mod._resolve_token() is None


# --------------------------------------------------------------------------
# schema loads with stdlib json (no PyYAML)
# --------------------------------------------------------------------------

def test_schema_loads_as_json():
    with open(SCHEMA, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    assert isinstance(schema, dict)
    assert "paths" in schema and schema["paths"]


def test_bootstrap_setup_loads_schema_offline(monkeypatch):
    """The boot logic now lives in modules/bootstrap_mcp.py (thin-bootstrap
    restructure), so setup(modules_path) runs offline — no parent()/td. This is
    the stock-TD "schema loads without PyYAML" proof that was previously
    impossible to run offline."""
    bootstrap = _load_by_path("td_bootstrap_mcp_under_test", MODULES / "bootstrap_mcp.py")
    fake_mcp = types.ModuleType("mcp")
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    bootstrap.setup(str(MODULES))
    assert isinstance(fake_mcp.openapi_schema, dict)
    assert fake_mcp.openapi_schema.get("paths")
    assert fake_mcp.schema_load_error is None

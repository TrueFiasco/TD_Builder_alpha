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
# session restore-point: never pops a modal dialog (unsaved project → skip)
# --------------------------------------------------------------------------

def test_session_restore_point_skips_unsaved_project(api_service_mod, tmp_path):
    """Unsaved project (no .toe on disk) → skip project.save() so it can't open a
    modal Save-As dialog that blocks the WebServer thread."""
    td = sys.modules["td"]
    td.project.folder = str(tmp_path)
    td.project.name = "never_saved.toe"  # does NOT exist under tmp_path
    td.project.save.reset_mock()
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()
    td.project.save.assert_not_called()
    assert svc._session_saved is True  # still once-per-session


def test_session_restore_point_saves_existing_project(api_service_mod, tmp_path):
    """Project already on disk → project.save() is called exactly once."""
    td = sys.modules["td"]
    f = tmp_path / "saved.toe"
    f.write_text("x", encoding="utf-8")
    td.project.folder = str(tmp_path)
    td.project.name = "saved.toe"
    td.project.save.reset_mock()
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()
    td.project.save.assert_called_once()


def test_session_restore_point_only_once(api_service_mod, tmp_path):
    """The flag makes it a no-op after the first call, even if it saved."""
    td = sys.modules["td"]
    f = tmp_path / "saved.toe"
    f.write_text("x", encoding="utf-8")
    td.project.folder = str(tmp_path)
    td.project.name = "saved.toe"
    td.project.save.reset_mock()
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()
    svc._ensure_session_restore_point()
    td.project.save.assert_called_once()


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

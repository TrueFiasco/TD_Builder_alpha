"""Unit tests for W-A1 — folding warnings into the three error tools.

A broken GLSL op returns EMPTY errors() while the failure shows only in
warnings() + the Info DAT (live-proven 2026-07-13). So get_td_node_errors,
get_error_summary and get_cook_errors must surface warnings AND promote a GLSL
compile-failure warning to error severity, listed first. These stub-lane tests
drive the pure Python of api_service.get_node_errors and
error_monitor.get_{cook_errors,error_summary} directly.

The live-lane "break a shader, ask any-errors?" acceptance is post-deploy.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from unittest import mock

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODULES_DIR = os.path.join(_REPO_ROOT, "MCP", "td-webserver", "modules")
_API_SERVICE_PY = os.path.join(_MODULES_DIR, "mcp", "services", "api_service.py")
_ERROR_MONITOR_PY = os.path.join(_MODULES_DIR, "mcp", "services", "error_monitor.py")

COMPILE_WARNING = "The GLSL Shader has compile errors (Use Info DAT to see details)."


# ---------------------------------------------------------------------------
# api_service.get_node_errors
# ---------------------------------------------------------------------------

def _load_api_service():
    if str(_MODULES_DIR) not in sys.path:
        sys.path.append(str(_MODULES_DIR))
    sys.modules.setdefault("td", mock.MagicMock(name="td"))
    sys.modules.setdefault("tdu", mock.MagicMock(name="tdu"))
    spec = importlib.util.spec_from_file_location(
        "td_webserver_api_service_warnings_undertest", _API_SERVICE_PY
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Node:
    valid = True

    def __init__(self, path, optype, errors="", warnings=""):
        self.path = path
        self.name = path.rsplit("/", 1)[-1]
        self.OPType = optype
        self._errors = errors
        self._warnings = warnings

    def errors(self, recurse=True):
        return self._errors

    def warnings(self, recurse=True):
        return self._warnings


@pytest.fixture(scope="module")
def api_mod():
    return _load_api_service()


@pytest.fixture(scope="module")
def service(api_mod):
    return api_mod.TouchDesignerApiService()


def test_glsl_compile_warning_promoted_to_error(api_mod, service, monkeypatch):
    node = _Node("/project1/glsl1", "glslTOP", errors="", warnings=COMPILE_WARNING)
    monkeypatch.setattr(api_mod.td, "op", lambda path: node)
    r = service.get_node_errors("/project1/glsl1")
    assert r["success"] is True, r.get("error")
    d = r["data"]
    assert d["hasErrors"] is True
    assert d["errorCount"] == 1
    assert d["glslCompileFailureCount"] == 1
    assert d["errors"][0]["isGlslCompileFailure"] is True
    assert d["errors"][0]["message"].startswith("GLSL COMPILE FAILURE:")
    # the promoted banner is NOT also left in the warnings list
    assert d["warningCount"] == 0


def test_plain_warning_surfaced_not_promoted(api_mod, service, monkeypatch):
    node = _Node("/project1/noise1", "noiseTOP", errors="", warnings="Resolution limit reached")
    monkeypatch.setattr(api_mod.td, "op", lambda path: node)
    d = service.get_node_errors("/project1/noise1")["data"]
    assert d["hasErrors"] is False
    assert d["errorCount"] == 0
    assert d["warningCount"] == 1
    assert d["warnings"][0]["severity"] == "warning"
    assert d["glslCompileFailureCount"] == 0


def test_compile_failure_listed_before_plain_errors(api_mod, service, monkeypatch):
    node = _Node(
        "/project1/glsl1", "glslTOP",
        errors="Something bad happened",
        warnings=COMPILE_WARNING,
    )
    monkeypatch.setattr(api_mod.td, "op", lambda path: node)
    d = service.get_node_errors("/project1/glsl1")["data"]
    assert d["errorCount"] == 2
    assert d["errors"][0]["isGlslCompileFailure"] is True     # promoted first
    assert d["errors"][1].get("isGlslCompileFailure") is not True


def test_no_warnings_keeps_clean_shape(api_mod, service, monkeypatch):
    node = _Node("/project1/x", "nullTOP", errors="", warnings="")
    monkeypatch.setattr(api_mod.td, "op", lambda path: node)
    d = service.get_node_errors("/project1/x")["data"]
    assert d["hasErrors"] is False and d["errorCount"] == 0
    assert d["warningCount"] == 0 and d["glslCompileFailureCount"] == 0


# ---------------------------------------------------------------------------
# error_monitor.get_error_summary / get_cook_errors
# ---------------------------------------------------------------------------


class _Root:
    path = "/"
    valid = True

    def __init__(self, errors="", warnings=""):
        self._errors = errors
        self._warnings = warnings

    def errors(self, recurse=True):
        return self._errors

    def warnings(self, recurse=True):
        return self._warnings

    def findChildren(self, **kw):
        return []


def _load_error_monitor(monkeypatch, root):
    if str(_MODULES_DIR) not in sys.path:
        sys.path.append(str(_MODULES_DIR))
    td_stub = types.ModuleType("td")
    td_stub.root = root
    td_stub.op = lambda path: root if path in ("/", None) else None
    # deliberately no td_stub.DAT -> _find_all_error_dats skips the DAT scan
    monkeypatch.setitem(sys.modules, "td", td_stub)
    spec = importlib.util.spec_from_file_location("td_error_monitor_undertest", _ERROR_MONITOR_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_error_summary_puts_glsl_failure_in_error_bucket(monkeypatch):
    root = _Root(errors="", warnings=COMPILE_WARNING)
    mod = _load_error_monitor(monkeypatch, root)
    r = mod.ErrorMonitorService().get_error_summary()
    assert r["success"] is True, r.get("error")
    summary = r["data"]["summary"]
    assert summary["error"]["count"] == 1
    assert summary["warning"]["count"] == 0
    assert r["data"]["total_count"] == 1


def test_cook_errors_lists_compile_failure_first(monkeypatch):
    root = _Root(errors="", warnings=f"harmless warning\n{COMPILE_WARNING}")
    mod = _load_error_monitor(monkeypatch, root)
    r = mod.ErrorMonitorService().get_cook_errors()
    assert r["success"] is True, r.get("error")
    errors = r["data"]["errors"]
    assert errors[0]["kind"] == "glsl_compile_failure"
    assert errors[0]["severity"] == "error"
    # the harmless one is still surfaced, as a warning
    assert any(e["severity"] == "warning" for e in errors)


def test_cook_errors_severity_filter_error_excludes_warnings(monkeypatch):
    root = _Root(errors="", warnings=f"harmless warning\n{COMPILE_WARNING}")
    mod = _load_error_monitor(monkeypatch, root)
    r = mod.ErrorMonitorService().get_cook_errors(severity_filter="error")
    errors = r["data"]["errors"]
    assert len(errors) == 1
    assert errors[0]["kind"] == "glsl_compile_failure"


def test_no_warnings_no_promotion(monkeypatch):
    root = _Root(errors="", warnings="")
    mod = _load_error_monitor(monkeypatch, root)
    r = mod.ErrorMonitorService().get_error_summary()
    assert r["data"]["total_count"] == 0

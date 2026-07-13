"""Unit tests for W-A3 — auto-flagging GLSL compile status on the update receipt.

update_node stamps a compact GLSL compile-status block onto its result whenever
the write could have affected a shader, so an agent that forgets to check errors
is still told the shader broke. Covered here:
  * api_service.update_node attaches result['glslStatus'] from the (monkeypatched)
    module-level _run_glsl_receipt hook, and omits it when the hook returns None.
  * td_live_client renders a LOUD note on compile_failed and a quiet OK note
    otherwise (_glsl_status_note).

The end-to-end "edit a shader par, receipt already carries the flag" loop is a
LIVE-LANE test (post-deploy).
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from unittest import mock

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODULES_DIR = os.path.join(_REPO_ROOT, "MCP", "td-webserver", "modules")
_API_SERVICE_PY = os.path.join(_MODULES_DIR, "mcp", "services", "api_service.py")
_LIVE_CLIENT_DIR = os.path.join(_REPO_ROOT, "MCP", "live_client")
_LIVE_CLIENT_PY = os.path.join(_LIVE_CLIENT_DIR, "td_live_client.py")


# ---------------------------------------------------------------------------
# api_service.update_node — receipt attaches glslStatus
# ---------------------------------------------------------------------------

def _load_api_service():
    if str(_MODULES_DIR) not in sys.path:
        sys.path.append(str(_MODULES_DIR))
    sys.modules.setdefault("td", mock.MagicMock(name="td"))
    sys.modules.setdefault("tdu", mock.MagicMock(name="tdu"))
    spec = importlib.util.spec_from_file_location(
        "td_webserver_api_service_glsl_receipt_undertest", _API_SERVICE_PY
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakePar:
    def __init__(self):
        self.val = ""


class _FakeParNS:
    def __init__(self):
        self.pixeldat = _FakePar()


class _FakeGlslNode:
    valid = True
    path = "/project1/glsl1"
    name = "glsl1"
    OPType = "glslTOP"

    def __init__(self):
        self.par = _FakeParNS()


@pytest.fixture(scope="module")
def api_mod():
    return _load_api_service()


@pytest.fixture(scope="module")
def service(api_mod):
    return api_mod.TouchDesignerApiService()


def test_update_receipt_carries_glsl_status(api_mod, service, monkeypatch):
    node = _FakeGlslNode()
    monkeypatch.setattr(api_mod.td, "op", lambda path: node)
    fake_receipt = {
        "checked_node": "/project1/glsl1",
        "op_type": "glslTOP",
        "ok": False,
        "compile_failed": True,
        "compiler_errors": ["ERROR: 0:3: syntax error"],
        "warnings": ["The GLSL Shader has compile errors (...)"],
    }
    seen = {}

    def _fake_receipt_hook(n, props):
        seen["node"] = n
        seen["props"] = props
        return fake_receipt

    monkeypatch.setattr(api_mod, "_run_glsl_receipt", _fake_receipt_hook)

    r = service.update_node("/project1/glsl1", {"pixeldat": "shader1"})
    assert r["success"] is True, r.get("error")
    assert r["data"]["glslStatus"] == fake_receipt
    # the hook received the real node + the exact properties dict
    assert seen["node"] is node
    assert seen["props"] == {"pixeldat": "shader1"}


def test_update_receipt_omits_glsl_status_when_hook_returns_none(api_mod, service, monkeypatch):
    node = _FakeGlslNode()
    monkeypatch.setattr(api_mod.td, "op", lambda path: node)
    monkeypatch.setattr(api_mod, "_run_glsl_receipt", lambda n, p: None)

    r = service.update_node("/project1/glsl1", {"pixeldat": "shader1"})
    assert r["success"] is True, r.get("error")
    assert "glslStatus" not in r["data"]


def test_run_glsl_receipt_never_raises_without_service(api_mod):
    # The real module-level hook must swallow the ImportError of mcp.services.glsl_status
    # under the test harness (MCP SDK owns `mcp`) and return None, not raise.
    assert api_mod._run_glsl_receipt(_FakeGlslNode(), {"pixeldat": "x"}) is None


# ---------------------------------------------------------------------------
# td_live_client — _glsl_status_note render + update wiring
# ---------------------------------------------------------------------------

def _load_live_client():
    if str(_LIVE_CLIENT_DIR) not in sys.path:
        sys.path.insert(0, str(_LIVE_CLIENT_DIR))
    spec = importlib.util.spec_from_file_location("td_live_client_glsl_receipt_undertest", _LIVE_CLIENT_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["td_live_client_glsl_receipt_undertest"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def client_mod():
    return _load_live_client()


def test_glsl_status_note_loud_on_failure(client_mod):
    note = client_mod._glsl_status_note({
        "checked_node": "/project1/glsl1",
        "compile_failed": True,
        "is_glsl": True,
        "compiler_errors": ["ERROR: 0:3: syntax error"],
        "warnings": [],
    })
    assert "GLSL COMPILE FAILED" in note
    assert "/project1/glsl1" in note
    assert "ERROR: 0:3: syntax error" in note


def test_glsl_status_note_ok_is_quiet(client_mod):
    note = client_mod._glsl_status_note({
        "checked_node": "/project1/glsl1", "compile_failed": False, "is_glsl": True,
    })
    assert "✅" in note and "OK" in note
    assert "FAILED" not in note


def test_glsl_status_note_absent_when_not_glsl(client_mod):
    assert client_mod._glsl_status_note(None) == ""
    assert client_mod._glsl_status_note({"is_glsl": False, "compile_failed": False}) == ""


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def patch(self, endpoint, json=None):
        return _Resp(self._payload)


def test_update_client_renders_compile_failure(client_mod, monkeypatch):
    payload = {
        "success": True,
        "data": {
            "updated": ["pixeldat"],
            "failed": [],
            "glslStatus": {
                "checked_node": "/project1/glsl1",
                "compile_failed": True,
                "is_glsl": True,
                "compiler_errors": ["ERROR: 0:3: syntax error"],
                "warnings": [],
            },
        },
    }
    monkeypatch.setattr(client_mod, "TDClient", lambda *a, **k: _Client(payload))
    out = asyncio.run(client_mod.update_td_node_parameters(
        {"node_path": "/project1/glsl1", "properties": {"pixeldat": "shader1"}}
    ))
    text = out[0].text
    assert "Updated 1 parameters" in text
    assert "GLSL COMPILE FAILED" in text
    assert "ERROR: 0:3: syntax error" in text

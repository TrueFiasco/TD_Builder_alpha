"""Unit tests for get_nodes limit/truncation (F3) — server slice+flags and the
td_live_client TRUNCATED-banner render.

The MCP/td-webserver tree hard-imports the TD-only ``td``/``tdu`` modules at module
scope and has no live test coverage; we install minimal stubs into ``sys.modules``
and load the modules by file path under private names (so we never import the
td-webserver ``mcp`` package, which would shadow the real MCP SDK), then drive the
pure Python directly — bypassing the HTTP layer.

Guards the F3 contract: counts (totalCount/returnedCount/truncated) are ALWAYS
present, the server defaults the cap to 200 when the caller passes no limit, and
the client renders a loud banner only when the response is actually truncated.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from unittest import mock

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODULES_DIR = os.path.join(_REPO_ROOT, "MCP", "td-webserver", "modules")
_API_SERVICE_PY = os.path.join(_MODULES_DIR, "mcp", "services", "api_service.py")
_LIVE_CLIENT_DIR = os.path.join(_REPO_ROOT, "MCP", "live_client")
_LIVE_CLIENT_PY = os.path.join(_LIVE_CLIENT_DIR, "td_live_client.py")


# --------------------------------------------------------------------------
# api_service.get_nodes — slicing + always-present counts
# --------------------------------------------------------------------------

def _load_api_service_module():
    # Mirror test_exec_python_script_scope.py's stub strategy: APPEND the modules dir
    # (so the real MCP SDK's `mcp` package keeps winning over td-webserver's `mcp`),
    # install td/tdu via setdefault, and load api_service by file path under a private
    # name so it can coexist with the other td-webserver test modules in one session.
    if str(_MODULES_DIR) not in sys.path:
        sys.path.append(str(_MODULES_DIR))
    sys.modules.setdefault("td", mock.MagicMock(name="td"))
    sys.modules.setdefault("tdu", mock.MagicMock(name="tdu"))
    spec = importlib.util.spec_from_file_location(
        "td_webserver_api_service_get_nodes_undertest", _API_SERVICE_PY
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeNode:
    def __init__(self, i: int):
        self.id = i
        self.name = f"node{i}"
        self.path = f"/project1/node{i}"
        self.OPType = "nullTOP"


class _FakeParent:
    valid = True

    def __init__(self, count: int):
        self._children = [_FakeNode(i) for i in range(count)]

    def findChildren(self, depth=None, name=None):
        return list(self._children)


@pytest.fixture(scope="module")
def api_mod():
    return _load_api_service_module()


@pytest.fixture(scope="module")
def service(api_mod):
    return api_mod.TouchDesignerApiService()


def _patch_parent(api_mod, monkeypatch, count):
    monkeypatch.setattr(api_mod.td, "op", lambda path: _FakeParent(count))


def test_explicit_limit_slices_and_flags_truncated(api_mod, service, monkeypatch):
    _patch_parent(api_mod, monkeypatch, count=10)
    r = service.get_nodes("/project1", limit=3)
    assert r["success"] is True, r.get("error")
    data = r["data"]
    assert data["totalCount"] == 10
    assert data["returnedCount"] == 3
    assert data["truncated"] is True
    assert len(data["nodes"]) == 3


def test_no_limit_under_default_cap_not_truncated(api_mod, service, monkeypatch):
    _patch_parent(api_mod, monkeypatch, count=5)
    r = service.get_nodes("/project1")  # limit=None -> server default 200
    assert r["success"] is True, r.get("error")
    data = r["data"]
    assert data["totalCount"] == 5
    assert data["returnedCount"] == 5
    assert data["truncated"] is False
    assert len(data["nodes"]) == 5


def test_no_limit_over_default_cap_truncates_at_200(api_mod, service, monkeypatch):
    _patch_parent(api_mod, monkeypatch, count=205)
    r = service.get_nodes("/project1")  # limit=None -> server default 200
    assert r["success"] is True, r.get("error")
    data = r["data"]
    assert data["totalCount"] == 205
    assert data["returnedCount"] == 200
    assert data["truncated"] is True
    assert len(data["nodes"]) == 200


def test_negative_limit_falls_back_to_default_not_negative_slice(api_mod, service, monkeypatch):
    # A negative limit must NOT become node_summaries[:-5] (which silently drops
    # children from the END); it is treated as absent -> server default 200.
    _patch_parent(api_mod, monkeypatch, count=10)
    r = service.get_nodes("/project1", limit=-5)
    assert r["success"] is True, r.get("error")
    data = r["data"]
    assert data["totalCount"] == 10
    assert data["returnedCount"] == 10
    assert data["truncated"] is False
    assert len(data["nodes"]) == 10


def test_zero_limit_falls_back_to_default(api_mod, service, monkeypatch):
    _patch_parent(api_mod, monkeypatch, count=3)
    r = service.get_nodes("/project1", limit=0)
    assert r["success"] is True, r.get("error")
    data = r["data"]
    assert data["returnedCount"] == 3
    assert data["truncated"] is False


def _load_generated_handlers_module():
    # generated_handlers.py does `from mcp.services.api_service import api_service`,
    # but the real MCP SDK owns the `mcp` package in this test session. Inject stub
    # submodule entries directly into sys.modules (the import system finds them there
    # without touching the SDK package), then load by file path under a private name.
    if str(_MODULES_DIR) not in sys.path:
        sys.path.append(str(_MODULES_DIR))
    sys.modules.setdefault("td", mock.MagicMock(name="td"))
    sys.modules.setdefault("tdu", mock.MagicMock(name="tdu"))
    if "mcp.services" not in sys.modules:
        sys.modules["mcp.services"] = types.ModuleType("mcp.services")
    if "mcp.services.api_service" not in sys.modules:
        stub = types.ModuleType("mcp.services.api_service")
        stub.api_service = mock.MagicMock(name="api_service")
        sys.modules["mcp.services.api_service"] = stub
    spec = importlib.util.spec_from_file_location(
        "td_webserver_generated_handlers_undertest",
        os.path.join(_MODULES_DIR, "mcp", "controllers", "generated_handlers.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_handler_coercion_rejects_negative_and_junk_limit():
    # generated_handlers.get_nodes must treat "-5"/-5/"0"/junk as absent (None) and
    # keep coercing positive numeric strings; a negative value forwarded through
    # would negative-slice in api_service.get_nodes and silently drop children.
    handlers = _load_generated_handlers_module()
    seen = {}

    def _capture(**kwargs):
        seen.update(kwargs)
        return {"success": True, "data": {}}

    with mock.patch.object(handlers, "api_service") as fake_service:
        fake_service.get_nodes.side_effect = _capture
        for raw, expected in [("-5", None), (-5, None), ("0", None), (0, None), ("abc", None), ("7", 7), (7, 7)]:
            seen.clear()
            handlers.get_nodes(parentPath="/project1", limit=raw)
            assert seen.get("limit") == expected, (
                f"limit={raw!r} coerced to {seen.get('limit')!r}, expected {expected!r}"
            )


def test_counts_present_even_when_empty(api_mod, service, monkeypatch):
    _patch_parent(api_mod, monkeypatch, count=0)
    r = service.get_nodes("/project1")
    assert r["success"] is True, r.get("error")
    data = r["data"]
    assert data == {
        "nodes": [],
        "totalCount": 0,
        "returnedCount": 0,
        "truncated": False,
    }


# --------------------------------------------------------------------------
# td_live_client.get_td_nodes — TRUNCATED banner / completeness footer render
# --------------------------------------------------------------------------

def _load_live_client_module():
    if str(_LIVE_CLIENT_DIR) not in sys.path:
        sys.path.insert(0, str(_LIVE_CLIENT_DIR))
    spec = importlib.util.spec_from_file_location(
        "td_live_client_get_nodes_undertest", _LIVE_CLIENT_PY
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["td_live_client_get_nodes_undertest"] = module
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, endpoint, params=None):
        return _FakeResponse(self._payload)


@pytest.fixture(scope="module")
def client_mod():
    return _load_live_client_module()


def _run_get_td_nodes(client_mod, monkeypatch, data_payload):
    payload = {"success": True, "data": data_payload}
    monkeypatch.setattr(client_mod, "TDClient", lambda *a, **k: _FakeClient(payload))
    result = asyncio.run(client_mod.get_td_nodes({"parent_path": "/project1"}))
    return result[0].text


def test_client_renders_truncated_banner(client_mod, monkeypatch):
    text = _run_get_td_nodes(
        client_mod,
        monkeypatch,
        {
            "nodes": [
                {"name": "a", "opType": "nullTOP", "path": "/project1/a"},
                {"name": "b", "opType": "nullTOP", "path": "/project1/b"},
                {"name": "c", "opType": "nullTOP", "path": "/project1/c"},
            ],
            "returnedCount": 3,
            "totalCount": 10,
            "truncated": True,
        },
    )
    assert text.startswith("**TRUNCATED")
    assert "SHOWING 3 OF 10 CHILDREN" in text
    assert "limit=10" in text
    assert "_3 of 10 node(s) shown._" in text


def test_client_renders_completeness_footer_when_not_truncated(client_mod, monkeypatch):
    text = _run_get_td_nodes(
        client_mod,
        monkeypatch,
        {
            "nodes": [{"name": "a", "opType": "nullTOP", "path": "/project1/a"}],
            "returnedCount": 1,
            "totalCount": 1,
            "truncated": False,
        },
    )
    assert "TRUNCATED" not in text
    assert "_1 of 1 node(s) shown._" in text

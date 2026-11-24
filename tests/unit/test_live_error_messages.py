"""Live tools must say WHY TouchDesigner did not answer (never an empty ``Error:``),
and ``capture_top_output`` must take a whole number like ``capture_op_viewer``.

Seams: the two helpers (``_exception_message`` / ``_status_message``), a real
handler driven with a faked HTTP client, and the tool schema.
"""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import os
import sys

import httpx
import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PY = os.path.join(_REPO_ROOT, "MCP", "live_client", "td_live_client.py")


def _load():
    spec = importlib.util.spec_from_file_location("td_live_client_errs", _PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


live = _load()


def _resp(status, text="", json_body=None):
    if json_body is not None:
        return httpx.Response(status, json=json_body)
    return httpx.Response(status, text=text)


# ---- exceptions ------------------------------------------------------------

def test_read_timeout_names_the_state_and_class_and_never_is_empty():
    msg = live._exception_message(httpx.ReadTimeout(""), read_timeout=20.0)
    assert "ReadTimeout" in msg
    assert "accepted the connection but did not answer in 20 s" in msg
    assert "dialog" in msg and "minimized" in msg and "cooking" in msg
    assert "Do not retry in a loop" in msg
    assert "get_mutation_status" not in msg


def test_script_timeout_points_at_get_mutation_status():
    msg = live._exception_message(httpx.ReadTimeout(""), read_timeout=60.0, script=True)
    assert "did not answer in 60 s" in msg
    assert "may still be running" in msg
    assert "get_mutation_status" in msg


def test_connect_error_keeps_the_not_running_text():
    msg = live._exception_message(httpx.ConnectError("refused"))
    assert msg == live._connection_error_message()


def test_unknown_exception_with_empty_message_still_has_class_name():
    msg = live._exception_message(RuntimeError(""))
    assert "RuntimeError" in msg
    assert msg.strip() != "Error:"


# ---- statuses --------------------------------------------------------------

def test_401_names_both_causes():
    msg = live._status_message(_resp(401))
    assert "401" in msg and "token" in msg.lower() and "cooking" in msg.lower()


def test_404_without_a_json_body_means_modules_not_found():
    msg = live._status_message(_resp(404))
    assert "404" in msg
    assert "modules" in msg and ".tox" in msg


def test_404_with_a_real_error_body_is_passed_through():
    msg = live._status_message(_resp(404, json_body={"success": False, "error": "Operator not found: /x"}))
    assert "404" in msg and "Operator not found: /x" in msg
    assert "modules" not in msg


def test_500_has_status_and_body():
    msg = live._status_message(_resp(500, text="boom"))
    assert "500" in msg and "boom" in msg


def test_non_200_with_empty_body_is_not_empty():
    msg = live._status_message(_resp(503))
    assert "503" in msg


# ---- through a real handler ------------------------------------------------

class _FakeClient:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def get(self, *a, **k):
        return self._go()

    post = patch = delete = get

    def _go(self):
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return self.behaviour


def _run(coro):
    return asyncio.run(coro)


def test_get_td_info_read_timeout_is_a_sentence(monkeypatch):
    monkeypatch.setattr(live, "TDClient", lambda **kw: _FakeClient(httpx.ReadTimeout("")))
    out = _run(live.get_td_info({}))[0].text
    assert "ReadTimeout" in out and "did not answer in 20 s" in out


def test_execute_python_script_timeout_mentions_mutation_status(monkeypatch):
    monkeypatch.setattr(live, "TDClient", lambda **kw: _FakeClient(httpx.ReadTimeout("")))
    out = _run(live.execute_python_script({"script": "pass"}))[0].text
    assert "get_mutation_status" in out


def test_handler_non_200_includes_status_code(monkeypatch):
    monkeypatch.setattr(live, "TDClient", lambda **kw: _FakeClient(_resp(401)))
    out = _run(live.get_td_info({}))[0].text
    assert "401" in out


def test_no_handler_formats_a_bare_str_of_the_exception():
    tree = ast.parse(open(_PY, encoding="utf-8").read())
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.name:
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == "str" and sub.args
                        and isinstance(sub.args[0], ast.Name) and sub.args[0].id == node.name):
                    offenders.append(sub.lineno)
    assert not offenders, f"bare str(exception) at lines {offenders}"


# ---- capture_top_output size ----------------------------------------------

def _tool(name):
    return next(t for t in live.TD_LIVE_TOOLS if t.name == name)


@pytest.mark.parametrize("value,sent", [
    (640, "640"), ("original", "original"), ("256", "256"), ("512", "512"), ("1024", "1024"),
    (1024, "1024"),
])
def test_capture_top_output_accepts_number_and_old_strings(monkeypatch, value, sent):
    captured = {}

    class C(_FakeClient):
        async def post(self, endpoint, json=None):
            captured.update(json)
            return _resp(200, json_body={"success": False, "error": "x"})

    monkeypatch.setattr(live, "TDClient", lambda **kw: C(None))
    _run(live.capture_top_output({"operator_path": "/a", "resolution": value}))
    assert captured["resolution"] == sent


def test_capture_top_output_rejects_nonsense_in_words(monkeypatch):
    monkeypatch.setattr(live, "TDClient", lambda **kw: _FakeClient(None))
    for bad in ("640x400", 0, -5, True, 2.5, "huge"):
        out = _run(live.capture_top_output({"operator_path": "/a", "resolution": bad}))[0].text
        assert "resolution" in out and "original" in out, bad


def test_capture_top_output_schema_admits_integer_and_original():
    schema = _tool("capture_top_output").inputSchema["properties"]["resolution"]
    kinds = {b.get("type") for b in schema["anyOf"]}
    assert "integer" in kinds
    assert any("original" in b.get("enum", []) for b in schema["anyOf"])

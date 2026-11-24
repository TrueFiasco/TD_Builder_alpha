"""Unit tests for exec_python_script scope / partial-stdout / time.sleep fixes (F2).

The MCP/td-webserver tree hard-imports the TD-only ``td``/``tdu`` modules at module
scope and has zero test coverage. Here we install minimal stubs into ``sys.modules``
and load ``api_service.py`` by file path (so we never import the td-webserver ``mcp``
package, which would shadow the real MCP SDK), then instantiate
``TouchDesignerApiService`` directly — bypassing the HTTP layer.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from unittest import mock

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODULES_DIR = os.path.join(_REPO_ROOT, "MCP", "td-webserver", "modules")
_API_SERVICE_PY = os.path.join(_MODULES_DIR, "mcp", "services", "api_service.py")


def _load_api_service_module():
    # Mirror tests/unit/test_live_auth_unit.py's stub strategy EXACTLY so the two files
    # can coexist in one pytest session sharing sys.modules["td"]: APPEND the modules dir
    # (so the real MCP SDK's `mcp` package keeps winning over td-webserver's `mcp`), and
    # install td/tdu as MagicMocks via setdefault (a richer stub than a bare namespace,
    # and the shape test_live_auth_unit expects — e.g. td.project.save is auto-created).
    if str(_MODULES_DIR) not in sys.path:
        sys.path.append(str(_MODULES_DIR))
    sys.modules.setdefault("td", mock.MagicMock(name="td"))
    sys.modules.setdefault("tdu", mock.MagicMock(name="tdu"))
    spec = importlib.util.spec_from_file_location(
        "td_webserver_api_service_undertest", _API_SERVICE_PY
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def service():
    module = _load_api_service_module()
    return module.TouchDesignerApiService()


def test_comprehension_over_imported_alias_succeeds(service):
    # Sub-fault (a): with the old two-dict exec, the comprehension's `np` resolved
    # via globals() and raised NameError. Single-namespace exec fixes it.
    script = (
        "import math as np\n"
        "vals = [np.sqrt(x) for x in [1, 4, 9]]\n"
        "result = vals\n"
    )
    r = service.exec_python_script(script)
    assert r["success"] is True, r.get("error")
    assert r["data"]["result"] == [1.0, 2.0, 3.0]


def test_nested_def_reads_toplevel_accumulator(service):
    # Sub-fault (a): a nested def referencing a top-level name.
    script = (
        "acc = [10, 20, 30]\n"
        "def total():\n"
        "    return sum(acc)\n"
        "result = total()\n"
    )
    r = service.exec_python_script(script)
    assert r["success"] is True, r.get("error")
    assert r["data"]["result"] == 60


def test_partial_stdout_folded_into_error_on_exception(service):
    # Sub-fault (b): output printed before the raise must survive in the error string.
    script = (
        "print('FIRST_LINE')\n"
        "print('SECOND_LINE')\n"
        "raise ValueError('boom')\n"
    )
    r = service.exec_python_script(script)
    assert r["success"] is False
    assert "FIRST_LINE" in r["error"]
    assert "SECOND_LINE" in r["error"]
    assert "boom" in r["error"]


def test_time_sleep_rejected_immediately(service):
    # Sub-fault (c): time.sleep must be rejected statically, before execution — so
    # the wall clock stays tiny even though the script asks to sleep 5 seconds.
    script = "import time\ntime.sleep(5)\n"
    start = time.perf_counter()
    r = service.exec_python_script(script)
    elapsed = time.perf_counter() - start
    assert r["success"] is False
    assert "time.sleep" in r["error"]
    assert elapsed < 1.0, f"guard did not short-circuit; took {elapsed:.2f}s"


def test_bare_sleep_from_import_rejected(service):
    # The guard also covers `from time import sleep; sleep(...)`.
    script = "from time import sleep\nsleep(3)\n"
    r = service.exec_python_script(script)
    assert r["success"] is False
    assert "time.sleep" in r["error"]


def test_syntax_error_returns_error_result_not_raise(service):
    # Sub-fault (b), consistency: SyntaxError now returns an error_result.
    r = service.exec_python_script("def broken(:\n    pass\n")
    assert r["success"] is False
    assert "Script execution failed" in r["error"]


# ---------------------------------------------------------------------------
# Tickets 01 + 02: nested results stay intact; script namespace = td's names.
# These tests swap a small fake ``td`` module into the loaded api_service module
# (the shared MagicMock cannot answer ``isinstance(x, td.OP)``).
# ---------------------------------------------------------------------------
import types


class _FakeOP:
    valid = True

    def __init__(self, path):
        self.path = path
        self.name = path.rsplit("/", 1)[-1]
        self.id = 1
        self.OPType = "fakeOP"


class _FakePar:
    def __init__(self, name, value):
        self.name = name
        self._value = value

    def eval(self):
        return self._value


class _FakeParMode:
    EXPRESSION = "EXPRESSION"


def _make_fake_td():
    fake = types.ModuleType("td")
    fake.OP = _FakeOP
    fake.Par = _FakePar
    fake.ParMode = _FakeParMode
    fake.TOP = type("TOP", (), {})
    fake.textDAT = type("textDAT", (), {})
    fake.run = lambda *a, **k: "ran"
    fake.mod = object()
    fake.absTime = object()
    for n in ("ops", "project", "root", "app", "ui", "iop", "ipar", "ext",
              "families", "monitors", "licenses", "sysinfo"):
        setattr(fake, n, object())
    # A real node resolves for paths only; anything else (a dict, list, tuple)
    # resolves to an unrelated operator -- the observed fault.
    stray = _FakeOP("/mcp_webserver_base/parameter1")
    fake.op = lambda x: stray
    # td.me / td.parent exist in real td and must not leak into scripts.
    fake.me = "LEAKED_ME"
    fake.parent = "LEAKED_PARENT"
    return fake


@pytest.fixture()
def fake_service(monkeypatch):
    module = _load_api_service_module()
    fake = _make_fake_td()
    monkeypatch.setattr(module, "td", fake)
    monkeypatch.setattr(module, "tdu", object())
    svc = module.TouchDesignerApiService()
    # The summary shape is incidental; keep it small and recognisable.
    svc._get_node_summary = lambda node: {"summary_of": node.path}
    return svc


def test_nested_dict_in_dict_intact(fake_service):
    r = fake_service._process_method_result({"a": {"b": 1.5, "c": "x"}})
    assert r == {"a": {"b": 1.5, "c": "x"}}


def test_list_of_tuples_intact(fake_service):
    r = fake_service._process_method_result([(1, 2), (3, 4)])
    assert r == [[1, 2], [3, 4]]


def test_tuple_in_dict_intact(fake_service):
    r = fake_service._process_method_result({"k": (1, "two", None)})
    assert r == {"k": [1, "two", None]}


def test_non_string_keys_become_strings(fake_service):
    r = fake_service._process_method_result({"outer": {1: "a", 2: "b"}})
    assert r == {"outer": {"1": "a", "2": "b"}}


def test_operator_inside_list_still_summarised(fake_service):
    r = fake_service._process_method_result([_FakeOP("/project1/geo1")])
    assert r == [{"summary_of": "/project1/geo1"}]


def test_parameter_inside_dict_still_evaluated(fake_service):
    r = fake_service._process_method_result({"p": _FakePar("tx", 0.25)})
    assert r == {"p": 0.25}


def test_numpy_scalar_and_array(fake_service):
    np = pytest.importorskip("numpy")
    r = fake_service._process_method_result(
        {"s": np.float32(0.5), "i": np.int64(3), "a": np.zeros((2, 3))}
    )
    assert r["s"] == 0.5 and type(r["s"]) is float
    assert r["i"] == 3 and type(r["i"]) is int
    assert "2" in str(r["a"]) and "3" in str(r["a"])
    assert len(str(r["a"])) < 80  # shape/type, not a full dump


def test_script_namespace_has_td_names_and_sentinels(fake_service):
    script = (
        "ok = [ParMode.EXPRESSION, run, textDAT, TOP, mod]\n"
        "try:\n"
        "    me.name\n"
        "except Exception as e:\n"
        "    me_msg = str(e)\n"
        "try:\n"
        "    parent()\n"
        "except Exception as e:\n"
        "    parent_msg = str(e)\n"
        "result = [me_msg, parent_msg]\n"
    )
    r = fake_service.exec_python_script(script)
    assert r["success"] is True, r.get("error")
    me_msg, parent_msg = r["data"]["result"]
    assert "LEAKED" not in me_msg + parent_msg
    assert "outside any node" in me_msg
    assert "mcp_webserver_base" in parent_msg

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

"""Unit tests for W-A GLSL compile-status flagging.

Covers:
  * utils.glsl pure helpers (family + compile-failure detection, mutation gate)
  * glsl_status.GlslStatusService.get_glsl_status (W-A2): Info DAT compiler-log
    read, op.warnings() fold-in, temp Info DAT create+destroy (leak-proof), and
    the receipt_for_mutation gate (W-A3 helper).

Same stub strategy as the other td-webserver unit tests: the tree hard-imports
``td`` at module scope and expects the ``utils`` package on sys.path, so we append
the modules dir, install a ``td`` stub, and load the modules under test by file
path (never importing the td-webserver ``mcp`` package, which would shadow the
real MCP SDK).

The end-to-end "break a live shader" loop is a LIVE-LANE test (needs TD running
with the post-deploy server); see tests/acceptance and the wave summary.
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
_GLSL_UTIL_PY = os.path.join(_MODULES_DIR, "utils", "glsl.py")
_GLSL_SERVICE_PY = os.path.join(_MODULES_DIR, "mcp", "services", "glsl_status.py")

COMPILE_WARNING = "The GLSL Shader has compile errors (Use Info DAT to see details)."
COMPILE_LOG = "ERROR: 0:12: 'vTexCoord' : undeclared identifier\nCompile Failed\n"


def _load_by_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# utils.glsl — pure helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def g():
    if str(_MODULES_DIR) not in sys.path:
        sys.path.append(str(_MODULES_DIR))
    return _load_by_path("td_utils_glsl_undertest", _GLSL_UTIL_PY)


class _Op:
    def __init__(self, optype):
        self.OPType = optype


def test_is_glsl_family_covers_all_four(g):
    for t in ("glslTOP", "glslmultiTOP", "glslPOP", "glslMAT"):
        assert g.is_glsl_family(_Op(t)) is True, t
    for t in ("noiseTOP", "textDAT", "geometryCOMP", ""):
        assert g.is_glsl_family(_Op(t)) is False, t


def test_compile_failure_message_matches_banner(g):
    assert g.is_compile_failure_message(COMPILE_WARNING) is True
    assert g.is_compile_failure_message("compile FAILED") is True
    assert g.is_compile_failure_message("uniform unassigned") is False
    assert g.is_compile_failure_message("") is False
    assert g.is_compile_failure_message(None) is False


def test_glsl_specific_compile_message_requires_both(g):
    assert g.is_glsl_specific_compile_message(COMPILE_WARNING) is True
    # compile-failure phrasing without a glsl/shader mention -> not self-identifying
    assert g.is_glsl_specific_compile_message("compile error in something") is False
    # glsl mention without a compile failure -> not a failure
    assert g.is_glsl_specific_compile_message("glsl warning: deprecated") is False


def test_scan_compiler_log_finds_error_lines(g):
    lines = g.scan_compiler_log(COMPILE_LOG)
    assert any("ERROR:" in ln for ln in lines)
    assert any("Compile Failed" in ln for ln in lines)
    assert g.scan_compiler_log("Compiled Successfully\n") == []
    assert g.scan_compiler_log("") == []


def test_mutation_touches_glsl_gate(g):
    glsl = _Op("glslTOP")
    dat = _Op("textDAT")
    assert g.mutation_touches_glsl(glsl, {"anything": 1}) is True     # glsl op: any write
    assert g.mutation_touches_glsl(dat, {"text": "..."}) is True      # DAT .text write
    assert g.mutation_touches_glsl(dat, {"pixeldat": "shader"}) is True
    assert g.mutation_touches_glsl(dat, {"length": 5}) is False       # unrelated DAT write
    assert g.mutation_touches_glsl(dat, None) is False


# ---------------------------------------------------------------------------
# glsl_status.GlslStatusService (W-A2 / W-A3)
# ---------------------------------------------------------------------------


class FakePar:
    def __init__(self, val=""):
        self.val = val


class FakeParNS:
    """Attribute bag for op.par; assigning op.par.x = v just records it."""


class FakeOp:
    def __init__(self, path, optype, text="", errors="", warnings="",
                 docked=None, parent=None):
        self.path = path
        self.OPType = optype
        self.name = path.rsplit("/", 1)[-1]
        self.valid = True
        self._text = text
        self._errors = errors
        self._warnings = warnings
        self.docked = docked or []
        self._parent = parent
        self.par = FakeParNS()
        self.nodeX = 0
        self.nodeY = 0
        self.cook_calls = 0
        self.destroyed = False
        self._op_refs = {}   # rel/val -> op (for .op() resolution)

    @property
    def text(self):
        return self._text

    def errors(self, recurse=False):
        return self._errors

    def warnings(self, recurse=False):
        return self._warnings

    def parent(self):
        return self._parent

    def cook(self, force=False):
        self.cook_calls += 1

    def destroy(self):
        self.destroyed = True

    def op(self, rel):
        return self._op_refs.get(rel)


class FakeParent(FakeOp):
    def __init__(self, path="/project1", info_text="", **kw):
        super().__init__(path, "containerCOMP", **kw)
        self._children = {}          # name -> op
        self._info_text = info_text  # text a freshly-created temp Info DAT reports
        self.created = []            # temp ops created
        self.create_calls = 0

    def op(self, rel):
        return self._children.get(rel) or self._op_refs.get(rel)

    def add(self, op_obj):
        self._children[op_obj.name] = op_obj
        op_obj._parent = self
        return op_obj

    def findChildren(self, depth=1):
        return list(self._children.values())

    def create(self, optype, name):
        self.create_calls += 1
        temp = FakeOp(f"{self.path}/{name}", "infoDAT" if optype == "infoDAT" else optype,
                      text=self._info_text, parent=self)
        self._children[name] = temp
        self.created.append(temp)
        return temp


def _load_service(monkeypatch, registry):
    """Load glsl_status.py by file path with a td stub whose op() reads `registry`.

    Uses monkeypatch.setitem so the plain-ModuleType td stub is auto-restored after
    the test and never leaks into the MagicMock-td tests sharing this session.
    """
    if str(_MODULES_DIR) not in sys.path:
        sys.path.append(str(_MODULES_DIR))
    td_stub = types.ModuleType("td")
    td_stub.op = lambda path: registry.get(path)
    monkeypatch.setitem(sys.modules, "td", td_stub)
    mod = _load_by_path("td_glsl_status_undertest", _GLSL_SERVICE_PY)
    return mod


def test_get_glsl_status_flags_compile_log_error(monkeypatch):
    parent = FakeParent(info_text=COMPILE_LOG)
    glsl = FakeOp("/project1/glsl1", "glslTOP", errors="", warnings="", parent=parent)
    parent.add(glsl)
    registry = {glsl.path: glsl}
    mod = _load_service(monkeypatch, registry)

    r = mod.GlslStatusService().get_glsl_status("/project1/glsl1")
    assert r["success"] is True, r.get("error")
    d = r["data"]
    assert d["is_glsl"] is True
    assert d["ok"] is False
    assert d["compile_failed"] is True
    assert any("ERROR:" in ln for ln in d["compiler_errors"])
    # temp Info DAT created AND destroyed (no leak)
    assert parent.create_calls == 1
    assert parent.created[0].destroyed is True


def test_get_glsl_status_flags_warning_banner_even_with_clean_log(monkeypatch):
    # Info DAT text does NOT carry an ERROR line, but op.warnings() shows the banner.
    parent = FakeParent(info_text="Compiled Successfully\n")
    glsl = FakeOp("/project1/glsl1", "glslTOP", warnings=COMPILE_WARNING, parent=parent)
    parent.add(glsl)
    mod = _load_service(monkeypatch, {glsl.path: glsl})

    d = mod.GlslStatusService().get_glsl_status("/project1/glsl1")["data"]
    assert d["compile_failed"] is True
    assert d["ok"] is False
    assert COMPILE_WARNING in d["warnings"]


def test_get_glsl_status_ok_when_clean(monkeypatch):
    parent = FakeParent(info_text="Compiled Successfully\n")
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    parent.add(glsl)
    mod = _load_service(monkeypatch, {glsl.path: glsl})

    d = mod.GlslStatusService().get_glsl_status("/project1/glsl1")["data"]
    assert d["ok"] is True
    assert d["compile_failed"] is False


def test_get_glsl_status_uses_existing_sibling_info_dat(monkeypatch):
    parent = FakeParent(info_text="SHOULD NOT BE READ")
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    info = FakeOp("/project1/glsl1_info", "infoDAT", text=COMPILE_LOG, parent=parent)
    parent.add(glsl)
    parent.add(info)
    mod = _load_service(monkeypatch, {glsl.path: glsl})

    d = mod.GlslStatusService().get_glsl_status("/project1/glsl1")["data"]
    assert d["compile_failed"] is True
    # no temp Info DAT created — the docked/sibling one was reused
    assert parent.create_calls == 0


def test_get_glsl_status_non_glsl_skips_info_dat(monkeypatch):
    parent = FakeParent(info_text=COMPILE_LOG)
    dat = FakeOp("/project1/text1", "textDAT", parent=parent)
    parent.add(dat)
    mod = _load_service(monkeypatch, {dat.path: dat})

    d = mod.GlslStatusService().get_glsl_status("/project1/text1")["data"]
    assert d["is_glsl"] is False
    assert d["compiler_log"] == ""
    assert parent.create_calls == 0


def test_get_glsl_status_missing_node(monkeypatch):
    mod = _load_service(monkeypatch, {})
    r = mod.GlslStatusService().get_glsl_status("/nope")
    assert r["success"] is False


def test_receipt_for_mutation_on_glsl_op(monkeypatch):
    parent = FakeParent(info_text=COMPILE_LOG)
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    parent.add(glsl)
    mod = _load_service(monkeypatch, {glsl.path: glsl})

    receipt = mod.GlslStatusService().receipt_for_mutation(glsl, {"outputresolution": "custom"})
    assert receipt is not None
    assert receipt["checked_node"] == "/project1/glsl1"
    assert receipt["compile_failed"] is True


def test_receipt_for_mutation_dat_sibling_scan(monkeypatch):
    parent = FakeParent(info_text=COMPILE_LOG)
    shader_dat = FakeOp("/project1/pixel", "textDAT", parent=parent)
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    glsl.par.pixeldat = FakePar(val="pixel")   # references the DAT by relative name
    glsl._op_refs["pixel"] = shader_dat          # sib.op('pixel') -> shader_dat
    parent.add(shader_dat)
    parent.add(glsl)
    mod = _load_service(monkeypatch, {glsl.path: glsl, shader_dat.path: shader_dat})

    receipt = mod.GlslStatusService().receipt_for_mutation(shader_dat, {"text": "void main(){}"})
    assert receipt is not None
    assert receipt["checked_node"] == "/project1/glsl1"   # resolved to the GLSL op


def test_receipt_for_mutation_none_when_unrelated(monkeypatch):
    parent = FakeParent()
    dat = FakeOp("/project1/text1", "textDAT", parent=parent)
    parent.add(dat)
    mod = _load_service(monkeypatch, {dat.path: dat})

    # A non-shader write on a plain DAT with no GLSL sibling -> no receipt.
    assert mod.GlslStatusService().receipt_for_mutation(dat, {"length": 3}) is None

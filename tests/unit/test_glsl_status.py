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
    assert g.mutation_touches_glsl(dat, {"pdat": "shader"}) is True    # glslMAT pixel-shader par
    assert g.mutation_touches_glsl(dat, {"vdat": "shader"}) is True    # glslMAT vertex-shader par
    assert g.mutation_touches_glsl(dat, {"length": 5}) is False       # unrelated DAT write
    assert g.mutation_touches_glsl(dat, None) is False


# ---------------------------------------------------------------------------
# glsl_status.GlslStatusService (W-A2 / W-A3)
# ---------------------------------------------------------------------------


class FakePar:
    """Models a TD par. PROVEN LIVE (2026-07-14, TD 099.2025.32820): an OP-type par
    (pixeldat/vertexdat/computedat/pdat/vdat) returns the referenced OPERATOR OBJECT
    from ``par.eval()`` — pass it as ``target``. String pars (e.g. ``file``) eval to
    their string val, which also models an OP par whose reference doesn't resolve."""

    def __init__(self, val="", target=None):
        self.val = val
        self._target = target

    def eval(self):
        return self._target if self._target is not None else self.val


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
        self._dock = None

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
        # PROVEN LIVE (2026-07-14, TD 099.2025.32820): OP.op(name) on a non-COMP does
        # NOT resolve sibling names — op('/x/glsl1').op('glsl1_pixel') is None even
        # for TD's own auto-docked default wiring. Only COMPs resolve relative names
        # (see FakeParent). The old sibling-resolving stub here is what let BUG-A
        # pass unit-tested.
        return None

    @property
    def dock(self):
        return self._dock

    @dock.setter
    def dock(self, host):
        # Live TD reflects docking immediately: setting child.dock = host makes the
        # child appear in host.docked.
        self._dock = host
        if host is not None and self not in host.docked:
            host.docked.append(self)


class FakeParent(FakeOp):
    def __init__(self, path="/project1", info_text="", **kw):
        super().__init__(path, "containerCOMP", **kw)
        self._children = {}          # name -> op
        self._info_text = info_text  # text a freshly-created temp Info DAT reports
        self.created = []            # temp ops created
        self.create_calls = 0

    def op(self, rel):
        # COMPs DO resolve relative child names (unlike base FakeOp above).
        return self._children.get(rel)

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
    # temp Info DAT created AND destroyed (no leak). This locks the READ_ONLY
    # contract of the get_glsl_status surface: a pure status read never leaves a
    # node behind — only the mutation-path receipt persists one (tests below).
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
    # is_glsl must be carried so the client can render the success-confirmation note
    # (td_live_client._glsl_status_note gates the "✅ GLSL compile OK" branch on it).
    assert receipt["is_glsl"] is True


def test_receipt_for_mutation_carries_is_glsl_on_clean_compile(monkeypatch):
    # On a clean compile the receipt must still carry is_glsl=True (and ok=True) so the
    # client's success-confirmation note fires — this half of W-A3 was dead when the
    # receipt omitted is_glsl.
    parent = FakeParent(info_text="Compiled Successfully\n")
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    parent.add(glsl)
    mod = _load_service(monkeypatch, {glsl.path: glsl})

    receipt = mod.GlslStatusService().receipt_for_mutation(glsl, {"outputresolution": "custom"})
    assert receipt is not None
    assert receipt["is_glsl"] is True
    assert receipt["ok"] is True
    assert receipt["compile_failed"] is False


def test_receipt_for_mutation_glslmat_pdat_scan(monkeypatch):
    # A Text DAT feeds a glslMAT via its `pdat` (pixel shader) par. Editing the DAT's
    # .text must resolve back to the MAT — glslMAT uses pdat/vdat, not pixeldat/
    # vertexdat/computedat, so the DAT-sibling scan must probe those par codes too.
    parent = FakeParent(info_text=COMPILE_LOG)
    shader_dat = FakeOp("/project1/pixelsrc", "textDAT", parent=parent)
    mat = FakeOp("/project1/glslmat1", "glslMAT", parent=parent)
    # BUG-A: relative ref — par.eval() yields the DAT object; mat.op('pixelsrc')
    # is None on live TD (non-COMP), so name-based resolution must NOT be used.
    mat.par.pdat = FakePar(val="pixelsrc", target=shader_dat)
    parent.add(shader_dat)
    parent.add(mat)
    mod = _load_service(monkeypatch, {mat.path: mat, shader_dat.path: shader_dat})

    receipt = mod.GlslStatusService().receipt_for_mutation(shader_dat, {"text": "void main(){}"})
    assert receipt is not None
    assert receipt["checked_node"] == "/project1/glslmat1"   # resolved to the glslMAT
    assert receipt["is_glsl"] is True


def test_receipt_for_mutation_dat_sibling_scan(monkeypatch):
    parent = FakeParent(info_text=COMPILE_LOG)
    shader_dat = FakeOp("/project1/pixel", "textDAT", parent=parent)
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    # BUG-A regression (proven live 2026-07-14): with a RELATIVE pixeldat ref the
    # receipt silently never fired — sib.op('pixel') is None on a non-COMP. The
    # fix resolves via par.eval(), which returns the DAT object directly.
    glsl.par.pixeldat = FakePar(val="pixel", target=shader_dat)
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


# ---------------------------------------------------------------------------
# W-A2 addendum — force-cook before status + file_path resolution
# ---------------------------------------------------------------------------


def test_get_glsl_status_force_cooks_the_op(monkeypatch):
    # PROVEN LIVE (2026-07-14): a file-synced shader DAT reloads from disk on its
    # own, but the GLSL op only RECOMPILES on its next cook — status read without
    # a force-cook is stale-clean. The status check must cook the op first.
    parent = FakeParent(info_text=COMPILE_LOG)
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    parent.add(glsl)
    mod = _load_service(monkeypatch, {glsl.path: glsl})

    mod.GlslStatusService().get_glsl_status("/project1/glsl1")
    assert glsl.cook_calls >= 1


def test_get_glsl_status_does_not_cook_non_glsl(monkeypatch):
    parent = FakeParent()
    dat = FakeOp("/project1/table1", "tableDAT", parent=parent)
    parent.add(dat)
    mod = _load_service(monkeypatch, {dat.path: dat})

    r = mod.GlslStatusService().get_glsl_status("/project1/table1")
    assert r["success"] is True
    assert dat.cook_calls == 0


def _load_service_with_root(monkeypatch, registry, root):
    if str(_MODULES_DIR) not in sys.path:
        sys.path.append(str(_MODULES_DIR))
    td_stub = types.ModuleType("td")
    td_stub.op = lambda path: registry.get(path)
    td_stub.root = root
    monkeypatch.setitem(sys.modules, "td", td_stub)
    return _load_by_path("td_glsl_status_file_undertest", _GLSL_SERVICE_PY)


def _shader_file_rig(broken=True):
    """A project with a textDAT synced to a shader file and a glslTOP fed by it."""
    parent = FakeParent(info_text=COMPILE_LOG if broken else "Compiled Successfully")
    dat = FakeOp("/project1/shader_src", "textDAT", parent=parent)
    dat.par.file = FakePar(r"C:\proj\shaders\probe_shader.glsl")
    parent.add(dat)
    glsl = FakeOp(
        "/project1/glsl1", "glslTOP",
        warnings="Warning: The GLSL Shader has compile errors (Use Info DAT to see details)." if broken else "",
        parent=parent,
    )
    # BUG-A: relative shader-source ref resolves ONLY via par.eval() (see FakeOp.op).
    glsl.par.pixeldat = FakePar("shader_src", target=dat)
    parent.add(glsl)
    registry = {dat.path: dat, glsl.path: glsl, parent.path: parent}
    return parent, dat, glsl, registry


def test_file_path_resolves_dat_and_checks_referencing_glsl_op(monkeypatch):
    parent, dat, glsl, registry = _shader_file_rig(broken=True)
    mod = _load_service_with_root(monkeypatch, registry, parent)

    r = mod.GlslStatusService().get_glsl_status(file_path=r"C:\proj\shaders\probe_shader.glsl")
    assert r["success"] is True, r.get("error")
    d = r["data"]
    assert d["matched_dats"] == ["/project1/shader_src"]
    assert d["checked_ops"] == ["/project1/glsl1"]
    assert d["compile_failed"] is True
    assert d["ok"] is False
    assert glsl.cook_calls >= 1        # the recompile actually happened


def test_file_path_basename_fallback_matches_relative_dat_path(monkeypatch):
    parent, dat, glsl, registry = _shader_file_rig(broken=False)
    dat.par.file = FakePar("shaders/probe_shader.glsl")   # project-relative form
    mod = _load_service_with_root(monkeypatch, registry, parent)

    r = mod.GlslStatusService().get_glsl_status(
        file_path=r"C:\somewhere\else\shaders\probe_shader.glsl"
    )
    assert r["success"] is True, r.get("error")
    assert r["data"]["checked_ops"] == ["/project1/glsl1"]
    assert r["data"]["ok"] is True


def test_file_path_no_match_is_friendly_error(monkeypatch):
    parent, dat, glsl, registry = _shader_file_rig()
    mod = _load_service_with_root(monkeypatch, registry, parent)

    r = mod.GlslStatusService().get_glsl_status(file_path=r"C:\nope\other.glsl")
    assert r["success"] is False
    assert "No op with a file par matching" in r["error"]


# ---------------------------------------------------------------------------
# BUG-A regression (proven live 2026-07-14, TD 099.2025.32820) — shader-source
# par resolution via par.eval(), plus the mutation-path persistent info DAT.
# ---------------------------------------------------------------------------


def test_receipt_resolves_via_parent_when_eval_is_stringy(monkeypatch):
    # Fallback branch: a par whose eval() yields only the string must resolve the
    # name against the PARENT (sibling names anchor there) — never via sib.op(),
    # which on live TD returns None for sibling names on a non-COMP.
    parent = FakeParent(info_text=COMPILE_LOG)
    shader_dat = FakeOp("/project1/pixel", "textDAT", parent=parent)
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    glsl.par.pixeldat = FakePar(val="pixel")      # eval() -> "pixel" (string)
    parent.add(shader_dat)
    parent.add(glsl)
    mod = _load_service(monkeypatch, {glsl.path: glsl, shader_dat.path: shader_dat})

    receipt = mod.GlslStatusService().receipt_for_mutation(shader_dat, {"text": "void main(){}"})
    assert receipt is not None
    assert receipt["checked_node"] == "/project1/glsl1"


def test_receipt_resolves_expression_mode_par(monkeypatch):
    # Expression-mode par: par.val is the RAW EXPRESSION string (useless as a
    # name); only par.eval() yields the operator. The fix must try eval() first.
    parent = FakeParent(info_text=COMPILE_LOG)
    shader_dat = FakeOp("/project1/pixel", "textDAT", parent=parent)
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    glsl.par.pixeldat = FakePar(val='op("pixel")', target=shader_dat)
    parent.add(shader_dat)
    parent.add(glsl)
    mod = _load_service(monkeypatch, {glsl.path: glsl, shader_dat.path: shader_dat})

    receipt = mod.GlslStatusService().receipt_for_mutation(shader_dat, {"text": "void main(){}"})
    assert receipt is not None
    assert receipt["checked_node"] == "/project1/glsl1"


def test_receipt_creates_persistent_docked_info_dat(monkeypatch):
    # Owner decision 2026-07-14: the mutation path (the W-A3 receipt, running inside
    # update_node — class DESTRUCTIVE) leaves a persistent `<name>_info` Info DAT
    # docked to a GLSL op that lacks one, matching TD's own create() convention and
    # the offline builder's _write_docked_info_dat. The plain get_glsl_status read
    # path keeps temp create+destroy (READ_ONLY annotation stays honest).
    parent = FakeParent(info_text=COMPILE_LOG)
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    parent.add(glsl)
    mod = _load_service(monkeypatch, {glsl.path: glsl})

    receipt = mod.GlslStatusService().receipt_for_mutation(glsl, {"outputresolution": "custom"})
    assert receipt is not None
    assert receipt["compile_failed"] is True
    assert parent.create_calls == 1
    info = parent.op("glsl1_info")
    assert info is not None
    assert info.destroyed is False               # persistent, not temp
    assert info in glsl.docked                   # docked to the GLSL op
    assert info.par.op == "glsl1"                # relative sibling ref (builder convention)


def test_receipt_reuses_persistent_info_dat(monkeypatch):
    parent = FakeParent(info_text=COMPILE_LOG)
    glsl = FakeOp("/project1/glsl1", "glslTOP", parent=parent)
    parent.add(glsl)
    mod = _load_service(monkeypatch, {glsl.path: glsl})
    svc = mod.GlslStatusService()

    assert svc.receipt_for_mutation(glsl, {"pixeldat": "x"}) is not None
    assert svc.receipt_for_mutation(glsl, {"pixeldat": "y"}) is not None
    # The second receipt found the docked/sibling `<name>_info` left by the first.
    assert parent.create_calls == 1

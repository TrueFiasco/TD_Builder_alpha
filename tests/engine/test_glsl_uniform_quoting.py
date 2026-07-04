"""W2b (audit C6/S12): ALL bridge .parm emission is quoting-aware via _parm_line.

The historical .parm desync class: TD's .parm parser is whitespace-delimited, so
one unquoted spaced value both self-truncates AND knocks the line parser out of
sync, silently reverting every FOLLOWING param in the file to its default (see
test_builder_parm_quoting.py for the live-verified failure mode). _param_lines
was fixed for that class, but the GLSL writers (_build_glsl_parm for the GLSL
TOP, _glsl_pop_uniform_lines for the GLSL POP) and the docked-DAT parms emitted
raw f-strings -- a uniform expression with a space (`absTime.seconds / 2.0`) or
an output root with a space in its path corrupted the file. W2b routes every
.parm body line through one emitter, toe_builder_bridge._parm_line.

Byte-level oracle: the build gate's raw reader (eval/build_gate/gate_common.py
read_parm_codes) -- whitespace-split, value returned RAW including quoting, the
same reader the gate uses against live-TD ground truth. Loaded lazily by path
(the eval harness sets offline env vars at import; snapshot/restore around it).

Builds offline via the real ToxBuilder path (the one td_build_project uses);
.tox.dir is written before toecollapse, so no TD binary is needed except for the
collapse->expand round-trip test, which self-skips without TD tools. KB-gated.
"""
import copy
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from paths import resolve_td_tool  # noqa: E402
from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402
from meta_agentic.execution.toe_builder_bridge import _parm_line  # noqa: E402

pytestmark = pytest.mark.requires_kb


@pytest.fixture(scope="module")
def read_parm_codes():
    """gate_common.read_parm_codes, loaded by file path inside the fixture so the
    hermetic (KB-free) lane never executes the eval harness at collection time."""
    gate_common_path = _REPO_ROOT / "eval" / "build_gate" / "gate_common.py"
    env_before = dict(os.environ)
    path_before = list(sys.path)
    try:
        spec = importlib.util.spec_from_file_location("_w2b_gate_common", gate_common_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        os.environ.clear()
        os.environ.update(env_before)
        sys.path[:] = path_before
    return mod.read_parm_codes


# ---------------------------------------------------------------------------
# Designs. uAfter/uB sit AFTER the space-carrying uniform on purpose: they are
# the desync victims -- pre-fix, the unquoted expression above them knocked the
# parser out of sync and their lines were the ones that silently dropped.
# ---------------------------------------------------------------------------
GLSL_TOP_DESIGN = {
    "operators": [
        {"name": "glsl1", "type": "glsl", "family": "TOP",
         "shader": "// pixel shader stub",
         "parameters": {"resolutionw": 1280, "resolutionh": 720, "resmult": True},
         "uniforms": [
             {"name": "uTime", "value": 1, "expr": "absTime.seconds / 2.0"},
             {"name": "uColor", "value": [0.1, 0.2, 0.3, 1.0],
              "expr": {"y": "me.time.frame % 10"}},
             {"name": "uScroll", "value": [0, 0],
              "expr": ["me.time.seconds * 0.1", None]},
             {"name": "uAfter", "value": 5},
         ]},
    ],
}

GLSL_POP_DESIGN = {
    "operators": [
        {"name": "pg", "type": "glsl", "family": "POP",
         "uniforms": [
             {"name": "uA", "value": 1.0, "expr": "absTime.seconds / 4"},
             {"name": "uB", "value": [1, 2, 3]},
         ]},
    ],
}


def _build_parm(tmp_path, design, name, op_name):
    # deepcopy: the builder injects docked wiring into the design's parameters
    # (op.setdefault("parameters", ...)), so a shared module-level design dict
    # would carry pixeldat/computedat into the next test and suppress auto-docking.
    ToxBuilder(str(tmp_path), verbose=False).build_tox(copy.deepcopy(design), name)
    return tmp_path / f"{name}.tox.dir" / name / f"{op_name}.parm"


def _assert_no_unquoted_space(body: str):
    """Every value/expression region with a space must carry quotes (the same
    sweep as test_builder_parm_quoting.test_no_space_token_left_unquoted)."""
    for line in body.splitlines():
        if line == "?" or not line.strip():
            continue
        parts = line.split(None, 2)  # name, mode, rest
        if len(parts) < 3:
            continue
        if " " in parts[2]:
            assert '"' in parts[2], f"unquoted space in: {line!r}"


# ---------------------------------------------------------------------------
# GLSL TOP (_build_glsl_parm early-return path)
# ---------------------------------------------------------------------------
def test_glsl_top_spaced_uniform_exprs_quoted(tmp_path, read_parm_codes):
    parm_path = _build_parm(tmp_path, GLSL_TOP_DESIGN, "w2b_top", "glsl1")
    body = parm_path.read_text(encoding="utf-8")

    # string-form expr on x (the killer case)
    assert 'vec0valuex 49 1 "absTime.seconds / 2.0"' in body, body
    # the exact pre-fix corruption must NOT appear
    assert "vec0valuex 49 1 absTime.seconds / 2.0" not in body, body
    # dict-form expr maps to the named component only
    assert 'vec1valuey 49 0.2 "me.time.frame % 10"' in body, body
    assert "vec1valuex 0 0.1" in body, body
    # list-form expr: index 0 gets the expression, index 1 stays constant
    assert 'vec2valuex 49 0 "me.time.seconds * 0.1"' in body, body
    assert "vec2valuey 0 0" in body, body
    _assert_no_unquoted_space(body)

    codes = read_parm_codes(parm_path)
    assert codes["vec0valuex"] == ("49", '1 "absTime.seconds / 2.0"'), codes["vec0valuex"]


def test_glsl_top_uniform_after_spaced_expr_survives(tmp_path, read_parm_codes):
    """The desync victim: the uniform AFTER the spaced expression must be intact."""
    parm_path = _build_parm(tmp_path, GLSL_TOP_DESIGN, "w2b_top_desync", "glsl1")
    codes = read_parm_codes(parm_path)
    assert codes.get("vec3name") == ("0", "uAfter"), codes.get("vec3name")
    assert codes.get("vec3valuex") == ("0", "5"), codes.get("vec3valuex")


def test_glsl_top_passthrough_params_normalized(tmp_path):
    """Passthrough params on the GLSL TOP path: bools become on/off, and the
    space-free lines keep their historical unquoted byte shape."""
    parm_path = _build_parm(tmp_path, GLSL_TOP_DESIGN, "w2b_top_params", "glsl1")
    body = parm_path.read_text(encoding="utf-8")
    assert "resmult 0 on" in body, body
    assert "True" not in body and "False" not in body, body
    assert "resolutionw 0 1280" in body, body
    assert "resolutionh 0 720" in body, body


# ---------------------------------------------------------------------------
# GLSL POP (_glsl_pop_uniform_lines appended to the normal parm flow)
# ---------------------------------------------------------------------------
def test_glsl_pop_spaced_expr_quoted_and_next_uniform_survives(tmp_path, read_parm_codes):
    parm_path = _build_parm(tmp_path, GLSL_POP_DESIGN, "w2b_pop", "pg")
    body = parm_path.read_text(encoding="utf-8")

    assert 'vec0valuex 49 1.0 "absTime.seconds / 4"' in body, body
    assert "vec0valuex 49 1.0 absTime.seconds / 4" not in body, body
    _assert_no_unquoted_space(body)

    codes = read_parm_codes(parm_path)
    assert codes["vec0type"] == ("0", "float"), codes["vec0type"]
    # desync victim: the whole second uniform must be intact
    assert codes.get("vec1name") == ("0", "uB")
    assert codes.get("vec1type") == ("0", "vec3")
    assert codes.get("vec1valuex") == ("0", "1")
    assert codes.get("vec1valuez") == ("0", "3")
    # the POP's normal parm flow (outputattrs default) is untouched
    assert codes.get("outputattrs") == ("0", "P")


def test_glsl_pop_dict_form_spaced_string_value_contained(tmp_path):
    """Dict-form uniforms with a garbage spaced string value: TD will reject the
    uniform, but the FILE must stay parseable (value quoted, no desync)."""
    design = {"operators": [{"name": "pg", "type": "glsl", "family": "POP",
                             "uniforms": {"uS": "a b"}}]}
    parm_path = _build_parm(tmp_path, design, "w2b_pop_dict", "pg")
    body = parm_path.read_text(encoding="utf-8")
    assert 'vec0valuex 0 "a b"' in body, body
    _assert_no_unquoted_space(body)


# ---------------------------------------------------------------------------
# Docked DAT parms: absolute file path with a space in the output root
# ---------------------------------------------------------------------------
def test_docked_dat_file_path_with_space_quoted(tmp_path, read_parm_codes):
    out_dir = tmp_path / "dir with space"
    out_dir.mkdir()
    ToxBuilder(str(out_dir), verbose=False).build_tox(copy.deepcopy(GLSL_TOP_DESIGN), "w2b_dock")
    comp_dir = out_dir / "w2b_dock.tox.dir" / "w2b_dock"

    file_parms = [p for p in comp_dir.glob("*.parm")
                  if "file" in read_parm_codes(p)]
    assert file_parms, f"no docked file-backed DAT .parm found in {comp_dir}"
    for p in file_parms:
        codes = read_parm_codes(p)
        mode, val = codes["file"]
        assert mode == "0"
        assert val.startswith('"') and val.endswith('"'), f"{p.name}: unquoted spaced path {val!r}"
        assert "dir with space" in val, val
        # pre-fix these were the desync victims below the truncated file line
        assert codes.get("syncfile") == ("0", "on"), (p.name, codes.get("syncfile"))
        assert codes.get("loadonstart") == ("0", "on"), (p.name, codes.get("loadonstart"))
        _assert_no_unquoted_space(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# _parm_line unit: the single emitter's edge cases
# ---------------------------------------------------------------------------
def test_parm_line_unit():
    # constants: spaces quoted, space-free bare, numbers verbatim
    assert _parm_line("chanscope", 0, "tx ty tz") == 'chanscope 0 "tx ty tz"'
    assert _parm_line("surftype", 0, "linestrip") == "surftype 0 linestrip"
    assert _parm_line("w", 0, 1280) == "w 0 1280"
    # toggles
    assert _parm_line("closed", 0, True) == "closed 0 on"
    assert _parm_line("specifypos", 0, False) == "specifypos 0 off"
    # mode 49: spaced expression quoted, space-free expression left bare
    assert (_parm_line("numcycles", 49, 3, "[3, 2, 7][me.chanIndex]")
            == 'numcycles 49 3 "[3, 2, 7][me.chanIndex]"')
    assert _parm_line("x", 49, 0, "absTime.frame") == "x 49 0 absTime.frame"
    # empty constant slot -> "" (the externaltox 49 "" <expr> shape)
    assert (_parm_line("externaltox", 49, "", "app.samplesFolder + '/Palette/x.tox'")
            == 'externaltox 49 "" "app.samplesFolder + \'/Palette/x.tox\'"')
    # pre-quoted values pass through untouched (never double-quoted)
    assert _parm_line("p", 0, '"already quoted"') == 'p 0 "already quoted"'
    # embedded double quotes are escaped inside the wrapping quotes
    assert _parm_line("p", 0, 'say "hi" now') == 'p 0 "say \\"hi\\" now"'


# ---------------------------------------------------------------------------
# Full round-trip through TD's own archive tokenizer (the gate's mechanism):
# build -> toecollapse -> real toeexpand -> raw reader; params byte-intact.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    resolve_td_tool("toeexpand") is None or resolve_td_tool("toecollapse") is None,
    reason="TouchDesigner tools (toeexpand/toecollapse) not installed",
)
def test_collapse_expand_roundtrip_byte_intact(tmp_path, read_parm_codes):
    design = copy.deepcopy(
        {"operators": GLSL_TOP_DESIGN["operators"] + GLSL_POP_DESIGN["operators"]})
    tox = ToxBuilder(str(tmp_path), verbose=False).build_tox(design, "w2b_rt")
    assert tox is not None and tox.exists(), "collapse failed"

    exp = tmp_path / "_expand"
    exp.mkdir()
    tox_copy = exp / tox.name
    shutil.copy2(tox, tox_copy)
    subprocess.run([str(resolve_td_tool("toeexpand")), str(tox_copy)],
                   cwd=str(exp), capture_output=True, text=True, timeout=120)
    # toeexpand returns rc 1 on success on some builds -> check for the .dir
    dirs = list(exp.glob("*.tox.dir"))
    assert dirs, "no .tox.dir produced by toeexpand"

    src_dir = tmp_path / "w2b_rt.tox.dir" / "w2b_rt"
    for op_name in ("glsl1", "pg"):
        before = read_parm_codes(src_dir / f"{op_name}.parm")
        after_files = list(dirs[0].glob(f"**/{op_name}.parm"))
        assert after_files, f"{op_name}.parm missing from expanded dir"
        after = read_parm_codes(after_files[0])
        assert after == before, (
            f"{op_name}.parm changed across collapse/expand:\n"
            f"before={before}\nafter={after}")
        # and the quoted spaced expression really is in the post-expand bytes
        if op_name == "glsl1":
            assert '"absTime.seconds / 2.0"' in after_files[0].read_text(encoding="utf-8")

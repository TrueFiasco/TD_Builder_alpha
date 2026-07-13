"""Repro for GAPS BUG 3 — a glslPOP's `shader`/`content` field must be written into
its docked `_compute` DAT file (shaders/<name>_compute.glsl), not the default stub.

The offline builder auto-docks the helper DATs a live create() makes; for a GLSL POP
that is a single file-backed `_compute` text DAT (KB/docked_dats.json -> "POP:glsl").
Before the fix, `_authored_for_role` only matched the literal field names
["compute","computeshader"] for the compute role, so a design that authored the shader
under `shader`/`content` (what the experts actually send) was ignored and the stub was
written. Mirrors the round-1 docking work (the TOP `pixel` role already accepts `shader`).

These tests build offline via ToxBuilder and inspect the on-disk shader file, so they
need no TouchDesigner binary (the .tox.dir/ + shaders/ are written before toecollapse).
KB-gated by tests/conftest.py (the builder reads ground truth + docked_dats from the KB).
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402

pytestmark = pytest.mark.requires_kb

POP_MARKER = "// CUSTOM_MARKER_BUG3_POP"
POP_SHADER = POP_MARKER + "\nvoid main() { P[TDIndex()] = vec3(1.0); }\n"
TOP_MARKER = "// CUSTOM_MARKER_BUG3_TOP"
TOP_SHADER = TOP_MARKER + "\nout vec4 fragColor;\nvoid main() { fragColor = vec4(1.0); }\n"


def _build(tmp_path, design, name):
    # build_tox returns the .tox path (or None if toecollapse is unavailable); either
    # way the .tox.dir/ and sibling shaders/ are already on disk for inspection.
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, name)
    return tmp_path


def test_glslpop_shader_field_lands_in_compute_dat(tmp_path):
    out = _build(
        tmp_path,
        {"operators": [{"name": "pg", "type": "glsl", "family": "POP", "shader": POP_SHADER}]},
        "bug3_pop",
    )
    compute = out / "shaders" / "pg_compute.glsl"
    assert compute.exists(), f"compute shader file not written: {list((out / 'shaders').glob('*')) if (out / 'shaders').exists() else 'no shaders dir'}"
    text = compute.read_text(encoding="utf-8")
    assert POP_MARKER in text, f"docked compute DAT got the stub, not the authored shader:\n{text}"
    assert "TDIndex()" in text  # our authored body, sanity


def test_glslpop_content_field_alias(tmp_path):
    # `content` is the other field name the GAPS report names; it must work too.
    out = _build(
        tmp_path,
        {"operators": [{"name": "pg", "type": "glsl", "family": "POP", "content": POP_SHADER}]},
        "bug3_content",
    )
    text = (out / "shaders" / "pg_compute.glsl").read_text(encoding="utf-8")
    assert POP_MARKER in text


def test_glsltop_shader_goes_to_pixel_not_compute(tmp_path):
    # Regression guard: a GLSL TOP has BOTH a pixel and a compute docked DAT. Its
    # `shader` field is the PIXEL shader; it must NOT also be copied into the compute
    # DAT (which would clobber the compute stub). The generic shader/content fallback
    # is only allowed for compute-only ops (no pixel spec), i.e. GLSL POPs.
    out = _build(
        tmp_path,
        {"operators": [{"name": "st", "type": "glsl", "family": "TOP", "shader": TOP_SHADER}]},
        "bug3_top",
    )
    pixel = (out / "shaders" / "st_pixel.glsl").read_text(encoding="utf-8")
    compute = (out / "shaders" / "st_compute.glsl").read_text(encoding="utf-8")
    assert TOP_MARKER in pixel, "pixel DAT should hold the authored shader"
    assert TOP_MARKER not in compute, "compute DAT must keep its stub, not the pixel shader"


def test_glsltop_content_field_alias_lands_in_pixel(tmp_path):
    # A GLSL TOP authored under `content` (the other field name the GAPS report uses)
    # must reach the pixel DAT too -- it silently fell to the stub before, because
    # only the compute-role fallback accepted the alias.
    out = _build(
        tmp_path,
        {"operators": [{"name": "st", "type": "glsl", "family": "TOP", "content": TOP_SHADER}]},
        "r2_content_top",
    )
    pixel = (out / "shaders" / "st_pixel.glsl").read_text(encoding="utf-8")
    assert TOP_MARKER in pixel, "TOP `content` field silently dropped -- pixel DAT got the stub"


def test_rebuild_preserves_hand_edited_shader(tmp_path):
    # R1: a design that authors NO shader must not re-stub a hand-edited (syncfile-
    # authored) shaders/*.glsl on rebuild -- the on-disk file is the operator's work.
    design = {"operators": [{"name": "pg", "type": "glsl", "family": "POP"}]}
    _build(tmp_path, design, "r1_keep")
    shader = tmp_path / "shaders" / "pg_compute.glsl"
    assert shader.exists()
    shader.write_text("// HAND_EDIT_PRESERVE_ME\nvoid main() {}\n", encoding="utf-8")
    _build(tmp_path, design, "r1_keep")  # rebuild, same design (no shader field)
    assert "HAND_EDIT_PRESERVE_ME" in shader.read_text(encoding="utf-8"), \
        "rebuild re-stubbed a hand-edited shader file"


def test_rebuild_with_design_shader_overwrites(tmp_path):
    # Design-authored content is the source of truth: when the design DOES carry a
    # shader, a rebuild overwrites any on-disk edit with it.
    design = {"operators": [{"name": "pg", "type": "glsl", "family": "POP", "shader": POP_SHADER}]}
    _build(tmp_path, design, "r1_win")
    shader = tmp_path / "shaders" / "pg_compute.glsl"
    shader.write_text("// HAND_EDIT_TO_BE_REPLACED\n", encoding="utf-8")
    _build(tmp_path, design, "r1_win")
    text = shader.read_text(encoding="utf-8")
    assert POP_MARKER in text, "design shader should win on rebuild"
    assert "HAND_EDIT_TO_BE_REPLACED" not in text

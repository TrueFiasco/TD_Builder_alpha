"""Repro for GAPS BUG 4 — a glslPOP's `uniforms` field must create Vectors-page
uniforms (vec{N}name / vec{N}type / vec{N}value{x..}) in the op's .parm.

Before the fix, the uniform->Vectors builder was gated behind `is_glsl_top`, so a GLSL
POP's `uniforms` was silently dropped. The GAPS report passes the DICT form
`uniforms: {"uScale": 1}`; the list form `[{"name","value"}]` must work too. The GLSL POP
Vectors page (KB operators.json -> "GLSL POP") requires `vec{N}type` to declare the
uniform (unlike the GLSL TOP path), so we assert that is emitted.

Builds offline via ToxBuilder and inspects the generated .parm; no TouchDesigner binary
needed. KB-gated by tests/conftest.py.
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


def _build_parm(tmp_path, design, name, op_name="pg"):
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, name)
    return (tmp_path / f"{name}.tox.dir" / name / f"{op_name}.parm").read_text(encoding="utf-8")


def test_glslpop_uniforms_dict_form(tmp_path):
    parm = _build_parm(
        tmp_path,
        {"operators": [{"name": "pg", "type": "glsl", "family": "POP", "uniforms": {"uScale": 1.5}}]},
        "bug4_dict",
    )
    assert "vec0name 0 uScale" in parm, f"no Vectors-page uniform emitted:\n{parm}"
    assert "vec0type 0 float" in parm, f"GLSL POP uniform needs vec0type:\n{parm}"
    assert "vec0valuex 0 1.5" in parm, parm


def test_glslpop_uniforms_list_form(tmp_path):
    parm = _build_parm(
        tmp_path,
        {"operators": [{"name": "pg", "type": "glsl", "family": "POP",
                        "uniforms": [{"name": "uColor", "value": [0.1, 0.2, 0.3]}]}]},
        "bug4_list",
    )
    assert "vec0name 0 uColor" in parm
    assert "vec0type 0 vec3" in parm
    assert "vec0valuex 0 0.1" in parm
    assert "vec0valuey 0 0.2" in parm
    assert "vec0valuez 0 0.3" in parm

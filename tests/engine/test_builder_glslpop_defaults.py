"""Builder-convenience: a GLSL POP should default outputattrs="P" when the design omits
it. A live-created glslPOP comes in with outputattrs='' -> P undeclared -> compile fail;
the offline builder mirrors the existing sopToCHOP attribscope='P' default so an omitted
outputattrs doesn't ship a broken POP. An explicit value must be preserved.

Builds offline via ToxBuilder; inspects the generated .parm. KB-gated by tests/conftest.py.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402


def _parm(tmp_path, design, name, op_name="pg"):
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, name)
    return (tmp_path / f"{name}.tox.dir" / name / f"{op_name}.parm").read_text(encoding="utf-8")


def test_glslpop_defaults_outputattrs_P(tmp_path):
    parm = _parm(tmp_path, {"operators": [{"name": "pg", "type": "glsl", "family": "POP"}]}, "d1")
    assert "outputattrs 0 P" in parm, f"glslPOP did not default outputattrs to P:\n{parm}"


def test_glsladvanced_pop_defaults_outputattrs_P(tmp_path):
    parm = _parm(tmp_path, {"operators": [{"name": "pg", "type": "glsladvanced", "family": "POP"}]}, "d1a")
    assert "outputattrs 0 P" in parm, parm


def test_explicit_outputattrs_preserved(tmp_path):
    parm = _parm(
        tmp_path,
        {"operators": [{"name": "pg", "type": "glsl", "family": "POP",
                        "parameters": {"outputattrs": "P N"}}]},
        "d2",
    )
    assert "outputattrs 0 P N" in parm, f"explicit outputattrs was overwritten:\n{parm}"


def test_non_glsl_pop_unaffected(tmp_path):
    # a plain grid POP must NOT get an outputattrs default (it has no such param)
    parm = _parm(tmp_path, {"operators": [{"name": "g", "type": "grid", "family": "POP"}]}, "d3", "g")
    assert "outputattrs" not in parm, parm

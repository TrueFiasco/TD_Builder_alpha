"""Regression: the offline builder must NOT mutate the caller's design dict.

W2b flagged that `_write_operator` wrote each op's auto-docked children back into the
CALLER's `op["parameters"]` (`op.setdefault("parameters", {})[host_param] = child`),
purely so `_build_glsl_parm` — which re-reads `op["parameters"]` — could see them. That
persisted the docked-DAT link params (`pixeldat`, ...) on the design object, so a REUSED
design silently lost its docked children on the SECOND build: `_write_docked_dats` skips
auto-docking any child whose host_param is already set, and the first build had set it.

The fix hands docked_wiring to `_build_glsl_parm` explicitly instead of mutating `op`.
This test proves (a) the design object is byte-unchanged after a build, and (b) building
the SAME design object twice yields identical output (the docked children survive).

Builds offline via ToxBuilder; KB-gated by tests/conftest.py (reads docked_dats.json).
"""
import copy
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


# A GLSL TOP with uniforms exercises BOTH the mutation site (docked pixel/compute/info
# DATs give docked_wiring) and the _build_glsl_parm consumer that used to rely on it.
def _glsl_design():
    return {
        "operators": [
            {"name": "sh", "type": "glsl", "family": "TOP",
             "uniforms": [{"name": "iRes", "value": [1, 1, 0, 0]}],
             "shader": "out vec4 fragColor; void main(){ fragColor = vec4(1.0); }"},
        ],
        "connections": [],
    }


def _rel_snapshot(root: Path):
    """{relative posix path: bytes} for every file under root."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


def _normalize(data: bytes, root: Path) -> bytes:
    """Strip the (varying) absolute output-root prefix so two builds into different dirs
    compare content-equal — docked DATs embed an absolute `file` path by design."""
    return data.replace(str(root).replace("\\", "/").encode(), b"<ROOT>")


def test_build_does_not_mutate_design(tmp_path):
    design = _glsl_design()
    before = copy.deepcopy(design)
    ToxBuilder(str(tmp_path / "a"), verbose=False).build_tox(design, "t")
    assert design == before, (
        "build mutated the caller's design dict; op['parameters'] must not gain "
        f"docked host_params. diff op0.parameters={design['operators'][0].get('parameters')!r}"
    )


def test_double_build_from_one_object_is_identical(tmp_path):
    design = _glsl_design()
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    ToxBuilder(str(root_a), verbose=False).build_tox(design, "t")   # first build
    ToxBuilder(str(root_b), verbose=False).build_tox(design, "t")   # SAME object reused

    snap_a = _rel_snapshot(root_a / "t.tox.dir")
    snap_b = _rel_snapshot(root_b / "t.tox.dir")

    # (a) the docked children must be present in BOTH — a lost child shows up as a
    #     missing file in build B (fresh dir), which set-equality catches.
    assert set(snap_a) == set(snap_b), (
        "second build produced a different file set — docked children lost on reuse. "
        f"only in first: {sorted(set(snap_a) - set(snap_b))}; "
        f"only in second: {sorted(set(snap_b) - set(snap_a))}"
    )
    assert any(f.endswith("sh_pixel.parm") for f in snap_a), \
        f"expected a docked pixel DAT; got {sorted(snap_a)}"

    # (b) content identical once the absolute output-root path is normalized out.
    for rel in snap_a:
        assert _normalize(snap_a[rel], root_a) == _normalize(snap_b[rel], root_b), \
            f"content diverged on second build for {rel}"

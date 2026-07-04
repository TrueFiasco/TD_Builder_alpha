"""Repro for GAPS BUG 2 — a geometry COMP requested via `containers` must build as a
geometryCOMP (COMP:geo) with its instancing params, not a generic COMP:container with the
params silently dropped.

Before the fix, `_write_container` hardcoded `COMP:container` and wrote an empty `?\n?\n`
.parm (only customPars were honoured), so type:"geometry" + instancing params produced a
broken generic container. The fix resolves the type via `_map_op_type` (geometry -> COMP:geo)
and applies the container's `parameters` through the shared `_param_lines` loop.

Builds offline via ToxBuilder; inspects the generated .n/.parm. No TouchDesigner binary
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


def _build(tmp_path, design, name):
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, name)
    return tmp_path / f"{name}.tox.dir" / name


def test_geometry_container_resolves_type_and_keeps_instancing(tmp_path):
    design = {"containers": [{
        "name": "geo_c", "type": "geometry", "family": "COMP",
        "parameters": {"instancing": 1, "instanceop": "../src", "instancetx": "tx"},
        "operators": [{"name": "torus_in", "type": "torus", "family": "SOP"}],
    }]}
    d = _build(tmp_path, design, "bug2")

    n = (d / "geo_c.n").read_text(encoding="utf-8")
    first = n.splitlines()[0]
    assert first == "COMP:geo", f"container built as {first!r}, expected COMP:geo:\n{n}"

    parm = (d / "geo_c.parm").read_text(encoding="utf-8")
    assert "instancing 0 1" in parm, f"instancing param dropped:\n{parm}"
    assert "instanceop" in parm and "instancetx" in parm, f"instance params dropped:\n{parm}"

    # the internal operator the geo instances is still created inside the container
    assert (d / "geo_c" / "torus_in.n").exists()


def test_plain_container_still_defaults_to_container(tmp_path):
    # Back-compat: a container with no `type` (legacy copy-paste group) stays COMP:container.
    design = {"containers": [{"name": "grp", "operators": [
        {"name": "n1", "type": "noise", "family": "CHOP"},
    ]}]}
    d = _build(tmp_path, design, "bug2_plain")
    first = (d / "grp.n").read_text(encoding="utf-8").splitlines()[0]
    assert first == "COMP:container", first

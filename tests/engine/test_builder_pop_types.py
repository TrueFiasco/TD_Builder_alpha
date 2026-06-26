"""Repro for GAPS BUG 1 — a Point Generator POP built as a base COMP.

The builder derives a POP's .n token from the wiki/display name (POP:pointgenerator), but
TD's real .n token is POP:pointgen — so TD imports the unknown type as a base COMP and
drops `numpoints`. Ground-truthed against a live TD save+expand of all 100 POPs: exactly 7
POPs have a token that differs from their basename; those get INTERNAL_NAME_MAP overrides.

Before the fix `_map_op_type("pointgenerator", _, "POP")` returned "POP:pointgenerator"
(the explicit-family fallback passes the name through unchanged); after the override it
returns "POP:pointgen". Builds offline and inspects the generated .n; KB-gated.
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


def _first_line(tmp_path, design, name, op_name):
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, name)
    p = tmp_path / f"{name}.tox.dir" / name / f"{op_name}.n"
    return p.read_text(encoding="utf-8").splitlines()[0]


def test_pointgenerator_uses_real_token_and_keeps_numpoints(tmp_path):
    design = {"operators": [
        {"name": "pg", "type": "pointgenerator", "family": "POP", "parameters": {"numpoints": 4410}},
    ]}
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, "bug1")
    d = tmp_path / "bug1.tox.dir" / "bug1"
    first = (d / "pg.n").read_text(encoding="utf-8").splitlines()[0]
    assert first == "POP:pointgen", f"built as {first!r}, not the real Point Generator POP token"
    parm = (d / "pg.parm").read_text(encoding="utf-8")
    assert "numpoints 0 4410" in parm, parm


@pytest.mark.parametrize("wiki,real", [
    ("pointgenerator", "pointgen"),
    ("glsladvanced", "glsladv"),
    ("attributecombine", "attcombine"),
    ("attributeconvert", "attconvert"),
    ("lookupattribute", "lookupatt"),
    ("lookupchannel", "lookupchan"),
    ("lookuptexture", "lookuptex"),
])
def test_abbreviated_pop_tokens(tmp_path, wiki, real):
    first = _first_line(tmp_path, {"operators": [{"name": "p", "type": wiki, "family": "POP"}]}, "t", "p")
    assert first == f"POP:{real}", first


@pytest.mark.parametrize("basename", ["grid", "sphere", "noise", "null", "merge", "glsl", "box"])
def test_matching_pop_basenames_still_resolve(tmp_path, basename):
    # control: POPs whose token equals their basename must keep resolving to POP:<basename>
    first = _first_line(tmp_path, {"operators": [{"name": "p", "type": basename, "family": "POP"}]}, "c", "p")
    assert first == f"POP:{basename}", first

"""td_validate must accept wires that touch containers (and their inner ops, any depth),
yet still reject a wire to a path that exists nowhere in the design."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "MCP"), str(REPO / "MCP" / "engine")):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.format_converter import FormatConverter, declared_paths  # noqa: E402
from validation.reference_validator import ReferenceValidator  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "container_wires"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _reference_errors(design):
    # Registry-free on purpose: from_builder and the reference stage never read the KB,
    # so these run in the hermetic (KB-free) lane. A placeholder registry avoids the
    # default OperatorRegistry() load.
    net = FormatConverter(registry=object()).from_builder(design)
    return [e.message for e in ReferenceValidator().validate(net).errors]


@pytest.mark.parametrize("fx", ["containers_wire_inner_ops.json",
                                "containers_wire_comp_to_comp.json"])
def test_fixture_reference_stage_clean(fx):
    assert _reference_errors(_load(fx)) == []


def test_missing_inner_op_still_rejected():
    d = _load("containers_wire_inner_ops.json")
    d["connections"][0]["to"] = "B/nope"
    errs = _reference_errors(d)
    assert any("/project1/B/nope" in m for m in errs), errs


def test_missing_container_still_rejected():
    d = _load("containers_wire_comp_to_comp.json")
    d["connections"][0]["to"] = "Z"
    assert any("/project1/Z" in m for m in _reference_errors(d))


def test_nested_container_paths_known():
    d = copy.deepcopy(_load("containers_wire_inner_ops.json"))
    d["containers"][0]["containers"] = [{
        "name": "deep", "type": "base", "family": "COMP",
        "operators": [{"name": "o", "type": "TOP:null"}]}]
    d["connections"] = [{"from": "A/deep/o", "to": "B/in1"}]
    assert _reference_errors(d) == []


def test_declared_paths_walks_every_container_shape():
    d = {"operators": [{"name": "top", "type": "TOP:null"}],
         "containers": [
             {"name": "A", "operators": [{"name": "x"}],
              "containers": [{"name": "deep", "children": [{"name": "y"}]}]},
             {"name": "N", "network": {"operators": [{"name": "z"}]}}]}
    assert declared_paths(d) == {
        "/project1/top", "/project1/A", "/project1/A/x", "/project1/A/deep",
        "/project1/A/deep/y", "/project1/N", "/project1/N/z"}


def test_dict_input_also_knows_container_paths():
    d = _load("containers_wire_inner_ops.json")
    d["connections"] = [{"from": "/project1/A/out1", "to": "/project1/B/in1"}]
    assert ReferenceValidator().validate(d).errors == []

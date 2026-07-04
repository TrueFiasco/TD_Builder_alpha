"""Component-source validator (BUG-3 validator half): a component is never a data source.

Mirrors the builder's build-time fail-loud (toe_builder_bridge._resolve_palette_source) as
a static td_validate rule. Proves it FIRES on seeded bare-component sources (with the same
vocabulary + candidate list) and stays QUIET on the resolvable cases the builder accepts —
including the BUG-3 external_tox fixture shapes from tests/unit/test_external_tox_wiring.py.

KB-gated (reads KB/palette_components.json).
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from validation.component_source_validator import ComponentSourceValidator  # noqa: E402

pytestmark = pytest.mark.requires_kb


# A tiny registry mirroring the real palette_components.json shape + the BUG-3 fixture
# provenance split (live == index authority; offline_manifest == name authority).
_REGISTRY = {
    "components": {
        "srcComp": {"tox_path": "tox/srcComp.tox",
                    "outputs": [{"index": 0, "out_op": "out1", "family": "CHOP"}],
                    "harvest": {"method": "offline_manifest+live"}},
        "liveMulti": {"tox_path": "tox/liveMulti.tox",
                      "outputs": [{"index": 0, "out_op": "out_a", "family": "CHOP"},
                                  {"index": 1, "out_op": "out_b", "family": "CHOP"}],
                      "harvest": {"method": "offline_manifest+live"}},   # index authority
        "offlineMulti": {"tox_path": "tox/offlineMulti.tox",
                         "outputs": [{"index": 0, "out_op": "out_a", "family": "CHOP"},
                                     {"index": 1, "out_op": "out_b", "family": "CHOP"}],
                         "harvest": {"method": "offline_manifest"}},     # name authority
        "noOut": {"tox_path": "tox/noOut.tox", "outputs": [],
                  "harvest": {"method": "offline_manifest+live"}},
    }
}


@pytest.fixture()
def validator(tmp_path):
    import json
    p = tmp_path / "palette_components.json"
    p.write_text(json.dumps(_REGISTRY), encoding="utf-8")
    return ComponentSourceValidator(palette_components_path=p)


def _codes(report):
    return [(f.code, f.severity, f.message) for f in report.errors + report.warnings]


# ---------------------------------------------------------------------------
# FIRES on seeded bare-component sources
# ---------------------------------------------------------------------------
def test_plain_comp_with_no_out_fires_error(validator):
    design = {"operators": [
        {"name": "box", "type": "base", "family": "COMP"},          # empty COMP
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "box", "to": "n1"}]}
    rep = validator.validate(design)
    assert rep.status == "FAIL"
    errs = [e for e in rep.errors if e.code == "COMPONENT_AS_SOURCE"]
    assert errs and "never itself a data source" in errs[0].message
    assert errs[0].suggestion == "box/out1"


def test_name_authority_multi_out_palette_fires_with_candidates(validator):
    design = {"operators": [
        {"name": "gen", "palette": "offlineMulti"},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "gen", "to": "n1"}]}
    rep = validator.validate(design)
    errs = [e for e in rep.errors if e.code == "COMPONENT_AS_SOURCE"]
    assert errs, _codes(rep)
    assert "out_a" in errs[0].message and "out_b" in errs[0].message   # candidates listed
    assert errs[0].suggestion == "gen/out_a"


def test_palette_zero_out_fires(validator):
    design = {"operators": [
        {"name": "gen", "palette": "noOut"},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "gen", "to": "n1"}]}
    rep = validator.validate(design)
    assert any(e.code == "COMPONENT_AS_SOURCE" for e in rep.errors), _codes(rep)


def test_in_design_multi_out_comp_warns_not_errors(validator):
    design = {"operators": [
        {"name": "grp", "type": "base", "family": "COMP", "operators": [
            {"name": "outA", "type": "out", "family": "CHOP"},
            {"name": "outB", "type": "out", "family": "CHOP"}]},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "grp", "to": "n1"}]}
    rep = validator.validate(design)
    assert rep.status == "PASS"   # advisory only (builder auto-binds the first)
    assert any(w.code == "COMPONENT_AS_SOURCE" for w in rep.warnings), _codes(rep)


# ---------------------------------------------------------------------------
# QUIET on the resolvable cases the builder accepts (BUG-3 fixture shapes)
# ---------------------------------------------------------------------------
def test_single_out_palette_quiet(validator):
    design = {"operators": [
        {"name": "gen", "palette": "srcComp"},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "gen", "to": "n1"}]}
    rep = validator.validate(design)
    assert rep.status == "PASS" and rep.errors == [] and rep.warnings == []


def test_index_authority_multi_out_palette_quiet(validator):
    # live-harvested multi-out: index order is connector truth → builder binds index 0.
    design = {"operators": [
        {"name": "gen", "palette": "liveMulti"},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "gen", "to": "n1"}]}
    rep = validator.validate(design)
    assert rep.status == "PASS" and not rep.errors, _codes(rep)


def test_explicit_inner_out_ref_quiet(validator):
    design = {"operators": [
        {"name": "gen", "palette": "offlineMulti"},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "gen/out_b", "to": "n1"}]}   # explicit → fine
    rep = validator.validate(design)
    assert rep.status == "PASS" and rep.errors == [], _codes(rep)


def test_external_tox_source_deferred_to_builder(validator):
    # external_tox interface needs a build-time toeexpand; the validator defers (stays quiet)
    # so the BUG-3 external_tox fixtures (resolvable single-out) are never falsely flagged.
    design = {"operators": [
        {"name": "fx", "external_tox": "components/fx.tox"},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "fx", "to": "n1"}]}
    rep = validator.validate(design)
    assert rep.status == "PASS" and rep.errors == [] and rep.warnings == []


def test_non_component_source_quiet(validator):
    # a plain CHOP source is not a component — never this rule's concern.
    design = {"operators": [
        {"name": "noise1", "type": "noise", "family": "CHOP"},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "noise1", "to": "n1"}]}
    rep = validator.validate(design)
    assert rep.status == "PASS" and rep.errors == [] and rep.warnings == []


def test_wiring_into_bare_comp_is_not_flagged(validator):
    # only SOURCE position matters — wiring INTO a bare comp (target) is resolved separately.
    design = {"operators": [
        {"name": "noise1", "type": "noise", "family": "CHOP"},
        {"name": "gen", "palette": "offlineMulti"},
    ], "connections": [{"from": "noise1", "to": "gen"}]}
    rep = validator.validate(design)
    assert rep.status == "PASS" and rep.errors == [], _codes(rep)

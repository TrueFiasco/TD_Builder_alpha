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
from core.operator_registry import OperatorRegistry  # noqa: E402
from core.format_converter import FormatConverter, extract_component_io  # noqa: E402
from core.models import OperatorFamily  # noqa: E402
from validation.pipeline import ValidationPipeline  # noqa: E402

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


def test_in_design_multi_out_comp_errors(validator):
    # owner policy: an in-design container has no connector-truth ordering, so a bare
    # multi-out source is ambiguous -> ERROR (the user must name which out).
    design = {"operators": [
        {"name": "grp", "type": "base", "family": "COMP", "operators": [
            {"name": "outA", "type": "out", "family": "CHOP"},
            {"name": "outB", "type": "out", "family": "CHOP"}]},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "grp", "to": "n1"}]}
    rep = validator.validate(design)
    assert rep.status == "FAIL"
    errs = [e for e in rep.errors if e.code == "COMPONENT_AS_SOURCE"]
    assert errs and "outA" in errs[0].message and "outB" in errs[0].message, _codes(rep)


# ---------------------------------------------------------------------------
# QUIET on the resolvable cases the builder accepts (BUG-3 fixture shapes)
# ---------------------------------------------------------------------------
def test_single_out_palette_warns_valid(validator):
    # owner policy: a bare single-out source is buildable but implicit -> WARNING, VALID.
    design = {"operators": [
        {"name": "gen", "palette": "srcComp"},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "gen", "to": "n1"}]}
    rep = validator.validate(design)
    assert rep.status == "PASS" and rep.errors == []          # stays VALID
    w = [w for w in rep.warnings if w.code == "COMPONENT_AS_SOURCE"]
    assert w, _codes(rep)
    # Cluster C: the warning is informational and must NOT steer to the 'comp/out1' rewrite
    # (the reference stage currently rejects that form — the advice would break a valid design).
    assert not w[0].suggestion and "gen/out1" not in w[0].message, w[0].message


def test_index_authority_multi_out_palette_warns_valid(validator):
    # live-harvested multi-out: index order IS connector truth → builder binds index 0
    # deterministically → not ambiguous → WARNING (valid), not an error.
    design = {"operators": [
        {"name": "gen", "palette": "liveMulti"},
        {"name": "n1", "type": "null", "family": "CHOP"},
    ], "connections": [{"from": "gen", "to": "n1"}]}
    rep = validator.validate(design)
    assert rep.status == "PASS" and not rep.errors, _codes(rep)
    assert any(w.code == "COMPONENT_AS_SOURCE" for w in rep.warnings), _codes(rep)


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


# ===========================================================================
# SHIPPED-PATH regression tests (W3a review). The bug that shipped: on the real
# td_validate path the network is FLATTENED by FormatConverter.from_builder BEFORE
# this stage runs, deleting a container's inner ops → the stage saw zero outs and
# false-ERRORed valid, buildable designs. The bypass-the-converter tests above hid
# it. These route through the actual tool path: from_builder -> ValidationPipeline.
# ===========================================================================

def _pipeline_report(design):
    reg = OperatorRegistry()
    net = FormatConverter(reg).from_builder(design)
    return net, ValidationPipeline(reg).validate(net, "shipped_path")


def _cw_stage(report):
    st = [s for s in report.stages if s.stage == "component_wiring"]
    assert st, [s.stage for s in report.stages]
    return st[0]


def _comp(name, inner_out_names):
    return {"name": name, "type": "base", "family": "COMP",
            "operators": [{"name": n, "type": "out", "family": "CHOP"} for n in inner_out_names]}


def test_shipped_from_builder_preserves_component_io():
    # the fix's mechanism: the inner outs survive conversion on custom_data even though the
    # network itself is flattened to [/src, /dst].
    net, _ = _pipeline_report({
        "operators": [_comp("src", ["out1"]), {"name": "dst", "type": "base", "family": "COMP"}],
        "connections": [{"from": "src", "to": "dst"}]})
    assert [o.path for o in net.operators] == ["/src", "/dst"], "expected the flattened network"
    src = next(o for o in net.operators if o.path == "/src")
    assert src.custom_data.get("component_io") == {"kind": "comp", "out_ops": ["out1"], "in_ops": []}


def test_shipped_single_out_bare_source_is_valid_with_warning():
    _, rep = _pipeline_report({
        "operators": [_comp("src", ["out1"]), {"name": "dst", "type": "base", "family": "COMP"}],
        "connections": [{"from": "src", "to": "dst"}]})
    assert rep.valid is True, [(e.stage, e.code, e.message) for e in rep.get_errors()]
    cw = _cw_stage(rep)
    assert cw.status == "PASS" and cw.errors == []
    warns = [w for w in cw.warnings if w.code == "COMPONENT_AS_SOURCE"]
    # informational warning, no 'src/out1' rewrite steer (Cluster C).
    assert warns and not warns[0].suggestion and "src/out1" not in warns[0].message, _codes(cw)


def test_shipped_multi_out_bare_source_is_error():
    _, rep = _pipeline_report({
        "operators": [_comp("src", ["outA", "outB"]), {"name": "dst", "type": "base", "family": "COMP"}],
        "connections": [{"from": "src", "to": "dst"}]})
    cw = _cw_stage(rep)
    assert cw.status == "FAIL"
    errs = [e for e in cw.errors if e.code == "COMPONENT_AS_SOURCE"]
    assert errs and "outA" in errs[0].message and "outB" in errs[0].message, _codes(cw)
    assert rep.valid is False


def test_shipped_zero_out_bare_source_is_error():
    # a COMP that has inner ops but NO out op -> genuinely zero outputs -> ERROR.
    src = {"name": "src", "type": "base", "family": "COMP",
           "operators": [{"name": "mid", "type": "noise", "family": "CHOP"}]}
    _, rep = _pipeline_report({
        "operators": [src, {"name": "dst", "type": "base", "family": "COMP"}],
        "connections": [{"from": "src", "to": "dst"}]})
    cw = _cw_stage(rep)
    assert cw.status == "FAIL"
    assert any(e.code == "COMPONENT_AS_SOURCE" for e in cw.errors), _codes(cw)
    assert rep.valid is False


def test_shipped_explicit_inner_ref_is_component_wiring_clean():
    # the recommended explicit form must draw NO finding from THIS stage (the reference
    # stage's handling of flattened inner-op paths is a separate, pre-existing concern).
    _, rep = _pipeline_report({
        "operators": [_comp("src", ["out1", "out2"]), {"name": "dst", "type": "base", "family": "COMP"}],
        "connections": [{"from": "src/out1", "to": "dst"}]})
    cw = _cw_stage(rep)
    assert cw.status == "PASS"
    assert not any(f.code == "COMPONENT_AS_SOURCE" for f in cw.errors + cw.warnings), _codes(cw)


def test_shipped_flat_design_draws_no_component_finding():
    # a normal flat CHOP->CHOP design must be untouched by this stage (no false positives).
    _, rep = _pipeline_report({
        "operators": [{"name": "a", "type": "noise", "family": "CHOP"},
                      {"name": "b", "type": "null", "family": "CHOP"}],
        "connections": [{"from": "a", "to": "b"}]})
    cw = _cw_stage(rep)
    assert cw.status == "PASS" and cw.errors == [] and cw.warnings == []
    assert rep.valid is True


def test_shipped_root_qualified_source_matches_bare_form():
    # D10 regression (adversarial workflow): a ROOT-QUALIFIED bare-comp source
    # ('/project1/src') must get the SAME verdict as the bare form ('src') — the earlier
    # root-strip made the answer depend on path depth. Multi-out -> ERROR (ambiguous which
    # out?), single-out -> WARNING (valid). The full path names the component, not the output.
    multi = {"operators": [_comp("src", ["out1", "out2"]), {"name": "d", "type": "base", "family": "COMP"}],
             "connections": [{"from": "/project1/src", "to": "d"}]}
    _, rep = _pipeline_report(multi)
    cw = _cw_stage(rep)
    assert cw.status == "FAIL" and any(e.code == "COMPONENT_AS_SOURCE" for e in cw.errors), _codes(cw)

    single = {"operators": [_comp("src", ["out1"]), {"name": "d", "type": "base", "family": "COMP"}],
              "connections": [{"from": "/project1/src", "to": "d"}]}
    _, rep2 = _pipeline_report(single)
    cw2 = _cw_stage(rep2)
    assert cw2.status == "PASS" and any(w.code == "COMPONENT_AS_SOURCE" for w in cw2.warnings), _codes(cw2)


def test_shipped_root_qualified_explicit_ref_is_clean():
    # '/project1/src/out1' — last segment is the inner op, so it's an explicit reference:
    # NO component_wiring finding (path-form-agnostic with the bare 'src/out1' form).
    _, rep = _pipeline_report({
        "operators": [_comp("src", ["out1", "out2"]), {"name": "d", "type": "base", "family": "COMP"}],
        "connections": [{"from": "/project1/src/out1", "to": "d"}]})
    cw = _cw_stage(rep)
    assert cw.status == "PASS"
    assert not any(f.code == "COMPONENT_AS_SOURCE" for f in cw.errors + cw.warnings), _codes(cw)


def test_shipped_nested_component_source_defers():
    # a source referencing a component NESTED inside another comp ('/project1/geo1/mixer'):
    # from_builder only stashes top-level components, so the validator can't see mixer's
    # interface -> it DEFERS (no finding), never false-positives. The design still builds.
    nested = {"operators": [
        {"name": "geo1", "type": "base", "family": "COMP",
         "operators": [_comp("mixer", ["out1", "out2"])]},
        {"name": "d", "type": "base", "family": "COMP"}],
        "connections": [{"from": "/project1/geo1/mixer", "to": "d"}]}
    _, rep = _pipeline_report(nested)
    cw = _cw_stage(rep)
    assert not any(f.code == "COMPONENT_AS_SOURCE" for f in cw.errors + cw.warnings), _codes(cw)


def test_shipped_explicit_ref_colliding_with_component_name_not_blocked():
    # Cluster A: an explicit inner ref 'src/out1' must NOT be mis-judged as a bare reference
    # to a DIFFERENT top-level component that happens to be named 'out1'. Last-segment matching
    # flipped this valid, buildable design to INVALID; full-identity exact-match does not.
    design = {"meta": {"root_comp": "project1"},
              "operators": [_comp("src", ["out1"]), _comp("out1", ["a"]),
                            {"name": "d", "type": "base", "family": "COMP"}],
              "connections": [{"from": "src/out1", "to": "d"}]}
    _, rep = _pipeline_report(design)
    cw = _cw_stage(rep)
    assert not any(f.code == "COMPONENT_AS_SOURCE" for f in cw.errors + cw.warnings), _codes(cw)


def test_shipped_nested_ref_with_toplevel_same_name_not_misjudged():
    # Cluster A / finding #4: 'foo/mixer' references a mixer NESTED inside foo, NOT the
    # distinct TOP-LEVEL 'mixer'. It must not be judged against the wrong (top-level) component.
    design = {"meta": {"root_comp": "project1"},
              "operators": [
                  {"name": "foo", "type": "base", "family": "COMP",
                   "operators": [_comp("mixer", ["o1", "o2"])]},
                  _comp("mixer", ["single"]),
                  {"name": "d", "type": "base", "family": "COMP"}],
              "connections": [{"from": "foo/mixer", "to": "d"}]}
    _, rep = _pipeline_report(design)
    cw = _cw_stage(rep)
    # 'foo/mixer' is not an exact-identity match for any top-level component -> deferred.
    assert not any(f.code == "COMPONENT_AS_SOURCE" for f in cw.errors + cw.warnings), _codes(cw)


def test_shipped_single_out_warning_does_not_recommend_rejected_form():
    # Cluster C: the single-out warning must be informational and must NOT advise rewriting
    # to 'comp/out1' — the reference stage currently rejects that inner-op path, so following
    # the advice would break a design that already validates.
    _, rep = _pipeline_report({
        "operators": [_comp("src", ["out1"]), {"name": "d", "type": "base", "family": "COMP"}],
        "connections": [{"from": "src", "to": "d"}]})
    cw = _cw_stage(rep)
    warns = [w for w in cw.warnings if w.code == "COMPONENT_AS_SOURCE"]
    assert warns, _codes(cw)
    assert not warns[0].suggestion, warns[0].suggestion
    assert "src/out1" not in warns[0].message, warns[0].message   # no rejected-path rewrite steer


def test_extract_component_io_unit():
    # the converter helper in isolation.
    assert extract_component_io({"external_tox": "x.tox"}, OperatorFamily.COMP) == {"kind": "external_tox"}
    assert extract_component_io({"palette": "audioAnalysis"}, OperatorFamily.COMP) == {"kind": "palette", "palette": "audioAnalysis"}
    assert extract_component_io({"type": "noise"}, OperatorFamily.CHOP) is None
    got = extract_component_io(
        {"type": "base", "family": "COMP",
         "operators": [{"name": "out1", "type": "out", "family": "CHOP"},
                       {"name": "in1", "type": "in", "family": "CHOP"},
                       {"name": "mid", "type": "noise", "family": "CHOP"}]},
        OperatorFamily.COMP)
    assert got == {"kind": "comp", "out_ops": ["out1"], "in_ops": ["in1"]}

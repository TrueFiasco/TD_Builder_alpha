"""Grounding validator (Stage 2.5) — family-correctness vs the shipped-KB build_token.

Proves the grounding guardrail is WIRED into td_validate (the ValidationPipeline), grounds
from KB/operators.json (shipped data, never the dev corpus), surfaces a wrong-family design
as an advisory finding naming the correct token, and stays silent on correct designs. Also
covers the build-time override half (`ground_design`).

KB-gated by tests/conftest.py (reads KB/operators.json).
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from core.operator_registry import OperatorRegistry  # noqa: E402
from core.format_converter import FormatConverter  # noqa: E402
from validation.pipeline import ValidationPipeline  # noqa: E402
from validation.grounding_validator import GroundingValidator  # noqa: E402

pytestmark = pytest.mark.requires_kb


def _grounding_stage(report):
    stages = [s for s in report.stages if s.stage == "grounding"]
    assert stages, f"grounding stage missing from pipeline; stages={[s.stage for s in report.stages]}"
    return stages[0]


# ---------------------------------------------------------------------------
# WIRED: the grounding finding surfaces in the full td_validate pipeline report
# ---------------------------------------------------------------------------
def test_wrong_family_surfaces_grounded_finding_in_pipeline():
    reg = OperatorRegistry()
    conv = FormatConverter(reg)
    pipeline = ValidationPipeline(reg)

    # 'bloom' is a TOP-only operator; declaring it CHOP is a wrong-family design.
    net = conv.from_builder({"operators": [{"name": "b", "type": "bloom", "family": "CHOP"}],
                             "connections": []})
    report = pipeline.validate(net, "wrong_family")

    g = _grounding_stage(report)
    codes = {(w.code, w.severity) for w in g.warnings}
    assert ("GROUNDING_FAMILY_MISMATCH", "warning") in codes, [w.message for w in g.warnings]
    hit = next(w for w in g.warnings if w.code == "GROUNDING_FAMILY_MISMATCH")
    assert hit.suggestion == "TOP:bloom", hit.suggestion
    assert "TOP" in hit.message and "bloom" in hit.message

    # advisory: grounding itself never errors or fails its stage (a wrong family still
    # builds *something*); the finding is a warning that names the fix.
    assert g.errors == []
    assert g.status == "PASS"


def test_correct_design_has_no_grounding_warnings():
    reg = OperatorRegistry()
    conv = FormatConverter(reg)
    pipeline = ValidationPipeline(reg)
    net = conv.from_builder({"operators": [
        {"name": "n", "type": "noise", "family": "CHOP"},
        {"name": "a", "type": "add", "family": "TOP"},
        {"name": "c", "type": "camera", "family": "COMP"},   # abbrev, grounded via alias
    ], "connections": []})
    report = pipeline.validate(net, "ok")
    g = _grounding_stage(report)
    assert g.warnings == [], [w.message for w in g.warnings]


# ---------------------------------------------------------------------------
# GroundingValidator unit surface (shipped-data grounding)
# ---------------------------------------------------------------------------
def test_check_design_on_builder_dict():
    gv = GroundingValidator()
    findings = gv.check_design({"operators": [
        {"name": "b", "type": "bloom", "family": "CHOP"},   # wrong family
        {"name": "n", "type": "noise", "family": "CHOP"},   # fine (multi-family, incl CHOP)
        {"name": "c", "type": "camera", "family": "COMP"},  # fine (abbrev alias)
    ]})
    codes = {f["code"] for f in findings}
    assert codes == {"GROUNDING_FAMILY_MISMATCH"}, findings
    assert findings[0]["suggestion"] == "TOP:bloom"


def test_ungrounded_or_unknown_type_is_silent():
    # a type that grounds under NO family must not be flagged by grounding (semantic owns
    # genuinely-unknown types; grounding must not false-flag real ops lacking a build_token).
    gv = GroundingValidator()
    findings = gv.check_design({"operators": [
        {"name": "x", "type": "totallynotanoperator", "family": "TOP"},
    ]})
    assert findings == [], findings


def test_ground_design_rewrites_to_build_token_without_mutating_input():
    gv = GroundingValidator()
    design = {"operators": [
        {"name": "c", "type": "camera", "family": "COMP"},   # -> COMP:cam
        {"name": "a", "type": "add", "family": "TOP"},        # -> TOP:add
        {"name": "n", "type": "noise", "family": "CHOP"},     # -> CHOP:noise
    ]}
    grounded = gv.ground_design(design)
    got = {o["name"]: o["type"] for o in grounded["operators"]}
    assert got == {"c": "COMP:cam", "a": "TOP:add", "n": "CHOP:noise"}, got
    # input untouched + idempotent
    assert design["operators"][0]["type"] == "camera"
    assert gv.ground_design(grounded) == grounded


def test_missing_kb_is_silent_noop(tmp_path):
    # KB-free lane: an unreadable path yields empty indexes and no findings/crash.
    gv = GroundingValidator(kb_operators_path=tmp_path / "does_not_exist.json")
    assert gv.check_design({"operators": [{"name": "b", "type": "bloom", "family": "CHOP"}]}) == []
    assert gv.validate({"operators": [{"name": "b", "type": "bloom", "family": "CHOP"}]}).status == "PASS"

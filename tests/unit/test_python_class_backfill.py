"""python_class backfill from the live census (board GT5).

HERMETIC: hand-built fixtures against kb_build.common.enrich_python_class. No KB
artifact, no TouchDesigner. Deliberately unmarked so it runs in both ci.yml lanes.

WHY THE CONTRACT LOOKS LIKE THIS. 164 of 663 KB operators carried no
python_class, 73 of them POPs -- not because those operators lack a class, but
because the KB scraped class names from offline-help class PAGES and that mirror
ships under half the pages it references (104 of the missing are POP classes).
So the nulls are a mirror artifact and filling them is a repair.

The 24 populated-but-wrong values are a different case. They may be overwritten
ONLY via an allowlist whose every entry was arbitrated by instantiating the
operator in live TouchDesigner. Anything else that disagrees with the derivation
is REPORTED, never written -- so an operator whose class genuinely diverges from
its OPType (which TD is free to introduce) surfaces as a finding instead of
being silently clobbered.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from kb_build.common import (  # noqa: E402
    PYTHON_CLASS_OVERWRITE_VERIFIED,
    _norm,
    enrich_python_class,
)


def _gt(*pairs):
    """(family, display name, td_create) -> the index enrich_python_class expects."""
    return {(fam, _norm(name)): tdc for fam, name, tdc in pairs}


def _op(fam, name, pyc=None):
    return {"family": fam, "name": name, "python_class": pyc}


# --------------------------------------------------------------------------
# filling nulls
# --------------------------------------------------------------------------
def test_fills_a_null_from_the_census():
    ops = [_op("POP", "Accumulate POP")]
    filled, corrected, unverified = enrich_python_class(
        ops, _gt(("POP", "Accumulate POP", "accumulatePOP")))
    assert (filled, corrected, unverified) == (1, 0, [])
    assert ops[0]["python_class"] == "accumulatePOP_Class"


def test_empty_string_counts_as_null():
    ops = [_op("POP", "Accumulate POP", "")]
    filled, _, _ = enrich_python_class(
        ops, _gt(("POP", "Accumulate POP", "accumulatePOP")))
    assert filled == 1
    assert ops[0]["python_class"] == "accumulatePOP_Class"


def test_never_overwrites_a_value_that_already_agrees():
    ops = [_op("POP", "Accumulate POP", "accumulatePOP_Class")]
    assert enrich_python_class(
        ops, _gt(("POP", "Accumulate POP", "accumulatePOP"))) == (0, 0, [])


def test_leaves_fossils_null():
    """A fossil is absent from the census, so there is nothing to derive.
    Synthesising `cudaTOP_Class` for an operator that cannot be created is the
    fabrication this wave removes -- null is the honest value."""
    ops = [_op("TOP", "CUDA TOP")]
    assert enrich_python_class(ops, _gt()) == (0, 0, [])
    assert ops[0]["python_class"] is None


def test_leaves_a_populated_fossil_untouched():
    ops = [_op("SOP", "Font SOP", "fontSOP_Class")]
    assert enrich_python_class(ops, _gt()) == (0, 0, [])
    assert ops[0]["python_class"] == "fontSOP_Class"


# --------------------------------------------------------------------------
# the join key
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kb_name, gt_name", [
    ("Nvidia Flex TOP", "NVIDIA_Flex_TOP"),
    ("Nvidia Flex Solver COMP", "NVIDIA_Flex_Solver_COMP"),
    ("Nvidia Flow TOP", "NVIDIA_Flow_TOP"),
    ("wrnchAI CHOP", "WrnchAI_CHOP"),
    ("TCP/IP DAT", "TCP/IP_DAT"),
    ("Art-Net DAT", "Art-Net_DAT"),
])
def test_join_is_normalised_not_literal(kb_name, gt_name):
    """TouchDesigner's own docs are inconsistently cased -- NVIDIA_Flex_TOP but
    Nvidia_Flow_Emitter_COMP -- and some names carry '/' or '-'. A literal
    name.replace(' ','_') join silently drops these; _norm() does not. Measured:
    _norm 663/663, literal 659/663."""
    fam = gt_name.rsplit("_", 1)[1]
    ops = [_op(fam, kb_name)]
    filled, _, _ = enrich_python_class(ops, _gt((fam, gt_name, "tok" + fam)))
    assert filled == 1, f"{kb_name!r} failed to join {gt_name!r}"


# --------------------------------------------------------------------------
# the overwrite allowlist
# --------------------------------------------------------------------------
def test_corrects_only_allowlisted_mismatches():
    """Alembic In POP is the designated trap: the KB says alembicPOP_Class and
    TouchDesigner's own doc page title agrees with the KB -- but instantiating the
    operator returns class `alembicinPOP`. Live TD wins over documentation."""
    ops = [_op("POP", "Alembic In POP", "alembicPOP_Class")]
    filled, corrected, unverified = enrich_python_class(
        ops, _gt(("POP", "Alembic In POP", "alembicinPOP")))
    assert (filled, corrected, unverified) == (0, 1, [])
    assert ops[0]["python_class"] == "alembicinPOP_Class"


def test_unlisted_mismatch_is_reported_never_written():
    ops = [_op("CHOP", "Some Future CHOP", "deliberatelyDifferent_Class")]
    filled, corrected, unverified = enrich_python_class(
        ops, _gt(("CHOP", "Some Future CHOP", "somefutureCHOP")))
    assert (filled, corrected) == (0, 0)
    assert unverified == [("CHOP", "Some Future CHOP",
                           "deliberatelyDifferent_Class", "somefutureCHOP_Class")]
    assert ops[0]["python_class"] == "deliberatelyDifferent_Class"


def test_allowlist_disagreeing_with_the_census_raises():
    """The allowlist is the reviewed artifact and the census is the measurement.
    If they drift apart, fail loudly rather than silently preferring one."""
    ops = [_op("POP", "Alembic In POP", "alembicPOP_Class")]
    with pytest.raises(ValueError, match="re-arbitrate against live TD"):
        enrich_python_class(ops, _gt(("POP", "Alembic In POP", "somethingElsePOP")))


def test_every_allowlist_entry_derives_from_its_optype():
    """Each entry must be `<OPType>_Class`; a hand-typed value that is not would
    mean the allowlist encodes a guess rather than the live probe."""
    for (fam, name), value in PYTHON_CLASS_OVERWRITE_VERIFIED.items():
        assert value.endswith("_Class"), (fam, name, value)
        assert value[:-6], (fam, name, value)


def test_allowlist_is_the_measured_size():
    assert len(PYTHON_CLASS_OVERWRITE_VERIFIED) == 24


# --------------------------------------------------------------------------
# contract
# --------------------------------------------------------------------------
def test_is_idempotent():
    ops = [_op("POP", "Accumulate POP"),
           _op("POP", "Alembic In POP", "alembicPOP_Class")]
    gt = _gt(("POP", "Accumulate POP", "accumulatePOP"),
             ("POP", "Alembic In POP", "alembicinPOP"))
    first = enrich_python_class(ops, gt)
    assert first == (1, 1, [])
    assert enrich_python_class(ops, gt) == (0, 0, [])


def test_operators_absent_from_the_census_are_skipped_entirely():
    ops = [_op("CHOP", "Not In Census CHOP", "whateverCHOP_Class")]
    assert enrich_python_class(ops, _gt()) == (0, 0, [])

"""Census <-> KB <-> ground-truth reconciliation (board GT7) -- checks (c), (d), (e).

REQUIRES THE KB, in two ways that must BOTH be respected:

  1. The module-level `requires_kb` mark is LOAD-BEARING. This module reads
     KB/operators.json DIRECTLY, with no `server`/`probe` fixture, so
     tests/conftest.py's fixture-driven automark cannot see the dependency (its
     docstring says exactly this). Without the mark, the hermetic lane -- which
     ci.yml actively guarantees has no KB -- would try to run these.

  2. The KB read is DEFERRED into _kb_operators(), never done at module scope.
     The marker alone is NOT enough: pytest IMPORTS a module before applying
     `-m`, so a module-level `json.loads(KB/operators.json)` raises
     FileNotFoundError during COLLECTION on a KB-free runner. That is
     "Interrupted: 1 error during collection", not a clean deselect, and it takes
     down both the hermetic test step and the collection-floor step (which runs
     `--co -q`). Verified by reproduction, and note the local Gate-G check
     (`-m "not requires_kb" --co | grep census_guard` = 0 hits) CANNOT catch this
     on a machine that has the KB. Tracked files may be read at module scope;
     gitignored ones may not.

THE THREE NUMBERS, never to be conflated (owner ruling), all asserted here
against the artifacts rather than quoted:
    647 = operators in TouchDesigner   (the census)
    640 = KB coverage                  (663 entries minus 23 fossils)
    663 = KB entries
Live-verified: 663 - 23 + 7 = 647.
"""
from __future__ import annotations

import copy
import functools
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "scripts"), str(REPO / "MCP")):
    if p not in sys.path:
        sys.path.insert(0, p)

import census_guard as G  # noqa: E402

pytestmark = pytest.mark.requires_kb

# TRACKED files -- safe to read at import time; they exist in every checkout.
CENSUS = json.loads(
    (REPO / "eval" / "ground_truth" / "td_census.json").read_text(encoding="utf-8"))
GT = json.loads(
    (REPO / "eval" / "ground_truth" / "operator_types.json").read_text(encoding="utf-8"))


@functools.lru_cache(maxsize=1)
def _kb_operators() -> list[dict]:
    """KB/operators.json is GITIGNORED. Read it lazily -- see point 2 of the
    module docstring: a module-scope read errors collection on a KB-free runner
    despite the requires_kb mark, because pytest imports before it filters."""
    return json.loads(
        (REPO / "KB" / "operators.json").read_text(encoding="utf-8"))["operators"]


# --------------------------------------------------------------------------
# (c) reconciliation, both directions
# --------------------------------------------------------------------------
def test_reconciliation_is_clean():
    assert G.check_kb_reconciliation(CENSUS, _kb_operators(), GT) == []


def test_the_gap_is_exactly_the_seven_known_holes():
    census_types = {t for names in CENSUS["operators"].values() for t in names}
    resolved, _ = G.resolve_kb_to_census(_kb_operators(), GT)
    assert census_types - resolved == set(G.KNOWN_HOLES)


def test_kb_entries_absent_from_the_census_are_exactly_the_23_fossils():
    _, unresolved = G.resolve_kb_to_census(_kb_operators(), GT)
    assert set(unresolved) == set(G.KNOWN_FOSSILS)


def test_the_owner_arithmetic_closes():
    """663 KB entries - 23 fossils + 7 holes = 647 census, derived rather than
    asserted -- this is the ruling reproduced from the artifacts."""
    resolved, unresolved = G.resolve_kb_to_census(_kb_operators(), GT)
    assert len(_kb_operators()) == 663
    assert len(unresolved) == 23
    assert len(G.KNOWN_HOLES) == 7
    assert len(_kb_operators()) - len(unresolved) + len(G.KNOWN_HOLES) == 647
    assert CENSUS["total_operators"] == 647


# --------------------------------------------------------------------------
# (d) ground truth is a subset of the census
# --------------------------------------------------------------------------
def test_ground_truth_is_a_subset_of_the_census():
    """Post-GT1 this is 0 violations BY CONSTRUCTION -- the generator sources the
    same registry. A violation means the file was hand-edited."""
    assert G.check_gt_subset(CENSUS, GT) == []


# --------------------------------------------------------------------------
# (e) count truth, artifact side
# --------------------------------------------------------------------------
def test_counts_are_clean():
    assert G.check_counts(CENSUS, _kb_operators(), GT) == []


def test_kb_coverage_is_640():
    census_types = {t for names in CENSUS["operators"].values() for t in names}
    resolved, _ = G.resolve_kb_to_census(_kb_operators(), GT)
    assert len(census_types & resolved) == 640


def test_len_kb_operators_is_the_only_honest_entry_count():
    """STANDING TRAP PIN. `len(OperatorRegistry().operators)` is 735, not 663 --
    the registry additionally keys every operator under its build_token alias
    (operator_registry.py:129-139). A count-truth check written against the
    registry would pin a fiction and pass while lying.

    This test exists so that "simplifying" the loader to use the registry turns
    something red instead of silently changing what 663 means.
    """
    from engine.core.operator_registry import OperatorRegistry

    reg = OperatorRegistry()
    assert len(_kb_operators()) == 663
    assert len(reg.operators) > len(_kb_operators()), (
        "the registry is expected to be alias-inflated; if this fails the alias "
        "keying changed and the 663 number must be re-derived deliberately")
    assert reg.get_statistics()["total_operators"] == len(reg.operators)


# --------------------------------------------------------------------------
# NEGATIVES -- red-green, kept in CI forever
# --------------------------------------------------------------------------
def test_an_unlisted_census_only_operator_is_caught():
    c = copy.deepcopy(CENSUS)
    c["operators"]["CHOP"].append("bogusCHOP")
    c["by_family"]["CHOP"] += 1
    c["total_operators"] += 1
    findings = G.check_kb_reconciliation(c, _kb_operators(), GT)
    assert any("bogusCHOP" in f and "not an allowlisted hole" in f for f in findings)


def test_a_phantom_reintroduced_into_the_ground_truth_is_caught():
    g = copy.deepcopy(GT)
    g["operators"]["POP"].append({"name": "Source_POP", "td_create": "sourcePOP"})
    findings = G.check_gt_subset(CENSUS, g)
    assert any("sourcePOP" in f and "not in the census" in f for f in findings)


def test_an_operator_filed_under_the_wrong_family_is_caught():
    g = copy.deepcopy(GT)
    g["operators"]["SOP"].append({"name": "Text_POP", "td_create": "textPOP"})
    findings = G.check_gt_subset(CENSUS, g)
    assert any("different family" in f for f in findings)


def test_a_stale_hole_allowlist_is_caught():
    """Anti-rot. An allowlisted hole that is no longer a hole must be removed, or
    the allowlist accumulates dead entries and the check quietly loses teeth."""
    c = copy.deepcopy(CENSUS)
    c["operators"]["POP"].remove("textPOP")
    c["by_family"]["POP"] -= 1
    c["total_operators"] -= 1
    findings = G.check_kb_reconciliation(c, _kb_operators(), GT)
    assert any("textPOP" in f and "no longer one" in f for f in findings)


def test_a_wrong_count_is_caught():
    c = copy.deepcopy(CENSUS)
    c["total_operators"] = 648
    assert any("647" in f for f in G.check_counts(c, _kb_operators(), GT))


def test_self_test_harness_reports_all_six_mutations_red():
    """The guard's own red-green demonstration, run as a test so the receipts in
    the PR are not a one-off transcript."""
    assert G.self_test(CENSUS, _kb_operators(), GT) == 0

"""Census snapshot integrity (W3 Census Lock, board GT7) -- checks (a) and (b).

HERMETIC: reads only tracked JSON under eval/ground_truth/. No KB, no
TouchDesigner, no network. Deliberately carries NO `requires_kb` mark so it runs
in BOTH ci.yml lanes -- including the hermetic lane, which actively fails if
KB/operators.json is present.

The snapshot is CI's stand-in for a live TouchDesigner: a dump of TD's own
`families[]` class registry at build 099.2025.32820, captured by
scripts/capture_td_census.py. It is the creatable authority behind the owner
ruling (647 operators in TD), so these assertions ARE that ruling, pinned.

The negative tests matter as much as the positive ones. A checker that crashed
on malformed input would "pass" a negative test that only asserted truthiness,
so each negative asserts the SPECIFIC finding text.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import census_guard as G  # noqa: E402

CENSUS = json.loads(
    (REPO / "eval" / "ground_truth" / "td_census.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# (a) identity + self-consistency
# --------------------------------------------------------------------------
def test_snapshot_is_clean():
    assert G.check_snapshot(CENSUS) == []


def test_build_id_is_inside_the_json():
    """Not in sibling prose. operator_types.json's predecessor recorded its TD pin
    only in a README paragraph, so no test could assert it."""
    assert CENSUS["td_build"] == "099.2025.32820"
    assert CENSUS["_schema"] == "td_census/1"
    assert CENSUS["captured_utc"].endswith("Z")


def test_families_seen_is_exactly_the_seven():
    """A new family is a real event -- POP itself was added in a TD release. If an
    eighth appears, a hardcoded 7-family loop would silently omit it while every
    total still looked self-consistent."""
    assert sorted(CENSUS["families_seen"]) == [
        "CHOP", "COMP", "DAT", "MAT", "POP", "SOP", "TOP"]


def test_by_family_cache_agrees_with_the_lists():
    for fam, names in CENSUS["operators"].items():
        assert CENSUS["by_family"][fam] == len(names), fam
    assert CENSUS["total_operators"] == sum(
        len(v) for v in CENSUS["operators"].values())


def test_every_name_ends_in_its_family():
    for fam, names in CENSUS["operators"].items():
        assert [n for n in names if not n.endswith(fam)] == [], fam


def test_no_repr_leak_in_any_name():
    """`families[FAM]` holds CLASSES, not strings. str(c) yields
    "<class 'td.abletonlinkCHOP'>"; only c.__name__ gives a usable token. This
    gotcha silently invalidated two earlier probes -- it must never come back
    looking like data."""
    for fam, names in CENSUS["operators"].items():
        for n in names:
            assert "<" not in n and "'" not in n and " " not in n, (fam, n)


# --------------------------------------------------------------------------
# inheritance chains (captured for W7c's class layer / W4's response dedup)
# --------------------------------------------------------------------------
def test_every_operator_has_a_chain_terminating_at_OP():
    inh = CENSUS["inherits"]
    for fam, names in CENSUS["operators"].items():
        for n in names:
            assert n in inh, n
            assert inh[n][-1] == "OP", (n, inh[n])
            assert fam in inh[n], (n, inh[n])


def test_chain_variety_is_small_and_base_heavy():
    """647 operators share only 12 distinct chains, and no leaf class is shared by
    two operators. So ALL duplicated class surface is inherited from a handful of
    bases -- which is why deduplicating by DEFINING class (not per operator) is
    the lever for tool-response size. Pinned so the shape of that claim is
    visible if TD's hierarchy changes."""
    chains = {tuple(v) for v in CENSUS["inherits"].values()}
    assert len(chains) == 12, sorted(chains)
    assert ("CHOP", "OP") in chains
    assert ("PanelCOMP", "COMP", "OP") in chains


def test_an_operator_class_may_subclass_another_operator_class():
    """pointfileinTOP inherits moviefileinTOP -- operator classes are not a flat
    tier under the family base. Anything walking the hierarchy must expect this."""
    assert CENSUS["inherits"]["pointfileinTOP"] == ["moviefileinTOP", "TOP", "OP"]


# --------------------------------------------------------------------------
# (b) per-family pins -- the owner ruling
# --------------------------------------------------------------------------
def test_family_pins_match_the_owner_ruling():
    assert CENSUS["by_family"] == {
        "CHOP": 165, "TOP": 146, "SOP": 112, "DAT": 71,
        "COMP": 40, "MAT": 13, "POP": 100,
    }
    assert CENSUS["total_operators"] == 647
    assert G.check_family_pins(CENSUS) == []


# --------------------------------------------------------------------------
# NEGATIVES -- the red half of the red-green demonstration, kept in CI forever
# --------------------------------------------------------------------------
def _doctored():
    return copy.deepcopy(CENSUS)


def test_wrong_build_is_caught():
    c = _doctored()
    c["td_build"] = "099.2025.32460"
    assert any("td_build mismatch" in f for f in G.check_snapshot(c))


def test_by_family_desync_is_caught():
    c = _doctored()
    c["operators"]["CHOP"].pop()          # list shrinks, by_family left stale
    assert any("by_family says" in f for f in G.check_snapshot(c))


def test_broken_family_pin_is_caught():
    c = _doctored()
    c["operators"]["CHOP"].pop()
    c["by_family"]["CHOP"] -= 1
    c["total_operators"] -= 1
    assert any("family pin: CHOP" in f for f in G.check_family_pins(c))


def test_an_eighth_family_is_caught():
    c = _doctored()
    c["families_seen"] = sorted(c["families_seen"] + ["XYZ"])
    assert any("families_seen" in f for f in G.check_snapshot(c))


def test_repr_leak_is_caught():
    c = _doctored()
    c["operators"]["CHOP"].append("<class 'td.bogusCHOP'>")
    c["by_family"]["CHOP"] += 1
    assert any("not ending in" in f or "by_family says" in f
               for f in G.check_snapshot(c))


def test_broken_inheritance_chain_is_caught():
    c = _doctored()
    c["inherits"]["abletonlinkCHOP"] = ["CHOP"]        # never reaches OP
    assert any("does not terminate at OP" in f for f in G.check_snapshot(c))

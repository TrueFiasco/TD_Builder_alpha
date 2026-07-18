"""eval/ground_truth/operator_types.json is the census, by construction (board GT1).

HERMETIC: tracked JSON only. No `requires_kb` mark, so it runs in both ci.yml
lanes. One test needs a local TouchDesigner install and self-skips.

This file used to come from a wiki scrape that INVENTED 13 operators and OMITTED
7 real ones. It is now generated from TouchDesigner's own `families[]` registry
by kb_build/gen_operator_types.py, so the phantoms cannot return -- there is no
step left that could synthesise a name. These tests pin that property rather
than the symptom: the shape, the counts, the absence of the specific phantoms,
and the presence of the operators the scrape had missed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import census_guard as G  # noqa: E402

GT_PATH = REPO / "eval" / "ground_truth" / "operator_types.json"
GT = json.loads(GT_PATH.read_text(encoding="utf-8"))
CENSUS = json.loads(
    (REPO / "eval" / "ground_truth" / "td_census.json").read_text(encoding="utf-8"))

FAMILIES = ["CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP"]

# Never real. Absent from the live registry AND from TouchDesigner's shipped
# offline help. The first five were the known set; the census surfaced eight more.
PHANTOMS = [
    "sourcePOP", "attractorPOP", "dragPOP", "collisionPOP", "killPOP",
    "addPOP", "velocityPOP", "analyzeDAT", "fuseSOP", "mirrorSOP",
    "normalsSOP", "scatterSOP", "gradientTOP",
]

# Real operators the scrape omitted. Their absence is why a model asked to
# receive FreeD or Stype camera-tracking data was offered a fossil that cannot
# create, with the working operator invisible.
FORMER_HOLES = [
    "freedinCHOP", "stypeinCHOP", "tcpipDAT", "alembicoutPOP",
    "textPOP", "tracePOP", "triangulatePOP",
]


def _entries():
    for fam in FAMILIES:
        for e in GT["operators"][fam]:
            yield fam, e


def test_totals_match_the_census():
    assert GT["total_operators"] == 647
    assert GT["by_family"] == {
        "CHOP": 165, "TOP": 146, "SOP": 112, "DAT": 71,
        "COMP": 40, "MAT": 13, "POP": 100,
    }


def test_by_family_cache_is_consistent():
    """by_family is denormalised; no code reads it, but the README and humans do."""
    for fam in FAMILIES:
        assert GT["by_family"][fam] == len(GT["operators"][fam]), fam
    assert sum(GT["by_family"].values()) == GT["total_operators"]


def test_entry_schema_is_exactly_name_and_td_create():
    """Three consumers index these two keys (eval/predicates.py,
    eval/build_gate/gate_common.py, kb_build/common.py). Adding a per-entry key
    is a consumer-visible change; adding a TOP-LEVEL key is not."""
    for fam, e in _entries():
        assert set(e) == {"name", "td_create"}, (fam, e)


def test_lists_are_sorted_by_name():
    for fam in FAMILIES:
        names = [e["name"] for e in GT["operators"][fam]]
        assert names == sorted(names), fam


def test_no_phantom_operators():
    tokens = {e["td_create"] for _, e in _entries()}
    normed = {G._norm(e["name"]) for _, e in _entries()}
    for p in PHANTOMS:
        assert p not in tokens, p
        assert G._norm(p) not in normed, p


def test_formerly_missing_operators_are_present():
    tokens = {e["td_create"] for _, e in _entries()}
    for h in FORMER_HOLES:
        assert h in tokens, h


def test_no_wiki_guide_pages():
    """`Write_a_CPlusPlus_CHOP` and friends are tutorial ARTICLES that the scrape's
    filename pattern swept in as operators. reground_operators.py already strips
    them from the KB; nothing stripped them here."""
    for fam, e in _entries():
        assert not e["name"].startswith(("Write_a_", "Write_", "Anatomy_of_")), e


def test_td_create_is_the_OPType_not_the_builder_n_token():
    """THREE namespaces exist and conflating them is a recurring bug:
        td_create / OPType  'abletonlinkCHOP'   <- this file
        builder .n token    'CHOP:ableton'      <- KB build_token
        wiki display name   'Ableton_Link_CHOP' <- this file's `name`
    Pinned with a case where all three differ, so nobody "corrects" it back."""
    chop = {e["name"]: e["td_create"] for e in GT["operators"]["CHOP"]}
    assert chop["Ableton_Link_CHOP"] == "abletonlinkCHOP"
    top = {e["name"]: e["td_create"] for e in GT["operators"]["TOP"]}
    assert top["Composite_TOP"] == "compositeTOP"


def test_every_td_create_is_in_the_census():
    assert G.check_gt_subset(CENSUS, GT) == []


def test_names_survive_normalisation_collisions():
    """The join into the KB is on normalised alphanumerics, so two entries that
    normalise alike would make that lookup ambiguous."""
    seen: dict[str, str] = {}
    for fam, e in _entries():
        key = (fam, G._norm(e["name"]))
        assert key not in seen, (key, seen.get(key), e["name"])
        seen[key] = e["name"]


def test_provenance_block_is_populated():
    p = GT["provenance"]
    assert p["generator"] == "kb_build/gen_operator_types.py"
    assert p["td_build"] == "099.2025.32820"
    assert len(p["census_sha256"]) == 64
    assert "semantics" in GT and "td_create" in GT["semantics"]


def test_provenance_census_sha_matches_the_committed_snapshot():
    import hashlib
    actual = hashlib.sha256(
        (REPO / "eval" / "ground_truth" / "td_census.json").read_bytes()).hexdigest()
    assert GT["provenance"]["census_sha256"] == actual, (
        "operator_types.json was generated from a DIFFERENT census than the one "
        "committed -- regenerate with kb_build/gen_operator_types.py")


HELP_TREE = Path(
    r"C:\Program Files\Derivative\TouchDesigner.2025.32820"
    r"\Samples\Learn\OfflineHelp\https.docs.derivative.ca")


@pytest.mark.skipif(not HELP_TREE.exists(),
                    reason="needs a local TouchDesigner 2025.32820 install "
                           "(the generator's name source); the committed output "
                           "is asserted by the hermetic tests above")
def test_generator_is_deterministic():
    """Same (snapshot, help tree) -> byte-identical output. This is the whole
    reproducibility claim, in one assertion."""
    r = subprocess.run(
        [sys.executable, str(REPO / "kb_build" / "gen_operator_types.py"), "--check"],
        capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"

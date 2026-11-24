"""Operator-name lookups must answer a correct name with the right operator.

Three faults found in a long real-world build; every one returned something that
LOOKED like an answer:

  A. get_operator_info("moviefileinTOP") came back as a shell with no parameters
     while "Movie File In TOP" answered in full. The class-style name missed both
     documentation tables and only the examples graph matched.
  B. find_operator_examples("textTOP") served Texture 3D TOP examples and
     "inTOP" served Point File In TOP, because examples matched by substring.
  C. find_operator_examples for a known operator with no examples returned a bare
     [], which reads the same as a failed search.

Seams under test: UnifiedGraphQuery.get_operator_info and
UnifiedGraphQuery.find_examples_by_operator, the two calls the MCP tools of the
same name delegate to. Needs the fetched KB (operators.json + the enhanced
gpickle), so the whole module is requires_kb.
"""
from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_kb

_REPO = Path(__file__).resolve().parents[2]
_KB = _REPO / "KB"
_SERVER_CORE = _REPO / "MCP" / "server_core"
if str(_SERVER_CORE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CORE))


@pytest.fixture(scope="module")
def kg():
    if not (_KB / "operators.json").exists():
        pytest.fail("KB not fetched: KB/operators.json is missing")
    import unified_graph_query as ugq
    with contextlib.redirect_stdout(io.StringIO()):
        return ugq.UnifiedGraphQuery(
            graphrag_json_path=str(_KB / "graphrag.json"),
            enhanced_graph_path=str(_KB / "knowledge_graph_enhanced.gpickle"),
            enriched_wiki_path=str(_KB / "operators.json"),
        )


def _info(kg, name):
    with contextlib.redirect_stdout(io.StringIO()):
        return kg.get_operator_info(name)


def _examples(kg, name, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return kg.find_examples_by_operator(name, **kw)


def _param_codes(info):
    return set((info or {}).get("wiki_parameters") or {})


# --- A. class-style names reach the documentation --------------------------------
@pytest.mark.parametrize("class_name, spaced", [
    ("moviefileinTOP", "Movie File In TOP"),
    ("keyboardinDAT", "Keyboard In DAT"),
])
def test_class_style_name_returns_same_parameters_as_spaced_name(kg, class_name, spaced):
    spaced_codes = _param_codes(_info(kg, spaced))
    assert len(spaced_codes) > 5, "fixture premise: the spaced name is documented"
    assert _param_codes(_info(kg, class_name)) == spaced_codes


def test_class_style_name_carries_the_documented_summary(kg):
    info = _info(kg, "moviefileinTOP")
    assert info.get("summary"), "class-style lookup lost the operator summary"
    assert "documentation" not in info or info["documentation"] != "missing"


def test_example_only_match_is_marked_not_a_silent_shell(kg):
    # 'audiooscillatorCHOPx' exists only as a node in the examples graph (a typo'd
    # name from a scraped network). Whatever comes back must say the docs are missing.
    info = _info(kg, "audiooscillatorCHOPx")
    if info is None:
        return  # not-found is an honest answer too
    assert not info.get("wiki_parameters")
    assert info.get("documentation") == "missing"
    assert "no documentation" in (info.get("summary") or "").lower()


def test_sweep_every_operator_class_name_matches_spaced_name(kg):
    """Every documented operator: the class-style name (spaces and punctuation
    removed, family kept) returns the same parameter count as the spaced name.
    Before this fix 245 of 663 disagreed (found nothing, or an empty shell)."""
    disagree = []
    for info in kg.enriched_wiki.values():
        name, fam = info["operator_name"], info["family"]
        if not name.endswith(" " + fam):
            continue
        class_name = re.sub(r"[^a-z0-9]", "", name[: -len(fam) - 1].lower()) + fam
        a = _info(kg, name)
        b = _info(kg, class_name)
        na = len((a or {}).get("wiki_parameters") or {}) if a else None
        nb = len((b or {}).get("wiki_parameters") or {}) if b else None
        if na != nb:
            disagree.append((name, class_name, na, nb))
    assert disagree == []


# --- B. examples match the operator exactly ---------------------------------------
def test_textTOP_serves_only_text_top(kg):
    ex = _examples(kg, "textTOP")
    assert isinstance(ex, list) and ex, ex
    assert {e["operator_type"] for e in ex} == {"TOP/textTOP"}


def test_inTOP_serves_only_in_top(kg):
    r = _examples(kg, "inTOP")
    if isinstance(r, dict):   # In TOP has no servable example: the explicit "none"
        assert r["_resolution"] == "no-examples" and r["operator"] == "In TOP"
        return
    assert r and {e["operator_type"] for e in r} == {"TOP/inTOP"}


def test_unknown_needle_falls_back_to_substring_and_says_so(kg):
    # 'texture3' names no operator exactly; the loose fallback still helps, but every
    # served example must be marked as a loose match.
    ex = _examples(kg, "texture3", family="TOP")
    assert isinstance(ex, list) and ex, ex
    assert all(e.get("match") == "substring" for e in ex)
    assert all(e.get("matched_operator") == "texture3dTOP" for e in ex)


def test_exact_match_is_not_marked_loose(kg):
    ex = _examples(kg, "Composite TOP")
    assert isinstance(ex, list) and ex
    assert all("match" not in e for e in ex)


# --- C. known operator, no examples: say so ---------------------------------------
@pytest.mark.parametrize("name, kw", [
    ("glslPOP", {"family": "POP"}),
    ("GLSL POP", {}),
])
def test_known_operator_without_examples_says_so(kg, name, kw):
    r = _examples(kg, name, **kw)
    assert isinstance(r, dict), r
    assert r["_resolution"] == "no-examples"
    assert r["operator"] == "GLSL POP"
    assert r["examples"] == []
    assert "get_operator_info" in r["message"] and "hybrid_search" in r["message"]


def test_unknown_operator_still_returns_empty_list(kg):
    assert _examples(kg, "notarealoperatorTOP") == []


def test_multiword_name_still_serves_examples(kg):
    # Regression guard for F6d (acceptance test_p02e): 'SOP to CHOP' -> soptoCHOP.
    ex = _examples(kg, "SOP to CHOP")
    assert isinstance(ex, list) and ex

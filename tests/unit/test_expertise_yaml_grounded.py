"""Agents/expertise/*.yaml must not name operators that do not exist (W3 Census Lock).

HERMETIC: parses tracked YAML against the tracked census. pyyaml is in
.github/requirements-light.txt, so both ci.yml lanes have it. Unmarked -- no KB.

WHY THIS IS IN SCOPE despite the wave's "no KB content change" bar: that bar
protects the VECTOR STORE, because changing chunk text forces a re-embed. These
files are prompt-side expertise -- unchunked, unembedded, loaded by the agent
layer. Editing them costs one diff and zero embedding compute, so the bar's
rationale does not reach them.

WHAT THE CENSUS EXPOSED HERE. `td_operators.yaml` carried 7 fabricated POP
entries with the giveaway `python_class: ''`, and `td_network_patterns.yaml`
carried a `particle_system` design pattern whose FOUR operator types
(addPOP / sourcePOP / forcePOP / renderPOP) and container (geoCOMP) are all
non-existent -- a wholly fabricated network shipped with `confidence: 0.8`. A
model retrieving it was guaranteed to fail, having already spent a turn planning
around it.

The runtime does pre-validate operator types at build time
(mcp_server.py:2511), so these were caught eventually -- but only after the
model had committed to them. Removing the source is the actual fix.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="pyyaml is in requirements-light")

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

EXPERTISE = REPO / "Agents" / "expertise"
CENSUS = json.loads(
    (REPO / "eval" / "ground_truth" / "td_census.json").read_text(encoding="utf-8"))
CENSUS_TYPES = {t for names in CENSUS["operators"].values() for t in names}

PHANTOM_TOKENS = [
    "sourcePOP", "attractorPOP", "dragPOP", "collisionPOP", "killPOP",
    "addPOP", "velocityPOP", "analyzeDAT", "fuseSOP", "mirrorSOP",
    "normalsSOP", "scatterSOP", "gradientTOP",
]
PHANTOM_NAMES = [
    "Source_POP", "Attractor_POP", "Drag_POP", "Collision_POP", "Kill_POP",
    "Add_POP", "Velocity_POP",
]

# td_file_formats.yaml deliberately RECORDS a failure
# ("dragPOP: Bad node type POP:drag - no ground truth available"). Documenting
# that something does not work is correct and useful; it is not an assertion
# that the operator exists.
DOCUMENTS_FAILURES = {"td_file_formats.yaml"}


def _yaml_files():
    return sorted(p for p in EXPERTISE.glob("*.yaml")
                  if p.name not in DOCUMENTS_FAILURES)


def _walk(node, path="$"):
    """Yield (path, dict) for every mapping in the tree."""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


@pytest.mark.parametrize("path", _yaml_files(), ids=lambda p: p.name)
def test_no_phantom_operator_named(path):
    text = path.read_text(encoding="utf-8")
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for tok in PHANTOM_TOKENS + PHANTOM_NAMES:
            if tok in line:
                hits.append(f"{path.name}:{i}: {line.strip()[:100]}")
    assert hits == [], (
        "these operators do not exist in TouchDesigner 099.2025.32820 "
        "(absent from the live families[] registry AND from the shipped offline "
        "help):\n  " + "\n  ".join(hits))


def test_every_operator_reference_in_network_patterns_is_creatable():
    """Every place a pattern NAMES an operator must name a real one.

    Two shapes carry operator names, and the first version of this test only
    covered one of them:

      * NODE SPECS -- a mapping with both `name` and `type` (a hierarchy entry)
      * PARAMETER SPECS -- a mapping with an `operator:` key (a parameters entry)

    Covering only node specs let `sliderCHOP` and `choptosopSOP` survive in
    `parameters:` blocks of the very patterns whose hierarchies had just been
    respelled -- internally contradictory, and structurally invisible to the
    guard. Widened so that cannot recur.

    The bare key `type` is deliberately NOT swept on its own: it also carries
    connection kinds ('wire', 'expression'), path kinds ('relative sibling') and
    GLSL template kinds ('fragment_shader'), none of which are operators.

    SCOPED TO `design_patterns`, which holds concrete buildable specs. The
    sibling `workflows` section is prose guidance and names operators
    conversationally -- `operator: "analyze"`, `"beat"`, `"geometry"`, and
    chains like "particle SOP" / "popnet" -- so holding it to OPType spelling
    would be a category error. It is the same split that governed deleting
    `design_patterns.particle_system` (fabricated, concrete, unbuildable) while
    leaving `workflows.particle_system` (prose, self-labelled
    `validated: false`) alone.
    """
    doc = yaml.safe_load(
        (EXPERTISE / "td_network_patterns.yaml").read_text(encoding="utf-8"))
    bad = []
    for path, node in _walk(doc.get("design_patterns") or {}, "$.design_patterns"):
        # node spec: {name, type, ...}
        if "name" in node and "type" in node:
            t = node.get("type")
            if isinstance(t, str) and t and t not in CENSUS_TYPES:
                bad.append(f"{path}: name={node['name']!r} type={t!r}")
        # parameter spec: {operator, param, value, ...}
        op = node.get("operator")
        if isinstance(op, str) and op and op not in CENSUS_TYPES:
            bad.append(f"{path}: operator={op!r} param={node.get('param')!r}")
    assert bad == [], (
        "these references name operators that are not creatable in the census -- "
        "a pattern containing them cannot build:\n  " + "\n  ".join(bad))


def test_no_phantom_spelling_survives_anywhere_in_network_patterns():
    """Belt-and-braces over the structured check above: a raw text sweep for the
    specific wrong spellings this wave corrected, so they cannot reappear in a
    shape the parser-based test does not model (prose `cause:`/`fix:` guidance
    named `geoCOMP` too, and that teaches the wrong token just as effectively)."""
    text = (EXPERTISE / "td_network_patterns.yaml").read_text(encoding="utf-8")
    wrong = ["sliderCHOP", "buttonCHOP", "choptosopSOP", "geoCOMP",
             "addPOP", "sourcePOP", "forcePOP", "renderPOP"]
    hits = [f"{w} (line {i})"
            for i, line in enumerate(text.splitlines(), 1)
            for w in wrong if w in line]
    assert hits == [], "corrected spellings reappeared:\n  " + "\n  ".join(hits)


def test_phantom_free_files_still_reference_real_operators():
    """Guard against the removal being over-broad: the POP family must still be
    described. A test that passes because the content is gone is not a pass."""
    text = (EXPERTISE / "td_operators.yaml").read_text(encoding="utf-8")
    for real in ["Noise_POP", "Transform_POP", "Null_POP"]:
        assert real in text, f"{real} should still be documented"

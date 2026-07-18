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


def test_every_node_spec_type_in_network_patterns_is_creatable():
    """Broadest-value assertion here: it caught all four fabricated types in the
    particle_system pattern at once, plus four more wrong tokens in unrelated
    patterns, without anyone knowing to look for them.

    Scoped to NODE SPECS -- mappings carrying both `name` and `type`, which is the
    shape of a hierarchy entry. The key `type` is also used for connection kinds
    ('wire', 'expression'), path kinds ('relative sibling') and GLSL template
    kinds ('fragment_shader'); none of those are operators.
    """
    doc = yaml.safe_load(
        (EXPERTISE / "td_network_patterns.yaml").read_text(encoding="utf-8"))
    bad = []
    for path, node in _walk(doc):
        if "name" not in node or "type" not in node:
            continue
        t = node.get("type")
        if isinstance(t, str) and t and t not in CENSUS_TYPES:
            bad.append(f"{path}: name={node['name']!r} type={t!r}")
    assert bad == [], (
        "these node specs name operators that are not creatable in the census -- "
        "a pattern containing them cannot build:\n  " + "\n  ".join(bad))


def test_phantom_free_files_still_reference_real_operators():
    """Guard against the removal being over-broad: the POP family must still be
    described. A test that passes because the content is gone is not a pass."""
    text = (EXPERTISE / "td_operators.yaml").read_text(encoding="utf-8")
    for real in ["Noise_POP", "Transform_POP", "Null_POP"]:
        assert real in text, f"{real} should still be documented"

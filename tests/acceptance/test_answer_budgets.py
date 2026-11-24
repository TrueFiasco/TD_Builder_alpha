"""Answers a session can read: default answers stay under one size budget.

In a long real-world build some tool answers were too big to read, so the call
was spent and nothing was learned: `get_operator_info` without `compact` (up to
~43 KB), `expand_toe_file` in `summary` mode (~800 KB on one line), and
`get_expert_prompt` (~59 KB). Each default answer must fit the budget and, when
there is more, say how to get it.

The budget is pinned here as a literal (24 KB), independent of the server's own
constant, so a quiet change to the constant fails these tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

BUDGET = 24 * 1024  # bytes of the tool's text answer

# The heaviest operators in the KB (full form 63–86 KB each).
HEAVY_OPS = ["PBR MAT", "Text COMP", "Geo Text COMP", "Phong MAT", "Geometry COMP"]


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


@pytest.mark.parametrize("op", HEAVY_OPS)
def test_get_operator_info_default_fits_budget_and_names_the_rest(probe, op):
    r = probe.call("get_operator_info", {"operator_name": op})
    assert r.ok, r.text[:300]
    assert _size(r.text) < BUDGET, f"{op}: {_size(r.text)} bytes"
    data = json.loads(r.text)
    assert data["name"] == op
    assert data["parameters"], "the default still lists every parameter name"
    how = json.dumps(data)
    assert "get_parameter_detail" in how and "compact=false" in how


def test_get_operator_info_compact_false_still_returns_everything(probe):
    r = probe.call("get_operator_info", {"operator_name": "PBR MAT", "compact": False})
    assert r.ok, r.text[:300]
    data = json.loads(r.text)
    assert "wiki_parameters" in data
    assert _size(r.text) > BUDGET  # the explicit ask is not cut


# --------------------------------------------------------------------------
# expand_toe_file(mode='summary')
# --------------------------------------------------------------------------

_DESIGN = {
    "operators": (
        [{"name": "scene", "type": "base", "family": "COMP"}]
        + [{"name": f"noise{i}", "type": "noise", "family": "CHOP", "parent": "scene",
            "parameters": {"amp": 2.5, "period": 3, "seed": i, "rough": 0.7}}
           for i in range(1, 21)]
        + [{"name": "null1", "type": "null", "family": "CHOP", "parent": "scene"},
           {"name": "out1", "type": "null", "family": "TOP"}]
    ),
    "connections": [{"from": "scene/noise1", "to": "scene/null1"}],
}


def _built_dir(probe, tmp_path):
    b = probe.call("td_build_project", {"design": _DESIGN, "project_name": "budget_probe",
                                        "mode": "tox", "output_dir": str(tmp_path)})
    dirs = list(tmp_path.glob("*.dir"))
    if not dirs:
        pytest.skip(f"offline build left no .dir to expand: {b.text[:200]}")
    return dirs[0]


def test_expand_summary_over_budget_is_an_overview_that_says_how(probe, tmp_path, monkeypatch):
    d = _built_dir(probe, tmp_path)
    full = probe.call("expand_toe_file", {"toe_path": str(d)}).json()["data"]
    assert "operators" in full and "_truncated" not in full     # under budget: unchanged
    # Shrink the budget below this small network's summary to drive the over-budget path.
    size = len(json.dumps(full).encode("utf-8"))
    assert size > 4000, size
    monkeypatch.setattr(probe.mod, "ANSWER_MAX_BYTES", 1024 + 2500)
    r = probe.call("expand_toe_file", {"toe_path": str(d)})
    env = r.json()
    assert env["ok"] is True and env["meta"].get("truncated") is True
    data = env["data"]
    assert data["node_count"] == full["node_count"]
    assert "operators" not in data and data["component_tree"]
    assert "component=" in data["_truncated"]["hint"]
    comp = next(c["path"] for c in data["component_tree"] if c["path"].endswith("/scene"))
    one = probe.call("expand_toe_file", {"toe_path": str(d), "component": comp}).json()
    assert one["ok"] is True and one["data"]["component"] == comp
    # Still over this tiny budget: operators listed in full detail until it runs out.
    listed = one["data"]["operators"]
    assert listed and all(o["path"].startswith(comp) for o in listed)
    assert len(listed) + one["data"]["_truncated"]["operators_omitted"] == 22
    # A single operator's path opens just that operator.
    op = probe.call("expand_toe_file", {"toe_path": str(d),
                                        "component": comp + "/noise7"}).json()["data"]
    assert [o["path"] for o in op["operators"]] == [comp + "/noise7"]
    assert op["operators"][0]["params"]


def test_expand_component_errors(probe, tmp_path):
    d = _built_dir(probe, tmp_path)
    r = probe.call("expand_toe_file", {"toe_path": str(d), "component": "/no/such"})
    assert not r.ok and "component_tree" in r.text
    r = probe.call("expand_toe_file", {"toe_path": str(d), "mode": "full", "component": "/x"})
    assert not r.ok and "summary" in r.text


def _td_file(rel):
    from paths import resolve_td_tool
    exe = resolve_td_tool("toeexpand")
    if not exe:
        pytest.skip("toeexpand (TouchDesigner) not installed")
    f = Path(exe).resolve().parents[1] / rel
    if not f.exists():
        pytest.skip(f"{rel} not in this TouchDesigner install")
    return f


def test_expand_summary_of_a_large_real_file_fits(probe):
    # TouchDesigner's own UI component: ~8,300 operators; the old summary was ~4.7 MB.
    f = _td_file(Path("Config") / "System" / "ui.tox")
    r = probe.call("expand_toe_file", {"toe_path": str(f)})
    assert r.ok, r.text[:300]
    assert _size(r.text) < BUDGET
    data = r.json()["data"]
    assert data["node_count"] > 5000 and data["component_tree"]
    big = max(data["component_tree"][1:], key=lambda c: c["operators"])["path"]
    r2 = probe.call("expand_toe_file", {"toe_path": str(f), "component": big})
    assert r2.ok and _size(r2.text) < BUDGET


# --------------------------------------------------------------------------
# get_expert_prompt
# --------------------------------------------------------------------------

def test_get_expert_prompt_default_fits_and_names_the_next_part(probe):
    r = probe.call("get_expert_prompt", {"expert_name": "td_designer", "phase": "build"})
    assert r.ok, r.text[:200]
    assert _size(r.text) < BUDGET
    assert "part=2" in r.text.split("\n", 1)[0]

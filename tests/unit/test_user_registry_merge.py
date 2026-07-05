"""User component registry merge (BUG-3 rider, B1).

The loader seam (_load_palette_components) merges ~/.td_builder/user_components.json
(dir overridable via TD_BUILDER_USER_DIR) over the shipped KB/palette_components.json —
user wins per component name. Review R1 requirements pinned here:
  - cache keyed on (path, mtime_ns, size) of BOTH files: a registration made between
    two builds in ONE process is visible without any restart/reset;
  - the merge builds a FRESH dict — the cached shipped spec is never mutated in place;
  - a malformed/absent user file never fails a build (shipped-only fallback);
  - offline-stamped user entries get the strict name-authority wiring policy
    end-to-end through a real build.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "MCP" / "server_core")):
    if p not in sys.path:
        sys.path.insert(0, p)

from meta_agentic.execution import toe_builder_bridge as bridge  # noqa: E402
from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402

# The shipped registry is committed; skip cleanly if a stripped checkout lacks it.
# The builds themselves resolve types against the fetched KB/operators.json.
_SHIPPED = REPO / "KB" / "palette_components.json"
pytestmark = [
    pytest.mark.requires_kb,
    pytest.mark.skipif(not _SHIPPED.is_file(),
                       reason="shipped KB/palette_components.json not present"),
]


@pytest.fixture()
def user_dir(tmp_path, monkeypatch):
    """Point the user registry at a temp dir and reset the loader cache."""
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    saved = (bridge._PALETTE_COMPONENTS_CACHE, bridge._PALETTE_COMPONENTS_CACHE_KEY)
    bridge._PALETTE_COMPONENTS_CACHE = None
    bridge._PALETTE_COMPONENTS_CACHE_KEY = None
    yield tmp_path
    bridge._PALETTE_COMPONENTS_CACHE, bridge._PALETTE_COMPONENTS_CACHE_KEY = saved


def _write_user(user_dir: Path, components: dict):
    (user_dir / "user_components.json").write_text(
        json.dumps({"components": components}), encoding="utf-8")


def _entry(outs, harvest=None):
    e = {
        "source": "project", "tox_path": "tox/x.tox", "wrapper": False,
        "inner_type": "COMP:base", "inputs": [],
        "outputs": [{"index": i, "out_op": n, "family": "CHOP"}
                    for i, n in enumerate(outs)],
    }
    if harvest:
        e["harvest"] = {"method": harvest}
    return e


def test_user_entry_merges_over_shipped(user_dir):
    _write_user(user_dir, {"myUserThing": _entry(["out1"])})
    spec = bridge._load_palette_components()
    assert "myUserThing" in spec["components"]
    assert "bloom" in spec["components"], "shipped entries must survive the merge"


def test_user_wins_collision_and_shipped_not_mutated(user_dir):
    override = _entry(["customOut"])
    override["tox_path"] = "OVERRIDDEN.tox"
    _write_user(user_dir, {"bloom": override})
    spec = bridge._load_palette_components()
    assert spec["components"]["bloom"]["tox_path"] == "OVERRIDDEN.tox"

    # remove the user file -> reload must return the PRISTINE shipped entry
    (user_dir / "user_components.json").unlink()
    spec2 = bridge._load_palette_components()
    assert spec2["components"]["bloom"]["tox_path"] != "OVERRIDDEN.tox"


def test_registration_between_builds_is_seen_r1(user_dir):
    _write_user(user_dir, {"first": _entry(["out1"])})
    spec = bridge._load_palette_components()
    assert "first" in spec["components"] and "second" not in spec["components"]

    # an external process registers another component: same path, new content
    _write_user(user_dir, {"first": _entry(["out1"]),
                           "second": _entry(["out1"])})
    spec2 = bridge._load_palette_components()
    assert "second" in spec2["components"], \
        "mtime/size-keyed cache must pick up a registration without a restart"


def test_absent_user_file_is_shipped_only(user_dir):
    spec = bridge._load_palette_components()
    assert "bloom" in spec["components"]


def test_malformed_user_file_warns_and_falls_back(user_dir):
    (user_dir / "user_components.json").write_text("not json {{{", encoding="utf-8")
    spec = bridge._load_palette_components()  # must not raise
    assert "bloom" in spec["components"]

    # wrong shape (no "components" object) is equally non-fatal
    (user_dir / "user_components.json").write_text(json.dumps({"oops": 1}),
                                                   encoding="utf-8")
    bridge._PALETTE_COMPONENTS_CACHE = None
    bridge._PALETTE_COMPONENTS_CACHE_KEY = None
    spec = bridge._load_palette_components()
    assert "bloom" in spec["components"]


def test_offline_stamped_user_entry_gets_strict_policy(user_dir, tmp_path):
    _write_user(user_dir, {"twoOutUser": _entry(["out_a", "out_b"],
                                                harvest="offline_manifest")})
    design = {
        "operators": [
            {"name": "gen", "palette": "twoOutUser", "position": [0, 0]},
            {"name": "nullA", "type": "null", "family": "CHOP", "position": [200, 0]},
        ],
        "connections": [{"from": "gen", "to": "nullA"}],
    }
    with pytest.raises(ValueError, match="out_a"):
        ToxBuilder(tmp_path / "b", verbose=False).build_tox(design, "strict")


def test_malformed_user_entry_skipped_not_crashing_g5(user_dir, tmp_path):
    # G5: a hand-edited entry with the WRONG shape (inputs/outputs as bare strings, not
    # {index,in_op,family} dicts) used to throw an uncaught AttributeError from the
    # index-sort at resolution time, FAILING the build — contradicting the loader's
    # "a user registry must never fail a build" contract. Now skipped at merge with a
    # warning; a valid sibling entry is unaffected.
    (user_dir / "user_components.json").write_text(json.dumps({"components": {
        "Hand": {"source": "project", "tox_path": "x.tox",
                 "inputs": ["in1"], "outputs": ["out1"],   # <- bare strings, malformed
                 "harvest": {"method": "offline_manifest"}},
        "Good": _entry(["out1"], harvest="offline_manifest"),
    }}), encoding="utf-8")

    spec = bridge._load_palette_components()               # must not raise
    assert "Hand" not in spec["components"], "malformed entry skipped at merge"
    assert "Good" in spec["components"], "valid sibling survives"
    assert "bloom" in spec["components"], "shipped registry intact"

    # a design referencing the SKIPPED entry degrades to the clean unknown-component
    # error (actionable), NOT an AttributeError crash.
    bad = {"operators": [{"name": "n", "palette": "Hand", "position": [0, 0]}]}
    with pytest.raises(ValueError, match="Unknown palette component 'Hand'"):
        ToxBuilder(tmp_path / "bad", verbose=False).build_tox(bad, "g5bad")

    # the valid sibling still builds (registry not poisoned by the bad entry).
    ok = {"operators": [{"name": "n", "palette": "Good", "position": [0, 0]}]}
    ToxBuilder(tmp_path / "ok", verbose=False).build_tox(ok, "g5ok")

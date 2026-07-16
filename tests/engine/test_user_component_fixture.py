"""W7 Δ7 — hermetic end-to-end over the committed own-content fixtures.

tests/fixtures/user_components/ holds two HAND-AUTHORED expanded component dirs
(own content, deliberately NOT a Derivative palette comp — license):

  pulseglow.tox.dir — plain (non-wrapper) comp; .cparm defines a float par
      (min/max/default), a menu par (token+label pairs), a string par with an
      expression default, and a pulse; its .parm overrides Rate (4 -> 12), so
      the EFFECTIVE default must come from .parm.
  wrapglow.tox.dir  — Derivative-style wrapper (connector-less root + icon +
      same-name inner COMP); the .cparm sits on the INNER comp, which is where
      the parser must read it from.

manifest_from_tox accepts an expanded .dir directly (no TD binary, no
toecollapse), so this whole file is hermetic -> CI-blocking in both lanes.
Also covers the bridge seam: an engine-written registry entry merges with
index_authority=False (the harvest stamp drives the strict NAME-authority
wiring policy — the BUG-3 class guard).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "MCP" / "server_core")):
    if p not in sys.path:
        sys.path.insert(0, p)

from kb_build import user_components as uc  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures" / "user_components"


# ---------------------------------------------------------------------------
# parse_component — skeleton fidelity
# ---------------------------------------------------------------------------
def test_pulseglow_skeleton_and_effective_defaults():
    sk = uc.parse_component(FIXTURES / "pulseglow.tox.dir")
    man = sk["manifest"]
    assert man["wrapper"] is False and man["interface_path"] == "/pulseglow"
    assert [i["name"] for i in man["inputs"]] == ["in1"]
    assert [o["name"] for o in man["outputs"]] == ["out1"]
    assert sk["inner_type"] == "COMP:base" and sk["subcompname"] is None
    # interface-scoped inventory: everything under /pulseglow, NOT the comp itself
    assert sk["contained_operators"] == ["CHOP:in", "CHOP:lfo", "CHOP:out"]
    assert sk["parse_warnings"] == []

    by = {p["name"]: p for p in sk["custom_parameters"]}
    # float par: .cparm default is 4, but the saved .parm carries Rate=12 —
    # the EFFECTIVE default must be the .parm override (Δ7)
    assert by["Rate"]["default"] == 12
    assert by["Rate"]["min"] == 0.1 and by["Rate"]["max"] == 30
    assert by["Rate"]["type_class"] == "number"
    # menu par: tokens VERBATIM, in file order, with labels
    assert [m["token"] for m in by["Wavetype"]["menu"]] == ["sine", "square", "saw"]
    assert by["Wavetype"]["menu"][0]["label"] == "Sine"
    assert by["Wavetype"]["default"] == "sine"
    # string par with an expression default
    assert by["Source"]["default"] == "app.samplesFolder + '/Audio/track.wav'"
    assert by["Source"]["type_class"] == "string"
    # pulse: no default ever
    assert by["Help"]["type_class"] == "pulse" and "default" not in by["Help"]


def test_wrapglow_wrapper_pars_come_from_inner_comp():
    sk = uc.parse_component(FIXTURES / "wrapglow.tox.dir")
    man = sk["manifest"]
    assert man["wrapper"] is True
    assert man["interface_path"] == "/wrapglow/wrapglow"
    assert sk["subcompname"] == "wrapglow"
    # icon plumbing excluded from the interface-scoped inventory
    assert sk["contained_operators"] == ["TOP:in", "TOP:out", "TOP:ramp"]
    by = {p["name"]: p for p in sk["custom_parameters"]}
    assert by["Amount"]["default"] == 0.5
    assert [m["token"] for m in by["Mode"]["menu"]] == ["soft", "hard"]


# ---------------------------------------------------------------------------
# entry + chunk text — registry field, io-chunk content, description round-trip
# ---------------------------------------------------------------------------
def test_entry_and_io_chunk_from_fixture():
    sk = uc.parse_component(FIXTURES / "pulseglow.tox.dir")
    entry, warns = uc.build_entry(
        sk, source="project", tox_path="C:/proj/pulseglow.tox",
        summary="LFO-driven pulse generator with wave shaping.",
        use_cases=["pulsing control signals"],
        parameter_descriptions={"Rate": "pulses per second"})
    assert warns == []
    assert entry["harvest"]["method"] == "offline_manifest"
    assert [p["name"] for p in entry["custom_parameters"]] == \
        ["Rate", "Wavetype", "Source", "Help"]

    rows = uc.component_block_rows("pulseglow", entry)
    io = rows[2]["text"]
    assert "Rate" in io and "default 12" in io and "range 0.1..30" in io
    assert "menu tokens: sine|square|saw" in io
    assert "pulses per second" in io          # authored description round-trip
    # registry round-trip keeps the field intact
    blob = json.loads(json.dumps(entry))
    assert blob["custom_parameters"][0]["default"] == 12


# ---------------------------------------------------------------------------
# bridge seam — engine-written entry merges with index_authority=False
# ---------------------------------------------------------------------------
def test_bridge_merges_engine_entry_as_name_authority(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    sk = uc.parse_component(FIXTURES / "pulseglow.tox.dir")
    entry, _ = uc.build_entry(sk, source="project",
                              tox_path="C:/proj/pulseglow.tox", summary="s")
    uc.upsert_registry_entry("pulseglow", entry)

    from meta_agentic.execution import toe_builder_bridge as bridge
    saved = (bridge._PALETTE_COMPONENTS_CACHE, bridge._PALETTE_COMPONENTS_CACHE_KEY)
    bridge._PALETTE_COMPONENTS_CACHE = None
    bridge._PALETTE_COMPONENTS_CACHE_KEY = None
    try:
        merged = bridge._load_palette_components()["components"]
        assert "pulseglow" in merged, "engine entry must merge over the shipped registry"
        # _palette_io_entry reads only module state — callable without a
        # constructed bridge instance.
        io = bridge.ToeBuilderBridge._palette_io_entry(None, "pulseglow")
        assert io["index_authority"] is False, \
            "offline_manifest stamp must select the strict NAME-authority policy"
        assert io["origin"] == "user_registry"
        assert [o["name"] for o in io["outputs"]] == ["out1"]
    finally:
        bridge._PALETTE_COMPONENTS_CACHE, bridge._PALETTE_COMPONENTS_CACHE_KEY = saved

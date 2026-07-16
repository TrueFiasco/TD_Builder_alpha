"""W7 T1/T7 — register_component through the ALREADY-CONSTRUCTED server adapter.

LOCAL kb-full lane only (boots the real in-process server + full KB warmup).
T1 (BLOCKER A): prepare → author → commit through call_tool, then hybrid_search
through the SAME server with NO restart finds the comp — `retrievable:true` is
earned by the reload, not asserted by hope. Δ1 assertions: user hits carry
score_kind and NEVER parameter_names/parameters/parameters_capped (palette
parity). T7: a partial-KB install gets the structured kb_partial envelope.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FIXTURE_DIR = REPO / "tests" / "fixtures" / "user_components"

SUMMARY = ("LFO-driven pulse generator producing rhythmic control channels "
           "with selectable waveform shaping.")


def test_t1_in_session_register_then_search(probe, tmp_path, monkeypatch):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    fixture = str(FIXTURE_DIR / "pulseglow.tox.dir")

    # prepare: skeleton comes back for authoring (incl. Δ7 custom parameters)
    r = probe.call("register_component",
                   {"specs": [{"tox_path": fixture}], "prepare": True})
    assert r.ok, r.text[:400]
    prep = r.json()["prepared"][0]
    assert prep["ok"] and prep["name"] == "pulseglow"
    par_names = [p["name"] for p in prep["custom_parameters"]]
    assert par_names == ["Rate", "Wavetype", "Source", "Help"]
    assert prep["shadows_shipped"] is False

    # commit with the authored semantics
    r2 = probe.call("register_component", {"specs": [{
        "tox_path": fixture, "name": "pulseglow", "summary": SUMMARY,
        "use_cases": ["pulsing control signals", "LFO modulation"],
        "parameter_descriptions": {"Rate": "pulses per second"},
    }]})
    assert r2.ok, r2.text[:400]
    res = r2.json()["results"][0]
    assert res["ok"] is True, res
    assert res["retrievable"] is True, "reload must succeed on the live adapter"
    assert res["chunk_count"] == 3
    assert res["shadows_shipped"] is False
    assert res["operator_count"] == 4          # echoed for prepare/commit mismatch

    # unified record + store exist under the pinned dir
    reg = json.loads((tmp_path / "user_components.json").read_text("utf-8"))
    entry = reg["components"]["pulseglow"]
    assert entry["harvest"]["method"] == "offline_manifest"
    assert entry["summary"] == SUMMARY
    assert [p["name"] for p in entry["custom_parameters"]] == par_names
    assert (tmp_path / "user_index" / "manifest.json").is_file()

    # SAME server, NO restart: capability-phrase retrieval
    r3 = probe.call("hybrid_search",
                    {"query": "LFO-driven pulse generator component", "n_results": 8})
    assert r3.ok, r3.text[:400]
    env = r3.json()
    assert env["_retrieval_backend"]["user_store_active"] is True
    hits = [h for h in env["semantic_results"]
            if h["metadata"].get("license_tier") == "user"
            and h["metadata"].get("name") == "pulseglow"]
    assert hits, "registered comp not retrievable through the live adapter"
    h = hits[0]
    assert "score_kind" in h                              # Δ1: honesty field present
    for k in ("parameter_names", "parameters", "parameters_capped"):
        assert k not in h, f"user hits must skip param hydration (palette parity): {k}"

    # exact-name query travels the direct-injection path
    r4 = probe.call("hybrid_search", {"query": "pulseglow", "n_results": 8})
    assert any(h["metadata"].get("name") == "pulseglow"
               and h["metadata"].get("license_tier") == "user"
               for h in r4.json()["semantic_results"]), \
        "exact-name recall failed through the server"


def test_t1b_save_to_palette_flow(probe, tmp_path, monkeypatch):
    """Palette-saved add: copy into <user palette>/TD_Builder/, palette-relative
    registry entry (source 'user'), overwrite policy with `replaced` reporting.
    Needs a real .tox (toecollapse) — self-skips without the TD binary."""
    from paths import resolve_td_tool
    if resolve_td_tool("toeexpand") is None or resolve_td_tool("toecollapse") is None:
        pytest.skip("TouchDesigner tools not installed")
    from meta_agentic.execution.tox_builder import ToxBuilder

    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path / "user"))
    pal = tmp_path / "palette"
    monkeypatch.setenv("TD_USER_PALETTE_DIR", str(pal))
    ops = [{"name": "in1", "type": "in", "family": "CHOP", "position": [0, 0]},
           {"name": "out1", "type": "out", "family": "CHOP", "position": [200, 0]}]
    tox = ToxBuilder(tmp_path, verbose=False).build_tox({"operators": ops}, "palComp")
    assert tox is not None and tox.exists()

    spec = {"tox_path": str(tox), "summary": "Palette-saved fixture comp."}
    r = probe.call("register_component",
                   {"specs": [spec], "save_to_palette": True})
    assert r.ok, r.text[:400]
    res = r.json()["results"][0]
    assert res["ok"] and res["retrievable"] is True
    assert "replaced" not in res
    assert (pal / "TD_Builder" / "palComp.tox").is_file()
    reg = json.loads(
        (tmp_path / "user" / "user_components.json").read_text("utf-8"))
    entry = reg["components"]["palComp"]
    assert entry["source"] == "user"
    assert entry["tox_path"] == "TD_Builder/palComp.tox"   # palette-RELATIVE (G6)

    # collision refused without overwrite; overwrite reports `replaced`
    r2 = probe.call("register_component",
                    {"specs": [spec], "save_to_palette": True})
    assert r2.json()["results"][0]["error"]["kind"] == "palette_collision"
    r3 = probe.call("register_component",
                    {"specs": [spec], "save_to_palette": True, "overwrite": True})
    res3 = r3.json()["results"][0]
    assert res3["ok"] and res3["replaced"].endswith("palComp.tox")
    assert res3["replaced_registry_entry"] is True


def test_t7_partial_kb_gets_structured_envelope(probe):
    mod = probe.mod
    saved = (mod._KB_STATUS, mod._KB_REASON)
    mod._KB_STATUS, mod._KB_REASON = "partial", "semantic search unavailable (test)"
    try:
        r = probe.call("register_component",
                       {"specs": [{"tox_path": "C:/nowhere/x.tox", "summary": "s"}]})
        d = r.json()
        assert d["ok"] is False
        assert d["error"]["status"] == "kb_partial", d
    finally:
        mod._KB_STATUS, mod._KB_REASON = saved

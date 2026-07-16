#!/usr/bin/env python3
r"""capture_baseline merge semantics (B1, PR #37 post-merge audit) — pure,
KB-free, no model.

Pins the contract: a scenario-SUBSET --capture-baseline MERGES with the
committed baseline.json — non-swept records reused verbatim, the
gate/aspirational/unmeasurable/incomplete sets recomputed over the merged map,
_provenance carried forward with a mixed-snapshot disclosure appended — instead
of silently erasing every non-swept scenario (the pre-fix behavior dropped the
baseline from 14 scenarios / 7-gate to 3 / 3 and blinded Lane R's --compare).
A capture that covers every prior scenario stays a fresh overwrite.

Run: py -3.11 -m pytest eval/agent_eval/tests/test_capture_merge.py -q
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AGENT_EVAL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_EVAL_DIR))

import run_agent_eval as R  # noqa: E402
import score as score_mod   # noqa: E402


# ---------------------------------------------------------------------------
# Harness — everything on tmp_path, no repo files touched
# ---------------------------------------------------------------------------
def _trials(sid, verdicts):
    return [score_mod.ScoreResult(scenario_id=sid, lane="model", verdict=v,
                                  advisory={"cost_usd": 0.1})
            for v in verdicts]


def _record(version="1.0", gate=True, verdicts=("PASS",) * 5, **extra):
    verdicts = list(verdicts)
    scored = [v for v in verdicts if v in ("PASS", "FAIL")]
    rec = {
        "version": version, "gate_eligible": gate, "n": len(verdicts),
        "verdicts": verdicts,
        "pass_rate": (sum(1 for v in scored if v == "PASS") / len(scored))
        if scored else None,
        "failure_fingerprints": {}, "advisory_median": {"cost_usd": 0.5},
    }
    rec.update(extra)
    return rec


def _env(tmp_path, monkeypatch, scenario_versions: dict, prior=None):
    """Point run_agent_eval's module paths at tmp_path and materialize the
    scenario files (id -> version) plus an optional prior baseline.json."""
    sdir = tmp_path / "scenarios"
    sdir.mkdir()
    for sid, version in scenario_versions.items():
        (sdir / f"{sid}.json").write_text(json.dumps(
            {"id": sid, "version": version, "gate": True,
             "prompt": "p", "expect": {}}), encoding="utf-8")
    monkeypatch.setattr(R, "SCENARIOS_DIR", sdir)
    monkeypatch.setattr(R, "BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(R, "stage_dir", lambda: tmp_path / "stage")
    if prior is not None:
        (tmp_path / "baseline.json").write_text(
            json.dumps(prior, indent=2, sort_keys=True), encoding="utf-8")


def _capture(results: dict, scenarios: list, identity=None):
    args = argparse.Namespace(n=5, config="guided")
    sweep = {"lane": "model", "run_id": "test-run", "results": results,
             "identity": identity if identity is not None
             else {"kb_sha": "kb-new"}}
    R.capture_baseline(args, {}, sweep, scenarios)
    return json.loads(R.BASELINE_PATH.read_text(encoding="utf-8"))


def _sc(sid, version="1.0", gate=True):
    return {"id": sid, "version": version, "gate": gate}


# ---------------------------------------------------------------------------
# The B1 contract: subset capture preserves non-swept scenarios
# ---------------------------------------------------------------------------
def test_subset_capture_preserves_nonswept_records(tmp_path, monkeypatch):
    prior = {
        "captured_with": {"lane": "model", "n": 5, "config": "guided",
                          "run_id": "prior-run"},
        "identity": {"kb_sha": "kb-old"},
        "_provenance": {"original_note": "hand-written history"},
        "scenarios": {
            "s01_a": _record(verdicts=("PASS",) * 5),               # gate
            "s02_b": _record(verdicts=("PASS",) * 4 + ("FAIL",)),   # aspirational
            "s03_c": _record(verdicts=("PASS",) * 5),               # gate
            "s04_d": _record(verdicts=("ERROR",) * 5),              # unmeasurable
        },
        "gate_set": ["s01_a", "s03_c"], "aspirational_set": ["s02_b"],
        "unmeasurable_set": ["s04_d"],
    }
    _env(tmp_path, monkeypatch,
         {"s01_a": "1.0", "s02_b": "1.0", "s03_c": "1.0", "s04_d": "1.0"},
         prior=prior)

    out = _capture({"s02_b": _trials("s02_b", ["PASS"] * 5)}, [_sc("s02_b")])

    assert sorted(out["scenarios"]) == ["s01_a", "s02_b", "s03_c", "s04_d"], \
        "subset capture erased non-swept scenarios (B1)"
    for sid in ("s01_a", "s03_c", "s04_d"):
        assert out["scenarios"][sid] == prior["scenarios"][sid], \
            f"reused record {sid} was not carried verbatim"
    assert out["scenarios"]["s02_b"]["pass_rate"] == 1.0, \
        "the swept scenario's record was not refreshed"
    # sets recomputed over the MERGED map: s02 promoted, reused members kept
    assert out["gate_set"] == ["s01_a", "s02_b", "s03_c"]
    assert out["aspirational_set"] == []
    assert out["unmeasurable_set"] == ["s04_d"]
    assert out["incomplete_set"] == []


def test_subset_capture_writes_disclosure_and_carries_provenance(
        tmp_path, monkeypatch):
    prior = {
        "captured_with": {"lane": "model", "n": 5, "config": "guided",
                          "run_id": "prior-run"},
        "identity": {"kb_sha": "kb-old", "tool_inventory_hash": "t-old"},
        "_provenance": {"original_note": "hand-written history"},
        "scenarios": {"s01_a": _record(), "s02_b": _record()},
        "gate_set": ["s01_a", "s02_b"], "aspirational_set": [],
        "unmeasurable_set": [],
    }
    _env(tmp_path, monkeypatch, {"s01_a": "1.0", "s02_b": "1.0"}, prior=prior)

    out = _capture({"s02_b": _trials("s02_b", ["PASS"] * 5)}, [_sc("s02_b")],
                   identity={"kb_sha": "kb-old", "tool_inventory_hash": "t-new"})

    assert out["captured_with"]["partial"] is True
    assert out["captured_with"]["recaptured"] == ["s02_b"]
    assert out["identity"]["tool_inventory_hash"] == "t-new", \
        "merged file must stamp the CURRENT sweep identity"
    prov = out["_provenance"]
    assert prov["original_note"] == "hand-written history", \
        "prior _provenance dropped on merge"
    note = prov["partial_recapture_test-run"]
    assert note["recaptured"] == ["s02_b"]
    assert note["reused_verbatim"] == ["s01_a"]
    assert note["reused_from_capture"]["run_id"] == "prior-run"
    assert note["identity_drift_vs_prior"] == {
        "tool_inventory_hash": {"prior": "t-old", "current": "t-new"}}, \
        "identity drift between reused and fresh records must be disclosed"


def test_full_capture_stays_fresh_overwrite(tmp_path, monkeypatch, capsys):
    prior = {
        "captured_with": {"run_id": "prior-run"},
        "identity": {"kb_sha": "kb-old"},
        "_provenance": {"original_note": "old history"},
        "scenarios": {"s01_a": _record(verdicts=("FAIL",) * 5)},
        "gate_set": [], "aspirational_set": ["s01_a"], "unmeasurable_set": [],
    }
    _env(tmp_path, monkeypatch, {"s01_a": "1.0"}, prior=prior)

    out = _capture({"s01_a": _trials("s01_a", ["PASS"] * 5)}, [_sc("s01_a")])

    assert "_provenance" not in out, \
        "a capture covering every prior scenario is a FRESH baseline"
    assert "partial" not in out["captured_with"]
    assert out["gate_set"] == ["s01_a"]
    assert "prior _provenance NOT carried forward" in capsys.readouterr().out


def test_no_prior_baseline_is_fresh(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch, {"s01_a": "1.0", "s02_b": "1.0"}, prior=None)
    out = _capture({"s01_a": _trials("s01_a", ["PASS"] * 5)}, [_sc("s01_a")])
    assert sorted(out["scenarios"]) == ["s01_a"]
    assert "_provenance" not in out and "partial" not in out["captured_with"]


# ---------------------------------------------------------------------------
# Merge edge cases
# ---------------------------------------------------------------------------
def test_reused_record_version_drift_warns(tmp_path, monkeypatch, capsys):
    prior = {
        "captured_with": {"run_id": "prior-run"}, "identity": {},
        "scenarios": {"s01_a": _record(version="1.0"), "s02_b": _record()},
        "gate_set": ["s01_a", "s02_b"], "aspirational_set": [],
        "unmeasurable_set": [],
    }
    # s01's scenario FILE was edited (version bumped) since the prior capture
    _env(tmp_path, monkeypatch, {"s01_a": "2.0", "s02_b": "1.0"}, prior=prior)

    out = _capture({"s02_b": _trials("s02_b", ["PASS"] * 5)}, [_sc("s02_b")])

    assert out["scenarios"]["s01_a"] == prior["scenarios"]["s01_a"]
    printed = capsys.readouterr().out
    assert "version drift" in printed and "s01_a" in printed, \
        "an edited scenario reused verbatim must warn that it needs recapture"


def test_stale_record_for_deleted_scenario_is_dropped(tmp_path, monkeypatch):
    prior = {
        "captured_with": {"run_id": "prior-run"}, "identity": {},
        "scenarios": {"s01_a": _record(), "s99_gone": _record()},
        "gate_set": ["s01_a", "s99_gone"], "aspirational_set": [],
        "unmeasurable_set": [],
    }
    _env(tmp_path, monkeypatch, {"s01_a": "1.0"}, prior=prior)  # no s99 file

    out = _capture({"s01_a": _trials("s01_a", ["PASS"] * 5)}, [_sc("s01_a")])

    assert "s99_gone" not in out["scenarios"]
    assert out["_provenance"]["partial_recapture_test-run"][
        "dropped_stale_records"] == ["s99_gone"]


def test_reused_incomplete_checkpoint_record_stays_incomplete(
        tmp_path, monkeypatch):
    prior = {
        "captured_with": {"run_id": "prior-run"}, "identity": {},
        "scenarios": {
            "s01_a": _record(),
            "s02_b": _record(verdicts=("PASS",) * 2, complete=False,
                             n_captured=2, n_expected=5),
        },
        "gate_set": ["s01_a"], "aspirational_set": [],
        "unmeasurable_set": [], "incomplete_set": ["s02_b"],
    }
    _env(tmp_path, monkeypatch,
         {"s01_a": "1.0", "s02_b": "1.0", "s03_c": "1.0"}, prior=prior)

    out = _capture({"s03_c": _trials("s03_c", ["PASS"] * 5)}, [_sc("s03_c")])

    assert out["incomplete_set"] == ["s02_b"], \
        "a reused partial-checkpoint record must not earn a set it never completed"
    assert out["gate_set"] == ["s01_a", "s03_c"]


def test_allskip_recapture_replaces_but_warns(tmp_path, monkeypatch, capsys):
    prior = {
        "captured_with": {"run_id": "prior-run"}, "identity": {},
        "scenarios": {"s01_a": _record(), "s02_b": _record()},
        "gate_set": ["s01_a", "s02_b"], "aspirational_set": [],
        "unmeasurable_set": [],
    }
    _env(tmp_path, monkeypatch, {"s01_a": "1.0", "s02_b": "1.0"}, prior=prior)

    out = _capture({"s01_a": _trials("s01_a", ["SKIP"] * 5)}, [_sc("s01_a")])

    # explicitly swept -> the SKIP record wins (all-SKIP joins no set) ...
    assert out["scenarios"]["s01_a"]["verdicts"] == ["SKIP"] * 5
    assert out["gate_set"] == ["s02_b"]
    # ... but replacing real measurements with nothing is flagged loudly
    printed = capsys.readouterr().out
    assert "scored nothing" in printed and "s01_a" in printed

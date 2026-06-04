"""#3 Validator accuracy.

Positives = known-good builder networks (should validate clean). Negatives =
mutators.py corruptions, each labelled with the stage that *should* catch it.
Runs every case through the real td_validate tool (5-stage pipeline).

Per-case score (0..1):
  positive: 1.0 iff valid==True (no false flag)
  negative: 1.0 iff invalid AND flagged by an expected stage; 0.5 if invalid
            but only by the wrong stage; 0.0 if it slipped through (a miss)
Aggregate metrics: false_flag_rate, miss_rate, right_stage_rate.
"""
from __future__ import annotations

from measure import mutators
from measure.harness import CaseScore, emit


def _validate(probe, net):
    r = probe.call("td_validate", {"network": net, "verbose": True})
    d = r.json()
    if not isinstance(d, dict) or "valid" not in d:
        return None, [], r.text[:100]
    stages = {e.get("stage") for e in d.get("errors", []) if isinstance(e, dict)}
    return bool(d["valid"]), stages, ""


def run_validator(probe, promote: bool = False) -> dict:
    scores: list[CaseScore] = []
    false_flags = misses = neg_total = pos_total = right_stage = 0

    for name, net in mutators.good_cases():
        pos_total += 1
        valid, err_stages, perr = _validate(probe, net)
        if valid is None:
            scores.append(CaseScore(name, 0.0, "positive",
                          {"false_flag": 1.0}, f"validate error: {perr}"))
            false_flags += 1
            continue
        if valid:
            scores.append(CaseScore(name, 1.0, "positive", {"false_flag": 0.0},
                          "clean (correct)"))
        else:
            false_flags += 1
            scores.append(CaseScore(name, 0.0, "positive", {"false_flag": 1.0},
                          f"FALSE FLAG by stages {sorted(err_stages)}"))

    for name, net, expected in mutators.negative_cases():
        neg_total += 1
        cat = name.split(":", 1)[1]
        valid, err_stages, perr = _validate(probe, net)
        if valid is None:
            scores.append(CaseScore(name, 0.0, cat, {"miss": 1.0},
                          f"validate error: {perr}"))
            misses += 1
            continue
        if valid:
            misses += 1
            scores.append(CaseScore(name, 0.0, cat, {"miss": 1.0},
                          f"MISS — expected {sorted(expected)} to flag it"))
        elif err_stages & expected:
            right_stage += 1
            scores.append(CaseScore(name, 1.0, cat, {"miss": 0.0},
                          f"caught by {sorted(err_stages & expected)} (correct)"))
        else:
            scores.append(CaseScore(name, 0.5, cat, {"miss": 0.0},
                          f"caught but by {sorted(err_stages)}, "
                          f"expected {sorted(expected)}"))

    extra = {
        "false_flag_rate": round(false_flags / pos_total, 4) if pos_total else 0.0,
        "miss_rate": round(misses / neg_total, 4) if neg_total else 0.0,
        "right_stage_rate": round(right_stage / neg_total, 4) if neg_total else 0.0,
    }
    return emit("validator_accuracy", scores, promote=promote, extra=extra)


def test_validator_accuracy(probe, promote):
    report = run_validator(probe, promote)
    assert report["n"] > 0, "no validator cases ran"

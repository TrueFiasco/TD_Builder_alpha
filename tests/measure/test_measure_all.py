"""Everything at once: run all deterministic targets + crosscut in one pass and
print one consolidated delta table. Agent quality (#4) only runs when opted in.

    pytest tests/measure/test_measure_all.py -s
    pytest tests/measure/test_measure_all.py -s --promote   # set new baselines
"""
from __future__ import annotations

import os

from measure.test_builder_params import run_builder
from measure.test_crosscut import run_crosscut
from measure.test_retrieval import run_retrieval
from measure.test_validator import run_validator


def test_measure_all(probe, promote):
    reports = {
        "validator_accuracy": run_validator(probe, promote),
        "crosscut": run_crosscut(probe, promote),
        "retrieval_recall": run_retrieval(probe, promote),
        "builder_param_acceptance": run_builder(probe, promote),
    }

    if os.environ.get("RUN_NL_EVAL") and os.environ.get("ANTHROPIC_API_KEY"):
        from measure.test_agent_quality import run_agent_quality
        reports["agent_quality"] = run_agent_quality(probe, promote)

    print("\n================ CONSOLIDATED ================")
    print(f"{'target':<28} {'n':>4} {'score':>8}  baseline-delta")
    for name, rep in reports.items():
        print(f"{name:<28} {rep['n']:>4} {rep['score_mean']:>8.4f}")
    print("=============================================")

    for name, rep in reports.items():
        assert rep["n"] > 0, f"{name} produced no cases"

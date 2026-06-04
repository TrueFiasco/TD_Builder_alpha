"""#4 Agent output quality (opt-in: RUN_NL_EVAL=1 + ANTHROPIC_API_KEY).

Reuses the existing H17 harness (unified_system/eval/prompt_eval.py): runs the
(prompt, expected_network) YAML cases through the V2 strategy, parses the
produced .toe.dir, and scores operator/connection recall against the answer
key. We add the missing baseline/delta/worst-case layer on top.

Real Claude API calls (~$0.05 + 2-5 min per case) — skipped by default.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

from measure._server import ALPHA_ROOT
from measure.harness import CaseScore, emit

PROMPT_EVAL = ALPHA_ROOT / "unified_system" / "eval" / "prompt_eval.py"

pytestmark = pytest.mark.mode2


def _load_prompt_eval():
    spec = importlib.util.spec_from_file_location("h17_prompt_eval", str(PROMPT_EVAL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_agent_quality(probe, promote: bool = False) -> dict:
    pe = _load_prompt_eval()
    cases = pe.discover_cases()
    scores: list[CaseScore] = []
    for case in cases:
        res = pe.run_case(case, pe.v2_runner)
        op_r = float(res.operator_recall or 0.0)
        cn_r = float(res.connection_recall or 0.0)
        score = round((op_r + cn_r) / 2.0, 4)
        detail = (f"err: {res.error[:70]}" if res.error
                  else f"missing {res.missing_operators[:3]}")
        scores.append(CaseScore(
            case.name, score, case.tier,
            {"operator_recall": round(op_r, 4),
             "connection_recall": round(cn_r, 4),
             "duration_s": round(res.duration_seconds, 2)},
            detail,
        ))
    return emit("agent_quality", scores, promote=promote)


def test_agent_quality(probe, promote, has_api_key):
    if not os.environ.get("RUN_NL_EVAL"):
        pytest.skip("agent quality is opt-in: set RUN_NL_EVAL=1 (real API cost)")
    if not has_api_key:
        pytest.skip("ANTHROPIC_API_KEY not set (Mode 2 required)")
    report = run_agent_quality(probe, promote)
    assert report["n"] > 0, "no eval cases discovered"

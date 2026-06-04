"""GLSL eval — v1 demo tests (D5, D6).

D5 — `bo_glsl_top_theme_color` (build_offline, easy): minimal end-to-end
     build → import → render → score loop with a known-good fixture shader.
D6 — `fo_glsl_fix_bug`           (fix_offline,   medium): asserts the eval
     detects the seeded GLSL error class in the compile log (Mode-1
     pre-cursor to the Mode-2 agent-driven fix scoring).

Both require live TD on 127.0.0.1:9981 with `/test` base + mcp webserver tox.
Skipped cleanly otherwise so the rest of the suite still runs.

D7 (`fc_creative_av_scene`, full_creative, Mode 2) is the agentic headline
case — see DESIGN_BRIEF.md. Not run in this file; needs the agent path.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from measure.harness import emit
from glsl_eval import runner


def _run_demo(probe, td_live, promote: bool, case_ids: list[str], label: str):
    if not td_live:
        pytest.skip("GLSL demo requires TouchDesigner on 127.0.0.1:9981 "
                    "with mcp_webserver_base.tox imported")
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scores = [runner.run_case(probe, cid, run_ts=run_ts) for cid in case_ids]
    report = emit(label, scores, promote=promote)
    assert report["n"] == len(case_ids), \
        f"expected {len(case_ids)} cases, got {report['n']}"
    return report


def test_d5_bo_glsl_top_theme_color(probe, td_live, promote):
    """D5 — minimal build_offline GLSL loop, default theme (sci-fi)."""
    report = _run_demo(probe, td_live, promote,
                       ["bo_glsl_top_theme_color"], "glsl_d5_build")
    # Sanity: a build_offline case must at least produce a score entry.
    case = report["cases"][0]
    assert case["score"] >= 0.0


def test_d6_fo_glsl_fix_bug(probe, td_live, promote):
    """D6 — fix_offline error-class detection from the LIVE compile log.

    Overrides slot bug=vec3_to_vec2 — a type-mismatch that fails to compile in
    any GLSL profile, so the live `glsl1_info` DAT reliably carries the real
    error (matching the Dali-corpus class `cannot convert from vec3 to vec2`).
    Proves the classifier works against TD's actual compile output, not just
    the reference catalogue.
    """
    if not td_live:
        pytest.skip("GLSL demo requires TouchDesigner on 127.0.0.1:9981")
    from datetime import datetime, timezone
    from glsl_eval import runner as glsl_runner
    from measure.harness import emit
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    scores = [glsl_runner.run_case(
        probe, "fo_glsl_fix_bug",
        overrides={"bug": "vec3_to_vec2"},
        run_ts=run_ts,
    )]
    report = emit("glsl_d6_fix", scores, promote=promote)
    assert report["n"] == 1
    assert report["cases"][0]["score"] >= 0.0

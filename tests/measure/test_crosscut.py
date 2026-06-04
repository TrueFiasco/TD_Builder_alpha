"""Cross-cutting cost / latency / output-quality — every tool is improvable.

Runs a representative set of calls and records response tokens, latency, and
an actionability/well-formedness score. Makes "contract" tools
(get_server_info, the Mode-2 envelope, the live-fallback message) carry a
number you can drive: fewer tokens, lower latency, more actionable errors.
"""
from __future__ import annotations

from measure.harness import CaseScore, emit
from measure.judge import rubric_score

SMOKE_NET = {
    "meta": {"project_name": "xc", "mode": "toe"},
    "operators": [
        {"name": "noise1", "family": "CHOP", "type": "noise"},
        {"name": "null1", "family": "CHOP", "type": "null",
         "inputs": [{"index": 0, "src": "noise1"}]},
    ],
}

_ACTIONABLE_RUBRIC = (
    "A good error/fallback message names the cause and a concrete remedy: "
    "the port 9981, importing mcp_webserver_base.tox, setting ANTHROPIC_API_KEY, "
    "or pointing at docs/MODES.md."
)


def _score(r) -> tuple[float, str]:
    if r.ok:
        return (1.0, "well-formed") if r.data is not None else (0.5, "ok, non-JSON")
    fuzzy, why = rubric_score(_ACTIONABLE_RUBRIC, r.text)
    return round((r.actionability + fuzzy) / 2.0, 4), f"err; {why[:60]}"


def run_crosscut(probe, promote: bool = False) -> dict:
    scores: list[CaseScore] = []

    calls = [
        ("get_server_info", {}, "contract"),
        ("td_validate", {"network": SMOKE_NET, "verbose": True}, "offline"),
        ("td_convert", {"network": SMOKE_NET, "source_layer": "builder",
                        "target_layer": "canonical"}, "offline"),
        ("spawn_engineer", {"engineer_type": "knowledge_validator",
                            "task_spec": {}}, "mode2_guard"),
        ("get_td_info", {}, "live_fallback"),
    ]
    for name, args, group in calls:
        r = probe.call(name, args)
        sc, why = _score(r)
        scores.append(CaseScore(
            name, sc, group,
            {"resp_tokens": float(r.resp_tokens),
             "latency_ms": round(r.latency_s * 1000, 1),
             "actionability": round(r.actionability, 4),
             "cost_usd": r.cost_usd},
            f"{r.resp_tokens}tok {r.latency_s*1000:.0f}ms; {why}",
        ))

    # compact-vs-full bloat signal on a tool that supports compact=true
    full = probe.call("get_operator_info", {"operator_name": "Noise CHOP"})
    comp = probe.call("get_operator_info",
                      {"operator_name": "Noise CHOP", "compact": True})
    if full.ok and comp.ok:
        saved = full.resp_tokens - comp.resp_tokens
        ratio = round(comp.resp_tokens / full.resp_tokens, 4) if full.resp_tokens else 1.0
        scores.append(CaseScore(
            "get_operator_info:compact_delta", round(1.0 - ratio, 4), "bloat",
            {"full_tokens": float(full.resp_tokens),
             "compact_tokens": float(comp.resp_tokens),
             "tokens_saved": float(saved)},
            f"compact saves {saved} tok ({ratio:.0%} of full)",
        ))

    return emit("crosscut", scores, promote=promote)


def test_crosscut(probe, promote):
    report = run_crosscut(probe, promote)
    assert report["n"] > 0

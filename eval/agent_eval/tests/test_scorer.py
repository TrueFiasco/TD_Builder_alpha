#!/usr/bin/env python3
r"""Seeded scorer tests — the design's acceptance criteria 4/5 + §12 R-3, proven
with synthetic transcripts + hand-built artifacts (no KB, no model, no CLI).

Run: py -3.11 -m pytest eval/agent_eval/tests/test_scorer.py -q
Needs the fetched KB: the artifacts these tests score are built with the real
ToxBuilder, which grounds op types against KB/operators.json. Runs on CI's
kb-full lane (KB present), not the hermetic (KB-free) lane.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

AGENT_EVAL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_EVAL_DIR))

import score as S  # noqa: E402


# ---------------------------------------------------------------------------
# Transcript builders — emit stream-json event lines like claude -p --output-format
# ---------------------------------------------------------------------------
def _init(connected=True):
    servers = [{"name": "td-builder", "status": "connected" if connected else "failed"}]
    return json.dumps({"type": "system", "subtype": "init", "mcp_servers": servers})


def _assistant_tool(tool, tid, inp, text=""):
    content = []
    if text:
        content.append({"type": "text", "text": text})
    content.append({"type": "tool_use", "id": tid,
                    "name": S.MCP_PREFIX + tool, "input": inp})
    return json.dumps({"type": "assistant",
                       "message": {"model": "claude-sonnet-x", "content": content}})


def _assistant_text(text):
    return json.dumps({"type": "assistant",
                       "message": {"model": "claude-sonnet-x",
                                   "content": [{"type": "text", "text": text}]}})


def _assistant_builtin(tool, tid, inp):
    return json.dumps({"type": "assistant", "message": {"model": "m", "content": [
        {"type": "tool_use", "id": tid, "name": tool, "input": inp}]}})


def _tool_result(tid, payload, is_error=False):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid,
         "content": [{"type": "text", "text": text}], "is_error": is_error}]}})


def _result(num_turns=3, cost=0.4):
    return json.dumps({"type": "result", "subtype": "success",
                       "num_turns": num_turns, "total_cost_usd": cost,
                       "duration_ms": 1234})


def _run(lines):
    return S.parse_stream_json(lines)


# ---------------------------------------------------------------------------
# A minimal real build, so artifact assertions have something on disk
# ---------------------------------------------------------------------------
def _build_lfo_chain(work: Path):
    for p in (str(AGENT_EVAL_DIR.parents[1]),
              str(AGENT_EVAL_DIR.parents[1] / "MCP" / "server_core"),
              str(AGENT_EVAL_DIR.parents[1] / "MCP" / "engine")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from meta_agentic.execution.tox_builder import ToxBuilder
    design = {
        "operators": [
            {"type": "lfo", "family": "CHOP", "name": "lfo1", "position": [0, 0]},
            {"type": "math", "family": "CHOP", "name": "math1", "position": [150, 0]},
            {"type": "null", "family": "CHOP", "name": "null1", "position": [300, 0]},
            {"type": "constant", "family": "CHOP", "name": "target1", "position": [300, 150],
             "parameters": {"value0": {"expr": "op('null1')['chan1']"}, "name0": "d"}},
        ],
        "connections": [{"from": "lfo1", "to": "math1"}, {"from": "math1", "to": "null1"}],
    }
    ToxBuilder(work, verbose=False).build_tox(design, "lfo_chain")
    return design


def _build_noise_null(work: Path, project_name: str, mode: str):
    for p in (str(AGENT_EVAL_DIR.parents[1]),
              str(AGENT_EVAL_DIR.parents[1] / "MCP" / "server_core"),
              str(AGENT_EVAL_DIR.parents[1] / "MCP" / "engine")):
        if p not in sys.path:
            sys.path.insert(0, p)
    design = {"operators": [
        {"type": "noise", "family": "TOP", "name": "noise1", "position": [0, 0]},
        {"type": "null", "family": "TOP", "name": "null1", "position": [150, 0]}],
        "connections": [{"from": "noise1", "to": "null1"}]}
    if mode == "toe":
        from meta_agentic.execution.toe_builder_bridge import ToeBuilderBridge
        return ToeBuilderBridge(work, verbose=False).build_from_design(dict(design), project_name)
    from meta_agentic.execution.tox_builder import ToxBuilder
    return ToxBuilder(work, verbose=False).build_tox(dict(design), project_name)


S01 = json.loads((AGENT_EVAL_DIR / "scenarios" / "s01_chop_chain.json").read_text("utf-8"))
S09 = json.loads((AGENT_EVAL_DIR / "scenarios" / "s09_abstention.json").read_text("utf-8"))
S12 = json.loads((AGENT_EVAL_DIR / "scenarios" / "s12_dual_mode.json").read_text("utf-8"))


def _s01_no_validate():
    """s01 with validate:null so these KB-free tests don't touch the engine."""
    sc = json.loads(json.dumps(S01))
    sc["expect"]["validate"] = None
    return sc


# ===========================================================================
# R-3 — connection barrier: quiet-no-server run is ERROR, never FAIL
# ===========================================================================
def test_r3_no_connection_evidence_is_error(tmp_path):
    # normal exit, complete transcript, ZERO tool calls (the proven 2.1.19x race)
    run = _run([_assistant_text("Sure, I built it!"), _result(num_turns=1)])
    res = S.score_scenario(_s01_no_validate(), run, tmp_path / "work")
    assert res.verdict == "ERROR", res.to_json()
    assert "connection" in (res.error or "").lower()


def test_r3_init_event_is_positive_evidence(tmp_path):
    # server connected via init event but the model still built nothing -> the
    # barrier is satisfied, so this is a real FAIL (missing artifact), not ERROR
    run = _run([_init(connected=True), _assistant_text("done"), _result()])
    res = S.score_scenario(_s01_no_validate(), run, tmp_path / "work")
    assert res.verdict == "FAIL", res.to_json()
    assert res.error is None


def test_r3_successful_tool_result_is_evidence(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    design = _build_lfo_chain(work)
    lines = [
        _assistant_tool("hybrid_search", "t1", {"query": "lfo"}),
        _tool_result("t1", {"results": []}),
        _assistant_tool("td_build_project", "t2",
                        {"design": design, "output_dir": work.as_posix()}),
        _tool_result("t2", {"status": "SUCCESS", "output_file": "lfo_chain.tox"}),
        _assistant_tool("td_validate", "t3", {"network": design}),
        _tool_result("t3", {"valid": True}),
        _result(),
    ]
    # no init event at all — connection proven purely by the successful results
    res = S.score_scenario(_s01_no_validate(), _run(lines), work)
    assert res.verdict == "PASS", res.to_json()


# ===========================================================================
# Criterion 4 — scorer independence: agent claims success over a BROKEN
# artifact -> FAIL (verdict from files, never from self-report)
# ===========================================================================
def test_c4_success_claim_over_missing_artifact_fails(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    # agent SAYS success and even returns a SUCCESS envelope, but nothing on disk
    lines = [
        _init(),
        _assistant_tool("td_build_project", "t1",
                        {"design": {"operators": []}, "output_dir": work.as_posix()},
                        text="Built and validated successfully!"),
        _tool_result("t1", {"status": "SUCCESS", "output_file": "lfo_chain.tox"}),
        _result(),
    ]
    res = S.score_scenario(_s01_no_validate(), _run(lines), work)
    assert res.verdict == "FAIL"
    assert any("artifact.tox" in f["assertion"] for f in res.failures), res.failures


def test_c4_validation_is_out_of_band_not_self_report(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    # build a REAL artifact but feed a design that FAILS the 5-stage pipeline;
    # the agent's own td_validate claims valid. Out-of-band validation must
    # still FAIL the scenario (criterion 4 + §4.2).
    _build_lfo_chain(work)
    broken = {"operators": [{"type": "nonexistentop", "family": "CHOP", "name": "x"}],
              "connections": []}
    lines = [
        _init(),
        _assistant_tool("td_build_project", "t1",
                        {"design": broken, "output_dir": work.as_posix()}),
        _tool_result("t1", {"status": "SUCCESS", "output_file": "lfo_chain.tox"}),
        _assistant_tool("td_validate", "t2", {"network": broken}),
        _tool_result("t2", {"valid": True, "total_errors": 0}),  # agent LIES
        _result(),
    ]
    sc = json.loads(json.dumps(S01))  # keep validate:PASS
    res = S.score_scenario(sc, _run(lines), work)
    assert res.verdict == "FAIL"
    assert any("validate.PASS" in f["assertion"] for f in res.failures), res.failures


# ===========================================================================
# Criterion 5 — discipline: writes outside the run dir / disallowed tool
# ===========================================================================
def test_c5_missing_output_dir_fails_discipline(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    _build_lfo_chain(work)
    lines = [
        _init(),
        _assistant_tool("td_build_project", "t1", {"design": {"operators": []}}),  # NO output_dir
        _tool_result("t1", {"status": "SUCCESS", "output_file": "lfo_chain.tox"}),
        _result(),
    ]
    res = S.score_scenario(_s01_no_validate(), _run(lines), work)
    assert res.verdict == "FAIL"
    assert any("writes_confined" in f["assertion"] for f in res.failures), res.failures


def test_c5_output_dir_escaping_run_dir_fails(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    _build_lfo_chain(work)
    escape = (tmp_path / "elsewhere").as_posix()
    lines = [
        _init(),
        _assistant_tool("td_build_project", "t1",
                        {"design": {"operators": []}, "output_dir": escape}),
        _tool_result("t1", {"status": "SUCCESS"}),
        _result(),
    ]
    res = S.score_scenario(_s01_no_validate(), _run(lines), work)
    assert res.verdict == "FAIL"
    assert any("writes_confined" in f["assertion"] for f in res.failures)


def test_c5_disallowed_builtin_tool_leak_is_error(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    # a leaked built-in (Read of KB off disk) despite --disallowedTools is a
    # HARNESS-CONFIG fault -> ERROR, not a model FAIL
    lines = [
        _init(),
        _assistant_builtin("Read", "b1", {"file_path": "KB/operators.json"}),
        _tool_result("b1", "file contents..."),
        _result(),
    ]
    res = S.score_scenario(_s01_no_validate(), _run(lines), work)
    assert res.verdict == "ERROR"
    assert "Read" in (res.error or "")


# ===========================================================================
# Runner-fault taxonomy — timeout/spend books ERROR, never FAIL
# ===========================================================================
def test_runner_error_is_error_not_fail(tmp_path):
    run = _run([_init(), _assistant_text("...")])
    run.runner_error = "timeout after 900s (wall-clock budget)"
    res = S.score_scenario(_s01_no_validate(), run, tmp_path / "work")
    assert res.verdict == "ERROR"
    assert "timeout" in res.error


# ===========================================================================
# SKIP — declared precondition absent
# ===========================================================================
def test_skip_precondition(tmp_path):
    res = S.score_scenario(_s01_no_validate(), _run([_init(), _result()]),
                           tmp_path / "work", skip_reason="requires bloom.tox: absent")
    assert res.verdict == "SKIP"


# ===========================================================================
# Positive abstention — s09: KB searched, nothing built, honest answer -> PASS
# ===========================================================================
def test_s09_abstention_pass(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    answer = ("TouchDesigner has no native Penrose or aperiodic-tiling operator. "
              "Real routes: a Script SOP generating the geometry, a precomputed "
              "table + instancing, or a GLSL approach.")
    lines = [
        _init(),
        _assistant_tool("hybrid_search", "t1", {"query": "penrose tiling"}),
        _tool_result("t1", {"results": []}),
        _assistant_text(answer),
        _result(),
    ]
    res = S.score_scenario(S09, _run(lines), work)
    assert res.verdict == "PASS", res.to_json()


def test_s09_fabricated_operator_fails(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    lines = [
        _init(),
        _assistant_tool("hybrid_search", "t1", {"query": "penrose"}),
        _tool_result("t1", {"results": []}),
        _assistant_text("Yes — use the penroseSOP operator to generate the tiling."),
        _result(),
    ]
    res = S.score_scenario(S09, _run(lines), work)
    assert res.verdict == "FAIL"
    assert any("must_not_match" in f["assertion"] for f in res.failures)


def test_s09_building_anyway_fails(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    lines = [
        _init(),
        _assistant_tool("hybrid_search", "t1", {"query": "penrose"}),
        _tool_result("t1", {"results": []}),
        _assistant_tool("td_build_project", "t2",
                        {"design": {"operators": []}, "output_dir": work.as_posix()}),
        _tool_result("t2", {"status": "SUCCESS"}),
        _assistant_text("Here are the routes: script SOP, instancing, glsl."),
        _result(),
    ]
    res = S.score_scenario(S09, _run(lines), work)
    assert res.verdict == "FAIL"
    assert any("tool_not_called" in f["assertion"] for f in res.failures)


# ===========================================================================
# R-2 — kb_lookup_any is the exact 10-tool enumeration, not "the N"
# ===========================================================================
def test_r2_kb_lookup_any_enumeration():
    assert len(S.KB_LOOKUP_TOOLS) == 10
    assert "get_expert_prompt" not in S.KB_LOOKUP_TOOLS
    assert "get_server_info" not in S.KB_LOOKUP_TOOLS
    assert set(S.TRACE_ALIASES["kb_lookup_any"]) == set(S.KB_LOOKUP_TOOLS)
    assert len(S.OFFLINE_TOOLS) == 17


def test_r2_alias_matches_any_member(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    _build_lfo_chain(work)
    design = {"operators": [], "connections": []}
    # uses find_parameter_usage (a KB tool that is NOT hybrid_search) — the
    # alias must still satisfy trace.tool_called[kb_lookup_any]
    lines = [
        _init(),
        _assistant_tool("find_parameter_usage", "t1", {"operator_type": "lfo"}),
        _tool_result("t1", {"usages": []}),
        _assistant_tool("td_build_project", "t2",
                        {"design": design, "output_dir": work.as_posix()}),
        _tool_result("t2", {"status": "SUCCESS", "output_file": "lfo_chain.tox"}),
        _assistant_tool("td_validate", "t3", {"network": design}),
        _tool_result("t3", {"valid": True}),
        _result(),
    ]
    res = S.score_scenario(_s01_no_validate(), _run(lines), work)
    # the kb_lookup_any and call_order trace assertions must be satisfied
    assert not any("kb_lookup_any" in f["assertion"] for f in res.failures), res.failures


# ===========================================================================
# R-1 — turns are SCORED from the transcript (there is no --max-turns)
# ===========================================================================
def test_r1_turns_scored_from_transcript():
    run = _run([_init(), _assistant_text("a"), _assistant_text("b"), _result(num_turns=7)])
    assert run.num_turns == 7           # from the result event
    assert S._advisory(run)["turns"] == 7


def test_r1_turns_counted_when_result_event_truncated():
    # truncated stream (no result event): turns still countable post-hoc
    run = _run([_init(), _assistant_text("a"), _assistant_text("b")])
    assert run.num_turns == 2


def test_r1_truncated_turns_count_messages_not_text_parts():
    # BUG-7: an assistant message with TWO text parts is ONE turn, not two
    two_part = json.dumps({"type": "assistant", "message": {"model": "m", "content": [
        {"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}})
    run = _run([_init(), two_part])  # no result event
    assert run.num_turns == 1


# ===========================================================================
# Review regression guards (adversarial pass, 2026-07-04)
# ===========================================================================
def test_bug1_combine_verdict_error_never_flips_wash_to_fail():
    from run_agent_eval import combine_verdict
    from score import ScoreResult
    mk = lambda *vs: [ScoreResult("s", "model", v) for v in vs]
    assert combine_verdict(mk("FAIL", "PASS", "ERROR")) == "PASS"  # ERROR rerun
    assert combine_verdict(mk("FAIL", "PASS")) == "PASS"          # tie
    assert combine_verdict(mk("FAIL")) == "FAIL"                  # lone fail
    assert combine_verdict(mk("FAIL", "FAIL", "PASS")) == "FAIL"  # 2-of-3
    assert combine_verdict(mk("ERROR", "ERROR")) == "ERROR"       # nothing scored
    assert combine_verdict(mk("SKIP")) == "SKIP"


def test_bug8_connected_but_all_errors_is_fail_not_error(tmp_path):
    # server connected (returns error envelopes for every call) — that's a
    # real model FAIL, NOT a harness ERROR. No init event; evidence must come
    # from the (failing) tool_result itself.
    work = tmp_path / "work"
    work.mkdir()
    lines = [
        _assistant_tool("td_build_project", "t1",
                        {"design": {"operators": []}, "output_dir": work.as_posix()}),
        _tool_result("t1", {"status": "ERROR", "message": "bad design"}),
        _assistant_text("I tried but the build failed."),
        _result(),
    ]
    run = _run(lines)
    assert run.connection_evidence == "tool_result"
    res = S.score_scenario(_s01_no_validate(), run, work)
    assert res.verdict == "FAIL", res.to_json()  # not ERROR
    assert res.error is None


def test_bug5_sibling_dir_prefix_does_not_escape_confinement(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    _build_lfo_chain(work)
    sibling = (tmp_path / "work_evil").as_posix()   # shares 'work' prefix
    lines = [
        _init(),
        _assistant_tool("td_build_project", "t1",
                        {"design": {"operators": []}, "output_dir": sibling}),
        _tool_result("t1", {"status": "SUCCESS"}),
        _result(),
    ]
    res = S.score_scenario(_s01_no_validate(), _run(lines), work)
    assert res.verdict == "FAIL"
    assert any("writes_confined" in f["assertion"] for f in res.failures)


def test_bug6_absent_catches_stray_even_if_named_like_fixture(tmp_path):
    # a real illicit build named text.tox (a fixture basename) but written
    # OUTSIDE assets/ must still trip the abstention 'absent' check
    work = tmp_path / "work"
    work.mkdir()
    (work / "assets").mkdir()
    (work / "assets" / "text.tox").write_text("staged fixture")   # legit
    (work / "text.tox").write_text("illicit build")               # stray, same name
    run = _run([_init(), _assistant_text("done")])
    sc = json.loads(json.dumps(S09))
    res = S.score_scenario(sc, run, work)
    assert res.verdict == "FAIL"
    assert any("artifact.absent" in f["assertion"] for f in res.failures), res.failures


def test_bug6_absent_ignores_staged_fixture_in_assets(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "assets").mkdir()
    (work / "assets" / "text.tox").write_text("staged fixture only")
    run = _run([_init(),
                _assistant_tool("hybrid_search", "t1", {"query": "x"}),
                _tool_result("t1", {"results": []}),
                _assistant_text("no native penrose op; use script SOP / instancing / glsl")])
    res = S.score_scenario(json.loads(json.dumps(S09)), run, work)
    assert res.verdict == "PASS", res.to_json()  # fixture under assets/ doesn't count


def test_bug3_tox_wearing_toe_name_fails_the_toe_assertion(tmp_path):
    # s12's regression target: a component NAMED *.toe (the "mode dropped ->
    # silent .tox" defect) must FAIL, not pass on extension trust.
    import shutil
    work = tmp_path / "work"
    work.mkdir()
    _build_noise_null(work, "tile_mini", mode="tox")     # real .tox
    tox = work / "tile_mini.tox"
    # masquerade: rename the .tox (+ its .dir) to a .toe name
    tox.rename(work / "tile_mini.toe")
    shutil.move(str(work / "tile_mini.tox.dir"), str(work / "tile_mini.toe.dir"))
    lines = [
        _init(),
        _assistant_tool("td_build_project", "t1",
                        {"design": {"operators": []}, "mode": "toe",
                         "output_dir": work.as_posix()}),
        _tool_result("t1", {"status": "SUCCESS", "output_file": "tile_mini.toe"}),
        _result(),
    ]
    art = S.ExpandedArtifact.locate(work, "tile_mini.toe")
    assert art is not None and not art.is_project()   # correctly detected as NOT a project
    res = S.score_scenario(S12, _run(lines), work)
    assert res.verdict == "FAIL"
    assert any("in disguise" in f["detail"] for f in res.failures), res.failures


def test_bug3_real_toe_is_recognized_as_project(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    _build_noise_null(work, "tile_mini", mode="toe")
    art = S.ExpandedArtifact.locate(work, "tile_mini.toe")
    assert art is not None and art.is_project()

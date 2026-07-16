#!/usr/bin/env python3
r"""Seeded scorer tests — the design's acceptance criteria 4/5 + §12 R-3, proven
with synthetic transcripts + hand-built artifacts (no KB, no model, no CLI, and
no live TouchDesigner — the `expect.live` probe is stubbed autouse below).

Run: py -3.11 -m pytest eval/agent_eval/tests/test_scorer.py -q
Needs the fetched KB: the artifacts these tests score are built with the real
ToxBuilder, which grounds op types against KB/operators.json. Runs on CI's
kb-full lane (KB present), not the hermetic (KB-free) lane.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

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
    assert len(S.OFFLINE_TOOLS) == 18
    assert "register_component" in S.OFFLINE_TOOLS
    assert "register_component" not in S.KB_LOOKUP_TOOLS


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


# ===========================================================================
# Live surface (PR #24/#26 re-bless) — td-builder-live parsing, the per-server
# connection barrier, and the tool_result_re assertion
# ===========================================================================
S15 = json.loads((AGENT_EVAL_DIR / "scenarios" / "s15_glsl_break_detect.json").read_text("utf-8"))
S18 = json.loads((AGENT_EVAL_DIR / "scenarios" / "s18_param_collapse_fidelity.json").read_text("utf-8"))


def _init_both(live_connected=True):
    servers = [{"name": "td-builder", "status": "connected"},
               {"name": "td-builder-live",
                "status": "connected" if live_connected else "failed"}]
    return json.dumps({"type": "system", "subtype": "init", "mcp_servers": servers})


def _assistant_live_tool(tool, tid, inp):
    return json.dumps({"type": "assistant", "message": {"model": "m", "content": [
        {"type": "tool_use", "id": tid, "name": S.LIVE_MCP_PREFIX + tool, "input": inp}]}})


# --- live-outcome probe stub -----------------------------------------------
# `expect.live.absent` asks a RUNNING TouchDesigner whether a node survived.
# These are seeded unit tests, so the probe is stubbed process-wide (autouse):
# without it the real one would drag the whole server stack into the light-deps
# CI lane and then ERROR on the missing TD. Each test states the world it wants
# back; the default is the clean one (scratch container gone).
def _nodes_listing(*paths, parent="/", total=None):
    """Render the get_td_nodes SUCCESS contract (td_live_client.py) — markdown,
    not JSON, with the `_N of M node(s) shown._` footer the scorer trusts."""
    lines = [f"## Nodes under {parent}\n"]
    for p in paths:
        lines.append(f"- `{p.rsplit('/', 1)[-1]}` (containerCOMP) - {p}")
    lines.append(f"\n_{len(paths)} of "
                 f"{len(paths) if total is None else total} node(s) shown._")
    return "\n".join(lines)


class _FakeLiveProbe:
    def __init__(self, state):
        self.state, self.calls = state, []

    def call(self, name, args):
        self.calls.append((name, args))
        # ok=True even for TD's fault prose — mirrors the real Probe, which is
        # the whole reason the scorer must not trust `ok` here.
        return SimpleNamespace(name=name, ok=True, text=self.state["text"])


@pytest.fixture(autouse=True)
def live_world(monkeypatch):
    """Default world: nothing matches -> the scratch container is gone."""
    state = {"text": _nodes_listing()}
    probe = _FakeLiveProbe(state)
    state["probe"] = probe
    monkeypatch.setattr(S, "_live_probe", lambda: probe)
    return state


def _s15_transcript(work, glsl_texts=("... GLSL COMPILE FAILED: `x` ...",
                                      "... GLSL COMPILE OK: `x` ..."),
                    cleanup="delete_td_node"):
    """A minimal transcript satisfying s15: KB lookup, live create, the
    status checks, cleanup, an honest report."""
    lines = [
        _init_both(),
        _assistant_tool("hybrid_search", "t1", {"query": "GLSL TOP"}),
        _tool_result("t1", {"results": []}),
        _assistant_live_tool("execute_python_script", "t2", {"script": "..."}),
        _tool_result("t2", "Created /eval_s15_scratch/glsl1"),
    ]
    for i, text in enumerate(glsl_texts):
        tid = f"g{i}"
        lines += [_assistant_live_tool("get_glsl_status", tid,
                                       {"node_path": "/eval_s15_scratch/glsl1"}),
                  _tool_result(tid, text)]
    if cleanup == "delete_td_node":
        lines += [_assistant_live_tool("delete_td_node", "t9",
                                       {"node_path": "/eval_s15_scratch"}),
                  _tool_result("t9", "Deleted")]
    elif cleanup == "destroy":
        # The path the real 2026-07-16 live run took (run live-s15-17): no
        # delete_td_node anywhere, cleanup via idiomatic python. v1 booked this
        # honest run FAIL; v2 must book it PASS.
        lines += [_assistant_live_tool("execute_python_script", "t9", {
            "script": "op('/eval_s15_scratch').destroy()\n"
                      "print(\"Exists:\", bool(op('/eval_s15_scratch')))"}),
            _tool_result("t9", "Exists: False")]
    lines += [
        _assistant_text("The compile failed as expected — compiler error 0:3 "
                        "'' : syntax error — then the fixed shader compiled clean "
                        "and I deleted the scratch container."),
        _result(),
    ]
    return lines


def test_live_prefix_parses_to_bare_names_not_unexpected(tmp_path):
    run = _run(_s15_transcript(tmp_path / "work"))
    assert not run.unexpected_tools
    by_name = {tc.name: tc for tc in run.tool_calls}
    assert by_name["get_glsl_status"].live is True
    assert by_name["hybrid_search"].live is False
    assert run.connection_evidence == "init_event"
    assert run.live_connection_evidence == "init_event"


def test_live_tool_result_is_live_evidence_only():
    # no init event, ONLY a live tool result: live evidence set, offline still
    # None (a live result must never vouch for the offline server)
    lines = [_assistant_live_tool("get_td_info", "t1", {}),
             _tool_result("t1", "TouchDesigner 2025.x"),
             _result()]
    run = _run(lines)
    assert run.live_connection_evidence == "tool_result"
    assert run.connection_evidence is None


def test_live_scenario_without_live_evidence_is_error(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    # offline server connected, live server NEVER — the model "did nothing
    # live", which must book as harness ERROR, not a model FAIL
    lines = [_init_both(live_connected=False),
             _assistant_tool("hybrid_search", "t1", {"query": "glsl"}),
             _tool_result("t1", {"results": []}),
             _assistant_text("could not reach TD"),
             _result()]
    res = S.score_scenario(json.loads(json.dumps(S15)), _run(lines), work)
    assert res.verdict == "ERROR", res.to_json()
    assert "live" in (res.error or "").lower()


def test_offline_scenario_ignores_missing_live_server(tmp_path):
    # an OFFLINE scenario must not care that no live server ever connected
    work = tmp_path / "work"
    work.mkdir()
    run = _run([_init(connected=True), _assistant_text("done"), _result()])
    res = S.score_scenario(_s01_no_validate(), run, work)
    assert res.verdict == "FAIL"        # scored (missing artifact), NOT ERROR
    assert res.error is None


def test_s15_pass_end_to_end(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    res = S.score_scenario(json.loads(json.dumps(S15)),
                           _run(_s15_transcript(work)), work)
    assert res.verdict == "PASS", res.to_json()


# --- expect.live.absent: OUTCOME, not mechanism (s15 v2) --------------------
def test_live_absent_scores_the_destroy_path_that_v1_failed(tmp_path, live_world):
    """THE regression: the 2026-07-16 live run cleaned up correctly with
    execute_python_script + .destroy() and v1 booked FAIL on
    trace.tool_called[delete_td_node]. The container is gone; that is the
    whole question, and v2 must answer PASS."""
    work = tmp_path / "work"
    work.mkdir()
    run = _run(_s15_transcript(work, cleanup="destroy"))
    assert "delete_td_node" not in {tc.name for tc in run.tool_calls}
    res = S.score_scenario(json.loads(json.dumps(S15)), run, work)
    assert res.verdict == "PASS", res.to_json()
    # and it is not vacuous — the scorer really did go and look, read-only
    assert live_world["probe"].calls == [
        ("get_td_nodes", {"parent_path": "/", "pattern": "eval_s15_scratch"})]


def test_live_absent_surviving_container_fails(tmp_path, live_world):
    """The other half: delete_td_node CALLED but the container still there —
    v1 passed this (the tool was called!), v2 fails it (the outcome is wrong)."""
    work = tmp_path / "work"
    work.mkdir()
    live_world["text"] = _nodes_listing("/eval_s15_scratch")
    res = S.score_scenario(json.loads(json.dumps(S15)),
                           _run(_s15_transcript(work)), work)
    assert res.verdict == "FAIL", res.to_json()
    assert res.fingerprints == ["live.absent[/eval_s15_scratch]"], res.failures


def test_live_absent_matches_exact_path_not_bare_name(tmp_path, live_world):
    """get_td_nodes applies `pattern` through findChildren(name=...), which TD
    resolves RECURSIVELY — a same-named node somewhere else is not this node."""
    work = tmp_path / "work"
    work.mkdir()
    live_world["text"] = _nodes_listing("/project1/backup/eval_s15_scratch")
    res = S.score_scenario(json.loads(json.dumps(S15)),
                           _run(_s15_transcript(work)), work)
    assert res.verdict == "PASS", res.to_json()


@pytest.mark.parametrize("fault", [
    "TD Error: 500 Internal Server Error",          # non-200 from the WebServer
    "Failed: Parent node not found at path: /",     # TD-side error_result
    "Cannot reach TouchDesigner on port 9981 — import mcp_webserver_base.tox",
])
def test_live_absent_td_fault_is_error_never_a_vacuous_pass(tmp_path, live_world,
                                                            fault):
    """The trap this primitive is built around: the live client reports TD
    faults as bare prose. None of it starts with 'Error:', none of it is JSON,
    so the envelope heuristic calls it ok=True — and it contains no node lines.
    Trusting `ok` would read 'TouchDesigner fell over' as 'nothing matched' and
    PASS the cleanup assertion in exactly the state it exists to catch."""
    work = tmp_path / "work"
    work.mkdir()
    live_world["text"] = fault
    res = S.score_scenario(json.loads(json.dumps(S15)),
                           _run(_s15_transcript(work)), work)
    assert res.verdict == "ERROR", res.to_json()      # not PASS, not FAIL
    assert "no node listing" in (res.error or "")


def test_live_absent_truncated_listing_is_error(tmp_path, live_world):
    # absence within a slice is not absence
    work = tmp_path / "work"
    work.mkdir()
    live_world["text"] = _nodes_listing("/other", total=205)
    res = S.score_scenario(json.loads(json.dumps(S15)),
                           _run(_s15_transcript(work)), work)
    assert res.verdict == "ERROR", res.to_json()
    assert "TRUNCATED" in (res.error or "")


def test_live_absent_probe_crash_is_error_not_fail(tmp_path, monkeypatch):
    # a dead probe is a harness fault — never "the model regressed" (§4)
    work = tmp_path / "work"
    work.mkdir()

    def _boom():
        raise ConnectionError("connection refused")

    monkeypatch.setattr(S, "_live_probe", _boom)
    res = S.score_scenario(json.loads(json.dumps(S15)),
                           _run(_s15_transcript(work)), work)
    assert res.verdict == "ERROR", res.to_json()
    assert "ConnectionError" in (res.error or "")


def test_live_probe_error_dominates_a_booked_failure(tmp_path, live_world):
    """ERROR outranks FAIL: if we could not read the world, the verdict is
    'unmeasured', even when another assertion already failed."""
    work = tmp_path / "work"
    work.mkdir()
    live_world["text"] = "TD Error: boom"
    res = S.score_scenario(          # detection never surfaced -> a real FAIL
        json.loads(json.dumps(S15)),
        _run(_s15_transcript(work, glsl_texts=("... GLSL COMPILE OK ...",))), work)
    assert res.verdict == "ERROR", res.to_json()


def test_expect_live_on_an_offline_scenario_is_refused_at_load(tmp_path):
    """Structural coupling: expect.live reaches a running TD at SCORING time,
    so it must sit behind td_live_running. On an offline scenario it would
    never SKIP — it would import the server stack in the light-deps CI lane and
    ERROR there. Fail loudly at load instead."""
    p = tmp_path / "s99_bad.json"
    p.write_text(json.dumps({
        "id": "s99_bad", "version": 1, "prompt": "x",
        "expect": {"live": {"absent": ["/x"]}},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="expect.live needs surface"):
        S.load_scenario(p)


def test_expect_live_on_a_live_scenario_loads(tmp_path):
    p = tmp_path / "s99_ok.json"
    p.write_text(json.dumps({
        "id": "s99_ok", "version": 1, "prompt": "x", "surface": "live",
        "expect": {"live": {"absent": ["/x"]}},
    }), encoding="utf-8")
    assert S.load_scenario(p)["requires"] == ["td_live_running"]


def test_tool_result_re_detection_never_surfaced_fails(tmp_path):
    # the shader "worked" both times — the FAILED detection the scenario exists
    # to prove never surfaced -> that exact assertion is the fingerprint
    work = tmp_path / "work"
    work.mkdir()
    res = S.score_scenario(
        json.loads(json.dumps(S15)),
        _run(_s15_transcript(work, glsl_texts=("... GLSL COMPILE OK: `x` ...",))),
        work)
    assert res.verdict == "FAIL"
    assert any("tool_result_re[get_glsl_status:GLSL COMPILE FAILED]" in f["assertion"]
               for f in res.failures), res.failures


def test_tool_result_re_tool_never_called_fails(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    lines = [_init_both(),
             _assistant_tool("hybrid_search", "t1", {"query": "GLSL TOP"}),
             _tool_result("t1", {"results": []}),
             _assistant_live_tool("get_td_node_errors", "t2", {"node_path": "/x"}),
             _tool_result("t2", "no errors"),
             _assistant_text("compile failed somewhere probably"),
             _result()]
    res = S.score_scenario(json.loads(json.dumps(S15)), _run(lines), work)
    assert res.verdict == "FAIL"
    assert any("tool_result_re" in f["assertion"] and "never called" in f["detail"]
               for f in res.failures), res.failures


def test_s18_pass_and_hybrid_only_discipline(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    envelope = {"semantic_results": [{
        "metadata": {"operator_name": "GLSL Create POP"},
        "score_kind": "rank_fusion_only",
        "parameter_count": 28,
        "parameter_names": ["computedat", "vec[0]{name,type,value}",
                            "const[0]{name,value}"],
        "parameters": {"computedat": {}}, "parameters_capped": True}]}
    lines = [
        _init(),
        _assistant_tool("hybrid_search", "t1", {"query": "GLSL POP", "compact": True}),
        _tool_result("t1", envelope),
        _assistant_tool("hybrid_search", "t2", {"query": "GLSL POP", "compact": False}),
        _tool_result("t2", envelope),
        _assistant_text("GLSL Create POP: 28 params total, 3 names listed; the "
                        "vector-uniform block collapses to vec[0]{name,type,value}; "
                        "full mode capped the detail (parameters_capped: true); "
                        "score_kind is rank_fusion_only on this install."),
        _result(),
    ]
    res = S.score_scenario(json.loads(json.dumps(S18)), _run(lines), work)
    assert res.verdict == "PASS", res.to_json()


def test_s18_reaching_for_another_kb_tool_fails(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    envelope = {"semantic_results": [{
        "score_kind": "rank_fusion_only", "parameters_capped": True,
        "parameter_names": ["vec[0]{name,type,value}"]}]}
    lines = [
        _init(),
        _assistant_tool("hybrid_search", "t1", {"query": "GLSL POP"}),
        _tool_result("t1", envelope),
        _assistant_tool("get_operator_info", "t2", {"operator_name": "GLSL Create POP"}),
        _tool_result("t2", {"parameters": {}}),
        _assistant_text("vec[0] ... rank fusion scores"),
        _result(),
    ]
    res = S.score_scenario(json.loads(json.dumps(S18)), _run(lines), work)
    assert res.verdict == "FAIL"
    assert any("tool_not_called" in f["assertion"] for f in res.failures), res.failures


def test_live_identity_field_registered():
    import identity as identity_mod
    assert "live_tool_inventory_hash" in identity_mod.AGENT_IDENTITY_FIELDS
    # pre-live baselines read as UNKNOWN (warn), never as a refusing mismatch
    mism, unknown = identity_mod.identity_mismatches(
        {"live_tool_inventory_hash": "abc"}, {"tool_inventory_hash": "x"},
        identity_mod.AGENT_IDENTITY_FIELDS)
    assert not any(f == "live_tool_inventory_hash" for f, _, _ in mism)
    assert "live_tool_inventory_hash" in unknown


def test_live_optin_env_gate_is_checked_before_the_socket(monkeypatch):
    # The safety lynchpin (review F3): without TD_EVAL_LIVE=1 a live scenario
    # SKIPs BEFORE any socket probe — TD being open must never be enough.
    import run_agent_eval as RA
    monkeypatch.delenv("TD_EVAL_LIVE", raising=False)
    monkeypatch.setattr(RA, "_td_reachable",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("socket probed despite no opt-in")))
    _, skip = RA.resolve_requires(["td_live_running"])
    assert skip and "TD_EVAL_LIVE" in skip


def test_surface_live_implies_td_live_running_gate(tmp_path):
    # Structural coupling (review F1): a live scenario that FORGETS the
    # requires token still gets it injected at load time — the opt-in gate
    # cannot be bypassed by omission.
    p = tmp_path / "s99_forgot_requires.json"
    p.write_text(json.dumps({
        "id": "s99_forgot_requires", "version": 1, "surface": "live",
        "requires": [], "prompt": "x", "expect": {}}), encoding="utf-8")
    sc = S.load_scenario(p)
    assert "td_live_running" in sc["requires"]
    # and the shipped live scenarios carry it explicitly
    for sid in ("s15_glsl_break_detect", "s16_pop_viewer_capture",
                "s17_glsl_file_sync_status"):
        shipped = S.load_scenario(AGENT_EVAL_DIR / "scenarios" / f"{sid}.json")
        assert shipped.get("surface") == "live"
        assert "td_live_running" in shipped["requires"]


def test_offline_and_live_tool_names_are_disjoint():
    # Replay routing and tool_result_re match on BARE names (review F3): a
    # live tool shadowing an offline name would silently misroute. Pin the
    # disjointness so a future rename trips here first.
    import inproc
    live = set(inproc.live_tool_names())
    assert len(live) >= 22
    assert not (live & set(S.OFFLINE_TOOLS)), live & set(S.OFFLINE_TOOLS)


def test_save_td_project_never_in_lane_m_allowlist():
    # The persistence boundary (review F2): live Lane M must not allowlist
    # the one tool whose effect outlives the session.
    import inproc
    from run_agent_eval import allowed_tools
    live_allowed = allowed_tools(live=True)
    assert S.LIVE_MCP_PREFIX + "save_td_project" not in live_allowed
    assert S.LIVE_MCP_PREFIX + "get_glsl_status" in live_allowed
    # the source list itself still HAS the tool (we exclude, not deny it exists)
    assert "save_td_project" in inproc.live_tool_names()
    # offline scenarios never allow ANY live tool
    assert not [t for t in allowed_tools(live=False)
                if t.startswith(S.LIVE_MCP_PREFIX)]


def test_compare_excludes_model_fields_for_replay_lane_only(tmp_path):
    import run_agent_eval as RA
    prior = {"identity": {
        "scenario_set_version": "1.0.0", "model_id": "claude-sonnet-4-6",
        "cli_version": "2.1.81 (Claude Code)", "server_version": "0.2.0",
        "kb_manifest_version": "0.2.0", "kb_sha": "k", "tool_inventory_hash": "t",
        "live_tool_inventory_hash": "l", "guidance_hash": "g"},
        "scenarios": {}}
    pth = tmp_path / "prior.json"
    pth.write_text(json.dumps(prior), encoding="utf-8")
    ident = dict(prior["identity"], model_id=None, cli_version=None)

    class _Args:
        compare = str(pth)
        allow_identity_drift = False

    # replay sweep: model_id/cli_version excluded -> no refusal (rc 0)
    rc = RA.compare_against(_Args(), {"identity": ident, "lane": "replay",
                                      "results": {}})
    assert rc == 0
    # model sweep with a REAL model mismatch must still refuse (rc 3)
    ident_m = dict(prior["identity"], model_id="some-other-model")
    rc = RA.compare_against(_Args(), {"identity": ident_m, "lane": "model",
                                      "results": {}})
    assert rc == 3

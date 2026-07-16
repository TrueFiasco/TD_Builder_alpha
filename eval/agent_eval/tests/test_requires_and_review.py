#!/usr/bin/env python3
r"""Agent-eval additions for the W7 register_component scenarios (s19-s21).

    py -3.11 -m pytest eval/agent_eval/tests/test_requires_and_review.py -q

Deliberately a SEPARATE file from test_scorer.py: that file is W7's this wave
(the 17->18 OFFLINE_TOOLS pin lives there), and one toucher per file per wave is
the operating rule.

Nothing here pins the real tool inventory. The `tool:` gate is exercised against
MONKEYPATCHED synthetic inventories, so this file stays green across any future
tool-surface change -- pinning the live count here would just duplicate
test_scorer.py:340 and rot the same way.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

AGENT_EVAL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_EVAL_DIR.parents[1]
for p in (str(AGENT_EVAL_DIR), str(REPO_ROOT), str(REPO_ROOT / "MCP" / "server_core")):
    if p not in sys.path:
        sys.path.insert(0, p)

import run_agent_eval as R  # noqa: E402
import score as S  # noqa: E402

SCENARIOS = ("s19_register_search_roundtrip", "s20_register_exact_name",
             "s21_register_hit_parity")
FIXTURE_DIR = AGENT_EVAL_DIR / "fixtures" / "knotgen.tox.dir"
FIXTURE_TOC = AGENT_EVAL_DIR / "fixtures" / "knotgen.tox.toc"


@pytest.fixture(autouse=True)
def _clear_tool_memo():
    """_known_tool_names is lru_cached (one probe per process) -- drop it around
    every test so a monkeypatched inventory can never leak between them."""
    R._known_tool_names.cache_clear()
    yield
    R._known_tool_names.cache_clear()


def _fake_inventory(monkeypatch, names):
    monkeypatch.setattr(R, "_known_tool_names", lambda: frozenset(names))


# ---------------------------------------------------------------------------
# requires: tool:<name>
# ---------------------------------------------------------------------------
def test_tool_token_satisfied_when_present(monkeypatch):
    _fake_inventory(monkeypatch, {"register_component", "hybrid_search"})
    tvars, skip = R.resolve_requires(["tool:register_component"])
    assert skip is None and tvars == {}


def test_tool_token_skips_when_absent(monkeypatch):
    """The pre-W7 case: SKIP is the honest verdict, never FAIL/ERROR."""
    _fake_inventory(monkeypatch, {"hybrid_search"})
    _, skip = R.resolve_requires(["tool:register_component"])
    assert skip and "register_component" in skip
    assert "not on this checkout's tool surface" in skip


def test_tool_token_probe_failure_skips_rather_than_crashing(monkeypatch):
    """F5 posture (mirrors _td_reachable): a broken probe must not take the whole
    sweep down -- it books this ONE scenario SKIP with the reason visible."""
    def boom():
        raise RuntimeError("server import exploded")
    monkeypatch.setattr(R, "_known_tool_names", boom)
    _, skip = R.resolve_requires(["tool:register_component"])
    assert skip and "probe failed" in skip and "RuntimeError" in skip


def test_tool_token_composes_with_other_requires(monkeypatch):
    _fake_inventory(monkeypatch, {"register_component"})
    monkeypatch.delenv("TD_EVAL_LIVE", raising=False)
    _, skip = R.resolve_requires(["tool:register_component", "td_live_running"])
    assert skip and "td_live_running" in skip     # first UNsatisfied token wins


def test_unknown_token_still_skips(monkeypatch):
    """Regression: the catch-all must survive the tool: branch landing above it."""
    _fake_inventory(monkeypatch, {"register_component"})
    _, skip = R.resolve_requires(["totally_made_up"])
    assert skip and "unknown requires entry" in skip


def test_live_token_untouched_by_the_new_branch(monkeypatch):
    monkeypatch.delenv("TD_EVAL_LIVE", raising=False)
    _, skip = R.resolve_requires(["td_live_running"])
    assert skip and "TD_EVAL_LIVE=1" in skip


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sid", SCENARIOS)
def test_scenario_loads_and_is_gated(sid):
    sc = S.load_scenario(AGENT_EVAL_DIR / "scenarios" / f"{sid}.json")
    assert sc["id"] == sid
    assert sc["requires"] == ["tool:register_component"], \
        "must SKIP (not ERROR) on a checkout without the tool"
    assert sc["gate"] is True
    assert sc["expect"]["artifact"] == {"absent": True}, \
        "register scenarios build nothing -- a stray .tox is a real failure"
    assert sc.get("surface") is None, "offline: must be replayable in hosted CI"
    assert sc["fixtures"] == ["knotgen.tox.dir", "knotgen.tox.toc"]


@pytest.mark.parametrize("sid", SCENARIOS)
def test_scenario_prompt_stages_fixture_from_run_dir(sid):
    """The prompt must reference the fixture through {{RUN_DIR}} -- an absolute
    path would bake this machine into the blessed trace and break hosted replay
    (bless() only templates the run dir)."""
    sc = S.load_scenario(AGENT_EVAL_DIR / "scenarios" / f"{sid}.json")
    assert "{{RUN_DIR}}/assets/knotgen.tox.dir" in sc["prompt"]
    assert "C:" not in sc["prompt"] and "c:/" not in sc["prompt"].lower()


@pytest.mark.parametrize("sid", SCENARIOS)
def test_scenario_trace_regexes_compile_and_avoid_dot_spans(sid):
    """tool_result_re is re.search(..., re.MULTILINE) -- NOT DOTALL. A bare '.'
    cannot cross the newlines of an indent=2 envelope, so multi-line spans must
    use [\\s\\S]."""
    import re
    sc = S.load_scenario(AGENT_EVAL_DIR / "scenarios" / f"{sid}.json")
    for item in sc["expect"]["trace"]:
        spec = item.get("tool_result_re")
        if not spec:
            continue
        re.compile(spec["re"])                       # must be a valid pattern
        assert ".{" not in spec["re"], \
            f"{sid}: '.{{n}}' span cannot cross newlines without DOTALL; use [\\s\\S]"


# ---------------------------------------------------------------------------
# fixture canary -- eval OWNS this fixture; these are the literals s19/s20/s21
# regex against. If someone edits the .cparm, fail HERE by name rather than as a
# mystery red replay.
# ---------------------------------------------------------------------------
def test_fixture_is_committed_and_hermetic():
    assert FIXTURE_DIR.is_dir() and FIXTURE_TOC.is_file(), \
        "knotgen fixture missing -- check .gitignore *.tox.dir/ re-inclusion"
    assert (FIXTURE_DIR / "knotgen.cparm").is_file()


def test_fixture_par_surface_matches_what_the_scenarios_assert():
    from kb_build import user_components as uc
    sk = uc.parse_component(FIXTURE_DIR)
    assert sk["parse_warnings"] == []
    by = {p["name"]: p for p in sk["custom_parameters"]}
    assert set(by) == {"Numpoints", "Scale", "Knottype"}

    # int with min/max -> "Numpoints (Num Points; default 200; range 16..2000)"
    assert by["Numpoints"]["type_class"] == "number"
    assert by["Numpoints"]["default"] == 200
    assert (by["Numpoints"]["min"], by["Numpoints"]["max"]) == (16, 2000)
    assert by["Numpoints"]["label"] == "Num Points"

    # vec3 -> list default -> "Scale (default 1, 1, 1)"; label == name, so
    # _format_custom_par omits the label bit entirely
    assert by["Scale"]["type_class"] == "multi"
    assert by["Scale"]["default"] == [1, 1, 1]
    assert by["Scale"]["label"] == by["Scale"]["name"]

    # menu tokens ride VERBATIM -- the #1 build rule
    assert by["Knottype"]["type_class"] == "menu"
    assert [m["token"] for m in by["Knottype"]["menu"]] == \
        ["trefoil", "figure8", "torus", "circle"]
    assert by["Knottype"]["default"] == "trefoil"


def test_fixture_renders_the_io_text_the_scenarios_grep_for():
    """End-to-end through the real chunk builder: the block_io text must still
    contain every literal s19 asserts on."""
    import re
    from kb_build import user_components as uc
    sk = uc.parse_component(FIXTURE_DIR)
    entry, _ = uc.build_entry(
        sk, source="project", tox_path="knotgen.tox", summary="x",
        use_cases=["y"], parameter_descriptions={"Numpoints": "d1", "Scale": "d2",
                                                 "Knottype": "d3"})
    rows = uc.component_block_rows("knotgen", entry)
    io = next(r["text"] for r in rows if r["chunk_type"] == "block_io")
    for rx in (r"Custom parameters:",
               r"Numpoints \(Num Points; default 200; range 16\.\.2000\)",
               r"menu tokens: trefoil\|figure8\|torus\|circle; default trefoil",
               r"Scale \(default 1, 1, 1\)"):
        assert re.search(rx, io), f"block_io no longer matches s19's regex: {rx}"


def test_fixture_name_does_not_shadow_a_shipped_palette_component():
    """s20 asserts shadows_shipped:false. Exact-name injection normalizes and
    substring-matches, so check both directions."""
    import re
    comps = json.loads((REPO_ROOT / "KB" / "palette_components.json")
                       .read_text(encoding="utf-8"))["components"]
    norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())  # noqa: E731
    shipped = {norm(n) for n in comps}
    for cand in ("knotgen", "wisp"):
        assert norm(cand) not in shipped
        assert not any(norm(cand) in s for s in shipped)


# ---------------------------------------------------------------------------
# stage_fixtures
# ---------------------------------------------------------------------------
def test_committed_fixture_dir_is_staged_into_assets(tmp_path):
    work = tmp_path / "work"
    R.stage_fixtures({"fixtures": ["knotgen.tox.dir", "knotgen.tox.toc"]}, work)
    staged = work / "assets" / "knotgen.tox.dir"
    assert staged.is_dir() and (staged / "knotgen.cparm").is_file()
    # the sibling .toc is load-bearing: the manifest parser refuses a .dir
    # without it ("No .toc file found")
    assert (work / "assets" / "knotgen.tox.toc").is_file()


def test_staged_fixture_still_parses(tmp_path):
    """What the tool will actually be handed at run time."""
    from kb_build import user_components as uc
    work = tmp_path / "work"
    R.stage_fixtures({"fixtures": ["knotgen.tox.dir", "knotgen.tox.toc"]}, work)
    sk = uc.parse_component(work / "assets" / "knotgen.tox.dir")
    assert [p["name"] for p in sk["custom_parameters"]] == \
        ["Numpoints", "Scale", "Knottype"]


def test_committed_fixture_never_triggers_generation(monkeypatch):
    """ensure_fixtures must not try to BUILD a committed fixture: it is repo
    content, not build output, and make_fixtures has no idea how to make it.
    Sentinel module rather than the real one -- this asserts the seam, and must
    hold whether or not make_fixtures happens to be importable."""
    import types
    sentinel = types.ModuleType("make_fixtures")
    sentinel.main = lambda *a, **k: pytest.fail(
        "make_fixtures.main() ran for a COMMITTED fixture")
    monkeypatch.setitem(sys.modules, "make_fixtures", sentinel)
    R.ensure_fixtures(["knotgen.tox.dir"])          # must be a no-op


def test_generated_fixture_path_still_works(tmp_path, monkeypatch):
    """s17's eval_fragment.glsl path must be untouched by the committed-first
    lookup."""
    gen = tmp_path / "generated"
    gen.mkdir()
    (gen / "made_up.glsl").write_text("// x", encoding="utf-8")
    monkeypatch.setattr(R, "FIXTURES_GENERATED", gen)
    monkeypatch.setattr(R, "fixture_source", lambda n: None)   # nothing committed
    work = tmp_path / "work"
    R.stage_fixtures({"fixtures": ["made_up.glsl"]}, work)
    assert (work / "assets" / "made_up.glsl").read_text(encoding="utf-8") == "// x"


# ---------------------------------------------------------------------------
# review ledger
# ---------------------------------------------------------------------------
sys.path.insert(0, str(AGENT_EVAL_DIR / "review"))
import extract_registrations as X  # noqa: E402


def _transcript(prepare_result: dict, commit_spec: dict, commit_result: dict) -> str:
    def use(tid, args):
        return json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": tid,
             "name": "mcp__td-builder__register_component", "input": args}]}})

    def res(tid, payload):
        return json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": tid,
             "content": [{"type": "text",
                          "text": json.dumps(payload, ensure_ascii=False)}]}]}})
    return "\n".join([
        json.dumps({"type": "system", "subtype": "init",
                    "mcp_servers": [{"name": "td-builder", "status": "connected"}]}),
        use("t1", {"specs": [{"tox_path": "/x/knotgen.tox.dir"}], "prepare": True}),
        res("t1", prepare_result),
        use("t2", {"specs": [commit_spec], "prepare": False}),
        res("t2", commit_result),
    ])


@pytest.fixture
def _ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(X, "REVIEW_DIR", tmp_path)
    monkeypatch.setattr(X, "LEDGER_JSONL", tmp_path / "registration_quality.jsonl")
    monkeypatch.setattr(X, "LEDGER_MD", tmp_path / "registration_quality.md")
    monkeypatch.setattr(X, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(X, "TRACES_DIR", tmp_path / "traces")
    return tmp_path


def _seed_run(root: Path) -> None:
    trial = root / "runs" / "model-test" / "s19_register_search_roundtrip"
    trial.mkdir(parents=True)
    (trial / "meta.json").write_text(json.dumps({"model_id": "claude-sonnet-4-6"}),
                                     encoding="utf-8")
    (trial / "transcript.jsonl").write_text(_transcript(
        prepare_result={"ok": True, "prepared": [{
            "name": "knotgen", "ok": True,
            "custom_parameters": [
                {"name": "Numpoints", "label": "Num Points", "default": 200,
                 "min": 16, "max": 2000, "type_class": "number"},
                {"name": "Knottype", "label": "Knot Type", "default": "trefoil",
                 "type_class": "menu",
                 "menu": [{"token": "trefoil", "label": "Trefoil"},
                          {"token": "circle", "label": "Circle"}]}],
            "inputs": [], "outputs": [{"name": "out1"}],
            "contained_operators": ["POP:circle", "POP:glsl"],
            "operator_count": 6}]},
        commit_spec={"tox_path": "/x/knotgen.tox.dir", "name": "knotgen",
                     "summary": "Generates a parametric knot curve as a POP line.",
                     "use_cases": ["knot geometry", "parametric curves"],
                     "parameter_descriptions": {
                         "Numpoints": "how many points sample the curve",
                         "Knottype": "which knot formula to generate"}},
        commit_result={"ok": True, "results": [{
            "name": "knotgen", "ok": True, "retrievable": True, "chunk_count": 3,
            "shadows_shipped": False, "operator_count": 6,
            "entry_summary": "Generates a parametric knot curve as a POP line."}]},
    ), encoding="utf-8")


def test_extractor_harvests_authored_fields_and_actuals(_ledger, monkeypatch):
    _seed_run(_ledger)
    monkeypatch.setattr(sys, "argv", ["x", "--runs", "model-test", "--render"])
    assert X.main() == 0

    rows = [json.loads(l) for l in
            (_ledger / "registration_quality.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    e = rows[0]
    assert e["component"] == "knotgen"
    assert e["scenario"] == "s19_register_search_roundtrip"
    assert e["model"] == "claude-sonnet-4-6"
    assert e["authored"]["summary"].startswith("Generates a parametric knot")
    assert e["authored"]["parameter_descriptions"]["Knottype"] == \
        "which knot formula to generate"
    # the prepare skeleton is juxtaposed as ground truth for the review
    assert [p["name"] for p in e["actual"]["custom_parameters"]] == \
        ["Numpoints", "Knottype"]
    assert e["committed"]["retrievable"] is True

    md = (_ledger / "registration_quality.md").read_text(encoding="utf-8")
    assert "Generates a parametric knot curve" in md
    assert "which knot formula to generate" in md
    assert "menu: trefoil|circle" in md            # actual column shows real tokens
    assert "Specificity:" in md and "verdict:" in md


def test_extractor_is_idempotent(_ledger, monkeypatch):
    _seed_run(_ledger)
    monkeypatch.setattr(sys, "argv", ["x", "--runs", "model-test"])
    X.main()
    X.main()
    rows = (_ledger / "registration_quality.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1, "re-running the extractor must not duplicate entries"


def test_extractor_is_green_with_nothing_to_harvest(_ledger, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["x", "--render"])
    assert X.main() == 0
    assert "no register_component calls found" in capsys.readouterr().out
    assert "No registrations harvested yet" in \
        (_ledger / "registration_quality.md").read_text(encoding="utf-8")


def test_extractor_flags_a_described_parameter_that_does_not_exist(_ledger, monkeypatch):
    """The Correctness axis's sharpest case: the model describes a parameter the
    component does not have. The ledger must SHOW that, not quietly drop it."""
    trial = _ledger / "runs" / "model-test" / "s19_register_search_roundtrip"
    trial.mkdir(parents=True)
    (trial / "transcript.jsonl").write_text(_transcript(
        prepare_result={"ok": True, "prepared": [{
            "name": "knotgen", "custom_parameters": [{"name": "Numpoints"}],
            "inputs": [], "outputs": [], "contained_operators": []}]},
        commit_spec={"tox_path": "/x/knotgen.tox.dir", "name": "knotgen",
                     "summary": "s", "use_cases": [],
                     "parameter_descriptions": {"Numpoints": "real",
                                                "Hallucinated": "invented"}},
        commit_result={"ok": True, "results": [{"name": "knotgen", "ok": True}]},
    ), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["x", "--runs", "model-test", "--render"])
    X.main()
    md = (_ledger / "registration_quality.md").read_text(encoding="utf-8")
    assert "Hallucinated" in md and "_(no such parameter!)_" in md

#!/usr/bin/env python3
r"""THE one command for the end-to-end agent eval (design AGENT_EVAL_DESIGN.md).

Two lanes, one scenario set, one scorer:

  Lane M (--lane model)  — the AGENT-GATE: headless `claude -p` subprocess per
      scenario against a per-run strict MCP config. Measures the model in the
      loop. Auth = the maintainer's logged-in Claude subscription ONLY (owner
      decision D-A): ANTHROPIC_API_KEY is actively stripped from the subprocess
      environment; no API-key path exists here.
  Lane R (--lane replay) — the REPLAY-GATE: blessed tool-call traces re-executed
      in-process (tests/measure probe pattern) and scored by the same scorer.
      Deterministic, key-free, minutes-fast — the CI invariant.

  HONESTY RULE (design §2): Lane R must never be reported as "agent eval
  passing" — reports name replay-gate and agent-gate distinctly. A green
  replay lane with a red model lane means "code fine, model path changed".

Budgets (§12 R-1): the pinned CLI (2.1.81) has NO --max-turns — enforcement is
wall-clock timeout per scenario + a sweep-level spend cap; turn counts are
scored post-hoc from the stream-json transcript. Budget/infra faults book as
ERROR, never FAIL (§4 taxonomy).

Usage:
  py -3.11 eval/agent_eval/run_agent_eval.py --lane replay
  py -3.11 eval/agent_eval/run_agent_eval.py --lane model
  py -3.11 eval/agent_eval/run_agent_eval.py --lane model --all --k 3
  py -3.11 eval/agent_eval/run_agent_eval.py --lane model --capture-baseline --n 5
  py -3.11 eval/agent_eval/run_agent_eval.py --lane replay --compare eval/agent_eval/baseline.json
  py -3.11 eval/agent_eval/run_agent_eval.py --lane model --scenario s05_palette_audio
  py -3.11 eval/agent_eval/run_agent_eval.py --bless <run-id>
"""

from __future__ import annotations

import argparse
import glob as globmod
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

AGENT_EVAL_DIR = Path(__file__).resolve().parent
EVAL_DIR = AGENT_EVAL_DIR.parent
REPO_ROOT = EVAL_DIR.parent

sys.path.insert(0, str(AGENT_EVAL_DIR))
import identity as identity_mod          # noqa: E402
import score as score_mod                # noqa: E402
from score import (LIVE_MCP_PREFIX, MCP_PREFIX, OFFLINE_TOOLS, NormalizedRun,  # noqa: E402
                   ToolCall, load_scenario, parse_stream_json, score_scenario)

CONFIG_PATH = AGENT_EVAL_DIR / "config.json"
GUIDANCE_PATH = AGENT_EVAL_DIR / "guidance.md"
MCP_TMPL_PATH = AGENT_EVAL_DIR / "mcp.eval.json.tmpl"
MCP_LIVE_TMPL_PATH = AGENT_EVAL_DIR / "mcp.eval.live.json.tmpl"
SCENARIOS_DIR = AGENT_EVAL_DIR / "scenarios"
TRACES_DIR = AGENT_EVAL_DIR / "traces"
RUNS_DIR = AGENT_EVAL_DIR / "runs"
BASELINE_PATH = AGENT_EVAL_DIR / "baseline.json"
FIXTURES_GENERATED = AGENT_EVAL_DIR / "fixtures" / "generated"

# Built-in Claude Code tools removed from the Lane-M surface (design §2:
# KB-first purity — with Read/Grep available the model could answer grounding
# scenarios by reading KB/operators.json off disk — plus hermeticity).
DISALLOWED_BUILTINS = [
    "Bash", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "NotebookRead",
    "Glob", "Grep", "LS", "WebFetch", "WebSearch", "Task", "Agent", "TodoWrite",
    "TodoRead", "KillShell", "BashOutput", "SlashCommand", "Skill",
    "EnterPlanMode", "ExitPlanMode",
]


# ---------------------------------------------------------------------------
# Config / environment
# ---------------------------------------------------------------------------
def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def main_tree() -> Path | None:
    parts = REPO_ROOT.parts
    if ".claude" in parts:
        return Path(*parts[: parts.index(".claude")])
    return None


def stage_dir() -> Path:
    mt = main_tree() or REPO_ROOT.parent
    return mt / "New KB build" / "Output" / "agent_eval"


def kb_root() -> Path:
    return REPO_ROOT / "KB"


def _td_reachable(timeout: float = 2.0) -> bool:
    """True when TouchDesigner's WebServer DAT answers (mirror of
    tests/conftest.py::_td_reachable, honoring the TD_API_URL override the
    live client itself uses). A malformed TD_API_URL (schemeless host,
    non-numeric port) reads as NOT reachable — a SKIP with a visible reason
    beats crashing the sweep inside resolve_requires (review F5)."""
    import socket
    from urllib.parse import urlparse
    try:
        url = urlparse(os.environ.get("TD_API_URL", "http://127.0.0.1:9981"))
        host, port = url.hostname, url.port or 9981
        if not host:
            return False
    except ValueError:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def resolve_requires(requires: list) -> tuple[dict, str | None]:
    """Resolve scenario preconditions. Returns (template_vars, skip_reason)."""
    tvars: dict[str, str] = {}
    for req in requires or []:
        if req == "td_live_running":
            # Live-surface scenarios (s15–s17): a RUNNING TouchDesigner with
            # the WebServer DAT up, PLUS an explicit opt-in. The env gate is
            # load-bearing: these scenarios MUTATE the open TD project (scratch
            # container, cleaned up, never saved — but still), and a scheduled
            # `--all` sweep must never poke a live show file just because TD
            # happened to be open. Auto-SKIP otherwise (hosted CI, TD closed) —
            # same posture as s11's install-conditional SKIP.
            if os.environ.get("TD_EVAL_LIVE") != "1":
                return tvars, (f"requires '{req}' not satisfied (set "
                               "TD_EVAL_LIVE=1 to opt in — live scenarios "
                               "mutate the open TD project)")
            if not _td_reachable():
                return tvars, (f"requires '{req}' not satisfied (TouchDesigner "
                               "WebServer not reachable — open TD with "
                               "mcp_webserver_base.tox imported)")
        elif req == "derivative_bloom_tox":
            # D-D: the REAL Derivative bloom.tox from the local TouchDesigner
            # install (app.samplesFolder convention on disk). Never committed,
            # never staged — s11 auto-SKIPs where TD is absent (hosted CI).
            cand = os.environ.get("TD_BLOOM_TOX")
            if not cand:
                hits = sorted(globmod.glob(
                    r"C:/Program Files/Derivative/TouchDesigner*/Samples/Palette/"
                    r"ImageFilters/bloom.tox"))
                cand = hits[-1] if hits else None
            if not cand or not Path(cand).exists():
                return tvars, f"requires '{req}' not satisfied (no local TouchDesigner install)"
            tvars["BLOOM_TOX"] = Path(cand).as_posix()
        else:
            return tvars, f"unknown requires entry '{req}' (treated as unsatisfied)"
    return tvars, None


def ensure_fixtures(names: list) -> None:
    missing = [n for n in names or [] if not (FIXTURES_GENERATED / n).exists()]
    if missing:
        sys.path.insert(0, str(AGENT_EVAL_DIR / "fixtures"))
        import make_fixtures
        make_fixtures.main()
    for n in names or []:
        if not (FIXTURES_GENERATED / n).exists():
            raise SystemExit(f"fixture '{n}' unavailable after generation")


def stage_fixtures(scenario: dict, work: Path) -> None:
    names = scenario.get("fixtures") or []
    if not names:
        return
    ensure_fixtures(names)
    assets = work / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for n in names:
        shutil.copy2(FIXTURES_GENERATED / n, assets / n)


def template_prompt(scenario: dict, work: Path, tvars: dict) -> str:
    p = scenario["prompt"].replace("{{RUN_DIR}}", work.resolve().as_posix())
    for k, v in tvars.items():
        p = p.replace("{{" + k + "}}", v)
    return p


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
def build_identity(cfg: dict, lane: str, model_id: str | None) -> dict:
    import inproc
    ident = {
        "scenario_set_version": cfg["scenario_set_version"],
        "model_id": model_id if lane == "model" else None,
        "cli_version": identity_mod.cli_version(cfg.get("cli", "claude"))
        if lane == "model" else None,
        "server_version": inproc.server_version(),
        "tool_inventory_hash": identity_mod.tool_inventory_hash(inproc.tool_names()),
        # The separate td-builder-live surface, stamped from its STATIC tool
        # list (no running TD needed). Proven blind spot: the offline hash
        # stayed constant across the live 21→22 get_glsl_status change.
        "live_tool_inventory_hash": identity_mod.tool_inventory_hash(
            inproc.live_tool_names()),
        "guidance_hash": identity_mod.sha256_text(
            GUIDANCE_PATH.read_text(encoding="utf-8")),
        # Soft-warn tier (AGENT_IDENTITY_WARN_FIELDS): the engine
        # builder/validation code that produced this run. Closes the
        # server_version blind spot; warns on drift, never refuses.
        "engine_code_hash": identity_mod.engine_code_hash(
            REPO_ROOT / "MCP" / "engine"),
        # Informational only — in neither field tuple, never compared.
        "git_sha": identity_mod.git_sha(REPO_ROOT),
    }
    ident.update(identity_mod.kb_identity(kb_root(), extra_roots=(REPO_ROOT,)))
    return ident


# ---------------------------------------------------------------------------
# Lane M — headless claude -p
# ---------------------------------------------------------------------------
def _cli_exe(cfg: dict) -> str:
    exe = shutil.which(cfg.get("cli", "claude"))
    if not exe:
        raise SystemExit("claude CLI not found on PATH (Lane M needs the logged-in CLI)")
    return exe


def _subprocess_env() -> dict:
    env = dict(os.environ)
    # D-A: subscription auth only. Strip every key-shaped credential so the
    # subprocess can only use the logged-in CLI; also strip model overrides.
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL",
                "ANTHROPIC_SMALL_FAST_MODEL", "ANTHROPIC_BASE_URL"):
        env.pop(var, None)
    return env


def allowed_tools(live: bool) -> list:
    """Lane M --allowedTools names. Offline scenarios: the fixed 17-tool
    surface. Live scenarios additionally allow the td-builder-live tools MINUS
    save_td_project — the PERSISTENCE boundary: everything else a live
    scenario can break is recoverable precisely because the open project is
    never written to disk, so the save tool stays off the allowlist entirely
    (review F2; the scenarios' tool_not_called assertion still scores any
    attempt, but the damage path is removed). Residual soft boundary:
    execute_python_script could call project.save(); the live server's
    non-negotiables forbid it."""
    names = [MCP_PREFIX + t for t in OFFLINE_TOOLS]
    if live:
        import inproc
        names += [LIVE_MCP_PREFIX + t for t in inproc.live_tool_names()
                  if t != "save_td_project"]
    return names


def run_model_once(scenario: dict, trial_dir: Path, cfg: dict, model_id: str,
                   guided: bool, tvars: dict) -> tuple[NormalizedRun, Path]:
    work = trial_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    stage_fixtures(scenario, work)
    prompt = template_prompt(scenario, work, tvars)
    (trial_dir / "prompt.txt").write_text(prompt, encoding="utf-8")

    # Live-surface scenarios also register td-builder-live and allow its tools;
    # offline scenarios keep the fixed 17-tool surface (hermeticity unchanged).
    live = scenario.get("surface") == "live"
    tmpl = MCP_LIVE_TMPL_PATH if live else MCP_TMPL_PATH
    mcp_cfg = tmpl.read_text(encoding="utf-8") \
        .replace("{{PYTHON}}", Path(sys.executable).as_posix()) \
        .replace("{{REPO_ROOT}}", REPO_ROOT.as_posix())
    cfg_path = trial_dir / "mcp.eval.json"
    cfg_path.write_text(mcp_cfg, encoding="utf-8")

    allowed = ",".join(allowed_tools(live))
    disallowed = ",".join(DISALLOWED_BUILTINS)
    cmd = [_cli_exe(cfg), "-p", "--model", model_id,
           "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(cfg_path), "--strict-mcp-config",
           "--allowedTools", allowed, "--disallowedTools", disallowed]
    if guided:
        cmd += ["--append-system-prompt", GUIDANCE_PATH.read_text(encoding="utf-8")]

    timeout_s = (scenario.get("budgets") or {}).get("timeout_s",
                                                    cfg["default_timeout_s"])
    t0 = time.time()
    runner_error = None
    stdout, stderr, rc = "", "", None
    try:
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              cwd=str(work), env=_subprocess_env(),
                              timeout=timeout_s)
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or b"").decode("utf-8", "replace") \
            if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode("utf-8", "replace") \
            if isinstance(e.stderr, bytes) else (e.stderr or "")
        runner_error = f"timeout after {timeout_s}s (wall-clock budget)"
    except OSError as e:
        runner_error = f"spawn failed: {e}"

    transcript = trial_dir / "transcript.jsonl"
    transcript.write_text(stdout or "", encoding="utf-8")
    (trial_dir / "stderr.log").write_text(stderr or "", encoding="utf-8")

    run = parse_stream_json((stdout or "").splitlines())
    run.lane = "model"
    if run.duration_s is None:
        run.duration_s = round(time.time() - t0, 2)
    if runner_error:
        run.runner_error = runner_error
    elif rc not in (0, None) and run.raw_result_event is None:
        run.runner_error = f"cli exited {rc} with no result event; stderr tail: " \
                           f"{(stderr or '')[-300:]}"
    (trial_dir / "meta.json").write_text(json.dumps({
        "scenario": scenario["id"], "returncode": rc,
        "timeout_s": timeout_s, "work_dir": work.resolve().as_posix(),
        "guided": guided, "model_requested": model_id,
        "model_observed": run.model_id,
    }, indent=2), encoding="utf-8")
    return run, work


# ---------------------------------------------------------------------------
# Lane R — in-process replay of blessed traces
# ---------------------------------------------------------------------------
def _template_args(obj, work: Path, tvars: dict):
    if isinstance(obj, str):
        out = obj.replace("{{RUN_DIR}}", work.resolve().as_posix())
        for k, v in tvars.items():
            out = out.replace("{{" + k + "}}", v)
        return out
    if isinstance(obj, list):
        return [_template_args(x, work, tvars) for x in obj]
    if isinstance(obj, dict):
        return {k: _template_args(v, work, tvars) for k, v in obj.items()}
    return obj


def run_replay_once(scenario: dict, trial_dir: Path, tvars: dict) -> tuple[NormalizedRun, Path]:
    import inproc
    work = trial_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    stage_fixtures(scenario, work)

    trace_path = TRACES_DIR / f"{scenario['id']}.jsonl"
    run = NormalizedRun(lane="replay")
    if not trace_path.exists():
        run.runner_error = f"no blessed trace at {trace_path.name}"
        return run, work

    inproc.ensure_warm()
    probe = inproc.get_probe()

    # Connection barrier, replay-side mirror (R-3): a mandatory
    # get_server_info preamble — positive evidence before any scored call.
    info = probe.call("get_server_info", {})
    if not info.ok:
        run.runner_error = "in-process server failed get_server_info preamble"
        return run, work
    run.connection_evidence = "in_process"

    # Live-surface scenarios replay their live-tool calls against the
    # in-process td-builder-live server (reached only when td_live_running
    # held, i.e. TD is up). Same barrier: positive get_td_info evidence first.
    live_probe, live_names = None, frozenset()
    if scenario.get("surface") == "live":
        live_probe = inproc.get_live_probe()
        live_names = frozenset(inproc.live_tool_names())
        td_info = live_probe.call("get_td_info", {})
        if not td_info.ok:
            run.runner_error = "in-process live server failed get_td_info preamble"
            return run, work
        run.live_connection_evidence = "in_process"

    steps = [json.loads(ln) for ln in
             trace_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    t0 = time.time()
    for step in steps:
        if "_meta" in step:
            continue
        args = _template_args(step.get("args") or {}, work, tvars)
        is_live = live_probe is not None and step["tool"] in live_names
        r = (live_probe if is_live else probe).call(step["tool"], args)
        run.tool_calls.append(ToolCall(name=step["tool"], args=args,
                                       ok=r.ok, result_text=r.text, live=is_live))
    run.duration_s = round(time.time() - t0, 2)
    (trial_dir / "replay_calls.json").write_text(json.dumps(
        [{"tool": tc.name, "ok": tc.ok} for tc in run.tool_calls], indent=2),
        encoding="utf-8")
    return run, work


# ---------------------------------------------------------------------------
# Sweep orchestration
# ---------------------------------------------------------------------------
def select_scenarios(args) -> list:
    paths = sorted(SCENARIOS_DIR.glob("s*.json"))
    scenarios = [load_scenario(p) for p in paths]
    if args.scenario:
        wanted = set(args.scenario)
        scenarios = [s for s in scenarios
                     if s["id"] in wanted or s["id"].split("_")[0] in wanted]
        missing = wanted - {s["id"] for s in scenarios} \
            - {s["id"].split("_")[0] for s in scenarios}
        if missing:
            raise SystemExit(f"unknown scenario(s): {sorted(missing)}")
    return scenarios


def _score_one(scenario, run, work, cfg):
    scenario = dict(scenario)
    scenario["_tolerated_builtin_tools"] = cfg.get("tolerated_builtin_tools") or []
    return score_scenario(scenario, run, work)


def run_sweep(args, cfg, scenarios, lane, model_id, identity) -> dict:
    run_id = args.run_id or f"{lane}-{time.strftime('%Y%m%d-%H%M%S')}"
    root = Path(args.runs_dir) if args.runs_dir else RUNS_DIR
    sweep_dir = root / run_id
    sweep_dir.mkdir(parents=True, exist_ok=False)
    spend_cap = args.spend_cap if args.spend_cap is not None \
        else cfg["sweep_spend_cap_usd"]
    spent = 0.0
    aborted = None

    n_trials = args.n if args.capture_baseline else args.k
    results: dict[str, list] = {}

    for sc in scenarios:
        sid = sc["id"]
        tvars, skip_reason = resolve_requires(sc.get("requires"))
        # Replay lane: a scenario with no blessed trace is a SKIP (precondition
        # absent), never an ERROR — the replay-gate only covers what's blessed.
        if lane == "replay" and not skip_reason \
                and not (TRACES_DIR / f"{sid}.jsonl").exists():
            skip_reason = "no blessed trace (not yet captured via --bless)"
        trials = []
        for t in range(n_trials):
            trial_dir = sweep_dir / (sid if n_trials == 1 else f"{sid}.t{t + 1}")
            trial_dir.mkdir(parents=True, exist_ok=True)
            if skip_reason:
                res = score_mod.ScoreResult(scenario_id=sid, lane=lane,
                                            verdict="SKIP", error=skip_reason)
            elif aborted:
                res = score_mod.ScoreResult(
                    scenario_id=sid, lane=lane, verdict="ERROR",
                    error=f"sweep aborted: {aborted}")
            else:
                if lane == "model":
                    run, work = run_model_once(sc, trial_dir, cfg, model_id,
                                               args.config != "bare", tvars)
                    spent += float(run.cost_usd or 0.0)
                else:
                    run, work = run_replay_once(sc, trial_dir, tvars)
                res = _score_one(sc, run, work, cfg)
                if spend_cap and spent > spend_cap:
                    # R-1: the spend cap is a sweep-level HARD budget. The run
                    # that crossed it stays scored; everything after is ERROR.
                    aborted = f"spend cap ${spend_cap:.2f} exceeded (${spent:.2f})"
            (trial_dir / "score.json").write_text(
                json.dumps(res.to_json(), indent=2, sort_keys=True), encoding="utf-8")
            trials.append(res)
            print(f"[{lane}] {sid} trial {t + 1}/{n_trials}: {res.verdict}"
                  + (f" ({res.error})" if res.error else ""), file=sys.stderr)

        # Escalation (§5): gate sweeps at k=1 — a FAIL triggers reruns,
        # red iff <2-of-3 pass. Never for baseline capture or ERROR/SKIP, and
        # suppressed by --no-escalation (shakeout sweeps where reruns just burn
        # spend on known rot).
        if (lane == "model" and not args.capture_baseline and n_trials == 1
                and not args.no_escalation
                and trials[0].verdict == "FAIL" and not aborted):
            for r in range(cfg["escalation_reruns"]):
                trial_dir = sweep_dir / f"{sid}.esc{r + 1}"
                trial_dir.mkdir(parents=True, exist_ok=True)
                run, work = run_model_once(sc, trial_dir, cfg, model_id,
                                           args.config != "bare", tvars)
                spent += float(run.cost_usd or 0.0)
                res = _score_one(sc, run, work, cfg)
                (trial_dir / "score.json").write_text(
                    json.dumps(res.to_json(), indent=2, sort_keys=True),
                    encoding="utf-8")
                trials.append(res)
                print(f"[{lane}] {sid} escalation {r + 1}: {res.verdict}",
                      file=sys.stderr)
        results[sid] = trials

    return {"run_id": run_id, "sweep_dir": sweep_dir, "results": results,
            "spent_usd": round(spent, 4), "aborted": aborted,
            "identity": identity, "lane": lane}


def combine_verdict(trials: list) -> str:
    """m-of-k over the SCORED (PASS/FAIL) trials; ERROR/SKIP are excluded from
    the denominator and dominate only when nothing scored.

    FAIL requires FAILs to be a STRICT MAJORITY of scored trials — not merely
    "not a pass-majority". This is load-bearing: an ERROR in an escalation
    rerun must never flip a wash into a FAIL. e.g. [FAIL, PASS, ERROR] scores as
    a 1-1 wash → PASS (don't cry regression on a harness fault), and
    [FAIL, PASS] (tie) → PASS. A lone [FAIL] with no clean rerun → FAIL (the one
    signal we have is FAIL); [FAIL, FAIL, PASS] → FAIL (2-of-3 fail)."""
    scored = [t for t in trials if t.verdict in ("PASS", "FAIL")]
    if not scored:
        if any(t.verdict == "SKIP" for t in trials):
            return "SKIP"
        return "ERROR"
    fails = sum(1 for t in scored if t.verdict == "FAIL")
    return "FAIL" if fails * 2 > len(scored) else "PASS"


def write_outputs(args, cfg, sweep: dict, scenarios: list) -> int:
    sweep_dir: Path = sweep["sweep_dir"]
    results = sweep["results"]
    by_id = {s["id"]: s for s in scenarios}

    combined = {sid: combine_verdict(trials) for sid, trials in results.items()}
    fingerprints = {sid: sorted({fp for t in trials for fp in t.fingerprints})
                    for sid, trials in results.items()}

    # canonical verdict set — NO timing/cost/run-id inside (Lane R determinism
    # is proven by byte-comparing this file across consecutive sweeps)
    verdicts = {
        "lane": sweep["lane"],
        "identity": sweep["identity"],
        "scenarios": {sid: {"verdict": combined[sid],
                            "fingerprints": fingerprints[sid],
                            "trials": [t.verdict for t in results[sid]]}
                      for sid in sorted(results)},
    }
    (sweep_dir / "verdicts.json").write_text(
        json.dumps(verdicts, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = {
        "run_id": sweep["run_id"], "lane": sweep["lane"],
        "spent_usd": sweep["spent_usd"], "aborted": sweep["aborted"],
        "identity": sweep["identity"],
        "scenarios": {sid: {
            "verdict": combined[sid],
            "gate_eligible": bool(by_id[sid].get("gate")),
            "trials": [t.to_json() for t in results[sid]],
        } for sid in sorted(results)},
    }
    (sweep_dir / "report.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")

    if not args.no_stage:
        _stage_markdown(sweep, combined, fingerprints, by_id)

    n_err = sum(1 for v in combined.values() if v == "ERROR")
    lane_name = "replay-gate" if sweep["lane"] == "replay" else "agent-gate"
    print(f"\n{'=' * 64}\n{lane_name.upper()} — run {sweep['run_id']}")
    for sid in sorted(combined):
        gate = "gate" if by_id[sid].get("gate") else "aspirational"
        fps = f"  [{'; '.join(fingerprints[sid][:3])}]" if fingerprints[sid] else ""
        print(f"  {combined[sid]:5s} {sid:22s} ({gate}){fps}")
    print(f"  spend: ${sweep['spent_usd']:.2f}"
          + (f"  ABORTED: {sweep['aborted']}" if sweep["aborted"] else ""))
    print("=" * 64)
    if sweep["lane"] == "replay":
        print("NOTE: this is the REPLAY-GATE (harness integrity under blessed "
              "traces). It is NOT the agent-gate — no model was measured.")

    gate_reds = [sid for sid, v in combined.items()
                 if v == "FAIL" and by_id[sid].get("gate")]
    if sweep["aborted"] or n_err:
        return 2
    return 1 if gate_reds else 0


def _stage_markdown(sweep, combined, fingerprints, by_id):
    sd = stage_dir()
    sd.mkdir(parents=True, exist_ok=True)
    lane_name = "replay-gate" if sweep["lane"] == "replay" else "agent-gate"
    lines = [
        f"# Agent eval — {lane_name} run `{sweep['run_id']}`", "",
        "Lane semantics (honesty rule): **replay-gate** = tool contract + KB + "
        "builder under blessed traces (deterministic, no model); **agent-gate** "
        "= model-in-the-loop. A green replay-gate never counts as the "
        "agent-gate passing.", "",
        "| scenario | verdict | tier | failure fingerprints |", "|---|---|---|---|",
    ]
    for sid in sorted(combined):
        tier = "gate" if by_id[sid].get("gate") else "aspirational"
        lines.append(f"| {sid} | {combined[sid]} | {tier} | "
                     f"{'; '.join(fingerprints[sid]) or '—'} |")
    lines += ["", f"Spend: ${sweep['spent_usd']:.2f}"
              + (f" — **ABORTED: {sweep['aborted']}**" if sweep["aborted"] else ""),
              "", "Identity:", "```json",
              json.dumps(sweep["identity"], indent=2, sort_keys=True), "```"]
    (sd / "AGENT_EVAL.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copy2(sweep["sweep_dir"] / "report.json", sd / "details.json")


# ---------------------------------------------------------------------------
# Baseline capture / compare / bless
# ---------------------------------------------------------------------------
def capture_baseline(args, cfg, sweep: dict, scenarios: list):
    by_id = {s["id"]: s for s in scenarios}
    out = {
        "captured_with": {"lane": sweep["lane"], "n": args.n,
                          "config": args.config, "run_id": sweep["run_id"]},
        "identity": sweep["identity"],
        "scenarios": {}, "gate_set": [], "aspirational_set": [],
        "unmeasurable_set": [],
    }
    for sid, trials in sorted(sweep["results"].items()):
        verdicts = [t.verdict for t in trials]
        scored = [v for v in verdicts if v in ("PASS", "FAIL")]
        pass_rate = (sum(1 for v in scored if v == "PASS") / len(scored)) \
            if scored else None
        fps: dict[str, int] = {}
        for t in trials:
            for fp in t.fingerprints:
                fps[fp] = fps.get(fp, 0) + 1
        med = {}
        for key in ("turns", "tool_calls", "cost_usd", "wall_s"):
            vals = [t.advisory.get(key) for t in trials
                    if t.advisory.get(key) is not None]
            med[key] = round(statistics.median(vals), 4) if vals else None
        out["scenarios"][sid] = {
            "version": by_id[sid]["version"],
            "gate_eligible": bool(by_id[sid].get("gate")),
            "n": len(trials), "verdicts": verdicts, "pass_rate": pass_rate,
            "failure_fingerprints": dict(sorted(fps.items())),
            "advisory_median": med,
        }
        # Gate membership is EARNED: 5/5 (or n/n) in this capture (§5).
        if by_id[sid].get("gate") and scored and pass_rate == 1.0 \
                and len(scored) == len(verdicts):
            out["gate_set"].append(sid)
        elif verdicts and all(v == "SKIP" for v in verdicts):
            pass  # skipped everywhere — neither set
        elif not scored:
            # every trial ERRORed — the harness never got a clean read; this is
            # NOT "the model can't do it" and must not hide in aspirational.
            out["unmeasurable_set"].append(sid)
        else:
            out["aspirational_set"].append(sid)
    BASELINE_PATH.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    sd = stage_dir()
    sd.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BASELINE_PATH, sd / "baseline.json")
    print(f"\nbaseline captured -> {BASELINE_PATH}\n  gate_set: {out['gate_set']}"
          f"\n  aspirational: {out['aspirational_set']}"
          + (f"\n  UNMEASURABLE (all-ERROR — harness fault, investigate): "
             f"{out['unmeasurable_set']}" if out['unmeasurable_set'] else ""))


def compare_against(args, sweep: dict) -> int:
    prior = json.loads(Path(args.compare).read_text(encoding="utf-8"))
    fields = identity_mod.AGENT_IDENTITY_FIELDS
    if sweep["lane"] == "replay":
        # Cross-lane compare (the documented replay-vs-committed-baseline flow):
        # a replay sweep has NO model or CLI in the loop, so those two fields
        # are structurally None and comparing them to a model-lane baseline
        # would refuse forever. The comparison still refuses on every
        # environment field (scenario set, server, KB, tool surfaces, guidance).
        fields = tuple(f for f in fields if f not in ("model_id", "cli_version"))
        print("[compare] replay lane: model_id/cli_version excluded from the "
              "identity check (model-lane facts; replay has neither)",
              file=sys.stderr)
    mism, unknown = identity_mod.identity_mismatches(
        sweep["identity"], prior.get("identity"), fields)
    if unknown:
        print(f"[compare] WARNING: prior baseline has no identity for "
              f"{unknown} — treating as unknown, proceeding.", file=sys.stderr)
    if mism:
        print("[compare] identity mismatch vs prior baseline:", file=sys.stderr)
        for f, old, cur in mism:
            print(f"    {f}: prior={old!r} current={cur!r}", file=sys.stderr)
        if not args.allow_identity_drift:
            print("[compare] REFUSING comparison (§7). Re-baseline, or pass "
                  "--allow-identity-drift to proceed marked NON-COMPARABLE.",
                  file=sys.stderr)
            return 3
        print("[compare] NON-COMPARABLE (identity drift overridden)", file=sys.stderr)

    # Soft tier: warn-only, exit-code-neutral by construction. Printed to
    # stdout (unlike the hard-tier stderr lines) so it reaches CI's
    # $GITHUB_STEP_SUMMARY through the tee alongside the DELTA table.
    warn_mism, warn_unknown = identity_mod.identity_mismatches(
        sweep["identity"], prior.get("identity"),
        identity_mod.AGENT_IDENTITY_WARN_FIELDS)
    for f, old, cur in warn_mism:
        print(f"[compare] WARNING (soft identity) {f}: prior={old!r} "
              f"current={cur!r} — engine code drifted since baseline; deltas "
              f"may reflect code changes, not regressions. Proceeding.")
    if warn_unknown:
        print(f"[compare] WARNING: prior baseline has no soft identity for "
              f"{warn_unknown} — unknown, proceeding (stamped at next capture).")

    combined = {sid: combine_verdict(t) for sid, t in sweep["results"].items()}
    print(f"\nDELTA vs {args.compare}:")
    for sid in sorted(combined):
        pr = (prior.get("scenarios") or {}).get(sid, {}).get("pass_rate")
        cur = combined[sid]
        marker = ""
        if pr == 1.0 and cur == "FAIL":
            marker = "  <-- REGRESSION vs 5/5 baseline"
        elif pr not in (None, 1.0) and cur == "PASS":
            marker = "  (improved vs baseline)"
        print(f"  {sid:22s} baseline_pass_rate={pr}  now={cur}{marker}")
    return 0


def bless(args, cfg):
    root = Path(args.runs_dir) if args.runs_dir else RUNS_DIR
    sweep_dir = root / args.bless
    if not sweep_dir.is_dir():
        raise SystemExit(f"run '{args.bless}' not found under {root}")
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for score_file in sorted(sweep_dir.glob("*/score.json")):
        data = json.loads(score_file.read_text(encoding="utf-8"))
        if data.get("verdict") != "PASS" or data.get("lane") != "model":
            continue
        trial_dir = score_file.parent
        meta = json.loads((trial_dir / "meta.json").read_text(encoding="utf-8"))
        run = score_mod.load_transcript(trial_dir / "transcript.jsonl")
        work_posix = meta["work_dir"]
        sid = data["scenario"]
        sc_path = SCENARIOS_DIR / f"{sid}.json"
        sc_version = load_scenario(sc_path)["version"] if sc_path.exists() else None
        lines = [json.dumps({"_meta": {
            "scenario": sid, "blessed_from": f"{args.bless}/{trial_dir.name}",
            "scenario_version": sc_version, "note":
                "calls-only trace (tool + args, {{RUN_DIR}}-templated); result "
                "envelopes deliberately NOT stored — replay re-executes and "
                "re-scores (design §7: storing them would leak KB-derived text "
                "into the repo)."}})]
        # Robust {{RUN_DIR}} templating: the model may echo the path with
        # backslashes or a trailing slash. Normalize both the JSON and the
        # needle to forward-slash + strip trailing slash before replacing, and
        # WARN if a build's output_dir failed to template (would hard-code an
        # absolute machine path into the committed trace).
        needle = work_posix.rstrip("/")
        for tc in run.tool_calls:
            args_json = json.dumps({"tool": tc.name, "args": tc.args})
            args_json = args_json.replace("\\\\", "/").replace(needle, "{{RUN_DIR}}")
            lines.append(args_json)
            if tc.name == "td_build_project":
                od = str((tc.args or {}).get("output_dir") or "")
                if od and needle.lower() not in od.replace("\\", "/").lower():
                    print(f"  WARNING: {sid} build output_dir {od!r} does not "
                          f"contain the run dir — trace may hard-code a path")
        out = TRACES_DIR / f"{sid}.jsonl"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # Guard: no absolute machine path may survive into a committed trace.
        residue = out.read_text(encoding="utf-8")
        if needle.lower() in residue.lower():
            print(f"  WARNING: {sid} trace still contains an absolute path after "
                  f"templating — inspect traces/{sid}.jsonl before committing")
        print(f"blessed {sid} <- {trial_dir.name} ({len(run.tool_calls)} calls)")
        n += 1
    if not n:
        print("nothing blessed (no PASSing model trials in that run)")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="TD Builder agent eval (two lanes)")
    ap.add_argument("--lane", choices=["model", "replay"], default=None)
    ap.add_argument("--scenario", action="append", default=None,
                    help="run only these scenario ids (repeatable; sNN prefix ok)")
    ap.add_argument("--all", action="store_true",
                    help="(model lane) run all scenarios, not just gate-eligible")
    ap.add_argument("--k", type=int, default=None,
                    help="trials per scenario (default: config gate_k=1 + escalation)")
    ap.add_argument("--n", type=int, default=None,
                    help="baseline-capture trials per scenario (default config baseline_n)")
    ap.add_argument("--capture-baseline", action="store_true")
    ap.add_argument("--compare", default=None,
                    help="prior baseline.json to diff against (refuses on identity mismatch)")
    ap.add_argument("--allow-identity-drift", action="store_true")
    ap.add_argument("--bless", default=None, metavar="RUN_ID",
                    help="promote a passing model run's tool sequences to traces/")
    ap.add_argument("--config", choices=["guided", "bare"], default="guided",
                    help="guided = canonical guidance injected (the documented "
                         "product, gates); bare = weakest-client floor (advisory)")
    ap.add_argument("--model", default=None,
                    help="model override (pilot/pin-resolution only; the "
                         "committed pin lives in config.json)")
    ap.add_argument("--spend-cap", type=float, default=None)
    ap.add_argument("--no-escalation", action="store_true",
                    help="suppress the FAIL→2-rerun escalation (shakeout sweeps)")
    ap.add_argument("--runs-dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--run-id", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--no-stage", action="store_true",
                    help="skip staging the human report to New KB build/Output")
    args = ap.parse_args()

    cfg = load_config()
    if args.bless:
        bless(args, cfg)
        return 0
    if not args.lane:
        ap.error("--lane model|replay is required (or --bless RUN_ID)")

    args.k = args.k or cfg["gate_k"]
    args.n = args.n or cfg["baseline_n"]

    scenarios = select_scenarios(args)
    if args.lane == "model" and not (args.all or args.scenario
                                     or args.capture_baseline):
        # routine model sweeps default to the gate-eligible set (§5); the
        # weekly full sweep passes --all
        scenarios = [s for s in scenarios if s.get("gate")]

    model_id = None
    if args.lane == "model":
        model_id = args.model or cfg.get("model_id")
        if not model_id:
            raise SystemExit(
                "config.json model_id is unset (D-B pin). Resolve the exact "
                "dated snapshot at pilot time (--model sonnet for the "
                "resolution run, then commit the observed id to config.json).")

    identity = build_identity(cfg, args.lane, model_id)
    sweep = run_sweep(args, cfg, scenarios, args.lane, model_id, identity)
    rc = write_outputs(args, cfg, sweep, scenarios)

    if args.capture_baseline:
        capture_baseline(args, cfg, sweep, scenarios)
    if args.compare:
        rc2 = compare_against(args, sweep)
        rc = rc2 if rc2 else rc
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

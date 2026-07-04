#!/usr/bin/env python3
r"""Crash-safe checkpoint for an in-flight baseline capture.

Reconstructs a PARTIAL baseline.json + blesses available traces from the
per-trial score.json / transcript.jsonl files already on disk under a run dir —
WITHOUT re-running anything and WITHOUT loading the KB (the trials are already
scored). Run it periodically (see the --loop-friendly exit codes) so a power
loss mid-capture leaves the captured model work assembled and committable
instead of stranded as loose trial files.

  py -3.11 eval/agent_eval/checkpoint.py --run baseline-n5
  py -3.11 eval/agent_eval/checkpoint.py --run baseline-n5 --n 5   # expected trials

Writes eval/agent_eval/baseline.json (marked partial until every scenario has n
scored trials) and eval/agent_eval/traces/<sid>.jsonl (calls-only, templated)
for every scenario with >=1 PASS trial. Exit 0 always (a checkpoint never fails
the loop); prints a one-line progress summary.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

AGENT_EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_EVAL_DIR))

import score as score_mod                       # noqa: E402  (light: no KB load)
from run_agent_eval import (BASELINE_PATH, RUNS_DIR, SCENARIOS_DIR,   # noqa: E402
                            TRACES_DIR, combine_verdict, load_config,
                            load_scenario)


def _scenario_versions() -> dict:
    out = {}
    for p in sorted(SCENARIOS_DIR.glob("s*.json")):
        sc = load_scenario(p)
        out[sc["id"]] = sc
    return out


def _trial_dirs_for(sweep_dir: Path, sid: str) -> list:
    """All trial dirs for a scenario id (sid, sid.tN, sid.escN)."""
    hits = []
    for d in sorted(sweep_dir.iterdir()):
        if not d.is_dir():
            continue
        name = d.name
        if name == sid or name.startswith(f"{sid}.t") or name.startswith(f"{sid}.esc"):
            if (d / "score.json").exists():
                hits.append(d)
    return hits


def _bless_from(trial_dir: Path, sid: str, sc_version) -> int:
    """Write a calls-only, {{RUN_DIR}}-templated trace from a PASSing model
    trial. Returns the number of calls blessed (0 if not blessable)."""
    meta_p, tr_p = trial_dir / "meta.json", trial_dir / "transcript.jsonl"
    if not (meta_p.exists() and tr_p.exists()):
        return 0
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    work_posix = meta.get("work_dir") or ""
    run = score_mod.load_transcript(tr_p)
    if not run.tool_calls:
        return 0
    needle = work_posix.rstrip("/")
    lines = [json.dumps({"_meta": {
        "scenario": sid, "blessed_from": f"{trial_dir.parent.name}/{trial_dir.name}",
        "scenario_version": sc_version,
        "note": "calls-only trace (tool + args, {{RUN_DIR}}-templated); result "
                "envelopes deliberately NOT stored — replay re-executes and "
                "re-scores. Written by checkpoint.py from a passing capture trial."}})]
    for tc in run.tool_calls:
        aj = json.dumps({"tool": tc.name, "args": tc.args})
        if needle:
            aj = aj.replace("\\\\", "/").replace(needle, "{{RUN_DIR}}")
        lines.append(aj)
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    (TRACES_DIR / f"{sid}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(run.tool_calls)


def checkpoint(run_id: str, n_expected: int, bless: bool) -> dict:
    sweep_dir = RUNS_DIR / run_id
    if not sweep_dir.is_dir():
        raise SystemExit(f"run dir not found: {sweep_dir}")
    scenarios = _scenario_versions()

    identity = None
    for cand in sorted(sweep_dir.glob("*/score.json")):
        # identity is stamped into verdicts/report at sweep end; before that,
        # reuse the last committed baseline's identity if present, else None.
        break
    prior = json.loads(BASELINE_PATH.read_text(encoding="utf-8")) \
        if BASELINE_PATH.exists() else {}
    identity = prior.get("identity")

    out = {
        "_checkpoint": True,
        "captured_with": {"lane": "model", "n": n_expected, "config": "guided",
                          "run_id": run_id, "status": "IN-PROGRESS (partial "
                          "checkpoint — reconstructed from on-disk trials)"},
        "identity": identity,
        "scenarios": {}, "gate_set": [], "aspirational_set": [],
        "unmeasurable_set": [], "incomplete_set": [],
    }
    total_trials = 0
    blessed = 0
    for sid, sc in scenarios.items():
        tdirs = _trial_dirs_for(sweep_dir, sid)
        results = [json.loads((d / "score.json").read_text(encoding="utf-8")) for d in tdirs]
        total_trials += len(results)
        verdicts = [r["verdict"] for r in results]
        scored = [v for v in verdicts if v in ("PASS", "FAIL")]
        pass_rate = (sum(1 for v in scored if v == "PASS") / len(scored)) if scored else None
        fps: dict = {}
        for r in results:
            for f in r.get("fingerprints", []):
                fps[f] = fps.get(f, 0) + 1
        med = {}
        for key in ("turns", "tool_calls", "cost_usd", "wall_s"):
            vals = [r["advisory"].get(key) for r in results
                    if r.get("advisory", {}).get(key) is not None]
            med[key] = round(statistics.median(vals), 4) if vals else None
        complete = len(verdicts) >= n_expected
        out["scenarios"][sid] = {
            "version": sc["version"], "gate_eligible": bool(sc.get("gate")),
            "n_captured": len(verdicts), "n_expected": n_expected,
            "complete": complete, "verdicts": verdicts, "pass_rate": pass_rate,
            "failure_fingerprints": dict(sorted(fps.items())), "advisory_median": med,
        }
        # gate membership only when COMPLETE and clean n/n PASS
        if complete and sc.get("gate") and scored and pass_rate == 1.0 \
                and len(scored) == len(verdicts):
            out["gate_set"].append(sid)
        elif not verdicts:
            out["incomplete_set"].append(sid)
        elif not complete:
            out["incomplete_set"].append(sid)
        elif all(v == "SKIP" for v in verdicts):
            pass
        elif not scored:
            out["unmeasurable_set"].append(sid)
        else:
            out["aspirational_set"].append(sid)

        if bless and any(r["verdict"] == "PASS" and r.get("lane") == "model" for r in results):
            first_pass = next(d for d, r in zip(tdirs, results)
                              if r["verdict"] == "PASS" and r.get("lane") == "model")
            blessed += 1 if _bless_from(first_pass, sid, sc["version"]) else 0

    BASELINE_PATH.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    out["_meta_total_trials"] = total_trials
    out["_meta_blessed"] = blessed
    return out


def main():
    ap = argparse.ArgumentParser(description="Crash-safe partial-baseline checkpoint")
    ap.add_argument("--run", required=True, help="run id under runs/ (e.g. baseline-n5)")
    ap.add_argument("--n", type=int, default=None, help="expected trials per scenario")
    ap.add_argument("--no-bless", action="store_true", help="skip trace blessing")
    args = ap.parse_args()
    n = args.n or load_config().get("baseline_n", 5)
    out = checkpoint(args.run, n, bless=not args.no_bless)
    done = sum(1 for s in out["scenarios"].values() if s["complete"])
    print(f"[checkpoint] {out['_meta_total_trials']} trials on disk; "
          f"{done}/{len(out['scenarios'])} scenarios complete; "
          f"gate={len(out['gate_set'])} aspirational={len(out['aspirational_set'])} "
          f"incomplete={len(out['incomplete_set'])}; "
          f"blessed {out['_meta_blessed']} traces -> baseline.json + traces/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

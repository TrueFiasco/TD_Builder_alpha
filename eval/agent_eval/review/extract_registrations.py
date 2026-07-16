#!/usr/bin/env python3
r"""Harvest the LLM-authored registration text out of agent-eval runs.

WHY THIS EXISTS
    register_component makes the model author the words a component is FOUND by:
    a `summary`, some `use_cases`, and a `parameter_descriptions` line per custom
    parameter. No gate can score that. A vacuous summary commits, reloads and
    reports `retrievable: true` exactly like a discriminating one -- the scenarios
    (s19-s21) prove the plumbing, and prove nothing at all about the prose.

    So: pull every authored field out of the transcripts, sit it next to what the
    component ACTUALLY is (parsed from the same run's `prepare` skeleton -- the
    ground truth the model was handed), and render one skimmable ledger the owner
    scores by eye against review/RUBRIC.md.

WHAT IT READS
    runs/<run-id>/<scenario>/transcript.jsonl   -- Lane M (authored text lives here)
    traces/<scenario>.jsonl                     -- blessed traces, with --traces.
        Calls-only by design (result envelopes are never committed), so entries
        sourced from a trace carry the authored args but no `actual` column.

LICENSE DISCIPLINE
    Only register_component's own args and results reach the ledger -- i.e. the
    user's own component data. KB-derived text (hybrid_search results, wiki
    content) is never read or written here, for the same reason bless() refuses
    to store result envelopes: this repo commits no KB content.

USAGE
    py -3.11 eval/agent_eval/review/extract_registrations.py --runs <run-id> --render
    py -3.11 eval/agent_eval/review/extract_registrations.py --render   # all runs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

AGENT_EVAL_DIR = Path(__file__).resolve().parent.parent
REVIEW_DIR = AGENT_EVAL_DIR / "review"
RUNS_DIR = AGENT_EVAL_DIR / "runs"
TRACES_DIR = AGENT_EVAL_DIR / "traces"
LEDGER_JSONL = REVIEW_DIR / "registration_quality.jsonl"
LEDGER_MD = REVIEW_DIR / "registration_quality.md"

sys.path.insert(0, str(AGENT_EVAL_DIR))
from score import parse_stream_json  # noqa: E402


# ---------------------------------------------------------------------------
# Harvest
# ---------------------------------------------------------------------------
def _authored(spec: dict) -> dict:
    """The fields the MODEL wrote (vs the ones it was handed)."""
    return {
        "summary": spec.get("summary"),
        "use_cases": spec.get("use_cases") or [],
        "parameter_descriptions": spec.get("parameter_descriptions") or {},
    }


def _actual_from_prepare(prepare_results: list, name: str) -> dict | None:
    """Ground truth for `name` from a prepare skeleton seen in the same run."""
    for sk in prepare_results:
        if sk.get("name") == name or name is None:
            return {
                "custom_parameters": sk.get("custom_parameters") or [],
                "inputs": [i.get("name") if isinstance(i, dict) else i
                           for i in (sk.get("inputs") or [])],
                "outputs": [o.get("name") if isinstance(o, dict) else o
                            for o in (sk.get("outputs") or [])],
                "contained_operators": sk.get("contained_operators") or [],
                "operator_count": sk.get("operator_count"),
                "wrapper": sk.get("wrapper"),
            }
    return None


def _spec_name(spec: dict) -> str:
    if spec.get("name"):
        return str(spec["name"])
    tox = str(spec.get("tox_path") or "")
    return Path(tox).name.split(".")[0] if tox else "<unnamed>"


def _entry_key(e: dict) -> str:
    """Dedup on scenario + comp + the authored content itself, so re-running the
    extractor over the same runs is idempotent but a genuinely new authoring
    (a re-capture, a prompt edit) lands as a new row."""
    blob = json.dumps([e["scenario"], e["component"], e["authored"]],
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def harvest_transcript(path: Path, scenario: str, run_id: str) -> list:
    run = parse_stream_json(path.read_text(encoding="utf-8").splitlines())
    calls = [tc for tc in run.tool_calls if tc.name == "register_component"]
    if not calls:
        return []

    # every skeleton this run saw, so a commit can be juxtaposed with its truth
    prepared: list = []
    for tc in calls:
        if not (tc.args or {}).get("prepare"):
            continue
        try:
            prepared.extend(json.loads(tc.result_text or "{}").get("prepared") or [])
        except (ValueError, AttributeError):
            continue

    meta = {}
    mp = path.parent / "meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}

    out = []
    for tc in calls:
        args = tc.args or {}
        if args.get("prepare"):
            continue                       # skeleton request, nothing authored yet
        for spec in args.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            name = _spec_name(spec)
            committed = {}
            try:
                for r in json.loads(tc.result_text or "{}").get("results") or []:
                    if r.get("name") == name:
                        committed = {k: r.get(k) for k in
                                     ("ok", "retrievable", "chunk_count",
                                      "entry_summary", "shadows_shipped",
                                      "operator_count")}
                        break
            except (ValueError, AttributeError):
                pass
            out.append({
                "scenario": scenario,
                "run_id": run_id,
                "component": name,
                "model": meta.get("model_id"),
                "source": "transcript",
                "authored": _authored(spec),
                "spec_verbatim": spec,
                "actual": _actual_from_prepare(prepared, name),
                "committed": committed,
            })
    return out


def harvest_trace(path: Path) -> list:
    """Blessed traces are calls-only: authored args survive, results do not."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            step = json.loads(line)
        except ValueError:
            continue
        if step.get("tool") != "register_component":
            continue
        args = step.get("args") or {}
        if args.get("prepare"):
            continue
        for spec in args.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            out.append({
                "scenario": path.stem,
                "run_id": "(blessed trace)",
                "component": _spec_name(spec),
                "model": None,
                "source": "trace",
                "authored": _authored(spec),
                "spec_verbatim": spec,
                "actual": None,     # calls-only trace: no skeleton was recorded
                "committed": {},
            })
    return out


def collect(run_selectors: list, include_traces: bool) -> list:
    entries = []
    roots = []
    if run_selectors:
        for sel in run_selectors:
            p = Path(sel)
            roots.append(p if p.is_dir() else RUNS_DIR / sel)
    elif RUNS_DIR.is_dir():
        roots = [d for d in sorted(RUNS_DIR.iterdir()) if d.is_dir()]

    for root in roots:
        if not root.is_dir():
            print(f"  (skip) no such run dir: {root}")
            continue
        for tpath in sorted(root.glob("*/transcript.jsonl")):
            trial = tpath.parent.name
            scenario = trial.split(".t")[0].split(".esc")[0]
            entries.extend(harvest_transcript(tpath, scenario, root.name))

    if include_traces and TRACES_DIR.is_dir():
        for tr in sorted(TRACES_DIR.glob("*.jsonl")):
            entries.extend(harvest_trace(tr))
    return entries


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def _fmt_par(p: dict) -> str:
    bits = []
    if p.get("menu"):
        bits.append("menu: " + "|".join(m.get("token", "?") for m in p["menu"]))
    if p.get("default") not in (None, ""):
        d = p["default"]
        bits.append("default " + (", ".join(str(x) for x in d)
                                  if isinstance(d, list) else str(d)))
    if p.get("min") is not None and p.get("max") is not None:
        bits.append(f"range {p['min']}..{p['max']}")
    return f"`{p.get('name')}`" + (f" — {'; '.join(bits)}" if bits else "")


def render(entries: list) -> str:
    L = [
        "# Registration quality ledger",
        "",
        "Every `summary` / `use_cases` / `parameter_descriptions` the model authored",
        "during a `register_component` scenario run, beside what the component",
        "actually is. Score by eye against [RUBRIC.md](RUBRIC.md) — 0–2 on each axis,",
        "one-word verdict. **Generated** by `review/extract_registrations.py --render`;",
        "the scoring lines are yours to fill in and keep.",
        "",
        f"Entries: **{len(entries)}**",
        "",
        "---",
        "",
    ]
    if not entries:
        L += ["_No registrations harvested yet — run a Lane M capture over s19–s21,",
              "then `extract_registrations.py --runs <run-id> --render`._", ""]
        return "\n".join(L)

    for e in entries:
        a, act = e["authored"], e["actual"]
        head = f"## {e['component']} — {e['scenario']}"
        sub = [x for x in (e["run_id"], e.get("model")) if x]
        L.append(head)
        if sub:
            L.append(f"<sub>{' · '.join(sub)}</sub>")
        L.append("")

        L.append("**Authored** (what the model wrote)")
        L.append("")
        L.append(f"> **summary** — {a['summary'] or '_(none)_'}")
        L.append(">")
        if a["use_cases"]:
            L.append("> **use_cases**")
            L += [f"> - {u}" for u in a["use_cases"]]
        else:
            L.append("> **use_cases** — _(none)_")
        L.append("")

        if a["parameter_descriptions"] or (act and act["custom_parameters"]):
            L.append("| parameter | authored description | actual (from skeleton) |")
            L.append("|---|---|---|")
            pars = {p.get("name"): p for p in (act["custom_parameters"] if act else [])}
            names = list(dict.fromkeys(
                list(a["parameter_descriptions"].keys()) + list(pars.keys())))
            for n in names:
                desc = a["parameter_descriptions"].get(n) or "_(not described)_"
                truth = _fmt_par(pars[n]) if n in pars else "_(no such parameter!)_"
                L.append(f"| `{n}` | {desc} | {truth} |")
            L.append("")

        if act:
            io = (f"in: {act['inputs'] or 'none'} · out: {act['outputs'] or 'none'}"
                  f" · {act['operator_count'] or len(act['contained_operators'])} inner ops"
                  f" ({', '.join(act['contained_operators'])})")
            L.append(f"**Actual I/O** — {io}")
            L.append("")
        else:
            L.append("**Actual** — _not available (calls-only trace; "
                     "re-run the extractor over the Lane M run for the skeleton)_")
            L.append("")

        c = e.get("committed") or {}
        if c:
            L.append(f"<sub>committed: retrievable={c.get('retrievable')} · "
                     f"chunks={c.get('chunk_count')} · "
                     f"shadows_shipped={c.get('shadows_shipped')}</sub>")
            L.append("")

        L.append("`Specificity: _/2   Correctness: _/2   Searchability: _/2   "
                 "→ verdict: ____`")
        L += ["", "---", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Harvest LLM-authored register_component text into a review ledger")
    ap.add_argument("--runs", nargs="*", default=None,
                    help="run id(s) or path(s) under runs/ (default: every run)")
    ap.add_argument("--traces", action="store_true",
                    help="also harvest blessed traces (authored args only, no actual)")
    ap.add_argument("--render", action="store_true",
                    help="rebuild registration_quality.md from the jsonl")
    args = ap.parse_args()

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    existing = []
    if LEDGER_JSONL.exists():
        existing = [json.loads(l) for l in
                    LEDGER_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    seen = {e.get("_key") for e in existing}

    added = 0
    for e in collect(args.runs, args.traces):
        e["_key"] = _entry_key(e)
        if e["_key"] in seen:
            continue
        seen.add(e["_key"])
        existing.append(e)
        added += 1

    LEDGER_JSONL.write_text(
        "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n"
                for e in existing), encoding="utf-8")

    if added:
        print(f"harvested {added} new registration(s) -> {LEDGER_JSONL.name} "
              f"({len(existing)} total)")
    elif existing:
        print(f"no new registrations "
              f"({len(existing)} entr{'y' if len(existing) == 1 else 'ies'} "
              f"already on file)")
    else:
        print("no register_component calls found — run a Lane M capture over "
              "s19-s21 first, then re-run with --runs <run-id>")

    if args.render:
        LEDGER_MD.write_text(render(existing), encoding="utf-8")
        try:
            shown = LEDGER_MD.relative_to(AGENT_EVAL_DIR.parents[1])
        except ValueError:                      # ledger redirected off-repo
            shown = LEDGER_MD
        print(f"rendered -> {shown}")
        print(f"review it against {(REVIEW_DIR / 'RUBRIC.md').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

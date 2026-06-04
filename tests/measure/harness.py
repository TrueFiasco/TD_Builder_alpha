"""The shared measurement primitive: baseline store + delta + worst-case backlog.

This is the piece the existing eval/ harness lacks. A target builds a list of
`CaseScore`s, calls `emit(target, scores, ...)`, and gets:
  - a timestamped JSON+MD report under tests/measure/results/,
  - a printed summary line with the delta vs the last promoted baseline,
  - a ranked worst-case backlog (the actionable output),
  - the stored baseline updated ONLY when `promote=True`.

`emit` returns the report dict so a test can make a light sanity assertion
(e.g. "n > 0", "no exception_text cases") without turning this into a gate.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEASURE_DIR = Path(__file__).resolve().parent
BASELINE_DIR = MEASURE_DIR / "baselines"
RESULTS_DIR = MEASURE_DIR / "results"


@dataclass
class CaseScore:
    """One measured case. `score` is the headline 0..1 number for this case."""

    case: str
    score: float
    group: str = "all"                       # e.g. operator family / tier / stage
    metrics: dict[str, float] = field(default_factory=dict)  # extra named scalars
    detail: str = ""                          # one-line why (what's missing / wrong)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def summarize(target: str, scores: list[CaseScore],
              extra: dict[str, float] | None = None) -> dict[str, Any]:
    """Aggregate CaseScores into a report dict (baseline-comparable)."""
    n = len(scores)
    score_mean = round(statistics.fmean(s.score for s in scores), 4) if n else 0.0

    metric_keys: set[str] = set()
    for s in scores:
        metric_keys.update(s.metrics)
    metrics_agg: dict[str, float] = {}
    for k in sorted(metric_keys):
        vals = [s.metrics[k] for s in scores if k in s.metrics]
        if vals:
            metrics_agg[k] = round(statistics.fmean(vals), 4)
    if extra:
        metrics_agg.update({k: round(float(v), 4) for k, v in extra.items()})

    by_group: dict[str, dict[str, float]] = {}
    groups = sorted({s.group for s in scores})
    for g in groups:
        gs = [s.score for s in scores if s.group == g]
        by_group[g] = {"n": len(gs), "score_mean": round(statistics.fmean(gs), 4)}

    return {
        "target": target,
        "timestamp": _now(),
        "n": n,
        "score_mean": score_mean,
        "metrics": metrics_agg,
        "by_group": by_group,
        "cases": [asdict(s) for s in scores],
    }


def baseline_path(target: str) -> Path:
    return BASELINE_DIR / f"{target}.json"


def load_baseline(target: str) -> dict[str, Any] | None:
    p = baseline_path(target)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def diff_vs_baseline(report: dict[str, Any],
                     baseline: dict[str, Any] | None) -> dict[str, Any]:
    """Per-metric and per-case delta. Positive score delta = improvement."""
    if not baseline:
        return {"baseline": None}
    out: dict[str, Any] = {
        "baseline_ts": baseline.get("timestamp"),
        "score_mean_delta": round(report["score_mean"] - baseline.get("score_mean", 0.0), 4),
        "metric_deltas": {},
        "regressed": [],
        "improved": [],
        "new_cases": [],
        "dropped_cases": [],
    }
    for k, v in report["metrics"].items():
        bv = baseline.get("metrics", {}).get(k)
        if bv is not None:
            out["metric_deltas"][k] = round(v - bv, 4)

    base_cases = {c["case"]: c["score"] for c in baseline.get("cases", [])}
    cur_cases = {c["case"]: c["score"] for c in report["cases"]}
    for name, sc in cur_cases.items():
        if name not in base_cases:
            out["new_cases"].append(name)
            continue
        d = round(sc - base_cases[name], 4)
        if d < -1e-9:
            out["regressed"].append({"case": name, "from": base_cases[name], "to": sc, "delta": d})
        elif d > 1e-9:
            out["improved"].append({"case": name, "from": base_cases[name], "to": sc, "delta": d})
    out["dropped_cases"] = [n for n in base_cases if n not in cur_cases]
    out["regressed"].sort(key=lambda x: x["delta"])
    out["improved"].sort(key=lambda x: -x["delta"])
    return out


def worst_cases(report: dict[str, Any], k: int = 15) -> list[dict[str, Any]]:
    """Ranked backlog: the lowest-scoring cases first. The actionable output."""
    return sorted(report["cases"], key=lambda c: c["score"])[:k]


def _write_reports(report: dict[str, Any], delta: dict[str, Any]) -> tuple[Path, Path]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{report['target']}_{_ts()}"
    jpath = RESULTS_DIR / f"{stem}.json"
    mpath = RESULTS_DIR / f"{stem}.md"
    payload = {**report, "delta": delta}
    jpath.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        f"# measure — {report['target']} ({report['timestamp']})",
        "",
        f"**score_mean = {report['score_mean']:.4f}**  (n={report['n']})",
    ]
    if delta.get("baseline") is not None or delta.get("baseline_ts"):
        sd = delta.get("score_mean_delta")
        lines.append(f"Δ vs baseline @{delta.get('baseline_ts')}: "
                     f"{sd:+.4f}" if sd is not None else "Δ: n/a")
    if report["metrics"]:
        lines += ["", "## metrics", ""]
        for kk, vv in report["metrics"].items():
            dd = delta.get("metric_deltas", {}).get(kk)
            lines.append(f"- {kk}: {vv:.4f}" + (f"  (Δ {dd:+.4f})" if dd is not None else ""))
    if report["by_group"]:
        lines += ["", "## by group", "", "| group | n | score |", "|---|--:|--:|"]
        for g, gd in sorted(report["by_group"].items()):
            lines.append(f"| {g} | {gd['n']} | {gd['score_mean']:.4f} |")
    lines += ["", "## worst cases (backlog)", "", "| case | group | score | detail |",
              "|---|---|--:|---|"]
    for c in worst_cases(report, 25):
        det = (c.get("detail") or "").replace("|", "/")[:90]
        lines.append(f"| {c['case']} | {c['group']} | {c['score']:.3f} | {det} |")
    mpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return jpath, mpath


def emit(target: str, scores: list[CaseScore], *,
         promote: bool = False,
         extra: dict[str, float] | None = None,
         worst_k: int = 12) -> dict[str, Any]:
    """Summarize, write reports, print metric+delta+backlog, optionally promote."""
    report = summarize(target, scores, extra=extra)
    baseline = load_baseline(target)
    delta = diff_vs_baseline(report, baseline)
    jpath, mpath = _write_reports(report, delta)

    sd = delta.get("score_mean_delta")
    head = f"[{target}] score_mean={report['score_mean']:.4f} n={report['n']}"
    if sd is not None:
        head += f"  delta={sd:+.4f} vs baseline@{delta.get('baseline_ts')}"
    else:
        head += "  (no baseline yet)"
    print("\n" + head)
    if report["metrics"]:
        print("  metrics: " + ", ".join(
            f"{k}={v:.4f}" + (f"({delta['metric_deltas'][k]:+.4f})"
                              if k in delta.get("metric_deltas", {}) else "")
            for k, v in report["metrics"].items()))
    wc = worst_cases(report, worst_k)
    if wc:
        print(f"  worst {len(wc)}:")
        for c in wc:
            print(f"    {c['score']:.3f}  {c['case']}  [{c['group']}]  {c.get('detail', '')[:70]}")
    if delta.get("regressed"):
        print(f"  REGRESSED {len(delta['regressed'])}: " +
              ", ".join(f"{r['case']}({r['delta']:+.3f})" for r in delta["regressed"][:8]))
    print(f"  report: {jpath.name}")

    if promote:
        BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        baseline_path(target).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"  PROMOTED -> {baseline_path(target).name}")

    return report

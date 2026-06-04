"""H17 NL-prompt eval harness.

Runs `(prompt, expected_network)` pairs through the meta-agentic
strategy runner, parses the produced `.toe.dir` with the unified-system
LosslessParser, and scores the operator/connection sets against the
expected ones with tolerant matching.

Designed to bracket the B0 ChromaDB merge / B1+B2 retrieval rewiring
work: run once for a baseline, run again after, report the delta.

Cost: each case invokes a multi-turn V2 strategy run (~$0.05 of
Claude API per case at QUICK_DRAFT preset, ~2-5 min wall clock).
Tests are skipped unless RUN_NL_EVAL=1.

Usage:
    # CLI: run all cases under cases/ and write reports to results/
    python -m unified_system.eval.prompt_eval

    # Single case for iteration:
    python -m unified_system.eval.prompt_eval --case basic_01_noise_level

    # Custom output dir:
    python -m unified_system.eval.prompt_eval --output ./my_results
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = Path(__file__).resolve().parent
CASES_DIR = EVAL_ROOT / "cases"
RESULTS_DIR = EVAL_ROOT / "results"


# ----------------------------------------------------------------------------
# Case + result models
# ----------------------------------------------------------------------------


@dataclass
class PromptCase:
    """Single eval case loaded from a YAML file under cases/."""

    name: str
    tier: str  # "basic" | "intermediate" | "advanced"
    prompt: str
    expected_operators: List[str] = field(default_factory=list)
    expected_connections: List[Tuple[str, str]] = field(default_factory=list)
    expected_parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tolerance: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def from_yaml(cls, path: Path) -> "PromptCase":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        connections = [tuple(pair) for pair in data.get("expected_connections", [])]
        return cls(
            name=data["name"],
            tier=data["tier"],
            prompt=data["prompt"],
            expected_operators=list(data.get("expected_operators", [])),
            expected_connections=connections,
            expected_parameters=dict(data.get("expected_parameters", {})),
            tolerance=dict(data.get("tolerance", {})),
            notes=data.get("notes", ""),
        )


@dataclass
class CaseResult:
    """Outcome of running one case."""

    name: str
    tier: str
    passed: bool
    operator_recall: float  # |expected ∩ actual| / |expected|
    operator_precision: float  # |expected ∩ actual| / |actual|
    connection_recall: float
    actual_operators: List[str] = field(default_factory=list)
    actual_connections: List[Tuple[str, str]] = field(default_factory=list)
    missing_operators: List[str] = field(default_factory=list)
    missing_connections: List[Tuple[str, str]] = field(default_factory=list)
    error: Optional[str] = None
    duration_seconds: float = 0.0
    quality_score: Optional[float] = None


# ----------------------------------------------------------------------------
# Runners
# ----------------------------------------------------------------------------


def v2_runner(prompt: str, project_name: str) -> Tuple[Optional[Path], Optional[float], List[str]]:
    """Invoke the V2 strategy and return (toe_dir_path, quality_score, errors).

    Real LLM calls. Skipped unless RUN_NL_EVAL=1 env is set or this is
    invoked directly via CLI.
    """
    sys.path.insert(0, str(REPO_ROOT / "META_AGENTIC_TOOL"))
    sys.path.insert(0, str(REPO_ROOT / "unified_system"))
    from meta_agentic.execution.strategy_runner import (  # type: ignore
        run_strategy,
        StrategyConfig,
        Preset,
    )

    config = StrategyConfig.from_preset(Preset.QUICK_DRAFT)
    result = run_strategy("v2", prompt, config=config, project_name=project_name)

    toe_path: Optional[Path] = result.toe_path
    if toe_path is not None:
        # run_strategy returns a .toe path; the .toe.dir lives next to it
        toe_dir = toe_path.with_suffix(toe_path.suffix + ".dir")
        if not toe_dir.exists() and toe_path.is_dir():
            toe_dir = toe_path
        return (toe_dir if toe_dir.exists() else None, result.quality_score, list(result.errors))

    return (None, result.quality_score, list(result.errors))


def mock_runner(prompt: str, project_name: str) -> Tuple[Optional[Path], Optional[float], List[str]]:
    """Stub runner for harness validation without hitting the API."""
    return (None, None, ["mock_runner: no actual run"])


# ----------------------------------------------------------------------------
# Retrieval-only mode (no API key required)
# ----------------------------------------------------------------------------
#
# Measures: given a prompt, does the merged ChromaDB store surface docs that
# cover the expected operators? Bypasses V2 strategy entirely. Directly tests
# whether B0 + B1+B2 fixed the *retrieval* failure documented in B1 — which
# is the work this plan actually did. Generation quality (V2's job) is a
# separate question.
#
# Score: operator-recall against expected_operators. A case passes if
# tolerance.min_operator_recall_retrieval (default 0.5) is met.


def retrieve_for_prompt(prompt: str, n_results: int = 50) -> List[Tuple[str, str, str]]:
    """Query the merged store and return [(family, name, doc_text), ...].

    Falls through multiple metadata keys to capture operator identity from any
    chunking style:
      - metadata.operator_name  (build_instruction docs use this)
      - metadata.name           (active store doc-source entries)
      - metadata.operator       (orphan store parameter entries)
      - metadata.operator_type  (active store snippet entries; e.g. 'noiseCHOP')

    Skips non-operator-bearing hits (howtos, concepts, generic snippets, python
    examples without an operator association).
    """
    sys.path.insert(0, str(REPO_ROOT / "META_AGENTIC_TOOL"))
    from search import get_search_adapter  # type: ignore

    adapter = get_search_adapter()
    result = adapter.search(prompt, n_results=n_results, include_relationships=False)

    valid_families = {"CHOP", "TOP", "SOP", "MAT", "DAT", "COMP", "POP"}
    hits: List[Tuple[str, str, str]] = []
    for r in result.get("semantic_results", []):
        meta = r.get("metadata") or {}
        fam = meta.get("family")
        if not fam or fam.upper() not in valid_families:
            continue
        name = (meta.get("operator_name") or meta.get("name")
                or meta.get("operator") or meta.get("operator_type"))
        if not name:
            continue
        text = r.get("content", "") or ""
        hits.append((fam.upper(), str(name), text))
    return hits


_WS_RE = __import__("re").compile(r"\s+")


def _norm_op_name(name: str, family: str) -> str:
    """Reduce a TD operator name to a comparison key.

    'Noise_CHOP'         → 'noise'
    'Noise CHOP'         → 'noise'
    'noiseCHOP'          → 'noise'   (active-store snippet shape)
    'Bullet_Solver_COMP' → 'bulletsolver'
    'Bullet Solver COMP' → 'bulletsolver'
    'POP to SOP'         → 'poptosop'
    """
    n = name.replace("_", " ").strip()
    fam_upper = family.upper()
    fam_lower = family.lower()
    # Strip a trailing space-prefixed family ('Noise CHOP' → 'Noise').
    suffix_spaced = f" {fam_upper}"
    if n.upper().endswith(suffix_spaced):
        n = n[: -len(suffix_spaced)].strip()
    # Strip a trailing concatenated family ('noiseCHOP' → 'noise').
    elif n.lower().endswith(fam_lower):
        n = n[: -len(fam_lower)]
    return _WS_RE.sub("", n).lower()


def _retrieved_op_keys(hits: List[Tuple[str, str, str]]) -> set:
    """Collapse retrieved (family, name, _) tuples to a normalised key set."""
    return {(fam.upper(), _norm_op_name(name, fam)) for fam, name, _doc in hits}


def _expected_op_keys(case: PromptCase) -> set:
    """Same normalisation, applied to case.expected_operators ('CHOP:noise')."""
    keys: set = set()
    for entry in case.expected_operators:
        if ":" not in entry:
            continue
        fam, name = entry.split(":", 1)
        keys.add((fam.strip().upper(), _WS_RE.sub("", name.strip().lower())))
    return keys


def run_retrieval_case(case: PromptCase, n_results: int = 20) -> CaseResult:
    """Run one case in retrieval-only mode."""
    t0 = time.time()
    try:
        hits = retrieve_for_prompt(case.prompt, n_results=n_results)
    except Exception as e:
        return CaseResult(
            name=case.name,
            tier=case.tier,
            passed=False,
            operator_recall=0.0,
            operator_precision=0.0,
            connection_recall=0.0,
            error=f"retrieval failed: {type(e).__name__}: {e}",
            duration_seconds=time.time() - t0,
        )

    expected = _expected_op_keys(case)
    retrieved = _retrieved_op_keys(hits)
    intersect = expected & retrieved
    recall = len(intersect) / len(expected) if expected else 1.0
    threshold = case.tolerance.get("min_operator_recall_retrieval",
                                   case.tolerance.get("min_operator_recall", 0.5))

    return CaseResult(
        name=case.name,
        tier=case.tier,
        passed=recall >= threshold,
        operator_recall=recall,
        operator_precision=0.0,  # not meaningful for retrieval (we keep top-K regardless)
        connection_recall=0.0,    # retrieval doesn't surface connections
        actual_operators=[f"{fam}:{nm}" for fam, nm in sorted(retrieved)],
        actual_connections=[],
        missing_operators=[f"{fam}:{nm}" for fam, nm in sorted(expected - retrieved)],
        missing_connections=[],
        duration_seconds=time.time() - t0,
        quality_score=None,
    )


# ----------------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------------


def _normalize_op(op_id: str) -> str:
    """Canonicalize 'CHOP:noise', 'chop:noise', 'CHOP/noise' -> 'CHOP:noise'."""
    s = op_id.strip().replace("/", ":").replace(" ", "")
    if ":" in s:
        family, op_type = s.split(":", 1)
        return f"{family.upper()}:{op_type}"
    return s


def extract_actual(toe_dir: Path) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Parse a `.toe.dir` and extract (operator_ids, connections)."""
    sys.path.insert(0, str(REPO_ROOT / "unified_system"))
    from parsers.lossless_parser import LosslessParser  # type: ignore

    network = LosslessParser(toe_dir).parse(verbose=False)
    operator_ids = [_normalize_op(op.op_type or f"{op.family.value}:{op.type}") for op in network.operators]
    # Deduplicate while preserving order
    seen = set()
    operator_ids = [o for o in operator_ids if not (o in seen or seen.add(o))]

    # Connections as (from_op_path, to_op_path) tuples — extract op names
    connections: List[Tuple[str, str]] = []
    for conn in network.connections:
        src = conn.from_op.rsplit("/", 1)[-1] if "/" in conn.from_op else conn.from_op
        dst = conn.to_op.rsplit("/", 1)[-1] if "/" in conn.to_op else conn.to_op
        connections.append((src, dst))

    return operator_ids, connections


def score_case(case: PromptCase, actual_operators: List[str], actual_connections: List[Tuple[str, str]]) -> Dict[str, Any]:
    """Compute recall/precision/pass for one case."""
    expected_ops = {_normalize_op(o) for o in case.expected_operators}
    actual_ops = {_normalize_op(o) for o in actual_operators}

    op_intersect = expected_ops & actual_ops
    op_recall = len(op_intersect) / len(expected_ops) if expected_ops else 1.0
    op_precision = len(op_intersect) / len(actual_ops) if actual_ops else 0.0
    missing_ops = sorted(expected_ops - actual_ops)

    expected_conns = set(case.expected_connections)
    actual_conns = set(actual_connections)
    conn_intersect = expected_conns & actual_conns
    conn_recall = len(conn_intersect) / len(expected_conns) if expected_conns else 1.0
    missing_conns = sorted(expected_conns - actual_conns)

    # Pass criteria: operator recall >= threshold, connection recall >= threshold
    op_threshold = case.tolerance.get("min_operator_recall", 0.8)
    conn_threshold = case.tolerance.get("min_connection_recall", 0.5)
    passed = op_recall >= op_threshold and conn_recall >= conn_threshold

    return {
        "passed": passed,
        "operator_recall": op_recall,
        "operator_precision": op_precision,
        "connection_recall": conn_recall,
        "missing_operators": missing_ops,
        "missing_connections": [list(c) for c in missing_conns],
    }


# ----------------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------------


def discover_cases(cases_dir: Path = CASES_DIR, name_filter: Optional[str] = None) -> List[PromptCase]:
    """Load all `*.yaml` cases under cases_dir, optionally filtered by name substring."""
    cases: List[PromptCase] = []
    for path in sorted(cases_dir.glob("*.yaml")):
        if name_filter and name_filter not in path.stem:
            continue
        cases.append(PromptCase.from_yaml(path))
    return cases


def run_case(case: PromptCase, runner: Callable[..., Tuple[Optional[Path], Optional[float], List[str]]]) -> CaseResult:
    """Run a single case through the runner and score it."""
    project_name = f"eval_{case.name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    t0 = time.time()
    try:
        toe_dir, quality_score, errors = runner(case.prompt, project_name)
    except Exception as e:
        return CaseResult(
            name=case.name,
            tier=case.tier,
            passed=False,
            operator_recall=0.0,
            operator_precision=0.0,
            connection_recall=0.0,
            error=f"runner raised: {type(e).__name__}: {e}\n{traceback.format_exc()}",
            duration_seconds=time.time() - t0,
        )

    if toe_dir is None or not toe_dir.exists():
        return CaseResult(
            name=case.name,
            tier=case.tier,
            passed=False,
            operator_recall=0.0,
            operator_precision=0.0,
            connection_recall=0.0,
            error="runner returned no .toe.dir; errors=" + "; ".join(errors or ["(none)"]),
            duration_seconds=time.time() - t0,
            quality_score=quality_score,
        )

    try:
        actual_ops, actual_conns = extract_actual(toe_dir)
    except Exception as e:
        return CaseResult(
            name=case.name,
            tier=case.tier,
            passed=False,
            operator_recall=0.0,
            operator_precision=0.0,
            connection_recall=0.0,
            error=f"parser raised: {type(e).__name__}: {e}",
            duration_seconds=time.time() - t0,
            quality_score=quality_score,
        )

    scored = score_case(case, actual_ops, actual_conns)
    return CaseResult(
        name=case.name,
        tier=case.tier,
        passed=scored["passed"],
        operator_recall=scored["operator_recall"],
        operator_precision=scored["operator_precision"],
        connection_recall=scored["connection_recall"],
        actual_operators=actual_ops,
        actual_connections=actual_conns,
        missing_operators=scored["missing_operators"],
        missing_connections=[tuple(c) for c in scored["missing_connections"]],
        duration_seconds=time.time() - t0,
        quality_score=quality_score,
    )


def aggregate_report(results: List[CaseResult]) -> Dict[str, Any]:
    """Build the JSON-serializable summary."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    by_tier: Dict[str, Dict[str, int]] = {}
    for r in results:
        bucket = by_tier.setdefault(r.tier, {"total": 0, "passed": 0})
        bucket["total"] += 1
        if r.passed:
            bucket["passed"] += 1

    return {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "total": total,
        "passed": passed,
        "pass_rate": passed / total if total else 0.0,
        "by_tier": by_tier,
        "cases": [
            {
                **asdict(r),
                "actual_connections": [list(c) for c in r.actual_connections],
                "missing_connections": [list(c) for c in r.missing_connections],
            }
            for r in results
        ],
    }


def write_reports(report: Dict[str, Any], output_dir: Path, label: str) -> Tuple[Path, Path]:
    """Write JSON + markdown reports. Returns (json_path, md_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"{label}_{timestamp}.json"
    md_path = output_dir / f"{label}_{timestamp}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# H17 eval — {label} ({report['timestamp']})\n\n")
        f.write(f"**Pass rate: {report['passed']}/{report['total']} = {report['pass_rate']*100:.1f}%**\n\n")
        f.write("## By tier\n\n")
        for tier, stats in sorted(report["by_tier"].items()):
            rate = stats["passed"] / stats["total"] if stats["total"] else 0.0
            f.write(f"- **{tier}**: {stats['passed']}/{stats['total']} = {rate*100:.1f}%\n")
        f.write("\n## Per-case\n\n")
        f.write("| Case | Tier | Pass | OpRecall | ConnRecall | Duration | Notes |\n")
        f.write("|---|---|:-:|:-:|:-:|--:|---|\n")
        for c in report["cases"]:
            note = c["error"][:80] + "…" if c["error"] else (
                f"missing ops: {', '.join(c['missing_operators'][:3])}" if c["missing_operators"] else "ok"
            )
            f.write(
                f"| {c['name']} | {c['tier']} | {'✓' if c['passed'] else '✗'} | "
                f"{c['operator_recall']:.2f} | {c['connection_recall']:.2f} | "
                f"{c['duration_seconds']:.0f}s | {note} |\n"
            )

    return json_path, md_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run H17 NL-prompt eval harness.")
    parser.add_argument("--case", help="Filter to cases whose name contains this substring")
    parser.add_argument("--output", type=Path, default=RESULTS_DIR, help="Where to write reports")
    parser.add_argument("--label", default="baseline", help="Report label (e.g. baseline, post_b0)")
    parser.add_argument("--mock", action="store_true", help="Use mock runner (no API calls)")
    parser.add_argument("--retrieval-only", action="store_true",
                        help="Skip V2 strategy invocation; score retrieval quality only "
                             "by querying the merged ChromaDB store directly. No API key needed.")
    parser.add_argument("--n-results", type=int, default=20,
                        help="Top-K for --retrieval-only mode (default 20)")
    args = parser.parse_args(argv)

    cases = discover_cases(name_filter=args.case)
    if not cases:
        print(f"No cases found in {CASES_DIR} (filter={args.case!r})")
        return 1

    if args.retrieval_only:
        print(f"Running {len(cases)} cases in RETRIEVAL-ONLY mode "
              f"(querying merged store top-{args.n_results}; no V2 / no API)...")
    else:
        runner = mock_runner if args.mock else v2_runner
        print(f"Running {len(cases)} cases with {'mock' if args.mock else 'V2 strategy (LIVE)'}...")
        if not args.mock and not os.environ.get("RUN_NL_EVAL"):
            print("Warning: RUN_NL_EVAL is not set. CLI invocation overrides the gate.")

    results: List[CaseResult] = []
    for i, case in enumerate(cases, 1):
        print(f"\n[{i}/{len(cases)}] {case.name} ({case.tier}): {case.prompt[:80]}...")
        if args.retrieval_only:
            result = run_retrieval_case(case, n_results=args.n_results)
        else:
            result = run_case(case, runner)
        results.append(result)
        marker = "PASS" if result.passed else "FAIL"
        print(
            f"  {marker}  op_recall={result.operator_recall:.2f}  "
            f"duration={result.duration_seconds:.1f}s"
        )
        if result.missing_operators:
            print(f"  missing: {', '.join(result.missing_operators)}")
        if result.error:
            print(f"  error: {result.error[:200]}")

    report = aggregate_report(results)
    json_path, md_path = write_reports(report, args.output, args.label)
    print(f"\n=== SUMMARY ===")
    print(f"Pass rate: {report['passed']}/{report['total']} = {report['pass_rate']*100:.1f}%")
    print(f"  Reports written to: {json_path} and {md_path}")
    return 0 if report["pass_rate"] > 0 else 2


if __name__ == "__main__":
    sys.exit(main())

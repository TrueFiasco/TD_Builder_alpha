"""Dataset loaders shared by the targets. All read existing answer keys under
META_AGENTIC_TOOL/operator_ground_truth/ — no fabricated expectations.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from measure._server import ALPHA_ROOT

GROUND_TRUTH = ALPHA_ROOT / "META_AGENTIC_TOOL" / "operator_ground_truth"
PARAMS_DIR = GROUND_TRUTH / "params"
OPERATOR_TYPES = GROUND_TRUTH / "operator_types.json"
EVAL_CASES = ALPHA_ROOT / "unified_system" / "eval" / "cases"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def full_run() -> bool:
    return os.environ.get("MEASURE_FULL", "") not in ("", "0", "false", "False")


def operator_types() -> dict[str, list[dict[str, str]]]:
    """{FAMILY: [{name, td_create}, ...]} from operator_types.json."""
    data = json.loads(OPERATOR_TYPES.read_text(encoding="utf-8"))
    return data.get("operators", {})


def ground_truth_params(limit_per_family: int | None = None) -> list[dict[str, Any]]:
    """Load *_defaults.json answer keys (the builder #1 dataset).

    Each entry: {operator, family, td_create_name, param_count, parameters:{...}}.
    Sampled deterministically (sorted, round-robin per family) unless MEASURE_FULL.
    """
    files = sorted(PARAMS_DIR.glob("*_defaults.json"))
    out: list[dict[str, Any]] = []
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if d.get("parameters"):
            out.append(d)

    if full_run() or limit_per_family is None:
        return out

    by_fam: dict[str, list[dict[str, Any]]] = {}
    for d in out:
        by_fam.setdefault(d.get("family", "?"), []).append(d)
    sampled: list[dict[str, Any]] = []
    for fam in sorted(by_fam):
        sampled.extend(by_fam[fam][:limit_per_family])
    return sampled


def sample_operators(n_per_family: int) -> list[dict[str, str]]:
    """A deterministic per-family slice of operator_types for retrieval #2."""
    ops: list[dict[str, str]] = []
    types = operator_types()
    for fam in sorted(types):
        entries = types[fam]
        take = entries if full_run() else entries[:n_per_family]
        for e in take:
            ops.append({"family": fam, "name": e["name"], "td_create": e.get("td_create", "")})
    return ops


# tunables (env-overridable so a quick loop and a full run share one dataset)
BUILDER_PER_FAMILY = _env_int("MEASURE_BUILDER_N", 3)
RETRIEVAL_PER_FAMILY = _env_int("MEASURE_RETRIEVAL_N", 6)

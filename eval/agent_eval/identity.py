#!/usr/bin/env python3
r"""Shared environment-identity stamp for BOTH eval harnesses (design §7/§8).

Imported by eval/agent_eval/run_agent_eval.py and (via importlib, to avoid a
module-name collision on sys.path) by eval/run_eval.py. Stdlib-only on purpose:
this module must be importable in every lane, including the light-deps CI lanes.

The identity block answers "what exactly produced this number?". Comparisons
across differing identity REFUSE by default (--allow-identity-drift overrides,
marking the report NON-COMPARABLE). A missing identity (pre-§8 baselines) is
"unknown": warn and proceed, never refuse.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

# Fields whose mismatch makes two RETRIEVAL results non-comparable (run_eval).
KB_IDENTITY_FIELDS = ("kb_manifest_version", "kb_sha")

# Fields whose mismatch makes two AGENT-EVAL results non-comparable (§7).
AGENT_IDENTITY_FIELDS = (
    "scenario_set_version", "model_id", "cli_version", "server_version",
    "kb_manifest_version", "kb_sha", "tool_inventory_hash", "guidance_hash",
)


def redact_path(p, extra_roots: tuple[Path, ...] = ()) -> str:
    """Tree-relative form of a provenance path for COMMITTED files.

    Mirrors eval/run_eval.py::redact_path (absolute local paths must not leak
    into committed baselines): inside a worktree strip the
    .claude/worktrees/<name>/ prefix; else relativize against any provided
    root; else fall back to the basename.
    """
    p = Path(p)
    parts = list(p.parts)
    if ".claude" in parts:
        i = parts.index(".claude")
        rel = parts[i + 3:] if len(parts) > i + 2 and parts[i + 1] == "worktrees" else parts[i:]
        return "/".join(rel) or p.name
    for root in extra_roots:
        try:
            return p.relative_to(root).as_posix()
        except ValueError:
            pass
    return p.name


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def kb_identity(kb_root: Path, extra_roots: tuple[Path, ...] = ()) -> dict:
    """KB identity: manifest version + sha256(manifest.json + operators.json).

    kb_sha covers the two files that define what the retrieval/build layers
    can know: a KB rebuild rotates operators.json, a re-release rotates the
    manifest. (Hashing the whole vector_db would be slow and adds nothing:
    it is rebuilt from these inputs and pinned by the release sha.)
    """
    kb_root = Path(kb_root)
    manifest = kb_root / "manifest.json"
    operators = kb_root / "operators.json"
    version = None
    if manifest.exists():
        try:
            version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
        except (ValueError, OSError):
            version = None
    h = hashlib.sha256()
    for f in (manifest, operators):
        if f.exists():
            h.update(sha256_file(f).encode("ascii"))
        else:
            h.update(b"ABSENT:" + f.name.encode("ascii"))
    return {
        "kb_manifest_version": version,
        "kb_sha": h.hexdigest(),
        "kb_root": redact_path(kb_root, extra_roots),
    }


def cli_version(cli: str = "claude") -> str | None:
    """`claude --version` for the identity block; None when the CLI is absent."""
    try:
        out = subprocess.run([cli, "--version"], capture_output=True, text=True,
                             timeout=30, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    v = (out.stdout or "").strip()
    return v or None


def tool_inventory_hash(tool_names) -> str:
    """sha256 of the sorted tool-name list (P01b's inventory, hashed)."""
    return sha256_text("\n".join(sorted(tool_names)))


def identity_mismatches(current: dict, prior: dict | None, fields) -> tuple[list, list]:
    """Compare two identity blocks over `fields`.

    Returns (mismatched, unknown): `mismatched` = [(field, prior, current)]
    where both sides have a value and they differ; `unknown` = fields absent
    on the prior side (pre-identity baselines -> warn, don't refuse).
    """
    mismatched, unknown = [], []
    prior = prior or {}
    for f in fields:
        cur, old = current.get(f), prior.get(f)
        if old in (None, ""):
            unknown.append(f)
        elif cur != old:
            mismatched.append((f, old, cur))
    return mismatched, unknown

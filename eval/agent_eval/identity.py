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
# live_tool_inventory_hash (added 2026-07-14, PR #24/#26 re-bless): the offline
# tool_inventory_hash is BLIND to the separate td-builder-live surface (proven:
# it stayed 1c81e8b4… across the 21→22 get_glsl_status change), so the live
# inventory is stamped as its own field. Pre-existing baselines lack it — that
# reads as "unknown" (warn, don't refuse) by design.
# user_store (added 2026-07-16, W7 re-bless, owner decision ⑥): what USER
# component store the run could see — "absent" for a hermetic (pinned-empty)
# run, else a content sha. The W7 pins (mcp.eval.json.tmpl per-trial,
# _server.py pre-import) should make every eval run "absent"; a deliberately
# dirty run (or a pin regression) therefore REFUSES --compare instead of
# silently measuring KB ∪ user-store under a KB-only identity.
AGENT_IDENTITY_FIELDS = (
    "scenario_set_version", "model_id", "cli_version", "server_version",
    "kb_manifest_version", "kb_sha", "tool_inventory_hash",
    "live_tool_inventory_hash", "guidance_hash", "user_store",
)

# Soft-warn tier (hygiene bundle H4b): mismatch prints a WARNING in --compare
# but NEVER refuses and never touches the exit code. engine_code_hash flips on
# ANY MCP/engine/**/*.py edit, comments included -- acceptable ONLY because
# this tier warns; it is not fit for the refuse tuple. It closes the
# server_version blind spot: a hand-bumped constant that stayed "0.2.0" across
# builder changes that materially altered behavior (baseline _provenance
# mixed_snapshot_disclosure: s01-s09 captured on a 4-stage validation
# pipeline, s10-s14 on a 6-stage one, identity blind to the difference).
AGENT_IDENTITY_WARN_FIELDS = ("engine_code_hash",)


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


def user_store_identity(components_json: Path, index_dir: Path) -> str:
    """Identity of the USER component store a run can see (W7, decision ⑥).

    Returns the literal string "absent" when neither the user registry
    (user_components.json) nor the user index manifest (user_index/
    manifest.json) exists — the hermetic state every pinned eval run must be
    in. Otherwise returns a sha256 over the bytes of whichever of the two
    exists (registry first), so ANY visible user store — even an empty or
    malformed registry file — flips the field and refuses --compare. The
    chroma payload under user_index/ is deliberately NOT hashed (sqlite bytes
    are not deterministic); the registry + self-signed manifest are the
    durable content of record. Stdlib-only, mirrors kb_identity's shape.
    """
    components_json, index_dir = Path(components_json), Path(index_dir)
    manifest = index_dir / "manifest.json"
    present = [f for f in (components_json, manifest) if f.exists()]
    if not present:
        return "absent"
    h = hashlib.sha256()
    for f in present:
        h.update(f.name.encode("utf-8") + b":")
        h.update(sha256_file(f).encode("ascii"))
    return h.hexdigest()


def engine_code_hash(engine_root: Path) -> str | None:
    """sha256 over sorted (posix-relpath, file-sha256) pairs of engine_root/**/*.py.

    Soft-warn identity field (AGENT_IDENTITY_WARN_FIELDS): "did the engine
    builder/validation code change since the baseline?". File bytes are hashed
    with CRLF normalized to LF so the value is stable across checkout
    newline conventions (core.autocrlf). Returns None when no .py files are
    found (partial checkout) -- reads as "unknown" downstream (warn, never
    refuse). Stdlib-only: pathlib + hashlib.
    """
    engine_root = Path(engine_root)
    files = sorted(
        (p for p in engine_root.rglob("*.py") if p.is_file()),
        key=lambda p: p.relative_to(engine_root).as_posix(),
    )
    if not files:
        return None
    h = hashlib.sha256()
    for f in files:
        rel = f.relative_to(engine_root).as_posix()
        content = hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        h.update(rel.encode("utf-8") + b"\0" + content.encode("ascii") + b"\n")
    return h.hexdigest()


def git_sha(repo_root: Path) -> str | None:
    """`git rev-parse --short HEAD`; None when git/repo is unavailable.

    INFORMATIONAL ONLY: stored in the identity dict for the human reading a
    report or baseline, present in NEITHER field tuple, never compared
    (identity_mismatches only inspects tuple fields). At --capture-baseline
    time it will agree with the hand-written _provenance.captured_git_sha.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=30, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    v = (out.stdout or "").strip()
    return v if out.returncode == 0 and v else None


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

r"""Server-side environment-identity helpers (D4 feedback spine).

TWIN of ``eval/agent_eval/identity.py``. The eval module is dev/CI-lane infra and
is NOT on either MCP server's ``sys.path``; importing it from the shipped product
would invert the layering (eval depends on the server, not the reverse) and break
in the release distribution. So the small stdlib-only helpers the feedback recorder
needs are LIFTED here, into an ``MCP/``-level sibling of ``server_instructions.py``
(importable by both servers).

Kept byte-behaviour-compatible with the eval twin; ``tests/test_feedback_spine.py``
asserts the two agree on fixtures so they cannot silently diverge. If you edit a
helper here, mirror it in ``eval/agent_eval/identity.py`` (and vice-versa). Unifying
the two into one shared module is a deferred follow-up (it would touch the eval
lanes). Stdlib-only on purpose.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def redact_path(p, extra_roots: tuple[Path, ...] = ()) -> str:
    """Tree-relative form of a provenance path (no absolute local paths leak).

    Mirrors ``eval/agent_eval/identity.py::redact_path``: inside a worktree strip
    the ``.claude/worktrees/<name>/`` prefix; else relativize against any provided
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

    A KB rebuild rotates ``operators.json``; a re-release rotates the manifest.
    Missing files hash as an explicit ``ABSENT:<name>`` marker (so a KB-less test
    or a partial install still produces a stable, honest identity).
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


def tool_inventory_hash(tool_names) -> str:
    """sha256 of the sorted tool-name list (P01b's inventory, hashed)."""
    return sha256_text("\n".join(sorted(tool_names)))

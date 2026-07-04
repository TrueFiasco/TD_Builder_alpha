"""
Canonical path resolution for TD Builder Alpha.

Single source of truth for repo-relative paths. Every consumer reads from here
rather than hardcoding absolute paths, so the project works regardless of
where it's checked out (e.g. C:/TD_builder_alpha, D:/dev/td_builder,
~/projects/td-builder-alpha, etc.).

Override the inferred root by setting the `TD_BUILDER_ROOT` environment
variable for non-standard layouts.

Usage:
    from paths import KB_OPERATORS, KB_WIKI_SUPPL, kb_operators_path
"""

from __future__ import annotations
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------
# This file lives AT the repo root. Walk-from-__file__ keeps that anchor
# correct regardless of how the project was cloned or where it sits on disk.
_DEFAULT_ROOT = Path(__file__).resolve().parent

# Optional override for non-standard installs.
REPO_ROOT: Path = (
    Path(os.environ["TD_BUILDER_ROOT"]).resolve()
    if os.environ.get("TD_BUILDER_ROOT")
    else _DEFAULT_ROOT
)

# ---------------------------------------------------------------------------
# Canonical KB locations (alpha layout)
# ---------------------------------------------------------------------------
KB_ROOT: Path = REPO_ROOT / "KB"
KB_OPERATORS: Path = KB_ROOT / "operators.json"
KB_DOCKED_DATS: Path = KB_ROOT / "docked_dats.json"
KB_PALETTE_COMPONENTS: Path = KB_ROOT / "palette_components.json"
KB_GRAPHRAG: Path = KB_ROOT / "graphrag.json"
KB_VECTORDB: Path = KB_ROOT / "vector_db"
KB_WIKI_SUPPL: Path = KB_ROOT / "wiki_supplemental"

# ---------------------------------------------------------------------------
# Resolver helpers
# ---------------------------------------------------------------------------
def kb_operators_path() -> Path:
    """Path to the canonical operator-schema JSON (KB/operators.json).

    Returns the alpha KB path; if it doesn't exist yet, a downstream
    FileNotFoundError points at the canonical install location.
    """
    return KB_OPERATORS


def kb_docked_dats_path() -> Path:
    """Path to the docked-DAT specs (KB/docked_dats.json) -- the per-op map of helper
    DATs the builder auto-creates + docks (GLSL shader/info DATs, callback scripts,
    table DATs, ...). Companion to operators.json; PR-reviewable."""
    return KB_DOCKED_DATS


def kb_palette_components_path() -> Path:
    """Path to the pre-built component registry (KB/palette_components.json) -- per-item
    reference + interface metadata for the builder's `palette` field (source root,
    tox_path, wrapper/subcompname, inner type, in/out connector op names). Companion to
    docked_dats.json; PR-reviewable."""
    return KB_PALETTE_COMPONENTS


def user_components_path() -> Path:
    """Path to the USER component registry (user_components.json) -- same per-item schema
    as KB/palette_components.json, merged over it at load (user wins on name collision).
    Lives OUTSIDE KB/ (the KB is a fetched, identity-hashed artifact and stays pristine):
    default ~/.td_builder/user_components.json (same home as the live-server api_token),
    directory overridable via TD_BUILDER_USER_DIR. Resolved at CALL time -- not import
    time -- so tests and a long-lived MCP server see env changes and fresh registrations
    without a module reload."""
    base = os.environ.get("TD_BUILDER_USER_DIR")
    root = Path(base).expanduser() if base and base.strip() else Path.home() / ".td_builder"
    return root / "user_components.json"


def wiki_supplemental(name: str) -> Path:
    """Return the absolute path to a wiki_supplemental .md file.

    Example:
        wiki_supplemental("Write_a_GLSL_TOP.md")
    """
    return KB_WIKI_SUPPL / name


# ---------------------------------------------------------------------------
# TouchDesigner CLI binary resolver (toecollapse / toeexpand)
# ---------------------------------------------------------------------------
# Single source of truth for locating TD's command-line tools, so the project
# works on any install / OS instead of hardcoding the Windows default path.
import glob as _glob
import shutil as _shutil
import sys as _sys

_TD_TOOL_ENV = {"toecollapse": "TD_TOECOLLAPSE", "toeexpand": "TD_TOEEXPAND"}


def resolve_td_tool(name: str) -> "Path | None":
    """Resolve a TouchDesigner CLI tool ('toecollapse' / 'toeexpand') to an
    absolute Path, or None if not found. Resolution order:
      1. per-tool env override (TD_TOECOLLAPSE / TD_TOEEXPAND)
      2. TD_BIN_DIR / <tool>
      3. PATH (shutil.which)
      4. platform default install globs (newest version wins)
    """
    stem = name[:-4] if name.lower().endswith(".exe") else name
    exe = stem + (".exe" if os.name == "nt" else "")
    env_key = _TD_TOOL_ENV.get(stem)
    if env_key and os.environ.get(env_key):
        p = Path(os.environ[env_key])
        if p.exists():
            return p
    bin_dir = os.environ.get("TD_BIN_DIR")
    if bin_dir:
        for cand in (Path(bin_dir) / exe, Path(bin_dir) / stem):
            if cand.exists():
                return cand
    for candidate_name in (exe, stem):
        found = _shutil.which(candidate_name)
        if found:
            return Path(found)
    if os.name == "nt":
        patterns = [r"C:\Program Files\Derivative\TouchDesigner*\bin\%s" % exe]
    elif _sys.platform == "darwin":
        patterns = ["/Applications/TouchDesigner*.app/Contents/MacOS/%s" % stem]
    else:
        patterns = [str(Path.home() / "TouchDesigner*" / "bin" / stem),
                    "/opt/derivative/TouchDesigner*/bin/%s" % stem]
    for pat in patterns:
        hits = sorted(_glob.glob(pat))
        if hits:
            return Path(hits[-1])
    return None


def td_tool_missing_error(name: str) -> str:
    """Actionable message to show when resolve_td_tool(name) returns None."""
    stem = name[:-4] if name.lower().endswith(".exe") else name
    env_key = _TD_TOOL_ENV.get(stem, "TD_BIN_DIR")
    return (f"TouchDesigner '{stem}' tool not found. Install TouchDesigner, or set "
            f"{env_key} (or TD_BIN_DIR) to the folder containing it. Looked on PATH "
            f"and in the default install location.")

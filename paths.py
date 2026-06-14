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
KB_GRAPHRAG: Path = KB_ROOT / "graphrag.json"
KB_VECTORDB: Path = KB_ROOT / "vector_db"
KB_WIKI_SUPPL: Path = KB_ROOT / "wiki_supplemental"

# ---------------------------------------------------------------------------
# Legacy layout (pre-alpha META_AGENTIC_TOOL/data/wiki_docs)
# ---------------------------------------------------------------------------
# Kept only as fallback for consumers that haven't migrated to the alpha KB.
# New code should NOT add paths here.
LEGACY_DATA: Path = REPO_ROOT / "META_AGENTIC_TOOL" / "data"
LEGACY_WIKI_DOCS: Path = LEGACY_DATA / "wiki_docs"
LEGACY_OPERATORS_ENRICHED: Path = LEGACY_WIKI_DOCS / "td_universal_parsed_enriched.json"
LEGACY_OPERATORS_BASE: Path = LEGACY_WIKI_DOCS / "td_universal_parsed.json"

# ---------------------------------------------------------------------------
# Resolver helpers
# ---------------------------------------------------------------------------
def kb_operators_path() -> Path:
    """First existing operator-schema JSON in the alpha → enriched → legacy chain.

    Returns:
        Path to the chosen JSON. If nothing exists, returns the alpha path so
        a downstream FileNotFoundError points at the canonical install location.
    """
    for candidate in (KB_OPERATORS, LEGACY_OPERATORS_ENRICHED, LEGACY_OPERATORS_BASE):
        if candidate.exists():
            return candidate
    return KB_OPERATORS


def kb_docked_dats_path() -> Path:
    """Path to the docked-DAT specs (KB/docked_dats.json) -- the per-op map of helper
    DATs the builder auto-creates + docks (GLSL shader/info DATs, callback scripts,
    table DATs, ...). Companion to operators.json; PR-reviewable."""
    return KB_DOCKED_DATS


def wiki_supplemental(name: str) -> Path:
    """Return the absolute path to a wiki_supplemental .md file.

    Example:
        wiki_supplemental("Write_a_GLSL_TOP.md")
    """
    return KB_WIKI_SUPPL / name

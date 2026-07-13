"""Server <-> KB version-compatibility check (Wave 5).

``SERVER_VERSION`` is a code constant; the installed KB carries its own version in
``KB/manifest.json``. The two are decoupled and have drifted before (see the note by the
manifest load in ``mcp_server.py``). This module computes a boot-time compatibility status
the server surfaces in ``get_server_info`` and warns about, once, on a mismatch.

POLICY: **WARN, never fail.** A version-mismatched KB still boots (degraded) rather than
bricking the server -- a stale KB running with a warning is more useful than no server.

Comparison is **semver-MINOR**: ``(major, minor)`` must match. Pre-1.0 semantics are
intentional -- a ``0.x`` minor bump is treated as breaking, so ``0.2`` vs ``0.3`` flags
incompatible while ``0.2.0`` vs ``0.2.1`` stays compatible.

Parsing is **hardened**: only a strict three-component all-numeric semver core
(``"X.Y.Z"``) is compared. Anything else -- ``None``, ``""``, a two-part ``"0.2"``, a
pre-release ``"0.2.0-alpha"``, or a four-part ``td_build``-shaped ``"0.99.2025.32460"`` --
yields status ``"unknown"`` and **never raises** at boot. ``td_build`` is surfaced as-is and
is **never parsed**: the offline server has no referent to compare a TouchDesigner build
string against. When a ``td_build`` is present, an additive, advisory ``td_build_notice``
field spells out that the ``compatible`` verdict covers ONLY server<->KB package versions,
not the live TD build, and points the caller at ``get_td_info`` for a live cross-check.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple


def read_kb_version(kb_root) -> Optional[str]:
    """Return the KB manifest's ``version`` string, or ``None`` if unreadable/absent.

    Pure helper used by tests (and available to callers). The running server keeps its own
    already-parsed ``_KB_MANIFEST_VERSION`` as the authoritative value and passes it to
    :func:`compat_status`, so this is not a second read on any hot path.
    """
    try:
        data = json.loads((Path(kb_root) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    v = data.get("version")
    return v if isinstance(v, str) else None


def _minor_tuple(v) -> Optional[Tuple[int, int]]:
    """``(major, minor)`` from a STRICT ``"X.Y.Z"`` all-numeric semver core, else ``None``.

    Deliberately strict: exactly three dot-components, each a non-negative int. This maps
    every malformed/ambiguous form to ``None`` (-> ``"unknown"``) so a boot check never
    guesses: ``"0.2"`` (short), ``"0.2.0-alpha"`` (pre-release patch), ``"0.99.2025.32460"``
    (four-part ``td_build`` shape), ``""``/``None``/``"x.y.z"`` (non-numeric) all reject.
    """
    if not isinstance(v, str):
        return None
    parts = v.split(".")
    if len(parts) != 3:
        return None
    try:
        major, minor, _patch = (int(p) for p in parts)
    except ValueError:
        return None
    return (major, minor)


def compat_status(server_version, kb_version, td_build=None) -> dict:
    """Compare server vs KB version at semver-minor granularity. **Never raises.**

    Returns:
        {
          "compatible": True | False | None,   # None == "unknown" (could not compare)
          "status":     "compatible" | "incompatible" | "unknown",
          "server_version": <as given>,
          "kb_version":     <as given>,
          "kb_td_build":    <as given; informational only, never parsed>,
          "td_build_notice": <advisory string when td_build present, else None>,
          "policy":         "warn",
        }
    """
    s = _minor_tuple(server_version)
    k = _minor_tuple(kb_version)
    if s is None or k is None:
        compatible, status = None, "unknown"
    elif s == k:
        compatible, status = True, "compatible"
    else:
        compatible, status = False, "incompatible"
    # Additive advisory: the compatible/status/policy verdict above is a pure
    # server<->KB package-version match and says NOTHING about the live TD build.
    td_build_notice = None
    if td_build:
        td_build_notice = (
            f"KB indexed against TouchDesigner build {td_build}. This offline server "
            "cannot see which TD build you are actually running, so the 'compatible' "
            "verdict above reflects ONLY the server<->KB package-version match, NOT your "
            "live TD build. Per-operator parameter schemas (menu tokens, param "
            f"names/order) can drift across TD builds -- compare {td_build} against "
            "td-builder-live's get_td_info 'version' field and, on any mismatch, verify "
            "unusual/newer ops live (get_td_node_parameters) before trusting KB schemas "
            "verbatim."
        )
    return {
        "compatible": compatible,
        "status": status,
        "server_version": server_version,
        "kb_version": kb_version,
        "kb_td_build": td_build,
        "td_build_notice": td_build_notice,
        "policy": "warn",
    }

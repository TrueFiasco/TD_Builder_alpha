"""Lossless JSON serialization/deserialization.

This module defines a *file-level* JSON representation that is sufficient to
reconstruct an expanded `.toe.dir`/`.tox.dir` exactly (using `LosslessData`).

It is intentionally focused on:
- `.toc` raw lines + ordering
- mapping `.toc` entries -> on-disk file paths
- raw file bytes/text content (base64 for binary)

Operator/connection structures may be present, but are not required to rebuild
the expanded directory.
"""

from __future__ import annotations

from dataclasses import is_dataclass, asdict
from enum import Enum
from typing import Any, Dict, Optional

from .models import TDNetwork, Metadata, FormatLayer, LosslessData


def _serialize(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return {k: _serialize(v) for k, v in asdict(obj).items() if v is not None}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return obj


def to_lossless_json_dict(network: TDNetwork) -> Dict[str, Any]:
    """Serialize a `TDNetwork` to a JSON-serializable dict (lossless)."""
    if not network.lossless_data:
        raise ValueError("Network has no lossless_data; cannot serialize as lossless JSON.")

    payload: Dict[str, Any] = {
        "format_version": network.format_version,
        "format_layer": FormatLayer.LOSSLESS.value,
        "metadata": _serialize(network.metadata),
        "lossless_data": _serialize(network.lossless_data),
    }

    # Optional structural info (useful for debugging/analysis; not required for rebuild)
    if network.operators:
        payload["operators"] = _serialize(network.operators)
    if network.connections:
        payload["connections"] = _serialize(network.connections)
    if network.statistics:
        payload["statistics"] = _serialize(network.statistics)

    return payload


def from_lossless_json_dict(data: Dict[str, Any]) -> TDNetwork:
    """Deserialize lossless JSON dict to a `TDNetwork` suitable for `.toe.dir` rebuild."""
    layer = data.get("format_layer")
    if layer not in (FormatLayer.LOSSLESS.value, "lossless"):
        raise ValueError(f"Expected format_layer='lossless', got {layer!r}")

    meta = data.get("metadata") or {}
    metadata = Metadata(
        project_name=meta.get("project_name", "lossless_project"),
        mode=meta.get("mode", "toe"),
        root_comp=meta.get("root_comp", "project1"),
        td_version=meta.get("td_version"),
        build_number=meta.get("build_number"),
        build_date=meta.get("build_date"),
        cookrate=meta.get("cookrate", 60),
        realtime=meta.get("realtime", True),
        description=meta.get("description"),
        tags=meta.get("tags", []) or [],
        author=meta.get("author"),
        created_at=meta.get("created_at"),
    )

    ld = data.get("lossless_data") or {}
    lossless_data = LosslessData(
        raw_files=ld.get("raw_files") or {},
        toc_order=ld.get("toc_order") or [],
        toc_raw_lines=ld.get("toc_raw_lines") or [],
        toc_disk_paths=ld.get("toc_disk_paths") or {},
    )

    # For pure file-level rebuild we can omit operators/connections entirely.
    # TOEBuilder (LOSSLESS) writes raw files first, so these are not required.
    return TDNetwork(
        format_version=data.get("format_version", "2.0.0"),
        format_layer=FormatLayer.LOSSLESS,
        metadata=metadata,
        operators=[],
        connections=[],
        lossless_data=lossless_data,
        canonical_data=None,
        statistics=None,
    )


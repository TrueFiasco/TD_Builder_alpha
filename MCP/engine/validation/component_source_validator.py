"""Component-Source Validator - the td_validate half of the BUG-3 wiring fix.

Invariant (BUG-3, evidence-driven): *a component is never itself a data source.* What a
component OUTPUTS lives on an inner ``out`` op, so a bare component name in a connection
SOURCE position can never bind — TD drops it silently at load. The builder enforces this at
build time (``toe_builder_bridge._resolve_palette_source`` resolves a bare component to its
single inner out op, or FAILS LOUD naming the candidate inner ops). This validator is the
static, pre-build half: it catches the same misuse at ``td_validate`` and reports it with
the SAME vocabulary and candidate list, so a design gets the fix hint before a build runs.

Policy — mirrors the builder exactly:
  * source with an explicit inner ref (``comp/out1``) → OK.
  * ``palette`` component (looked up in the shipped ``KB/palette_components.json``):
      - 0 out ops                          → ERROR (nothing to source from);
      - index-authority OR exactly 1 out   → OK (the builder auto-binds it);
      - name-authority w/ >1 out ops       → ERROR listing the candidate out ops.
    (``index_authority = harvest.method != "offline_manifest"`` — the builder's own rule.)
  * ``external_tox`` component → SKIP: its interface needs a build-time toeexpand of the
    referenced .tox, so the builder owns that fail-loud; the validator can't decide offline.
  * plain ``COMP``-family op (no palette/external_tox):
      - 0 inner out ops                    → ERROR (a bare/empty COMP is not a data source);
      - exactly 1 inner out op             → OK (the builder resolves it);
      - >1 inner out ops                   → WARNING (the builder auto-binds the first; name
                                             it explicitly to be unambiguous).

SHIPPED-DATA ONLY: reads ``KB/palette_components.json``, never the dev corpus.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).parent.parent))

from core.models import StageReport, TDNetwork, ValidationError  # noqa: E402

_OUT_ALNUM = "out"


def _alnum(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _is_out_op(op: dict) -> bool:
    """An inner op that is an Out operator (its short type is 'out', any family)."""
    t = str(op.get("type") or "")
    t = t.split(":", 1)[1] if ":" in t else t
    return _alnum(t) == _OUT_ALNUM


def _default_palette_components() -> _Path:
    return _Path(__file__).resolve().parents[3] / "KB" / "palette_components.json"


class ComponentSourceValidator:
    def __init__(self, palette_components_path: _Path | None = None):
        self._registry = self._load(palette_components_path or _default_palette_components())

    @staticmethod
    def _load(path: _Path) -> dict:
        try:
            data = json.loads(_Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data.get("components", data) or {}

    # -- registry resolution (mirror toe_builder_bridge._palette_io_entry) --
    def _palette_out_info(self, component_name: str):
        """(-> out_op names, index_authority) for a registered palette component, or None
        if the name isn't registered (an unknown palette is the semantic stage's concern)."""
        spec = self._registry.get(component_name)
        if spec is None:
            return None
        outs = [o.get("out_op") for o in sorted(spec.get("outputs", []) or [],
                                                key=lambda x: x.get("index", 0))]
        method = (spec.get("harvest") or {}).get("method", "")
        index_authority = method != "offline_manifest"
        return outs, index_authority

    # -- input extraction --------------------------------------------------
    def _components_and_connections(self, network_json):
        """Return (components: name -> descriptor, connections: [(src, dst)]).

        descriptor kinds: 'palette' {palette}, 'external_tox', 'comp' {out_ops}. For the
        builder-dict form the full component context is present; for a converted TDNetwork
        only plain COMP-family ops survive (palette/external_tox designs don't convert), so
        we describe those from the network's operator paths."""
        components: dict[str, dict] = {}
        connections: list[tuple[str, str]] = []

        if isinstance(network_json, TDNetwork):
            # basename -> op; find COMP-family ops and their inner out children by path.
            by_path = {op.path: op for op in network_json.operators}
            for op in network_json.operators:
                fam = op.family.value if hasattr(op.family, "value") else str(op.family or "")
                if fam != "COMP":
                    continue
                name = op.path.rstrip("/").split("/")[-1]
                prefix = op.path.rstrip("/") + "/"
                out_ops = [p.split("/")[-1] for p, o in by_path.items()
                           if p.startswith(prefix) and "/" not in p[len(prefix):]
                           and _alnum(o.type) == _OUT_ALNUM]
                components.setdefault(name, {"kind": "comp", "out_ops": out_ops})
            for c in network_json.connections:
                connections.append((c.source, c.target))
            connections = [(s.split("/")[-1] if s else s, t) for s, t in connections]
            return components, connections

        # builder-dict form: walk operators + containers (like _prepass_component_io)
        def walk(ops, containers):
            for o in (ops or []):
                if isinstance(o, dict):
                    yield o
                    yield from walk(o.get("operators") or o.get("children") or [],
                                    o.get("containers") or [])
            for c in (containers or []):
                if isinstance(c, dict):
                    yield c
                    yield from walk(c.get("operators") or c.get("children") or [],
                                    c.get("containers") or [])

        for o in walk(network_json.get("operators", []), network_json.get("containers", [])):
            name = o.get("name")
            if not name or name in components:
                continue
            if o.get("palette"):
                components[name] = {"kind": "palette", "palette": o["palette"]}
            elif o.get("external_tox") or o.get("externaltox"):
                components[name] = {"kind": "external_tox"}
            elif str(o.get("family") or "").upper() == "COMP":
                inner = [c for c in (o.get("operators") or o.get("children") or []) if isinstance(c, dict)]
                components[name] = {"kind": "comp", "out_ops": [c.get("name") for c in inner if _is_out_op(c)]}

        for c in (network_json.get("connections") or []):
            if isinstance(c, dict):
                connections.append((c.get("from") or c.get("source"),
                                    c.get("to") or c.get("target")))
        # also per-operator inputs shape ({"inputs": [...]}) is builder-internal; connections
        # array is the documented form td_validate/td_build accept, so that's what we check.
        return components, connections

    # -- the rule ----------------------------------------------------------
    def _finding_for_source(self, base: str, desc: dict, idx: int):
        kind = desc["kind"]
        if kind == "external_tox":
            return None  # builder owns this (needs the .tox manifest at build time)

        if kind == "palette":
            info = self._palette_out_info(desc["palette"])
            if info is None:
                return None  # unknown palette name — semantic stage's concern
            outs, index_authority = info
            if not outs:
                return ("error", f"Cannot wire from component '{base}': a component is never "
                        f"itself a data source, and palette component '{desc['palette']}' "
                        f"contains no out operators.", None)
            if index_authority or len(outs) == 1:
                return None
            return ("error", f"Cannot wire from component '{base}': a component is never itself "
                    f"a data source; reference its inner out op. '{base}' has {len(outs)} out "
                    f"ops: {outs}. Use an explicit source, e.g. \"from\": \"{base}/{outs[0]}\".",
                    f"{base}/{outs[0]}")

        # plain COMP
        outs = desc.get("out_ops") or []
        if not outs:
            return ("error", f"Cannot wire from component '{base}': a component is never itself "
                    f"a data source and '{base}' has no inner out operator. Add an Out op inside "
                    f"it, or reference an explicit inner out op, e.g. \"from\": \"{base}/out1\".",
                    f"{base}/out1")
        if len(outs) == 1:
            return None
        return ("warning", f"Wiring from bare component '{base}' is ambiguous: it has "
                f"{len(outs)} out ops {outs}; the build binds the first. Name it explicitly, "
                f"e.g. \"from\": \"{base}/{outs[0]}\".", f"{base}/{outs[0]}")

    def validate(self, network_json) -> StageReport:
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []
        components, connections = self._components_and_connections(network_json)
        for i, (src, _dst) in enumerate(connections):
            if not src or "/" in str(src):
                continue  # explicit inner ref or empty — fine
            desc = components.get(str(src))
            if desc is None:
                continue  # source isn't a component — not this rule's concern
            found = self._finding_for_source(str(src), desc, i)
            if not found:
                continue
            sev, msg, sugg = found
            err = ValidationError(code="COMPONENT_AS_SOURCE", stage="component_wiring",
                                  severity=sev, message=msg,
                                  location=f"connections[{i}].from", suggestion=sugg)
            (errors if sev == "error" else warnings).append(err)
        status = "PASS" if not errors else "FAIL"
        return StageReport(stage="component_wiring", status=status, errors=errors, warnings=warnings)

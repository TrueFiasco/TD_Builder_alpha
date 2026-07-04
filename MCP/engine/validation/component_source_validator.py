"""Component-Source Validator - the td_validate half of the BUG-3 wiring fix.

Invariant (BUG-3, evidence-driven): *a component is never itself a data source.* What a
component OUTPUTS lives on an inner ``out`` op, so a bare component name in a connection
SOURCE position can never bind — TD drops it silently at load. The builder enforces this at
build time (``toe_builder_bridge._resolve_palette_source`` resolves a bare component to its
single inner out op, or FAILS LOUD naming the candidate inner ops). This validator is the
static, pre-build half: it catches the same misuse at ``td_validate`` and reports it with
the SAME vocabulary and candidate list, so a design gets the fix hint before a build runs.

Policy (owner-set, W3a review) — judge a bare component SOURCE against its REAL inner outs,
and prefer advisory over blocking so a VALID, buildable design is never rejected:
  * explicit inner ref (``comp/out1``)     → clean (no finding).
  * exactly ONE unambiguous output         → WARNING, design stays VALID. The builder
                                             auto-resolves the bare form to ``comp/out1``; the
                                             warning just advises the explicit reference so
                                             validate and build agree.
  * ZERO, or AMBIGUOUS multi-output        → ERROR (the user must name ``comp/<out>``).
  * ``external_tox`` component             → defer: its interface lives in an external .tox
                                             resolved at build via toeexpand — no validate-time
                                             finding (the builder owns that fail-loud).
"Unambiguous" multi-output = a live-harvested ``palette`` entry whose connector order IS
index-truth (``harvest.method != "offline_manifest"`` → the builder binds index 0
deterministically). An in-design container or a name-authority registration has no
connector-truth ordering, so >1 output is genuinely ambiguous → ERROR.

CRITICAL (fixed in W3a review): a bare-COMP source's inner ops are only visible when the
DESIGN is present. ``FormatConverter.from_builder`` FLATTENS a container's inner ops away
before this stage runs on the shipped ``td_validate`` path, which used to make every
in-design COMP look like it had ZERO outs → false ERROR on valid designs. from_builder now
stashes each component's interface on ``Operator.custom_data['component_io']``, read by the
TDNetwork branch here, so the judgement sees the real outs.

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

        descriptor kinds: 'palette' {palette}, 'external_tox', 'comp' {out_ops}. Both the
        builder-dict form and a converted TDNetwork carry the FULL component interface: the
        dict form still has the inner ops inline; `from_builder` flattens them away, so it
        stashes each component's interface on `Operator.custom_data['component_io']`
        (FormatConverter.extract_component_io) — which is what we read here. Without that
        stash a bare-COMP source looks like it has zero out ops and this stage would
        false-reject a valid, buildable design (the builder auto-resolves it to comp/out1)."""
        components: dict[str, dict] = {}
        connections: list[tuple[str, str]] = []

        if isinstance(network_json, TDNetwork):
            for op in network_json.operators:
                cio = (getattr(op, "custom_data", None) or {}).get("component_io")
                if not cio:
                    continue
                name = op.path.rstrip("/").split("/")[-1]
                components.setdefault(name, cio)
            # sources stay as authored (abs paths ok) — _bare_component_ref matches by the
            # LAST segment against component basenames, so it needs no root normalization.
            for c in network_json.connections:
                connections.append((c.source, c.target))
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

    @staticmethod
    def _bare_component_ref(src, components: dict):
        """Return the component name IFF `src` is a BARE reference to a known component —
        i.e. the source's LAST path segment names a component. Otherwise None (an explicit
        inner ref like ``comp/out1`` whose last segment is the inner op, or a non-component).

        Matching on the last segment is path-form-agnostic on purpose: ``mixer``,
        ``/project1/mixer`` and ``/project1/geo1/mixer`` all reference the SAME component and
        must get the SAME verdict — the earlier root-strip made the answer depend on path
        depth (a 2-segment abs path collapsed to a bare name and errored, while a 3-segment
        one kept a slash and was skipped). A trailing inner segment (``comp/out1``,
        ``/project1/comp/out1``) means the last segment is the inner op, not a component, so
        it is correctly treated as an explicit reference and drawn no finding."""
        segs = [s for s in str(src or "").split("/") if s]
        if not segs:
            return None
        return segs[-1] if segs[-1] in components else None

    # -- the rule ----------------------------------------------------------
    #
    # Owner policy (W3a review): a bare component SOURCE, judged against the component's real
    # inner out ops —
    #   * exactly one unambiguous output  -> WARNING, design stays VALID (the builder
    #                                        auto-resolves it to comp/out1; validate + build agree);
    #   * zero, or ambiguous multi-output -> ERROR (the user must name comp/<out>);
    #   * external_tox (inner interface not in the design; resolved at build via toeexpand)
    #                                     -> defer, no validate-time finding.
    # "Unambiguous" multi-output = a live-harvested palette entry whose connector order IS
    # index-truth (the builder binds index 0 deterministically); an in-design container or a
    # name-authority registration has no connector-truth ordering, so multi-output is ambiguous.
    def _finding_for_source(self, base: str, desc: dict, idx: int):
        kind = desc.get("kind")
        if kind == "external_tox":
            return None  # builder owns this (needs the .tox manifest at build time)

        if kind == "palette":
            info = self._palette_out_info(desc.get("palette"))
            if info is None:
                return None  # unknown palette name — semantic stage's concern
            outs, index_authority = info
            what = f"palette component '{desc.get('palette')}'"
        elif kind == "comp":
            outs = [o for o in (desc.get("out_ops") or []) if o]
            index_authority = False   # in-design output order is not connector-truth
            what = f"component '{base}'"
        else:
            return None

        if not outs:
            return ("error", f"Cannot wire from component '{base}': a component is never itself "
                    f"a data source, and {what} has no inner out operator. Add an Out op inside "
                    f"it, or reference an explicit inner out op, e.g. \"from\": \"{base}/out1\".",
                    f"{base}/out1")
        if len(outs) == 1 or index_authority:
            # deterministic single/index-truth binding — buildable, but the bare form is
            # implicit; advise the explicit reference (design stays VALID).
            return ("warning", f"Wiring from bare component '{base}' binds its output "
                    f"'{outs[0]}' implicitly — a component is never itself a data source. Name "
                    f"it explicitly, e.g. \"from\": \"{base}/{outs[0]}\".", f"{base}/{outs[0]}")
        # ambiguous multi-output — the user must say which.
        return ("error", f"Cannot wire from component '{base}': a component is never itself a "
                f"data source; reference its inner out op. {what} has {len(outs)} out ops: "
                f"{outs}. Use an explicit source, e.g. \"from\": \"{base}/{outs[0]}\".",
                f"{base}/{outs[0]}")

    def validate(self, network_json) -> StageReport:
        errors: list[ValidationError] = []
        warnings: list[ValidationError] = []
        components, connections = self._components_and_connections(network_json)
        for i, (src, _dst) in enumerate(connections):
            base = self._bare_component_ref(src, components)
            if base is None:
                continue  # explicit inner ref, non-component source, or empty — no finding
            found = self._finding_for_source(base, components[base], i)
            if not found:
                continue
            sev, msg, sugg = found
            err = ValidationError(code="COMPONENT_AS_SOURCE", stage="component_wiring",
                                  severity=sev, message=msg,
                                  location=f"connections[{i}].from", suggestion=sugg)
            (errors if sev == "error" else warnings).append(err)
        status = "PASS" if not errors else "FAIL"
        return StageReport(stage="component_wiring", status=status, errors=errors, warnings=warnings)

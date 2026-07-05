"""Component-Source Validator - the td_validate half of the BUG-3 wiring fix.

Invariant (BUG-3, evidence-driven): *a component is never itself a data source.* What a
component OUTPUTS lives on an inner ``out`` op, so a bare component name in a connection
SOURCE position can never bind — TD drops it silently at load. The builder enforces this at
build time (``toe_builder_bridge._resolve_palette_source`` resolves a bare component to its
single inner out op, or FAILS LOUD naming the candidate inner ops). This validator is the
static, pre-build half: it catches the same misuse at ``td_validate`` and reports it with
the SAME vocabulary and candidate list, so a design gets the fix hint before a build runs.

Policy (owner-set, W3a review) — judge a BARE component SOURCE against its REAL inner outs,
and prefer advisory over blocking so a VALID, buildable design is never rejected:
  * explicit inner ref (``comp/out1``)     → clean (no finding).
  * exactly ONE unambiguous output         → informational WARNING, design stays VALID. The
                                             build auto-resolves the bare source to its single
                                             output. The warning does NOT recommend rewriting
                                             to ``comp/out1`` — td_validate's reference stage
                                             currently rejects that inner-op path (from_builder
                                             flattens it away), so that advice would break a
                                             design that already validates (deferred follow-up).
  * ZERO, or AMBIGUOUS multi-output        → ERROR (the user must name ``comp/<out>``).
  * ``external_tox`` component             → defer: its interface lives in an external .tox
                                             resolved at build via toeexpand — no validate-time
                                             finding (the builder owns that fail-loud).
"Unambiguous" multi-output = a live-harvested ``palette`` entry whose connector order IS
index-truth (``harvest.method != "offline_manifest"`` → the builder binds index 0
deterministically). An in-design container or a name-authority registration has no
connector-truth ordering, so >1 output is genuinely ambiguous → ERROR.

WHAT COUNTS AS A BARE COMPONENT SOURCE (W3a re-review): a source is bare IFF its FULL
normalized identity (``_norm_identity``) EXACTLY matches a known TOP-LEVEL component keyed by
its own full identity. Matching the last path segment alone was WRONG — it mis-read an
explicit ``comp/out1`` (or a nested ``foo/mixer``) as a bare reference to a DIFFERENT
component that happened to be named ``out1``/``mixer``, hard-blocking a valid design. Keying
by identity (never basename) also keeps two same-basename components distinct.

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
            root = (network_json.metadata.root_comp or "").strip("/")
            for op in network_json.operators:
                cio = (getattr(op, "custom_data", None) or {}).get("component_io")
                if not cio:
                    continue
                # key by FULL normalized IDENTITY, never basename: two same-basename comps at
                # different paths stay distinct, and an explicit inner ref can never collide
                # with a same-named component (a comp literally called 'out1').
                components.setdefault(self._norm_identity(op.path, root), cio)
            for c in network_json.connections:
                connections.append((self._norm_identity(c.source, root), c.target))
            return components, connections

        # builder-dict form: the TOP-LEVEL operators/containers ARE the components (a nested
        # op is a component's interface, not a separate component — matches the TDNetwork
        # stash, which only carries top-level ops).
        root = str((network_json.get("metadata") or {}).get("root_comp") or "project1")
        for o in (list(network_json.get("operators") or []) + list(network_json.get("containers") or [])):
            if not isinstance(o, dict) or not o.get("name"):
                continue
            ident = self._norm_identity(o.get("path") or o["name"], root)
            if ident in components:
                continue
            if o.get("palette"):
                components[ident] = {"kind": "palette", "palette": o["palette"]}
            elif o.get("external_tox") or o.get("externaltox"):
                components[ident] = {"kind": "external_tox"}
            elif str(o.get("family") or "").upper() == "COMP":
                inner = [c for c in (o.get("operators") or o.get("children") or []) if isinstance(c, dict)]
                components[ident] = {"kind": "comp", "out_ops": [c.get("name") for c in inner if _is_out_op(c)]}
        for c in (network_json.get("connections") or []):
            if isinstance(c, dict):
                src = c.get("from") or c.get("source")
                connections.append((self._norm_identity(src, root), c.get("to") or c.get("target")))
        return components, connections

    @staticmethod
    def _norm_identity(path, root: str) -> str:
        """Canonical component identity for an operator path OR a connection source: drop
        empty segments and a single leading root_comp segment, then rejoin.

        from_builder is INCONSISTENT — a top-level op lands at '/mixer' (root_comp dropped)
        while a multi-segment / root-qualified connection source resolves to
        '/project1/mixer/out1' — so BOTH operator paths and sources must pass through here
        before they can be compared. A source is then a BARE component reference IFF its
        normalized identity EXACTLY matches a known component identity: 'mixer' and
        '/project1/mixer' both normalize to 'mixer' (match), while an explicit 'comp/out1' or
        '/project1/comp/out1' normalizes to 'comp/out1' (no exact match -> treated as an
        explicit inner ref, no finding) EVEN IF a component happens to be named 'out1'."""
        segs = [s for s in str(path or "").split("/") if s]
        if segs and root and segs[0] == root:
            segs = segs[1:]
        return "/".join(segs)

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
            # deterministic single/index-truth binding — the build auto-resolves it and this
            # design is VALID. This is an INFORMATIONAL warning only: it must NOT steer the
            # user to rewrite bare 'comp' -> 'comp/out1', because td_validate's reference stage
            # currently rejects that inner-op path (from_builder flattens the inner op away) —
            # so the advice would break a design that already validates. (Teaching reference to
            # accept the flattened inner path is a tracked, deferred follow-up.)
            return ("warning", f"Source '{base}' is a component, not a data source of its own; "
                    f"the build resolves it to its output '{outs[0]}'. This builds and validates "
                    f"correctly — noted for clarity, no change needed.", None)
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
            # `src` is the normalized identity. An EXACT match against a known top-level
            # component is a BARE component source (any path form). An explicit inner ref
            # ('comp/out1'), a nested-component ref, or a non-component does NOT exact-match
            # -> no finding. Exact identity match (not last-segment) is what kills the
            # collision where a source ends in a segment that names a different component.
            desc = components.get(src) if src else None
            if desc is None:
                continue
            base = src.split("/")[-1]
            found = self._finding_for_source(base, desc, i)
            if not found:
                continue
            sev, msg, sugg = found
            err = ValidationError(code="COMPONENT_AS_SOURCE", stage="component_wiring",
                                  severity=sev, message=msg,
                                  location=f"connections[{i}].from", suggestion=sugg)
            (errors if sev == "error" else warnings).append(err)
        status = "PASS" if not errors else "FAIL"
        return StageReport(stage="component_wiring", status=status, errors=errors, warnings=warnings)

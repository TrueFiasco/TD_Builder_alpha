"""Grounding Validator - Stage 2.5: operator FAMILY-correctness vs live-TD grounding.

Grounds each design op's ``(family, type)`` against the SHIPPED KB
(``KB/operators.json``'s per-op ``build_token`` = the captured live-TD ``.n`` token).
This closes the last gap the build-correctness gate exposed. The builder now grounds the
token it emits (``toe_builder_bridge._grounded_build_token``) and the ``OperatorRegistry``
recognises the real token, but nothing told ``td_validate`` that a design's DECLARED
``(type, family)`` is *wrong-family* — e.g. ``{"type": "add", "family": "SOP"}`` when the
op the user described is really ``TOP:add``. Semantic validation only checks that the type
exists SOMEWHERE; grounding checks it exists in the DECLARED family, and if not, surfaces
the family/token the live capture grounds it to.

Two entry points (the two insertion sites named in the original prototype):
  * ``validate(network_json) -> StageReport``  — pipeline stage 2.5. Findings are
    WARNINGS: grounding is advisory and never flips a passing design to FAIL (a wrong
    family still builds *something*; the warning names the correct token so the caller can
    fix it). This is the regression-safe posture; a later wave may promote to error once
    coverage is proven false-positive-free.
  * ``ground_design(design) -> design'``  — build-time normalisation: rewrite each op's
    ``type`` to its grounded ``build_token``. The builder realises the SAME override inline
    via ``toe_builder_bridge._grounded_build_token``, reading the SAME KB source, so the
    two agree by construction.

SHIPPED-DATA ONLY: grounds from ``KB/operators.json`` (build_token + names), never the dev
corpus (``New KB build/Resources/operator_ground_truth/``), which is not in the release.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).parent.parent))

from core.models import StageReport, TDNetwork, ValidationError  # noqa: E402

_OP_FAMILIES = ("CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP")


def _alnum(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _default_kb_operators() -> _Path:
    """Repo-root/KB/operators.json — the same shipped bundle the OperatorRegistry loads
    (validation/ -> engine/ -> MCP/ -> repo root)."""
    return _Path(__file__).resolve().parents[3] / "KB" / "operators.json"


class GroundingValidator:
    """Stage 2.5: family-correctness against the shipped KB build_token grounding.

    Builds three indexes from ``KB/operators.json`` once:
      * ``known_keys``       — ``(FAMILY, alnum_alias)`` that name a REAL operator (from the
                               display name, the build_token type, and the python_class
                               base). "Known" ⊇ "grounded": a real op with no build_token is
                               still known in its own family, so it never false-flags.
      * ``families_by_type`` — ``alnum_type -> {families}`` (from display names) for
                               wrong-family suggestions.
      * ``token_by_key``     — ``(FAMILY, alnum_alias) -> build_token`` for ``ground_design``.
    """

    def __init__(self, kb_operators_path: _Path | None = None):
        self.known_keys: set[tuple[str, str]] = set()
        self.families_by_type: dict[str, set[str]] = {}
        self.token_by_key: dict[tuple[str, str], str] = {}
        self._load(kb_operators_path or _default_kb_operators())

    # -- index build -------------------------------------------------------
    def _load(self, path: _Path) -> None:
        try:
            data = json.loads(_Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # No KB (e.g. KB-free lane) → empty indexes → grounding is a silent no-op.
            return
        for o in data.get("operators", []):
            if o.get("type") != "operator":
                continue
            name = o.get("name") or ""
            fam = (o.get("family") or "").upper()
            if fam not in _OP_FAMILIES or not name:
                continue
            base = name[: -len(fam)].strip() if name.upper().endswith(fam) else name
            name_alias = _alnum(base)

            aliases = {name_alias}
            bt = o.get("build_token")
            if bt and ":" in bt:
                aliases.add(_alnum(bt.split(":", 1)[1]))
            cls = o.get("python_class") or ""
            if cls.endswith("_Class"):
                cls_base = cls[: -len("_Class")]
                if cls_base.upper().endswith(fam):
                    cls_base = cls_base[: -len(fam)]
                aliases.add(_alnum(cls_base))
            aliases.discard("")

            for a in aliases:
                self.known_keys.add((fam, a))
                if bt and ":" in bt:
                    self.token_by_key.setdefault((fam, a), bt)
            if name_alias:
                self.families_by_type.setdefault(name_alias, set()).add(fam)

    # -- input normalisation ----------------------------------------------
    @staticmethod
    def _iter_ops(network_json):
        """Yield ``(index, family_upper, short_type)`` for a builder dict OR a TDNetwork."""
        if isinstance(network_json, TDNetwork):
            for i, op in enumerate(network_json.operators):
                fam = op.family.value if hasattr(op.family, "value") else str(op.family or "")
                typ = op.type or ""
                yield i, fam.upper(), typ
        else:
            for i, op in enumerate(network_json.get("operators", []) or []):
                fam = str(op.get("family") or "")
                typ = str(op.get("type") or "")
                # colon-form type carries its own family; it wins over an absent field
                if ":" in typ:
                    pre, rest = typ.split(":", 1)
                    if not fam:
                        fam = pre
                    typ = rest
                yield i, fam.upper(), typ

    # -- findings ----------------------------------------------------------
    def check_design(self, network_json) -> list[dict]:
        """Return grounding findings (dicts). A wrong-family op yields a
        GROUNDING_FAMILY_MISMATCH pointing at the grounded family/token."""
        findings: list[dict] = []
        for i, fam, typ in self._iter_ops(network_json):
            if not fam or not typ:
                continue  # semantic stage owns missing-field errors
            t = _alnum(typ.split(":", 1)[1] if ":" in typ else typ)
            if not t:
                continue
            if (fam, t) in self.known_keys:
                continue  # real operator in the declared family — grounded / OK
            other = sorted(self.families_by_type.get(t, set()) - {fam})
            if other:
                sugg = self.token_by_key.get((other[0], t)) or f"{other[0]}:{typ}"
                fams_str = ", ".join(other)
                findings.append({
                    "code": "GROUNDING_FAMILY_MISMATCH",
                    "severity": "warning",
                    "location": f"operators[{i}].family",
                    "message": (f"'{typ}' is not a {fam} operator; live TD grounds it under "
                                f"{fams_str}. Did you mean {sugg!r}?"),
                    "suggestion": sugg,
                })
            # else: type is unknown under EVERY family → an ungrounded/new op. Stay silent;
            # the semantic stage already flags genuinely-unknown types, and grounding must
            # not false-flag the real ops that legitimately carry no build_token yet.
        return findings

    def validate(self, network_json) -> StageReport:
        """Pipeline stage entry point. Emits WARNINGS (never errors) so a grounded
        finding surfaces in td_validate without flipping a passing design to FAIL."""
        warnings = [
            ValidationError(
                code=f["code"], stage="grounding", severity="warning",
                message=f["message"], location=f.get("location"), suggestion=f.get("suggestion"),
            )
            for f in self.check_design(network_json)
        ]
        return StageReport(stage="grounding", status="PASS", errors=[], warnings=warnings)

    # -- build-time override ----------------------------------------------
    def ground_design(self, design: dict) -> dict:
        """Return a copy of ``design`` with each op's ``type`` replaced by the captured
        ``build_token`` when a correction exists (idempotent; only overrides when the
        grounding has a captured token). The builder applies the SAME correction inline via
        ``_grounded_build_token`` — this is the standalone/normalisation form of it."""
        out = json.loads(json.dumps(design))
        for op in out.get("operators", []) or []:
            fam = str(op.get("family") or "")
            typ = str(op.get("type") or "")
            if ":" in typ:
                pre, rest = typ.split(":", 1)
                if not fam:
                    fam = pre
                typ = rest
            key = (fam.upper(), _alnum(typ))
            bt = self.token_by_key.get(key)
            if bt and bt != op.get("type"):
                op["type"] = bt
        return out

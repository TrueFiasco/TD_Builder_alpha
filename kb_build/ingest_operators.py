"""
§6.1 operator_overview (~673) + §6.2 parameter_group (~1,700).

Both are re-grounded from operators.json, which is ALREADY ground-truth-merged:
each parameter carries a typed `default` (5 / "average" / True), real `type`
(menu/float/toggle/string/op), `menuNames`, `page` with source='ground_truth'.
Identity (name/family/python_class/.n token) comes from the Identity join, and
the SPACED canonical name is emitted — never the underscored wiki-title form —
so the name-integrity gate reads 0 retokenized for these chunks (294 -> 0).

This replaces the old per-param fan-out (10,899 parameter chunks) with one
condensed group per operator page (~1,700) and drops the orphan/python dump,
delivering the ~4x index-size cut while keeping operator_lookup + parameter
answerable. parent_chunk links each group back to its operator_overview.
"""
from __future__ import annotations

import re

import common as C

_BOX = "⊞"  # ⊞ artifact that prefixes many wiki param descriptions


def _clean(desc: str) -> str:
    if not desc:
        return ""
    d = desc.replace(_BOX, " ").strip()
    d = re.sub(r"^\s*-\s*", "", d)
    return " ".join(d.split())


def _gist(desc: str, words: int = 9) -> str:
    d = _clean(desc)
    if not d:
        return ""
    toks = d.split()
    return " ".join(toks[:words]) + ("…" if len(toks) > words else "")


def _default_repr(p: dict) -> str:
    dv = p.get("default")
    t = p.get("type")
    if dv is None or dv == "":
        return ""
    if t in ("string", "menu", "OP", "op") and isinstance(dv, str):
        return f"'{dv}'"
    if isinstance(dv, bool):
        return "True" if dv else "False"
    return str(dv)


def _page_of(p: dict) -> str:
    pg = p.get("page")
    if pg in (None, ""):
        sec = (p.get("section") or "").replace("Parameters - ", "").replace(" Page", "").strip()
        return sec or "General"
    return pg


def _key_params(o: dict, limit: int = 6) -> list[str]:
    """The operator-specific param codes (skip the shared Common page)."""
    specific = [p["code"] for p in o.get("parameters", []) if _page_of(p).lower() != "common"]
    if len(specific) < 3:
        specific = [p["code"] for p in o.get("parameters", [])]
    seen, out = set(), []
    for c in specific:
        if c not in seen:
            seen.add(c)
            out.append(c)
        if len(out) >= limit:
            break
    return out


def _menu_labels(p: dict, cap: int = 6) -> str:
    """Compact menu-label list for a single menu param, e.g. [Add/Subtract/Multiply]."""
    labels = [str(x) for x in (p.get("menuLabels") or []) if x][:cap]
    return f" [{'/'.join(labels)}]" if labels else ""


def build(idn: C.Identity) -> list[dict]:
    rows: list[dict] = []
    for o in idn.operators:
        name = o.get("name")
        if not name:
            continue
        ident = idn.identity_meta(o)
        family = o.get("family") or ""
        pyc = o.get("python_class") or ""
        summary = " ".join((o.get("summary") or "").split())
        # keep up to 4 sentences of the capability summary
        m = re.split(r"(?<=[.!?])\s+", summary)
        short = " ".join(m[:4]).strip() if m else summary
        if len(short) > 520:
            short = short[:517].rstrip() + "…"
        oid = f"op:{C.slug(pyc or name)}:overview"

        # --- §6.1 operator_overview — a PURE capability chunk: name + explicit
        # family word + full summary. No param codes / menu labels here (those
        # live in parameter_group), so it does not outrank its own param groups
        # on parameter queries, and carries no format-noise. ---
        ov = f"{name} ({family} operator). {short or name + '.'} [class:{pyc}]"
        rows.append(C.make_row(oid, ov, "operator_overview", C.STORE_OPERATOR, dict(ident)))

        # --- §6.2 parameter_group (one per page) ---
        pages: dict[str, list[dict]] = {}
        for p in o.get("parameters", []):
            pages.setdefault(_page_of(p), []).append(p)

        for page, params in pages.items():
            # Front-load the param DISPLAY NAMES + codes so the specific term a
            # parameter query asks for ("Black Level", "Filter Size") sits at the
            # dense head of the text instead of being diluted by 14 gists.
            head = ", ".join(f"{p.get('display_name') or p['code']} ({p['code']})" for p in params[:14])
            parts = []
            for p in params[:12]:
                dr = _default_repr(p)
                g = _gist(p.get("description"), words=5)
                seg = f"{p['code']} ({p.get('display_name') or p['code']}"
                seg += f", {dr})" if dr else ")"
                # menu LABELS (Add/Subtract/Multiply, RMS Power, …) — the operation vocab
                seg += _menu_labels(p)
                if g:
                    seg += f": {g}"
                parts.append(seg)
            more = f" (+{len(params) - 12} more)" if len(params) > 12 else ""
            # Lead with name + page + display-name index (repeat name + explicit family
            # to fight MiniLM cross-family confusion; Phase-2 rerank resolves the rest).
            text = (f"{name} ({family} operator) '{page}' parameters: {head}. "
                    f"Codes & defaults — " + "; ".join(parts) + more
                    + f". class {pyc}. Hydrate: get_parameter_detail('{name}', <code>).")
            pmeta = dict(ident)
            pmeta["parameter_group"] = page
            pmeta["parameters"] = [p["code"] for p in params]
            rows.append(C.make_row(
                f"param:{C.slug(pyc or name)}:{C.slug(page)}", text,
                "parameter_group", C.STORE_PARAM, pmeta, parent=oid))
    return rows


INPUTS = [C.SHIPPED_KB / "operators.json", C.GT / "operator_types.json"]

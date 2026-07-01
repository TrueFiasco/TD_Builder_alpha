"""
§6.7 Example networks — OPSnippets ``real_example`` chunks.

Each official OPSnippet (snippets/semantic/<optype>.json) is a self-contained
example network. We emit one condensed chunk per example: the canonical primary
operator + distinct co-ops (helpers like readMe / annotate / null / out stripped)
+ a few real non-default params + the curator sentence from index.tsv (the
semantic dumps' own description field is usually empty).

Identity: operator_name + python_class are taken from the Identity registry
(canonical), set ONLY when the optype resolves — a real_example never asserts an
unresolved python_class, so the name-integrity gate stays at 0 unresolved.
"""
from __future__ import annotations

import csv
import json

import common as C

_HELPER_NAMES = {"readme", "annotate"}
_HELPER_TYPES = {"DAT:text", "COMP:annotate"}
_HELPER_BASES = {"null", "out", "in", "comment"}


def _curator_index() -> dict[str, str]:
    """relpath -> first curator sentence from index.tsv."""
    out: dict[str, str] = {}
    with open(C.SNIPPETS / "index.tsv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            rel = (row.get("relpath") or "").strip()
            txt = (row.get("text") or "").strip()
            if rel and txt:
                out[rel.lower()] = txt.split(". ")[0].strip().rstrip(".") + "."
    return out


def _op_for_optype(idn: C.Identity, optype: str):
    """Resolve an OPSnippet optype (e.g. 'analyzeCHOP') to an operators.json record."""
    return idn.by_pyclass.get(optype + "_Class")


def build(idn: C.Identity) -> list[dict]:
    import glob

    curators = _curator_index()
    rows: list[dict] = []

    for path in sorted(glob.glob(str(C.SNIPPETS / "semantic" / "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        optype = data.get("operator_type") or ""
        op_rec = _op_for_optype(idn, optype)
        primary_name = op_rec.get("name") if op_rec else optype
        family = op_rec.get("family") if op_rec else None

        for ex in data.get("examples", []):
            ex_name = ex.get("name") or "example"
            ops = ex.get("operators", []) or []
            # distinct co-op types, helpers stripped
            co_types, notable = [], []
            for op in ops:
                nm = (op.get("name") or "").lower()
                ty = op.get("type") or ""
                base = ty.split(":")[-1].lower()
                if nm in _HELPER_NAMES or ty in _HELPER_TYPES or base in _HELPER_BASES:
                    continue
                if ty and ty not in co_types:
                    co_types.append(ty)
                for pk, pv in list((op.get("parameters") or {}).items())[:4]:
                    if isinstance(pv, (int, float, str)) and str(pv) not in ("", "0", "off"):
                        notable.append(f"{base}.{pk}={pv}")
            if not co_types:
                continue
            rel = f"{(family or optype[:3]).upper()}/{optype}/{ex_name}".lower()
            # try a couple of relpath shapes for the curator join
            curator = curators.get(rel) or curators.get(f"{optype}/{ex_name}".lower()) or ""
            # The embedded text is the SEARCH BODY: capability (curator) + network shape.
            # Real param VALUES live in meta.notable_params (hydration detail) so an example
            # does not crowd parameter-lookup queries it cannot actually answer (plan §5).
            text = (f"{primary_name} example — {curator} "
                    f"Network: {', '.join(co_types[:8])}."
                    + f" [example_id={optype}/{ex_name}"
                    + (f" | primary={op_rec['python_class']}" if op_rec else "")
                    + (f" | hydrate=find_operator_examples('{op_rec['python_class']}')]" if op_rec else "]"))
            meta = {"example_id": f"{optype}/{ex_name}", "license_tier": "public"}
            if notable:
                meta["notable_params"] = notable[:6]
            if op_rec:
                meta.update({"operator_name": primary_name, "name": primary_name,
                             "family": family, "python_class": op_rec["python_class"]})
            rows.append(C.make_row(
                f"ex:{C.slug(optype)}:{C.slug(ex_name)}", text, "real_example",
                C.STORE_EXAMPLE, meta))
    return rows


INPUTS = [C.SNIPPETS / "index.tsv"]

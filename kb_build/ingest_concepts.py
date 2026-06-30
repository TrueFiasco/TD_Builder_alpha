"""
§6.5 Concepts / Glossary — concept chunks (vocabulary grounding).

One chunk per term from concept_semantic_descriptions.yaml (clean Haiku
definitions), with ≤5 canonical related operators derived by inverting
operators.json `.concepts` (so related ops are guaranteed canonical names, not
the ~40% non-canonical fragments the old related_operators field carried).

Concept chunks carry meta.term (not name/python_class), so bears_identity is
False and they pass the name-integrity gate untouched.
"""
from __future__ import annotations

import yaml

import common as C


def _concept_to_ops(idn: C.Identity) -> dict[str, list[str]]:
    inv: dict[str, set] = {}
    for o in idn.operators:
        nm = o.get("name")
        for c in (o.get("concepts") or []):
            inv.setdefault(C._norm(c), set()).add(nm)
    return {k: sorted(v) for k, v in inv.items()}


def build(idn: C.Identity) -> list[dict]:
    rows: list[dict] = []
    inv = _concept_to_ops(idn)
    cs = yaml.safe_load((C.HAIKU / "concept_semantic_descriptions.yaml").read_text(encoding="utf-8")) or {}
    for term, definition in cs.items():
        d = " ".join(str(definition or "").split())
        related = inv.get(C._norm(term), [])[:5]
        rel = f" Related operators: {', '.join(related)}." if related else ""
        text = f"CONCEPT: {term} — {d}{rel} [hydrate: operators.json#concepts]"
        rows.append(C.make_row(
            f"concept:{C.slug(term)}", text, "concept", C.STORE_CONCEPT,
            {"term": term, "license_tier": "public"}))
    return rows


INPUTS = [C.HAIKU / "concept_semantic_descriptions.yaml"]

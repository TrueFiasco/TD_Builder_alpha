"""
§6.3 Python API — class_method + python_pattern + callback (re-grounded, dump dropped).

Replaces the 18,042 boilerplate ``python_example`` chunks with curated, runnable
handles:
  * class_method  — one chunk per (Class, method) from the Haiku class digests
                    (CHOP_Class.numSamples, AudiofileinCHOP_Class.metadata, …).
  * python_pattern— one chunk per named pattern from python_patterns_semantics
                    (create_operator, access_chop_value, chop_to_numpy, …).
  * callback      — one chunk per TD callback (onValueChange, onParValueChange, …).

Name-integrity: these chunks carry meta.class / meta.method / meta.name but NOT
python_class — a base-class token like ``CHOP_Class`` is not an operator
python_class, so setting it would register as an unresolved identity. With no
python_class and no operator name/family, ``bears_identity`` stays False.
"""
from __future__ import annotations

import yaml

import common as C


def _load_class_methods() -> dict[tuple[str, str], str]:
    """Union of the two Haiku class digests, keyed by (Class, method)."""
    pairs: dict[tuple[str, str], str] = {}

    base = yaml.safe_load((C.HAIKU / "base_class_semantics.yaml").read_text(encoding="utf-8")) or {}
    for key, desc in base.items():
        if "." in key:
            cls, meth = key.split(".", 1)
            pairs[(cls, meth)] = desc

    cs = yaml.safe_load((C.HAIKU / "class_semantic_descriptions.yaml").read_text(encoding="utf-8")) or {}
    for cls, methods in cs.items():
        if not isinstance(methods, dict):
            continue
        for meth, desc in methods.items():
            pairs.setdefault((cls, meth), desc)
    return pairs


def build(idn: C.Identity) -> list[dict]:
    rows: list[dict] = []

    # --- class_method ---
    for (cls, meth), desc in sorted(_load_class_methods().items()):
        d = " ".join(str(desc or "").split())
        text = f"{cls}.{meth} — {d}" if d else f"{cls}.{meth}"
        rows.append(C.make_row(
            f"pym:{C.slug(cls)}:{C.slug(meth)}", text, "class_method", C.STORE_PYTHON,
            {"class": cls, "method": meth}))

    # --- python_pattern ---
    pp = yaml.safe_load((C.HAIKU / "python_patterns_semantics.yaml").read_text(encoding="utf-8")) or {}
    for nm, body in pp.items():
        desc = " ".join(str((body or {}).get("description") or "").split())
        code = str((body or {}).get("code") or "").strip()
        text = f"Python pattern '{nm}': {desc}"
        if code:
            text += f"  Code: {code}"
        rows.append(C.make_row(
            f"pyp:{C.slug(nm)}", text, "python_pattern", C.STORE_PYTHON,
            {"name": nm, "pattern": nm}))

    # --- callback ---
    cb = yaml.safe_load((C.HAIKU / "python_callbacks_semantics.yaml").read_text(encoding="utf-8")) or {}
    for nm, body in cb.items():
        desc = " ".join(str((body or {}).get("description") or "").split())
        sig = str((body or {}).get("signature") or "").strip()
        text = f"Callback {nm}{('('+sig+')') if sig and '(' not in sig else (' ' + sig if sig else '')}: {desc}"
        rows.append(C.make_row(
            f"pycb:{C.slug(nm)}", text, "callback", C.STORE_PYTHON,
            {"name": nm, "callback": nm}))

    return rows


INPUTS = [
    C.HAIKU / "base_class_semantics.yaml",
    C.HAIKU / "class_semantic_descriptions.yaml",
    C.HAIKU / "python_patterns_semantics.yaml",
    C.HAIKU / "python_callbacks_semantics.yaml",
]

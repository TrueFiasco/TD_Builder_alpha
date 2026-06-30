"""
§6.4 Palette components -> BLOCK chunks (block_overview / block_usecase / block_io).

The discriminator is the prebuilt component's capability one-liner + its name +
category, so an agent searching "bloom glow prebuilt component" finds the bloom
palette block instead of hand-building it. Palette blocks deliberately do NOT
assert operator identity (no python_class / OP family on the chunk) — a comp is
instantiated by copying its .tox, not by create_td_node — so they stay clean
through the name-integrity gate.

Sources (merged by case-normalized name):
  expertise/palette_semantic_catalog.yaml  — 278 catalog entries (primary)
  palette_lossless/enriched_index.json     — inner-op inventory + complexity (264)
  haiku_output/palette_descriptions.yaml   — the discriminating summary, by category
"""
from __future__ import annotations

import json
import yaml

import common as C


def _load():
    cat = yaml.safe_load((C.EXPERT / "palette_semantic_catalog.yaml").read_text(encoding="utf-8"))
    cat = {k: v for k, v in cat.items() if k != "_metadata" and isinstance(v, dict)}
    enriched = json.loads((C.PAL_LOSSLESS / "enriched_index.json").read_text(encoding="utf-8")).get("palettes", {})
    descs_by_cat = yaml.safe_load((C.HAIKU / "palette_descriptions.yaml").read_text(encoding="utf-8"))
    # flatten {category:{name:desc}} -> {name_norm: desc}
    desc = {}
    for _cat, items in (descs_by_cat or {}).items():
        for nm, d in (items or {}).items():
            desc[C._norm(nm)] = d
    # case-normalized enriched lookup
    enr = {C._norm(k): v for k, v in enriched.items()}
    return cat, enr, desc


def build(idn: C.Identity) -> list[dict]:
    cat, enr, desc = _load()
    rows: list[dict] = []

    for name, e in sorted(cat.items()):
        nn = C._norm(name)
        category = e.get("category") or "Uncategorized"
        enrich = enr.get(nn, {})
        # discriminating summary: haiku description > catalog summary > purpose
        summary = (desc.get(nn) or e.get("summary") or e.get("purpose") or "").strip()
        summary = " ".join(summary.split())
        use_cases = [u for u in (e.get("use_cases") or []) if u]
        key_ops = [k for k in (e.get("key_operators") or []) if k and k != "help"]
        contained = enrich.get("contained_operators") or []
        op_count = enrich.get("operator_count")
        complexity = enrich.get("complexity")
        tox_path = e.get("tox_path") or f"{category}\\{name}.tox"
        wiki = e.get("wiki_url") or f"https://docs.derivative.ca/Palette:{name}"

        base_meta = {
            "name": name,                 # block name — meta_name_any matches lowercased
            "palette_name": name,
            "category": category,
            "has_ui": bool(e.get("has_ui")),
            "complexity": complexity,
            "operator_count": op_count,
            "tox_path": tox_path,
            "wiki_url": wiki,
            "license_tier": "public",
        }
        oid = f"block:{C.slug(name)}:overview"

        # --- block_overview (primary, richest discriminator) ---
        uc = f" Use for: {'; '.join(use_cases)}." if use_cases else ""
        ov = (f"PALETTE COMPONENT: {name} [{category}] — "
              f"{summary or f'{name} prebuilt {category} component.'}"
              f" Prebuilt TouchDesigner Palette component"
              f"{f' ({op_count} inner operators, {complexity})' if op_count else ''}."
              f"{uc}"
              f" Instantiate: drag {tox_path} from the Palette browser, or right-click the network"
              f" > Add Operator > Palette:{name} (copy the .tox; do not hand-build).")
        rows.append(C.make_row(oid, ov, "block_overview", C.STORE_BLOCK, dict(base_meta)))

        # --- block_usecase (use-case / intent phrasing) ---
        tags = ", ".join(use_cases + key_ops) if (use_cases or key_ops) else category
        usecase_txt = (f"PALETTE USE-CASE: {name} ({category}). {summary} "
                       f"When you need {tags.lower()}, use the prebuilt {name} component rather than"
                       f" building it from scratch. Tags: {tags}. wiki: {wiki}")
        rows.append(C.make_row(f"block:{C.slug(name)}:usecase", usecase_txt,
                               "block_usecase", C.STORE_BLOCK, dict(base_meta), parent=oid))

        # --- block_io (inner operator inventory) — only when we have lossless data ---
        if contained:
            distinct = sorted(set(contained))
            io_txt = (f"PALETTE I/O: {name} ({category}) — internal network of {op_count} operators"
                      f" ({', '.join(distinct[:18])}). It is a self-contained COMP; wire its TOP/CHOP"
                      f" inputs/outputs like any component.")
            io_meta = dict(base_meta)
            io_meta["contained_operators"] = distinct
            rows.append(C.make_row(f"block:{C.slug(name)}:io", io_txt,
                                   "block_io", C.STORE_BLOCK, io_meta, parent=oid))

    return rows


# inputs this ingester pins in sources.lock.json
INPUTS = [
    C.EXPERT / "palette_semantic_catalog.yaml",
    C.PAL_LOSSLESS / "enriched_index.json",
    C.HAIKU / "palette_descriptions.yaml",
]

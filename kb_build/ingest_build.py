"""
§6.9 Build instructions — how to CONNECT operators (build-critical).

Two kinds of chunk:
  * build_instruction (converter) — for every "X to Y" converter operator, the
    connection mechanism as a FIELD (parameter_reference vs wire): converters are
    pull-not-push, so you set the source-family parameter rather than wiring.
  * build_instruction (rule) — a small set of canonical connection/layout rules
    (Feedback TOP needs a real wire; select-by-name; left→right ~150px layout).

Converters use the canonical operators.json name (resolves through the
name-integrity gate even when python_class is dirty/None for the newer POP
converters). Rule chunks assert no operator identity.
"""
from __future__ import annotations

import common as C

# canonical, non-operator build/layout rules
RULES = [
    ("feedback_needs_wire",
     "BUILD RULE — Feedback TOP loop: the Feedback TOP needs a real WIRE from the end of the loop "
     "into its input, in addition to (or instead of) its .top parameter. A .top reference alone does "
     "not iterate. Keep the whole loop at rgba16float. connection_type: wire."),
    ("converter_pull_not_push",
     "BUILD RULE — Family converters (CHOP to TOP, DAT to CHOP, …) are pull-not-push: they read the "
     "source by a parameter set to the source operator's NAME, not by a wire. connection_type: "
     "parameter_reference."),
    ("select_by_name",
     "BUILD RULE — Reference an operator elsewhere by NAME (Select TOP/CHOP/DAT/SOP) instead of "
     "wiring across the network: set the Select operator's source parameter to the target's path. "
     "connection_type: parameter_reference."),
    ("node_layout",
     "BUILD RULE — Network layout: data flows LEFT to RIGHT; place each downstream op ~150px to the "
     "right of its input (nodeX += 150) and ancillary/control ops (Info/callback DATs) ~150px BELOW "
     "the op they serve. Keep one operator per logical step; don't stack ops at (0,0)."),
]


def build(idn: C.Identity) -> list[dict]:
    rows: list[dict] = []

    # --- converters ---
    for o in idn.operators:
        name = o.get("name") or ""
        if " to " not in name:
            continue
        family = o.get("family")
        pyc = o.get("python_class")
        src_fam = name.split(" to ")[0].strip().split()[0]   # "CHOP to TOP" -> CHOP
        src_param = src_fam.lower()
        ident = idn.identity_meta(o)
        meta = dict(ident)
        meta["connection_type"] = "parameter_reference"
        text = (f"Build {name} ({family}). Converts {src_fam} to {family}."
                f"Connection: set the '{src_param}' parameter to the source {src_fam} operator's name "
                f"(parameter_reference — pull-not-push; a wire alone won't work). "
                f"e.g. {src_param}='source1'."
                + (f" [class:{pyc}]" if pyc else ""))
        rows.append(C.make_row(f"build:{C.slug(name)}", text, "build_instruction",
                               C.STORE_BUILD, meta))

    # --- canonical rules ---
    for rid, text in RULES:
        rows.append(C.make_row(f"build:rule:{rid}", text, "build_instruction",
                               C.STORE_BUILD, {"name": rid, "license_tier": "public"}))
    return rows


INPUTS = [C.SHIPPED_KB / "operators.json", C.SHIPPED_KB / "docked_dats.json"]

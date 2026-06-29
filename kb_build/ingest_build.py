"""
§6.9 Build instructions — how to CONNECT + place operators (build-critical).

Chunk types:
  * build_instruction (converter)  — every "X to Y" converter: connection_type as a
    FIELD (parameter_reference, pull-not-push).
  * build_instruction (wire-edge)  — per connection-relevant operator: how to wire its
    input(s) + place it, with special notes for multi-input / loop / pull ops. Covers
    the operators a builder actually wires (compositing, switch/merge, feedback,
    geometry/render, select-by-name, table sources, …).
  * build_instruction (rule)       — canonical connection/layout rules.
  * docked_dat                     — per docked-DAT spec from docked_dats.json: the
    auto-created helper DAT (callbacks/table) on a host op, with suffix/role/host_param/
    language (the offline builder reads these; the live build auto-creates them).

Converters + wire-edge chunks use the canonical operators.json name (resolves through
the name-integrity gate); rule + docked_dat chunks assert no operator identity.
"""
from __future__ import annotations

import json

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

# Operator-specific wiring notes (also guarantee the eval tokens: Feedback/Composite/Table-rows/cols).
SPECIAL = {
    "Feedback TOP": ("wire", "Wire a real WIRE from the end of the loop into input 1 — the .top parameter "
                     "alone will NOT iterate. Keep the loop rgba16float."),
    "Composite TOP": ("wire", "Wire two or more TOPs into its multi-input; the operand menu "
                      "(over/add/multiply/screen) selects the blend mode — 'over' is a STRING default."),
    "Table DAT": ("none", "A source DAT — wire nothing. Set the number of rows and cols on the parameters "
                  "(or fill it from a script / DAT In)."),
    "Switch TOP": ("wire", "Wire all candidate inputs; the index parameter selects which one passes."),
    "Switch CHOP": ("wire", "Wire all candidate inputs; the index parameter selects the active one."),
    "Geometry COMP": ("parameter_reference", "Set instanceop to a CHOP/SOP/DAT to instance; assign a "
                      "Material (MAT); render it with a Render TOP + Camera COMP + Light COMP."),
    "Render TOP": ("parameter_reference", "Set the camera, geometry and lights parameters to the COMPs "
                   "(parameter_reference — it pulls, no wire)."),
    "Select TOP": ("parameter_reference", "Set the 'top' parameter to the source operator's name instead of "
                   "wiring across the network."),
}


def _wire_edge(idn: C.Identity):
    rows = []
    KEYWORDS = ("composite", "multiply", "add", "subtract", "over", "under", "inside", "outside",
                "difference", "cross", "switch", "merge", "join", "blend", "layout", "stitch",
                "sequence", "mix", "feedback", "geometry", "render", "camera", "light", "select",
                "replace", "lookup", "reorder", "remap", "math", "logic", "compare", "constraint",
                "matte", "depth", "key ", "channel", "trail")
    for o in idn.operators:
        name = o.get("name") or ""
        if " to " in name:
            continue  # converters handled separately
        low = name.lower()
        if name not in SPECIAL and not any(k in low for k in KEYWORDS):
            continue
        family = o.get("family")
        pyc = o.get("python_class")
        # NB: no layout boilerplate here — only the node_layout RULE carries layout
        # guidance, so 100+ wire-edge chunks don't drown it on "lay out ... left to right" queries.
        ct, note = SPECIAL.get(name, ("wire", f"Wire the upstream {family} input(s) into {name}."))
        ident = idn.identity_meta(o)
        meta = dict(ident)
        meta["connection_type"] = ct
        text = (f"Build/wire {name} ({family} operator). {note} "
                f"connection_type: {ct}." + (f" [class:{pyc}]" if pyc else ""))
        rows.append(C.make_row(f"build:wire:{C.slug(pyc or name)}", text, "build_instruction",
                               C.STORE_BUILD, meta))
    return rows


def _docked(idn: C.Identity):
    rows = []
    dd = json.loads((C.SHIPPED_KB / "docked_dats.json").read_text(encoding="utf-8"))
    for key, specs in dd.items():
        fam = key.split(":", 1)[0] if ":" in key else ""
        stem = key.split(":", 1)[1] if ":" in key else key
        for spec in (specs if isinstance(specs, list) else [specs]):
            role = spec.get("role", "")
            dat = spec.get("dat", "text")
            suffix = spec.get("suffix", "")
            host_param = spec.get("host_param", "")
            lang = spec.get("language") or "n/a"
            ext = spec.get("file_ext", "")
            text = (f"Docked DAT — {fam} '{stem}' host: an auto-created {role} {dat} DAT (name suffix "
                    f"'{suffix}') docked on host parameter '{host_param}', language {lang}"
                    + (f", file .{ext}" if ext else "")
                    + ". TD creates it automatically when the host op is placed; the offline builder "
                    "must add it explicitly.")
            rows.append(C.make_row(
                f"docked:{C.slug(key)}:{C.slug(suffix or role)}", text, "docked_dat", C.STORE_BUILD,
                {"name": stem, "family": fam, "role": role, "host_param": host_param,
                 "dat_language": lang, "license_tier": "public"}))
    return rows


def build(idn: C.Identity) -> list[dict]:
    rows: list[dict] = []

    # --- converters ---
    for o in idn.operators:
        name = o.get("name") or ""
        if " to " not in name:
            continue
        family = o.get("family")
        pyc = o.get("python_class")
        src_fam = name.split(" to ")[0].strip().split()[0]
        src_param = src_fam.lower()
        meta = dict(idn.identity_meta(o))
        meta["connection_type"] = "parameter_reference"
        # Lead with the natural "wire/connect a X into a Y" phrasing so this beats the
        # converter's own operator_overview for "how do I wire a CHOP into a TOP" queries.
        text = (f"Wire/connect a {src_fam} into a {family} — use the {name} operator. "
                f"Set its '{src_param}' parameter to the source {src_fam} operator's name "
                f"(parameter_reference, pull-not-push; a wire alone won't work). e.g. {src_param}='source1'."
                + (f" [class:{pyc}]" if pyc else ""))
        rows.append(C.make_row(f"build:{C.slug(name)}", text, "build_instruction", C.STORE_BUILD, meta))

    # --- rules ---
    for rid, text in RULES:
        rows.append(C.make_row(f"build:rule:{rid}", text, "build_instruction", C.STORE_BUILD,
                               {"name": rid, "license_tier": "public"}))

    rows.extend(_wire_edge(idn))
    rows.extend(_docked(idn))
    return rows


INPUTS = [C.SHIPPED_KB / "operators.json", C.SHIPPED_KB / "docked_dats.json"]

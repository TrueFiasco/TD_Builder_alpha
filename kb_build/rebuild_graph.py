"""
§6.11 / deferral #1 — knowledge-graph rebuild (transform, not from scratch).

The enhanced gpickle the graph MCP tools consume (find_operator_combination,
get_network_patterns, find_similar_patterns) has two measured defects
(tool_coverage baseline): find_operator_combination resolves only 4/8 intents and
get_network_patterns signatures are 100% readMe-polluted. Both are node-content
problems, so we transform the shipped graph in place rather than re-derive 37k
nodes:

  1. HELPER FILTER — drop readMe/annotate/info helper ops from ExampleNetwork
     operators and from NetworkPattern signatures (the DAT:text / COMP:annotate
     nodes that pollute every signature).
  2. OPTYPE NORMALIZATION — rewrite the TD short .n token base to the canonical
     OPType base on example + pattern operator tokens, so a natural canonical
     query (COMP:geometry, COMP:camera, TOP:composite) resolves. The tool matches
     req_type as a SUBSTRING of the example type, so the example must carry the
     long canonical form.
  3. CANONICAL IDENTITY — enrich Operator nodes with the spaced canonical name +
     python_class + .n token, joined from operators.json.

Reads the shipped gpickle, writes the rebuilt one to Output/KB. Never commits a KB.
"""
from __future__ import annotations

import json
import pickle
import re
from collections import Counter

import common as C

# TD short .n-token base -> canonical OPType base. The 3 that break the measured
# intents (geo/cam/comp) plus well-known TD abbreviations; each canonical target is
# verified to exist in operators.json before it is applied (see build()).
ABBREV = {
    ("COMP", "geo"): "geometry",
    ("COMP", "cam"): "camera",
    ("TOP", "comp"): "composite",
    ("TOP", "chanmix"): "channelmix",
    ("TOP", "hsvrgb"): "hsvtorgb",
    ("TOP", "rgbhsv"): "rgbtohsv",
    ("TOP", "tex3d"): "texture3d",
    ("DAT", "datexec"): "datexecute",
    ("DAT", "parexec"): "parameterexecute",
    ("COMP", "geotext"): "geometry",
}

# An op is a non-structural helper if its name or type marks it as documentation.
_HELPER_NAME = re.compile(r"(readme|annotate|comment)", re.I)
_HELPER_TYPES = {"COMP:annotate"}


def _is_helper(op: dict) -> bool:
    name = str(op.get("name") or "")
    ty = str(op.get("type") or "")
    if ty in _HELPER_TYPES:
        return True
    if ty == "DAT:text" and _HELPER_NAME.search(name):
        return True
    return bool(_HELPER_NAME.search(name))


def _norm_type(ty: str) -> str:
    """Apply the abbreviation map to a 'FAMILY:base' token."""
    if not ty or ":" not in ty:
        return ty
    fam, b = ty.split(":", 1)
    repl = ABBREV.get((fam.upper(), b.lower()))
    return f"{fam}:{repl}" if repl else ty


def _polluted(sig: str) -> bool:
    s = (sig or "").lower()
    return "dat:text" in s or "readme" in s


def build(idn: C.Identity) -> dict:
    src = C.SHIPPED_KB / "knowledge_graph_enhanced.gpickle"
    g = pickle.loads(src.read_bytes())
    nodes, edges = g["nodes"], g["edges"]

    # verify abbreviation targets exist in operators.json (family base set)
    fam_bases = {}
    for o in idn.operators:
        fam = o.get("family")
        if not fam:
            continue
        nb = re.sub(r"[^a-z0-9]", "", (o.get("name") or "").lower()).replace(fam.lower(), "")
        nt = idn.n_token(o) or ""
        fam_bases.setdefault(fam, set()).add(nb)
        if nt:
            fam_bases[fam].add(re.sub(r"[^a-z0-9]", "", nt.lower()).replace(fam.lower(), ""))
    applied = {k: v for k, v in ABBREV.items() if v in fam_bases.get(k[0], set())}
    dropped_abbrev = {k: v for k, v in ABBREV.items() if k not in applied}

    stats = Counter()

    # --- ExampleNetwork: filter helpers + normalize op tokens ---
    for n in nodes.values():
        if n.get("type") != "ExampleNetwork":
            continue
        ops = n.get("operators", []) or []
        kept = []
        for op in ops:
            if _is_helper(op):
                stats["ex_helpers_dropped"] += 1
                continue
            new_ty = _norm_type(op.get("type", ""))
            if new_ty != op.get("type"):
                stats["ex_types_normalized"] += 1
                op["type"] = new_ty
            kept.append(op)
        n["operators"] = kept

    # --- NetworkPattern: drop helper tokens + normalize + recompute signature ---
    kept_patterns = {}
    for nid, n in list(nodes.items()):
        if n.get("type") != "NetworkPattern":
            continue
        try:
            toks = json.loads((n.get("operator_types") or "[]").replace("'", '"'))
        except Exception:
            toks = [t.strip() for t in (n.get("pattern_signature") or "").split("+")]
        clean = []
        for t in toks:
            t = t.strip()
            if not t or t == "DAT:text" or t in _HELPER_TYPES or _HELPER_NAME.search(t):
                continue
            clean.append(_norm_type(t))
        clean = sorted(set(clean))
        if len(clean) < 2:                      # nothing meaningful left → drop the pattern
            del nodes[nid]
            stats["patterns_dropped"] += 1
            continue
        n["operator_types"] = json.dumps(clean)
        n["pattern_signature"] = " + ".join(clean)
        kept_patterns[nid] = n
    stats["patterns_kept"] = len(kept_patterns)
    stats["patterns_polluted_after"] = sum(1 for n in kept_patterns.values()
                                           if _polluted(n.get("pattern_signature", "")))

    # --- Operator nodes: canonical identity from operators.json ---
    by_fam_base = {}
    for o in idn.operators:
        fam = o.get("family")
        if not fam:
            continue
        nb = re.sub(r"[^a-z0-9]", "", (o.get("name") or "").lower())
        by_fam_base[(fam, nb)] = o
    for n in nodes.values():
        if n.get("type") != "Operator":
            continue
        fam = n.get("family")
        nm = re.sub(r"[^a-z0-9]", "", str(n.get("name") or "").lower())
        rec = by_fam_base.get((fam, nm))
        if rec:
            n["canonical_name"] = rec.get("name")
            n["python_class"] = rec.get("python_class")
            n["n_token"] = idn.n_token(rec)
            n["optype"] = (rec.get("python_class") or "").replace("_Class", "")
            stats["operators_identity_enriched"] += 1

    out = C.OUT / "knowledge_graph_enhanced.gpickle"
    out.write_bytes(pickle.dumps(g, protocol=pickle.HIGHEST_PROTOCOL))

    return {"out": str(out), "nodes": len(nodes), "edges": len(edges),
            "abbrev_applied": {f"{k[0]}:{k[1]}": v for k, v in applied.items()},
            "abbrev_skipped": {f"{k[0]}:{k[1]}": v for k, v in dropped_abbrev.items()},
            "stats": dict(stats)}


if __name__ == "__main__":
    idn = C.Identity()
    res = build(idn)
    print(json.dumps(res, indent=2))
    # standalone rebuild replaced the gpickle in the staged KB -> re-receipt it
    # (inside build_kb the final kb_build receipt covers this instead)
    C.write_kb_receipt(C.OUT, "rebuild_graph")

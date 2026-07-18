#!/usr/bin/env python3
r"""
Curated GOLD queries for Derivative's official "Sweet 16" operators.

The TD docs publish a "Sweet 16 <FAM>s" list — the 16 must-learn operators — for
CHOP, TOP, and SOP only (DAT/COMP/MAT/POP have no official Sweet 16). This reads
those wiki tables from the local OfflineHelp, and for each of the 48 operators
emits one operator_lookup gold query, grounded in the operator's wiki summary
(name/family/python_class stripped), falling back to the official one-line
Purpose when the summary is too thin/ambiguous. Reuses gen_coverage's gates
(resolve / no-leak / uniqueness) + a static KB-match check. Offline, deterministic.

Output: eval/sweet16_queries.jsonl ({id,query,category,relevant_predicate,notes,gen}),
same schema run_eval/predicates score — category 'operator_lookup', gen.tier 'sweet16'.
"""
from __future__ import annotations
import argparse, io, json, re, sys
from pathlib import Path
from collections import defaultdict

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))
from predicates import GroundTruth, _norm  # noqa: E402
import gen_coverage as G  # reuse the gates  # noqa: E402
import run_eval  # noqa: E402  # resolve_gt_paths (tracked-GT-first since W3)

WIKI = Path(r"C:\TD_Builder_Alpha_Build_V0.1.2\New KB build\Resources\Learn\OfflineHelp\https.docs.derivative.ca")
KB = G.resolve_kb_root(None)
RES = G.resolve_resources(None, KB)
# Families with an OFFICIAL wiki "Sweet 16 / Sweet Sixteen" table (col1 op, col2 purpose):
SWEET_FAMS = ["CHOP", "TOP", "SOP", "DAT"]
# Families with NO official Sweet list — user-specified curated short-lists (no purpose table):
EXPLICIT = {
    "MAT": ["PBR MAT", "Phong MAT", "Constant MAT", "Line MAT", "GLSL MAT"],  # "sweet 5"
    "COMP": ["Geometry COMP", "Camera COMP", "Null COMP", "Light COMP", "Base COMP",
             "Bullet Solver COMP", "Container COMP"],                          # "sweet 7"
}

_OL = ["operator that {c}", "which operator {c}", "find an operator that {c}", "is there an operator that {c}"]

# Hand-curated queries for Sweet-16 ops the auto-builder can't phrase without leaking the
# name/family (multi-word-core component words, or converters). Verified: no full-name/family
# token, unique to the op. (The Sweet-16 list is itself curated, so these belong.)
MANUAL = {
    "Movie File In TOP": "operator that plays back recorded video clips and still image sequences loaded from disk",
    "CHOP to SOP": "operator that builds geometry points whose positions come from sampled channel data",
    "CHOP to TOP": "operator that turns numeric channel values into a raster image, one pixel per sample",
    # auto-strip mangled these summaries into broken grammar -> hand-authored (gold op unchanged):
    "Audio Device In CHOP": "operator that captures live audio from a microphone or sound card into channels",
    "SOP to CHOP": "operator that reads a geometry object's point positions and attributes out as channels",
    "Select TOP": "operator that fetches an image from any other operator anywhere in the project",
    "Transform SOP": "operator that translates, rotates and scales 3D input geometry in object space",
    "Timer CHOP": "operator that runs countdown timers and drives timed, sequenced events",
    "Reorder TOP": "operator that remaps which input channels feed the red, green, blue and alpha outputs",
    # generic COMP/MAT whose summaries are too thin/plumbing for an auto capability query:
    "Base COMP": "operator that is an empty component you nest a custom sub-network of operators inside",
    "Null COMP": "operator that passes a component through unchanged, a tidy reference and connection point",
    "Constant MAT": "material that shades a surface with a single flat uniform color, ignoring scene lighting",
    "Line MAT": "material that draws edges, lines and vectors with adjustable width and color",
    "Geometry COMP": "operator that holds 3D geometry and renders it as an object in a scene, with instancing",
    "Container COMP": "operator that holds a 2D panel layout for building user interfaces",
    "Camera COMP": "operator that defines the viewpoint, lens and projection used to render a 3D scene",
    "Light COMP": "operator that defines a point, cone or distant light source illuminating a 3D scene",
    "Bullet Solver COMP": "operator that runs a rigid-body physics simulation where objects collide and respond to forces and gravity",
}


def parse_sweet16(fam):
    """Return [(op_fullname, purpose)] from the family wiki's Sweet 16/Sixteen table (col1 op, col2 purpose)."""
    html = (WIKI / f"{fam}.htm").read_text(encoding="utf-8", errors="replace")
    m = (re.search(rf'id="Sweet_(?:16|Sixteen)_{fam}s"', html)
         or re.search(r'id="Sweet_(?:16|Sixteen)_[^"]*"', html))
    rest = html[m.end():]
    nxt = re.search(r"<h2", rest)
    seg = rest[: nxt.start()] if nxt else rest
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", seg, re.S):
        tds = re.findall(r"<td>(.*?)</td>", row, re.S)
        if not tds:
            continue
        a = re.search(r'title="([^"]+)"', tds[0])     # col1 first link title = full op name
        if not a:
            continue
        op = a.group(1).strip()
        purpose = re.sub(r"<[^>]+>", " ", tds[1]) if len(tds) > 1 else ""
        purpose = re.sub(r"\s+", " ", purpose).strip().rstrip(".")
        if op.endswith(fam):
            out.append((op, purpose))
    return out


def build_op_tokens(ops):
    """capability token sets per operator (own name stripped) — for the uniqueness check."""
    tok = {}
    for o in ops:
        strip, _ = G.op_identity(o)
        cap = G.strip_phrases(G.first_sentence(G.strip_leading_boilerplate(o.get("summary") or "")), strip)
        tok[o["name"]] = G.content_tokens(cap)
    return tok


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    # W3 Census Lock: default to the TRACKED ground truth. This was the only
    # GroundTruth instantiation with no override at all, and it pointed at the
    # untracked corpus twin -- so it silently graded against a different file
    # than CI. --gt-types exists so a corpus copy can still be compared on demand.
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--gt-types", default=None,
                    help="operator_types.json (default: tracked eval/ground_truth)")
    args = ap.parse_args()
    gt_types = (Path(args.gt_types) if args.gt_types
                else run_eval.resolve_gt_paths(None, None, KB)[1])
    gt = GroundTruth(operators_json=KB / "operators.json",
                     operator_types_json=gt_types)
    ops = json.loads((KB / "operators.json").read_text(encoding="utf-8"))["operators"]
    by_name = {o["name"]: o for o in ops}
    safe_pyc = G.safe_python_classes(ops)
    op_tokens = build_op_tokens(ops)
    fam_members = defaultdict(set)
    for o in ops:
        if o.get("family") in G.FAMILIES:
            fam_members[o["family"]].add(o["name"])

    rows, report = [], []
    fam_order = SWEET_FAMS + list(EXPLICIT)
    for fam in fam_order:
        sweet = parse_sweet16(fam) if fam in SWEET_FAMS else [(op, "") for op in EXPLICIT[fam]]
        n = 0
        for op_name, purpose in sweet:
            o = by_name.get(op_name)
            if not o:
                report.append((fam, op_name, "NOT_IN_KB")); continue
            pyc = o.get("python_class") or ""
            strip, hard = G.op_identity(o)
            full_only = {o.get("name"), (o.get("name") or "").replace(" ", ""), pyc}  # full-name leak only (for manual)
            if op_name in MANUAL:
                query = MANUAL[op_name]
                if G.has_leak(query, full_only):
                    report.append((fam, op_name, "manual_leak")); continue
                amb, src = "disambiguated", "manual_curated"
            else:
                # primary: wiki summary first sentence (name/family stripped); fallback: official Purpose
                cap = G.cap_len(G.lead_case(G.strip_phrases(
                    G.first_sentence(G.strip_leading_boilerplate(o.get("summary") or "")), strip)))
                src = "summary"
                qt = G.content_tokens(cap)
                uniq, _, g, r, _ = G._dominates(qt, op_name, op_tokens)
                amb = "unique"
                if G._good_capability(cap) and not G.has_leak(cap, hard) and (uniq or G._dominates(
                        qt, op_name, op_tokens, restrict=fam_members[fam])[0]):
                    if not uniq:
                        amb = "disambiguated"
                    base = cap
                else:
                    p = G.lead_case(G.strip_phrases(G.clean_text(purpose), strip))   # official Purpose fallback
                    src, base, amb = "official_purpose", p, "disambiguated"
                    if not base or G.has_leak(base, hard):
                        report.append((fam, op_name, "leak_or_empty_purpose")); continue
                query = _OL[n % len(_OL)].format(c=base)
                if amb == "disambiguated":
                    query = f"{query} (it is a {fam} operator)"
                if G.has_leak(query, hard):
                    report.append((fam, op_name, "leak")); continue
            # gold (resolve check)
            if not (gt.pyclass_ok(pyc) or gt.name_ok(op_name)):
                report.append((fam, op_name, "unresolved")); continue
            clauses = []
            if pyc in safe_pyc:
                clauses.append({"python_class_any": [pyc]})
            clauses.append({"op_name_any": [op_name]})
            n += 1
            rows.append({
                "id": f"sw-{fam.lower()}-{n:02d}", "query": query, "category": "operator_lookup",
                "relevant_predicate": {"clauses": clauses},
                "notes": f"Derivative Sweet-16 {fam}; official purpose: {purpose!r}; query from {src}",
                "gen": {"family": fam, "op": op_name, "kind": "operator", "chunk_type": "operator_overview",
                        "ambiguity": amb, "tier": "sweet16", "source": f"wiki Sweet_16_{fam}s",
                        "official_purpose": purpose},
            })
        report.append((fam, f"emitted {n}/{len(sweet)}", ""))

    out = EVAL_DIR / "sweet16_queries.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    # ---- static KB-match + leak audit (independent) ----
    import chromadb
    from predicates import is_relevant
    if not (KB / "vector_db" / "chroma.sqlite3").exists():
        # KF1: PersistentClient is create-if-missing — refuse, never create
        raise FileNotFoundError(f"no vector_db at {KB / 'vector_db'} — fetch the KB first")
    col = chromadb.PersistentClient(path=str(KB / "vector_db")).get_collection("td_unified")
    g = col.get(include=["metadatas", "documents"], limit=col.count())
    chunks = [{"metadata": m, "content": d} for m, d in zip(g["metadatas"], g["documents"])]
    matched = sum(1 for r in rows if any(is_relevant(c, r["relevant_predicate"]) for c in chunks))
    leaks = G._count_answer_leaks(rows)

    print("=" * 64)
    print(f"Curated 'sweet' gold queries -> {len(rows)} "
          f"(CHOP/TOP/SOP/DAT = official wiki Sweet-16; MAT=5 + COMP=7 = user-curated)")
    print("=" * 64)
    for fam, a, b in report:
        if isinstance(a, str) and a.startswith("emitted"):
            print(f"  {fam}: {a}")
    drops = [(f, op, why) for f, op, why in report if why]
    if drops:
        print("  drops/issues:", drops)
    by_fam = defaultdict(int)
    for r in rows:
        by_fam[r["gen"]["family"]] += 1
    print("  per family:", dict(by_fam))
    amb = defaultdict(int)
    for r in rows:
        amb[r["gen"]["ambiguity"]] += 1
    print("  ambiguity:", dict(amb), "| query source:",
          {s: sum(1 for r in rows if f"from {s}" in r['notes']) for s in ("summary", "official_purpose")})
    print(f"  KB-matchable: {matched}/{len(rows)} | answer-leaks: {leaks}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()

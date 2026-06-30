#!/usr/bin/env python3
r"""
PHASE 1 — re-ground operators.json from the live-TD capture (the SOURCE fix).

Produces a corrected operators.json staged to Output/build_gate/operators.regrounded.json
(never committed; handed to the KB-rebuild session for release) + REGROUND_DIFF.md.

Corrections (LIVE TD = authority, via operator_ground_truth):
  (a) build_token  -- add the real live `.n` token to every op (CanonicalMap.n_token);
                      Art-Net DAT's GT token is the bad hyphenated 'DAT:art-net' -> 'DAT:artnet'
                      (verified live: create token artnetDAT -> DAT:artnet).
  (b) param codes  -- correct wiki codes live TD doesn't use: any KB code absent from the
                      captured live codes whose 'common'-stripped form IS a live code
                      (commonrenamefrom -> renamefrom, ...). Tag source 'ground_truth_regrounded'.
  (c) hygiene      -- drop wiki guide PAGES that aren't operators (Write a *, Anatomy of *);
                      de-duplicate identical duplicate display-names.

Usage: py -3.11 eval/build_gate/reground_operators.py
"""
from __future__ import annotations
import json, sys
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parent))
import gate_common as gc  # noqa: E402

TOKEN_OVERRIDES = {"Art-Net DAT": "DAT:artnet"}   # GT captured the hyphen; live create = artnetDAT


def is_wiki_page(name: str) -> bool:
    n = name.lower()
    return n.startswith("write a ") or n.startswith("anatomy of")


def main():
    src = json.loads(gc.kb_operators_json().read_text(encoding="utf-8"))
    ops = src.get("operators", [])
    cmap = gc.CanonicalMap.load().operators
    pdefs = gc.get_param_defaults()

    diffs = {"build_token_added": [], "param_code_fixed": [], "wiki_pages_dropped": [],
             "duplicates_dropped": [], "token_override": [], "no_build_token": []}
    out_ops = []
    seen = {}   # (family, name) -> index in out_ops

    for o in ops:
        name = o.get("name")
        fam = o.get("family")
        if not name or not fam:
            out_ops.append(o)
            continue

        # (c) drop wiki guide pages
        if is_wiki_page(name):
            diffs["wiki_pages_dropped"].append(name)
            continue
        # (c) de-dup identical display-names (keep first; drop exact dup)
        key = (fam, name)
        if key in seen:
            diffs["duplicates_dropped"].append(name)
            continue
        seen[key] = len(out_ops)

        rec = cmap.get(name)
        # (a) build_token
        bt = TOKEN_OVERRIDES.get(name) or (rec["n_token"] if rec else None)
        if bt:
            o["build_token"] = bt
            if name in TOKEN_OVERRIDES:
                diffs["token_override"].append({"op": name, "to": bt})
            else:
                diffs["build_token_added"].append({"op": name, "build_token": bt})
        else:
            diffs["no_build_token"].append(name)

        # (b) param-code re-grounding vs captured live codes
        gt_name = rec["gt_name"] if rec else name.replace(" ", "_")
        captured = pdefs._params(fam, name)   # {code: spec} or None
        if captured:
            capcodes = set(captured.keys())
            for p in o.get("parameters", []):
                code = p.get("code", "")
                if code and code not in capcodes:
                    if code.startswith("common") and code[len("common"):] in capcodes:
                        fixed = code[len("common"):]
                        diffs["param_code_fixed"].append({"op": name, "from": code, "to": fixed})
                        p["code"] = fixed
                        p["source"] = "ground_truth_regrounded"
        out_ops.append(o)

    # write regrounded operators.json (preserve metadata + add a regroundnote)
    src["operators"] = out_ops
    md = src.setdefault("metadata", {})
    md["regrounded"] = {
        "by": "eval/build_gate/reground_operators.py",
        "build_tokens_added": len(diffs["build_token_added"]) + len(diffs["token_override"]),
        "param_codes_fixed": len(diffs["param_code_fixed"]),
        "wiki_pages_dropped": len(diffs["wiki_pages_dropped"]),
        "duplicates_dropped": len(diffs["duplicates_dropped"]),
        "operators_out": len(out_ops),
    }
    stage = gc.stage_dir()
    (stage / "operators.regrounded.json").write_text(json.dumps(src, indent=2), encoding="utf-8")

    # diff report
    lines = ["# REGROUND_DIFF — operators.json corrections (source fix)", "",
             f"- operators in: {len(ops)}  -> out: {len(out_ops)}",
             f"- build_token added: {len(diffs['build_token_added'])} (+{len(diffs['token_override'])} override)",
             f"- param codes fixed: {len(diffs['param_code_fixed'])}",
             f"- wiki pages dropped: {len(diffs['wiki_pages_dropped'])} -> {diffs['wiki_pages_dropped']}",
             f"- duplicate names dropped: {len(diffs['duplicates_dropped'])} -> {diffs['duplicates_dropped']}",
             f"- token overrides: {diffs['token_override']}",
             f"- ops with NO build_token (no live capture, e.g. hardware): {len(diffs['no_build_token'])}",
             "", "## Param-code corrections (common-prefix -> live code)", ""]
    # group param fixes by the (from->to) pair
    pair_counts = {}
    for d in diffs["param_code_fixed"]:
        k = f"{d['from']} -> {d['to']}"
        pair_counts[k] = pair_counts.get(k, 0) + 1
    for k, c in sorted(pair_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{k}` — {c} ops")
    lines += ["", "## build_token additions (sample, first 30)", ""]
    for d in diffs["build_token_added"][:30]:
        lines.append(f"- {d['op']}: `{d['build_token']}`")
    (stage / "REGROUND_DIFF.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("REGROUND complete:")
    print(f"  operators {len(ops)} -> {len(out_ops)}")
    print(f"  build_token added : {len(diffs['build_token_added'])} (+{len(diffs['token_override'])} override)")
    print(f"  param codes fixed : {len(diffs['param_code_fixed'])}  ({dict(list(pair_counts.items())[:6])})")
    print(f"  wiki pages dropped: {diffs['wiki_pages_dropped']}")
    print(f"  duplicates dropped: {diffs['duplicates_dropped']}")
    print(f"  no build_token    : {len(diffs['no_build_token'])}")
    print(f"  wrote: {stage / 'operators.regrounded.json'}")
    print(f"         {stage / 'REGROUND_DIFF.md'}")


if __name__ == "__main__":
    main()

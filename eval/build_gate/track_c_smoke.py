#!/usr/bin/env python3
r"""
TRACK C -- tool-integration smoke test (the search->build HANDOFF).

Drives the full chain a human brief flows through, IN-PROCESS, faithful to the live
MCP tools:
    hybrid_search  (UnifiedSearchAdapter -- the shipped semantic search)
 -> get_operator_info / get_parameter_detail  (UnifiedGraphQuery -- the KB hydration)
 -> td_build_project (ToxBuilder)  -> real toeexpand  -> td_validate (ValidationPipeline)

The point is the HANDOFF, not per-tool liveness: does the operator the SEARCH side
surfaces (by canonical name, integrity-clean) actually BUILD to the correct live `.n`
token and validate? That is exactly where KB<->builder integration breaks.

Usage: py -3.11 eval/build_gate/track_c_smoke.py
"""

from __future__ import annotations

import contextlib
import json
import shutil
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parent))
import gate_common as gc          # noqa: E402
import run_eval                   # noqa: E402  (offline env + search adapter)
import track_a_offline as ta      # noqa: E402  (build_and_expand + td_validate)
from tool_coverage import build_graph, tool_get_parameter_detail, _wiki_params  # noqa: E402

# 5 realistic briefs: the natural-language goal, the operator a builder must land on
# (canonical name + family), and a headline parameter to hydrate.
BRIEFS = [
    {"id": "opacity", "query": "fade an image in and out by controlling its opacity / brightness",
     "op": "Level TOP", "family": "TOP", "param": "opacity"},
    {"id": "audio-analyze", "query": "get the amplitude envelope of an audio file for audio-reactive visuals",
     "op": "Analyze CHOP", "family": "CHOP", "param": "function"},
    {"id": "instance-geo", "query": "instance copies of geometry across a grid of points in 3D",
     "op": "Geometry COMP", "family": "COMP", "param": "instanceop"},
    {"id": "feedback-trails", "query": "feedback trails that slowly fade over time",
     "op": "Feedback TOP", "family": "TOP", "param": "blend"},
    {"id": "pop-pointgen", "query": "generate a cloud of points procedurally with POPs",
     "op": "Point Generator POP", "family": "POP", "param": "numpoints"},
]


def main():
    cmap = gc.CanonicalMap.load()
    gt = gc.get_ground_truth()
    kb_root = run_eval.resolve_kb_root(None).resolve()
    toeexpand = gc._bridge() and __import__("paths").resolve_td_tool("toeexpand")

    print("loading search adapter + graph (chromadb + graphrag)...", file=sys.stderr)
    adapter = run_eval.build_adapter(use_legacy=False,
                                     vectordb_path=kb_root / "vector_db",
                                     graph_path=kb_root / "knowledge_graph_enhanced.gpickle")
    kg = build_graph(kb_root)

    work = gc.stage_dir() / "_work_c"
    work.mkdir(parents=True, exist_ok=True)
    results = []
    for b in BRIEFS:
        r = {"id": b["id"], "query": b["query"], "intended_op": b["op"], "family": b["family"]}
        rec = cmap.operators.get(b["op"], {})

        # 1) SEARCH: does the top-k surface the intended op (integrity-clean)?
        hits = run_eval.search(adapter, b["query"], 8)
        surfaced, surfaced_clean = False, False
        for h in hits:
            chk = __import__("predicates").check_name_integrity(h, gt)
            m = h.get("metadata", {}) if isinstance(h, dict) else {}
            nm = m.get("name") or m.get("operator") or m.get("operator_name")
            if nm and gc._norm(nm) == gc._norm(b["op"]):
                surfaced = True
                surfaced_clean = (chk or {}).get("status") != "retokenized"
                break
        r["search_resolves"] = surfaced
        r["search_name_clean"] = surfaced_clean

        # 2) INFO hydrate
        with contextlib.redirect_stdout(sys.stderr):
            info = kg.get_operator_info(b["op"])
        r["info_hydrates"] = bool(info) and len(list(_wiki_params(info))) > 0

        # 3) PARAM detail + GT default
        with contextlib.redirect_stdout(sys.stderr):
            det = tool_get_parameter_detail(info, b["param"])
        r["param_found"] = det is not None

        # 4) HANDOFF BUILD: build the intended op -> right .n token?  (the key criterion)
        type_in = rec.get("extracted_type", b["op"])
        design = {"operators": [{"name": "op0", "type": type_in, "family": b["family"], "parameters": {}}],
                  "connections": [], "project": "opnet"}
        out_dir = work / b["id"]
        shutil.rmtree(out_dir, ignore_errors=True)
        with contextlib.redirect_stdout(sys.stderr):
            be = ta.build_and_expand(design, out_dir, toeexpand)
        exp_tok = rec.get("n_token")
        r["built"] = be["built"]
        r["got_n_token"] = be["n_token"]
        r["expected_n_token"] = exp_tok
        r["handoff_builds"] = bool(exp_tok and be["n_token"] and be["n_token"].strip() == exp_tok.strip())

        # 5) VALIDATE
        with contextlib.redirect_stdout(sys.stderr):
            v = ta.td_validate_builder(design)
        r["validate_clean"] = v["pass"]
        shutil.rmtree(out_dir, ignore_errors=True)

        r["PASS"] = bool(r["search_resolves"] and r["handoff_builds"] and r["validate_clean"])
        results.append(r)
        print(f"[{b['id']:16s}] search={r['search_resolves']} build_token={r['handoff_builds']} "
              f"validate={r['validate_clean']} -> {'PASS' if r['PASS'] else 'FAIL'}", file=sys.stderr)

    payload = {"harness": "build_gate.track_c", "n_briefs": len(BRIEFS),
               "pass": sum(1 for r in results if r["PASS"]), "briefs": results}
    stage = gc.stage_dir()
    (stage / "track_c_smoke.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md = ["# TD Builder — Track C: tool-integration smoke (search→build handoff)", "",
          f"{payload['pass']}/{len(BRIEFS)} briefs pass the full chain "
          "(search surfaces the op → it builds to the correct live `.n` token → validate clean).", "",
          "| brief | intended op | search | name-clean | info | param | **build→right token** | validate | PASS |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        md.append(f"| {r['id']} | {r['intended_op']} | {r['search_resolves']} | {r['search_name_clean']} | "
                  f"{r['info_hydrates']} | {r['param_found']} | {r['handoff_builds']} "
                  f"({r['got_n_token']} vs {r['expected_n_token']}) | {r['validate_clean']} | "
                  f"{'PASS' if r['PASS'] else 'FAIL'} |")
    (stage / "TRACK_C.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nTrack C: {payload['pass']}/{len(BRIEFS)} pass -> {stage / 'track_c_smoke.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()

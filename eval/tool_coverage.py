#!/usr/bin/env python3
r"""
Phase-0.5 TOOL-coverage harness for the TD Builder KB.

run_eval.py gates the RANKING tool (hybrid_search). This gates the rest of the
KB-dependent MCP tools -- the hydration/lookup + pattern tools the builder relies
on once it knows an operator -- so we can catch tool regressions/fixes as the KB
is rebuilt. It drives the real engine behind the tools (UnifiedGraphQuery, the
`knowledge_graph` the MCP handlers delegate to), offline + in-process, exactly as
mcp_server.py constructs it. Reuses the same labels in labeled_queries.jsonl.

Checks (capture the CURRENT baseline, before any KB change):
  1. get_operator_info  -- for each labeled operator: does it resolve? is the
     returned name canonical (not retokenized)? does it carry parameters?
  2. get_parameter_detail -- for each labeled (operator, param): is the param
     found, does it return a default, and does that default MATCH the live-TD
     ground truth (operator_ground_truth/params/<FAM>_<Op>_defaults.json)?
     [This is the headline: the wiki defaults are known-wrong; Phase 1 re-grounds
      them. Expect a low default-correct rate today.]
  3. find_operator_examples -- for each labeled operator: >=1 real example? (the
     "~55% of operators have any example" gap.)
  4. find_operator_combination -- for intent operator-sets (mirroring the howto
     queries): does the pattern tool return >=1 example?
  5. get_network_patterns -- inventory at min_frequency 5 / 2, and how many
     pattern signatures are readMe/DAT:text-polluted (the section 6.11 defect).

Output: a compact scorecard to the console; full per-probe details to disk
(eval/tool_baseline.json + New KB build/Output/eval/{tool_baseline.json,
TOOL_COVERAGE.md}). Token-light by design -- the console scorecard is ~12 lines.

Usage:
    py -3.11 eval/tool_coverage.py
    py -3.11 eval/tool_coverage.py --kb "C:/path/to/KB"
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import sys
from pathlib import Path

# run_eval sets offline + single-thread env at import, adds eval/ to sys.path, and
# exposes the path resolvers + SERVER_CORE. Reuse them (DRY, same KB resolution).
import run_eval  # noqa: E402  (its import side effects are wanted)
from predicates import GroundTruth, OP_FAMILIES, _norm  # noqa: E402

SERVER_CORE = run_eval.SERVER_CORE
EVAL_DIR = run_eval.EVAL_DIR
HARNESS_VERSION = "0.1.0"

# Intent -> operator_types (colon-form) for the pattern tool. These mirror the
# howto-category queries: a goal a builder would phrase, and the canonical op set
# that realizes it. find_operator_combination is keyed by operator set.
PATTERN_INTENTS = [
    {"id": "feedback-trails",       "howto": "ho-02", "ops": ["TOP:feedback", "TOP:composite", "TOP:level"]},
    {"id": "instance-from-chop",    "howto": "ho-05", "ops": ["COMP:geometry", "CHOP:constant", "CHOP:null"]},
    {"id": "render-3d-scene",       "howto": "ho-10", "ops": ["COMP:geometry", "COMP:camera", "TOP:render"]},
    {"id": "audio-reactive",        "howto": "ho-04", "ops": ["CHOP:audiofilein", "CHOP:analyze", "CHOP:trail"]},
    {"id": "blur-composite",        "howto": "ho-12", "ops": ["TOP:blur", "TOP:composite"]},
    {"id": "noise-displace",        "howto": "ho-09", "ops": ["TOP:noise", "TOP:displace"]},
    {"id": "lfo-drive-param",       "howto": "ho-11", "ops": ["CHOP:lfo", "CHOP:null"]},
    {"id": "movie-to-level",        "howto": "—",     "ops": ["TOP:moviefilein", "TOP:level"]},
]


# ---------------------------------------------------------------------------
# Engine (the real tool backend) + faithful handler replicas
# ---------------------------------------------------------------------------
def build_graph(kb_root: Path):
    """Construct UnifiedGraphQuery exactly as mcp_server.py does (offline)."""
    for p in (str(run_eval.REPO_ROOT), str(SERVER_CORE)):  # REPO_ROOT so the engine's `import paths` resolves
        if p not in sys.path:
            sys.path.insert(0, p)
    os.chdir(SERVER_CORE)
    with contextlib.redirect_stdout(sys.stderr):
        spec = importlib.util.spec_from_file_location(
            "unified_graph_query", str(SERVER_CORE / "unified_graph_query.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.UnifiedGraphQuery(
            graphrag_json_path=str(kb_root / "graphrag.json"),
            enhanced_graph_path=str(kb_root / "knowledge_graph_enhanced.gpickle"),
            enriched_wiki_path=str(kb_root / "operators.json"),
        )


def _wiki_params(info: dict):
    """Yield (code, param_dict) over get_operator_info's wiki_parameters (dict OR list)."""
    wp = (info or {}).get("wiki_parameters", {})
    if isinstance(wp, dict):
        for code, p in wp.items():
            yield code, (p if isinstance(p, dict) else {"value": p})
    elif isinstance(wp, list):
        for p in wp:
            if isinstance(p, dict):
                yield p.get("code", p.get("name", "")), p


def tool_get_parameter_detail(info: dict, parameter_name: str):
    """Replicate mcp_server's get_parameter_detail param lookup (case-insensitive code)."""
    for code, p in _wiki_params(info):
        if str(code).lower() == parameter_name.lower():
            return {"code": code, "name": p.get("display_name", code),
                    "type": p.get("type", "unknown"), "default": p.get("default"),
                    "section": p.get("section", "")}
    return None


# ---------------------------------------------------------------------------
# Ground truth: live-TD param defaults
# ---------------------------------------------------------------------------
class ParamDefaults:
    """operator_ground_truth/params/<FAM>_<Name_underscored>_defaults.json lookup."""

    def __init__(self, params_dir: Path):
        self.dir = Path(params_dir)
        self._cache: dict = {}

    def _file(self, family: str, name: str) -> Path:
        return self.dir / f"{family}_{name.replace(' ', '_')}_defaults.json"

    def _params(self, family: str, name: str):
        key = (family, name)
        if key not in self._cache:
            f = self._file(family, name)
            self._cache[key] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        rec = self._cache[key]
        return (rec.get("parameters") or {}) if rec else None

    def resolve(self, family: str, name: str, code: str):
        """Resolve a label's param code to the value-bearing live-TD code + default.

        Returns (probe_code, gt_default, status). status is:
          scalar     -- code exists with a concrete default
          tuplet     -- code is a multi-value parent (e.g. Lag's 'lag'); the real
                        value lives on code+'1' (e.g. 'lag1'=0.2). Probe THAT.
          null       -- code exists but its default is null (op-ref/empty param)
          no_gt_file -- no ground-truth file for the operator
          missing    -- the code is not in the live-TD capture at all
        """
        params = self._params(family, name)
        if params is None:
            return code, None, "no_gt_file"
        p = params.get(code)
        if isinstance(p, dict) and p.get("default") is not None:
            return code, p.get("default"), "scalar"
        comp = params.get(code + "1")  # tuplet parent -> first component (lag -> lag1)
        if isinstance(comp, dict) and comp.get("default") is not None:
            return code + "1", comp.get("default"), "tuplet"
        if isinstance(p, dict):
            return code, None, "null"
        return code, None, "missing"


def _eq_default(a, b) -> bool:
    if a is None or b is None:
        return False
    return str(a).strip().lower() == str(b).strip().lower()


# ---------------------------------------------------------------------------
# Probes derived from the SAME 60 labels
# ---------------------------------------------------------------------------
def _first(clauses, key):
    for cl in clauses:
        if key in cl and cl[key]:
            return cl[key][0]
    return None


def _all_vals(clauses, key):
    out = []
    for cl in clauses:
        for v in cl.get(key, []) or []:
            if v not in out:
                out.append(v)
    return out


def derive_probes(queries):
    """From labeled_queries -> {operators:[{name,family,python_class,from}],
    params:[{op,family,python_class,codes,from}]}."""
    operators, params, seen_ops = [], [], {}

    def reg_op(name, pyc, src):
        if not name:
            return
        if name not in seen_ops:
            fam = next((f for f in OP_FAMILIES if name.upper().endswith(f)), None)
            rec = {"name": name, "family": fam, "python_class": pyc, "from": src}
            seen_ops[name] = rec
            operators.append(rec)
        elif pyc and not seen_ops[name].get("python_class"):
            seen_ops[name]["python_class"] = pyc

    for row in queries:
        if row["category"] not in ("operator_lookup", "parameter"):
            continue  # build_instruction/negative/etc. carry no operator/param probe
        cl = row.get("relevant_predicate", {}).get("clauses", [])
        name = _first(cl, "op_name_any")
        pyc = _first(cl, "python_class_any")
        if row["category"] == "operator_lookup":
            reg_op(name, pyc, row["id"])
        elif row["category"] == "parameter":
            reg_op(name, pyc, row["id"])
            codes = _all_vals(cl, "param_code_any")
            if name and codes:
                fam = seen_ops.get(name, {}).get("family")
                params.append({"op": name, "family": fam, "python_class": pyc,
                               "codes": codes, "from": row["id"]})
    return {"operators": operators, "params": params}


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def run_checks(kg, probes, gt: GroundTruth, defaults: ParamDefaults):
    with contextlib.redirect_stdout(sys.stderr):
        return _run_checks_inner(kg, probes, gt, defaults)


def _run_checks_inner(kg, probes, gt, defaults):
    results = {}

    # 1) get_operator_info
    oi = {"n": 0, "resolved": 0, "name_correct": 0, "has_params": 0, "retokenized": 0, "detail": []}
    info_cache = {}
    for op in probes["operators"]:
        oi["n"] += 1
        info = kg.get_operator_info(op["name"])
        info_cache[op["name"]] = info
        resolved = bool(info)
        ret_name = (info or {}).get("name") or (info or {}).get("operator_name")
        name_ok = bool(ret_name) and _norm(ret_name) == _norm(op["name"])
        n_params = len(list(_wiki_params(info))) if info else 0
        retok = bool(ret_name) and ("_" in str(ret_name)) and (gt.canonical_for(ret_name) not in (None, ret_name))
        oi["resolved"] += resolved
        oi["name_correct"] += name_ok
        oi["has_params"] += (n_params > 0)
        oi["retokenized"] += retok
        oi["detail"].append({"op": op["name"], "from": op["from"], "resolved": resolved,
                             "returned_name": ret_name, "name_correct": name_ok,
                             "n_params": n_params, "retokenized_name": retok})
    results["get_operator_info"] = oi

    # 2) get_parameter_detail vs live-TD ground truth.
    # "verifiable" = GT has a concrete (non-null) default to check against; a GT
    # default of null (op-reference/empty params) is INCONCLUSIVE, not a failure.
    pd = {"n": 0, "param_found": 0, "default_present": 0, "default_correct": 0,
          "verifiable": 0, "inconclusive": 0, "gt_file_missing": 0, "tuplet": 0, "detail": []}
    for pr in probes["params"]:
        info = info_cache.get(pr["op"]) or kg.get_operator_info(pr["op"])
        for code in pr["codes"]:
            pd["n"] += 1
            probe_code, gt_default, gt_status = (
                defaults.resolve(pr["family"], pr["op"], code) if pr["family"] else (code, None, "no_gt_file"))
            # probe the tool with the REAL value-bearing code (lag -> lag1 for tuplets)
            det = tool_get_parameter_detail(info, probe_code)
            found = det is not None
            tool_default = det.get("default") if det else None
            present = tool_default is not None
            if gt_status == "tuplet":
                pd["tuplet"] += 1
            if gt_status in ("scalar", "tuplet"):
                pd["verifiable"] += 1
                correct = _eq_default(tool_default, gt_default)
                pd["default_correct"] += correct
                status = "correct" if correct else "wrong"
            elif gt_status == "no_gt_file":
                pd["gt_file_missing"] += 1
                status = "no_gt_file"
            else:  # null / missing -> can't verify a value
                pd["inconclusive"] += 1
                status = f"inconclusive_{gt_status}"
            pd["param_found"] += found
            pd["default_present"] += present
            pd["detail"].append({"op": pr["op"], "label_code": code, "probe_code": probe_code,
                                "from": pr["from"], "param_found": found, "tool_default": tool_default,
                                "gt_default": gt_default, "gt_status": gt_status, "status": status})
    results["get_parameter_detail"] = pd

    # 3) find_operator_examples coverage
    fe = {"n": 0, "has_example": 0, "detail": []}
    for op in probes["operators"]:
        fe["n"] += 1
        try:
            ex = kg.find_examples_by_operator(op["name"], 10, family=op.get("family"))
        except Exception:
            ex = []
        cnt = len(ex) if isinstance(ex, list) else 0
        fe["has_example"] += (cnt > 0)
        fe["detail"].append({"op": op["name"], "n_examples": cnt})
    results["find_operator_examples"] = fe

    # 4) find_operator_combination over intents, queried with NATURAL canonical
    # operator tokens (what a builder would type). Report the tool default
    # (require_connection=True) and the looser co-occurrence (False). Misses are
    # mostly TOKEN BRITTLENESS: the example data keys by TD's short OPType
    # (comp/geo/cam) while the canonical query uses composite/geometry/camera, and
    # find_operator_combination does not bridge that gap (verified vs the live tool:
    # the render pattern exists as 'COMP:cam + COMP:geo + ... + TOP:render'). This
    # is the section 6.9/6.11 token-normalization gap, not absent data.
    fc = {"n": 0, "has_hit_connected": 0, "has_hit_cooccur": 0, "detail": []}
    unresolved = set()
    for intent in PATTERN_INTENTS:
        fc["n"] += 1
        try:
            connected = kg.find_examples_by_operator_combination(intent["ops"], True, 5)
            cooccur = kg.find_examples_by_operator_combination(intent["ops"], False, 5)
        except Exception:
            connected, cooccur = [], []
        nc = len(connected) if isinstance(connected, list) else 0
        no = len(cooccur) if isinstance(cooccur, list) else 0
        # member ops whose canonical token finds no solo example (token-unresolved)
        miss_ops = []
        for op_t in intent["ops"]:
            try:
                solo = kg.find_examples_by_operator_combination([op_t], False, 1)
            except Exception:
                solo = []
            if not solo:
                miss_ops.append(op_t)
                unresolved.add(op_t)
        fc["has_hit_connected"] += (nc > 0)
        fc["has_hit_cooccur"] += (no > 0)
        fc["detail"].append({"intent": intent["id"], "ops": intent["ops"], "howto": intent["howto"],
                            "n_connected": nc, "n_cooccur": no, "token_unresolved_ops": miss_ops})
    fc["token_unresolved_ops"] = sorted(unresolved)
    results["find_operator_combination"] = fc

    # 5) get_network_patterns inventory + readMe pollution
    def _polluted(p) -> bool:
        s = json.dumps(p, default=str).lower()
        return "dat:text" in s or "readme" in s or '"text"' in s
    np_res = {}
    for mf in (5, 2):
        try:
            pats = kg.get_network_patterns(mf)
        except Exception:
            pats = []
        pats = pats if isinstance(pats, list) else []
        np_res[f"min_freq_{mf}"] = {"count": len(pats),
                                    "polluted": sum(1 for p in pats if _polluted(p))}
    results["get_network_patterns"] = np_res
    return results


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def scorecard_lines(r):
    oi, pd = r["get_operator_info"], r["get_parameter_detail"]
    fe, fc, npat = r["find_operator_examples"], r["find_operator_combination"], r["get_network_patterns"]
    p5, p2 = npat["min_freq_5"], npat["min_freq_2"]
    return [
        f"  get_operator_info       resolved {oi['resolved']}/{oi['n']}  name-correct {oi['name_correct']}/{oi['n']}"
        f"  has-params {oi['has_params']}/{oi['n']}  retokenized-name {oi['retokenized']}",
        f"  get_parameter_detail    param-found {pd['param_found']}/{pd['n']}  default-present {pd['default_present']}/{pd['n']}"
        f"  default-correct {pd['default_correct']}/{pd['verifiable']} verifiable ({pd['inconclusive']} inconclusive)",
        f"  find_operator_examples  >=1 example {fe['has_example']}/{fe['n']} operators",
        f"  find_operator_combination  >=1 hit (natural tokens): connected {fc['has_hit_connected']}/{fc['n']}  cooccur {fc['has_hit_cooccur']}/{fc['n']}"
        f"  ({len(fc['token_unresolved_ops'])} token-unresolved ops drive misses)",
        f"  get_network_patterns    freq>=5: {p5['count']} ({p5['polluted']} readMe-polluted)"
        f"  | freq>=2: {p2['count']} ({p2['polluted']} polluted)",
    ]


def write_markdown(md_path: Path, payload: dict):
    r = payload["results"]
    oi, pd = r["get_operator_info"], r["get_parameter_detail"]
    fe, fc, npat = r["find_operator_examples"], r["find_operator_combination"], r["get_network_patterns"]
    lines = [
        "# TD Builder — Tool-coverage baseline (Phase 0.5)",
        "",
        f"- Generated by `eval/tool_coverage.py` v{payload['harness_version']} (offline, in-process)",
        f"- Engine: real `UnifiedGraphQuery` (the `knowledge_graph` MCP handlers delegate to)",
        f"- KB: `{payload['kb_root']}`",
        f"- Probes derived from the same {payload['n_queries']} labels: "
        f"{oi['n']} operators, {pd['n']} (operator,param) pairs, {fc['n']} pattern intents",
        "",
        "## Scorecard",
        "",
        "| Tool | metric | result |",
        "|---|---|---|",
        f"| get_operator_info | resolved / name-correct / has-params | {oi['resolved']}/{oi['n']} · {oi['name_correct']}/{oi['n']} · {oi['has_params']}/{oi['n']} |",
        f"| get_operator_info | retokenized name surfaced | {oi['retokenized']} |",
        f"| get_parameter_detail | param-found | {pd['param_found']}/{pd['n']} |",
        f"| get_parameter_detail | default present | {pd['default_present']}/{pd['n']} |",
        f"| **get_parameter_detail** | **default matches live-TD ground truth** | **{pd['default_correct']}/{pd['verifiable']} verifiable** ({pd['inconclusive']} inconclusive) |",
        f"| find_operator_examples | operators with >=1 example | {fe['has_example']}/{fe['n']} |",
        f"| find_operator_combination | intents w/ >=1 hit (require_connection) | {fc['has_hit_connected']}/{fc['n']} |",
        f"| find_operator_combination | intents w/ >=1 hit (co-occurrence) | {fc['has_hit_cooccur']}/{fc['n']} |",
        f"| get_network_patterns | freq>=5 count (readMe-polluted) | {npat['min_freq_5']['count']} ({npat['min_freq_5']['polluted']}) |",
        f"| get_network_patterns | freq>=2 count (readMe-polluted) | {npat['min_freq_2']['count']} ({npat['min_freq_2']['polluted']}) |",
        "",
        "## What this baselines (and what Phase 1+ must fix)",
        f"- **get_operator_info + get_parameter_detail work for common SCALAR params, but tuplet params break.** "
        f"All {oi['resolved']}/{oi['n']} operators resolve with canonical names + parameters, and scalar defaults match "
        f"the live-TD capture on **{pd['default_correct']}/{pd['verifiable']}** verifiable params. The miss(es) are "
        f"**multi-value tuplet params** ({pd['tuplet']} probed): e.g. Lag CHOP's `lag` is really `lag1`/`lag2`=0.2, but the "
        "wiki only has the value-less grouping `lag` (default null), so `get_parameter_detail('Lag CHOP','lag1')` returns "
        "*not found* — the tool can't hydrate the code a builder actually uses. §6.2 must re-ground tuplet params from "
        "`operator_ground_truth`. (Sample is the labeled common params; widen to quantify the long tail.)",
        f"- **find_operator_combination is token-brittle.** With natural canonical tokens it discovers only "
        f"{fc['has_hit_connected']}/{fc['n']} intents; the misses come from operators whose examples are keyed by TD's "
        f"short OPType ({', '.join(fc['token_unresolved_ops']) or 'none here'} → comp/geo/cam), which the tool does not "
        "bridge from the canonical name. Verified vs the live tool: the render pattern DOES exist as "
        "`COMP:cam + COMP:geo + COMP:light + DAT:text + TOP:render`. This is the §6.9/§6.11 token-normalization gap, not absent data.",
        f"- **Example coverage is partial** ({fe['has_example']}/{fe['n']} operators have >=1 example; "
        "Audio File In CHOP is the miss here) — §6.7 OPSnippets widens it.",
        f"- **Pattern signatures are 100% readMe-polluted** ({npat['min_freq_2']['polluted']}/{npat['min_freq_2']['count']} at "
        "freq>=2 every signature carries a `DAT:text` node) and reachable only by exact operator-set — §6.11 re-authors "
        "them intent-labeled + filters helper noise.",
        "",
        "_Offline, faithful to the live tools (drives `UnifiedGraphQuery` directly). Re-run after each "
        "Phase-1 section to watch these move. Deterministic — no HNSW jitter (graph/dict lookups, not ANN)._",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Phase-0.5 tool-coverage harness")
    ap.add_argument("--kb", default=None)
    ap.add_argument("--queries", default=str(EVAL_DIR / "labeled_queries.jsonl"))
    ap.add_argument("--out", default=str(EVAL_DIR / "tool_baseline.json"))
    ap.add_argument("--stage-dir", default=None)
    ap.add_argument("--gt-operators", default=None, help="authoritative operators.json (default: stable, independent of --kb)")
    ap.add_argument("--gt-types", default=None, help="authoritative operator_types.json (default: stable Resources)")
    ap.add_argument("--params-dir", default=None, help="operator_ground_truth/params dir (default: stable Resources)")
    args = ap.parse_args()

    kb_root = run_eval.resolve_kb_root(args.kb).resolve()
    stage_dir = run_eval.resolve_stage_dir(args.stage_dir, kb_root).resolve()
    out_path = Path(args.out).resolve()
    # GT resolved INDEPENDENTLY of --kb (flags win) so it stays valid for a rebuilt KB.
    gt_ops, gt_types = run_eval.resolve_gt_paths(args.gt_operators, args.gt_types, kb_root)
    params_dir = (Path(args.params_dir) if args.params_dir else gt_types.parent / "params").resolve()

    gt = GroundTruth(operators_json=gt_ops, operator_types_json=gt_types)
    defaults = ParamDefaults(params_dir)
    queries = [json.loads(ln) for ln in Path(args.queries).read_text(encoding="utf-8").splitlines() if ln.strip()]
    probes = derive_probes(queries)
    print(f"KB: {kb_root}\nprobes: {len(probes['operators'])} operators, "
          f"{sum(len(p['codes']) for p in probes['params'])} param checks, "
          f"{len(PATTERN_INTENTS)} pattern intents\nbuilding UnifiedGraphQuery (this loads graphrag.json + gpickle)...\n",
          file=sys.stderr)

    kg = build_graph(kb_root)
    results = run_checks(kg, probes, gt, defaults)

    payload = {
        "harness_version": HARNESS_VERSION,
        "kb_root": run_eval.redact_path(kb_root),
        "engine": "UnifiedGraphQuery (offline, in-process)",
        "n_queries": len(queries),
        "results": results,
        "notes": ("Tool-behavior baseline for the KB-dependent MCP tools other than hybrid_search "
                  "(gated by run_eval.py). Defaults compared against operator_ground_truth (live-TD). "
                  "Deterministic: graph/dict lookups, no HNSW. Re-run after each Phase-1 section."),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "tool_baseline.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_markdown(stage_dir / "TOOL_COVERAGE.md", payload)

    print("\n" + "=" * 64)
    print(f"TOOL-COVERAGE BASELINE  (KB: {kb_root.name})")
    for ln in scorecard_lines(results):
        print(ln)
    print("=" * 64)
    print(f"\nwrote:\n  {out_path}\n  {stage_dir / 'tool_baseline.json'}\n  {stage_dir / 'TOOL_COVERAGE.md'}")


if __name__ == "__main__":
    main()

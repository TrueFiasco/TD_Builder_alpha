#!/usr/bin/env python3
r"""
TRACK A -- offline core build-correctness harness (the CORE gate).

For each KB operator: derive a minimal builder `design` from its KB name, run the
SHIPPING offline builder (`ToxBuilder.build_tox`, the exact path `td_build_project`
uses), collapse to a real `.tox`, expand it with TD's REAL `toeexpand`, then read
the op's `.n` token + `.parm` codes from the RAW expanded files (NOT the tolerant
lossless_parser, which masks unquoted-space bugs) and compare against the captured
live-TD ground truth + run in-process `td_validate`.

Two feeds per op:
  * "extracted" -- type = registry-extracted token (e.g. 'abletonlink'), the
                   principled KB-derived input. The realistic path. ALWAYS run.
  * "ntoken"    -- type = captured n_token colon-form (e.g. 'CHOP:ableton'), the
                   CORRECT token. Run ONLY for ops whose builder_token != n_token,
                   as a counterfactual: "given the right token, do params/validate
                   come out clean?" -- i.e. would the proposed INTERNAL_NAME_MAP /
                   AMBIGUOUS_OPERATORS fix actually build correctly?

The TOKEN-mismatch census is already computed (no build needed) by
gate_common.CanonicalMap; this harness CONFIRMS it end-to-end through the real
TD round-trip and adds the param-serialization + validate dimensions.

Usage (worktree; py -3.11; KB hardlinked in):
    py -3.11 eval/build_gate/track_a_offline.py --seed
    py -3.11 eval/build_gate/track_a_offline.py --all --resume
    py -3.11 eval/build_gate/track_a_offline.py --families CHOP,POP
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parent))
import gate_common as gc  # noqa: E402

HARNESS = "build_gate.track_a"
VERSION = "0.1.0"
EXPAND_TIMEOUT_S = 120

# verdict precedence (worst first)
VERDICT_RANK = ["BUILD_FAIL", "EXPAND_FAIL", "OP_NOT_FOUND", "TOKEN_MISMATCH",
                "PARAM_DROP", "PARAM_VALUE", "VALIDATE_FAIL", "PASS"]


# ---------------------------------------------------------------------------
# In-process td_validate — same stack as the shipped handler, constructed via
# the engine's single seam (MCP/engine/api/validate.py::build_validation_stack)
# ---------------------------------------------------------------------------
_VALIDATOR = None
_CONVERTER = None


def _validator():
    global _VALIDATOR, _CONVERTER
    if _VALIDATOR is None:
        gc.ensure_paths()
        # Lazy: `api` resolves only after ensure_paths() puts the engine root up.
        from api.validate import build_validation_stack
        _registry, _CONVERTER, _VALIDATOR = build_validation_stack()
    return _VALIDATOR, _CONVERTER


def td_validate_builder(design: dict) -> dict:
    try:
        validator, converter = _validator()
        network = converter.from_builder(design)
        report = validator.validate(network, design.get("project", "network"))
        return {"pass": bool(report.valid),
                "errors": [{"stage": e.stage, "message": e.message} for e in report.get_errors()][:6]}
    except Exception as e:
        return {"pass": False, "errors": [{"stage": "exception", "message": str(e)}]}


# ---------------------------------------------------------------------------
# Perturbed params
# ---------------------------------------------------------------------------
def load_perturbed(family: str, gt_name: str) -> dict:
    """params/{FAM}_{gt}_perturbed.json -> {code: value} for value-bearing entries."""
    f = gc.params_dir() / f"{family}_{gt_name}_perturbed.json"
    if not f.exists():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))
    out = {}
    for code, spec in (data.get("parameters") or {}).items():
        if not isinstance(spec, dict):
            continue
        val = spec.get("value")
        if val is None:
            continue
        out[code] = val
    return out


def captured_perturbed_parm(family: str, gt_name: str) -> dict:
    """The captured op_perturbed.parm of this op (ground truth for serialized form)."""
    inner = gc.tox_expanded_dir() / f"{family}_{gt_name}.tox.dir" / f"sample_{gt_name}"
    return gc.read_parm_codes(inner / "op_perturbed.parm")


# ---------------------------------------------------------------------------
# Build + expand one design through the REAL TD round-trip
# ---------------------------------------------------------------------------
def build_and_expand(design: dict, out_dir: Path, toeexpand: Path) -> dict:
    """ToxBuilder.build_tox -> collapsed .tox -> real toeexpand -> raw op0.n/.parm.

    Returns {built, build_error, expanded, expand_error, n_token, parm}.
    """
    gc.ensure_paths()
    from meta_agentic.execution.tox_builder import ToxBuilder

    out_dir.mkdir(parents=True, exist_ok=True)
    res = {"built": False, "build_error": None, "expanded": False,
           "expand_error": None, "n_token": None, "parm": {}}

    builder = ToxBuilder(out_dir, verbose=False)
    try:
        tox_path = builder.build_tox(design, "opnet")
    except Exception as e:
        res["build_error"] = f"exception: {e}"
        return res
    if not tox_path or not Path(tox_path).exists():
        tail = "\n".join(getattr(builder, "build_log", [])[-4:]) if hasattr(builder, "build_log") else ""
        res["build_error"] = "build_tox returned no .tox" + (f" | {tail}" if tail else "")
        return res
    res["built"] = True

    # expand the COLLAPSED .tox with real toeexpand, in an isolated subdir we own
    exp = out_dir / "_expand"
    if exp.exists():
        shutil.rmtree(exp, ignore_errors=True)
    exp.mkdir(parents=True)
    tox_copy = exp / Path(tox_path).name
    shutil.copy2(tox_path, tox_copy)
    try:
        subprocess.run([str(toeexpand), str(tox_copy)], cwd=str(exp),
                       capture_output=True, text=True, timeout=EXPAND_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        res["expand_error"] = "toeexpand timeout"
        return res
    # toeexpand returns rc 1 on success on some builds -> check for the .dir, not rc
    dirs = list(exp.glob("*.tox.dir"))
    if not dirs:
        res["expand_error"] = "no .tox.dir produced by toeexpand"
        return res
    res["expanded"] = True
    tox_dir = dirs[0]

    # locate the op: it was named "op0"; the wrapper is opnet.n
    n_files = list(tox_dir.glob("**/op0.n"))
    if not n_files:
        # fall back: any .n that isn't the top wrapper
        others = [p for p in tox_dir.glob("**/*.n") if p.stem != tox_dir.stem.replace(".tox", "")]
        if not others:
            res["expand_error"] = "op0.n not found in expanded dir"
            return res
        n_files = others
    n_path = n_files[0]
    res["n_token"] = gc.read_n_token(n_path)
    res["parm"] = gc.read_parm_codes(n_path.with_suffix(".parm"))
    return res


# ---------------------------------------------------------------------------
# Param comparison
# ---------------------------------------------------------------------------
_TOGGLE = {"on": "1", "off": "0", "true": "1", "false": "0", "1": "1", "0": "0"}


def _val_equal(built: str, captured: str) -> bool:
    """Tolerant compare of two serialized .parm values, token-wise:
      * numeric  -> equal within float32 rounding (TD rounds ~6 sig figs on save;
                    the builder emits the full float64 repr -> functionally equal).
      * toggle   -> on/off == 1/0 == true/false (TD accepts all; see memory).
      * else     -> case-insensitive string equality.
    Multi-component values ('0.62 0.62 0.62') compare component-by-component."""
    b_toks = built.strip().split()
    c_toks = captured.strip().split()
    if len(b_toks) != len(c_toks):
        # also allow whole-string toggle/equality fallthrough
        return gc._eq_default(built, captured)
    for b, c in zip(b_toks, c_toks):
        bl, cl = b.strip().lower(), c.strip().lower()
        if bl == cl:
            continue
        if bl in _TOGGLE and cl in _TOGGLE and _TOGGLE[bl] == _TOGGLE[cl]:
            continue
        try:
            fb, fc = float(b), float(c)
            if abs(fb - fc) <= 1e-3 * max(1.0, abs(fc)):
                continue
            return False
        except ValueError:
            return False
    return True


def compare_params(set_codes: dict, built_parm: dict, captured_parm: dict) -> dict:
    """Compare the params we SET against what got serialized (built, via the real TD
    round-trip) and the captured ground-truth op_perturbed.parm.

    DROP (the strong signal -- catches the unquoted-space desync that drops trailing
    params, and genuine code loss): a code we fed that TD's own capture DOES contain
    but the builder DID NOT emit. Rename-robust (a builder lag->lag1 rename leaves
    'lag' absent from the capture, so it is not miscounted).

    VALUE (soft signal): for codes present in BOTH where the captured value is a
    CONSTANT (mode 0), tolerant-compare the value. Expression-mode captures (the op's
    default is an expression we didn't truly override) are skipped, not failed.
    """
    codes_set = list(set_codes.keys())
    built_codes = set(built_parm)
    cap_codes = set(captured_parm)

    dropped = [c for c in codes_set if c in cap_codes and c not in built_codes]
    emitted = [c for c in codes_set if c in built_codes]
    extra = sorted(built_codes - cap_codes)            # builder wrote, TD didn't (informational)

    value_mismatches, skipped_expr = [], 0
    for c in sorted(cap_codes & built_codes):
        cap_mode, cap_val = captured_parm[c]
        b_mode, b_val = built_parm[c]
        if cap_mode != "0":                 # expression / non-constant default -> not a literal perturbation
            skipped_expr += 1
            continue
        if not _val_equal(b_val, cap_val):
            value_mismatches.append({"code": c, "built": f"{b_mode} {b_val}".strip(),
                                     "captured": f"{cap_mode} {cap_val}".strip()})
    return {
        "codes_set": len(codes_set), "codes_emitted": len(emitted),
        "codes_dropped": dropped[:12], "n_dropped": len(dropped),
        "value_mismatches": value_mismatches[:12], "n_value_mismatch": len(value_mismatches),
        "n_extra": len(extra), "extra": extra[:12], "skipped_expr": skipped_expr,
    }


# ---------------------------------------------------------------------------
# One (op, feed)
# ---------------------------------------------------------------------------
def run_one(op_name: str, rec: dict, feed: str, out_dir: Path, toeexpand: Path) -> dict:
    family = rec["family"]
    gt_name = rec["gt_name"]
    if feed == "extracted":
        type_in = rec["extracted_type"]
    else:  # ntoken
        type_in = rec["n_token"]  # colon form; _map_op_type returns as-is

    set_codes = load_perturbed(family, gt_name)
    design = {"operators": [{"name": "op0", "type": type_in, "family": family,
                             "parameters": set_codes}],
              "connections": [], "project": "opnet"}

    out = {"op": op_name, "family": family, "feed": feed, "track": "A",
           "coverage": rec["coverage"], "type_in": type_in,
           "builder_token": rec["builder_token"], "expected_n_token": rec["n_token"]}

    be = build_and_expand(design, out_dir, toeexpand)
    out["built"] = be["built"]
    out["build_error"] = be["build_error"]
    out["expanded"] = be["expanded"]
    out["expand_error"] = be["expand_error"]
    out["got_n_token"] = be["n_token"]

    # token comparison (only meaningful when we have a captured authority)
    exp_tok = rec["n_token"]
    if exp_tok and be["n_token"]:
        out["token_exact"] = (be["n_token"].strip() == exp_tok.strip())
        out["token_norm"] = (gc.norm_token(be["n_token"]) == gc.norm_token(exp_tok))
    else:
        out["token_exact"] = None
        out["token_norm"] = None

    # params
    cap = captured_perturbed_parm(family, gt_name)
    out["params"] = compare_params(set_codes, be["parm"], cap)

    # validate (always on the builder design)
    out["validate"] = td_validate_builder(design)

    # verdict
    out["verdict"] = _verdict(out)
    return out


def _verdict(o: dict) -> str:
    if not o["built"]:
        return "BUILD_FAIL"
    if not o["expanded"]:
        return "EXPAND_FAIL"
    if o["got_n_token"] is None:
        return "OP_NOT_FOUND"
    if o["token_exact"] is False:           # only when we had an authority
        return "TOKEN_MISMATCH"
    p = o["params"]
    if p["n_dropped"] > 0:
        return "PARAM_DROP"
    if p["n_value_mismatch"] > 0:
        return "PARAM_VALUE"
    if not o["validate"]["pass"]:
        return "VALIDATE_FAIL"
    return "PASS"


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------
SEED_FIXED = [
    # 7 POP INTERNAL_NAME_MAP overrides (must PASS -- regression guard)
    "Point Generator POP", "GLSL Advanced POP", "Attribute Combine POP",
    "Attribute Convert POP", "Lookup Attribute POP", "Lookup Channel POP", "Lookup Texture POP",
    # known-divergent (expect TOKEN_MISMATCH until fixed)
    "Ableton Link CHOP", "Add TOP", "Camera COMP", "Table COMP", "MIDI In DAT",
    "Threshold TOP", "Difference TOP",
    # known-correct override sanity
    "Audio Device In CHOP", "Composite TOP", "HSV Adjust TOP",
    # plain ops that should just PASS
    "Noise CHOP", "Level TOP", "Constant CHOP", "Transform SOP", "Text DAT",
]


def select_ops(cmap, args) -> list[str]:
    ops = cmap.operators
    if args.seed:
        return [n for n in SEED_FIXED if n in ops]
    fams = set(f.strip().upper() for f in args.families.split(",")) if args.families else None
    names = [n for n, r in ops.items() if (fams is None or r["family"] in fams)]
    if args.all or fams:
        # deterministic order: family then name
        names.sort(key=lambda n: (ops[n]["family"], n))
        return names
    # default sample: strided per family + the fixed seed
    per_fam = {}
    for n in sorted(names, key=lambda n: (ops[n]["family"], n)):
        per_fam.setdefault(ops[n]["family"], []).append(n)
    picked = set(SEED_FIXED) & set(names)
    for fam, lst in per_fam.items():
        step = max(1, len(lst) // args.sample)
        picked.update(lst[::step][:args.sample])
    return sorted(picked, key=lambda n: (ops[n]["family"], n))


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Track A -- offline build-correctness gate")
    ap.add_argument("--seed", action="store_true", help="fixed seed list (~22 ops), both feeds")
    ap.add_argument("--all", action="store_true", help="all KB operators")
    ap.add_argument("--families", default=None, help="comma list e.g. CHOP,POP")
    ap.add_argument("--sample", type=int, default=8, help="per-family sample when not --all/--seed")
    ap.add_argument("--resume", action="store_true", help="skip (op,feed) already in the JSONL")
    ap.add_argument("--out", default=None, help="results JSONL (default: stage_dir/track_a_results.jsonl)")
    ap.add_argument("--limit", type=int, default=0, help="cap number of ops (debug)")
    args = ap.parse_args()

    gc.ensure_paths()
    toeexpand = gc._bridge() and __import__("paths").resolve_td_tool("toeexpand")
    if toeexpand is None:
        print("FATAL: toeexpand not found", file=sys.stderr)
        sys.exit(2)

    cmap = gc.CanonicalMap.load() if (gc.stage_dir() / gc.CanonicalMap.FILENAME).exists() else gc.CanonicalMap.build()
    if not (gc.stage_dir() / gc.CanonicalMap.FILENAME).exists():
        cmap.save()

    sel = select_ops(cmap, args)
    if args.limit:
        sel = sel[:args.limit]

    stage = gc.stage_dir()
    stage.mkdir(parents=True, exist_ok=True)
    out_jsonl = Path(args.out) if args.out else (stage / "track_a_results.jsonl")
    work_root = stage / "_work_a"
    work_root.mkdir(parents=True, exist_ok=True)

    done = set()
    if args.resume and out_jsonl.exists():
        for ln in out_jsonl.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    r = json.loads(ln)
                    done.add((r["op"], r["feed"]))
                except Exception:
                    pass
    mode = "a" if (args.resume and out_jsonl.exists()) else "w"

    t0 = time.time()
    n_done = 0
    with open(out_jsonl, mode, encoding="utf-8") as fh:
        for i, name in enumerate(sel):
            rec = cmap.operators[name]
            feeds = ["extracted"]
            # ntoken counterfactual only for token-mismatched ops that have an authority
            if rec["n_token"] and gc.norm_token(rec["builder_token"]) != gc.norm_token(rec["n_token"]):
                feeds.append("ntoken")
            for feed in feeds:
                if (name, feed) in done:
                    continue
                safe = f"{i:03d}_{rec['family']}_{gc._norm(name)}_{feed}"
                out_dir = work_root / safe
                try:
                    r = run_one(name, rec, feed, out_dir, toeexpand)
                except Exception as e:
                    r = {"op": name, "family": rec["family"], "feed": feed, "track": "A",
                         "verdict": "BUILD_FAIL", "build_error": f"harness exception: {e}",
                         "coverage": rec["coverage"]}
                fh.write(json.dumps(r) + "\n")
                fh.flush()
                n_done += 1
                # keep disk bounded: drop the per-op work tree after recording
                shutil.rmtree(out_dir, ignore_errors=True)
                print(f"[{i+1}/{len(sel)}] {name:30s} {feed:9s} -> {r['verdict']}", file=sys.stderr)

    dt = round(time.time() - t0, 1)
    print(f"\nTrack A: {n_done} (op,feed) records in {dt}s -> {out_jsonl}", file=sys.stderr)
    # build the rollup report
    write_report(out_jsonl, stage, cmap, args)


# ---------------------------------------------------------------------------
def write_report(jsonl: Path, stage: Path, cmap, args):
    recs = [json.loads(ln) for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    ext = [r for r in recs if r.get("feed") == "extracted"]

    def tally(rows):
        t = {"ops": len(rows), "built": 0, "expanded": 0, "token_exact": 0,
             "param_clean": 0, "validate_pass": 0, "pass": 0, "token_checkable": 0}
        for r in rows:
            t["built"] += bool(r.get("built"))
            t["expanded"] += bool(r.get("expanded"))
            if r.get("token_exact") is not None:
                t["token_checkable"] += 1
                t["token_exact"] += bool(r.get("token_exact"))
            p = r.get("params", {})
            t["param_clean"] += (p.get("n_dropped", 0) == 0 and p.get("n_value_mismatch", 0) == 0)
            t["validate_pass"] += bool(r.get("validate", {}).get("pass"))
            t["pass"] += (r.get("verdict") == "PASS")
        return t

    totals = tally(ext)
    by_family = {}
    for r in ext:
        by_family.setdefault(r["family"], []).append(r)
    by_family = {f: tally(rows) for f, rows in sorted(by_family.items())}
    by_verdict = {}
    for r in ext:
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1

    # ntoken counterfactual: of the token-mismatched ops, feed the CORRECT token and ask
    #   (a) does the BUILD come out clean (token exact + params clean)?  -> proves the
    #       INTERNAL_NAME_MAP / AMBIGUOUS_OPERATORS fix would build correctly.
    #   (b) does td_validate pass?  -> EXPECTED NO: the OperatorRegistry is keyed on the
    #       DISPLAY token, so it does not recognise the real token. That divergence is the
    #       core integration defect Track D must close (align builder + validator + GT).
    nt = [r for r in recs if r.get("feed") == "ntoken"]

    def _build_clean(r):
        p = r.get("params", {})
        return bool(r.get("built") and r.get("expanded") and r.get("token_exact")
                    and p.get("n_dropped", 0) == 0 and p.get("n_value_mismatch", 0) == 0)
    nt_build_clean = sum(1 for r in nt if _build_clean(r))
    nt_validate_pass = sum(1 for r in nt if r.get("validate", {}).get("pass"))
    nt_pass = nt_build_clean

    mismatches = sorted([r for r in ext if r.get("verdict") != "PASS"],
                        key=lambda r: VERDICT_RANK.index(r["verdict"]) if r["verdict"] in VERDICT_RANK else 99)

    # Distinguish DOCUMENTED (expected) residuals from PRINCIPLED (regression) failures.
    expected_residuals, principled_failures = [], []
    for r in mismatches:
        c = gc.classify_residual(r)
        row = {"op": r["op"], "family": r["family"], "verdict": r["verdict"], "codes": c.get("codes", [])}
        if c["kind"] == "expected":
            expected_residuals.append({**row, "class": c["cls"], "reason": c["reason"]})
        else:
            principled_failures.append(row)

    payload = {
        "harness": HARNESS, "version": VERSION,
        "config": {"scope": "seed" if args.seed else ("all" if args.all else (args.families or f"sample{args.sample}")),
                   "n_ops_extracted": len(ext)},
        "totals": totals, "by_family": by_family, "by_verdict": by_verdict,
        "residual_triage": {
            "expected_documented": len(expected_residuals),
            "principled_failures": len(principled_failures),
            "expected": expected_residuals,
            "principled": principled_failures,
        },
        "ntoken_counterfactual": {"n_mismatched_ops_tested": len(nt),
                                  "build_clean_with_correct_token": nt_build_clean,
                                  "validate_pass_with_correct_token": nt_validate_pass},
        "mismatches": mismatches[:120],
        "results_jsonl": str(jsonl),
    }
    (stage / "track_a_offline.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # markdown scorecard
    lines = [
        "# TD Builder — Track A: offline build-correctness", "",
        f"- Harness `{HARNESS}` v{VERSION} (in-process `ToxBuilder` + real toeexpand, raw `.n`/`.parm`)",
        f"- Scope: **{payload['config']['scope']}**, {len(ext)} operators (extracted feed)", "",
        "## Totals (extracted feed = realistic KB-derived input)", "",
        "| metric | result |", "|---|---|",
        f"| built | {totals['built']}/{totals['ops']} |",
        f"| expanded (real toeexpand) | {totals['expanded']}/{totals['ops']} |",
        f"| **.n token == captured live token** | **{totals['token_exact']}/{totals['token_checkable']} checkable** |",
        f"| params clean (no drop/value-mismatch) | {totals['param_clean']}/{totals['ops']} |",
        f"| td_validate clean | {totals['validate_pass']}/{totals['ops']} |",
        f"| **PASS (all dimensions)** | **{totals['pass']}/{totals['ops']}** |",
        "",
        f"- ntoken counterfactual ({len(nt)} token-mismatched ops fed their CORRECT token): "
        f"**{nt_build_clean}/{len(nt)} build clean** (token exact + params clean -> the INTERNAL_NAME_MAP / "
        f"AMBIGUOUS_OPERATORS fix would build correctly), but only **{nt_validate_pass}/{len(nt)} pass td_validate** "
        "-- because the OperatorRegistry is keyed on the DISPLAY token, not the real one. That builder<->validator "
        "disagreement is the core integration defect (Track D).",
        "",
        "## By family", "", "| family | ops | token-exact | param-clean | validate | PASS |", "|---|---|---|---|---|---|",
    ]
    for f, t in by_family.items():
        lines.append(f"| {f} | {t['ops']} | {t['token_exact']}/{t['token_checkable']} | {t['param_clean']}/{t['ops']} | {t['validate_pass']}/{t['ops']} | {t['pass']}/{t['ops']} |")
    lines += ["", "## By verdict", "", "| verdict | count |", "|---|---|"]
    for v in VERDICT_RANK:
        if v in by_verdict:
            lines.append(f"| {v} | {by_verdict[v]} |")

    # Residual triage — the load-bearing distinction: DOCUMENTED vs PRINCIPLED.
    lines += ["", "## Residual triage (documented vs principled)", "",
              f"- **Principled failures (regressions to investigate): {len(principled_failures)}** "
              "— must be 0 for a clean gate. Any non-PASS op NOT in the EXPECTED_RESIDUALS "
              "allowlist (`gate_common.py`) lands here.",
              f"- Expected residuals (documented, root-caused, non-builder-code): {len(expected_residuals)}.",
              ""]
    if principled_failures:
        lines += ["### ⚠ Principled failures", "", "| op | family | verdict | codes |", "|---|---|---|---|"]
        for r in principled_failures:
            lines.append(f"| {r['op']} | {r['family']} | {r['verdict']} | {','.join(map(str, r['codes'][:5]))} |")
        lines.append("")
    lines += ["### Expected residuals (allowlisted)", "",
              "| op | family | class | codes | reason |", "|---|---|---|---|---|"]
    for r in expected_residuals:
        lines.append(f"| {r['op']} | {r['family']} | {r['class']} | {','.join(map(str, r['codes'][:4]))} | {r['reason']} |")

    lines += ["", "## Failing operators (worst-first)", "",
              "| op | family | verdict | got .n | expected .n | dropped params |", "|---|---|---|---|---|---|"]
    for r in mismatches[:80]:
        p = r.get("params", {})
        lines.append(f"| {r['op']} | {r['family']} | {r['verdict']} | {r.get('got_n_token')} | "
                     f"{r.get('expected_n_token')} | {','.join(p.get('codes_dropped', [])[:5])} |")
    (stage / "TRACK_A.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {stage / 'track_a_offline.json'}\n       {stage / 'TRACK_A.md'}", file=sys.stderr)


if __name__ == "__main__":
    main()

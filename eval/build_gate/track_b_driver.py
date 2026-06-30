"""
TRACK B driver -- runs INSIDE TouchDesigner via the td-builder-live MCP
`execute_python_script` tool (NOT under py-3.11; the live MCP isn't reachable
from a subprocess). LIVE TD is the authority.

Per op: create via the `td_create` token (getattr(td, token)) in a scratch
container -> read back the REAL identity (n.type / n.family / n.OPType) and
compare to the captured n_token -> set the perturbed params (live) and confirm
each KB code is accepted + value takes -> record cook errors -> destroy the probe.

Reads the canonical map + perturbed files FROM DISK, appends one JSON line per op
to track_b_results.jsonl (resumable -- a TD crash loses only the in-memory scratch
container, never the ledger). Driven in slices: the caller sets globals
  _B_START, _B_END  (op index range, sorted by family then name)
  _B_RESET          (truncate the ledger first)
then exec()s this file. Flat exec scope: top-level code only, no nested defs.
"""
import json
import os

# --- config (absolute; the gate stages to the MAIN tree) -------------------
_BASE = r"C:\TD_Builder_Alpha_Build_V0.1.2\New KB build"
CMAP_PATH = _BASE + r"\Output\build_gate\canonical_op_map.json"
PARAMS_DIR = _BASE + r"\Resources\operator_ground_truth\params"
OUT = _BASE + r"\Output\build_gate\track_b_results.jsonl"

_start = globals().get("_B_START", 0)
_end = globals().get("_B_END", 9999)
_reset = globals().get("_B_RESET", False)

cmap = json.load(open(CMAP_PATH, encoding="utf-8"))["operators"]
names = sorted(cmap.keys(), key=lambda k: (cmap[k]["family"], k))

if _reset and os.path.exists(OUT):
    os.remove(OUT)
done = set()
if os.path.exists(OUT):
    for ln in open(OUT, encoding="utf-8"):
        ln = ln.strip()
        if ln:
            try:
                done.add(json.loads(ln)["op"])
            except Exception:
                pass

scratch = op("/td_gate_scratch")
if scratch is None:
    scratch = op("/").create(getattr(td, "baseCOMP"), "td_gate_scratch")
    scratch.nodeX, scratch.nodeY = 0, -400

fh = open(OUT, "a", encoding="utf-8")
processed = 0
passed = 0
for _nm in names[_start:_end]:
    if _nm in done:
        continue
    r = cmap[_nm]
    rec = {"op": _nm, "family": r["family"], "td_create": r["td_create"],
           "track": "B", "coverage": r["coverage"]}
    tok = r["td_create"]
    if not tok:
        rec["verdict"] = "NO_TD_CREATE"
        fh.write(json.dumps(rec) + "\n")
        processed += 1
        continue
    cls = getattr(td, tok, None)
    if cls is None:
        rec["verdict"] = "LIVE_CREATE_FAIL"
        rec["error"] = "no td.%s class" % tok
        fh.write(json.dumps(rec) + "\n")
        processed += 1
        continue
    probe = None
    try:
        probe = scratch.create(cls, "probe")
    except Exception as e:
        rec["verdict"] = "LIVE_CREATE_FAIL"
        rec["error"] = str(e)[:200]
        fh.write(json.dumps(rec) + "\n")
        processed += 1
        continue

    rec["live_type"] = probe.type
    rec["live_family"] = probe.family
    rec["live_optype"] = probe.OPType
    exp = r["n_token"]
    if exp:
        got = probe.family + ":" + probe.type
        rec["n_token_expected"] = exp
        rec["n_token_live"] = got
        rec["token_match"] = (got.strip().lower() == exp.strip().lower())
    else:
        rec["token_match"] = None

    # perturbed params (value-bearing) set LIVE + read back
    tried = 0
    present = 0
    valok = 0
    missing = []
    errored = []
    pfile = os.path.join(PARAMS_DIR, "%s_%s_perturbed.json" % (r["family"], r["gt_name"]))
    if os.path.exists(pfile):
        pdata = json.load(open(pfile, encoding="utf-8")).get("parameters", {})
        for code in pdata:
            spec = pdata[code]
            if not isinstance(spec, dict):
                continue
            val = spec.get("value")
            if val is None:
                continue
            tried += 1
            par = getattr(probe.par, code, None)
            if par is None:
                missing.append(code)
                continue
            present += 1
            try:
                par.val = val
                rb = getattr(probe.par, code).eval()
                ok = False
                try:
                    ok = abs(float(rb) - float(val)) <= 1e-3 * max(1.0, abs(float(val)))
                except Exception:
                    ok = str(rb).strip().lower() == str(val).strip().lower()
                if ok:
                    valok += 1
            except Exception:
                errored.append(code)
    rec["params"] = {"tried": tried, "present": present, "value_ok": valok,
                     "missing": missing[:12], "n_missing": len(missing),
                     "errored": errored[:12], "n_errored": len(errored)}

    try:
        errs = probe.errors(recurse=False)
    except Exception:
        errs = ""
    rec["cook_errors"] = (errs[:300] if isinstance(errs, str) else str(errs)[:300])

    if rec.get("token_match") is False:
        v = "TYPE_MISMATCH"
    elif len(missing) > 0:
        v = "PARAM_MISSING"
    elif len(errored) > 0:
        v = "PARAM_LIVE_ERROR"
    elif rec["cook_errors"]:
        v = "COOK_ERROR"
    else:
        v = "PASS"
    rec["verdict"] = v
    if v == "PASS":
        passed += 1
    fh.write(json.dumps(rec) + "\n")
    fh.flush()
    processed += 1
    try:
        probe.destroy()
    except Exception:
        pass

fh.close()
print(json.dumps({"slice": [_start, _end], "processed": processed, "passed": passed,
                  "ledger_total": len(done) + processed, "n_ops": len(names)}))

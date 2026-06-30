"""Phase 0 (repro) — build the 3 representative buggy ops as 1-op .tox with the
CURRENT (unfixed) ToxBuilder, keep the .tox on disk, and print the build script +
the raw .n token + the rename .parm lines. The live side then loadTox's these to
show they import broken. Read-only w.r.t. shipping code; writes only to Output/_repro."""
import sys, json, shutil
sys.path.insert(0, r"C:\TD_Builder_Alpha_Build_V0.1.2\.claude\worktrees\loving-ride-98201b\eval\build_gate")
import gate_common as gc
gc.ensure_paths()
from meta_agentic.execution.tox_builder import ToxBuilder

OUT = gc.stage_dir() / "_repro"
if OUT.exists():
    shutil.rmtree(OUT, ignore_errors=True)
OUT.mkdir(parents=True, exist_ok=True)

cmap = gc.CanonicalMap.load().operators

CASES = [
    {"op": "Camera COMP", "type": "camera", "family": "COMP",
     "params": {"fov": 45.5, "scale": 1.5}},
    {"op": "Add TOP", "type": "add", "family": "TOP",
     "params": {"operand": "add"}},
    {"op": "Analyze CHOP", "type": "analyze", "family": "CHOP",
     "params": {"function": "average", "renamefrom": "*_in", "renameto": "_out"}},
]

manifest = []
for c in CASES:
    safe = c["type"]
    design = {"operators": [{"name": "op0", "type": c["type"], "family": c["family"],
                             "parameters": c["params"]}],
              "connections": [], "project": f"repro_{safe}"}
    b = ToxBuilder(OUT / safe, verbose=False)
    tox = b.build_tox(design, f"repro_{safe}")
    # raw built op .n / .parm (pre-collapse dir the builder leaves)
    ddir = OUT / safe / f"repro_{safe}.tox.dir" / f"repro_{safe}"
    n_tok = gc.read_n_token(ddir / "op0.n")
    parm = gc.read_parm_codes(ddir / "op0.parm")
    rec = cmap[c["op"]]
    entry = {
        "op": c["op"], "build_script": design, "tox_path": str(tox),
        "offline_n_token": n_tok, "expected_live_n_token": rec["n_token"], "td_create": rec["td_create"],
        "fed_param_codes": list(c["params"].keys()),
        "emitted_param_codes": sorted(parm.keys()),
        "rename_lines": {k: parm[k] for k in parm if "rename" in k.lower()},
    }
    manifest.append(entry)
    print("=" * 70)
    print(f"{c['op']}: offline .n = {n_tok}   (live/GT should be {rec['n_token']})")
    print(f"  tox: {tox}")
    print(f"  fed param codes   : {entry['fed_param_codes']}")
    print(f"  rename emitted as : {entry['rename_lines'] or '(none / dropped)'}")

(OUT / "repro_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("\nmanifest:", OUT / "repro_manifest.json")

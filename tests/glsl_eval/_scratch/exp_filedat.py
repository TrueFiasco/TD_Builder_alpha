"""Verify the user's proposed architecture: GLSL TOP shader via an EXTERNAL
.glsl file referenced by the Text DAT (file + syncfile on), with the DAT text
cleared. Tests: (1) loads & compiles from file with no .text cache,
(2) editing the file alone changes the render after sync.
"""
import sys
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
def call(t, a):
    r = p.call(t, a); print(f"-- {t} ok={r.ok}: {(r.text or '')[:120].strip()}"); return r

SHADER_DIR = "C:/TD_builder_alpha/tests/glsl_eval/_scratch/live_build/shaders"
SHADER_FILE = SHADER_DIR + "/ext_ramp.glsl"

# v1 shader: blue-ish tint baked in (no uniform, keep it simple & deterministic)
V1 = """// EXTERNAL file shader v1
out vec4 fragColor;
void main(){
    vec2 uv=vUV.st; float r=length(uv-0.5);
    float ramp=0.5+0.5*sin(40.0*r);
    vec3 c=vec3(0.1, 0.2, 0.9)*ramp + 0.15*uv.x;
    fragColor=TDOutputSwizzle(vec4(c,1.0));
}"""
# v2: same structure, RED tint -> render mean must shift if file-sync works
V2 = V1.replace("vec3(0.1, 0.2, 0.9)", "vec3(0.9, 0.1, 0.1)").replace("v1", "v2")

import os
os.makedirs(SHADER_DIR, exist_ok=True)
open(SHADER_FILE, "w", encoding="utf-8").write(V1)
print("wrote v1 ->", SHADER_FILE)

# ensure a clean glsl TOP exists
call("execute_python_script", {"script":
    "h=op('/glsl_ex') or root\n"
    "x=op('/glsl_ex')\n"
    "print('glsl_ex exists:', bool(x))"})
call("create_td_node", {"parent_path": "/", "node_type": "baseCOMP", "node_name": "glsl_ex"})
call("create_td_node", {"parent_path": "/glsl_ex", "node_type": "glslTOP", "node_name": "ftest"})

probe_tpl = r'''
import numpy as np, collections
g=op('/glsl_ex/ftest'); pd=op(g.par.pixeldat.eval())
print("pixeldat dat:", pd.path if pd else None)
# point the pixel DAT at the external file, sync on, CLEAR cached text
pd.par.file = r"__FILE__"
pd.par.syncfile = True
pd.text = ""
try: pd.par.loadonstartpulse.pulse()
except Exception: pass
try: pd.par.refreshpulse.pulse()
except Exception:
    try: pd.par.loadfile.pulse()
    except Exception as e: print("no explicit reload pulse:", e)
g.cook(force=True)
print("DAT text now (first 60):", repr(pd.text[:60]))
print("DAT .par.file =", repr(pd.par.file.eval()), "syncfile=", pd.par.syncfile.eval())
print("WARN:", repr(g.warnings(recurse=False)))
a=np.asarray(g.numpyArray()); f=a.reshape(-1,a.shape[-1])
print("RENDER mean=", [round(float(x),3) for x in f.mean(0)])
'''

print("\n# --- load shader from external file (v1, blue) ---")
r = call("execute_python_script", {"script": probe_tpl.replace("__FILE__", SHADER_FILE)})
print((r.text or "").strip()[-700:])

# --- edit ONLY the file, re-sync, expect render to shift to red ---
open(SHADER_FILE, "w", encoding="utf-8").write(V2)
print("\n# --- rewrote file -> v2 (red); re-sync, expect mean shift ---")
r = call("execute_python_script", {"script": probe_tpl.replace("__FILE__", SHADER_FILE)})
print((r.text or "").strip()[-500:])
p.close()

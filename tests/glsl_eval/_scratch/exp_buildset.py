"""Can the BUILD-SCRIPT path (MCP update_td_node_parameters) set the GLSL TOP
Vectors sequence properly? Source-declared uTint ramp so the only variable is
whether the param tool drives the value. Strong red tint = unmistakable.
"""
import sys
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); OUT.append(s)
def call(t, a):
    r = p.call(t, a); log(f"-- {t} ok={r.ok} kind={r.error_kind}: {(r.text or '')[:160].strip()}"); return r

SH_SRC_DECL = """uniform vec3 uTint;
// circular ramp, uTint source-declared
out vec4 fragColor;
void main(){
    vec2 uv = vUV.st;
    float r = length(uv - 0.5);
    float ramp = 0.5 + 0.5*sin(40.0*r);
    vec3 c = uTint*ramp + 0.2*uv.x;
    fragColor = TDOutputSwizzle(vec4(c, 1.0));
}"""

READBACK = r'''
n=op('/glsl_ex/proc'); n.cook(force=True)
import numpy as np
a=np.asarray(n.numpyArray()); m=[round(float(x),3) for x in a.reshape(-1,a.shape[-1]).mean(0)]
print("numBlocks=%s vec0name=%r vec0=(%.3f,%.3f,%.3f) warn=%r rendermean=%s" % (
    n.seq.vec.numBlocks, n.par.vec0name.eval(),
    n.par.vec0valuex.eval(), n.par.vec0valuey.eval(), n.par.vec0valuez.eval(),
    bool(n.warnings(recurse=False)), m))
'''

# clean slate: source-declared shader, vec sequence emptied via seq API
call("execute_python_script", {"script":
    "op('/glsl_ex/proc_pixel').text=" + repr(SH_SRC_DECL) + "\n"
    "op('/glsl_ex/proc').seq.vec.numBlocks=0\n"
    "op('/glsl_ex/proc').cook(force=True)\nprint('reset done')"})
r = call("execute_python_script", {"script": READBACK})
log("BASELINE (vec emptied):", (r.text or "").split('```')[1].strip() if '```' in (r.text or '') else (r.text or '')[:200])

# TEST A: build-script tool ONLY, count+block in one call (red tint)
call("update_td_node_parameters", {"node_path": "/glsl_ex/proc", "properties": {
    "vec": 1, "vec0name": "uTint",
    "vec0valuex": 0.9, "vec0valuey": 0.05, "vec0valuez": 0.05}})
r = call("execute_python_script", {"script": READBACK})
log("TEST A (tool {vec:1, vec0*}):", (r.text or "").split('```')[1].strip() if '```' in (r.text or '') else (r.text or '')[:200])

# TEST B: tool, block params WITHOUT the 'vec' count key
call("execute_python_script", {"script": "op('/glsl_ex/proc').seq.vec.numBlocks=0\nprint('re-emptied')"})
call("update_td_node_parameters", {"node_path": "/glsl_ex/proc", "properties": {
    "vec0name": "uTint", "vec0valuex": 0.05, "vec0valuey": 0.9, "vec0valuez": 0.05}})
r = call("execute_python_script", {"script": READBACK})
log("TEST B (tool, no count key, green):", (r.text or "").split('```')[1].strip() if '```' in (r.text or '') else (r.text or '')[:200])

# TEST C: known-good seq API via execute_python_script (control)
call("execute_python_script", {"script":
    "n=op('/glsl_ex/proc')\nn.seq.vec.numBlocks=1\n"
    "n.par.vec0name='uTint'; n.par.vec0valuex=0.05; n.par.vec0valuey=0.05; n.par.vec0valuez=0.9\n"
    "n.cook(force=True)\nprint('seq api set')"})
r = call("execute_python_script", {"script": READBACK})
log("TEST C (seq API, blue, control):", (r.text or "").split('```')[1].strip() if '```' in (r.text or '') else (r.text or '')[:200])

with open("tests/glsl_eval/_scratch/buildset_out.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT))
p.close()

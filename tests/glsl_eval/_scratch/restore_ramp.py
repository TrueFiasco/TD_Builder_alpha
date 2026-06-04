"""Restore the circular-ramp shader (uses uTint, NO source decl) + Vectors
page entry, so the user can double-check uniform-declaration behaviour in the
TD UI. Report the exact live state.
"""
import sys
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
def call(t, a): return p.call(t, a)

SH_NO_DECL = """// circular ramp -- uses uTint, NOT declared in source
out vec4 fragColor;
void main(){
    vec2 uv = vUV.st;
    float r = length(uv - 0.5);
    float ramp = 0.5 + 0.5*sin(40.0*r);
    vec3 c = uTint*ramp + 0.2*uv.x;
    fragColor = TDOutputSwizzle(vec4(c, 1.0));
}"""

call("execute_python_script", {"script": "op('/glsl_ex/proc_pixel').text=" + repr(SH_NO_DECL)})
call("update_td_node_parameters", {"node_path": "/glsl_ex/proc",
     "properties": {"vec": 1, "vec0name": "uTint",
                    "vec0valuex": 0.2, "vec0valuey": 0.6, "vec0valuez": 0.9,
                    "loaduniformnames": 0}})

report = r'''
n=op('/glsl_ex/proc'); n.cook(force=True)
d=op('/glsl_ex/proc_pixel')
print("PIXEL_DAT (/glsl_ex/proc_pixel):")
print(d.text)
print("---")
print("Vectors page: vec=%s vec0name=%r vec0=(%.2f,%.2f,%.2f)" % (
    n.par.vec.eval(), n.par.vec0name.eval(),
    n.par.vec0valuex.eval(), n.par.vec0valuey.eval(), n.par.vec0valuez.eval()))
print("WARNINGS:", repr(n.warnings(recurse=False)))
idat=op('/glsl_ex/proc_info'); idat.cook(force=True)
print("INFO DAT (/glsl_ex/proc_info):")
print("\n".join(" ".join(c.val for c in row) for row in idat.rows()))
import numpy as np, collections
a=np.asarray(n.numpyArray()); f=a.reshape(-1,a.shape[-1])
cols=collections.Counter(map(tuple,(f[:,:3]*8).round().astype(int).tolist()))
print("RENDER mean=%s uniq8=%d  (2-colour red/blue == error checkerboard)" % (
    [round(float(x),3) for x in f.mean(0)], len(cols)))
'''
r = call("execute_python_script", {"script": report})
print((r.text or "").strip())
p.close()

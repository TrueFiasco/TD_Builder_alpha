"""Does loaduniformnames=true let the Vectors page auto-declare the uniform
(page-only, no source decl)? Also capture clean valid vs checkerboard sigs.
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
def call(t, a): return p.call(t, a)

SH_NO_DECL = """// uTint NOT declared in source
out vec4 fragColor;
void main(){
    vec2 uv=vUV.st; float r=length(uv-0.5);
    vec3 c=uTint*(0.5+0.5*sin(40.0*r))+0.2*uv.x;
    fragColor=TDOutputSwizzle(vec4(c,1.0));
}"""
SH_SRC_DECL = "uniform vec3 uTint;\n" + SH_NO_DECL

READ = r'''
n=op('/glsl_ex/proc'); n.cook(force=True)
import numpy as np, collections
idat=op('/glsl_ex/proc_info'); idat.cook(force=True)
info=" / ".join(c.val for r in idat.rows() for c in r)[:300]
a=np.asarray(n.numpyArray()); f=a.reshape(-1,a.shape[-1])
cols=collections.Counter(map(tuple,(f[:,:3]*8).round().astype(int).tolist()))
print("WARN=", repr(n.warnings(recurse=False))[:160])
print("INFO=", info)
print("STATS mean",[round(float(x),3) for x in f.mean(0)],
      "std",[round(float(x),3) for x in f.std(0)],
      "uniq8",len(cols),"top2",cols.most_common(2))
'''
def step(tag, sh, props):
    call("execute_python_script", {"script": "op('/glsl_ex/proc_pixel').text=" + repr(sh)})
    call("update_td_node_parameters", {"node_path": "/glsl_ex/proc", "properties": props})
    r = call("execute_python_script", {"script": READ})
    body = (r.text or "")
    i = body.find("WARN=")
    log("\n===== %s =====" % tag)
    log(body[i:i + 700].strip() if i >= 0 else body[:700].strip())

# A: page-only + loaduniformnames OFF (control = known fail)
step("A page-only, loaduniformnames=0",
     SH_NO_DECL, {"vec": 1, "vec0name": "uTint", "vec0valuex": 0.2,
                  "vec0valuey": 0.6, "vec0valuez": 0.9, "loaduniformnames": 0})
# B: page-only + loaduniformnames ON  (does the user's model work with this?)
step("B page-only, loaduniformnames=1",
     SH_NO_DECL, {"vec": 1, "vec0name": "uTint", "loaduniformnames": 1})
# C: canonical working ref: source-declared + page supplies value
step("C source-decl + page value (canonical)",
     SH_SRC_DECL, {"vec": 1, "vec0name": "uTint", "vec0valuex": 0.2,
                   "vec0valuey": 0.6, "vec0valuez": 0.9, "loaduniformnames": 0})

with open("tests/glsl_eval/_scratch/loaduni_out.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT))
p.close()

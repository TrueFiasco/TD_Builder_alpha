"""Build-first empirical probe (v2): authoritative compile-error read +
force-cook + full output to file. No assertions from memory.
"""
import sys
sys.path.insert(0, "tests")
sys.path.insert(0, ".")
sys.path.insert(0, "tests/measure")
import bootstrap  # noqa: E402
bootstrap.setup()
from _server import load_server  # noqa: E402
from probe import Probe  # noqa: E402

p = Probe(load_server())
OUT = []


def log(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


def call(tool, args):
    return p.call(tool, args)


def set_pixel(text):
    call("execute_python_script",
         {"script": "op('/glsl_ex/proc_pixel').text = " + repr(text)})


def set_params(props):
    call("update_td_node_parameters",
         {"node_path": "/glsl_ex/proc", "properties": props})


def observe(tag):
    s = (
        "import numpy as np, collections\n"
        "n=op('/glsl_ex/proc')\n"
        "n.cook(force=True)\n"
        "err=n.errors(recurse=False)\n"
        "print('ERRORS', repr(err[:400]))\n"
        "a=np.asarray(n.numpyArray())\n"
        "f=a.reshape(-1,a.shape[-1])\n"
        "cols=collections.Counter(map(tuple,(f[:,:3]*8).round().astype(int).tolist()))\n"
        "print('STATS mean',[round(float(x),3) for x in f.mean(0)],"
        "'std',[round(float(x),3) for x in f.std(0)],"
        "'uniq8',len(cols),'top3',cols.most_common(3))\n"
    )
    r = call("execute_python_script", {"script": s})
    log(f"\n===== {tag} =====")
    log("OBSERVE:", (r.text or "").strip()[:1100])


SH_NO_DECL = """// procedural, uTint NOT declared in source
out vec4 fragColor;
void main(){
    vec2 uv = vUV.st;
    float r = length(uv-0.5);
    float ring = 0.5+0.5*sin(40.0*r);
    vec3 c = uTint * ring + 0.2*uv.x;
    fragColor = TDOutputSwizzle(vec4(c,1.0));
}"""

SH_SRC_DECL = """// procedural, uTint DECLARED in source
uniform vec3 uTint;
out vec4 fragColor;
void main(){
    vec2 uv = vUV.st;
    float r = length(uv-0.5);
    float ring = 0.5+0.5*sin(40.0*r);
    vec3 c = uTint * ring + 0.2*uv.x;
    fragColor = TDOutputSwizzle(vec4(c,1.0));
}"""

SH_VERSION = """#version 330
out vec4 fragColor;
void main(){ fragColor = TDOutputSwizzle(vec4(vUV.st,0.0,1.0)); }"""

SH_PLAIN = """// no uniforms at all, pure procedural
out vec4 fragColor;
void main(){
    vec2 uv=vUV.st; float r=length(uv-0.5);
    vec3 c=vec3(0.5+0.5*sin(40.0*r), uv.x, uv.y);
    fragColor=TDOutputSwizzle(vec4(c,1.0));
}"""

log("# baseline: plain procedural, zero uniforms")
set_params({"vec": 0})
set_pixel(SH_PLAIN)
observe("B0 plain procedural (no uniforms)")

log("\n# T1: page-only binding, NO source decl")
set_params({"vec": 1, "vec0name": "uTint",
            "vec0valuex": 0.2, "vec0valuey": 0.6, "vec0valuez": 0.9})
set_pixel(SH_NO_DECL)
observe("T1 page-only, no source decl, tint=(.2,.6,.9)")

log("\n# T1b: same, change value -> does render change?")
set_params({"vec0valuex": 0.95, "vec0valuey": 0.05, "vec0valuez": 0.05})
observe("T1b page-only, tint=(.95,.05,.05)")

log("\n# T2: BOTH source decl + page entry")
set_pixel(SH_SRC_DECL)
observe("T2 source-decl + page entry both")

log("\n# T3: source-decl only, page removed")
set_params({"vec": 0})
set_pixel(SH_SRC_DECL)
observe("T3 source-decl only, vec=0")

log("\n# T5: user #version 330")
set_pixel(SH_VERSION)
observe("T5 user #version 330")

with open("tests/glsl_eval/_scratch/out.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT))
p.close()
print("\n[written tests/glsl_eval/_scratch/out.txt]")

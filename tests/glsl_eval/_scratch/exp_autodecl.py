"""Decisive, user-fair test: does adding a Vectors-page entry cause TD to
auto-insert `uniform vec3 uTint;` into the shader DAT itself?

Start from a shader with NO uTint usage and NO decl. Add the page entry.
Re-read the DAT text. If TD injected the declaration -> the user's
"just set the parameter" model is correct (UI/param side writes the decl).
If the DAT is unchanged -> the decl must be authored in source.
"""
import sys
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
OUT = []
def log(*a): OUT.append(" ".join(str(x) for x in a))
def call(t, a): return p.call(t, a)

SH_CLEAN = """// no uTint anywhere
out vec4 fragColor;
void main(){
    vec2 uv=vUV.st;
    fragColor=TDOutputSwizzle(vec4(uv,0.0,1.0));
}"""

call("execute_python_script", {"script": "op('/glsl_ex/proc_pixel').text=" + repr(SH_CLEAN)})
# reset page
call("update_td_node_parameters", {"node_path": "/glsl_ex/proc", "properties": {"vec": 0}})
r0 = call("execute_python_script", {"script": "print('BEFORE_LEN', len(op('/glsl_ex/proc_pixel').text)); print('HAS_UNIFORM', 'uniform' in op('/glsl_ex/proc_pixel').text)"})
log("STEP0 (clean shader, vec=0):"); log((r0.text or "").split('```')[1] if '```' in (r0.text or '') else (r0.text or "")[:300])

# now add the Vectors page entry named uTint via param API
call("update_td_node_parameters", {"node_path": "/glsl_ex/proc",
     "properties": {"vec": 1, "vec0name": "uTint",
                    "vec0valuex": 0.2, "vec0valuey": 0.6, "vec0valuez": 0.9}})
r1 = call("execute_python_script", {"script":
    "d=op('/glsl_ex/proc_pixel')\n"
    "print('AFTER_LEN', len(d.text))\n"
    "print('HAS_UNIFORM_LINE', 'uniform' in d.text)\n"
    "print('DAT_TEXT_BEGIN'); print(d.text); print('DAT_TEXT_END')\n"
    "n=op('/glsl_ex/proc'); n.cook(force=True)\n"
    "print('WARN', repr(n.warnings(recurse=False))[:150])"})
log("\nSTEP1 (after adding Vectors entry 'uTint' via API):")
log((r1.text or "").strip()[:1200])

with open("tests/glsl_eval/_scratch/autodecl_out.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT))
p.close()

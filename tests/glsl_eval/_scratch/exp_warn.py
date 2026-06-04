"""Where does the GLSL TOP compile log live? (abs paths, MCP-created info DAT)"""
import sys
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); OUT.append(s); print(s)
def call(t, a):
    r = p.call(t, a); log(f"-- {t} ok={r.ok}"); return r

SH_NO_DECL = """// uTint NOT declared in source
out vec4 fragColor;
void main(){
    vec2 uv=vUV.st; float r=length(uv-0.5);
    vec3 c=uTint*(0.5+0.5*sin(40.0*r))+0.2*uv.x;
    fragColor=TDOutputSwizzle(vec4(c,1.0));
}"""

call("execute_python_script", {"script": "op('/glsl_ex/proc_pixel').text=" + repr(SH_NO_DECL)})
call("update_td_node_parameters", {"node_path": "/glsl_ex/proc",
     "properties": {"vec": 1, "vec0name": "uTint",
                    "vec0valuex": 0.2, "vec0valuey": 0.6, "vec0valuez": 0.9}})
call("create_td_node", {"parent_path": "/glsl_ex", "node_type": "infoDAT", "node_name": "proc_info"})
call("update_td_node_parameters", {"node_path": "/glsl_ex/proc_info",
     "properties": {"op": "/glsl_ex/proc"}})

probe_script = r'''
n=op('/glsl_ex/proc')
n.cook(force=True)
print("ERRORS=", repr(n.errors(recurse=False)))
print("WARNINGS=", repr(n.warnings(recurse=False)))
idat=op('/glsl_ex/proc_info')
idat.cook(force=True)
print("INFO_DAT (%d rows):" % idat.numRows)
for row in idat.rows():
    print("  " + " | ".join(c.val for c in row))
'''
r = call("execute_python_script", {"script": probe_script})
log("PROBE:\n" + (r.text or "").strip()[:1800])

with open("tests/glsl_eval/_scratch/warn_out.txt", "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT))
p.close()

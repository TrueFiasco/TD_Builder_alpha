"""Import via the EXTERNAL-COMPONENT mechanism (externaltox + enableexternaltox
+ pulse) -- the real method the user uses. butterfly.tox = positive control,
glslx.tox = the rebuilt corrected offline tox. Same method for both.
"""
import sys
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
def call(t, a):
    r = p.call(t, a); return r

cases = {
    "CONTROL_butterfly": "C:/TD_Projects/butterfly/butterfly.tox",
    "MINE_glslx":        "C:/TD_builder_alpha/tests/glsl_eval/_scratch/offline_v2/glslx.tox",
}

for name, tox in cases.items():
    call("execute_python_script", {"script":
        f"x=op('/glsl_ex/{name}')\nif x: x.destroy()\nprint('cleared')"})
    call("create_td_node", {"parent_path": "/glsl_ex", "node_type": "baseCOMP", "node_name": name})
    s = r'''
c=op("/glsl_ex/__N__")
c.par.externaltox = r"__T__"
c.par.enableexternaltox = True
try: c.par.enableexternaltoxpulse.pulse()
except Exception as e: print("pulse err", e)
c.cook(force=True)
kids=c.findChildren(depth=4)
print("[__N__] child count:", len(kids))
for k in kids[:12]: print("   ", k.path, "(", k.family, "/", k.type, ")")
print("[__N__] warnings:", repr(c.warnings(recurse=True))[:320])
print("[__N__] errors  :", repr(c.errors(recurse=True))[:200])
'''.replace("__N__", name).replace("__T__", tox)
    r = call("execute_python_script", {"script": s})
    body = (r.text or "")
    i = body.find(f"[{name}] child count")
    print(f"\n===== {name} =====")
    print(body[i:i+900].strip() if i >= 0 else body[:600].strip())

p.close()

"""Import the corrected offline tox; confirm children load (no 'missing parent')."""
import sys
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
def call(t, a):
    r = p.call(t, a); print(f"-- {t} ok={r.ok}: {(r.text or '')[:90].strip()}"); return r

TOX = "C:/TD_builder_alpha/tests/glsl_eval/_scratch/offline_v2/glslx.tox"
call("create_td_node", {"parent_path": "/", "node_type": "baseCOMP", "node_name": "glsl_ex"})
call("execute_python_script", {"script": "x=op('/glsl_ex/imp2')\nif x: x.destroy()\nprint('cleared')"})
call("create_td_node", {"parent_path": "/glsl_ex", "node_type": "baseCOMP", "node_name": "imp2"})

s = r'''
imp=op('/glsl_ex/imp2')
imp.loadTox(r"__TOX__")
imp.cook(force=True)
kids=imp.findChildren(depth=4)
print("CHILD COUNT:", len(kids))
for c in kids: print("  ", c.path, "(", c.family, "/", c.type, ")")
print("imp.warnings:", repr(imp.warnings(recurse=True))[:300])
g=None
for c in kids:
    if c.family=='TOP' and 'glsl' in c.type.lower(): g=c; break
if g:
    g.cook(force=True)
    print("GLSL warnings:", repr(g.warnings(recurse=True))[:200])
    sd=op(g.par.pixeldat.eval()) if g.par.pixeldat.eval() else None
    print("shader dat:", sd.path if sd else None, "textlen:", len(sd.text) if sd else 0)
'''.replace("__TOX__", TOX)
r = call("execute_python_script", {"script": s})
print("\n" + (r.text or "").strip()[-900:])
p.close()

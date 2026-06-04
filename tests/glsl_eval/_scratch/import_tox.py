"""Import the path-B collapsed .tox into live TD and observe everything.
loadTox() loads INTO a COMP (returns None) -> make /glsl_ex/imp, load into
it, then introspect that subtree.
"""
import sys
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
def call(t, a):
    r = p.call(t, a); print(f"-- {t} ok={r.ok}: {(r.text or '')[:120].strip()}"); return r

TOX = "C:/TD_builder_alpha/tests/glsl_eval/_scratch/offline_build/top_vector_param.tox"

# fresh target comp via the build tool
call("execute_python_script", {"script":
    "h=op('/glsl_ex')\nx=h.op('imp')\n"
    "\nif x: x.destroy()\nprint('cleared old imp:', x)"})
call("create_td_node", {"parent_path": "/glsl_ex", "node_type": "baseCOMP", "node_name": "imp"})

script = r'''
import numpy as np, collections
imp = op('/glsl_ex/imp')
imp.loadTox(r"__TOXPATH__")
imp.cook(force=True)
kids = imp.findChildren(depth=4)
print("IMP children (%d):" % len(kids))
for c in kids:
    print("  ", c.path, "(", c.family, "/", c.type, ")")
glsl = None
for c in kids:
    if c.family == 'TOP' and 'glsl' in c.type.lower():
        glsl = c; break
print("GLSL_OP:", glsl.path if glsl else None)
if glsl:
    glsl.cook(force=True)
    pd = glsl.par.pixeldat.eval()
    print("pixeldat par =", repr(pd))
    sdat = op(pd) if pd else None
    if sdat is None and glsl.parent():
        sdat = glsl.parent().op(pd) if pd else None
    print("SHADER_DAT:", sdat.path if sdat else None)
    if sdat:
        print("SHADER_TEXT_BEGIN"); print(sdat.text); print("SHADER_TEXT_END")
    print("WARNINGS:", repr(glsl.warnings(recurse=False)))
    print("ERRORS:", repr(glsl.errors(recurse=False)))
    try:
        a = np.asarray(glsl.numpyArray()); f = a.reshape(-1, a.shape[-1])
        cols = collections.Counter(map(tuple, (f[:, :3]*8).round().astype(int).tolist()))
        print("RENDER mean=", [round(float(x), 3) for x in f.mean(0)],
              "uniq8=", len(cols), "(2-colour red/blue == error checkerboard)")
    except Exception as e:
        print("RENDER read failed:", e)
'''.replace("__TOXPATH__", TOX)

r = call("execute_python_script", {"script": script})
print(); print((r.text or "").strip())
p.close()

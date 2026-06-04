"""Properly check ALL warning sources when loading a shader from an external
file (load-only: syncfile OFF, loadonstart ON, never write the DAT).
"""
import sys
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
def call(t, a):
    r = p.call(t, a); print(f"-- {t} ok={r.ok}: {(r.text or '')[:90].strip()}"); return r

SF = "C:/TD_builder_alpha/tests/glsl_eval/_scratch/live_build/shaders/ext_ramp.glsl"

call("create_td_node", {"parent_path": "/", "node_type": "baseCOMP", "node_name": "glsl_ex"})
call("create_td_node", {"parent_path": "/glsl_ex", "node_type": "glslTOP", "node_name": "ftest"})

script = r'''
g  = op('/glsl_ex/ftest')
d  = op('/glsl_ex/ftest_pixel')
import os
print("FILE on disk:", os.path.exists(r"__SF__"), os.path.getsize(r"__SF__"), "bytes")

# load-only: syncfile OFF, loadonstart ON, do NOT write d.text
d.par.file = r"__SF__"
d.par.syncfile = False
d.par.loadonstart = True
d.par.loadonstartpulse.pulse()
d.cook(force=True)
g.cook(force=True)

print("DAT.text len:", len(d.text), "| first line:", repr(d.text.splitlines()[0] if d.text else ""))
print("DAT  warnings:", repr(d.warnings(recurse=False)))
print("DAT  errors  :", repr(d.errors(recurse=False)))
print("TOP  warnings:", repr(g.warnings(recurse=True)))
print("TOP  errors  :", repr(g.errors(recurse=True)))
print("COMP warnings:", repr(op('/glsl_ex').warnings(recurse=True)))
import numpy as np
a=np.asarray(g.numpyArray()); m=[round(float(x),3) for x in a.reshape(-1,a.shape[-1]).mean(0)]
print("RENDER mean:", m)
'''.replace("__SF__", SF)

r = call("execute_python_script", {"script": script})
print("\n" + (r.text or "").strip()[-1100:])
p.close()

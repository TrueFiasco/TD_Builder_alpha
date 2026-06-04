"""Minimal correct external-file load: set file, pulse loadonstartpulse, cook.
Then edit file + re-pulse -> render must change. Confirms 'shader = a file'.
"""
import sys, os
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
def call(t, a):
    r = p.call(t, a); print(f"-- {t} ok={r.ok}: {(r.text or '')[:90].strip()}"); return r

SF = "C:/TD_builder_alpha/tests/glsl_eval/_scratch/live_build/shaders/ext_ramp.glsl"
V1 = """// ext file v1 BLUE
out vec4 fragColor;
void main(){ vec2 uv=vUV.st; float r=length(uv-0.5);
 float a=0.5+0.5*sin(40.0*r);
 fragColor=TDOutputSwizzle(vec4(vec3(0.1,0.2,0.9)*a+0.15*uv.x,1.0)); }"""
V2 = """// ext file v2 RED
out vec4 fragColor;
void main(){ vec2 uv=vUV.st; float r=length(uv-0.5);
 float a=0.5+0.5*sin(40.0*r);
 fragColor=TDOutputSwizzle(vec4(vec3(0.9,0.1,0.1)*a+0.15*uv.x,1.0)); }"""

os.makedirs(os.path.dirname(SF), exist_ok=True)
open(SF, "w", encoding="utf-8").write(V1)

READ = r'''
g=op('/glsl_ex/ftest'); d=op('/glsl_ex/ftest_pixel')
d.par.file = r"__SF__"
d.par.syncfile = True
d.par.loadonstart = True
d.par.loadonstartpulse.pulse()
g.cook(force=True)
import numpy as np
a=np.asarray(g.numpyArray()); m=[round(float(x),3) for x in a.reshape(-1,a.shape[-1]).mean(0)]
print("textlen=%d first=%r warn=%r mean=%s" % (
    len(d.text), d.text.splitlines()[0] if d.text else "", bool(g.warnings(recurse=False)), m))
'''

print("# v1 (blue) from external file:")
print(call("execute_python_script", {"script": READ.replace("__SF__", SF)}).text.strip()[-260:])

open(SF, "w", encoding="utf-8").write(V2)
print("\n# rewrote file -> v2 (red); re-pulse load:")
print(call("execute_python_script", {"script": READ.replace("__SF__", SF)}).text.strip()[-260:])

# also: does it survive with syncfile ON but text cache cleared & only loadonstart?
print("\n# clear cached text, rely on loadonstart only, recook:")
chk = r'''
g=op('/glsl_ex/ftest'); d=op('/glsl_ex/ftest_pixel')
d.text=""
d.par.loadonstartpulse.pulse()
g.cook(force=True)
import numpy as np
a=np.asarray(g.numpyArray()); m=[round(float(x),3) for x in a.reshape(-1,a.shape[-1]).mean(0)]
print("after clear+reload textlen=%d warn=%r mean=%s" % (len(d.text), bool(g.warnings(recurse=False)), m))
'''
print(call("execute_python_script", {"script": chk}).text.strip()[-200:])
p.close()

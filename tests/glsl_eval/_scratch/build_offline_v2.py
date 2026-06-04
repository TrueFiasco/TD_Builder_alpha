"""CORRECTED offline build: add the root container COMP operator the way the
working butterfly build does (name == root_comp, parent=None). Then collapse
and import into live TD to verify it round-trips (no 'missing parent').
"""
import sys, shutil, subprocess
from pathlib import Path

US = Path("C:/TD_builder_alpha/unified_system")
sys.path.insert(0, str(US))
from api.network_builder import NetworkBuilder

OUT = Path("C:/TD_builder_alpha/tests/glsl_eval/_scratch/offline_v2")
if OUT.exists(): shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

SHADER = """uniform vec3 uTint;
out vec4 fragColor;
void main(){
    vec2 uv = vUV.st;
    float r = length(uv - 0.5);
    float ramp = 0.5 + 0.5*sin(40.0*r);
    fragColor = TDOutputSwizzle(vec4(uTint*ramp + 0.2*uv.x, 1.0));
}"""

b = NetworkBuilder("glslx", mode="tox", root_comp="glslx")
b.add_operator("glslx", "COMP", "base", parent=None)              # <-- ROOT CONTAINER (the missing piece)
b.add_operator("shader", "DAT", "text", parent="glslx")
b.add_operator("glsl1", "TOP", "glsl", parent="glslx")
b.add_operator("out1", "TOP", "null", parent="glslx")
b.set_text("shader", SHADER)
for k, v in [("pixeldat", "shader"), ("vec0name", "uTint")]:
    try: b.set_parameter("glsl1", k, v)
    except Exception as e: print("param drop", k, e)
b.connect("glsl1", "out1")

rep = b.validate()
print("validate: valid=%s errors=%s" % (rep.valid, rep.total_errors))
toc = Path(b.build_tox(OUT / "glslx.tox", verbose=False))
print("TOC entries:", toc.read_text().splitlines())

# collapse with the running-TD-matched toecollapse
TC = r"C:/Program Files/Derivative/TouchDesigner/bin/toecollapse.exe"
subprocess.run([TC, str(toc)], cwd=str(OUT), check=False)
tox = OUT / "glslx.tox"
print("collapsed tox exists:", tox.exists(), tox.stat().st_size if tox.exists() else "-", "bytes")

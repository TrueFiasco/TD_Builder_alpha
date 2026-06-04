"""PATH B (offline, from-scratch): build top_vector_param .tox via the
unified_system NetworkBuilder + TOEBuilder, with NO live TD.

Goal: produce the .tox.toc + .tox.dir and SHOW exactly what the offline build
script emits. This is the historically-weak BASIC builder path (the thing the
agent-under-test would use), so its limitations are the point — we observe,
we don't paper over.

Encodes the live-VERIFIED top_vector_param pattern:
  - Text DAT 'shader' = source-declared `uniform vec3 uTint;` circular ramp
  - GLSL TOP 'glsl1' with pixeldat -> shader, Vectors block0 uTint=(.2,.6,.9)
  - Null TOP 'out1'  (glsl1 -> out1)
"""
import sys, json, shutil
from pathlib import Path

US = Path("C:/TD_builder_alpha/unified_system")
sys.path.insert(0, str(US))

from api.network_builder import NetworkBuilder  # noqa: E402

OUT = Path("C:/TD_builder_alpha/tests/glsl_eval/_scratch/offline_build")
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

SHADER = """uniform vec3 uTint;
// circular ramp (live-verified working pattern)
out vec4 fragColor;
void main(){
    vec2 uv = vUV.st;
    float r = length(uv - 0.5);
    float ramp = 0.5 + 0.5*sin(40.0*r);
    vec3 c = uTint*ramp + 0.2*uv.x;
    fragColor = TDOutputSwizzle(vec4(c, 1.0));
}"""

log = []
def show(*a):
    s = " ".join(str(x) for x in a); print(s); log.append(s)

b = NetworkBuilder("top_vector_param", mode="tox")

# --- operators ---
b.add_operator("shader", "DAT", "text")
b.add_operator("glsl1", "TOP", "glsl")
b.add_operator("out1", "TOP", "null")

# --- DAT text (the GLSL source) ---
b.set_text("shader", SHADER)

# --- params: set defensively so we SEE which the offline path accepts ---
def tryset(op, p, v):
    try:
        b.set_parameter(op, p, v)
        show(f"  set_parameter OK   {op}.{p} = {v!r}")
    except Exception as e:
        show(f"  set_parameter DROP {op}.{p}: {type(e).__name__}: {e}")

show("== setting GLSL TOP params (offline registry-validated) ==")
tryset("glsl1", "pixeldat", "/project1/shader")
tryset("glsl1", "vec0name", "uTint")
tryset("glsl1", "vec0valuex", 0.2)
tryset("glsl1", "vec0valuey", 0.6)
tryset("glsl1", "vec0valuez", 0.9)

# --- connect ---
b.connect("glsl1", "out1")

# --- the builder-format network JSON (the spec) ---
spec = b.to_json("builder")
(OUT / "network.builder.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
show("\n== builder network JSON ==")
show(json.dumps(spec, indent=2)[:1400])

# --- validate ---
rep = b.validate()
show(f"\n== validation: valid={rep.valid} errors={rep.total_errors} warnings={rep.total_warnings} ==")
for e in rep.get_errors()[:8]:
    show(f"  ERR [{e.stage}] {e.message}")

# --- build the .tox (emits .tox.dir/ + .tox.toc) ---
show("\n== build_tox ==")
try:
    toc = b.build_tox(OUT / "top_vector_param.tox", verbose=True)
    show("toc file:", toc)
except Exception as e:
    import traceback
    show("BUILD FAILED:", type(e).__name__, e)
    show(traceback.format_exc()[:1500])

(OUT / "build_log.txt").write_text("\n".join(log), encoding="utf-8")
print("\n[done] artifacts in", OUT)

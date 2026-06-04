"""Re-test the GLSL TOP uniform mechanic with the Vectors sequence ACTUALLY
activated via the seq API (prior tests were confounded: vec count stayed 0).
Test page-only (no source decl) properly, then source-decl, for contrast.
Leave it in the circular-ramp state for the user to eyeball in the UI.
"""
import sys
sys.path.insert(0, "tests"); sys.path.insert(0, "."); sys.path.insert(0, "tests/measure")
import bootstrap; bootstrap.setup()
from _server import load_server
from probe import Probe

p = Probe(load_server())
def call(t, a): return p.call(t, a)

SH_NO_DECL = """// circular ramp -- uses uTint, NOT declared in source
out vec4 fragColor;
void main(){
    vec2 uv = vUV.st;
    float r = length(uv - 0.5);
    float ramp = 0.5 + 0.5*sin(40.0*r);
    vec3 c = uTint*ramp + 0.2*uv.x;
    fragColor = TDOutputSwizzle(vec4(c, 1.0));
}"""
SH_SRC_DECL = "uniform vec3 uTint;\n" + SH_NO_DECL


def scenario(tag, shader):
    set_and_read = (
        "n=op('/glsl_ex/proc')\n"
        "op('/glsl_ex/proc_pixel').text=" + repr(shader) + "\n"
        # activate the Vectors sequence PROPERLY
        "n.seq.vec.numBlocks = 1\n"
        "n.par.vec0name = 'uTint'\n"
        "n.par.vec0valuex = 0.2; n.par.vec0valuey = 0.6; n.par.vec0valuez = 0.9\n"
        "n.cook(force=True)\n"
        "print('SEQ numBlocks =', n.seq.vec.numBlocks, '| vec0name =', repr(n.par.vec0name.eval()))\n"
        "print('WARNINGS =', repr(n.warnings(recurse=False)))\n"
        "idat=op('/glsl_ex/proc_info'); idat.cook(force=True)\n"
        "ix=idat.text.find('Pixel Shader')\n"
        "print('PIXEL_COMPILE:', idat.text[ix:ix+160].strip())\n"
        "import numpy as np, collections\n"
        "a=np.asarray(n.numpyArray()); f=a.reshape(-1,a.shape[-1])\n"
        "cols=collections.Counter(map(tuple,(f[:,:3]*8).round().astype(int).tolist()))\n"
        "print('RENDER mean=%s uniq8=%d' % ([round(float(x),3) for x in f.mean(0)], len(cols)))\n"
    )
    r = call("execute_python_script", {"script": set_and_read})
    body = (r.text or "")
    i = body.find("SEQ numBlocks")
    print("\n===== %s =====" % tag)
    print(body[i:i + 600].strip() if i >= 0 else body[:600].strip())


scenario("PAGE-ONLY, no source decl (seq properly active)", SH_NO_DECL)
scenario("SOURCE-DECL + page value (seq properly active)", SH_SRC_DECL)

# leave it in the circular-ramp state the user asked to eyeball:
call("execute_python_script", {"script":
    "n=op('/glsl_ex/proc')\n"
    "op('/glsl_ex/proc_pixel').text=" + repr(SH_NO_DECL) + "\n"
    "n.seq.vec.numBlocks = 1\n"
    "n.par.vec0name='uTint'; n.par.vec0valuex=0.2; n.par.vec0valuey=0.6; n.par.vec0valuez=0.9\n"
    "n.cook(force=True)\n"
    "print('LEFT STATE: /glsl_ex/proc, circular ramp, NO source decl, Vectors seq active (1 block uTint).')"})
p.close()

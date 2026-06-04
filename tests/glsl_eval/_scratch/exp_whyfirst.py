"""Why did THIS build fail when prior offline builds presumably didn't?
Test two hypotheses by inspecting .toc structure:
  H1: .toe (project) vs .tox (component) emit the root differently
  H2: builder only emits a root node if the spec explicitly includes it
"""
import sys, shutil
from pathlib import Path
US = Path("C:/TD_builder_alpha/unified_system")
sys.path.insert(0, str(US))
from api.network_builder import NetworkBuilder

OUT = Path("C:/TD_builder_alpha/tests/glsl_eval/_scratch/whyfirst")
if OUT.exists(): shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

SH = "uniform vec3 uTint;\nout vec4 fragColor;\nvoid main(){ fragColor=TDOutputSwizzle(vec4(uTint,1.0)); }"

def build(tag, mode, with_root):
    b = NetworkBuilder("project1", mode=mode)
    if with_root:
        # explicitly add the root container as an operator
        try:
            b.add_operator("project1", "COMP", "base", parent="/")
            root_added = "OK"
        except Exception as e:
            root_added = f"FAILED: {e}"
    else:
        root_added = "n/a (not attempted)"
    b.add_operator("shader", "DAT", "text")
    b.add_operator("glsl1", "TOP", "glsl")
    b.add_operator("out1", "TOP", "null")
    b.set_text("shader", SH)
    try: b.set_parameter("glsl1", "pixeldat", "shader")
    except Exception: pass
    b.connect("glsl1", "out1")
    outp = OUT / f"{tag}.{ 'toe' if mode=='toe' else 'tox' }"
    try:
        if mode == "toe":
            toc = b.build_toe(outp, verbose=False)
        else:
            toc = b.build_tox(outp, verbose=False)
        toc = Path(toc)
        entries = toc.read_text(encoding="utf-8", errors="replace").splitlines()
        # is there a root node file (first path segment defines itself)?
        roots = sorted({e.split("/")[0] for e in entries if e and not e.startswith("#") and e != ".build"})
        has_rootnode = any(e in (f"{r}.n" for r in roots) for e in entries)
        print(f"\n### {tag}  mode={mode} with_root={with_root}  (root_added={root_added})")
        print("   toc:", entries)
        print("   distinct top segments:", roots)
        print("   contains a '<root>.n' node file? ->", has_rootnode)
    except Exception as e:
        print(f"\n### {tag} mode={mode} with_root={with_root}: BUILD ERROR {type(e).__name__}: {e}")

build("toe_noroot",  "toe", False)
build("tox_noroot",  "tox", False)
build("toe_withroot","toe", True)
build("tox_withroot","tox", True)

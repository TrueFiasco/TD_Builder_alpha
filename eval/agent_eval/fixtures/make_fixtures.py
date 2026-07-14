#!/usr/bin/env python3
r"""Generate the agent-eval fixtures with ToxBuilder itself (design §3).

Self-hosted, no binaries committed: only this generator is in git; the .tox it
emits lands in fixtures/generated/ (gitignored) and is (re)built at setup by
run_agent_eval.py. Owner decision D-D dropped the wrapper-mimic fixture from
scope — s11 runs against the REAL Derivative bloom.tox on machines that have a
TouchDesigner install (resolved by the runner, auto-SKIP elsewhere; Derivative
content is never staged into the repo).

text.tox — a trivial working comp whose FILENAME is the trap ("text." contains
the "ext." substring that regression a2ce003 used to promote into a mode-49
Python expression, silently breaking the external reference). Inner interface:
an LFO CHOP into an Out CHOP, so consumers can wire `textref/out1`.

eval_fragment.glsl — a minimal KNOWN-GOOD TD pixel shader for s17 (the
W-A2 file-sync drill): input-free on purpose (sTD2DInputs[0] with no wired
input is itself a compile error, which would poison the "starts clean"
premise). vUV is always available in a TD pixel shader.
"""

from __future__ import annotations

import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent
REPO_ROOT = FIXTURES_DIR.parents[2]
GENERATED = FIXTURES_DIR / "generated"

EVAL_FRAGMENT_GLSL = """\
layout(location = 0) out vec4 fragColor;

void main()
{
    fragColor = vec4(vUV.s, vUV.t, 0.5, 1.0);
}
"""


def main() -> Path:
    for p in (str(REPO_ROOT), str(REPO_ROOT / "MCP" / "server_core"),
              str(REPO_ROOT / "MCP" / "engine")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from meta_agentic.execution.tox_builder import ToxBuilder

    GENERATED.mkdir(parents=True, exist_ok=True)
    design = {
        "operators": [
            {"type": "lfo", "family": "CHOP", "name": "timing", "position": [0, 0],
             "parameters": {"frequency": 1}},
            {"type": "out", "family": "CHOP", "name": "out1", "position": [200, 0]},
        ],
        "connections": [{"from": "timing", "to": "out1"}],
    }
    builder = ToxBuilder(GENERATED, verbose=False)
    tox = builder.build_tox(design, "text")
    if not tox or not Path(tox).exists():
        raise SystemExit("fixture build failed: text.tox not produced")
    print(f"[fixtures] built {tox}")

    glsl = GENERATED / "eval_fragment.glsl"
    glsl.write_text(EVAL_FRAGMENT_GLSL, encoding="utf-8", newline="\n")
    print(f"[fixtures] wrote {glsl}")
    return Path(tox)


if __name__ == "__main__":
    main()

"""GLSL eval runner — v1 demo path for build_offline / fix_offline cases.

Loads a case from cases.yaml, fills its slots, writes the corresponding
fixture shader into a live-created GLSL TOP under /test/<case_id>, captures
the GLSL compile log + a rendered image, and scores the per-section
composite into a CaseScore for the harness.

Mode 1 (no API key): we use hand-authored fixture shaders keyed by
(case_id, slot choices). That's the honest Mode-1 contract — we're measuring
the build/import/render/error pipeline, not the agent. The agentic path is
Mode 2 (`generate_via_agent=True`, future).

Artifacts per case run:
    tests/glsl_eval/results/<run_ts>/<case_id>/
        prompt.txt        the filled, concrete prompt
        shader.glsl       the shader source actually written
        errors.txt        get_td_node_errors output
        output.png        captured TOP output (if reachable)
        case.json         scores + metrics + provenance
"""
from __future__ import annotations

import base64
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from measure._server import ALPHA_ROOT
from measure.harness import CaseScore

EVAL_DIR = Path(__file__).resolve().parent
CASES_PATH = EVAL_DIR / "cases.yaml"
RESULTS_ROOT = EVAL_DIR / "results"
TEST_BASE = "/test"

# GLSL compile error classes the eval recognises (from glsl9errors.txt + the
# wider catalogue). Used by fix_offline to verify the seeded class is removed.
ERROR_CLASSES: dict[str, re.Pattern] = {
    "version_not_first": re.compile(r"#version.*must occur first", re.I),
    "uniform_redefinition": re.compile(r"redefinition.*uniform|uniform.*redefinition|':\s*redefinition", re.I),
    "vec3_to_vec2": re.compile(r"cannot convert from.*vec3.*to.*vec2", re.I),
    "reserved_word": re.compile(r"Reserved word", re.I),
}

# Reference compile-log fragments for each bug class — extracted from the real
# Dec-2024 Dali run (`glsl9errors.txt`, sci-fi #10). v1 fix_offline scores the
# catalogue's classifier against these. v2 will additionally verify the live
# agent's repair against the live op's compile log.
REFERENCE_LOGS: dict[str, str] = {
    "version_not_first":
        "ERROR: /shader:1: '#version' : must occur first in shader\n"
        "ERROR: /shader:1: '#version' : bad profile name; use es, core, or compatibility",
    "uniform_redefinition":
        "ERROR: /glsl_dali_scene/shader_dali:10: 'vUV' : redefinition",
    "vec3_to_vec2":
        "ERROR: /glsl_dali_scene/shader_dali:150: '=' :  cannot convert from "
        "' temp highp vec3' to ' temp highp vec2'",
    "reserved_word":
        "ERROR: /10_scifi_flight/shader_code:82: 'active' : Reserved word.",
}

# ---------------------------------------------------------------------------
# Fixture shaders — hand-authored, known-good (or known-broken for fix_*)
# Keyed by (case_id, dominant slot). Keep small and inline for v1.
# ---------------------------------------------------------------------------

_FIXTURES: dict[str, str] = {
    # D5 — bo_glsl_top_theme_color (build_offline, easy) — known-good per theme.
    # NOTE: uTime is NOT a TD built-in (per td_glsl_expert/build.md) — it must
    # be declared as a uniform or the shader fails to compile. At t=0 these
    # still render a spatial gradient (real pixel variance).
    "bo_glsl_top_theme_color::sci-fi": """\
uniform float uTime;
out vec4 fragColor;
void main() {
    vec2 uv = vUV.st;
    float t = uTime;
    vec3 c = vec3(0.05 + 0.5 * uv.x, 0.1 + 0.4 * uv.y,
                  0.6 + 0.4 * sin(t + uv.x * 6.2831));
    fragColor = TDOutputSwizzle(vec4(c, 1.0));
}
""",
    "bo_glsl_top_theme_color::horror": """\
out vec4 fragColor;
void main() {
    vec2 uv = vUV.st;
    float v = smoothstep(0.0, 1.0, fract(sin(dot(uv, vec2(91.7, 47.3))) * 4318.5));
    vec3 c = vec3(0.35 * v, 0.02, 0.02);
    fragColor = TDOutputSwizzle(vec4(c, 1.0));
}
""",
    "bo_glsl_top_theme_color::dali_persistence": """\
uniform float uTime;
out vec4 fragColor;
void main() {
    vec2 uv = vUV.st * 2.0 - 1.0;
    float r = length(uv) - 0.5 - 0.15 * sin(uTime + uv.x * 3.0);
    float clk = smoothstep(0.02, 0.0, abs(r));
    vec3 c = mix(vec3(0.74, 0.55, 0.25), vec3(0.95, 0.85, 0.5), clk);
    fragColor = TDOutputSwizzle(vec4(c, 1.0));
}
""",
    "bo_glsl_top_theme_color::picasso_cubist": """\
out vec4 fragColor;
void main() {
    vec2 uv = vUV.st;
    vec2 g = floor(uv * 5.0);
    float k = fract(sin(dot(g, vec2(12.9, 78.2))) * 4317.0);
    vec3 c = vec3(k, 1.0 - k, 0.5 * fract(k * 3.7));
    fragColor = TDOutputSwizzle(vec4(c, 1.0));
}
""",

    # D6 — fo_glsl_fix_bug (fix_offline, medium) — DELIBERATELY broken per {bug}
    "fo_glsl_fix_bug::uniform_redefinition": """\
in vec2 vUV;   // TD already declares vUV -- triggers redefinition
out vec4 fragColor;
void main() {
    fragColor = TDOutputSwizzle(vec4(vUV, 0.0, 1.0));
}
""",
    "fo_glsl_fix_bug::version_not_first": """\
// stray comment
#version 330
out vec4 fragColor;
void main() { fragColor = TDOutputSwizzle(vec4(1.0)); }
""",
    "fo_glsl_fix_bug::vec3_to_vec2": """\
out vec4 fragColor;
void main() {
    vec3 a = vec3(0.5, 0.4, 0.3);
    vec2 b = a;  // cannot convert vec3 -> vec2
    fragColor = TDOutputSwizzle(vec4(b, 0.0, 1.0));
}
""",
    "fo_glsl_fix_bug::reserved_word": """\
out vec4 fragColor;
void main() {
    float active = 0.5;     // 'active' is reserved in some profiles
    fragColor = TDOutputSwizzle(vec4(active, active, active, 1.0));
}
""",
}


# ---------------------------------------------------------------------------
# Case loading and slot filling
# ---------------------------------------------------------------------------

def load_cases() -> dict[str, dict[str, Any]]:
    """Load cases.yaml -> {case_id: case_dict}."""
    data = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    return {c["id"]: c for c in (data.get("cases") or [])}


def fill_prompt(case: dict[str, Any], overrides: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """Render the templated prompt with case defaults + overrides; return (prompt, effective_slots)."""
    slots = dict(case.get("slots", {}))
    if overrides:
        slots.update(overrides)
    text = case["prompt"]
    for k, v in slots.items():
        text = text.replace("{" + k + "}", str(v))
    return text, slots


def fixture_key(case_id: str, slots: dict[str, str]) -> str | None:
    """Pick the dominant slot for fixture lookup. Currently: theme for D5, bug for D6."""
    for key in ("bug", "theme", "sim", "stage", "driver", "binding"):
        if key in slots and f"{case_id}::{slots[key]}" in _FIXTURES:
            return f"{case_id}::{slots[key]}"
    # fallback: any fixture for this case id
    matches = [k for k in _FIXTURES if k.startswith(case_id + "::")]
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Live-TD interaction (one execute_python_script does all setup atomically)
# ---------------------------------------------------------------------------

_SETUP_TEMPLATE = r'''
from td import baseCOMP, glslTOP
parent = op("{parent}")
if parent is None:
    # auto-create /test under the project root so the eval doesn't depend
    # on a pre-existing base COMP
    root_op = op("/") or op("/project1")
    if root_op is None:
        raise RuntimeError("cannot locate TD project root")
    name = "{parent}".lstrip("/")
    parent = root_op.create(baseCOMP, name)
# clear any prior case container
case_box = parent.op("{case_id}")
if case_box is not None:
    case_box.destroy()
case_box = parent.create(baseCOMP, "{case_id}")
gtop = case_box.create(glslTOP, "glsl1")
gtop.par.resolutionw = 256
gtop.par.resolutionh = 256
# CRITICAL: TD auto-creates the pixel-shader text DAT (+ info + compute DATs)
# when the glslTOP is created. Write into THAT DAT — never create a second
# one (a name collision renames ours to glsl1_pixel1, leaving the TOP bound to
# TD's empty default DAT, which renders solid white). [confirmed live]
pix = gtop.par.pixeldat.eval()
if pix is None:
    pix = case_box.op("glsl1_pixel")
    if pix is None:
        from td import textDAT
        pix = case_box.create(textDAT, "glsl1_pixel")
    gtop.par.pixeldat = pix.name
pix.text = {shader_literal}
try:
    pix.par.language = "glsl"
except Exception:
    pass
gtop.cook(force=True)
print("READY {parent}/{case_id}/glsl1 pixeldat=" + (pix.path if pix else "NONE"))
'''


def _setup_live_glsl(probe, case_id: str, shader: str) -> tuple[bool, str]:
    """Create /test/<case_id>/{glsl1, glsl1_pixel} live with the given shader.

    Returns (ok, detail). Idempotent — destroys any prior case_box first.
    """
    script = _SETUP_TEMPLATE.format(
        parent=TEST_BASE,
        case_id=case_id,
        shader_literal=repr(shader),
    )
    r = probe.call("execute_python_script", {"script": script})
    if not r.ok or "READY" not in (r.text or ""):
        return False, f"live setup failed: {(r.text or '')[:200]}"
    return True, "READY"


def _capture_errors(probe, op_path: str) -> tuple[str, bool, list[str]]:
    """Return (raw_log, has_errors, error_lines) for a GLSL TOP.

    KEY TD FACT [confirmed live]: a GLSL shader compile FAILURE surfaces as a
    *warning* (not an error), and the full compile log lives in the
    auto-created `<op>_info` info DAT — NOT in errors()/get_td_node_errors.
    The info DAT format matches the Dec-2024 `glsl9errors.txt`:

        Vertex Shader Compile Results:
        Compiled Successfully
        =============
        Pixel Shader Compile Results:
        ERROR: /path/glsl1_pixel:2: 'notAVar' : undeclared identifier

    So we read warnings() + that info DAT, and treat any `ERROR:` line (or a
    'compile error' warning) as a real failure.
    """
    info_path = op_path + "_info"
    script = (
        f'g = op("{op_path}")\n'
        f'def _s(fn):\n'
        f'    try: return str(fn() or "")\n'
        f'    except BaseException: return ""\n'
        f'warn = _s(g.warnings)\n'
        f'info = op("{info_path}")\n'
        f'log = info.text if (info is not None and hasattr(info, "text")) else ""\n'
        f'print("---WARN---")\n'
        f'print(warn)\n'
        f'print("---INFO---")\n'
        f'print(log)\n'
        f'print("---END---")\n'
    )
    r = probe.call("execute_python_script", {"script": script})
    text = r.text or ""
    warn = log = ""
    if "---WARN---" in text and "---INFO---" in text and "---END---" in text:
        warn = text.split("---WARN---", 1)[1].split("---INFO---", 1)[0].strip()
        log = text.split("---INFO---", 1)[1].split("---END---", 1)[0].strip()

    raw = f"=== warnings() ===\n{warn}\n\n=== {info_path} ===\n{log}"
    has = False
    msgs: list[str] = []
    if "compile error" in warn.lower():
        has = True
    for line in log.splitlines():
        if "ERROR:" in line:
            has = True
            msgs.append(line.strip())
    return raw, has, msgs


# A real render must have pixel variance. Solid white (TD's broken-shader
# fallback) is mean=1.0 std=0.0; solid black is mean=0 std=0. Any genuine
# shader output (gradient, pattern, even a flat colour with alpha) has std>0.
_RENDER_STD_MIN = 0.01


def _sample_render(probe, op_path: str) -> tuple[bool, float, float, str]:
    """Sample the live TOP's actual pixels via numpyArray (no Pillow needed).

    Returns (rendered_ok, mean, std, detail). `rendered_ok` is True iff the
    output has real variance — this is the durable 'is it a real render, or
    TD's white fallback' test. This is the signal your eye applies, automated.
    """
    script = (
        f'g = op("{op_path}")\n'
        f'import numpy\n'
        f'try:\n'
        f'    a = g.numpyArray()\n'
        f'    print("STATS %.6f %.6f" % (float(a.mean()), float(a.std())))\n'
        f'except Exception as e:\n'
        f'    print("SAMPLE_FAIL: " + str(e))\n'
    )
    r = probe.call("execute_python_script", {"script": script})
    text = r.text or ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("STATS "):
            try:
                _, m, s = line.split()
                mean, std = float(m), float(s)
                ok = std > _RENDER_STD_MIN
                return ok, mean, std, (
                    f"mean={mean:.3f} std={std:.3f} "
                    f"({'real render' if ok else 'FLAT — white/black fallback'})"
                )
            except ValueError:
                pass
    return False, 0.0, 0.0, f"could not sample pixels: {text[:80]}"


def _save_png(probe, op_path: str, out_png: Path) -> bool:
    """Save the TOP frame to disk for human review (artifact only — the SCORE
    comes from _sample_render, not from this file existing)."""
    out_path_str = str(out_png.resolve()).replace("\\", "/")
    script = (
        f'import os\n'
        f'os.makedirs(os.path.dirname(r"{out_path_str}"), exist_ok=True)\n'
        f'try:\n'
        f'    op("{op_path}").save(r"{out_path_str}")\n'
        f'    print("SAVED")\n'
        f'except Exception as e:\n'
        f'    print("FAIL: " + str(e))\n'
    )
    r = probe.call("execute_python_script", {"script": script})
    return r.ok and "SAVED" in (r.text or "") and out_png.exists()


# ---------------------------------------------------------------------------
# Section scorers
# ---------------------------------------------------------------------------

def _score_build_offline(has_errors: bool, render_ok: bool,
                         mean: float, std: float
                         ) -> tuple[float, dict[str, float], str]:
    compile_clean = 0.0 if has_errors else 1.0
    renders = 1.0 if render_ok else 0.0
    score = round((compile_clean + renders) / 2.0, 4)
    metrics = {"compile_clean": compile_clean, "renders": renders,
               "pixel_mean": round(mean, 4), "pixel_std": round(std, 4)}
    detail = (f"compile={'clean' if compile_clean else 'errors'}, "
              f"render={'real' if render_ok else 'FLAT(white/black)'} "
              f"(std={std:.3f})")
    return score, metrics, detail


def _score_fix_offline(error_msgs: list[str], expected_class: str
                       ) -> tuple[float, dict[str, float], str]:
    """Mode-1 fix-task scoring — error-class classifier.

    Scores whether our regex catalogue correctly classifies the expected bug.
    Sources, in order:
      1. Live op compile log (when TD surfaces GLSL errors via op.errors())
      2. Reference log from the Dec-2024 Dali corpus
    The latter guarantees deterministic classification in v1; v2 (agent path)
    will additionally check the class is REMOVED after the agent's repair.
    """
    pat = ERROR_CLASSES.get(expected_class)
    if pat is None:
        return 0.0, {"class_detected": 0.0}, f"no regex for class '{expected_class}'"

    live_text = "\n".join(error_msgs)
    live_hit = bool(pat.search(live_text))
    ref_text = REFERENCE_LOGS.get(expected_class, "")
    ref_hit = bool(pat.search(ref_text))

    detected = live_hit or ref_hit
    score = 1.0 if detected else 0.0
    source = "live" if live_hit else ("reference" if ref_hit else "miss")
    return score, {
        "class_detected": float(detected),
        "matched_live": float(live_hit),
        "matched_reference": float(ref_hit),
        "n_live_errors": float(len(error_msgs)),
    }, (
        f"class '{expected_class}' {source}; "
        f"live_errors={len(error_msgs)} (live={'y' if live_hit else 'n'}, "
        f"ref={'y' if ref_hit else 'n'})"
    )


# ---------------------------------------------------------------------------
# Public: run one case
# ---------------------------------------------------------------------------

def run_case(probe, case_id: str, overrides: dict[str, str] | None = None,
             run_ts: str | None = None) -> CaseScore:
    cases = load_cases()
    if case_id not in cases:
        return CaseScore(case_id, 0.0, "unknown", {}, "case not in cases.yaml")
    case = cases[case_id]
    section = case.get("section", "unknown")

    prompt, slots = fill_prompt(case, overrides)
    fkey = fixture_key(case_id, slots)
    if not fkey:
        return CaseScore(case_id, 0.0, section, {},
                         f"no fixture for {case_id} with slots {slots}")
    shader = _FIXTURES[fkey]

    # artifact folder
    run_ts = run_ts or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    art = RESULTS_ROOT / run_ts / case_id
    art.mkdir(parents=True, exist_ok=True)
    (art / "prompt.txt").write_text(prompt, encoding="utf-8")
    (art / "shader.glsl").write_text(shader, encoding="utf-8")

    t0 = time.perf_counter()
    ok, why = _setup_live_glsl(probe, case_id, shader)
    if not ok:
        (art / "errors.txt").write_text(why, encoding="utf-8")
        return CaseScore(case_id, 0.0, section,
                         {"duration_s": round(time.perf_counter() - t0, 2)},
                         why[:120])

    # Let TD's GL thread actually compile and cook a frame. Re-force a cook
    # after the first wait — pixel-shader compile happens off the main thread
    # so the first errors query can race ahead of it.
    op_path = f"{TEST_BASE}/{case_id}/glsl1"
    time.sleep(0.8)
    probe.call("execute_python_script",
               {"script": f'op("{op_path}").cook(force=True)'})
    time.sleep(1.2)

    errors_text, has_err, err_msgs = _capture_errors(probe, op_path)
    (art / "errors.txt").write_text(errors_text, encoding="utf-8")
    out_png = art / "output.png"
    render_ok, mean, std, render_detail = _sample_render(probe, op_path)
    _save_png(probe, op_path, out_png)  # artifact for human review

    if section == "build_offline":
        score, metrics, detail = _score_build_offline(has_err, render_ok, mean, std)
    elif section == "fix_offline":
        expected = slots.get("bug", "")
        score, metrics, detail = _score_fix_offline(err_msgs, expected)
    else:
        score, metrics, detail = 0.0, {}, f"section '{section}' not scored by v1 runner"

    metrics["duration_s"] = round(time.perf_counter() - t0, 2)

    # Persist case.json
    (art / "case.json").write_text(json.dumps({
        "case_id": case_id, "section": section, "slots": slots,
        "prompt": prompt, "score": score, "metrics": metrics,
        "detail": detail, "fixture": fkey,
        "expected_failure": case.get("expected_failure"),
        "success_criteria": case.get("success_criteria"),
    }, indent=2), encoding="utf-8")

    return CaseScore(case_id, score, section, metrics, detail)

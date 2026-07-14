"""Shared GLSL compile-failure detection helpers (W-A).

Pure, dependency-light logic used by every surface that must flag a GLSL compile
failure: the error tools (``get_node_errors`` / ``get_error_summary`` /
``get_cook_errors`` — W-A1), the ``get_glsl_status`` tool (W-A2), and the
mutation-receipt auto-flag (W-A3).

Why it lives in ``utils`` and imports NOTHING from ``td`` or the ``mcp`` package:
``api_service`` is unit-tested by loading it via file path (see
``tests/unit/test_exec_python_script_scope.py``), where the *installed MCP SDK*
owns the ``mcp`` name — so a ``from mcp.services... import`` inside ``api_service``
would fail under test. ``utils`` IS on the test's ``sys.path`` (it is the
td-webserver ``modules`` dir), so ``from utils.glsl import ...`` resolves in both
the test harness and the live TD runtime. These helpers therefore stay free of
``td`` and take the operator only to read its ``.OPType`` attribute.

Live-proven root cause (2026-07-13, TD 099.2025.32820): a broken ``glslTOP``
returns ``errors()`` == '' while ``warnings()`` ==
"The GLSL Shader has compile errors (Use Info DAT to see details)." — so a tool
that only wraps ``.errors()`` reports 0 on a hard compile failure. These helpers
recognise that banner and the compiler-log ``ERROR:`` lines so the failure is
never silent.
"""

import re

# GLSL-family operators, by the substring present in every one of their OPTypes
# (glslTOP, glslmultiTOP, glslPOP, glslMAT — verified against KB/operators.json
# build tokens TOP:glsl / TOP:glslmulti / POP:glsl / MAT:glsl). Matching the
# marker (rather than an exact allow-list) future-proofs against new GLSL ops.
GLSL_OPTYPE_MARKER = "glsl"

# DAT-reference parameters a GLSL op uses to point at its shader source. The names
# differ by family (verified against KB/operators.json):
#   * glslTOP / glslmultiTOP / glslPOP -> pixeldat / vertexdat / computedat
#   * glslMAT                          -> pdat / vdat  (pixel/vertex shader DATs;
#                                         the MAT has no compute stage)
# All are listed so a shader-source edit on ANY GLSL family is traced back to its op
# (the MAT's pdat/vdat were the W-A3 blind spot before the live-feedback wave). When
# a mutation writes one of these (or ``.text`` on a DAT one of them references) the
# receipt must re-check compile status (W-A3). ``.text`` is handled separately as a
# node-level write, not a par.
SHADER_SOURCE_PARS = ("pixeldat", "vertexdat", "computedat", "pdat", "vdat")

# op.warnings() compile-failure banner. TD phrases it "The GLSL Shader has compile
# errors (...)"; match the stable "compile error(s)"/"compile failed" core so
# minor wording drift still trips it.
_COMPILE_FAILURE_RE = re.compile(r"compile\s*(?:error|fail)", re.IGNORECASE)

# A GLSL/shader mention — used to promote a compile-failure warning that we cannot
# attribute to a specific op (recurse strings sometimes drop the op path): the
# banner itself names GLSL, so the message is self-identifying.
_GLSL_MENTION_RE = re.compile(r"\b(?:glsl|shader)\b", re.IGNORECASE)

# Fatal lines in a shader compiler log (Info DAT text). Per the howto skill:
# GLSL emits "ERROR: 0:12: ..." and a trailing "Compile Failed".
_LOG_ERROR_RE = re.compile(r"(?:ERROR:|Compile Failed)")


def op_type_of(op) -> str:
    """Best-effort ``op.OPType`` as a string ('' if unavailable). No ``td`` needed."""
    try:
        return str(getattr(op, "OPType", "") or "")
    except Exception:  # noqa: BLE001 — a hostile/partial stub must not crash detection
        return ""


def is_glsl_family(op) -> bool:
    """True for glslTOP / glslmultiTOP / glslPOP / glslMAT (and any GLSL variant)."""
    return GLSL_OPTYPE_MARKER in op_type_of(op).lower()


def is_compile_failure_message(msg) -> bool:
    """True if a warning/error message looks like a GLSL compile-failure banner."""
    return bool(msg) and bool(_COMPILE_FAILURE_RE.search(str(msg)))


def is_glsl_specific_compile_message(msg) -> bool:
    """True only when the message BOTH names GLSL/shader AND reads as a compile
    failure — safe to promote even without a resolvable op (the banner is
    self-identifying). Avoids promoting a generic 'compile error' from some
    unrelated subsystem."""
    if not msg:
        return False
    text = str(msg)
    return bool(_GLSL_MENTION_RE.search(text)) and bool(_COMPILE_FAILURE_RE.search(text))


def scan_compiler_log(text) -> list:
    """Return the fatal lines ('ERROR:' / 'Compile Failed') from an Info DAT's text.

    Non-empty result == the shader failed to compile. Mirrors the manual recipe in
    the td-builder-howto skill so the tool and the documented workaround agree.
    """
    if not text:
        return []
    return [ln.strip() for ln in str(text).splitlines() if _LOG_ERROR_RE.search(ln)]


def mutation_touches_glsl(op, properties) -> bool:
    """W-A3 gate: should this ``update_node`` receipt re-check GLSL compile status?

    True when EITHER the mutated op is itself a GLSL-family op (any par write can
    break a shader — e.g. swapping the source DAT), OR the write is a shader-source
    write on a DAT: ``.text`` (``properties`` carries a 'text' key) or any
    ``SHADER_SOURCE_PARS`` par (pixeldat/vertexdat/computedat for TOP/POP,
    pdat/vdat for MAT). The caller decides which op to
    actually status-check (the GLSL op, not the DAT): it resolves cross-container
    consumers via a GLSL-scoped *forward-pointer* check (dock shortcut + capped
    scan reading GLSL ops' own ``SHADER_SOURCE_PARS``). A *general*
    reverse-reference walk over arbitrary pars remains OUT of scope (roadmap N6).
    """
    if is_glsl_family(op):
        return True
    if not isinstance(properties, dict):
        return False
    keys = {str(k).lower() for k in properties.keys()}
    if "text" in keys:
        return True
    return any(p in keys for p in SHADER_SOURCE_PARS)

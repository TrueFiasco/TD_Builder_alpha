"""GLSL compile-status service (W-A2 + the W-A3 receipt helper).

``get_glsl_status(node_path)`` returns ``{ok, errors, warnings, compiler_log,
compiler_errors, ...}`` for a GLSL-family op. The compiler log is the shader's
Info DAT text — the source of truth for GLSL compile output (``op.errors()`` is
empty on a hard compile failure; see ``utils.glsl``). We prefer an existing
docked/sibling ``<name>_info`` Info DAT and otherwise create a temporary one,
point it at the op, read ``.text``, and destroy it (the temp-node pattern proven
in ``capture_service._capture_via_opviewer``).

``receipt_for_mutation(node, properties)`` is the W-A3 hook: given a just-applied
``update_node`` mutation, it decides whether the change could affect a shader and,
if so, returns a compact compile-status summary to staple onto the mutation
receipt — so an agent that forgets to check errors is still told about a break.
"""

from typing import Any, Optional

import td
from utils.glsl import (
    SHADER_SOURCE_PARS,
    is_compile_failure_message,
    is_glsl_family,
    mutation_touches_glsl,
    op_type_of,
    scan_compiler_log,
)
from utils.logging import log_message
from utils.result import error_result, success_result
from utils.types import LogLevel, Result

_TEMP_INFO_NAME = "temp_glsl_info_capture"


class GlslStatusService:
    """Compile-status reader for GLSL ops (TOP/multiTOP/POP/MAT)."""

    def __init__(self) -> None:
        log_message("GlslStatusService initialized (W-A2)", LogLevel.INFO)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def get_glsl_status(self, node_path: str) -> Result:
        """Return the compile status of the op at ``node_path``.

        ok=False iff the shader failed to compile (compiler-log ERROR lines or a
        compile-failure warning banner) OR the op reports plain errors. For a
        non-GLSL op we skip the Info DAT entirely (nothing to compile) and just
        report is_glsl=False with any errors/warnings.
        """
        node = td.op(node_path)
        if node is None or not getattr(node, "valid", False):
            return error_result(f"Node not found at path: {node_path}")

        is_glsl = is_glsl_family(node)
        errors = self._lines(self._safe_call(node, "errors"))
        warnings = self._lines(self._safe_call(node, "warnings"))

        if is_glsl:
            compiler_log = self._read_compiler_log(node)
            compiler_errors = scan_compiler_log(compiler_log)
        else:
            compiler_log = ""
            compiler_errors = []

        compile_failed = bool(compiler_errors) or any(
            is_compile_failure_message(w) for w in warnings
        )
        ok = not compile_failed and not errors

        return success_result(
            {
                "node_path": str(getattr(node, "path", node_path)),
                "op_type": op_type_of(node),
                "is_glsl": is_glsl,
                "ok": ok,
                "compile_failed": compile_failed,
                "errors": errors,
                "warnings": warnings,
                "compiler_log": compiler_log,
                "compiler_errors": compiler_errors,
            }
        )

    def receipt_for_mutation(self, node: Any, properties: Any) -> Optional[dict]:
        """W-A3: compact compile-status summary to append to an update_node receipt,
        or None when the mutation cannot have affected a shader.

        Foolproof path: if the mutated op is itself GLSL-family, status-check it.
        Otherwise, if the write was a shader-source write (``.text`` / a shader par)
        on a DAT, do a BOUNDED sibling scan (parent's direct children only) for a
        GLSL op whose own shader-source par (``SHADER_SOURCE_PARS`` —
        pixeldat/vertexdat/computedat on TOP/POP, pdat/vdat on MAT) references this
        DAT — "via the op's own pars", never a full-project reverse walk (N6).
        Never raises: any failure returns None (a receipt must not break a mutation).
        """
        try:
            if not mutation_touches_glsl(node, properties):
                return None
            target = self._resolve_glsl_target(node, properties)
            if target is None:
                return None
            result = self.get_glsl_status(str(getattr(target, "path", "")))
            if not result.get("success"):
                return None
            data = result["data"]
            return {
                "checked_node": data["node_path"],
                "op_type": data["op_type"],
                # is_glsl gates the client's success-confirmation note
                # (td_live_client._glsl_status_note); omitting it made the "✅ GLSL
                # compile OK" half of W-A3 unreachable in production. The checked op
                # is always GLSL-family here (the target is resolved to one), so this
                # is True on the success path.
                "is_glsl": data["is_glsl"],
                "ok": data["ok"],
                "compile_failed": data["compile_failed"],
                "compiler_errors": data["compiler_errors"][:20],
                "warnings": data["warnings"][:20],
            }
        except Exception as e:  # noqa: BLE001 — best-effort; never break the mutation
            log_message(f"GLSL receipt check skipped: {e}", LogLevel.WARNING)
            return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_glsl_target(self, node: Any, properties: Any) -> Optional[Any]:
        """The GLSL op whose compile status a mutation on ``node`` should re-check."""
        if is_glsl_family(node):
            return node
        # DAT shader-source write: find the sibling GLSL op that references this DAT.
        try:
            parent = node.parent()
            siblings = parent.findChildren(depth=1) if parent is not None else []
        except Exception:
            return None
        node_path = str(getattr(node, "path", ""))
        for sib in siblings or []:
            if not is_glsl_family(sib):
                continue
            for par_name in SHADER_SOURCE_PARS:
                par = getattr(getattr(sib, "par", None), par_name, None)
                if par is None:
                    continue
                try:
                    val = str(getattr(par, "val", "") or "")
                except Exception:
                    val = ""
                if not val:
                    continue
                try:
                    ref = sib.op(val)
                except Exception:
                    ref = None
                if ref is node or (ref is not None and str(getattr(ref, "path", "")) == node_path):
                    return sib
        return None

    def _read_compiler_log(self, node: Any) -> str:
        """Return the shader's Info DAT text, creating a temp Info DAT if needed.

        Prefers a docked Info DAT or a sibling ``<name>_info`` (built ops ship one),
        else creates ``temp_glsl_info_capture``, points its ``op`` par at the node,
        cooks, reads ``.text``, and destroys it in a finally-equivalent — so a temp
        Info DAT never leaks even on error.
        """
        info = self._find_existing_info_dat(node)
        temp = None
        try:
            if info is None:
                parent = node.parent()
                if parent is None:
                    return ""
                # Clear any leaked temp from a prior aborted call so create() does
                # not silently auto-suffix (we would then destroy the wrong node).
                stale = parent.op(_TEMP_INFO_NAME)
                if stale is not None and getattr(stale, "valid", False):
                    try:
                        stale.destroy()
                    except Exception:
                        pass
                temp = parent.create("infoDAT", _TEMP_INFO_NAME)
                try:
                    temp.par.op = str(getattr(node, "path", ""))
                except Exception:
                    pass
                try:
                    temp.nodeX, temp.nodeY = node.nodeX, node.nodeY - 150
                except Exception:
                    pass
                self._safe_cook(temp)
                info = temp
            else:
                self._safe_cook(info)
            text = getattr(info, "text", "") if info is not None else ""
            return str(text or "")
        except Exception as e:  # noqa: BLE001
            log_message(f"_read_compiler_log failed: {e}", LogLevel.WARNING)
            return ""
        finally:
            if temp is not None:
                try:
                    temp.destroy()
                except Exception:
                    pass

    def _find_existing_info_dat(self, node: Any) -> Optional[Any]:
        """A docked Info DAT, or a sibling named ``<name>_info`` that is an infoDAT."""
        try:
            for child in getattr(node, "docked", None) or []:
                if op_type_of(child) == "infoDAT":
                    return child
        except Exception:
            pass
        try:
            parent = node.parent()
            if parent is not None:
                sib = parent.op(str(getattr(node, "name", "")) + "_info")
                if sib is not None and getattr(sib, "valid", True) and op_type_of(sib) == "infoDAT":
                    return sib
        except Exception:
            pass
        return None

    @staticmethod
    def _safe_cook(op_obj: Any) -> None:
        try:
            op_obj.cook(force=True)
        except Exception:
            pass

    @staticmethod
    def _safe_call(node: Any, method: str) -> str:
        """Call node.errors()/warnings() defensively, returning '' on any failure."""
        try:
            fn = getattr(node, method, None)
            if callable(fn):
                return fn() or ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _lines(text: Any) -> list:
        if not text:
            return []
        return [ln.strip() for ln in str(text).splitlines() if ln.strip()]


# Singleton for use by controllers + api_service (W-A3).
glsl_status_service = GlslStatusService()

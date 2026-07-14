"""GLSL compile-status service (W-A2 + the W-A3 receipt helper).

``get_glsl_status(node_path)`` returns ``{ok, errors, warnings, compiler_log,
compiler_errors, ...}`` for a GLSL-family op. The compiler log is the shader's
Info DAT text — the source of truth for GLSL compile output (``op.errors()`` is
empty on a hard compile failure; see ``utils.glsl``). We prefer an existing
docked/sibling ``<name>_info`` Info DAT. When none exists, the READ path creates
a temporary one, reads ``.text``, and destroys it (the temp-node pattern proven
in ``capture_service._capture_via_opviewer``) — the tool's READ_ONLY annotation
stays honest. The MUTATION path (the W-A3 receipt, running inside update_node,
class DESTRUCTIVE) instead creates a persistent ``<name>_info`` docked to the
GLSL op — the same Info DAT TD's own create() ships (owner decision 2026-07-14).

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

    def get_glsl_status(
        self, node_path: str = "", file_path: str = "", persist_info: bool = False
    ) -> Result:
        """Return the compile status of the op at ``node_path``, or of every GLSL
        op whose shader source is a DAT synced to ``file_path`` (the check for the
        edit-the-.glsl-file-on-disk workflow).

        ok=False iff the shader failed to compile (compiler-log ERROR lines or a
        compile-failure warning banner) OR the op reports plain errors. For a
        non-GLSL op we skip the Info DAT entirely (nothing to compile) and just
        report is_glsl=False with any errors/warnings.

        ``persist_info`` is server-internal (NOT exposed on the HTTP route — the
        tool's READ_ONLY annotation depends on that): only the W-A3 mutation
        receipt passes True, allowing a missing Info DAT to be created
        persistently and docked instead of temp-and-destroyed.
        """
        if not node_path and file_path:
            return self._status_for_shader_file(file_path)
        node = td.op(node_path)
        if node is None or not getattr(node, "valid", False):
            return error_result(f"Node not found at path: {node_path}")

        is_glsl = is_glsl_family(node)
        # PROVEN LIVE (2026-07-14): a file-synced shader DAT reloads from disk
        # automatically, but the GLSL op only RECOMPILES on its next cook — an
        # idle branch reads stale-clean without this force-cook. It also makes
        # the W-A3 receipt (which routes through here) synchronous with the
        # .text write it is annotating.
        if is_glsl:
            self._safe_cook(node)
        errors = self._lines(self._safe_call(node, "errors"))
        warnings = self._lines(self._safe_call(node, "warnings"))

        if is_glsl:
            compiler_log = self._read_compiler_log(node, persist_info=persist_info)
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
            # persist_info: the receipt runs inside update_node (class DESTRUCTIVE),
            # so it may leave a permanent docked <name>_info on the checked op.
            result = self.get_glsl_status(
                str(getattr(target, "path", "")), persist_info=True
            )
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

    _FILE_SCAN_CAP = 8000

    def _status_for_shader_file(self, file_path: str) -> Result:
        """Compile status for every GLSL op whose shader source is a DAT synced to
        ``file_path``. TD auto-reloads a synced DAT when the file changes on disk,
        but the recompile only happens on the op's next cook — the per-op status
        check above force-cooks, so this is the one-call answer to "I just edited
        a shader file; did it break anything?". Matching: exact normalized path
        first, basename fallback (DAT file pars are often project-relative)."""
        root = getattr(td, "root", None)
        if root is None:
            return error_result("td.root unavailable; cannot scan for shader DATs")
        try:
            all_ops = list(root.findChildren())[: self._FILE_SCAN_CAP]
        except Exception as e:  # noqa: BLE001
            return error_result(f"Project scan failed: {e}")

        # TD file pars freely mix / and \ on Windows, and POSIX os.path.basename
        # does not split backslashes at all — normalize separators (and case;
        # TD ships on Windows/macOS, both case-insensitive filesystems) BEFORE
        # comparing so the match behaves identically on every platform,
        # including the Linux CI runner exercising this code with stubs.
        def _norm(p: str) -> str:
            return str(p).replace("\\", "/").lower()

        target = _norm(file_path)
        base = target.rstrip("/").rsplit("/", 1)[-1]
        exact, by_name = [], []
        for o in all_ops:
            par = getattr(getattr(o, "par", None), "file", None)
            if par is None:
                continue
            try:
                val = str(par.eval() or "")
            except Exception:  # noqa: BLE001 — stub/odd pars: fall back to .val
                val = str(getattr(par, "val", "") or "")
            if not val:
                continue
            norm = _norm(val)
            if norm == target:
                exact.append(o)
            elif norm.rstrip("/").rsplit("/", 1)[-1] == base:
                by_name.append(o)
        dats = exact or by_name
        if not dats:
            return error_result(
                f"No op with a file par matching '{file_path}' found "
                f"(scanned {len(all_ops)} ops). Is the DAT's Sync-to-File path set?"
            )
        dat_paths = {str(getattr(d, "path", "")) for d in dats}

        checked = []
        for o in all_ops:
            if not is_glsl_family(o):
                continue
            for par_name in SHADER_SOURCE_PARS:
                par = getattr(getattr(o, "par", None), par_name, None)
                if par is None:
                    continue
                ref = self._resolve_op_par(o, par)
                if ref is not None and str(getattr(ref, "path", "")) in dat_paths:
                    checked.append(o)
                    break
        if not checked:
            return error_result(
                "Matched DAT(s) " + ", ".join(sorted(dat_paths)) +
                f" for '{file_path}', but no GLSL op references them via "
                f"{'/'.join(SHADER_SOURCE_PARS)}."
            )
        statuses = []
        for o in checked:
            r = self.get_glsl_status(str(getattr(o, "path", "")))
            if r.get("success"):
                statuses.append(r["data"])
        return success_result({
            "file_path": file_path,
            "matched_dats": sorted(dat_paths),
            "checked_ops": [s["node_path"] for s in statuses],
            "ok": bool(statuses) and all(s["ok"] for s in statuses),
            "compile_failed": any(s["compile_failed"] for s in statuses),
            "statuses": statuses,
        })

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
                ref = self._resolve_op_par(sib, par)
                if ref is node or (ref is not None and str(getattr(ref, "path", "")) == node_path):
                    return sib
        return None

    @staticmethod
    def _resolve_op_par(owner: Any, par: Any) -> Optional[Any]:
        """Resolve a shader-source (OP-type) par to the operator it references.

        PROVEN LIVE (2026-07-14, TD 099.2025.32820): ``OP.op(name)`` on a non-COMP
        does NOT resolve sibling names — ``op('/x/glsl1').op('glsl1_pixel')`` is
        None even though that is TD's own auto-docked default wiring. ``par.eval()``
        on an OP-type par returns the referenced operator directly (and handles
        expression-mode pars, where ``par.val`` is the raw expression string). For
        string-y evals (odd/stub pars) fall back to resolving against the owner's
        PARENT — sibling names anchor there, never at the owner itself.
        """
        try:
            resolved = par.eval()
        except Exception:  # noqa: BLE001 — stub/odd pars: fall back to .val
            resolved = None
        if resolved is not None and not isinstance(resolved, str):
            return resolved
        val = str(resolved or getattr(par, "val", "") or "")
        if not val:
            return None
        try:
            parent = owner.parent()
            return parent.op(val) if parent is not None else None
        except Exception:  # noqa: BLE001
            return None

    def _read_compiler_log(self, node: Any, persist_info: bool = False) -> str:
        """Return the shader's Info DAT text, creating an Info DAT if needed.

        Prefers a docked Info DAT or a sibling ``<name>_info`` (built ops ship one).
        When none exists the behavior forks on ``persist_info`` (owner decision
        2026-07-14):
          * False (the READ_ONLY ``get_glsl_status`` surface): create
            ``temp_glsl_info_capture``, read ``.text``, and destroy it in a
            finally-equivalent — a pure status read never mutates the network.
          * True (the W-A3 mutation receipt, inside update_node, class DESTRUCTIVE):
            create a permanent ``<name>_info`` docked to the GLSL op — the same
            Info DAT TD's own create() ships — and KEEP it on success (destroyed
            only if the read errors out), so every op actually worked on ends up
            with its compile-error surface.
        """
        info = self._find_existing_info_dat(node)
        created = None
        keep_created = False
        try:
            if info is None:
                parent = node.parent()
                if parent is None:
                    return ""
                if persist_info:
                    created = self._create_persistent_info_dat(node, parent)
                else:
                    # Clear any leaked temp from a prior aborted call so create()
                    # does not silently auto-suffix (we would then destroy the
                    # wrong node).
                    stale = parent.op(_TEMP_INFO_NAME)
                    if stale is not None and getattr(stale, "valid", False):
                        try:
                            stale.destroy()
                        except Exception:
                            pass
                    created = parent.create("infoDAT", _TEMP_INFO_NAME)
                    try:
                        created.par.op = str(getattr(node, "path", ""))
                    except Exception:
                        pass
                    try:
                        created.nodeX, created.nodeY = node.nodeX, node.nodeY - 150
                    except Exception:
                        pass
                self._safe_cook(created)
                info = created
            else:
                self._safe_cook(info)
            text = getattr(info, "text", "") if info is not None else ""
            keep_created = persist_info
            return str(text or "")
        except Exception as e:  # noqa: BLE001
            log_message(f"_read_compiler_log failed: {e}", LogLevel.WARNING)
            return ""
        finally:
            if created is not None and not keep_created:
                try:
                    created.destroy()
                except Exception:
                    pass

    @staticmethod
    def _create_persistent_info_dat(node: Any, parent: Any) -> Any:
        """Create the permanent ``<name>_info`` Info DAT docked to ``node``
        (mutation path only). Mirrors the offline builder's
        ``toe_builder_bridge._write_docked_info_dat`` and TD's own create()
        convention: named ``<host>_info``, ``op`` par = relative sibling name,
        docked to the host, placed at the docked-child offset (+160, -120).
        Docking is best-effort: if the ``dock`` assignment fails, the name and
        position still make the DAT discoverable via the ``<name>_info`` sibling
        lookup in ``_find_existing_info_dat``.
        """
        info = parent.create("infoDAT", str(getattr(node, "name", "")) + "_info")
        try:
            info.par.op = str(getattr(node, "name", ""))
        except Exception:
            pass
        try:
            info.nodeX, info.nodeY = node.nodeX + 160, node.nodeY - 120
        except Exception:
            pass
        try:
            info.dock = node
        except Exception:
            pass
        return info

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

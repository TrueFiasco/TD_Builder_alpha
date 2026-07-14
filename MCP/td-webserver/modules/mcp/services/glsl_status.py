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
The consuming GLSL op is resolved by treating (GLSL op + shader DAT(s) + info
DAT) as one unit: dock shortcut, then sibling scan, then a capped project scan
over GLSL-family ops (its "no consumer" answers memoized per DAT path with a
short TTL — see ``_find_glsl_consumer_projectwide``) — always via the ops' own
``SHADER_SOURCE_PARS`` forward pointers. Statuses and receipts carry ``shader_sources`` (which DAT holds each
stage, and the on-disk .glsl/.vert/.frag its ``file`` par syncs to).
"""

import time
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
        # Negative-consumer memo for the receipt's project-scan lane: DAT path ->
        # time.monotonic() of a full scan that found NO GLSL consumer. See
        # _find_glsl_consumer_projectwide for the invalidation/staleness story.
        self._no_consumer_memo: dict = {}
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
            shader_sources = self._shader_sources(node)
        else:
            compiler_log = ""
            compiler_errors = []
            shader_sources = []

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
                # Which DAT holds each shader stage and the on-disk
                # .glsl/.vert/.frag its `file` par syncs to — the "what do I
                # edit to fix this" answer, in the status itself.
                "shader_sources": shader_sources,
            }
        )

    def receipt_for_mutation(self, node: Any, properties: Any) -> Optional[dict]:
        """W-A3: compact compile-status summary to append to an update_node receipt,
        or None when the mutation cannot have affected a shader.

        Foolproof path: if the mutated op is itself GLSL-family, status-check it.
        Otherwise, if the write was a shader-source write (``.text`` / a shader par)
        on a DAT, resolve the consuming GLSL op via the ladder in
        ``_resolve_glsl_target`` (dock shortcut -> bounded sibling scan -> capped
        project scan over GLSL-family ops). Every lane reads the GLSL ops' OWN
        shader-source pars (``SHADER_SOURCE_PARS`` — pixeldat/vertexdat/computedat
        on TOP/POP, pdat/vdat on MAT) — a *general* reverse-reference walk over
        arbitrary pars remains out of scope (roadmap N6).
        Never raises: any failure returns None (a receipt must not break a mutation).
        """
        try:
            if not mutation_touches_glsl(node, properties):
                return None
            if is_glsl_family(node):
                # Any par write on a GLSL op can rewire it at a DAT previously
                # memoized as consumerless — drop the negative memo so the next
                # edit on that DAT rescans (see _find_glsl_consumer_projectwide).
                self._no_consumer_memo.clear()
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
                # Which DAT holds each shader stage (and the on-disk file feeding
                # it) — so after a failed receipt the agent knows what to fix
                # without a follow-up call.
                "shader_sources": data.get("shader_sources", []),
            }
        except Exception as e:  # noqa: BLE001 — best-effort; never break the mutation
            log_message(f"GLSL receipt check skipped: {e}", LogLevel.WARNING)
            return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    # Shared cap for both project-wide scan lanes: the file_path lane and the
    # receipt's last-resort cross-container consumer scan.
    _PROJECT_SCAN_CAP = 8000

    # Negative-consumer memo tuning (receipt lane): how long a "no GLSL consumer
    # references this DAT" answer stays trusted, and how many DAT paths may be
    # memoized before the memo is wholesale cleared (crude bound — entries
    # rebuild on demand; per-entry LRU machinery is not worth it here).
    _NO_CONSUMER_TTL_SECONDS = 30.0
    _NO_CONSUMER_MEMO_MAX = 256

    def _capped_project_ops(self, root: Any, lane: str) -> list:
        """All project ops via the recursive ``root.findChildren()``, truncated at
        ``_PROJECT_SCAN_CAP``. A cap hit is LOGGED — past the cap either lane
        silently misses (a shader DAT / a cross-container consumer), and that
        must at least be visible. Raises whatever findChildren raises; each
        caller keeps its own degrade story (error_result vs no-receipt)."""
        found = list(root.findChildren())
        if len(found) > self._PROJECT_SCAN_CAP:
            log_message(
                f"GLSL {lane} project scan hit its {self._PROJECT_SCAN_CAP}-op cap "
                f"({len(found)} ops in project) — ops beyond the cap were not "
                "scanned; a consumer/DAT past the cap is silently missed",
                LogLevel.WARNING,
            )
        return found[: self._PROJECT_SCAN_CAP]

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
            all_ops = self._capped_project_ops(root, "file_path")
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
            if is_glsl_family(o) and self._op_references_dats(o, dat_paths):
                checked.append(o)
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
        """The GLSL op whose compile status a mutation on ``node`` should re-check.

        Ladder — first hit wins; the receipt is single-target by design (the
        client note renders one node, and a shared shader breaks identically in
        every consumer):
          (a) the mutated op is itself GLSL-family;
          (b) dock shortcut: TD's create() docks the shader DAT to its GLSL op,
              so ``node.dock`` is the consumer for default wiring — verified via
              the op's own shader-source pars, never trusted blindly (a docked
              ``<name>_info`` has the same dock relationship but is no source);
          (c) bounded sibling scan (parent's direct children) — same-container
              manual wiring;
          (d) capped project-wide scan over GLSL-family ops only — cross-container
              ``../`` or absolute refs. Every lane reads the GLSL ops' OWN
              forward pointers (``SHADER_SOURCE_PARS``); a general reverse walk
              over arbitrary pars remains out of scope (roadmap N6).
        """
        if is_glsl_family(node):
            return node
        node_path = str(getattr(node, "path", ""))
        # (b) dock shortcut. getattr does NOT swallow a raising property — guard it.
        try:
            dock = getattr(node, "dock", None)
        except Exception:  # noqa: BLE001 — hostile/partial ops
            dock = None
        if dock is not None and is_glsl_family(dock) and self._op_references_dats(
            dock, {node_path}, node
        ):
            return dock
        # (c) bounded sibling scan.
        try:
            parent = node.parent()
            siblings = parent.findChildren(depth=1) if parent is not None else []
        except Exception:  # noqa: BLE001
            siblings = []
        for sib in siblings or []:
            if is_glsl_family(sib) and self._op_references_dats(sib, {node_path}, node):
                return sib
        # (d) capped project scan.
        return self._find_glsl_consumer_projectwide(node, node_path)

    def _op_references_dats(
        self, glsl_op: Any, dat_paths: set, dat_node: Any = None
    ) -> bool:
        """True if any shader-source par on ``glsl_op`` resolves (via
        ``_resolve_op_par``) to ``dat_node`` (identity) or a path in ``dat_paths``."""
        for par_name in SHADER_SOURCE_PARS:
            par = getattr(getattr(glsl_op, "par", None), par_name, None)
            if par is None:
                continue
            ref = self._resolve_op_par(glsl_op, par)
            if ref is None:
                continue
            if ref is dat_node or str(getattr(ref, "path", "")) in dat_paths:
                return True
        return False

    def _find_glsl_consumer_projectwide(self, node: Any, node_path: str) -> Optional[Any]:
        """Ladder lane (d): first GLSL-family op anywhere in the project whose
        shader-source par references ``node``.

        Only DATs can be shader sources, and ``mutation_touches_glsl`` fires on
        any ``text`` key (which a textTOP write also carries) — the DAT pre-filter
        keeps non-DAT text writes from paying the project walk. The family check
        is exact (TD OPTypes end in their family name: textDAT, tableDAT, ...);
        a 'dat' substring would let dattoCHOP-style ops slip through. The walk
        reuses the file lane's capped ``td.root.findChildren()`` pattern; no root
        (unit stubs, teardown) degrades to no receipt, never an error.

        Perf (PR #29 review): a "no consumer" answer is memoized per DAT path for
        ``_NO_CONSUMER_TTL_SECONDS`` — without it, EVERY ``text`` write on a
        consumerless DAT pays a full recursive findChildren() + GLSL scan on the
        TD main thread. Staleness story, honestly: rewiring via update_node (any
        GLSL-op par write) clears the memo immediately (``receipt_for_mutation``);
        wiring changed any OTHER way — create_node with shader-source
        ``parameters``, ``execute_python_script``, manual UI edits — is seen only
        after the TTL, so a receipt can be missing for up to that window on an
        already-memoized DAT.
        """
        if not op_type_of(node).endswith("DAT"):
            return None
        now = time.monotonic()
        memo = self._no_consumer_memo.get(node_path)
        if memo is not None and (now - memo) < self._NO_CONSUMER_TTL_SECONDS:
            return None
        root = getattr(td, "root", None)
        if root is None:
            return None
        try:
            all_ops = self._capped_project_ops(root, "receipt")
        except Exception:  # noqa: BLE001
            return None
        for o in all_ops:
            if is_glsl_family(o) and self._op_references_dats(o, {node_path}, node):
                return o
        if len(self._no_consumer_memo) >= self._NO_CONSUMER_MEMO_MAX:
            self._no_consumer_memo.clear()
        self._no_consumer_memo[node_path] = now
        log_message(
            f"GLSL receipt: no consumer references {node_path} "
            f"(scanned {len(all_ops)} ops); memoized for "
            f"{self._NO_CONSUMER_TTL_SECONDS:.0f}s",
            LogLevel.DEBUG,
        )
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

    def _shader_sources(self, node: Any) -> list:
        """One entry per populated shader-source par on a GLSL op: which DAT holds
        the stage's shader and which on-disk file (the DAT's ``file`` par) feeds
        it. A populated par whose reference doesn't resolve is reported with
        ``dat=None`` and the raw par value — honesty over silence. Deduped by
        resolved DAT: glslTOP exposes both ``pixeldat`` and ``pdat`` for the same
        DAT (legacy alias, proven live 2026-07-14).
        """
        sources = []
        seen = set()
        for par_name in SHADER_SOURCE_PARS:
            par = getattr(getattr(node, "par", None), par_name, None)
            if par is None:
                continue
            raw = str(getattr(par, "val", "") or "")
            ref = self._resolve_op_par(node, par)
            if ref is None and not raw:
                continue
            if ref is not None:
                entry = {
                    "par": par_name,
                    "dat": str(getattr(ref, "path", "")),
                    "dat_name": str(getattr(ref, "name", "")),
                    "file": self._dat_file_of(ref),
                }
            else:
                entry = {"par": par_name, "dat": None, "dat_name": raw, "file": ""}
            key = entry["dat"] or entry["dat_name"]
            if key in seen:
                continue
            seen.add(key)
            sources.append(entry)
        return sources

    @staticmethod
    def _dat_file_of(dat: Any) -> str:
        """The DAT's ``file`` par value (its synced .glsl/.vert/.frag), or ''
        when the shader text is embedded (no file sync)."""
        par = getattr(getattr(dat, "par", None), "file", None)
        if par is None:
            return ""
        try:
            val = par.eval()
        except Exception:  # noqa: BLE001 — stub/odd pars: fall back to .val
            val = None
        if val is None or not isinstance(val, str):
            val = getattr(par, "val", "") or ""
        return str(val or "")

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

"""Error Monitor Service for Network Editor MCP.

Aggregates TouchDesigner errors from three sources:
  1. Every Error DAT in the project (no hardcoded paths).
  2. `op.errors(recurse=True)` rolled up from the root (catches
     parameter-expression errors, missing-input errors, cook errors).
  3. (Reserved for the in-app cook-error stream if/when wired.)

Wave 3 (B11/B12/B13): the previous implementation only checked a 4-path
hardcoded list for an Error DAT and never called `op.errors()`, so:
  - flap_lfo NameError on `frequency` expression -> invisible
  - flap_pivot "Not enough sources" -> invisible
  - "no DAT found" was silently returned as zero errors

The new aggregator works WITHOUT any Error DAT (op.errors() is built-in to
every operator). Error DATs are merged in when they exist.
"""

from typing import Any, Dict, List, Optional, Tuple

import td
from utils.glsl import (
    is_compile_failure_message,
    is_glsl_family,
    is_glsl_specific_compile_message,
)
from utils.logging import log_message
from utils.types import LogLevel, Result


# Error DAT column mapping (standard TD Error DAT structure).
ERROR_DAT_COLUMNS = {
    "source": 0,    # operator path
    "message": 1,   # error text
    "absframe": 2,  # absolute frame
    "frame": 3,     # local frame
    "severity": 4,  # 0=info, 1=warning, 2=error, 3=fatal
    "type": 5,      # operator type/family
}

SEVERITY_MAP = {
    0: "info", 1: "warning", 2: "error", 3: "fatal",
    "0": "info", "1": "warning", "2": "error", "3": "fatal",
    "info": "info", "warning": "warning", "error": "error", "fatal": "fatal",
    # Live-observed Error DAT column strings (W-D research, TD 2025.32820):
    # hard errors log severity="abort" (onError int 3) and informational rows
    # log "message" — without these keys both fell through to the "info"
    # default, mis-bucketing real aborts as info.
    "abort": "fatal", "message": "info",
}

# Safety cap on how many ops we'll walk when calling op.errors() in fallback
# mode. The primary path is one td.root.errors(recurse=True) call, which is
# O(1) — this cap only kicks in if that approach is unavailable.
_MAX_OPS_TO_WALK = 5000


class ErrorMonitorService:
    """Aggregator over Error DAT records + op.errors() output."""

    def __init__(self, error_dat_path: Optional[str] = None):
        # Retained for backward compat with constructor callers. When set, this
        # specific DAT is included in the merge regardless of OPType heuristic.
        self.error_dat_path = error_dat_path
        log_message("ErrorMonitorService initialized (Wave 3 aggregator)", LogLevel.INFO)

    # ------------------------------------------------------------------
    # Source discovery
    # ------------------------------------------------------------------

    def _find_all_error_dats(self, scope_op: Optional[Any] = None) -> List[Any]:
        """Return every Error DAT in the project (or under scope_op if given).

        Replaces the old `_find_error_dat` singleton + 4-path hardcoded list.
        Searches the whole tree by OPType == 'errorDAT'; also honours any
        explicitly-configured path from __init__.
        """
        root = scope_op if scope_op is not None else td.root
        try:
            all_dats = root.findChildren(type=td.DAT) if hasattr(td, "DAT") else []
        except Exception as e:
            log_message(f"findChildren(type=DAT) failed: {e}", LogLevel.WARNING)
            all_dats = []

        error_dats = [d for d in all_dats if getattr(d, "OPType", "") == "errorDAT"]

        # Include the explicitly-configured path if set and not already found.
        if self.error_dat_path:
            configured = td.op(self.error_dat_path)
            if configured is not None and configured.valid and configured not in error_dats:
                error_dats.append(configured)

        return error_dats

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_error_dat(self, error_dat: Any) -> List[Dict[str, Any]]:
        """Extract rows from a single Error DAT into normalized records."""
        records: List[Dict[str, Any]] = []
        try:
            num_rows = error_dat.numRows
        except Exception:
            return records
        if num_rows <= 1:
            return records

        for row_idx in range(1, num_rows):
            try:
                source = self._get_cell(error_dat, row_idx, "source")
                message = self._get_cell(error_dat, row_idx, "message")
                absframe = self._get_cell(error_dat, row_idx, "absframe", default=0)
                frame = self._get_cell(error_dat, row_idx, "frame", default=0)
                severity_raw = self._get_cell(error_dat, row_idx, "severity", default=0)
                op_type = self._get_cell(error_dat, row_idx, "type", default="")

                # numeric str -> int where possible
                try:
                    severity_raw = int(severity_raw)
                except (TypeError, ValueError):
                    pass

                records.append({
                    "source": source,
                    "message": message,
                    "absframe": int(absframe) if str(absframe).strip().lstrip("-").isdigit() else 0,
                    "frame": int(frame) if str(frame).strip().lstrip("-").isdigit() else 0,
                    "severity": SEVERITY_MAP.get(severity_raw, "info"),
                    "type": op_type,
                    "kind": "error_dat",
                    "_dat_path": str(getattr(error_dat, "path", "")),
                    "_row": row_idx,
                })
            except Exception as e:
                log_message(f"Error parsing DAT row {row_idx}: {e}", LogLevel.WARNING)

        return records

    def _parse_op_errors_string(self, error_output: str, fallback_path: str = "/") -> List[Dict[str, Any]]:
        """Parse the string returned by op.errors(recurse=True).

        Format: 'Error message (node_path)\n...' — same parser as
        api_service.get_node_errors. Severity is unknown from this source, so
        we default to 'error' (matches the bug-report intent: these surface
        parameter-expression and cook errors that the Error DAT misses).
        """
        records: List[Dict[str, Any]] = []
        if not error_output:
            return records

        for raw_line in error_output.strip().split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            source = fallback_path
            message = line
            op_type = ""

            # Try to extract `Message (node_path)` form.
            if "(" in line and line.endswith(")"):
                msg_part, path_part = line.rsplit("(", 1)
                candidate = path_part.rstrip(")").strip()
                # Only treat as a node path if it looks like one (starts with /).
                if candidate.startswith("/"):
                    source = candidate
                    message = msg_part.strip()
                    try:
                        node = td.op(source)
                        if node is not None and node.valid:
                            op_type = getattr(node, "OPType", "") or ""
                    except Exception:
                        pass

            records.append({
                "source": source,
                "message": message,
                "absframe": 0,  # not provided by op.errors()
                "frame": 0,
                "severity": "error",  # default for op.errors()-sourced records
                "type": op_type,
                "kind": "op_errors",
            })

        return records

    def _parse_warnings_string(self, warning_output: str, fallback_path: str = "/") -> List[Dict[str, Any]]:
        """Parse op.warnings(recurse=True) output into normalized warning records.

        W-A1: warnings are surfaced (severity 'warning'), BUT any warning that reads
        as a GLSL compile failure is PROMOTED to severity 'error' (kind
        'glsl_compile_failure') so a hard shader break — which leaves errors() empty
        and shows only here — lands in the ERROR bucket of get_error_summary and is
        never silently reported as zero errors. Promotion is by the self-identifying
        banner ("The GLSL Shader has compile errors ...") OR a resolved GLSL-family
        op with a compile-failure message.
        """
        records: List[Dict[str, Any]] = []
        if not warning_output:
            return records

        for raw_line in warning_output.strip().split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            source = fallback_path
            message = line
            op_type = ""
            op_is_glsl = False

            if "(" in line and line.endswith(")"):
                msg_part, path_part = line.rsplit("(", 1)
                candidate = path_part.rstrip(")").strip()
                if candidate.startswith("/"):
                    source = candidate
                    message = msg_part.strip()
                    try:
                        node = td.op(source)
                        if node is not None and node.valid:
                            op_type = getattr(node, "OPType", "") or ""
                            op_is_glsl = is_glsl_family(node)
                    except Exception:
                        pass

            promote = is_glsl_specific_compile_message(message) or (
                op_is_glsl and is_compile_failure_message(message)
            )
            if promote:
                records.append({
                    "source": source,
                    "message": f"GLSL COMPILE FAILURE: {message}",
                    "absframe": 0,
                    "frame": 0,
                    "severity": "error",
                    "type": op_type,
                    "kind": "glsl_compile_failure",
                })
            else:
                records.append({
                    "source": source,
                    "message": message,
                    "absframe": 0,
                    "frame": 0,
                    "severity": "warning",
                    "type": op_type,
                    "kind": "op_warnings",
                })

        return records

    def _get_cell(self, dat: Any, row: int, col_name: str, default: Any = "") -> Any:
        """Safely read a DAT cell by column name, falling back to index."""
        try:
            value = dat[row, col_name]
            return str(value) if value is not None else default
        except Exception:
            pass
        try:
            col_idx = ERROR_DAT_COLUMNS.get(col_name, 0)
            value = dat[row, col_idx]
            return str(value) if value is not None else default
        except Exception:
            return default

    # ------------------------------------------------------------------
    # Aggregator
    # ------------------------------------------------------------------

    def _collect_all_errors(self, scope_path: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Merge Error DAT records + op.errors() output into one normalized list.

        Dedups by (source, message, absframe). Returns (records, notes) where
        notes carries diagnostic info (how many DATs found, whether the
        op.errors() roll-up was used, scope path, etc.).
        """
        scope_op = td.op(scope_path) if scope_path else td.root
        notes: Dict[str, Any] = {
            "scope_path": str(getattr(scope_op, "path", "/")) if scope_op else scope_path,
            "error_dats_found": 0,
            "op_errors_lines": 0,
            "op_warnings_lines": 0,
        }

        all_records: List[Dict[str, Any]] = []

        # Source 1: Error DAT contents (if any exist).
        try:
            error_dats = self._find_all_error_dats(scope_op)
            notes["error_dats_found"] = len(error_dats)
            notes["error_dat_paths"] = [str(d.path) for d in error_dats]
            for dat in error_dats:
                all_records.extend(self._parse_error_dat(dat))
        except Exception as e:
            log_message(f"Error DAT scan failed: {e}", LogLevel.WARNING)
            notes["error_dat_scan_error"] = str(e)

        # Source 2: op.errors(recurse=True) rolled up from scope (catches
        # parameter-expression errors, missing-input errors, cook errors).
        try:
            if scope_op is not None and hasattr(scope_op, "errors") and callable(scope_op.errors):
                error_output = scope_op.errors(recurse=True) or ""
                op_err_records = self._parse_op_errors_string(error_output, fallback_path=str(scope_op.path))
                notes["op_errors_lines"] = len(op_err_records)
                all_records.extend(op_err_records)
        except Exception as e:
            log_message(f"op.errors() roll-up failed: {e}", LogLevel.WARNING)
            notes["op_errors_scan_error"] = str(e)

        # Source 3 (W-A1): op.warnings(recurse=True) rolled up from scope. Surfaces
        # warnings AND promotes GLSL compile failures (empty in errors()) to errors.
        try:
            if scope_op is not None and hasattr(scope_op, "warnings") and callable(scope_op.warnings):
                warning_output = scope_op.warnings(recurse=True) or ""
                w_records = self._parse_warnings_string(warning_output, fallback_path=str(scope_op.path))
                notes["op_warnings_lines"] = len(w_records)
                all_records.extend(w_records)
        except Exception as e:
            log_message(f"op.warnings() roll-up failed: {e}", LogLevel.WARNING)
            notes["op_warnings_scan_error"] = str(e)

        # Dedup by (source, message, absframe). DAT-sourced records win over
        # op_errors-sourced when they share a key (they carry severity).
        deduped: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
        for rec in all_records:
            key = (rec.get("source", ""), rec.get("message", ""), rec.get("absframe", 0))
            existing = deduped.get(key)
            if existing is None or (existing.get("kind") == "op_errors" and rec.get("kind") == "error_dat"):
                deduped[key] = rec

        return list(deduped.values()), notes

    # ------------------------------------------------------------------
    # Public methods (3 tools, one underlying aggregator)
    # ------------------------------------------------------------------

    def get_cook_errors(
        self,
        source_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
        limit: int = 100,
    ) -> Result:
        """Return cook + parameter-expression errors aggregated from all sources."""
        try:
            records, notes = self._collect_all_errors()

            # W-A1: order so a GLSL compile failure is FIRST (and never pushed past
            # the limit), then other errors/fatals, then warnings/info.
            def _rank(rec: Dict[str, Any]) -> int:
                if rec.get("kind") == "glsl_compile_failure":
                    return 0
                if rec.get("severity") in ("fatal", "error"):
                    return 1
                return 2

            records = sorted(records, key=_rank)

            filtered: List[Dict[str, Any]] = []
            for rec in records:
                if source_filter and source_filter not in rec.get("source", ""):
                    continue
                if severity_filter and rec.get("severity") != severity_filter:
                    continue
                filtered.append(rec)
                if len(filtered) >= limit:
                    break

            log_message(
                f"Aggregated {len(filtered)} errors "
                f"(error_dats={notes['error_dats_found']}, op_errors_lines={notes['op_errors_lines']})",
                LogLevel.INFO,
            )

            return {
                "success": True,
                "data": {
                    "errors": filtered,
                    "total_count": len(filtered),
                    "notes": notes,
                },
            }
        except Exception as e:
            log_message(f"get_cook_errors failed: {e}", LogLevel.ERROR)
            return {"success": False, "error": f"Exception aggregating errors: {e}"}

    def get_error_summary(self) -> Result:
        """Bucket aggregated errors by severity; return counts and latest per bucket."""
        try:
            records, notes = self._collect_all_errors()

            summary = {
                "info":    {"count": 0, "latest": None},
                "warning": {"count": 0, "latest": None},
                "error":   {"count": 0, "latest": None},
                "fatal":   {"count": 0, "latest": None},
            }

            for rec in records:
                sev = rec.get("severity", "info")
                bucket = summary.get(sev)
                if bucket is None:
                    continue
                bucket["count"] += 1
                # Keep latest by absframe (when available; op_errors records have 0).
                if bucket["latest"] is None or rec.get("absframe", 0) > bucket["latest"].get("absframe", 0):
                    bucket["latest"] = rec

            return {
                "success": True,
                "data": {
                    "summary": summary,
                    "total_count": len(records),
                    "notes": notes,
                },
            }
        except Exception as e:
            log_message(f"get_error_summary failed: {e}", LogLevel.ERROR)
            return {"success": False, "error": f"Exception summarizing errors: {e}"}

    def get_python_exceptions(self, limit: int = 50) -> Result:
        """Filter aggregated records for Python-flavored exceptions."""
        try:
            records, notes = self._collect_all_errors()

            exceptions: List[Dict[str, Any]] = []
            for rec in records:
                if len(exceptions) >= limit:
                    break
                # W-A1 folded op.warnings() into the shared aggregator for the three
                # authorized error tools (get_td_node_errors/get_error_summary/
                # get_cook_errors). get_python_exceptions was NOT in that scope, and
                # its `"dat" in op_type` heuristic below would misclassify any plain
                # DAT-family warning (op_type contains "DAT") as a Python exception.
                # Keep this tool to its pre-wave sources (Error DAT rows + op.errors())
                # by dropping the warnings-sourced kinds. A GLSL compile failure is a
                # shader break, not a Python exception, so it is excluded too.
                if rec.get("kind") in ("op_warnings", "glsl_compile_failure"):
                    continue
                op_type = (rec.get("type") or "").lower()
                message = rec.get("message") or ""
                is_python = (
                    "python" in op_type
                    or "script" in op_type
                    or "dat" in op_type
                    or "Traceback" in message
                    or "Exception" in message
                    or "Error:" in message
                    or "NameError" in message
                    or "AttributeError" in message
                    or "TypeError" in message
                    or "ValueError" in message
                    or "SyntaxError" in message
                )
                if is_python:
                    exceptions.append(rec)

            return {
                "success": True,
                "data": {
                    "exceptions": exceptions,
                    "total_count": len(exceptions),
                    "notes": notes,
                },
            }
        except Exception as e:
            log_message(f"get_python_exceptions failed: {e}", LogLevel.ERROR)
            return {"success": False, "error": f"Exception filtering Python errors: {e}"}

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear_errors(self) -> Result:
        """Clear every Error DAT we can find (best-effort)."""
        try:
            error_dats = self._find_all_error_dats()
            if not error_dats:
                return {"success": False, "error": "No Error DAT found"}

            cleared = []
            for dat in error_dats:
                if hasattr(dat, "clear") and callable(dat.clear):
                    try:
                        dat.clear()
                        cleared.append(str(dat.path))
                    except Exception as e:
                        log_message(f"Failed to clear {dat.path}: {e}", LogLevel.WARNING)

            if not cleared:
                return {"success": False, "error": "Error DATs found but none support clear()"}

            return {"success": True, "data": {"cleared_paths": cleared}}
        except Exception as e:
            return {"success": False, "error": f"Exception clearing errors: {e}"}


# Singleton instance for use by controllers
error_monitor = ErrorMonitorService()

"""
TouchDesigner MCP Web Server API Service Implementation
Provides API functionality related to TouchDesigner
"""

import ast
import contextlib
import datetime
import hashlib
import importlib
import inspect
import io
import os
import pydoc
import shutil
from typing import Any, Optional, Protocol

import td
import tdu  # B16 — expose tdu helpers (Color, Position, Vector, Dependency, ...) to user scripts
from utils.logging import log_message
from utils.result import error_result, success_result
from utils.serialization import safe_serialize
from utils.types import LogLevel, Result
from utils.version import get_mcp_api_version


class IApiService(Protocol):
	"""API service interface"""

	def get_td_info(self) -> Result: ...
	def get_td_python_classes(self, mode: str = "full") -> Result: ...
	def get_td_python_class_details(self, class_name: str) -> Result: ...
	def get_module_help(self, module_name: str, mode: str = "summary") -> Result: ...
	def get_node_detail(self, node_path: str) -> Result: ...
	def get_node_errors(self, node_path: str, recurse: bool = True) -> Result: ...
	def update_node(self, node_path: str, properties: dict[str, Any]) -> Result: ...
	def exec_node_method(
		self, node_path: str, method: str, args: list, kwargs: dict
	) -> Result: ...


class _NoContextSentinel:
	"""B16 — placeholder for `me` and `parent` in exec_python_script.

	These TD names are contextual bindings whose values depend on the operator
	a script runs inside. exec_python_script runs scripts from the WebServer
	DAT context, where `td.op.me` doesn't exist and `td.parent()` resolves to
	`/mcp_webserver_base` (MCP infrastructure). Returning that to user code
	silently misleads — every attribute access misfires somewhere unhelpful.

	Each instance raises a clear RuntimeError when accessed, pointing the
	caller at the abs-path workaround.
	"""

	def __init__(self, name: str, hint: str):
		self._name = name
		self._hint = hint

	def __getattr__(self, attr):
		raise RuntimeError(
			f"`{self._name}` is not available in exec_python_script — {self._hint} "
			f"(attempted: {self._name}.{attr})"
		)

	def __call__(self, *args, **kwargs):
		raise RuntimeError(
			f"`{self._name}()` is not available in exec_python_script — {self._hint}"
		)

	def __repr__(self):
		return f"<unavailable: {self._name}>"


class TouchDesignerApiService(IApiService):
	"""Implementation of the TouchDesigner API service"""

	def __init__(self):
		# Session-start safety net: TD's auto-backup only fires on save, and API
		# mutations skip the undo stack. Before the FIRST mutating call per server
		# process we COPY the last-saved .toe to a restore point — a pure filesystem
		# copy via _snapshot_toe(), never project.save(), so no modal dialog can hang
		# the WebServer thread. Guarded by _session_saved → at most one copy per process.
		self._session_saved = False
		# Diagnosable outcome of that copy so a swallowed failure (e.g. a Windows
		# deny-read lock on the open .toe) is observable via get_td_info, not just an
		# invisible log line. One of: "not_run" | "ok: <path>" | "skipped: <reason>"
		# | "unavailable: <reason>".
		self._restore_point_status = "not_run"

		# --- D3 (W6a): live-mutation recovery + explicit-checkpoint state. Layered
		# strictly BELOW PR #21's restore-point block above (which is byte-frozen).
		# All fields are per-process (reset on TD restart, like _session_saved).
		self._mutation_seq = 0             # 0 = no API mutation yet; first commit -> 1
		self._last_mutation = None         # {seq, tool, target, timestamp, outcome}
		self._dirty_since_snapshot = False  # >=1 API mutation since last EXPLICIT snapshot
		self._last_snapshot = None         # {path, source_mtime, at_seq} — save_td_project
		self._restore_point_meta = None    # {source_mtime, at_seq} — implicit restore point

	def _ensure_session_restore_point(self) -> None:
		"""Copy the last-saved .toe to a restore point once, before the first mutation.

		API mutations skip TD's undo stack and auto-backup only fires on save, so we
		capture a whole-project restore point. This is a PURE FILESYSTEM COPY
		(_snapshot_toe) of the on-disk .toe — it never calls project.save(), so no TD
		modal dialog can be raised in ANY project state, and it never rebinds the
		project identity or increments the filename. It does NOT touch the .tox the
		component was imported from.

		Why not project.save()? TD has no silent non-rebinding save-a-copy: no-arg
		project.save() writes the real file AND increments to <name>.2.toe (and if that
		increment target already exists, pops an OVERWRITE-confirmation modal), while
		project.save(<path>) is Save-As and REBINDS project.name/folder/path. Either
		form can raise a modal, and the WebServer DAT's onHTTPRequest runs on TD's
		single main thread — a modal there freezes the whole connection (~60 s hang, no
		timeout rescue, cannot be dismissed programmatically). A filesystem copy
		sidesteps all of it.

		Tradeoff: captures LAST-SAVED on-disk state, not unsaved in-memory edits.

		Best-effort: any failure is recorded in _restore_point_status (surfaced via
		get_td_info) and logged; the mutation always proceeds.
		"""
		if self._session_saved:
			return
		# Set the flag first: once-per-session regardless of outcome.
		self._session_saved = True
		try:
			src = os.path.join(td.project.folder, td.project.name)
			if not os.path.exists(src):
				# GENUINELY never-saved ONLY — keyed on FILE EXISTENCE, never on the
				# name. A SAVED project whose name is "untitled.toe"/"NewProject.1.toe"
				# EXISTS on disk → takes the copy branch below (do NOT add a name
				# heuristic). With nothing on disk there is nothing to copy, and every
				# save form would dialog or rebind → skip (best-effort).
				self._restore_point_status = "skipped: project not saved to disk"
				log_message(
					"Session restore point skipped: project not yet saved to disk "
					"(save once to enable restore points).",
					LogLevel.INFO,
				)
				return
			dst = self._restore_point_path(src)
			self._snapshot_toe(src, dst)  # dialog-free by construction
			self._restore_point_status = f"ok: {dst}"
			log_message(
				f"Session restore point: copied last-saved {src} -> {dst} "
				f"(unsaved in-session edits are NOT captured).",
				LogLevel.INFO,
			)
		except Exception as e:  # noqa: BLE001 — safety net must not block work
			self._restore_point_status = f"unavailable: {e}"
			log_message(
				f"Session restore-point copy failed (continuing): {e}",
				LogLevel.WARNING,
			)

	@staticmethod
	def _restore_point_path(src: str) -> str:
		"""Stable per-project restore target in a dedicated dir.

		~/.td_builder/restore_points/<stem>.<hash>.toe — keeps the artist's project
		folder clean and reuses the ~/.td_builder convention (utils/auth.py). The hash
		of the ABSOLUTE source path disambiguates projects that share a basename
		(scene.toe in different folders) so they never clobber each other in the flat
		dir. TD_RESTORE_DIR overrides the base dir (advanced users; and hermetic tests
		redirect writes away from the real $HOME).
		"""
		base = os.environ.get("TD_RESTORE_DIR") or os.path.join(
			os.path.expanduser("~"), ".td_builder", "restore_points"
		)
		stem = os.path.splitext(os.path.basename(src))[0]
		key = hashlib.sha1(
			os.path.normcase(os.path.abspath(src)).encode("utf-8")
		).hexdigest()[:16]
		return os.path.join(base, f"{stem}.{key}.toe")

	@staticmethod
	def _snapshot_toe(src: str, dst: str) -> None:
		"""Dialog-free .toe snapshot: atomically copy src -> dst.

		ONLY filesystem ops (makedirs + copyfile + os.replace) → cannot raise a TD
		modal in ANY state; it either succeeds or raises a Python exception the caller
		handles. Atomic: copy to <dst>.tmp then os.replace, so a crash mid-copy never
		leaves a truncated restore point. `tmp` MUST stay colocated with `dst` (same
		dir/volume) so os.replace is an atomic same-volume rename — do not relocate it
		or a cross-device os.replace re-emerges (copyfile itself is fine cross-volume).

		RAISES on I/O failure; callers choose best-effort (swallow, as the session
		restore point does) vs fail-fast (JSON error, as a future explicit save tool
		will). Shared dialog-proof primitive — reused by [D3] save_td_project.
		"""
		os.makedirs(os.path.dirname(dst), exist_ok=True)
		tmp = dst + ".tmp"  # colocated with dst — see docstring
		try:
			shutil.copyfile(src, tmp)
			os.replace(tmp, dst)
		finally:
			if os.path.exists(tmp):
				try:
					os.remove(tmp)  # clean a partial temp on failure
				except OSError:
					pass

	def get_td_info(self) -> Result:
		"""Get information about the TouchDesigner server"""

		version = td.app.version
		build = td.app.build

		# Surface the session restore-point outcome so the AI can tell the user where
		# rollback lives — and, critically, so a SILENTLY-swallowed copy failure (e.g.
		# a Windows deny-read lock on the open .toe) is observable rather than an
		# invisible log line. _restore_point_status is "<word>: <detail>" (or
		# "not_run"); split it into a structured field.
		word, _, rest = self._restore_point_status.partition(": ")
		restore_point = {
			"status": word,                       # not_run | ok | skipped | unavailable
			"path": rest if word == "ok" else None,
			"detail": rest or None,
		}

		server_info = {
			"server": f"TouchDesigner {version}.{build}",
			"version": f"{version}.{build}",
			"osName": td.app.osName,
			"osVersion": td.app.osVersion,
			"mcpApiVersion": get_mcp_api_version(),
			"restorePoint": restore_point,
		}

		return success_result(server_info)

	# =====================================================================
	# D3 (W6a): explicit checkpoint + live-mutation recovery. Everything below
	# LAYERS ON TOP of PR #21's frozen restore-point regions
	# (_ensure_session_restore_point / _restore_point_path / _snapshot_toe /
	# get_td_info's restorePoint block) — none of those are modified.
	# =====================================================================

	@staticmethod
	def _iso_mtime(mtime: float) -> str:
		"""ISO-8601 of a filesystem mtime — the artist's last-save time, not now()."""
		return datetime.datetime.fromtimestamp(mtime).isoformat()

	@staticmethod
	def _now_iso() -> str:
		return datetime.datetime.now().isoformat()

	def _restore_point_triple(self) -> dict:
		"""Structured {status, path, detail} parse of _restore_point_status.

		Same shape get_td_info builds inline (that block is #21-frozen) — a parallel
		helper so the mutator envelopes can stamp it without touching #21's code.
		"""
		word, _, rest = self._restore_point_status.partition(": ")
		return {
			"status": word,                       # not_run | ok | skipped | unavailable
			"path": rest if word == "ok" else None,
			"detail": rest or None,
		}

	def _restore_point_extended(self) -> dict:
		"""M1: the triple + the IMPLICIT restore point's staleness fields.

		source_mtime/at_seq come from _restore_point_meta and are surfaced ONLY when
		the copy actually landed (status 'ok'); null otherwise, so a caller never
		reads a skipped/failed snapshot's timing as if it were a live rollback point.
		"""
		triple = self._restore_point_triple()
		meta = self._restore_point_meta or {}
		ok = triple["status"] == "ok"
		return {
			**triple,
			"source_mtime": meta.get("source_mtime") if ok else None,
			"at_seq": meta.get("at_seq") if ok else None,
		}

	def _ensure_restore_point_tracked(self) -> None:
		"""Caller-layer wrapper over the FROZEN _ensure_session_restore_point().

		copyfile does not preserve mtime, so the implicit restore point's source
		mtime exists only at copy time — capture it here (pre-copy) so the recovery
		contract can disclose how stale the DEFAULT rollback target is. Records
		_restore_point_meta {source_mtime, at_seq: 0} iff the copy landed (status
		'ok'); at_seq is 0 by construction (the copy fires before the first mutation
		commit). Never blocks the mutation. The §11 spy targets the underlying
		_ensure_session_restore_point, which this invokes transitively.
		"""
		if self._session_saved:
			return
		src_mtime = None
		try:
			src = os.path.join(td.project.folder, td.project.name)
			if os.path.exists(src):
				src_mtime = self._iso_mtime(os.path.getmtime(src))
		except Exception:  # noqa: BLE001 — a stat failure must never block work
			src_mtime = None
		self._ensure_session_restore_point()  # FROZEN primitive (best-effort)
		if self._restore_point_status.startswith("ok"):
			self._restore_point_meta = {"source_mtime": src_mtime, "at_seq": 0}

	def _record_mutation(self, tool: str, target: str, outcome: str = "ok") -> None:
		"""Single commit-point increment: bump the seq receipt, record the last
		mutation, mark the session dirty since the last EXPLICIT snapshot. The one
		server-side seq source; the future D4-live half reads it off the envelope.
		"""
		self._mutation_seq += 1
		self._last_mutation = {
			"seq": self._mutation_seq,
			"tool": tool,
			"target": target,
			"timestamp": self._now_iso(),
			"outcome": outcome,
		}
		self._dirty_since_snapshot = True

	def _stamp_mutation(
		self, data: dict, tool: str, target: str, outcome: str = "ok"
	) -> dict:
		"""OBS-1: record the mutation, then stamp mutation_seq + restorePoint into the
		mutator's response data so a client that never calls get_td_info still sees a
		skipped/unavailable restore point. Returns data for inline use."""
		self._record_mutation(tool, target, outcome)
		data["mutation_seq"] = self._mutation_seq
		data["restorePoint"] = self._restore_point_triple()
		return data

	@staticmethod
	def _explicit_snapshot_targets(src: str) -> list:
		"""Ordered checkpoint targets for save_td_project (D-R2, EXPLICIT-only).

		Primary: <project_folder>/Backup/<stem>.tdbuilder-restore.toe — mirrors TD's
		own discoverable Backup/ convention for human-initiated checkpoints, with a
		DISTINCT suffix so it never collides with (or is mistaken for) TD's own
		<name>.<n>.toe auto-increments (Windows Backup/ is case-insensitive).
		Fallback: the dedicated restore-dir (~/.td_builder/restore_points/,
		TD_RESTORE_DIR-overridable), abs-path-hashed so same-basename projects never
		clobber each other AND kept distinct (by suffix) from the implicit restore
		point's <stem>.<hash>.toe. save_project tries these in order; only if BOTH
		raise does it fail-fast. The IMPLICIT restore point (PR #21) is untouched —
		it keeps its own frozen _restore_point_path target in the restore-dir.
		"""
		stem = os.path.splitext(os.path.basename(src))[0]
		targets = []
		folder = os.path.dirname(src)
		if folder and os.path.isdir(folder):
			targets.append(
				os.path.join(folder, "Backup", f"{stem}.tdbuilder-restore.toe")
			)
		base = os.environ.get("TD_RESTORE_DIR") or os.path.join(
			os.path.expanduser("~"), ".td_builder", "restore_points"
		)
		key = hashlib.sha1(
			os.path.normcase(os.path.abspath(src)).encode("utf-8")
		).hexdigest()[:16]
		targets.append(os.path.join(base, f"{stem}.{key}.tdbuilder-restore.toe"))
		return targets

	def save_project(self) -> Result:
		"""Client-callable checkpoint (D3): a dialog-proof filesystem copy of the
		last-saved .toe. Wraps the shared _snapshot_toe primitive — NEVER
		project.save(), never an inline copyfile — so it cannot raise a TD modal in
		ANY project state. Writes to <project_folder>/Backup/ (falls back to the
		restore-dir); fail-fast JSON error on failure. Does NOT set _session_saved
		(independent of the implicit restore point) and never rebinds project
		identity (no TD API call at all).

		Captures LAST-MANUAL-SAVE state only — there is no dialog-safe way to flush
		in-memory edits — so source_mtime discloses exactly how stale the copy is.
		"""
		try:
			src = os.path.join(td.project.folder, td.project.name)
		except Exception as e:  # noqa: BLE001
			return error_result(f"Cannot resolve the project path: {e}")
		if not os.path.exists(src):
			# Keyed on FILE EXISTENCE, never the name (matches the implicit guard):
			# nothing on disk to copy, and every save form would dialog or rebind.
			return error_result(
				"Project has never been saved to disk — save it once (Ctrl+S) first, "
				"then retry. There is nothing on disk to checkpoint."
			)
		try:
			pre_mtime = os.path.getmtime(src)  # pre-copy: the ARTIST's save time [m7]
		except OSError as e:
			return error_result(f"Cannot stat the project file: {e}")
		source_mtime = self._iso_mtime(pre_mtime)

		last_err = None
		dst_used = None
		for dst in self._explicit_snapshot_targets(src):
			try:
				self._snapshot_toe(src, dst)  # dialog-proof; raises on I/O failure
				dst_used = dst
				break
			except Exception as e:  # noqa: BLE001 — try the fallback target next
				last_err = e
		if dst_used is None:
			return error_result(
				f"Checkpoint failed — could not write a snapshot to the project "
				f"Backup folder or the restore dir: {last_err}"
			)

		# D-R6: a single at-copy-time stat cannot see an EXTERNAL writer mutating src
		# mid-copy; re-stat after the copy and flag a possibly-torn snapshot. The
		# primitive stays byte-untouched — this lives entirely in the caller.
		warning = None
		try:
			if os.path.getmtime(src) != pre_mtime:
				warning = (
					"the source .toe changed on disk during the copy; the snapshot may "
					"be torn (a mix of old and new bytes). Re-run save_td_project."
				)
		except OSError:
			pass

		# Set the explicit-snapshot state atomically with clearing the dirty flag [m6]
		# (source_mtime/at_seq cannot be reconstructed later, so they persist here).
		self._last_snapshot = {
			"path": dst_used,
			"source_mtime": source_mtime,
			"at_seq": self._mutation_seq,
		}
		self._dirty_since_snapshot = False

		data = {
			"saved": True,
			"captured": "last_saved",          # the only value — no in-memory flush
			"path": dst_used,
			"source_path": src,
			"source_mtime": source_mtime,
			"rebound": False,
			"mutation_seq": self._mutation_seq,  # receipt only, never a gate
			"message": (
				f"Checkpoint written to {dst_used} (captures the last-saved state as "
				f"of {source_mtime})."
			),
		}
		if warning:
			data["warning"] = warning
		return success_result(data)

	def get_mutation_status(self) -> Result:
		"""Post-timeout reconciliation surface (D3). AUTHENTICATED — deliberately NOT
		folded into the tokenless get_td_info. last_snapshot backs the explicit
		checkpoint; restore_point exposes the implicit PR #21 target + its staleness
		fields (M1). A client polls this after a timeout to learn what committed."""
		return success_result({
			"last_committed_seq": self._mutation_seq,
			"last_mutation": self._last_mutation,
			"api_dirty_since_snapshot": self._dirty_since_snapshot,
			"last_snapshot": self._last_snapshot,
			"restore_point": self._restore_point_extended(),
		})

	def get_td_python_classes(self, mode: str = "full") -> Result:
		"""Get list of Python classes and modules available in TouchDesigner.

		B25 — mode parameter controls response size:
		  "full"    (default): every class with full docstring (~50k tokens, current behavior)
		  "summary": category counts only (~150 tokens)
		  "names":   sorted name list, no descriptions (~1-2k tokens)
		"""
		mode = (mode or "full").strip().lower()

		if mode == "summary":
			categories = {
				"baseClasses": 0,    # Non-op classes (Color, Vector, Position, ...)
				"opSubclasses": 0,   # CHOP/TOP/SOP/MAT/DAT/COMP/POP families
				"singletons": 0,     # Module-level singletons (app, project, ui, ...)
				"exceptions": 0,     # Exception subclasses
			}
			op_suffixes = ("CHOP", "TOP", "SOP", "MAT", "DAT", "COMP", "POP")
			for name, obj in inspect.getmembers(td):
				if name.startswith("_"):
					continue
				try:
					if inspect.isclass(obj) and issubclass(obj, BaseException):
						categories["exceptions"] += 1
					elif inspect.isclass(obj) and any(name.endswith(s) for s in op_suffixes):
						categories["opSubclasses"] += 1
					elif inspect.isclass(obj):
						categories["baseClasses"] += 1
					else:
						categories["singletons"] += 1
				except Exception:
					categories["singletons"] += 1
			return success_result({
				"mode": "summary",
				"categories": categories,
				"total": sum(categories.values()),
			})

		if mode == "names":
			names = sorted(
				name for name in dir(td) if not name.startswith("_")
			)
			return success_result({
				"mode": "names",
				"names": names,
				"total": len(names),
			})

		# Default: full — preserves existing response shape.
		classes = []
		for name, obj in inspect.getmembers(td):
			if name.startswith("_"):
				continue
			description = inspect.getdoc(obj) or ""
			classes.append({"name": name, "description": description})
		return success_result({"mode": "full", "classes": classes})

	def get_td_python_class_details(self, class_name: str) -> Result:
		"""Get detailed information about a specific Python class or module"""

		obj = None
		if hasattr(td, class_name):
			obj = getattr(td, class_name)
			log_message(f"Found {class_name} in td module", LogLevel.DEBUG)
		else:
			log_message(f"Class not found: {class_name}", LogLevel.WARNING)
			return error_result(f"Class or module not found: {class_name}")

		methods = []
		properties = []

		for name, member in inspect.getmembers(obj):
			if name.startswith("_"):
				continue

			try:
				info = {
					"name": name,
					"description": inspect.getdoc(member) or "",
					"type": type(member).__name__,
				}
				if (
					inspect.isfunction(member)
					or inspect.ismethod(member)
					or inspect.ismethoddescriptor(member)
				):
					methods.append(info)
				else:
					properties.append(info)
			except Exception as e:
				log_message(
					f"Error processing member {name}: {str(e)}", LogLevel.WARNING
				)

		if inspect.isclass(obj):
			type_info = inspect.classify_class_attrs(obj)[0].kind
		else:
			type_info = type(obj).__name__

		class_details = {
			"name": class_name,
			"type": type_info,
			"description": inspect.getdoc(obj) or "",
			"methods": methods,
			"properties": properties,
		}

		return success_result(class_details)

	def get_module_help(self, module_name: str, mode: str = "summary") -> Result:
		"""Get Python help() output for a module or class.

		W6.2 (B35) — `mode` controls response size:
		  "summary" (default): short overview — type, first-line docstring,
		    public attribute list (first 20). ~1-3 KB.
		  "full": complete pydoc.render_doc() text. NO cap — the caller has
		    explicitly opted in. Note: `target='td'` produces ~35 MB; narrow
		    to e.g. 'td.OP' for a sane size.

		Default was changed from full to summary because `pydoc.render_doc(td)`
		measured 34,988,767 chars (~35 MB) in live probe — far beyond any
		reasonable MCP response budget.
		"""

		target = self._resolve_help_target(module_name)
		if target is None:
			log_message(f"Module not found: {module_name}", LogLevel.WARNING)
			return error_result(f"Module not found: {module_name}")

		try:
			mode_norm = (mode or "summary").strip().lower()
			if mode_norm == "summary":
				attrs = sorted([a for a in dir(target) if not a.startswith("_")])
				raw_doc = (getattr(target, "__doc__", "") or "").strip()
				first_line = raw_doc.split("\n", 1)[0] if raw_doc else ""
				lines = [
					f"Help summary for {module_name}",
					"",
					f"  Type: {type(target).__name__}",
				]
				if first_line:
					lines.append(f"  Docstring: {first_line}")
				attr_preview = ", ".join(attrs[:20])
				suffix = "..." if len(attrs) > 20 else ""
				lines.append(
					f"  Public attributes ({len(attrs)}): {attr_preview}{suffix}"
				)
				lines.append("")
				lines.append(
					f"  For full text, call with mode='full' AND a narrower target"
				)
				lines.append(
					f"  (e.g. '{module_name}.OP' or '{module_name}.CHOP')."
				)
				help_text = "\n".join(lines)
			elif mode_norm == "full":
				# No cap — caller has explicitly opted in.
				help_text = self._normalize_help_text(pydoc.render_doc(target))
			else:
				return error_result(
					f"Invalid mode {mode!r}; must be 'summary' or 'full'"
				)
		except Exception as exc:  # noqa: BLE001
			log_message(
				f"Error generating help for {module_name}: {str(exc)}",
				LogLevel.ERROR,
			)
			return error_result(
				f"Failed to get help for {module_name}: {str(exc)}",
			)

		log_message(
			f"Retrieved help for {module_name} (mode={mode_norm}, {len(help_text)} chars)",
			LogLevel.DEBUG,
		)
		return success_result(
			{
				"moduleName": module_name,
				"mode": mode_norm,
				"helpText": help_text,
			}
		)

	def get_node(self, node_path: str) -> Result:
		"""Alias for get_node_detail for backwards compatibility"""
		return self.get_node_detail(node_path)

	def get_node_detail(self, node_path: str) -> Result:
		"""Get node at the specified path"""

		node = td.op(node_path)

		if node is None or not node.valid:
			return error_result(f"Node not found at path: {node_path}")

		node_info = self._get_node_summary(node)
		return success_result(node_info)

	def get_node_errors(self, node_path: str, recurse: bool = True) -> Result:
		"""Collect error messages for the specified node, optionally including descendants.

		B17 — `recurse` was previously hardcoded True; the caller's flag was discarded.
		"""

		node = td.op(node_path)

		if node is None or not node.valid:
			return error_result(f"Node not found at path: {node_path}")

		# Use TouchDesigner's built-in errors() method
		all_errors = []
		if hasattr(node, "errors") and callable(node.errors):
			try:
				# errors(recurse=...) returns a string with newline-separated error messages
				error_output = node.errors(recurse=recurse)
				if error_output:
					# Parse the error output into structured data
					error_lines = error_output.strip().split("\n")
					for line in error_lines:
						line = line.strip()
						if line:
							# Extract node path from error message if present
							# Format: "Error message (node_path)"
							if "(" in line and line.endswith(")"):
								message_part, path_part = line.rsplit("(", 1)
								error_node_path = path_part.rstrip(")")
								message = message_part.strip()

								# Try to get the actual node to extract more info
								error_node = td.op(error_node_path)
								if error_node and error_node.valid:
									all_errors.append(
										{
											"nodePath": error_node.path,
											"nodeName": error_node.name,
											"opType": error_node.OPType,
											"message": message,
										}
									)
								else:
									all_errors.append(
										{
											"nodePath": error_node_path,
											"nodeName": "",
											"opType": "",
											"message": message,
										}
									)
							else:
								# Simple error message without node path
								all_errors.append(
									{
										"nodePath": node.path,
										"nodeName": node.name,
										"opType": node.OPType,
										"message": line,
									}
								)
			except Exception as e:
				log_message(
					f"Error getting errors from node {node_path}: {str(e)}",
					LogLevel.WARNING,
				)

		return success_result(
			{
				"nodePath": node.path,
				"nodeName": node.name,
				"opType": node.OPType,
				"errorCount": len(all_errors),
				"hasErrors": bool(all_errors),
				"errors": all_errors,
			}
		)

	def get_nodes(
		self,
		parent_path: str,
		pattern: Optional[str] = None,
		include_properties: bool = False,
		limit: Optional[int] = None,
	) -> Result:
		"""Get nodes under the specified parent path, optionally filtered by pattern

		Args:
		    parent_path: Path to the parent node
		    pattern: Pattern to filter nodes by name (e.g. "text*" for all nodes starting with "text")
		    include_properties: Whether to include full node properties (default False for better performance)
		    limit: Max children to return. Defaults to 200 server-side when None; the
		        response is sliced to this many and flagged truncated when the parent has
		        more children. Counts (totalCount/returnedCount/truncated) are ALWAYS emitted.

		Returns:
		    Result: Success with list of nodes or error
		"""

		parent_node = td.op(parent_path)
		if parent_node is None or not parent_node.valid:
			return error_result(f"Parent node not found at path: {parent_path}")

		if pattern:
			log_message(
				f"Calling parent_node.findChildren(name='{pattern}')",
				LogLevel.DEBUG,
			)
			nodes = parent_node.findChildren(name=pattern)
		else:
			log_message("Calling parent_node.findChildren(depth=1)", LogLevel.DEBUG)
			nodes = parent_node.findChildren(depth=1)

		if include_properties:
			node_summaries = [self._get_node_summary(node) for node in nodes]
		else:
			node_summaries = [self._get_node_summary_light(node) for node in nodes]

		# Server-side default cap so a runaway child count still produces a loud,
		# self-describing truncation flag instead of an unbounded response.
		effective_limit = limit if limit is not None else 200
		total = len(node_summaries)
		shown = node_summaries[:effective_limit]
		return success_result(
			{
				"nodes": shown,
				"totalCount": total,
				"returnedCount": len(shown),
				"truncated": total > len(shown),
			}
		)

	def create_node(
		self,
		parent_path: str,
		node_type: str,
		node_name: Optional[str] = None,
		parameters: Optional[dict[str, Any]] = None,
	) -> Result:
		"""Create a new node under the specified parent path"""

		self._ensure_restore_point_tracked()
		parent_node = td.op(parent_path)
		if parent_node is None or not parent_node.valid:
			return error_result(
				f"Parent node not found at path: {parent_path}",
			)

		# B15 — when no name is supplied, use 1-arg create() so TD auto-names
		# (math1, math2, ...). Passing node_name=None to the 2-arg form produces
		# a node literally named "None".
		if node_name is None:
			new_node = parent_node.create(node_type)
		else:
			new_node = parent_node.create(node_type, node_name)

		if new_node is None or not new_node.valid:
			return error_result(
				f"Failed to create node of type {node_type} under {parent_path}"
			)

		if parameters and isinstance(parameters, dict):
			for prop_name, prop_value in parameters.items():
				try:
					if hasattr(new_node.par, prop_name):
						par = getattr(new_node.par, prop_name)
						if hasattr(par, "val"):
							# W6.1 (B33) — accept dict-shape values for mode-aware writes.
							self._apply_property(par, prop_value)
					elif hasattr(new_node, prop_name):
						prop = getattr(new_node, prop_name)
						if isinstance(prop, (int, float, str)):
							setattr(new_node, prop_name, prop_value)
				except Exception as e:
					log_message(
						f"Error setting parameter {prop_name} on new node: {str(e)}",
						LogLevel.WARNING,
					)

		node_info = self._get_node_summary(new_node)
		# W6.3 (B36) — surface path/name/type at top-level data so existing
		# clients (td_live_client.py:436-438 reads data['path']) get a useful
		# string instead of falling back to 'unknown'. Keep `result` nested for
		# any caller already reading the full node summary there.
		return success_result(self._stamp_mutation({
			"path": new_node.path,
			"name": new_node.name,
			"type": new_node.OPType,
			"result": node_info,
		}, "create_node", new_node.path))

	def delete_node(self, node_path: str) -> Result:
		"""Delete the node at the specified path"""

		self._ensure_restore_point_tracked()
		node = td.op(node_path)
		if node is None or not node.valid:
			return error_result(f"Node not found at path: {node_path}")

		node_info = self._get_node_summary(node)
		node.destroy()

		if td.op(node_path) is None:
			log_message(f"Node deleted successfully: {node_path}", LogLevel.DEBUG)
			return success_result(self._stamp_mutation(
				{"deleted": True, "node": node_info}, "delete_node", node_path))
		else:
			log_message(
				f"Failed to verify node deletion: {node_path}", LogLevel.WARNING
			)
			return error_result(f"Failed to delete node: {node_path}")

	def exec_node_method(
		self, node_path: str, method: str, args: list, kwargs: dict
	) -> Result:
		"""Call method on the specified node"""

		self._ensure_restore_point_tracked()
		node = td.op(node_path)
		if node is None or not node.valid:
			return error_result(f"Node not found at path: {node_path}")

		if not hasattr(node, method):
			return error_result(f"Method {method} not found on node {node_path}")

		method = getattr(node, method)
		if not callable(method):
			return error_result(f"{method} is not a callable method")

		result = method(*args, **kwargs)

		log_message(
			f"Method: {method}, args: {args}, kwargs: {kwargs}, result: {result}",
			LogLevel.DEBUG,
		)
		log_message(
			f"Method execution complete, result type: {type(result).__name__}",
			LogLevel.DEBUG,
		)

		processed_result = self._process_method_result(result)

		return success_result(self._stamp_mutation(
			{"result": processed_result}, "exec_node_method", node_path))

	def exec_python_script(self, script: str) -> Result:
		"""Execute a Python script directly in TouchDesigner

		Args:
		    script (str): The Python script to execute

		Returns:
		    Result: Success result with execution output or error result with message
		"""

		self._ensure_restore_point_tracked()

		# B16 — verified-available globals (probed via hasattr(td, ...) in live TD,
		# 2026-05-14). `me` and `parent` get sentinels — they would otherwise be
		# misleading (no node context; td.parent() resolves to /mcp_webserver_base).
		# Names without `hasattr(td, ...)` (runEnv, clamp) are intentionally absent
		# so users get a clean `NameError` instead of `AttributeError: 'NoneType'`.

		# place(host, x, y): position an op AND its docked children as a group. TD has no
		# native group-move (only op.docked + per-op nodeX/nodeY), so this is injected as a
		# built-in layout helper. See the td-builder-howto skill, "Place every node".
		def place(host, x, y):
			host.nodeX, host.nodeY = x, y
			for i, child in enumerate(host.docked):
				child.nodeX, child.nodeY = x + i * 160, y - 120
			return host

		local_vars = {
			# Workhorse functions
			"op":        td.op,
			"ops":       td.ops,
			"td":        td,
			"tdu":       tdu,
			# Network roots / state
			"project":   td.project,
			"root":      td.root,
			"absTime":   td.absTime,
			"app":       td.app,
			"ui":        td.ui,
			# Contextual shortcuts — exist as TD attrs; values may be unhelpful
			# in this context, but standard TD scripts reference them.
			"iop":       td.iop,
			"ipar":      td.ipar,
			"ext":       td.ext,
			"mod":       td.mod,
			# System info
			"families":  td.families,
			"monitors":  td.monitors,
			"licenses":  td.licenses,
			"sysinfo":   td.sysinfo,
			# Sentinels for misleading contextual names
			"me":        _NoContextSentinel(
				"me",
				"scripts run outside any node. Use absolute paths via op('/abs/path').",
			),
			"parent":    _NoContextSentinel(
				"parent",
				"`parent` resolves to MCP infrastructure (/mcp_webserver_base) from this context, "
				"not your project. Use op('/abs/path/to/parent') instead.",
			),
			# Output channel
			"result":    None,
			# Layout helper (def'd above): move an op + its docked children as a group.
			"place":     place,
		}

		stdout_capture = io.StringIO()
		stderr_capture = io.StringIO()

		# Parse once, then run the script EXACTLY once. The previous implementation
		# re-eval()'d the last source line to capture a return value, which
		# double-executed a side-effectful final statement — e.g. a script ending
		# in `op('/x').create(...)` created TWO nodes. Instead: if the last
		# top-level statement is a bare expression AND the script doesn't bind
		# `result` itself, rewrite that expression to `result = <expr>` in the AST
		# so its value is captured with no second execution.
		try:
			tree = ast.parse(script, mode="exec")
		except SyntaxError as exec_error:
			return error_result(f"Script execution failed: {str(exec_error)}")

		# Best-effort static guard: time.sleep() runs on TD's single main thread and
		# freezes TD + the live connection for the duration with no rescue. This is a
		# deterrent, NOT a sandbox — a script can still obfuscate via getattr(time,'sleep').
		if self._script_calls_time_sleep(tree):
			return error_result(
				"time.sleep() is not allowed in execute_python_script — it runs on "
				"TouchDesigner's single main thread; sleeping there freezes TD and the "
				"live connection for the duration with no rescue. Split the delay across "
				"multiple tool calls instead."
			)

		if (
			tree.body
			and isinstance(tree.body[-1], ast.Expr)
			and not self._script_assigns_result(tree)
		):
			last = tree.body[-1]
			assign = ast.Assign(
				targets=[ast.Name(id="result", ctx=ast.Store())],
				value=last.value,
			)
			ast.copy_location(assign, last)
			tree.body[-1] = assign
			ast.fix_missing_locations(tree)

		try:
			code = compile(tree, "<exec_python_script>", "exec")
		except SyntaxError as exec_error:
			return error_result(f"Script execution failed: {str(exec_error)}")

		with (
			contextlib.redirect_stdout(stdout_capture),
			contextlib.redirect_stderr(stderr_capture),
		):
			try:
				# Single namespace (globals IS locals) so the script behaves like real
				# module-level code: comprehensions, generator expressions, and nested
				# defs resolve free names (imports, loop vars, helpers) via the same dict
				# top-level statements write into. Side effect: scripts lose implicit
				# access to this module's own globals; td/tdu are injected into local_vars.
				exec(code, local_vars)
			except Exception as exec_error:
				# Fold any output captured before the failure into the error string —
				# it is the only field guaranteed to reach the client on an error path.
				partial_stdout = stdout_capture.getvalue()
				partial_stderr = stderr_capture.getvalue()
				message = f"Script execution failed: {str(exec_error)}"
				if partial_stdout:
					message += (
						"\n--- stdout captured before failure ---\n" + partial_stdout
					)
				if partial_stderr:
					message += (
						"\n--- stderr captured before failure ---\n" + partial_stderr
					)
				return error_result(message)

			result = local_vars.get("result")
			processed_result = self._process_method_result(result)

			stdout_val = stdout_capture.getvalue()
			stderr_val = stderr_capture.getvalue()

			return success_result(self._stamp_mutation(
				{
					"result": processed_result,
					"stdout": stdout_val,
					"stderr": stderr_val,
				},
				"exec_python_script",
				"<script>",
			))

	@staticmethod
	def _script_calls_time_sleep(tree: ast.Module) -> bool:
		"""Best-effort static detector for a ``time.sleep()`` call in a user script.

		Matches ``time.sleep(...)`` (an ``Attribute`` named ``sleep`` whose value is
		the ``Name`` ``time``) and a bare ``sleep(...)`` call (covers
		``from time import sleep``). This is a static deterrent, NOT a sandbox — a
		script can still obfuscate the call (e.g. ``getattr(time, 'sleep')(...)``).
		"""
		for node in ast.walk(tree):
			if not isinstance(node, ast.Call):
				continue
			func = node.func
			if (
				isinstance(func, ast.Attribute)
				and func.attr == "sleep"
				and isinstance(func.value, ast.Name)
				and func.value.id == "time"
			):
				return True
			if isinstance(func, ast.Name) and func.id == "sleep":
				return True
		return False

	@staticmethod
	def _script_assigns_result(tree: ast.Module) -> bool:
		"""True if the script explicitly binds a top-level name ``result``.

		When it does, a trailing bare expression must NOT overwrite that value —
		the explicit ``result`` is authoritative (matches the old behavior, which
		only ran the last-line capture when ``result`` was unset). Handles plain,
		annotated, augmented, and tuple/list-unpacking assignments.
		"""
		for node in tree.body:
			if isinstance(node, ast.Assign):
				for target in node.targets:
					for sub in ast.walk(target):
						if isinstance(sub, ast.Name) and sub.id == "result":
							return True
			elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
				if isinstance(node.target, ast.Name) and node.target.id == "result":
					return True
		return False

	def _apply_property(self, par, value):
		"""Apply a property value to a Par, handling expression / constant / bind / export modes.

		W6.1 (B33) — accept dict-shape values for mode-aware parameter writes:

		  {"mode": "constant",   "val": <scalar>}     # explicit constant assignment
		  {"mode": "expression", "expr": "<text>"}    # Python expression (e.g. "absTime.frame * 0.1")
		  {"mode": "bind",       "bindExpr": "<text>"}  # bind expression (or "expr" as alias)
		  {"mode": "export",     "bindMaster": "/op/path:par_name"}  # bind to another op's Par

		Scalar values (anything not a dict-with-mode) pass through to par.val
		unchanged — backwards-compatible with pre-W6.1 callers.

		Round-trip-compatible with Wave 3 B23's _expressions sidecar: the read
		side emits {mode: 'expression', expr: '...', eval_error?: '...'} and
		this write side accepts the same shape (eval_error ignored on write).

		Param attributes used (verified on real TD params, 2026-05-14):
		  par.mode     — ParMode enum (CONSTANT / EXPRESSION / BIND / EXPORT)
		  par.expr     — expression text for EXPRESSION mode
		  par.bindExpr — bind-expression text for BIND mode
		  par.bindMaster — Par reference for EXPORT mode (must be a Par object)
		  par.val      — the constant/evaluated value

		Raises ValueError for unsupported modes or malformed `bindMaster`.
		TD raises its own exceptions when a param doesn't support the requested
		mode (e.g. menu-int params can't take expressions) — those propagate
		up to update_node's failed[] list.
		"""
		if isinstance(value, dict) and "mode" in value:
			ParMode = type(par.mode)
			mode_name = str(value["mode"]).upper()
			if mode_name == "EXPRESSION":
				par.mode = ParMode.EXPRESSION
				par.expr = value.get("expr", "")
			elif mode_name == "CONSTANT":
				par.mode = ParMode.CONSTANT
				par.val = value.get("val", value.get("value"))
			elif mode_name == "BIND":
				par.mode = ParMode.BIND
				par.bindExpr = value.get("bindExpr", value.get("expr", ""))
			elif mode_name == "EXPORT":
				# W6.1 — par.mode = EXPORT is settable, but par.bindMaster is
				# read-only in TD. The source for an EXPORT-mode param must be
				# wired via an Export DAT operator (rows mapping source-op.par
				# to target-op.par). We can set the mode flag here; the source
				# is the caller's responsibility. If the caller supplied
				# `bindMaster` expecting us to wire it, raise an actionable error.
				if value.get("bindMaster"):
					raise ValueError(
						"EXPORT mode source binding cannot be set via par.bindMaster "
						"(read-only in TD). Wire the source via an Export DAT "
						"(rows: <source_op> <source_par> <target_op> <target_par>), "
						"or use mode='bind' with bindExpr for the modern equivalent."
					)
				par.mode = ParMode.EXPORT
			else:
				raise ValueError(
					f"unsupported mode: {mode_name!r}; "
					f"must be 'constant', 'expression', 'bind', or 'export'"
				)
			return
		# Scalar path — existing behavior, unchanged.
		par.val = value

	def update_node(self, node_path: str, properties: dict[str, Any]) -> Result:
		"""Update properties of the node at the specified path"""

		self._ensure_restore_point_tracked()
		node = td.op(node_path)

		if node is None or not node.valid:
			return error_result(f"Node not found at path: {node_path}")

		updated_properties = []
		failed_properties = []

		for prop_name, prop_value in properties.items():
			try:
				if hasattr(node.par, prop_name):
					par = getattr(node.par, prop_name)
					if hasattr(par, "val"):
						# W6.1 (B33) — _apply_property handles scalar AND
						# dict-shape {mode, expr/val/bindExpr/bindMaster} writes.
						self._apply_property(par, prop_value)
						updated_properties.append(prop_name)
					else:
						failed_properties.append(
							{
								"name": prop_name,
								"reason": "Not a settable parameter",
							}
						)
				elif hasattr(node, prop_name):
					prop = getattr(node, prop_name)
					if isinstance(prop, (int, float, str)):
						setattr(node, prop_name, prop_value)
						updated_properties.append(prop_name)
					else:
						failed_properties.append(
							{
								"name": prop_name,
								"reason": "Not a settable property",
							}
						)
				else:
					failed_properties.append(
						{"name": prop_name, "reason": "Property not found on node"}
					)
			except Exception as e:
				log_message(
					f"Error updating property {prop_name}: {str(e)}", LogLevel.ERROR
				)
				failed_properties.append({"name": prop_name, "reason": str(e)})

		result = {
			"path": node_path,
			"updated": updated_properties,
			"failed": failed_properties,
			"message": f"Updated {len(updated_properties)} properties",
		}

		if updated_properties:
			log_message(
				f"Successfully updated properties: {updated_properties}",
				LogLevel.DEBUG,
			)
			return success_result(self._stamp_mutation(result, "update_node", node_path))
		else:
			log_message(
				f"No properties were updated. Failed: {failed_properties}",
				LogLevel.WARNING,
			)
			if failed_properties:
				return error_result("Failed to update any properties")
			else:
				return error_result("No matching properties to update")

	def _get_node_properties(self, node):
		"""Return (params_dict, expressions_dict).

		params_dict holds scalar evaluated values (backwards-compatible with the
		previous return shape, just-the-dict).

		B23 — expressions_dict is a per-param sidecar populated only for params
		that have non-default mode (expression / bind / export) OR raised during
		par.eval(). Shape per entry:
		    {"mode": "expression", "expr": "sin(...)", "eval_error": "NameError: ..."}
		Empty when the node has no params with expressions/errors — the caller
		can omit the `_expressions` key from the response entirely.
		"""
		params_dict = {}
		expressions_dict = {}
		for par in node.pars("*"):
			eval_error = None
			try:
				value = par.eval()
				if isinstance(value, td.OP):
					value = value.path
				params_dict[par.name] = value
			except Exception as e:
				eval_error = str(e)
				params_dict[par.name] = f"<Error: {eval_error}>"
				log_message(
					f"Error evaluating parameter {par.name}: {eval_error}",
					LogLevel.DEBUG,
				)

			# B23 — read mode + expression; build sidecar only when non-default.
			try:
				mode_obj = getattr(par, "mode", None)
				mode_name = getattr(mode_obj, "name", None) if mode_obj is not None else None
				expr = getattr(par, "expr", "") or ""
				is_non_default_mode = mode_name is not None and mode_name != "CONSTANT"
				if is_non_default_mode or eval_error:
					entry = {}
					if mode_name:
						entry["mode"] = mode_name.lower()
					if expr:
						entry["expr"] = expr
					if eval_error:
						entry["eval_error"] = eval_error
					if entry:
						expressions_dict[par.name] = entry
			except Exception as e:
				# Sidecar is best-effort — never let it break the main response.
				log_message(
					f"B23 sidecar build failed for {par.name}: {e}",
					LogLevel.DEBUG,
				)

		return params_dict, expressions_dict

	def _get_node_summary_light(self, node) -> dict:
		"""Get lightweight information about a node (without properties for better performance)"""
		try:
			node_info = {
				"id": node.id,
				"name": node.name,
				"path": node.path,
				"opType": node.OPType,
				"properties": {},  # Empty properties for lightweight response
			}

			return node_info
		except Exception as e:
			log_message(
				f"Error collecting node information: {str(e)}", LogLevel.WARNING
			)
			return {"name": node.name if hasattr(node, "name") else "unknown"}

	def _get_node_summary(self, node) -> dict:
		"""Get detailed information about a node"""
		try:
			params, expressions = self._get_node_properties(node)
			node_info = {
				"id": node.id,
				"name": node.name,
				"path": node.path,
				"opType": node.OPType,
				"properties": params,
			}
			# B23 — only surface the sidecar when at least one param has
			# expr/mode/eval_error. Normal nodes pay zero overhead.
			if expressions:
				node_info["_expressions"] = expressions
			return node_info
		except Exception as e:
			log_message(
				f"Error collecting node information: {str(e)}", LogLevel.WARNING
			)
			return {"name": node.name if hasattr(node, "name") else "unknown"}

	def _resolve_help_target(self, module_name: str) -> Optional[Any]:
		"""Locate a module/class for help() lookup."""
		if not module_name:
			return None

		target_name = module_name.strip()
		if not target_name:
			return None

		# Handle dotted names like "td.noiseCHOP" or "td.tdu.SomeClass"
		def resolve_dotted_name(name: str) -> Optional[Any]:
			parts = name.split(".")
			# Only allow access starting from td or tdu
			if parts[0] == "td":
				obj: Any = td
			elif parts[0] == "tdu" and hasattr(td, "tdu"):
				obj = td.tdu
			else:
				return None
			for part in parts[1:]:
				# Validate part is non-empty and a valid identifier
				if not part or not part.isidentifier():
					return None
				if not hasattr(obj, part):
					return None
				obj = getattr(obj, part)
			return obj

		# Try resolving as a dotted name
		if "." in target_name:
			resolved = resolve_dotted_name(target_name)
			if resolved is not None:
				return resolved

		# Try direct attribute of td
		if hasattr(td, target_name):
			return getattr(td, target_name)

		# Try importing as a module
		imported = self._import_module_safely(target_name)
		if imported:
			return imported

		# Try importing with td. prefix
		if not target_name.startswith("td."):
			imported = self._import_module_safely(f"td.{target_name}")
			if imported:
				return imported

		return None

	def _import_module_safely(self, target: str) -> Optional[Any]:
		try:
			return importlib.import_module(target)
		except (ImportError, ModuleNotFoundError) as e:
			log_message(f"Failed to import module '{target}': {str(e)}", LogLevel.DEBUG)
			return None
		except Exception as e:
			log_message(
				f"Unexpected error importing module '{target}': {str(e)}",
				LogLevel.WARNING,
			)
			return None

	def _normalize_help_text(self, text: str) -> str:
		"""Normalize help text by removing terminal control sequences.

		The pydoc module uses backspace characters (\b) for text formatting
		(e.g., bold text is written as "c\bc" to print 'c' over 'c').
		This method removes those backspace sequences to produce clean text.
		If a backspace is encountered at the start (empty buffer), it is safely
		ignored as there is no character to remove.
		"""
		if not text:
			return text
		buffer: list[str] = []
		for char in text:
			if char == "\b":
				if buffer:
					buffer.pop()
				continue
			buffer.append(char)
		return "".join(buffer)

	def _process_method_result(self, result: Any) -> Any:
		"""
		Process method result based on its type to make it JSON serializable

		Args:
		    result: Result value to process

		Returns:
		    Processed value that can be serialized to JSON
		"""
		if isinstance(result, (int, float, str, bool)) or result is None:
			return result

		if isinstance(result, (list, tuple)):
			processed_list = []
			for item in result:
				processed_list.append(self._process_item(item))
			return processed_list

		if isinstance(result, dict):
			processed_dict = {}
			for key, value in result.items():
				processed_dict[key] = self._process_item(value)
			return processed_dict

		try:
			result_dict = {}
			for item in result:
				processed = self._process_item(item)
				if hasattr(item, "name"):
					result_dict[item.name] = processed
				else:
					result_dict[f"item_{len(result_dict)}"] = processed
			return result_dict
		except TypeError:
			return self._process_item(result)

	def _process_item(self, item: Any) -> Any:
		"""
		Process individual item from a result for JSON serialization

		Args:
		    item: Item to process

		Returns:
		    Processed item that can be serialized to JSON
		"""
		if isinstance(item, (int, float, str, bool)) or item is None:
			return item

		if hasattr(td, "op") and callable(td.op):
			node = td.op(item)
			if node and hasattr(node, "valid") and node.valid:
				return self._get_node_summary(node)

		if not callable(item) and hasattr(item, "name"):
			return str(item)

		if hasattr(item, "eval") and callable(item.eval):
			try:
				value = item.eval()
				if hasattr(td, "OP") and isinstance(value, td.OP):
					return value.path
				return value
			except Exception as e:
				log_message(
					f"Error evaluating parameter {item.name if hasattr(item, 'name') else 'unknown'}: {str(e)}",
					LogLevel.DEBUG,
				)
				return f"<Error: {str(e)}>"

		try:
			return safe_serialize(item)
		except Exception:
			return str(item)


api_service = TouchDesignerApiService()

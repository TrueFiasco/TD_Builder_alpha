"""
TouchDesigner MCP Web Server API Service Implementation
Provides API functionality related to TouchDesigner
"""

import contextlib
import importlib
import inspect
import io
import pydoc
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

	def get_td_info(self) -> Result:
		"""Get information about the TouchDesigner server"""

		version = td.app.version
		build = td.app.build

		server_info = {
			"server": f"TouchDesigner {version}.{build}",
			"version": f"{version}.{build}",
			"osName": td.app.osName,
			"osVersion": td.app.osVersion,
			"mcpApiVersion": get_mcp_api_version(),
		}

		return success_result(server_info)

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
	) -> Result:
		"""Get nodes under the specified parent path, optionally filtered by pattern

		Args:
		    parent_path: Path to the parent node
		    pattern: Pattern to filter nodes by name (e.g. "text*" for all nodes starting with "text")
		    include_properties: Whether to include full node properties (default False for better performance)

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

		return success_result({"nodes": node_summaries})

	def create_node(
		self,
		parent_path: str,
		node_type: str,
		node_name: Optional[str] = None,
		parameters: Optional[dict[str, Any]] = None,
	) -> Result:
		"""Create a new node under the specified parent path"""

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
		return success_result({
			"path": new_node.path,
			"name": new_node.name,
			"type": new_node.OPType,
			"result": node_info,
		})

	def delete_node(self, node_path: str) -> Result:
		"""Delete the node at the specified path"""

		node = td.op(node_path)
		if node is None or not node.valid:
			return error_result(f"Node not found at path: {node_path}")

		node_info = self._get_node_summary(node)
		node.destroy()

		if td.op(node_path) is None:
			log_message(f"Node deleted successfully: {node_path}", LogLevel.DEBUG)
			return success_result({"deleted": True, "node": node_info})
		else:
			log_message(
				f"Failed to verify node deletion: {node_path}", LogLevel.WARNING
			)
			return error_result(f"Failed to delete node: {node_path}")

	def exec_node_method(
		self, node_path: str, method: str, args: list, kwargs: dict
	) -> Result:
		"""Call method on the specified node"""

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

		return success_result({"result": processed_result})

	def exec_python_script(self, script: str) -> Result:
		"""Execute a Python script directly in TouchDesigner

		Args:
		    script (str): The Python script to execute

		Returns:
		    Result: Success result with execution output or error result with message
		"""

		# B16 — verified-available globals (probed via hasattr(td, ...) in live TD,
		# 2026-05-14). `me` and `parent` get sentinels — they would otherwise be
		# misleading (no node context; td.parent() resolves to /mcp_webserver_base).
		# Names without `hasattr(td, ...)` (runEnv, clamp) are intentionally absent
		# so users get a clean `NameError` instead of `AttributeError: 'NoneType'`.
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
		}

		stdout_capture = io.StringIO()
		stderr_capture = io.StringIO()

		with (
			contextlib.redirect_stdout(stdout_capture),
			contextlib.redirect_stderr(stderr_capture),
		):
			if "\n" not in script and ";" not in script:
				try:
					result = eval(script, globals(), local_vars)
					local_vars["result"] = result
					processed_result = self._process_method_result(result)

					log_message(
						f"Script evaluated. Raw result: {repr(result)}",
						LogLevel.DEBUG,
					)

					stdout_val = stdout_capture.getvalue()
					stderr_val = stderr_capture.getvalue()

					return success_result(
						{
							"result": processed_result,
							"stdout": stdout_val,
							"stderr": stderr_val,
						}
					)
				except SyntaxError:
					pass

			try:
				exec(script, globals(), local_vars)

				if "result" not in local_vars:
					lines = script.strip().split("\n")
					if lines:
						last_expr = lines[-1].strip()
						if last_expr and not last_expr.startswith(
							(
								"import",
								"from",
								"#",
								"if",
								"def",
								"class",
								"for",
								"while",
							)
						):
							try:
								local_vars["result"] = eval(
									last_expr, globals(), local_vars
								)
								log_message(
									f"Extracted result from last line: {last_expr}",
									LogLevel.DEBUG,
								)
							except Exception:
								pass

				result = local_vars.get("result")
				processed_result = self._process_method_result(result)

				stdout_val = stdout_capture.getvalue()
				stderr_val = stderr_capture.getvalue()

				return success_result(
					{
						"result": processed_result,
						"stdout": stdout_val,
						"stderr": stderr_val,
					}
				)
			except Exception as exec_error:
				raise Exception(f"Script execution failed: {str(exec_error)}")

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
			return success_result(result)
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

"""BOOTSTRAP — embedded inside mcp_webserver_base.tox as the ``import_modules`` DAT.

The component is STANDALONE: ``build_standalone_tox.py`` copies every file under
``modules/`` into the .tox as a Text DAT (inside its ``embedded`` COMP), so the
single .tox works when dragged in from anywhere, with nothing beside it.

Where the modules come from, first match wins:

1. a ``modules`` folder beside the component's External .tox file (a repo or an
   install tree: edit the files on disk, restart TouchDesigner, done);
2. the folder named by the ``TD_BUILDER_WEBSERVER_MODULES`` environment variable
   (either the ``modules`` folder itself or the folder that holds it);
3. the copy embedded in the .tox (whatever was on disk when it was generated).

If none of them loads, every HTTP route answers 503 with a sentence naming each
place it looked and the error, instead of TouchDesigner's silent 404.

This on-disk file is the CANONICAL SOURCE for the embedded DAT text; the
generator copies it verbatim. ``setup()`` is the only function that touches
TouchDesigner (``parent()``, ``project``); everything else is plain Python and
unit-tested offline (tests/unit/test_webserver_standalone_boot.py).
"""

import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import sys
import traceback
import types

MODULES_ENV = "TD_BUILDER_WEBSERVER_MODULES"
# A folder counts as the modules folder when this file is in it.
MARKER_FILE = "bootstrap_mcp.py"
# Inside the .tox: the COMP holding the module DATs, and its manifest DAT.
EMBEDDED_COMP = "embedded"
MANIFEST_DAT = "manifest"
# Path of the OpenAPI schema, relative to the modules folder.
SCHEMA_RELPATH = "td_server/openapi_server/openapi/openapi.yaml"

_boot_result = None


# --------------------------------------------------------------------------------
# Where to look on disk
# --------------------------------------------------------------------------------


def candidate_dirs(externaltox, project_folder, environ):
	"""Ordered ``[(label, modules_dir)]`` of disk places to look for the modules.

	``externaltox`` may be relative: TouchDesigner resolves it against the project
	(.toe) folder, so do the same.
	"""
	candidates = []
	tox = (externaltox or "").strip()
	if tox:
		if not os.path.isabs(tox):
			tox = os.path.join(project_folder or os.getcwd(), tox)
		candidates.append(
			(
				"beside the component's External .tox file",
				os.path.join(os.path.dirname(os.path.abspath(tox)), "modules"),
			)
		)
	env = (environ.get(MODULES_ENV) or "").strip()
	if env:
		label = f"the {MODULES_ENV} environment variable"
		candidates.append((label, env))
		candidates.append((label, os.path.join(env, "modules")))
	return candidates


def find_disk_modules(candidates):
	"""Return ``(modules_dir or None, tried)``; ``tried`` lists every place checked."""
	tried = []
	for label, path in candidates:
		if os.path.isfile(os.path.join(path, MARKER_FILE)):
			return path, tried
		tried.append(f"{path} ({label})")
	return None, tried


# --------------------------------------------------------------------------------
# Importing from the embedded copy
# --------------------------------------------------------------------------------


class EmbeddedModuleFinder(importlib.abc.MetaPathFinder, importlib.abc.InspectLoader):
	"""Imports modules from ``{relpath: source}`` (relpaths use ``/``).

	Folders without an ``__init__.py`` become empty packages, matching the
	namespace packages (``mcp``, ``utils``) the disk layout relies on. Modules get a
	``__file__`` under ``virtual_root`` so tracebacks read like the disk layout.
	"""

	def __init__(self, files, virtual_root):
		self._files = dict(files)
		self._root = virtual_root
		self._dirs = set()
		for rel in self._files:
			parts = rel.split("/")[:-1]
			for i in range(1, len(parts) + 1):
				self._dirs.add("/".join(parts[:i]))

	def _lookup(self, fullname):
		base = fullname.replace(".", "/")
		if base + "/__init__.py" in self._files:
			return base + "/__init__.py", True
		if base + ".py" in self._files:
			return base + ".py", False
		if base in self._dirs:
			return base + "/__init__.py", True  # package with no __init__.py
		return None, False

	def _origin(self, rel):
		return os.path.join(self._root, *rel.split("/"))

	def find_spec(self, fullname, path=None, target=None):
		rel, is_pkg = self._lookup(fullname)
		if rel is None:
			return None
		origin = self._origin(rel)
		spec = importlib.util.spec_from_loader(
			fullname, self, origin=origin, is_package=is_pkg
		)
		spec.has_location = True  # sets __file__ = origin
		if is_pkg:
			spec.submodule_search_locations = [os.path.dirname(origin)]
		return spec

	def is_package(self, fullname):
		return self._lookup(fullname)[1]

	def get_source(self, fullname):
		rel, _ = self._lookup(fullname)
		if rel is None:
			raise ImportError(f"no embedded module {fullname!r}", name=fullname)
		return self._files.get(rel, "")

	def get_code(self, fullname):
		rel, _ = self._lookup(fullname)
		return self.source_to_code(self.get_source(fullname), self._origin(rel))

	def get_filename(self, fullname):
		rel, _ = self._lookup(fullname)
		return self._origin(rel)

	def read_text(self, relpath):
		"""Return an embedded non-Python file (e.g. the schema), or None."""
		return self._files.get(relpath)


def read_embedded(comp):
	"""Return ``(files, manifest)`` from the component's embedded COMP, or
	``(None, reason)`` when this .tox carries no embedded copy."""
	holder = comp.op(EMBEDDED_COMP) if comp is not None else None
	manifest_dat = holder.op(MANIFEST_DAT) if holder is not None else None
	if manifest_dat is None:
		return None, (
			f"no embedded copy inside this .tox (no '{EMBEDDED_COMP}/{MANIFEST_DAT}' DAT; "
			f"it predates the standalone build)"
		)
	manifest = json.loads(manifest_dat.text)
	files = {}
	for rel, dat_name in manifest.get("files", {}).items():
		dat = holder.op(dat_name)
		if dat is None:
			return None, f"the embedded copy is damaged: DAT '{dat_name}' for {rel} is missing"
		files[rel] = dat.text
	return files, manifest


class FolderModuleFinder(importlib.abc.MetaPathFinder):
	"""Resolves the top-level names in a modules folder from that folder FIRST.

	``mcp`` and ``utils`` are folders without ``__init__.py``, and Python always
	prefers a regular package of the same name anywhere on ``sys.path`` (a
	pip-installed MCP SDK is also called ``mcp``), whatever the path order. This
	finder claims those names for the modules folder; submodules then follow the
	package's own ``__path__``.
	"""

	def __init__(self, folder):
		self.folder = folder

	def find_spec(self, fullname, path=None, target=None):
		if "." in fullname:
			return None
		return importlib.machinery.PathFinder.find_spec(fullname, [self.folder])


def _install_finder(finder):
	"""Put ``finder`` first on ``sys.meta_path``, replacing an earlier boot's."""
	sys.meta_path[:] = [
		f
		for f in sys.meta_path
		if not isinstance(f, (EmbeddedModuleFinder, FolderModuleFinder))
	]
	sys.meta_path.insert(0, finder)


# --------------------------------------------------------------------------------
# Boot
# --------------------------------------------------------------------------------


def _forget_mcp_modules():
	"""Drop half-imported ``mcp``/``utils``/``bootstrap_mcp`` modules so the next
	import starts clean (and a failed embedded import cannot shadow a later one)."""
	for name in list(sys.modules):
		root = name.split(".", 1)[0]
		if root in ("mcp", "utils", "bootstrap_mcp"):
			del sys.modules[name]


def boot(
	candidates,
	embedded_files=None,
	embedded_manifest=None,
	virtual_root=None,
	embedded_missing=None,
):
	"""Load the modules from the first working source and import the controller.

	``embedded_missing`` is the reason there is no embedded copy (for the message).
	Returns a dict describing the outcome (``ok``, ``source``, ``path``, ``message``).
	Never raises: on failure it installs a stand-in controller that answers every
	route with 503 and the reason, then returns ``ok: False``.
	"""
	modules_path, tried = find_disk_modules(candidates)
	try:
		if modules_path is not None:
			source = {"kind": "disk", "path": modules_path}
			for p in (modules_path, os.path.join(modules_path, "td_server")):
				if p not in sys.path:
					sys.path.append(p)
			_install_finder(FolderModuleFinder(modules_path))
			import bootstrap_mcp

			bootstrap_mcp.setup(modules_path, source=source)
		elif embedded_files:
			built_from = (embedded_manifest or {}).get("built_from", "unknown")
			source = {"kind": "embedded", "path": virtual_root, "built_from": built_from}
			finder = EmbeddedModuleFinder(embedded_files, virtual_root)
			_install_finder(finder)
			import bootstrap_mcp

			bootstrap_mcp.setup(
				virtual_root,
				schema_text=finder.read_text(SCHEMA_RELPATH),
				source=source,
			)
		else:
			looked = "; ".join(tried) if tried else "no folder on disk was named"
			raise ModuleNotFoundError(
				f"modules folder not found. Looked in: {looked}; and "
				f"{embedded_missing or 'this .tox has no embedded copy'}. Fix: put "
				f"the 'modules' folder beside the .tox, set {MODULES_ENV} to it, or "
				f"use a standalone .tox made by build_standalone_tox.py; then restart "
				f"TouchDesigner."
			)
		# Import the controller here so a broken module is reported as a sentence
		# on every route, not as TouchDesigner's 404.
		import mcp.controllers.api_controller  # noqa: F401
	except Exception as e:  # noqa: BLE001 — boot must always leave a responder
		if modules_path is not None:
			where = f" from {modules_path}"
		elif embedded_files:
			where = " from the copy embedded in the .tox"
		else:
			where = ""
		message = (
			f"TD Builder webserver failed to load{where}: {e.__class__.__name__}: {e}"
		)
		_print_banner(message, traceback.format_exc())
		install_failure_responder(message)
		return {"ok": False, "source": None, "path": modules_path, "message": message}

	print(f"[MCP] webserver modules loaded {_describe(source)}")
	return {"ok": True, "source": source["kind"], "path": source["path"], "message": None}


def _describe(source):
	if source["kind"] == "disk":
		return f"from disk: {source['path']}"
	return f"from the copy embedded in the .tox (built from {source['built_from']})"


def _print_banner(message, tb):
	print("=" * 64)
	print("[MCP][ERROR] " + message)
	print("[MCP][ERROR] every route will answer 503 with this message.")
	print(tb.rstrip())
	print("=" * 64)


class FailureController:
	"""Stand-in for ``api_controller_openapi``: answers every route with 503."""

	def __init__(self, message):
		self.message = message

	def onHTTPRequest(self, webServerDAT, request, response):
		response["statusCode"] = 503
		response["statusReason"] = "Service Unavailable"
		response["headers"] = {"Content-Type": "application/json"}
		response["data"] = json.dumps(
			{
				"success": False,
				"data": None,
				"error": self.message,
				"errorCategory": "EXTERNAL",
			}
		)
		return response


def install_failure_responder(message):
	"""Make ``from mcp.controllers.api_controller import api_controller_openapi``
	return a :class:`FailureController`, so the callbacks DAT answers every route."""
	_forget_mcp_modules()
	pkg = types.ModuleType("mcp")
	pkg.__path__ = []
	controllers = types.ModuleType("mcp.controllers")
	controllers.__path__ = []
	api = types.ModuleType("mcp.controllers.api_controller")
	api.api_controller_openapi = FailureController(message)
	pkg.controllers = controllers
	controllers.api_controller = api
	sys.modules["mcp"] = pkg
	sys.modules["mcp.controllers"] = controllers
	sys.modules["mcp.controllers.api_controller"] = api


def setup():
	"""TouchDesigner entry point, called by the callbacks DAT. Idempotent."""
	global _boot_result
	if _boot_result is not None:
		return _boot_result
	comp = parent()  # noqa: F821 — TouchDesigner builtin in DAT modules
	try:
		externaltox = comp.par.externaltox.eval()
	except Exception:  # noqa: BLE001
		externaltox = ""
	try:
		project_folder = project.folder  # noqa: F821 — TouchDesigner builtin
	except Exception:  # noqa: BLE001
		project_folder = ""
	candidates = candidate_dirs(externaltox, project_folder, os.environ)

	files = manifest = missing = None
	if find_disk_modules(candidates)[0] is None:
		try:
			files, manifest = read_embedded(comp)
		except Exception as e:  # noqa: BLE001
			files, manifest = None, f"the embedded copy could not be read: {e}"
		if files is None:
			files, manifest, missing = None, None, manifest  # read_embedded's reason
	base = os.path.dirname(externaltox) if externaltox else (project_folder or os.getcwd())
	virtual_root = os.path.join(base, "modules [embedded in .tox]")
	_boot_result = boot(candidates, files, manifest, virtual_root, missing)
	return _boot_result

"""MCP webserver boot logic — DISK-DELIVERED.

The embedded ``import_modules`` DAT inside ``mcp_webserver_base.tox`` is a THIN
bootstrap: it only puts ``<tox_dir>/modules`` and ``modules/td_server`` on
``sys.path`` (it has to live in the DAT because it calls TD's ``parent()``
builtin) and then delegates here. Keeping the real setup body on disk means every
future change is disk-delivered — no ``.tox`` rebuild and, crucially, no embedded
Text-DAT drift (the bug class where the embedded copy silently diverges from the
on-disk file).

``setup(modules_path)`` takes the modules path as an argument (no ``parent()``,
no ``td``), so it is fully importable and testable offline.
"""

import json
import os


def setup(modules_path):
	"""Load the OpenAPI schema and publish it on the ``mcp`` package.

	Called by the embedded ``import_modules`` bootstrap AFTER ``sys.path`` is set
	up, so ``import mcp`` and the disk modules resolve. Sets both
	``mcp.openapi_schema`` and ``mcp.schema_load_error`` (None on success) — the
	API controller surfaces the latter so a load failure is an actionable error
	rather than a silent 404.
	"""
	import mcp

	schema_path = find_openapi_schema_path(modules_path)
	try:
		if schema_path is None:
			raise FileNotFoundError(
				"OpenAPI schema file not found in any known location."
			)
		# The schema file is JSON (despite the .yaml extension), so it loads with
		# the stdlib json module — no PyYAML dependency, which some TouchDesigner
		# builds lack (a missing `import yaml` used to abort setup() and 404 every
		# CRUD/exec route). The .yaml name is upstream heritage; runtime routing
		# (this loader + openapi_router) is the schema's only live consumer.
		with open(schema_path, "r", encoding="utf-8") as f:
			openapi_schema = json.load(f)
		if not isinstance(openapi_schema, dict) or "paths" not in openapi_schema:
			raise ValueError(f"schema at {schema_path} loaded but has no 'paths' key")
		mcp.openapi_schema = openapi_schema
		mcp.schema_load_error = None
		print(
			f"[MCP] OpenAPI schema loaded from {schema_path} "
			f"({len(openapi_schema.get('paths', {}))} paths)"
		)
	except Exception as e:
		mcp.openapi_schema = {}
		mcp.schema_load_error = str(e)
		# FAIL LOUD: the app still boots (capture/feedback routes work), but the
		# CRUD/exec surface is gone — make that unmissable in the textport.
		print("=" * 64)
		print("[MCP][ERROR] FAILED TO LOAD OPENAPI SCHEMA")
		print(f"[MCP][ERROR]   {e}")
		print("[MCP][ERROR]   CRUD/exec endpoints will 404 until this is fixed.")
		print("[MCP][ERROR]   (capture/feedback endpoints are unaffected)")
		print("=" * 64)


def find_openapi_schema_path(modules_path):
	candidates = [
		os.path.join(
			modules_path, "td_server", "openapi_server", "openapi", "openapi.yaml"
		),
		os.path.join(
			os.path.dirname(os.path.dirname(modules_path)),
			"td_server",
			"openapi_server",
			"openapi",
			"openapi.yaml",
		),
	]
	for path in candidates:
		if os.path.exists(path):
			return path
	return None

"""MCP webserver boot logic — DISK-DELIVERED.

The ``import_modules`` DAT inside ``mcp_webserver_base.tox`` finds the modules
(a ``modules`` folder on disk, or the copy embedded in the standalone .tox; see
``MCP/td-webserver/import_modules.py``) and then delegates here.

``setup(modules_path, schema_text=None, source=None)`` takes everything as
arguments (no ``parent()``, no ``td``), so it is importable and testable offline.
"""

import json
import os


def setup(modules_path, schema_text=None, source=None):
	"""Load the OpenAPI schema and publish it on the ``mcp`` package.

	Called by the ``import_modules`` bootstrap AFTER the modules are importable.
	Sets ``mcp.openapi_schema`` and ``mcp.schema_load_error`` (None on success) —
	the API controller surfaces the latter so a load failure is an actionable
	error rather than a silent 404 — and ``mcp.modules_source``, which says where
	the running modules came from (``{"kind": "disk"|"embedded", "path": ...}``).

	``schema_text`` is the schema's contents when it comes from the copy embedded
	in the .tox; otherwise the schema is looked up on disk under ``modules_path``.
	"""
	import mcp

	mcp.modules_source = dict(source) if source else {"kind": "disk", "path": modules_path}
	if schema_text is not None:
		schema_path = "the copy embedded in the .tox"
	else:
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
		if schema_text is not None:
			openapi_schema = json.loads(schema_text)
		else:
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

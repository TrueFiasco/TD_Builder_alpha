"""Ticket 10: the webserver component works as ONE standalone .tox.

Covers the embedded bootstrap (``MCP/td-webserver/import_modules.py``), the schema
hand-off in ``modules/bootstrap_mcp.py`` and the generator
(``MCP/td-webserver/build_standalone_tox.py``):

- where the modules are looked for, in order (beside the .tox, env var, embedded);
- the embedded copy really boots the real controller (auth answers 401);
- a missing or broken module answers 503 with a sentence on every route instead
  of TouchDesigner's silent 404;
- the generated .tox.dir carries every module file verbatim.

Booting imports the td-webserver ``mcp`` package, which would shadow the MCP SDK
in this pytest process, so every boot runs in a child Python process with
MagicMock ``td``/``tdu`` stubs. No TouchDesigner or knowledge base needed.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WEBSERVER = REPO / "MCP" / "td-webserver"
MODULES = WEBSERVER / "modules"


def _load(name: str, path: Path):
	spec = importlib.util.spec_from_file_location(name, path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


boot_mod = _load("td_webserver_import_modules_undertest", WEBSERVER / "import_modules.py")
gen = _load("td_webserver_build_standalone_tox_undertest", WEBSERVER / "build_standalone_tox.py")


# --------------------------------------------------------------------------------
# Child-process harness
# --------------------------------------------------------------------------------

_PRELUDE = textwrap.dedent(
	"""
	import json, os, sys
	from unittest import mock
	sys.modules["td"] = mock.MagicMock(name="td")
	sys.modules["tdu"] = mock.MagicMock(name="tdu")
	import importlib.util
	spec = importlib.util.spec_from_file_location("import_modules", sys.argv[1])
	im = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(im)
	sys.path.insert(0, sys.argv[2])
	import build_standalone_tox as gen

	def request(path, method="GET", headers=None):
		from mcp.controllers.api_controller import api_controller_openapi
		req = {"method": method, "uri": path, "pars": {}, "data": ""}
		req.update(headers or {})
		resp = api_controller_openapi.onHTTPRequest(None, req, {})
		return resp.get("statusCode"), json.loads(resp.get("data") or "null")
	"""
)


def _run(body: str, tmp_path: Path) -> dict:
	"""Run ``body`` after the prelude; it must print one JSON line last."""
	script = tmp_path / "child.py"
	script.write_text(_PRELUDE + textwrap.dedent(body), encoding="utf-8")
	env = dict(os.environ)
	env["TD_API_TOKEN"] = "test-token"  # never write ~/.td_builder/api_token
	env.pop(boot_mod.MODULES_ENV, None)
	env.pop("TD_LIVE_READONLY", None)
	proc = subprocess.run(
		[sys.executable, str(script), str(WEBSERVER / "import_modules.py"), str(WEBSERVER)],
		capture_output=True, text=True, timeout=120, env=env, cwd=str(tmp_path),
	)
	assert proc.returncode == 0, proc.stdout + proc.stderr
	return json.loads(proc.stdout.strip().splitlines()[-1])


# --------------------------------------------------------------------------------
# Where the modules are looked for
# --------------------------------------------------------------------------------


def test_candidates_absolute_tox_then_env(tmp_path):
	tox = tmp_path / "dev" / "mcp_webserver_base.tox"
	env = {boot_mod.MODULES_ENV: str(tmp_path / "repo")}
	got = [p for _, p in boot_mod.candidate_dirs(str(tox), "C:/elsewhere", env)]
	assert got == [
		str(tmp_path / "dev" / "modules"),
		str(tmp_path / "repo"),
		os.path.join(str(tmp_path / "repo"), "modules"),
	]


def test_candidates_relative_tox_resolves_against_project_folder(tmp_path):
	got = boot_mod.candidate_dirs("dev/mcp_webserver_base.tox", str(tmp_path), {})
	assert [p for _, p in got] == [str(tmp_path / "dev" / "modules")]


def test_candidates_empty_when_nothing_named():
	assert boot_mod.candidate_dirs("", "", {}) == []


def test_find_disk_modules_first_with_marker_wins(tmp_path):
	empty, real = tmp_path / "a", tmp_path / "b"
	empty.mkdir()
	real.mkdir()
	(real / boot_mod.MARKER_FILE).write_text("", encoding="utf-8")
	path, tried = boot_mod.find_disk_modules([("first", str(empty)), ("second", str(real))])
	assert path == str(real)
	assert tried == [f"{empty} (first)"]


class _Dat:
	def __init__(self, text):
		self.text = text


class _Comp:
	def __init__(self, children):
		self._children = children

	def op(self, name):
		return self._children.get(name)


def test_read_embedded_round_trip():
	holder = _Comp({"manifest": _Dat(json.dumps({"files": {"a/b.py": "a_b_py"}, "built_from": "x"})),
	                "a_b_py": _Dat("X = 1\n")})
	files, manifest = boot_mod.read_embedded(_Comp({"embedded": holder}))
	assert files == {"a/b.py": "X = 1\n"}
	assert manifest["built_from"] == "x"


def test_read_embedded_reports_an_old_thin_tox():
	files, reason = boot_mod.read_embedded(_Comp({}))
	assert files is None
	assert "no embedded copy" in reason


# --------------------------------------------------------------------------------
# Booting (child processes)
# --------------------------------------------------------------------------------


def test_embedded_copy_boots_the_real_controller(tmp_path):
	out = _run(
		"""
		files = gen.collect_module_files()
		r = im.boot([], files, {"built_from": "test build"}, os.path.join(os.getcwd(), "modules [embedded in .tox]"))
		import mcp
		status, body = request("/api/td/nodes")
		print(json.dumps({
			"result": r,
			"source": mcp.modules_source,
			"paths": len(mcp.openapi_schema.get("paths", {})),
			"schema_error": mcp.schema_load_error,
			"mcp_file": getattr(sys.modules["mcp.controllers.api_controller"], "__file__", ""),
			"unauth_status": status,
		}))
		""",
		tmp_path,
	)
	assert out["result"]["ok"] is True, out
	assert out["result"]["source"] == "embedded"
	assert out["source"]["built_from"] == "test build"
	assert out["paths"] >= 5 and out["schema_error"] is None
	assert "modules [embedded in .tox]" in out["mcp_file"]
	# The real controller is running: auth is enforced, so no token = 401.
	assert out["unauth_status"] == 401


def test_disk_modules_win_over_the_embedded_copy(tmp_path):
	out = _run(
		f"""
		r = im.boot([("beside", {str(MODULES)!r})], {{"x.py": ""}}, {{}}, "unused")
		import mcp
		print(json.dumps({{"result": r, "source": mcp.modules_source}}))
		""",
		tmp_path,
	)
	assert out["result"] == {"ok": True, "source": "disk", "path": str(MODULES), "message": None}
	assert out["source"]["kind"] == "disk"


def test_nothing_found_answers_503_naming_every_place(tmp_path):
	missing = tmp_path / "dev" / "modules"
	out = _run(
		f"""
		r = im.boot([("beside the component's External .tox file", {str(missing)!r})],
		            None, None, None, "no embedded copy inside this .tox")
		print(json.dumps({{"result": r, "routes": [request(p) for p in ("/api/td/server/td", "/api/td/nodes")]}}))
		""",
		tmp_path,
	)
	assert out["result"]["ok"] is False
	for status, body in out["routes"]:
		assert status == 503
		assert str(missing) in body["error"]
		assert "no embedded copy inside this .tox" in body["error"]
		assert boot_mod.MODULES_ENV in body["error"]


def test_broken_disk_module_answers_503_with_the_error(tmp_path):
	broken = tmp_path / "modules"
	shutil.copytree(MODULES, broken, ignore=shutil.ignore_patterns("__pycache__"))
	target = broken / "mcp" / "controllers" / "openapi_router.py"
	target.write_text(target.read_text(encoding="utf-8") + "\ndef oops(:\n", encoding="utf-8")
	out = _run(
		f"""
		r = im.boot([("beside", {str(broken)!r})], {{"x.py": ""}}, {{}}, "unused")
		print(json.dumps({{"result": r, "route": request("/api/td/nodes")}}))
		""",
		tmp_path,
	)
	status, body = out["route"]
	assert out["result"]["ok"] is False
	assert status == 503
	assert f"from {broken}" in body["error"] and "SyntaxError" in body["error"]


def test_callbacks_script_survives_a_failed_boot(tmp_path):
	"""The real callbacks script (embedded in the .tox) imports the controller at
	module level; after a failed boot that import must still succeed and answer."""
	out = _run(
		f"""
		r = im.boot([], None, None, None, "no embedded copy inside this .tox")
		sys.modules["import_modules"] = im
		im._boot_result = r  # setup() is idempotent: the script's call is a no-op
		ns = {{}}
		exec(open({str(MODULES / "mcp_webserver_script.py")!r}, encoding="utf-8").read(), ns)
		resp = ns["onHTTPRequest"](None, {{"method": "GET", "uri": "/api/td/nodes", "pars": {{}}, "data": ""}}, {{}})
		print(json.dumps({{"status": resp["statusCode"], "body": json.loads(resp["data"])}}))
		""",
		tmp_path,
	)
	assert out["status"] == 503
	assert "modules folder not found" in out["body"]["error"]


# --------------------------------------------------------------------------------
# The generator
# --------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def composed():
	files = gen.collect_module_files()
	tox_files, toc = gen.compose_tox_dir(
		files,
		(WEBSERVER / "import_modules.py").read_text(encoding="utf-8"),
		(MODULES / "mcp_webserver_script.py").read_text(encoding="utf-8"),
		"test build",
	)
	return files, tox_files, toc


def test_binary_text_round_trip():
	text = "héllo\nworld\n"
	assert gen.read_binary_text(gen.binary_text(text)) == text


def test_every_module_file_is_embedded_verbatim(composed):
	files, tox_files, _ = composed
	inner = f"{gen.COMP}/{gen.EMBEDDED_COMP}"
	manifest = json.loads(gen.read_binary_text(tox_files[f"{inner}/{gen.MANIFEST_DAT}.text"]))
	assert manifest["built_from"] == "test build"
	on_disk = {
		p.relative_to(MODULES).as_posix()
		for p in MODULES.rglob("*")
		if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
	}
	assert set(manifest["files"]) == on_disk
	assert "td_server/openapi_server/openapi/openapi.yaml" in on_disk
	for rel, dat in manifest["files"].items():
		embedded = gen.read_binary_text(tox_files[f"{inner}/{dat}.text"])
		assert embedded == (MODULES / rel).read_text(encoding="utf-8").replace("\r\n", "\n"), rel
	assert len(set(manifest["files"].values())) == len(manifest["files"])


def test_bootstrap_and_callbacks_are_embedded_without_file_sync(composed):
	_, tox_files, _ = composed
	boot_text = gen.read_binary_text(tox_files[f"{gen.COMP}/import_modules.text"])
	assert boot_text == (WEBSERVER / "import_modules.py").read_text(encoding="utf-8").replace("\r\n", "\n")
	cb_parm = tox_files[f"{gen.COMP}/mcp_webserver_script.parm"].decode()
	assert "syncfile" not in cb_parm and "file " not in cb_parm
	assert "callbacks 32 mcp_webserver_script" in tox_files[f"{gen.COMP}/mpc_webserver.parm"].decode()


def test_toc_lists_each_file_once_parents_first(composed):
	_, tox_files, toc = composed
	assert sorted(toc) == sorted(tox_files) and len(toc) == len(set(toc))
	assert toc[0] == ".build"
	for i, rel in enumerate(toc):
		if "/" in rel:
			parent_n = rel.rsplit("/", 1)[0] + ".n"
			assert parent_n in toc[:i], f"{rel} listed before {parent_n}"


def test_dat_names_are_legal():
	assert gen.dat_name_for("mcp/services/api_service.py") == "mcp_services_api_service_py"
	assert gen.dat_name_for("1x.py") == "f_1x_py"


def test_generated_tox_collapses(tmp_path):
	"""End to end through toecollapse/toeexpand (skipped without TouchDesigner).
	Writes only into tmp_path, never over the shipped .tox."""
	sys.path.insert(0, str(REPO))
	try:
		from paths import resolve_td_tool
	finally:
		sys.path.remove(str(REPO))
	if resolve_td_tool("toecollapse") is None or resolve_td_tool("toeexpand") is None:
		pytest.skip("TouchDesigner's toecollapse/toeexpand not installed")
	out = gen.write_tox(tmp_path / "mcp_webserver_base.tox", built_from="test build")
	assert out.stat().st_size > 10_000
	# toeexpand exits 1 even on a TouchDesigner-saved .tox, so judge by its output.
	subprocess.run([str(resolve_td_tool("toeexpand")), str(out)],
	               capture_output=True, timeout=120, cwd=str(tmp_path))
	manifest = tmp_path / "mcp_webserver_base.tox.dir" / gen.COMP / gen.EMBEDDED_COMP / "manifest.text"
	assert json.loads(gen.read_binary_text(manifest.read_bytes()))["built_from"] == "test build"

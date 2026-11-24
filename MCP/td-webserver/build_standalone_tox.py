"""Build the STANDALONE ``mcp_webserver_base.tox`` from the files on disk.

The .tox carries a copy of every file under ``modules/`` as a readable Text DAT
(inside its ``embedded`` COMP, listed by ``embedded/manifest``), so the single
.tox works when dragged in from anywhere. A ``modules`` folder beside the .tox
(or named by ``TD_BUILDER_WEBSERVER_MODULES``) still wins at boot, so editing the
files on disk keeps working in a repo or install tree. See ``import_modules.py``.

Usage (TouchDesigner does not need to be open; ``toecollapse`` ships with it)::

    py -3.11 MCP/td-webserver/build_standalone_tox.py            # -> mcp_webserver_base.tox
    py -3.11 MCP/td-webserver/build_standalone_tox.py --out X.tox

Re-run it whenever ``modules/`` or ``import_modules.py`` changes and you want the
embedded copy to match (at least once per release). The boot banner and
``mcp.modules_source`` say which copy is running and what it was built from.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MODULES_DIR = HERE / "modules"
BOOTSTRAP = HERE / "import_modules.py"
CALLBACKS = MODULES_DIR / "mcp_webserver_script.py"
DEFAULT_OUT = HERE / "mcp_webserver_base.tox"

COMP = "mcp_webserver_base"
EMBEDDED_COMP = "embedded"
MANIFEST_DAT = "manifest"
TOC_HEADER = "# 4 0 0 0 1"

# Files under modules/ that are never embedded.
_SKIP_DIRS = {"__pycache__"}
_SKIP_SUFFIXES = {".pyc", ".pyo"}

_BUILD = (
	"version 099\nbuild 2025.32820\ntime Thu Jul  2 14:54:50 2026\n"
	"osname Windows\nosversion 10\n"
)
_ROOT_N = (
	"COMP:base\nv -265.647 -51.6369 0.677355\ntile -200 225 160 130\n"
	"flags =  current on viewer 1 parlanguage 0\ncolor 0.55 0.55 0.55 \nend\n"
)
_ROOT_CPARM = (
	"?\npages 1 params\n"
	'772804866 Port Port 1 1 0 0 1 1 9999 2 0 "" "" params 0\n'
	'772804867 Active Active 1 1 0 0 1 1 1 2 1 "" "" params 2\n'
	'772804869 Restart Restart 1 1 0 0 1 1 1 2 0 "" "" params 1\n?\n'
)
_ROOT_PARM = "?\npageindex 0 2\nenableexternaltox 0 off\nPort 67108928 9981\n?\n"
_PARAMETER_N = (
	"DAT:parameter\ntile 850 1000 354 276\nflags =  viewer 1 parlanguage 0\n"
	"color 0.55 0.55 0.55 \nend\n"
)
_WEBSERVER_N = (
	"DAT:webserver\ntile 850 775 369 152\nflags =  viewer 1 parlanguage 0\n"
	"color 0.55 0.55 0.55 \nview -1 8 0 1 1 1 0 0 0 0 1 1 0\nend\n"
)
_WEBSERVER_PARM = (
	"?\nactive 48 on op('parameter1')['Active',1]\n"
	"restart 49 0 op('parameter1')['Restart',1]\n"
	"port 49 1 op('parameter1')['Port',1]\n"
	"callbacks 32 mcp_webserver_script\n"
	'password 1024 ""\nminprotocol 0 tls10\nlanguage 0 json\n?\n'
)
_PYTHON_PARM = "?\nlanguage 0 python\n?\n"


def _text_n(tile_x: int, tile_y: int, w: int = 200, h: int = 100, extra_flags: str = "") -> str:
	return (
		f"DAT:text\ntile {tile_x} {tile_y} {w} {h}\n"
		f"flags =  viewer 1{extra_flags} parlanguage 0\ncolor 0.55 0.55 0.55 \nend\n"
	)


def binary_text(content: str) -> bytes:
	"""A Text DAT's ``.text`` file in TouchDesigner's native format: ``2\\n*``,
	five big-endian uint32 ``1 1 1 1 2``, the UTF-8 length, then the UTF-8 text
	(same format as ``ToeBuilderBridge._write_binary_text``)."""
	data = content.encode("utf-8")
	return b"2\n*" + struct.pack(">5I", 1, 1, 1, 1, 2) + struct.pack(">I", len(data)) + data


def read_binary_text(blob: bytes) -> str:
	"""Inverse of :func:`binary_text` (used by the tests)."""
	if blob[:3] != b"2\n*":
		raise ValueError("not a Text DAT .text file")
	(length,) = struct.unpack(">I", blob[23:27])
	return blob[27 : 27 + length].decode("utf-8")


def _normalize(text: str) -> str:
	return text.replace("\r\n", "\n")


def collect_module_files(modules_dir: Path = MODULES_DIR) -> dict[str, str]:
	"""``{relpath: text}`` for every file under ``modules_dir`` (``/`` separators),
	sorted, skipping caches."""
	files = {}
	for path in sorted(modules_dir.rglob("*")):
		if not path.is_file() or path.suffix in _SKIP_SUFFIXES:
			continue
		rel = path.relative_to(modules_dir)
		if _SKIP_DIRS.intersection(rel.parts):
			continue
		files[rel.as_posix()] = _normalize(path.read_text(encoding="utf-8"))
	return files


def dat_name_for(relpath: str) -> str:
	"""A legal, readable DAT name for a module file: ``mcp/services/api_service.py``
	-> ``mcp_services_api_service_py``."""
	name = re.sub(r"[^A-Za-z0-9]", "_", relpath)
	if name[0].isdigit():
		name = "f_" + name
	return name


def compose_tox_dir(
	files: dict[str, str], bootstrap_text: str, callbacks_text: str, built_from: str
) -> tuple[dict[str, bytes], list[str]]:
	"""Every file of ``mcp_webserver_base.tox.dir`` as ``{relpath: bytes}``, plus
	the table-of-contents order. Pure: no disk access."""
	out: dict[str, bytes] = {}
	toc: list[str] = []

	def put(rel: str, content) -> None:
		out[rel] = content.encode("utf-8") if isinstance(content, str) else content
		toc.append(rel)

	put(".build", _BUILD)
	put(f"{COMP}.n", _ROOT_N)
	put(f"{COMP}.cparm", _ROOT_CPARM)
	put(f"{COMP}.parm", _ROOT_PARM)
	put(f"{COMP}/parameter1.n", _PARAMETER_N)
	put(f"{COMP}/mpc_webserver.n", _WEBSERVER_N)
	put(f"{COMP}/mpc_webserver.parm", _WEBSERVER_PARM)
	put(f"{COMP}/import_modules.n", _text_n(1550, 325, 650, 360, " activate on"))
	put(f"{COMP}/import_modules.parm", _PYTHON_PARM)
	put(f"{COMP}/import_modules.text", binary_text(_normalize(bootstrap_text)))
	# The callbacks DAT is embedded with NO file sync: a relative `file` path is
	# resolved against the .toe's folder, not the .tox's, so it would point at
	# the wrong place (or nowhere) in most projects.
	put(f"{COMP}/mcp_webserver_script.n", _text_n(825, 300, 644, 380, " activate on"))
	put(f"{COMP}/mcp_webserver_script.parm", _PYTHON_PARM)
	put(f"{COMP}/mcp_webserver_script.text", binary_text(_normalize(callbacks_text)))

	names: dict[str, str] = {}
	for rel in files:
		name = dat_name_for(rel)
		if name in names.values() or name == MANIFEST_DAT:
			raise ValueError(f"two module files map to the same DAT name {name!r}")
		names[rel] = name
	manifest = {
		"about": (
			"TD Builder webserver modules embedded by build_standalone_tox.py. "
			"Each DAT holds one file of MCP/td-webserver/modules/."
		),
		"built_from": built_from,
		"files": names,
	}

	put(
		f"{COMP}/{EMBEDDED_COMP}.n",
		"COMP:base\ntile 1550 775 160 130\nflags =  viewer 1 parlanguage 0\n"
		"color 0.55 0.55 0.55 \nend\n",
	)
	inner = f"{COMP}/{EMBEDDED_COMP}"
	put(f"{inner}/{MANIFEST_DAT}.n", _text_n(0, 0, 260, 160))
	put(f"{inner}/{MANIFEST_DAT}.text", binary_text(json.dumps(manifest, indent=1) + "\n"))
	for i, (rel, name) in enumerate(names.items()):
		x, y = 300 + (i % 6) * 250, -(i // 6) * 150
		put(f"{inner}/{name}.n", _text_n(x, y))
		if rel.endswith(".py"):
			put(f"{inner}/{name}.parm", _PYTHON_PARM)
		put(f"{inner}/{name}.text", binary_text(files[rel]))
	return out, toc


def built_from_label() -> str:
	"""``<MCP API version> @ <git commit>``, flagged when modules/ has local edits."""
	sys.path.insert(0, str(MODULES_DIR))
	try:
		from utils.version import MCP_API_VERSION
	except Exception:  # noqa: BLE001
		MCP_API_VERSION = "?"
	finally:
		sys.path.remove(str(MODULES_DIR))
	try:
		sha = subprocess.run(
			["git", "rev-parse", "--short", "HEAD"],
			cwd=REPO, capture_output=True, text=True, check=True,
		).stdout.strip()
		dirty = subprocess.run(
			["git", "status", "--porcelain", "--", str(HERE)],
			cwd=REPO, capture_output=True, text=True, check=True,
		).stdout.strip()
	except Exception:  # noqa: BLE001
		return f"MCP API {MCP_API_VERSION} @ unknown commit"
	return f"MCP API {MCP_API_VERSION} @ {sha}" + (" + local changes" if dirty else "")


def write_tox(out_path: Path, built_from: str | None = None) -> Path:
	"""Compose the .tox.dir in a temp folder and collapse it into ``out_path``."""
	sys.path.insert(0, str(REPO))
	from paths import resolve_td_tool, td_tool_missing_error

	toecollapse = resolve_td_tool("toecollapse")
	if toecollapse is None:
		raise SystemExit(td_tool_missing_error("toecollapse"))

	files = collect_module_files()
	built_from = built_from or built_from_label()
	tox_files, toc = compose_tox_dir(
		files,
		BOOTSTRAP.read_text(encoding="utf-8"),
		CALLBACKS.read_text(encoding="utf-8"),
		built_from,
	)
	with tempfile.TemporaryDirectory(prefix="standalone_tox_") as tmp:
		tmp = Path(tmp)
		tox_dir = tmp / f"{COMP}.tox.dir"
		for rel, blob in tox_files.items():
			target = tox_dir / rel
			target.parent.mkdir(parents=True, exist_ok=True)
			target.write_bytes(blob)
		toc_path = tmp / f"{COMP}.tox.toc"
		toc_path.write_text(TOC_HEADER + "\n" + "\n".join(toc) + "\n", encoding="utf-8", newline="\n")
		result = subprocess.run(
			[str(toecollapse), str(toc_path)], capture_output=True, text=True, timeout=300
		)
		built = tmp / f"{COMP}.tox"
		if result.returncode != 0 or not built.is_file() or built.stat().st_size < 100:
			raise SystemExit(
				f"toecollapse failed (exit {result.returncode}): {result.stderr or result.stdout}"
			)
		out_path.parent.mkdir(parents=True, exist_ok=True)
		shutil.copyfile(built, out_path)
	print(
		f"Wrote {out_path} ({out_path.stat().st_size} bytes): {len(files)} embedded "
		f"files, built from {built_from}"
	)
	return out_path


def main(argv=None) -> int:
	parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
	parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write the .tox")
	args = parser.parse_args(argv)
	write_tox(args.out.resolve())
	return 0


if __name__ == "__main__":
	sys.exit(main())

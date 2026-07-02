"""THIN BOOTSTRAP — the ONE piece embedded inside mcp_webserver_base.tox.

It does only the bare minimum that MUST run inside the DAT context: it calls TD's
`parent()` builtin to locate the .tox on disk, puts `<tox_dir>/modules` and
`modules/td_server` on sys.path, then delegates ALL real work to the disk module
`modules/bootstrap_mcp.py`.

Keep this file tiny and stable. After the v0.2.0 .tox rebuild that installs this
bootstrap, every other module change is disk-delivered — this is intended to be
the last `.tox` touch. This on-disk copy is the CANONICAL SOURCE for the embedded
DAT text: to update the embedded DAT, paste this file's contents verbatim.
"""

import os
import sys


def setup():
	externaltox = parent().par.externaltox.eval()
	tox_dir_path = os.path.dirname(externaltox)
	modules_path = os.path.join(tox_dir_path, "modules")

	if modules_path not in sys.path:
		sys.path.append(modules_path)

	td_server_path = os.path.join(modules_path, "td_server")
	if td_server_path not in sys.path:
		sys.path.append(td_server_path)

	# Delegate to the disk module (importable now that modules_path is on sys.path).
	# All boot logic lives there, so it can change without touching this .tox.
	import bootstrap_mcp

	bootstrap_mcp.setup(modules_path)

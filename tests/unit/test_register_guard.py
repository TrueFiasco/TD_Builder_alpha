"""G6: register_user_component.py rejects an absolute --tox-path for user/derivative
sources (which emit an app.userPaletteFolder/app.samplesFolder-RELATIVE expression).

The guard runs BEFORE the manifest expand, so this needs no TouchDesigner tools — a
stub file that merely exists is enough to reach the argument check.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "kb_build" / "register_user_component.py"


def _run(args, tmp_path):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=120)


def test_user_source_rejects_absolute_tox_path(tmp_path):
    stub = tmp_path / "comp.tox"
    stub.write_text("stub", encoding="utf-8")
    reg = tmp_path / "reg.json"
    # default --tox-path is the file's ABSOLUTE path -> invalid for --source user
    proc = _run([str(stub), "--source", "user", "--registry", str(reg)], tmp_path)
    assert proc.returncode == 2, (proc.stdout + proc.stderr)
    assert "must be RELATIVE" in proc.stderr, proc.stderr
    assert not reg.exists(), "no registry may be written when the guard rejects the args"


def test_relative_tox_path_passes_the_guard(tmp_path):
    stub = tmp_path / "comp.tox"
    stub.write_text("stub", encoding="utf-8")
    reg = tmp_path / "reg.json"
    # a relative --tox-path is accepted by the guard; the run may still fail later at the
    # expand (stub is not a real .tox), but NOT for the guard reason.
    proc = _run([str(stub), "--source", "user", "--tox-path", "Tools/comp.tox",
                 "--registry", str(reg)], tmp_path)
    assert "must be RELATIVE" not in proc.stderr, proc.stderr

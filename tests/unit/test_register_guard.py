"""G6: 'user'/'derivative' sources emit an app.userPaletteFolder/
app.samplesFolder-RELATIVE expression, so an absolute tox_path must be refused.

W7 rework: the guard's single home is the ENGINE (kb_build/user_components.py
relative_path_guard, enforced inside build_entry and fail-fast in commit_specs
— covered in tests/unit/test_user_components_engine.py); this file keeps the
delegating CLI's contract: rc=2, the "must be RELATIVE" message on stderr, and
NO registry write. The CLI pre-checks the guard BEFORE the manifest expand, so
a stub file is enough — no TouchDesigner tools needed.
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

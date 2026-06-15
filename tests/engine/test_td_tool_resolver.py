"""Unit tests for the TouchDesigner binary resolver in paths.py (audit #9).

Pure/deterministic — no KB, no MCP server, no TouchDesigner required.
"""
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import paths  # noqa: E402


def _clear_td_env(monkeypatch):
    for k in ("TD_TOECOLLAPSE", "TD_TOEEXPAND", "TD_BIN_DIR"):
        monkeypatch.delenv(k, raising=False)


def test_env_override_wins_and_strips_exe(tmp_path, monkeypatch):
    _clear_td_env(monkeypatch)
    fake = tmp_path / "toecollapse.exe"
    fake.write_text("")
    monkeypatch.setenv("TD_TOECOLLAPSE", str(fake))
    # Both 'toecollapse' and 'toecollapse.exe' map to the same env override.
    assert paths.resolve_td_tool("toecollapse") == fake
    assert paths.resolve_td_tool("toecollapse.exe") == fake


def test_td_bin_dir_resolves(tmp_path, monkeypatch):
    _clear_td_env(monkeypatch)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    name = "toeexpand.exe" if os.name == "nt" else "toeexpand"
    tool = bindir / name
    tool.write_text("")
    monkeypatch.setenv("TD_BIN_DIR", str(bindir))
    assert paths.resolve_td_tool("toeexpand") == tool


def test_missing_returns_none_and_actionable_message(monkeypatch):
    _clear_td_env(monkeypatch)
    # Force PATH + default-install globs to find nothing.
    monkeypatch.setattr(paths._shutil, "which", lambda *_a, **_k: None)
    monkeypatch.setattr(paths._glob, "glob", lambda *_a, **_k: [])
    assert paths.resolve_td_tool("toecollapse") is None
    msg = paths.td_tool_missing_error("toecollapse")
    assert "TD_TOECOLLAPSE" in msg
    assert "Install TouchDesigner" in msg

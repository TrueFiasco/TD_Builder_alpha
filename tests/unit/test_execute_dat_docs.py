"""F8 doc-surface guard: Execute-DAT (parexec) firing semantics + next-frame lines.

Greps the three runtime doc surfaces for the required substrings, mirroring the
canary-test pattern of asserting content rather than exact byte layout. No runtime
behavior changes, so this is a pure content check.
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/unit/ -> repo root

_TD_LIVE_CLIENT = _REPO_ROOT / "MCP" / "live_client" / "td_live_client.py"
_SKILL = _REPO_ROOT / "Agents" / "td-builder-howto" / "SKILL.md"
_BUILD_MD = _REPO_ROOT / "Agents" / "experts" / "td_python_expert" / "build.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_td_live_client_exec_description_documents_execute_dat_firing():
    text = _read(_TD_LIVE_CLIENT)
    # The execute_python_script Tool description must carry the parexec facts.
    for needle in ("onValueChange", "onPulse", "next frame"):
        assert needle in text, f"missing {needle!r} in td_live_client.py"


def test_update_params_description_notes_no_onvaluechange():
    # The source splits the sentence across adjacent string literals, so assert on
    # fragments that each live within a single literal.
    text = _read(_TD_LIVE_CLIENT)
    assert "will NOT fire a Parameter Execute DAT" in text
    assert "UI-edit only" in text


def test_skill_md_documents_parexec_gotchas():
    text = _read(_SKILL).lower()
    assert "onpulse" in text
    assert "silently" in text


def test_build_md_documents_execute_dat_gotchas():
    text = _read(_BUILD_MD)
    assert "onValueChange" in text
    assert "onPulse" in text

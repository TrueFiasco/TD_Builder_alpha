#!/usr/bin/env python3
r"""user_store identity-field tests (W7 re-bless, owner decision ⑥) — pure,
KB-free, no model, no server import.

Pins the contract: "absent" when no user store is visible (the hermetic state
every pinned eval run must be in); a content sha otherwise — so a
deliberately-dirty run (or a hermeticity-pin regression) REFUSES --compare
instead of silently measuring KB ∪ user-store under a KB-only identity.

Run: py -3.11 -m pytest eval/agent_eval/tests/test_user_store_identity.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_EVAL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_EVAL_DIR))

import identity  # noqa: E402


def test_user_store_in_refuse_tier():
    assert "user_store" in identity.AGENT_IDENTITY_FIELDS, (
        "user_store must live in the REFUSE tier — a dirty store makes "
        "results non-comparable (decision ⑥)"
    )


def test_absent_when_nothing_exists(tmp_path):
    got = identity.user_store_identity(
        tmp_path / "user_components.json", tmp_path / "user_index")
    assert got == "absent"


def test_registry_alone_flips(tmp_path):
    reg = tmp_path / "user_components.json"
    reg.write_text('{"components": {}}', encoding="utf-8")
    got = identity.user_store_identity(reg, tmp_path / "user_index")
    assert got != "absent" and len(got) == 64, (
        "ANY visible registry file — even empty — must flip the field"
    )


def test_index_manifest_alone_flips(tmp_path):
    idx = tmp_path / "user_index"
    idx.mkdir()
    (idx / "manifest.json").write_text("{}", encoding="utf-8")
    got = identity.user_store_identity(tmp_path / "user_components.json", idx)
    assert got != "absent" and len(got) == 64


def test_deterministic_and_content_sensitive(tmp_path):
    reg = tmp_path / "user_components.json"
    reg.write_text('{"components": {"a": 1}}', encoding="utf-8")
    idx = tmp_path / "user_index"
    h1 = identity.user_store_identity(reg, idx)
    assert h1 == identity.user_store_identity(reg, idx), "not deterministic"
    reg.write_text('{"components": {"a": 2}}', encoding="utf-8")
    assert identity.user_store_identity(reg, idx) != h1, "blind to a content edit"


def test_chroma_payload_not_hashed(tmp_path):
    """Only registry + index manifest are content-of-record: sqlite bytes under
    user_index/ are nondeterministic and must not perturb the identity."""
    reg = tmp_path / "user_components.json"
    reg.write_text('{"components": {"a": 1}}', encoding="utf-8")
    idx = tmp_path / "user_index"
    idx.mkdir()
    (idx / "manifest.json").write_text('{"regime": "x"}', encoding="utf-8")
    h1 = identity.user_store_identity(reg, idx)
    (idx / "chroma.sqlite3").write_bytes(b"\x00" * 64)
    assert identity.user_store_identity(reg, idx) == h1

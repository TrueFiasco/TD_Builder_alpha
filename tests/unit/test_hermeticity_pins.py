"""The session-wide hermeticity pins in tests/conftest.py (`_user_dir_pin`).

These assert the suite is kept off the maintainer's real user dir and real TD
palette root BY CONSTRUCTION. Both were previously safe only by convention: the
two tests that exercise register_component(save_to_palette=true) happen to pin
TD_USER_PALETTE_DIR themselves, so a new save_to_palette test that forgot would
have written straight into a real user's palette with nothing to catch it. Same
coupling W7's review fixed structurally for `surface: "live"` scenarios.

Why the palette root needs its own pin: it is NOT under ~/.td_builder, so
TD_BUILDER_USER_DIR does not cover it. Unpinned, paths.user_palette_dir() falls
back to the Windows known-folder Documents — the real, OneDrive-redirected
Documents/Derivative/Palette. And commit_specs() mkdirs the target folder
(kb_build/user_components.py) BEFORE it copies and before the registry upsert,
so a call that fails in between orphans an empty folder in that real palette
with no registry entry — the exact state observed on the maintainer's machine
on 2026-07-16.

Hermetic: pure env + path resolution, no KB, no chromadb, no TD binary.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import paths  # noqa: E402


def test_user_dir_pin_is_in_effect():
    """TD_BUILDER_USER_DIR is pinned and actually drives the resolvers."""
    pinned = os.environ.get("TD_BUILDER_USER_DIR", "")
    assert pinned.strip(), "conftest._user_dir_pin must pin TD_BUILDER_USER_DIR"
    assert paths.user_components_path().parent == Path(pinned)
    assert paths.user_index_dir().parent == Path(pinned)


def test_palette_pin_is_in_effect(tmp_path_factory):
    """TD_USER_PALETTE_DIR is pinned to a throwaway temp location.

    Asserts the property the pin must HAVE, not the exact dir it lands in:
    there are two legitimate pinners and which one won depends on test order.
    conftest._user_dir_pin pins into the pytest tmp tree; measure/_server then
    re-pins to a tempfile.mkdtemp() before the server import (it has to — it is
    also the server seam for non-pytest callers like agent-eval Lane R). So a
    lane that loads the server first, as CI does with `pytest tests/engine
    tests/unit`, legitimately sees the mkdtemp value here.
    """
    pinned = os.environ.get("TD_USER_PALETTE_DIR", "")
    assert pinned.strip(), "conftest._user_dir_pin must pin TD_USER_PALETTE_DIR"
    resolved = paths.user_palette_dir().resolve()
    assert resolved == Path(pinned).resolve(), "the env override must win"
    tmp_roots = {Path(tempfile.gettempdir()).resolve(),
                 tmp_path_factory.getbasetemp().resolve()}
    assert any(resolved.is_relative_to(r) for r in tmp_roots), \
        f"palette pin {resolved} is not a throwaway temp dir (roots: {sorted(tmp_roots)})"


def test_palette_dir_never_resolves_into_the_real_documents(monkeypatch):
    """The load-bearing one: while the suite runs, user_palette_dir() must not
    land anywhere inside the real Documents root that TD itself uses."""
    pinned = paths.user_palette_dir().resolve()

    # What this machine WOULD resolve unpinned. Taken from the real resolver
    # rather than re-deriving the known-folder lookup here, so the comparison
    # stays honest on Windows (OneDrive-redirected Documents), macOS and CI
    # Linux alike, and cannot drift from paths.py.
    monkeypatch.delenv("TD_USER_PALETTE_DIR", raising=False)
    real_palette = paths.user_palette_dir().resolve()
    real_documents = real_palette.parent.parent   # paths.py: <Documents>/Derivative/Palette

    assert pinned != real_palette, \
        f"user_palette_dir() resolves to the REAL palette {real_palette} during tests"
    assert not pinned.is_relative_to(real_documents), (
        f"palette pin {pinned} sits inside the real Documents root {real_documents}; "
        f"register_component(save_to_palette=true) would mkdir/copy there")

    # NB: deliberately not asserting "outside Path.home()" — on Windows the
    # pytest tmp tree lives at %LOCALAPPDATA%\Temp, i.e. UNDER the home dir, so
    # that assertion is unsatisfiable here. Real Documents is the invariant.


# ---------------------------------------------------------------------------
# The agent-eval harness pins its OWN env: it materializes a per-trial MCP
# config and launches the servers as a separate process tree, so no pytest
# fixture above reaches it. register_component sits in the fixed 18-tool
# surface (score.py OFFLINE_TOOLS), so EVERY offline trial can call it with
# save_to_palette=true — these keep both pins wired there too.
# ---------------------------------------------------------------------------
_TMPLS = ("mcp.eval.json.tmpl", "mcp.eval.live.json.tmpl")


def test_agent_eval_templates_pin_both_user_and_palette_dirs():
    agent_eval = REPO / "eval" / "agent_eval"
    for name in _TMPLS:
        env = json.loads((agent_eval / name).read_text(encoding="utf-8")) \
            ["mcpServers"]["td-builder"]["env"]
        assert env.get("TD_BUILDER_USER_DIR") == "{{USER_DIR}}", name
        assert env.get("TD_USER_PALETTE_DIR") == "{{PALETTE_DIR}}", \
            f"{name} must pin the palette root: it is NOT under ~/.td_builder, so " \
            f"TD_BUILDER_USER_DIR does not cover it and an agent calling " \
            f"register_component(save_to_palette=true) would write to the real palette"


def test_agent_eval_substitutes_every_token_its_templates_declare():
    """A token declared in a .tmpl with no substitution site would reach the
    server as a LITERAL env value (a dir named '{{PALETTE_DIR}}'), i.e. a pin
    that quietly stops pinning. run_agent_eval also raises on leftovers at
    materialization time; this catches it in the KB-free lane instead."""
    agent_eval = REPO / "eval" / "agent_eval"
    runner = (agent_eval / "run_agent_eval.py").read_text(encoding="utf-8")
    for name in _TMPLS:
        raw = (agent_eval / name).read_text(encoding="utf-8")
        for token in sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", raw))):
            assert f'"{token}"' in runner, \
                f"{name} declares {token} but run_agent_eval.py never substitutes it"

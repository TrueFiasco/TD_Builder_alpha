"""Shared fixtures for the measurement suite.

Loads the td-builder MCP server once per session (in-process), restores
stdout, exposes a `probe` for sync tool calls + cross-cutting metrics, a
`promote` flag for baseline updates, and a `td_live` reachability probe.
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(__file__))  # make `measure` importable

from measure._server import load_server  # noqa: E402
from measure.probe import Probe  # noqa: E402


def pytest_addoption(parser):
    parser.addoption(
        "--promote", action="store_true", default=False,
        help="Update the stored baseline(s) with this run's numbers.",
    )


# Anything driving the in-process OFFLINE server needs the fetched KB (the
# `server` fixture fails loudly without it), so the KB-free CI lane must
# deselect those tests via `-m "not requires_kb"`. The LIVE fixtures are
# deliberately not here: MCP/live_server.py imports no KB artifacts (only
# mcp/httpx, both in requirements-light), so live-fixture tests are
# hermetic-lane safe — marking them was a conservative over-mark. Builder
# tests that read the KB directly (no fixture) carry an explicit module-level
# pytestmark instead — fixture inspection cannot see a ToxBuilder(...) call
# inside the test body.
_KB_FIXTURES = {"server", "probe"}


def pytest_collection_modifyitems(items):
    for item in items:
        if _KB_FIXTURES & set(getattr(item, "fixturenames", ())):
            item.add_marker(pytest.mark.requires_kb)


@pytest.fixture(scope="session", autouse=True)
def _user_dir_pin(tmp_path_factory):
    """W7 hermeticity (belt-and-suspenders): no test may read or write the
    maintainer's real ~/.td_builder OR their real TD palette root. Two
    independent env overrides, both resolved at CALL time, so this session-wide
    pin covers tests/unit + tests/engine too (the measure/_server loader
    force-pins TD_BUILDER_USER_DIR again before the server import):

      * TD_BUILDER_USER_DIR -> paths.user_components_path() / user_index_dir()
      * TD_USER_PALETTE_DIR -> paths.user_palette_dir(), which is NOT under
        ~/.td_builder and so is NOT covered by the pin above. Its unpinned
        fallback is the Windows known-folder Documents, i.e. the maintainer's
        real Documents/Derivative/Palette; register_component(save_to_palette=
        true) mkdirs a folder there before it copies, so an unpinned test that
        fails mid-commit orphans an empty folder in a real user's palette.

    Tests that need their own dir monkeypatch.setenv over this; the pin is the
    safety net for the ones that forget (tests/unit/test_hermeticity_pins.py
    holds the line structurally rather than by convention)."""
    os.environ["TD_BUILDER_USER_DIR"] = str(tmp_path_factory.mktemp("td_user_pin"))
    os.environ["TD_USER_PALETTE_DIR"] = str(tmp_path_factory.mktemp("td_palette_pin"))


@pytest.fixture(scope="session")
def promote(pytestconfig) -> bool:
    return bool(pytestconfig.getoption("--promote"))


@pytest.fixture(scope="session")
def server():
    """The imported MCP server module (heavy; loaded once)."""
    # A missing KB is operator error, not a reason to silently skip the whole
    # offline gate -- fail loudly with the fix. (Live-TD-down stays a real skip
    # via the separate live_server fixture.)
    repo_root = os.path.dirname(os.path.dirname(__file__))  # tests/ -> repo root
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from paths import KB_OPERATORS
    if not KB_OPERATORS.exists():
        pytest.fail(
            f"KB not fetched (missing {KB_OPERATORS}). "
            "Run `python scripts/fetch_vector_db.py` from the repo root, then re-run.",
            pytrace=False,
        )
    try:
        return load_server()
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"MCP server failed to load: {exc}", pytrace=False)


@pytest.fixture(scope="session")
def probe(server):
    p = Probe(server)
    # The KB warm-up thread only starts in main(); when the server is imported
    # in-process the tool handlers just report "kb_warming". Trigger the blocking
    # load ourselves so KB-dependent tests see a ready KB (~1-2 min, one-time).
    ensure = getattr(server, "_ensure_kb", None)
    if callable(ensure):
        try:
            ensure()
        except Exception:
            pass
    yield p
    p.close()


def _is_first_party_module(root: str) -> bool:
    """True when `root` names one of our own modules (a live-server import
    regression), not a third-party dependency."""
    repo = Path(__file__).resolve().parent.parent
    candidates = (repo / "MCP", repo / "MCP" / "live_client",
                  repo / "MCP" / "server_core", repo / "tests" / "measure")
    return any((d / f"{root}.py").exists() or (d / root).is_dir()
               for d in candidates)


@pytest.fixture(scope="session")
def live_server():
    """The imported live-TD MCP server module (MCP/live_server.py).

    Only a missing third-party dependency (light-deps env without mcp/httpx)
    is a legitimate skip; a first-party module failing to import, or any other
    load error, is an import regression and must fail loudly — before this
    guard was narrowed, a real regression silently skipped every live test.
    """
    try:
        from measure._server import load_live_server
        return load_live_server()
    except ModuleNotFoundError as exc:
        root = (exc.name or "").split(".")[0]
        if not root or _is_first_party_module(root):
            pytest.fail(f"live server import regression: {exc}", pytrace=False)
        pytest.skip(f"live MCP server unavailable (missing dependency): {exc}")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"live MCP server failed to load: {exc}", pytrace=False)


@pytest.fixture(scope="session")
def live_probe(live_server):
    p = Probe(live_server)
    yield p
    p.close()


def _td_reachable(host: str = "127.0.0.1", port: int = 9981, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def td_live() -> bool:
    """True when TouchDesigner's WebServer DAT is reachable on 9981."""
    return _td_reachable()


@pytest.fixture(scope="session")
def has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))

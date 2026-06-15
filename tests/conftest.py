"""Shared fixtures for the measurement suite.

Loads the td-builder MCP server once per session (in-process), restores
stdout, exposes a `probe` for sync tool calls + cross-cutting metrics, a
`promote` flag for baseline updates, and a `td_live` reachability probe.
"""
from __future__ import annotations

import os
import socket
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))  # make `measure` importable

from measure._server import load_server  # noqa: E402
from measure.probe import Probe  # noqa: E402


def pytest_addoption(parser):
    parser.addoption(
        "--promote", action="store_true", default=False,
        help="Update the stored baseline(s) with this run's numbers.",
    )


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


@pytest.fixture(scope="session")
def live_server():
    """The imported live-TD MCP server module (MCP/live_server.py)."""
    try:
        from measure._server import load_live_server
        return load_live_server()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"live MCP server unavailable: {exc}")


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

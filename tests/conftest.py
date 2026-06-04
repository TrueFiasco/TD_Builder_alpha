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
    try:
        return load_server()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MCP server unavailable: {exc}")


@pytest.fixture(scope="session")
def probe(server):
    p = Probe(server)
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

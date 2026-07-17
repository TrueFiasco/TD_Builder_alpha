"""Positive live-auth test — asserts on raw HTTP status, not the probe.

Historically `probe._classify` marked a `"TD Error (401): ..."` string as
ok=True (the blindness that motivated this file); the classifier now flags
`TD Error`/`Failed` prefixes, but this test deliberately keeps talking to the
TD WebServer DAT directly with httpx — raw status codes are positive evidence
the token matrix works, independent of any probe heuristics:

    no token            -> 401
    wrong token         -> 401
    correct token       -> 200 (+ success envelope)
    GET /api/td/server/td (health) -> 200 WITHOUT a token

Skipped when TouchDesigner is unreachable (these are positive assertions, not
graceful-fallback checks). Requires the NEW modules loaded in TD — restart TD or
re-init the WebServer DAT so `<tox_dir>/modules` re-imports.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

TD_API_URL = os.environ.get("TD_API_URL", "http://127.0.0.1:9981")


def _expected_token():
    """Resolve the shared secret the same way the client/server do."""
    env = os.environ.get("TD_API_TOKEN")
    if env and env.strip():
        return env.strip()
    override = os.environ.get("TD_API_TOKEN_FILE")
    path = Path(override) if override else Path.home() / ".td_builder" / "api_token"
    try:
        if path.exists():
            tok = path.read_text(encoding="utf-8").strip()
            if tok:
                return tok
    except OSError:
        pass
    return None


def _get(path, params=None, headers=None):
    with httpx.Client(base_url=TD_API_URL, timeout=10.0) as c:
        return c.get(path, params=params, headers=headers)


@pytest.fixture(scope="module")
def token():
    tok = _expected_token()
    if not tok:
        pytest.skip(
            "no shared token available (set TD_API_TOKEN or open TD once to "
            "generate ~/.td_builder/api_token)"
        )
    return tok


def _require_td(td_live):
    if not td_live:
        pytest.skip("TouchDesigner WebServer DAT not reachable on 9981")


def test_no_token_rejected(td_live):
    _require_td(td_live)
    r = _get("/api/nodes", params={"parentPath": "/"})
    assert r.status_code == 401, (
        f"expected 401 without a token, got {r.status_code}: {r.text[:200]}. "
        "If 200, TD is still running the OLD (pre-auth) modules — reload them."
    )


def test_wrong_token_rejected(td_live):
    _require_td(td_live)
    r = _get(
        "/api/nodes",
        params={"parentPath": "/"},
        headers={"Authorization": "Bearer not-the-real-token"},
    )
    assert r.status_code == 401, f"expected 401 with wrong token, got {r.status_code}"


def test_correct_token_accepted(td_live, token):
    _require_td(td_live)
    r = _get(
        "/api/nodes",
        params={"parentPath": "/"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, (
        f"expected 200 with the correct token, got {r.status_code}: {r.text[:200]}"
    )
    body = r.json()
    assert body.get("success") is True, body


def test_health_route_open_without_token(td_live):
    _require_td(td_live)
    r = _get("/api/td/server/td")
    assert r.status_code == 200, (
        f"health route should be reachable tokenless (200), got {r.status_code}"
    )

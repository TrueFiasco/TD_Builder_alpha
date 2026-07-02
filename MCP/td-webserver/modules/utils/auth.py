"""Shared-secret token auth for the TouchDesigner MCP WebServer DAT.

The WebServer DAT binds ALL interfaces (it cannot bind loopback-only), so on a
venue/studio LAN any peer can otherwise reach the unauthenticated CRUD/exec
routes. This module is the practical control: a shared secret the MCP client
sends as `Authorization: Bearer <token>` and the controller verifies BEFORE
routing.

Token lifecycle
---------------
- Storage: ``~/.td_builder/api_token`` — the only path BOTH processes (this TD
  side and the separate ``MCP/live_client`` process) can compute without knowing
  the repo root. It lives under the per-user home dir (ACL'd on Windows via
  ``%USERPROFILE%``; chmod 600 on POSIX).
- Resolve order: ``TD_API_TOKEN`` env → token file → generate + persist.
- The token is materialized EAGERLY at server boot (see
  ``APIControllerOpenAPI.__init__``) so it exists before the first request — a
  lazy first-request generation would 401 that first call (the client only reads
  the file on its next call).
- The token VALUE is never printed (screenshare-leak safe); only the file PATH
  is printed once when a token is first generated.

This module is DISK-DELIVERED (loaded from ``<tox_dir>/modules`` on sys.path),
so it reaches users without a ``.tox`` rebuild.
"""

import hmac
import os
import secrets
from pathlib import Path
from typing import Any, Optional

# Env var names — pair with the existing TD_API_URL (no new prefix).
# Kept as module constants so a rename (pending S2 config-consolidation) is a
# one-line change here + the mirror in live_client/td_live_client.py.
TOKEN_ENV = "TD_API_TOKEN"
TOKEN_FILE_ENV = "TD_API_TOKEN_FILE"

# Header carrying the shared secret, e.g. "Authorization: Bearer <token>".
AUTH_HEADER = "Authorization"
BEARER_PREFIX = "bearer "  # compared case-insensitively

_cached_token: Optional[str] = None
_resolved = False


def default_token_path() -> Path:
    """The token file location both processes agree on.

    ``TD_API_TOKEN_FILE`` overrides it (e.g. for tests or a shared network path);
    otherwise ``~/.td_builder/api_token``.
    """
    override = os.environ.get(TOKEN_FILE_ENV)
    if override and override.strip():
        return Path(override.strip())
    return Path.home() / ".td_builder" / "api_token"


def get_expected_token() -> Optional[str]:
    """Return the shared secret this server expects, resolving/generating once.

    Resolve order: ``TD_API_TOKEN`` env → token file → generate + persist.
    Cached process-wide. Returns ``None`` only if init genuinely fails (missing
    env AND the file can neither be read nor created) — callers MUST treat
    ``None`` as "deny everything" (fail closed).
    """
    global _cached_token, _resolved
    if _resolved:
        return _cached_token
    _cached_token = _resolve_or_create()
    _resolved = True
    return _cached_token


def _resolve_or_create() -> Optional[str]:
    env = os.environ.get(TOKEN_ENV)
    if env and env.strip():
        return env.strip()

    path = default_token_path()
    try:
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
    except OSError as exc:
        print(f"[MCP][auth][ERROR] could not read token file {path}: {exc}")
        # Fall through and attempt to (re)create it.

    try:
        token = secrets.token_urlsafe(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(token, encoding="utf-8")
        _restrict_permissions(path)
        # Print only the PATH, never the value - the textport may be shared.
        print(
            f"[MCP][auth] API token created at {path} - the local MCP client "
            f"reads it automatically. For a remote client set {TOKEN_ENV}; see "
            f"MCP/COMM_LAYER.md."
        )
        return token
    except OSError as exc:
        print(
            f"[MCP][auth][ERROR] could not create token file {path}: {exc}. "
            f"Set the {TOKEN_ENV} environment variable instead. All authenticated "
            f"routes will return 401 until a token is available."
        )
        return None


def _restrict_permissions(path: Path) -> None:
    """Best-effort chmod 600 (POSIX only). On Windows the file is already
    protected by the per-user %USERPROFILE% ACLs; os.chmod there is a no-op for
    group/other bits, so we simply skip it."""
    if os.name == "nt":
        return
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def token_matches(provided: Optional[str]) -> bool:
    """Constant-time comparison of a provided token against the expected one.

    Fails closed: ``False`` if either side is missing/empty (including when the
    token subsystem failed to initialize and ``get_expected_token()`` is None).
    """
    expected = get_expected_token()
    if not expected or not provided:
        return False
    return hmac.compare_digest(str(provided), str(expected))


def token_from_request(request: Any) -> Optional[str]:
    """Extract the bearer token from a TD WebServer DAT request dict.

    TD exposes HTTP headers as top-level keys of ``request`` (not nested), but we
    also check a nested ``request['headers']`` dict defensively in case that
    convention differs across builds. Header lookup is case-insensitive.
    """
    raw = _header_value(request, AUTH_HEADER)
    if not raw:
        return None
    raw = raw.strip()
    if raw.lower().startswith(BEARER_PREFIX):
        return raw[len(BEARER_PREFIX):].strip() or None
    # Tolerate a bare token with no scheme.
    return raw or None


def _header_value(request: Any, name: str) -> Optional[str]:
    if not isinstance(request, dict):
        return None
    target = name.lower()
    nested = request.get("headers")
    if isinstance(nested, dict):
        for key, value in nested.items():
            if isinstance(key, str) and key.lower() == target:
                return value if isinstance(value, str) else str(value)
    for key, value in request.items():
        if isinstance(key, str) and key.lower() == target:
            return value if isinstance(value, str) else str(value)
    return None

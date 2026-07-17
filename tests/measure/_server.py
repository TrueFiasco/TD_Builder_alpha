"""In-process loader for the td-builder MCP server.

The real server lives at META_AGENTIC_TOOL/mcp_server.py. Its stdio loop is
guarded by `if __name__ == "__main__":`, so importing the module as a normal
module (NOT run_name="__main__") gives us its `list_tools` / `call_tool`
coroutines without starting the protocol loop.

Two import side effects are handled here:
  1. The module sets `sys.stdout = sys.stderr` at import time (stdout-pollution
     guard for the JSON-RPC channel). We restore real stdout afterwards so
     pytest capture works.
  2. It starts a daemon KB warm-up thread and lazy-loads a sentence-transformers
     model on the first KB-dependent tool call. That is slow (~1-2 min) on the
     first such call; callers should allow a generous timeout.

`__file__` resolution is preserved (module loaded from its true path) so the
server resolves the KB bundle to <root>/KB exactly as in production.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import threading
from pathlib import Path
from types import ModuleType

ALPHA_ROOT = Path(__file__).resolve().parents[2]  # C:\TD_builder_alpha
SERVER_PATH = ALPHA_ROOT / "MCP" / "server_core" / "mcp_server.py"

_server_mod: ModuleType | None = None
_load_error: BaseException | None = None
_lock = threading.Lock()


def load_server() -> ModuleType:
    """Import the server once (process-wide). Raises with a clear message on failure."""
    global _server_mod, _load_error
    with _lock:
        if _server_mod is not None:
            return _server_mod
        if _load_error is not None:
            raise RuntimeError(f"server import previously failed: {_load_error!r}") from _load_error

        root = str(ALPHA_ROOT)
        if root not in sys.path:
            sys.path.insert(0, root)

        # W7 hermeticity: pin the USER component dir to a fresh empty tmp dir
        # BEFORE the server module import. The server boots user_search=True and
        # the builder's registry merge resolves TD_BUILDER_USER_DIR at call time
        # — without this pin, every gate run (tests/measure, tests/acceptance,
        # agent-eval Lane R + identity derivation, all of which boot through this
        # loader) would silently measure the maintainer's real ~/.td_builder.
        os.environ["TD_BUILDER_USER_DIR"] = tempfile.mkdtemp(prefix="td_user_pin_")
        # Pin the palette root too — a SEPARATE override, because the palette is
        # NOT under ~/.td_builder and the pin above does not reach it. Unpinned it
        # resolves to the maintainer's REAL Documents/Derivative/Palette, which
        # register_component(save_to_palette=true) mkdirs and copies into. Needed
        # HERE and not only in tests/conftest.py because this loader is also the
        # server seam for non-pytest callers (agent-eval Lane R replays a recorded
        # register_component through eval/agent_eval/inproc.py, where no pytest
        # fixture is in play).
        os.environ["TD_USER_PALETTE_DIR"] = tempfile.mkdtemp(prefix="td_palette_pin_")

        try:
            import bootstrap  # repo-root PYTHONPATH shim

            bootstrap.setup()

            spec = importlib.util.spec_from_file_location(
                "td_builder_mcp_server", str(SERVER_PATH)
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot create import spec for {SERVER_PATH}")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            try:
                spec.loader.exec_module(mod)
            finally:
                # Server redirected stdout -> stderr at import; restore it so
                # pytest's capture sees test output normally.
                if sys.__stdout__ is not None:
                    sys.stdout = sys.__stdout__
        except BaseException as exc:  # noqa: BLE001 - re-raised with context
            _load_error = exc
            raise RuntimeError(
                f"Failed to import td-builder MCP server from {SERVER_PATH}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        for attr in ("call_tool", "list_tools"):
            if not hasattr(mod, attr):
                raise RuntimeError(
                    f"server module loaded but missing '{attr}' "
                    f"(MCP SDK decorator contract changed?)"
                )
        _server_mod = mod
        return mod


LIVE_SERVER_PATH = ALPHA_ROOT / "MCP" / "live_server.py"
_live_mod: ModuleType | None = None
_live_lock = threading.Lock()


def load_live_server() -> ModuleType:
    """Import the live-TD server (MCP/live_server.py) once (process-wide)."""
    global _live_mod
    with _live_lock:
        if _live_mod is not None:
            return _live_mod
        live_client = str(ALPHA_ROOT / "MCP" / "live_client")
        if live_client not in sys.path:
            sys.path.insert(0, live_client)
        spec = importlib.util.spec_from_file_location("td_builder_live_server", str(LIVE_SERVER_PATH))
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot create import spec for {LIVE_SERVER_PATH}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        for attr in ("call_tool", "list_tools"):
            if not hasattr(mod, attr):
                raise RuntimeError(f"live server missing '{attr}'")
        _live_mod = mod
        return mod

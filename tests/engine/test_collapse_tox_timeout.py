"""Repro for the build-timeout hang-guard.

`_collapse_tox` shelled out to `toecollapse` with NO subprocess timeout, so a hung
toecollapse would block the build (and the MCP request) indefinitely. The fix bounds the
subprocess with a generous timeout and, on TimeoutExpired, fails gracefully (returns None)
with a message that points at the deterministic on-disk path — because the *client-side*
~45s tool-call timeout (which the server cannot override) often fires while the .tox still
completes on disk.

KB-independent: drives `_collapse_tox` directly with subprocess mocked.
"""
import subprocess as _sp
import sys
import types
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from meta_agentic.execution import tox_builder as tb  # noqa: E402


def test_collapse_tox_times_out_gracefully(tmp_path, monkeypatch):
    b = tb.ToxBuilder(str(tmp_path), verbose=False)
    b.output_dir = Path(str(tmp_path))
    name = "hang"
    (tmp_path / f"{name}.tox.toc").write_text("# 4 0 0 0 1\n", encoding="utf-8")

    # toecollapse "resolves" to a dummy, and the subprocess "hangs" (TimeoutExpired).
    monkeypatch.setattr(tb, "resolve_td_tool", lambda *_a, **_k: "toecollapse")

    def fake_run(*_a, **kwargs):
        # The fix must pass a timeout; surface it so we can assert it's bounded.
        assert kwargs.get("timeout"), "subprocess.run must be called with a timeout"
        raise _sp.TimeoutExpired(cmd="toecollapse", timeout=kwargs["timeout"])

    monkeypatch.setattr(
        tb, "subprocess",
        types.SimpleNamespace(run=fake_run, TimeoutExpired=_sp.TimeoutExpired),
    )

    # Must NOT propagate TimeoutExpired; returns None (build failed cleanly).
    assert b._collapse_tox(name) is None

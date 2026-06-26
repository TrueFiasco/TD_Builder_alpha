"""Round-3 Stream 2 — expand_toe_file robustness.

(2a) toeexpand must run under a timeout so a stuck process can't block the request
     forever; on TimeoutExpired the tool returns its normal ok:false envelope.
(2b) the summary must flag cross-project references (absolute op('/...') / paths whose
     first segment != the component root) so dormant foreign refs are visible.
"""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from core.models import ParameterValue  # noqa: E402


# ---- 2b: foreign-reference lint (pure helper, via the loaded server module) ----

def _net(project, ops):
    return SimpleNamespace(metadata=SimpleNamespace(project_name=project), operators=ops)


def test_scan_foreign_refs_flags_cross_project(server):
    scan = getattr(server, "_scan_foreign_refs", None)
    assert callable(scan), "_scan_foreign_refs not defined on server module"

    expr = ParameterValue(value=0, expression="op('/project1/foo')['tx']")
    ops = [
        SimpleNamespace(path="/comp/a", parameters={
            "tx": expr,                 # foreign op() expression
            "instanceop": "/comp/src",  # internal absolute (same root) -> NOT foreign
            "label": "hello world",     # not a path
        }),
        SimpleNamespace(path="/comp/b", parameters={"top": "/otherproj/render"}),  # foreign absolute value
    ]
    refs = scan(_net("comp", ops))
    flagged = {(r["path"], r["ref"]) for r in refs}

    assert ("/comp/a", "/project1/foo") in flagged
    assert ("/comp/b", "/otherproj/render") in flagged
    assert not any(r["ref"] == "/comp/src" for r in refs), "internal ref must not be flagged"
    assert not any(r["param"] == "label" for r in refs), "non-path value must not be flagged"


def test_scan_foreign_refs_clean_network(server):
    scan = server._scan_foreign_refs
    ops = [SimpleNamespace(path="/comp/a", parameters={"top": "../sib", "v": 3})]
    assert scan(_net("comp", ops)) == []


# ---- 2a: toeexpand hang-guard ----

def test_expand_toe_file_times_out_cleanly(probe, tmp_path, monkeypatch):
    import paths
    dummy = tmp_path / "dummy.tox"
    dummy.write_bytes(b"\x00\x01\x02not-a-real-tox")

    # toeexpand "resolves" so we reach the subprocess; the subprocess "hangs".
    monkeypatch.setattr(paths, "resolve_td_tool", lambda *_a, **_k: "toeexpand")
    seen = {}

    def fake_run(*_a, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(cmd="toeexpand", timeout=kwargs.get("timeout", 1))

    monkeypatch.setattr(subprocess, "run", fake_run)

    r = probe.call("expand_toe_file", {"toe_path": str(dummy), "mode": "summary"})
    data = r.json()
    assert data.get("ok") is False, data
    msg = (data.get("error") or {}).get("message", "").lower()
    assert "toeexpand" in msg and ("exceed" in msg or "timeout" in msg or "abort" in msg), data
    assert seen.get("timeout"), "expand must pass a timeout to subprocess.run"

"""Offline unit tests for the live-server security hardening.

No TouchDesigner required. Covers the pure/isolatable pieces:
  - utils/auth.py: token_matches (constant-time, fail-closed) + token_from_request
  - api_service.exec_python_script: AST rewrite runs the script EXACTLY once
    (the old re-eval() double-executed a side-effectful last line)
  - td_live_client._resolve_token: never raises; returns None on any file error
  - the OpenAPI schema file loads with stdlib json (no PyYAML dependency)

The TD-side modules import `td`/`tdu`; we inject MagicMock stubs so they load
without TouchDesigner. Modules are loaded by file path under private names so we
don't collide with the installed `mcp` SDK.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULES = REPO / "MCP" / "td-webserver" / "modules"
LIVE_CLIENT = REPO / "MCP" / "live_client"
SCHEMA = MODULES / "td_server" / "openapi_server" / "openapi" / "openapi.yaml"


def _load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# auth.py is stdlib-only → load it directly by file path.
auth = _load_by_path("td_auth_under_test", MODULES / "utils" / "auth.py")


@pytest.fixture(scope="module")
def api_service_mod():
    """Import api_service.py offline with td/tdu stubbed."""
    if str(MODULES) not in sys.path:
        sys.path.append(str(MODULES))  # append: keep the real `mcp` SDK winning
    sys.modules.setdefault("td", mock.MagicMock(name="td"))
    sys.modules.setdefault("tdu", mock.MagicMock(name="tdu"))
    return _load_by_path(
        "td_api_service_under_test", MODULES / "mcp" / "services" / "api_service.py"
    )


# --------------------------------------------------------------------------
# auth.token_matches — constant-time, fail-closed
# --------------------------------------------------------------------------

def _set_expected(monkeypatch, value):
    """Force get_expected_token() to a known value without touching $HOME."""
    monkeypatch.setattr(auth, "_resolved", True, raising=False)
    monkeypatch.setattr(auth, "_cached_token", value, raising=False)


def test_token_matches_correct(monkeypatch):
    _set_expected(monkeypatch, "s3cr3t-token")
    assert auth.token_matches("s3cr3t-token") is True


def test_token_matches_wrong(monkeypatch):
    _set_expected(monkeypatch, "s3cr3t-token")
    assert auth.token_matches("s3cr3t-tokeX") is False
    assert auth.token_matches("s3cr3t") is False


def test_token_matches_missing_provided(monkeypatch):
    _set_expected(monkeypatch, "s3cr3t-token")
    assert auth.token_matches(None) is False
    assert auth.token_matches("") is False


def test_token_matches_expected_none_fails_closed(monkeypatch):
    # Token subsystem failed to initialize → deny everything.
    _set_expected(monkeypatch, None)
    assert auth.token_matches("anything") is False
    assert auth.token_matches(None) is False


# --------------------------------------------------------------------------
# auth.token_from_request — Authorization: Bearer extraction
# --------------------------------------------------------------------------

@pytest.mark.parametrize("request_dict,expected", [
    ({"Authorization": "Bearer abc123"}, "abc123"),
    ({"authorization": "bearer abc123"}, "abc123"),          # case-insensitive
    ({"Authorization": "  Bearer   abc123  "}, "abc123"),    # whitespace
    ({"headers": {"Authorization": "Bearer nested"}}, "nested"),
    ({"Authorization": "rawtoken"}, "rawtoken"),             # tolerate no scheme
    ({"method": "GET", "uri": "/api/nodes"}, None),          # no auth header
    ({}, None),
    ("not-a-dict", None),
])
def test_token_from_request(request_dict, expected):
    assert auth.token_from_request(request_dict) == expected


# --------------------------------------------------------------------------
# exec_python_script — runs the script EXACTLY once (no double side effect)
# --------------------------------------------------------------------------

@pytest.fixture
def recorder():
    """A module the exec'd script can import + call; counts invocations."""
    rec = types.ModuleType("_exec_recorder")
    state = {"n": 0}

    def hit():
        state["n"] += 1
        return state["n"]

    rec.hit = hit
    rec.state = state
    sys.modules["_exec_recorder"] = rec
    yield rec
    sys.modules.pop("_exec_recorder", None)


def test_exec_last_expr_runs_once(api_service_mod, recorder):
    svc = api_service_mod.TouchDesignerApiService()
    # Last line is a side-effectful bare expression — must run exactly once.
    res = svc.exec_python_script("import _exec_recorder\n_exec_recorder.hit()")
    assert res["success"] is True
    assert recorder.state["n"] == 1, "side-effectful last line executed more than once"
    assert res["data"]["result"] == 1


def test_exec_explicit_result_respected(api_service_mod, recorder):
    svc = api_service_mod.TouchDesignerApiService()
    # Explicit `result` set; trailing bare expr still runs once but must not
    # overwrite the explicit result.
    res = svc.exec_python_script(
        "import _exec_recorder\nresult = 42\n_exec_recorder.hit()"
    )
    assert res["success"] is True
    assert recorder.state["n"] == 1
    assert res["data"]["result"] == 42


def test_exec_single_expression_returns_value(api_service_mod):
    svc = api_service_mod.TouchDesignerApiService()
    res = svc.exec_python_script("1 + 1")
    assert res["success"] is True
    assert res["data"]["result"] == 2


def test_exec_syntax_error_wrapped(api_service_mod):
    svc = api_service_mod.TouchDesignerApiService()
    # F2: a SyntaxError now RETURNS an error_result (the partial-stdout-safe path,
    # consistent with the runtime-exception branch) instead of raising. The message
    # still carries "Script execution failed".
    res = svc.exec_python_script("def (:")
    assert res["success"] is False
    assert "Script execution failed" in res["error"]


def test_script_assigns_result_detection(api_service_mod):
    svc_cls = api_service_mod.TouchDesignerApiService
    assert svc_cls._script_assigns_result(ast.parse("result = 1"))
    assert svc_cls._script_assigns_result(ast.parse("a, result = 1, 2"))
    assert svc_cls._script_assigns_result(ast.parse("result += 1"))
    assert svc_cls._script_assigns_result(ast.parse("result: int = 1"))
    assert not svc_cls._script_assigns_result(ast.parse("x = 1\nop('a')"))
    assert not svc_cls._script_assigns_result(ast.parse("d['result'] = 1"))


# --------------------------------------------------------------------------
# session restore-point: dialog-proof BY CONSTRUCTION (a pure filesystem copy,
# NEVER project.save()) — see api_service._ensure_session_restore_point.
# Offline these prove "project.save is never called + the copy is performed
# correctly + a copy failure is swallowed and made observable". They CANNOT
# prove dialog-freeness or non-rebind against a MagicMock td — that is GATE-B
# (live HITL against the main-tree install).
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def restore_dir(tmp_path, monkeypatch):
    """Redirect restore-point writes into tmp for EVERY test in this module (never the
    real ~/.td_builder) and reset the shared module-scoped `td` mock's project path to a
    non-existent location. autouse because the exec_* tests also fire the restore point
    (exec_python_script → _ensure_session_restore_point) and the module-scoped `td` mock
    leaks td.project.folder/name across tests — without this, running a saved-project test
    before an exec test (any reordering / node-id selection) would copy into the real
    ~/.td_builder. Tests that need the dir take it by name; others still get isolated."""
    d = tmp_path / "restore_points"
    monkeypatch.setenv("TD_RESTORE_DIR", str(d))
    td = sys.modules.get("td")
    if td is not None:
        td.project.folder = str(tmp_path)
        td.project.name = "_no_such_project_.toe"  # absent → restore point skips by default
    return d


def _saved_project(td, tmp_path, name, content=b"toe-bytes"):
    """Put a real on-disk .toe for `name` and point td.project at it; returns src."""
    f = tmp_path / name
    f.write_bytes(content)
    td.project.folder = str(tmp_path)
    td.project.name = name
    td.project.save.reset_mock()
    return str(f)


def test_restore_point_saved_copies_silently(api_service_mod, tmp_path, restore_dir):
    """Saved project → the last-saved .toe is COPIED to the restore dir; project.save
    is NEVER called (no dialog/increment/rebind reachable)."""
    td = sys.modules["td"]
    src = _saved_project(td, tmp_path, "saved.toe", b"hello-toe")
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()
    td.project.save.assert_not_called()
    dst = svc._restore_point_path(src)
    assert os.path.exists(dst), "restore copy was not created"
    assert Path(dst).read_bytes() == b"hello-toe", "restore copy content mismatch"
    assert svc._restore_point_status.startswith("ok:")


def test_restore_point_untitled_skips(api_service_mod, tmp_path, restore_dir):
    """Genuinely never-saved (no file on disk) → skip: no copy, no save, no raise."""
    td = sys.modules["td"]
    td.project.folder = str(tmp_path)
    td.project.name = "never_saved.toe"  # does NOT exist on disk
    td.project.save.reset_mock()
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()  # must not raise
    td.project.save.assert_not_called()
    assert not list(restore_dir.glob("*.toe")), "no restore file for a never-saved project"
    assert svc._restore_point_status.startswith("skipped:")


def test_restore_point_untitled_NAME_but_saved_copies(api_service_mod, tmp_path, restore_dir):
    """OWNER CAVEAT: the skip keys on FILE EXISTENCE, not the name. A SAVED project
    merely named untitled.toe / NewProject.1.toe exists on disk → it COPIES."""
    td = sys.modules["td"]
    for name in ("untitled.toe", "NewProject.1.toe"):
        src = _saved_project(td, tmp_path, name)
        svc = api_service_mod.TouchDesignerApiService()
        svc._ensure_session_restore_point()
        td.project.save.assert_not_called()
        assert os.path.exists(svc._restore_point_path(src)), f"{name} should copy, not skip"
        assert svc._restore_point_status.startswith("ok:")


def test_restore_point_increment_target_exists_no_save(api_service_mod, tmp_path, restore_dir):
    """THE BUG CASE: base .toe AND a pre-existing <name>.2.toe both on disk. The old
    no-arg save incremented into .2.toe → overwrite modal → hang. Now project.save is
    called ZERO times (increment path unreachable), the copy goes to the restore dir,
    and .2.toe is left untouched."""
    td = sys.modules["td"]
    src = _saved_project(td, tmp_path, "proj.toe", b"base")
    collide = tmp_path / "proj.2.toe"
    collide.write_bytes(b"pre-existing-increment")
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()
    td.project.save.assert_not_called()  # the increment/dialog path is never taken
    assert os.path.exists(svc._restore_point_path(src))
    assert collide.read_bytes() == b"pre-existing-increment", ".2.toe must be untouched"
    assert svc._restore_point_status.startswith("ok:")


def test_restore_point_copy_failure_is_swallowed_and_observable(
    api_service_mod, tmp_path, restore_dir, monkeypatch
):
    """A copy failure (e.g. a deny-read lock) must NOT raise and must NOT block the
    mutation — it is swallowed, recorded as 'unavailable', and surfaced via status."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "saved.toe")

    def boom(*a, **k):
        raise PermissionError("locked")

    monkeypatch.setattr(api_service_mod.shutil, "copyfile", boom)
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()  # must not raise
    td.project.save.assert_not_called()
    assert svc._restore_point_status.startswith("unavailable:")


def test_restore_point_only_once(api_service_mod, tmp_path, restore_dir, monkeypatch):
    """The flag makes it a no-op after the first call: the snapshot primitive runs at
    most once per instance."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "saved.toe")
    spy = mock.Mock()
    monkeypatch.setattr(api_service_mod.TouchDesignerApiService, "_snapshot_toe", spy)
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()
    svc._ensure_session_restore_point()
    assert spy.call_count == 1


def test_restore_point_only_once_even_after_failure(api_service_mod, tmp_path, restore_dir, monkeypatch):
    """Flag-first guarantee: _session_saved is set BEFORE the copy, so a FAILED first
    snapshot must NOT retry-storm — the primitive is attempted at most once per instance
    even when it raises (guards against moving the flag-set below the try)."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "saved.toe")
    spy = mock.Mock(side_effect=PermissionError("locked"))
    monkeypatch.setattr(api_service_mod.TouchDesignerApiService, "_snapshot_toe", spy)
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_session_restore_point()  # first: raises internally → swallowed
    svc._ensure_session_restore_point()  # second: flag already set → no retry
    assert spy.call_count == 1
    assert svc._restore_point_status.startswith("unavailable:")


def test_restore_point_path_disambiguates_same_basename(api_service_mod, tmp_path, restore_dir):
    """Two projects sharing a basename in different folders get DISTINCT restore files
    in the flat dir (abs-path hash), so they never clobber each other."""
    rp = api_service_mod.TouchDesignerApiService._restore_point_path
    a = rp(str(tmp_path / "projA" / "scene.toe"))
    b = rp(str(tmp_path / "projB" / "scene.toe"))
    assert a != b, "same-basename projects must not collide"
    assert os.path.basename(a).startswith("scene.") and a.endswith(".toe")


def test_restore_point_never_calls_project_save(api_service_mod, tmp_path, restore_dir):
    """Core invariant across states: project.save() is NEVER called."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "s.toe")  # saved
    api_service_mod.TouchDesignerApiService()._ensure_session_restore_point()
    td.project.save.assert_not_called()
    td.project.name = "missing.toe"        # untitled (folder still points at tmp_path)
    td.project.save.reset_mock()
    api_service_mod.TouchDesignerApiService()._ensure_session_restore_point()
    td.project.save.assert_not_called()


# --------------------------------------------------------------------------
# D3 (W6a): explicit save_td_project tool — per-state modal-safety matrix.
# Offline these prove: wraps the shared _snapshot_toe (NOT an inline copyfile, and
# NEVER project.save()); fail-fast JSON on untitled/unwritable/locked; correct
# envelope incl. source_mtime == the src's mtime (never now()); sets _last_snapshot
# atomically with clearing _dirty_since_snapshot; never sets _session_saved. Dialog-
# freeness + non-rebind are GATE-B (live) — a MagicMock td cannot prove those.
# EVERY test asserts td.project.save.assert_not_called().
# --------------------------------------------------------------------------

def test_save_project_wraps_snapshot_toe_not_inline_copy(
    api_service_mod, tmp_path, restore_dir, monkeypatch
):
    td = sys.modules["td"]
    src = _saved_project(td, tmp_path, "proj.toe", b"bytes")
    spy = mock.Mock()
    monkeypatch.setattr(api_service_mod.TouchDesignerApiService, "_snapshot_toe", spy)
    svc = api_service_mod.TouchDesignerApiService()
    res = svc.save_project()
    assert res["success"] is True
    d = res["data"]
    assert d["saved"] is True and d["captured"] == "last_saved" and d["rebound"] is False
    assert "mutation_seq" in d
    # wraps the shared primitive with (src, dst) — proves it is NOT an inline copyfile
    assert spy.call_count == 1
    called_src, called_dst = spy.call_args[0]
    assert called_src == src and called_dst == d["path"]
    # source_mtime is the src's real mtime, never now()
    expected = api_service_mod.TouchDesignerApiService._iso_mtime(os.path.getmtime(src))
    assert d["source_mtime"] == expected
    # primary target = <folder>/Backup/<stem>.tdbuilder-restore.toe
    assert os.path.basename(d["path"]) == "proj.tdbuilder-restore.toe"
    assert os.path.basename(os.path.dirname(d["path"])) == "Backup"
    td.project.save.assert_not_called()


def test_save_project_untitled_fails_fast_json(api_service_mod, tmp_path, restore_dir):
    td = sys.modules["td"]
    td.project.folder = str(tmp_path)
    td.project.name = "never_saved.toe"  # NOT on disk
    td.project.save.reset_mock()
    svc = api_service_mod.TouchDesignerApiService()
    res = svc.save_project()
    assert res["success"] is False and "save" in res["error"].lower()
    td.project.save.assert_not_called()
    assert not (tmp_path / "Backup").exists(), "no target dir created for a never-saved project"


def test_save_project_target_exists_silent_overwrite(api_service_mod, tmp_path, restore_dir):
    td = sys.modules["td"]
    src = _saved_project(td, tmp_path, "proj.toe", b"v1")
    svc = api_service_mod.TouchDesignerApiService()
    r1 = svc.save_project()
    assert r1["success"] is True
    dst = r1["data"]["path"]
    assert Path(dst).read_bytes() == b"v1"
    Path(src).write_bytes(b"v2")
    r2 = svc.save_project()
    assert r2["success"] is True and r2["data"]["path"] == dst
    assert Path(dst).read_bytes() == b"v2", "silent atomic overwrite of the stable target"
    td.project.save.assert_not_called()


def test_save_project_primary_unwritable_falls_back(
    api_service_mod, tmp_path, restore_dir, monkeypatch
):
    """Row 3: the Backup primary is unwritable -> lands in the fallback restore-dir;
    only if BOTH failed would it error. The raise IS the check (TOCTOU-free)."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    real_copyfile = api_service_mod.shutil.copyfile

    def picky(s, d):
        if "Backup" in d:  # the primary target's colocated <dst>.tmp carries "Backup"
            raise PermissionError("backup dir read-only")
        return real_copyfile(s, d)

    monkeypatch.setattr(api_service_mod.shutil, "copyfile", picky)
    svc = api_service_mod.TouchDesignerApiService()
    res = svc.save_project()
    assert res["success"] is True
    dst = res["data"]["path"]
    assert "Backup" not in dst and str(restore_dir) in dst
    assert dst.endswith(".tdbuilder-restore.toe")
    assert Path(dst).read_bytes() == b"bytes"
    td.project.save.assert_not_called()


def test_save_project_locked_dst_fails_fast_no_partial(
    api_service_mod, tmp_path, restore_dir, monkeypatch
):
    """Row 3b: os.replace onto a locked dst -> PermissionError -> both targets fail ->
    JSON error, and the primitive's finally leaves NO partial state (.tmp cleaned)."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")

    def boom(a, b):
        raise PermissionError("dst locked")

    monkeypatch.setattr(api_service_mod.os, "replace", boom)
    svc = api_service_mod.TouchDesignerApiService()
    res = svc.save_project()
    assert res["success"] is False
    # R5b: sweep BOTH the project tree and the fallback restore_dir explicitly —
    # restore_dir currently nests under tmp_path, but the sweep must not silently
    # lose the fallback target if the fixture ever moves it elsewhere.
    roots = {tmp_path} | ({restore_dir} if restore_dir.exists() else set())
    leftovers = sorted({p for root in roots for p in root.rglob("*.tdbuilder-restore.toe*")})
    assert leftovers == [], f"partial state left behind: {leftovers}"
    td.project.save.assert_not_called()


def test_save_project_reflects_external_change_before_call(api_service_mod, tmp_path, restore_dir):
    """Row 5: a pre-call external rewrite is reflected in the copy AND disclosed via
    source_mtime (not via the torn-warning, which is only for mid-copy changes)."""
    td = sys.modules["td"]
    src = _saved_project(td, tmp_path, "proj.toe", b"old")
    Path(src).write_bytes(b"new-external-bytes")
    svc = api_service_mod.TouchDesignerApiService()
    res = svc.save_project()
    assert res["success"] is True
    d = res["data"]
    assert Path(d["path"]).read_bytes() == b"new-external-bytes"
    expected = api_service_mod.TouchDesignerApiService._iso_mtime(os.path.getmtime(src))
    assert d["source_mtime"] == expected
    assert "warning" not in d
    td.project.save.assert_not_called()


def test_save_project_torn_snapshot_sets_warning(
    api_service_mod, tmp_path, restore_dir, monkeypatch
):
    """Row 5b (D-R6): the src mtime changes across the copy (external mid-copy writer)
    -> the post-copy re-stat sets the `warning` field."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    monkeypatch.setattr(
        api_service_mod.os.path, "getmtime", mock.Mock(side_effect=[1000.0, 2000.0])
    )
    svc = api_service_mod.TouchDesignerApiService()
    res = svc.save_project()
    assert res["success"] is True
    assert "warning" in res["data"] and "torn" in res["data"]["warning"].lower()
    td.project.save.assert_not_called()


def test_save_project_state_independent_of_session_and_atomic_snapshot(
    api_service_mod, tmp_path, restore_dir
):
    """save_td_project does NOT set _session_saved (stays independent of the implicit
    restore point) and sets _last_snapshot atomically with clearing the dirty flag."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    svc = api_service_mod.TouchDesignerApiService()
    assert svc._session_saved is False
    svc._dirty_since_snapshot = True  # pretend a prior API mutation dirtied the session
    res = svc.save_project()
    assert res["success"] is True
    assert svc._session_saved is False, "must NOT satisfy the implicit restore point"
    assert svc._dirty_since_snapshot is False
    assert svc._last_snapshot is not None
    assert svc._last_snapshot["path"] == res["data"]["path"]
    assert svc._last_snapshot["source_mtime"] == res["data"]["source_mtime"]
    assert svc._last_snapshot["at_seq"] == svc._mutation_seq
    td.project.save.assert_not_called()


# --------------------------------------------------------------------------
# D3: restorePoint field-contract, mutator spy, envelope stamping, recovery.
# --------------------------------------------------------------------------

def test_restore_point_field_contract(api_service_mod):
    """Drive _restore_point_status through every form and assert both the frozen
    get_td_info parse and the parallel _restore_point_triple emit {status, path,
    detail} — so a refactor of the status string cannot silently break surfacing."""
    svc = api_service_mod.TouchDesignerApiService()
    cases = {
        "not_run": {"status": "not_run", "path": None, "detail": None},
        "ok: /a/b.toe": {"status": "ok", "path": "/a/b.toe", "detail": "/a/b.toe"},
        "skipped: project not saved to disk":
            {"status": "skipped", "path": None, "detail": "project not saved to disk"},
        "unavailable: locked": {"status": "unavailable", "path": None, "detail": "locked"},
    }
    for status_str, expected in cases.items():
        svc._restore_point_status = status_str
        assert svc._restore_point_triple() == expected, status_str
        assert svc.get_td_info()["data"]["restorePoint"] == expected, status_str


def test_all_five_mutators_invoke_restore_point(
    api_service_mod, tmp_path, restore_dir, monkeypatch
):
    """A refactor must not drop a restore-point call site. Spy the UNDERLYING frozen
    _ensure_session_restore_point (the tracked wrapper invokes it transitively) and
    confirm each of the 5 mutating service methods reaches it."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    calls = []
    monkeypatch.setattr(
        api_service_mod.TouchDesignerApiService,
        "_ensure_session_restore_point",
        lambda self: calls.append(1),
    )
    invocations = (
        lambda s: s.create_node("/parent", "noiseTOP"),
        lambda s: s.delete_node("/x"),
        lambda s: s.exec_node_method("/x", "cook", [], {}),
        lambda s: s.exec_python_script("result = 1"),
        lambda s: s.update_node("/x", {"foo": 1}),
    )
    for invoke in invocations:
        calls.clear()
        svc = api_service_mod.TouchDesignerApiService()
        try:
            invoke(svc)
        except Exception:
            pass
        assert calls, "mutator did not invoke _ensure_session_restore_point"


def test_mutator_envelope_stamps_seq_and_restore_point(api_service_mod, tmp_path, restore_dir):
    """OBS-1: every mutator success envelope carries mutation_seq + restorePoint, and
    _record_mutation advances the seq / marks dirty / records the last mutation."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    svc = api_service_mod.TouchDesignerApiService()
    d = svc.create_node("/parent", "noiseTOP")["data"]
    assert d["mutation_seq"] == 1
    assert isinstance(d["restorePoint"], dict) and d["restorePoint"]["status"] == "ok"
    assert svc._dirty_since_snapshot is True
    assert svc._last_mutation["seq"] == 1 and svc._last_mutation["tool"] == "create_node"
    d2 = svc.update_node("/x", {"foo": 1})["data"]
    assert d2["mutation_seq"] == 2


def test_get_mutation_status_null_last_snapshot_fallback(api_service_mod, tmp_path, restore_dir):
    """Implicit-only session (no save_td_project): last_snapshot is null and the
    disclosure is computable from restore_point alone (at_seq 0, source_mtime set)."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    svc = api_service_mod.TouchDesignerApiService()
    svc.create_node("/parent", "noiseTOP")
    ms = svc.get_mutation_status()["data"]
    assert ms["last_committed_seq"] == 1
    assert ms["api_dirty_since_snapshot"] is True
    assert ms["last_snapshot"] is None
    rp = ms["restore_point"]
    assert rp["status"] == "ok" and rp["at_seq"] == 0 and rp["source_mtime"] is not None
    assert ms["last_mutation"]["tool"] == "create_node"


def test_get_mutation_status_no_rollback_target_when_skipped(api_service_mod, tmp_path, restore_dir):
    """Untitled project: restore_point.status is skipped and its staleness fields are
    null — the agent must read this as NO rollback target, never a stale number."""
    td = sys.modules["td"]
    td.project.folder = str(tmp_path)
    td.project.name = "never.toe"  # not on disk -> restore point skips
    td.project.save.reset_mock()
    svc = api_service_mod.TouchDesignerApiService()
    svc.create_node("/parent", "noiseTOP")  # fires the (skipped) restore point
    rp = svc.get_mutation_status()["data"]["restore_point"]
    assert rp["status"] == "skipped"
    assert rp["source_mtime"] is None and rp["at_seq"] is None


def test_get_mutation_status_after_explicit_save(api_service_mod, tmp_path, restore_dir):
    """save_td_project populates last_snapshot and clears the dirty flag; a checkpoint
    is NOT itself a mutation (seq unchanged)."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    svc = api_service_mod.TouchDesignerApiService()
    svc.create_node("/parent", "noiseTOP")  # seq 1, dirty
    save = svc.save_project()
    ms = svc.get_mutation_status()["data"]
    assert ms["api_dirty_since_snapshot"] is False
    assert ms["last_snapshot"] is not None
    assert ms["last_snapshot"]["path"] == save["data"]["path"]
    assert ms["last_snapshot"]["at_seq"] == 1
    assert ms["last_committed_seq"] == 1  # the save did not advance the seq


def test_exec_script_failure_marks_dirty_no_seq_bump(api_service_mod, tmp_path, restore_dir):
    """R1: a script that raises IN-BAND may have half-mutated the graph before the
    exception. The commit receipt must NOT advance (nothing committed), but the
    session must go dirty and last_mutation must record outcome='error' — otherwise
    get_mutation_status reports a clean api_dirty_since_snapshot=false over a
    possibly-torn graph. (F2 reshaped this path to RETURN an error_result rather
    than raise — the dirty-flag contract is identical either way.)"""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    svc = api_service_mod.TouchDesignerApiService()
    res = svc.exec_python_script("x = 1\nraise RuntimeError('mid-script boom')")
    assert res["success"] is False and "mid-script boom" in res["error"]
    assert svc._mutation_seq == 0, "a failed exec must NOT advance the commit receipt"
    assert svc._dirty_since_snapshot is True, "failed exec may have half-mutated the graph"
    lm = svc._last_mutation
    assert lm["outcome"] == "error" and lm["tool"] == "exec_python_script"
    assert lm["seq"] == 0  # receipt of the last COMMIT, not this failure
    ms = svc.get_mutation_status()["data"]
    assert ms["last_committed_seq"] == 0 and ms["api_dirty_since_snapshot"] is True


def test_exec_script_pre_execution_failure_stays_clean(api_service_mod, tmp_path, restore_dir):
    """R1 boundary: failures BEFORE any user code runs — a parse SyntaxError and the
    time.sleep static guard — cannot have mutated the graph, so they must NOT mark
    the session dirty (only the in-band exec failure path does)."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    svc = api_service_mod.TouchDesignerApiService()
    assert svc.exec_python_script("def broken(:")["success"] is False
    assert svc.exec_python_script("import time\ntime.sleep(5)")["success"] is False
    assert svc._dirty_since_snapshot is False
    assert svc._last_mutation is None


def test_exec_node_method_failure_marks_dirty_no_seq_bump(
    api_service_mod, tmp_path, restore_dir
):
    """R1 (same contract, effectful-method path): exec_node_method's method call
    raises -> exception propagates unchanged, seq unchanged, dirty True."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    node = mock.MagicMock(name="node")
    node.valid = True
    node.cook = mock.Mock(side_effect=RuntimeError("cook exploded"))
    with mock.patch.object(td, "op", return_value=node):
        svc = api_service_mod.TouchDesignerApiService()
        with pytest.raises(RuntimeError, match="cook exploded"):
            svc.exec_node_method("/x", "cook", [], {})
    assert svc._mutation_seq == 0
    assert svc._dirty_since_snapshot is True
    lm = svc._last_mutation
    assert lm["outcome"] == "error" and lm["tool"] == "exec_node_method"
    assert lm["target"] == "/x"


def test_torn_snapshot_warning_persists_to_mutation_status(
    api_service_mod, tmp_path, restore_dir, monkeypatch
):
    """R2: the D-R6 torn-copy warning must survive PAST the one-shot save response —
    get_mutation_status.last_snapshot carries it (the timeout/recovery reader is
    exactly who needs it). The dirty flag still clears: it tracks post-snapshot
    mutations, not snapshot quality."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    monkeypatch.setattr(
        api_service_mod.os.path, "getmtime", mock.Mock(side_effect=[1000.0, 2000.0])
    )
    svc = api_service_mod.TouchDesignerApiService()
    svc._dirty_since_snapshot = True  # pretend a prior mutation dirtied the session
    res = svc.save_project()
    assert res["success"] is True and "warning" in res["data"]
    ms = svc.get_mutation_status()["data"]
    assert ms["last_snapshot"]["warning"] == res["data"]["warning"]
    assert "torn" in ms["last_snapshot"]["warning"].lower()
    assert ms["api_dirty_since_snapshot"] is False
    td.project.save.assert_not_called()


def test_clean_snapshot_has_no_warning_key(api_service_mod, tmp_path, restore_dir):
    """R2 inverse: an untorn checkpoint's last_snapshot must NOT carry a warning key
    (absence is the clean-anchor signal)."""
    td = sys.modules["td"]
    _saved_project(td, tmp_path, "proj.toe", b"bytes")
    svc = api_service_mod.TouchDesignerApiService()
    assert svc.save_project()["success"] is True
    assert "warning" not in svc.get_mutation_status()["data"]["last_snapshot"]


def test_restore_point_meta_captured_on_ok(api_service_mod, tmp_path, restore_dir):
    """The tracked wrapper records {source_mtime, at_seq:0} pre-copy when the implicit
    copy lands (the only moment source_mtime exists — copyfile drops mtime)."""
    td = sys.modules["td"]
    src = _saved_project(td, tmp_path, "proj.toe", b"bytes")
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_restore_point_tracked()
    assert svc._restore_point_status.startswith("ok")
    assert svc._restore_point_meta is not None and svc._restore_point_meta["at_seq"] == 0
    expected = api_service_mod.TouchDesignerApiService._iso_mtime(os.path.getmtime(src))
    assert svc._restore_point_meta["source_mtime"] == expected


def test_restore_point_meta_none_when_skipped(api_service_mod, tmp_path, restore_dir):
    td = sys.modules["td"]
    td.project.folder = str(tmp_path)
    td.project.name = "never.toe"  # not on disk -> skipped
    td.project.save.reset_mock()
    svc = api_service_mod.TouchDesignerApiService()
    svc._ensure_restore_point_tracked()
    assert svc._restore_point_status.startswith("skipped")
    assert svc._restore_point_meta is None


# --------------------------------------------------------------------------
# client _resolve_token — never raises; None on any file error
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client_mod():
    if str(LIVE_CLIENT) not in sys.path:
        sys.path.insert(0, str(LIVE_CLIENT))
    return _load_by_path("td_live_client_under_test", LIVE_CLIENT / "td_live_client.py")


def test_resolve_token_env_wins(client_mod, monkeypatch):
    monkeypatch.setenv("TD_API_TOKEN", "env-token")
    assert client_mod._resolve_token() == "env-token"


def test_resolve_token_from_file(client_mod, monkeypatch, tmp_path):
    monkeypatch.delenv("TD_API_TOKEN", raising=False)
    f = tmp_path / "api_token"
    f.write_text("file-token\n", encoding="utf-8")
    monkeypatch.setenv("TD_API_TOKEN_FILE", str(f))
    assert client_mod._resolve_token() == "file-token"


def test_resolve_token_missing_file_returns_none(client_mod, monkeypatch, tmp_path):
    monkeypatch.delenv("TD_API_TOKEN", raising=False)
    monkeypatch.setenv("TD_API_TOKEN_FILE", str(tmp_path / "does_not_exist"))
    assert client_mod._resolve_token() is None


def test_resolve_token_unreadable_returns_none(client_mod, monkeypatch, tmp_path):
    # Point at a directory → read_text raises OSError → must be swallowed → None.
    monkeypatch.delenv("TD_API_TOKEN", raising=False)
    monkeypatch.setenv("TD_API_TOKEN_FILE", str(tmp_path))
    assert client_mod._resolve_token() is None


# --------------------------------------------------------------------------
# auth-constant cross-process sync — client <-> TD side must agree to
# authenticate at all. Both modules declare the env names + default token
# path independently ("a rename is a one-line change on both sides"); these
# tests are the enforcement that comment promises. Values are compared, not
# symbols: the constant NAMES differ across the modules by design
# (TD_API_TOKEN_ENV vs TOKEN_ENV).
# --------------------------------------------------------------------------

def test_token_env_names_match_across_processes(client_mod):
    assert client_mod.TD_API_TOKEN_ENV == auth.TOKEN_ENV
    assert client_mod.TD_API_TOKEN_FILE_ENV == auth.TOKEN_FILE_ENV


def test_default_token_path_agrees_no_override(client_mod, monkeypatch):
    monkeypatch.delenv(auth.TOKEN_FILE_ENV, raising=False)
    assert client_mod._default_token_path() == auth.default_token_path()
    # The contract both sides derive independently:
    assert auth.default_token_path() == Path.home() / ".td_builder" / "api_token"


def test_default_token_path_agrees_under_override(client_mod, monkeypatch, tmp_path):
    target = tmp_path / "shared" / "api_token"
    # Padded value: both sides must apply the same .strip().
    monkeypatch.setenv(auth.TOKEN_FILE_ENV, f"  {target}  ")
    assert client_mod._default_token_path() == auth.default_token_path() == target


# --------------------------------------------------------------------------
# schema loads with stdlib json (no PyYAML)
# --------------------------------------------------------------------------

def test_schema_loads_as_json():
    with open(SCHEMA, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    assert isinstance(schema, dict)
    assert "paths" in schema and schema["paths"]


def test_bootstrap_setup_loads_schema_offline(monkeypatch):
    """The boot logic now lives in modules/bootstrap_mcp.py (thin-bootstrap
    restructure), so setup(modules_path) runs offline — no parent()/td. This is
    the stock-TD "schema loads without PyYAML" proof that was previously
    impossible to run offline."""
    bootstrap = _load_by_path("td_bootstrap_mcp_under_test", MODULES / "bootstrap_mcp.py")
    fake_mcp = types.ModuleType("mcp")
    monkeypatch.setitem(sys.modules, "mcp", fake_mcp)
    bootstrap.setup(str(MODULES))
    assert isinstance(fake_mcp.openapi_schema, dict)
    assert fake_mcp.openapi_schema.get("paths")
    assert fake_mcp.schema_load_error is None

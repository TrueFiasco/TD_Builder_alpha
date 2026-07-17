r"""Hermetic unit tests for the D4 feedback spine (MCP/feedback*.py).

Lives in tests/unit so the hermetic + engine-kb CI lanes collect it (it sat
at tests/ top level until 2026-07-17, which no lane selects — 38 orphaned
tests). Deliberately NOT under tests/acceptance or tests/measure, keeping the
standing `pytest tests\acceptance tests\measure` gate unchanged. These tests
need no KB and no running server: they drive the decorator with a FAKE async
dispatch and duck-typed envelope objects, and point TD_FEEDBACK_DIR at a tmp
dir. (One exception: test_d4_01 uses the `server` fixture → auto requires_kb
→ engine-kb lane only.)
"""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "MCP"))

import env_identity          # noqa: E402
import feedback              # noqa: E402
import feedback_classify as fc  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def TextObj(text):
    return SimpleNamespace(type="text", text=text)


def ImageObj():
    return SimpleNamespace(type="image", data="BASE64==", mimeType="image/png")


def jtext(obj):
    return TextObj(json.dumps(obj))


@pytest.fixture(autouse=True)
def _reset_and_isolate(tmp_path, monkeypatch):
    """Fresh module caches + a tmp records dir + flag OFF, before every test."""
    monkeypatch.setenv("TD_FEEDBACK_DIR", str(tmp_path / "feedback"))
    monkeypatch.delenv("TD_FEEDBACK_ENABLED", raising=False)
    monkeypatch.delenv("TD_BUILDER_ROOT", raising=False)
    feedback._identity_cache.clear()
    feedback._config_default_cache = None
    feedback._scrub_cache = None
    feedback._last_sweep_date = None
    yield


def _wrap(fn, server="td-builder-test", tool_names=("a", "b")):
    return feedback.feedback_recorded(
        server=server, server_version="9.9", kb_root=str(_REPO / "no_such_kb"),
        instructions_text="rules", tool_names=tool_names,
    )(fn)


def _read_lines():
    d = feedback.feedback_dir()
    files = sorted(d.glob("*.jsonl"))
    lines = []
    for f in files:
        lines += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    return files, lines


# --------------------------------------------------------------------------- #
# Off is a no-op; on is transparent
# --------------------------------------------------------------------------- #
def test_off_is_noop(monkeypatch):
    sentinel = [TextObj("hello")]

    async def fn(name, arguments):
        return sentinel

    out = asyncio.run(_wrap(fn)("hybrid_search", {"query": "x"}))
    assert out is sentinel                     # same object -> byte-identical envelope
    files, lines = _read_lines()
    assert files == [] and lines == []         # nothing written when off


def test_on_returns_identical_and_records(monkeypatch):
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")
    sentinel = [TextObj(json.dumps({"anything": 1}))]

    async def fn(name, arguments):
        return sentinel

    out = asyncio.run(_wrap(fn)("hybrid_search", {"query": "x"}))
    assert out is sentinel                     # recorder never swaps the object
    files, lines = _read_lines()
    assert len(files) == 1
    header, rec = lines[0], lines[1]
    assert header["kind"] == "session_header"
    assert header["identity"]["server_version"] == "9.9"
    assert header["identity"]["tool_inventory_hash"] == env_identity.tool_inventory_hash(("a", "b"))
    assert header["identity"]["instructions_hash"] == env_identity.sha256_text("rules")
    assert rec["kind"] == "call" and rec["tool"] == "hybrid_search"
    assert rec["outcome"] == "unknown"         # non-adapter tool -> honestly unknown
    assert "latency_ms" in rec


def test_recorder_failure_is_isolated(monkeypatch):
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")
    monkeypatch.setattr(feedback, "_build_record",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    sentinel = [TextObj("ok")]

    async def fn(name, arguments):
        return sentinel

    out = asyncio.run(_wrap(fn)("get_operator_info", {"operator_name": "add"}))
    assert out is sentinel                     # tool result survives a writer crash
    _, lines = _read_lines()
    assert lines == []                         # nothing written, nothing raised


def test_recorder_writes_nothing_to_stdout(monkeypatch):
    """stdout is the MCP JSON-RPC channel: the recorder must write ONLY to its file,
    never stdout — on a normal call and on a recorder failure (no stray print)."""
    import contextlib
    import io
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")

    async def fn(name, arguments):
        return [jtext({"valid": True, "errors": []})]

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        asyncio.run(_wrap(fn)("td_validate", {"network": {"x": 1}}))
        monkeypatch.setattr(feedback, "_build_record",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        asyncio.run(_wrap(fn)("td_validate", {"network": {"x": 1}}))
    assert buf.getvalue() == ""                       # JSON-RPC channel stays pristine
    _, lines = _read_lines()
    assert any(x.get("kind") == "call" for x in lines)  # first (pre-failure) call recorded


def test_exception_path_reraises_and_records(monkeypatch):
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")

    async def fn(name, arguments):
        raise ValueError("kaboom")

    with pytest.raises(ValueError):
        asyncio.run(_wrap(fn)("td_validate", {}))
    _, lines = _read_lines()
    rec = lines[1]
    assert rec["outcome"] == "error"
    assert rec["exception"]["type"] == "ValueError"


# --------------------------------------------------------------------------- #
# Classifier — read-only, three-state, per-tool adapters
# --------------------------------------------------------------------------- #
def test_classifier_is_read_only():
    env = [jtext({"valid": False, "errors": [{"message": "bad wire"}]})]
    before = copy.deepcopy([o.__dict__ for o in env])
    fc.classify("td_validate", env, None)
    assert [o.__dict__ for o in env] == before      # envelope never mutated


@pytest.mark.parametrize("tool,envelope,expect", [
    # td_validate
    ("td_validate", jtext({"valid": True, "errors": []}), ("success", None)),
    ("td_validate", jtext({"valid": False, "errors": [{"message": "x"}]}),
     ("error", "validation_error")),
    ("td_validate", jtext({"error": "Validation error: boom", "traceback": "..."}),
     ("unknown", None)),                                            # no 'valid' key
    ("td_validate", TextObj("Error: 'network' is required"), ("unknown", None)),
    # td_build_project
    ("td_build_project", jtext({"status": "SUCCESS"}), ("success", None)),
    ("td_build_project", jtext({"status": "ERROR", "message": "no file"}),
     ("error", "build_failure")),
    ("td_build_project", jtext({"status": "STARTED", "job_id": "abc"}), ("unknown", None)),
    # td_build_status — the BLOCKER + its three sibling traps
    ("td_build_status", jtext({"status": "done", "result": {"status": "SUCCESS"}}),
     ("success", None)),
    ("td_build_status", jtext({"status": "done", "result": {"status": "ERROR", "message": "boom"}}),
     ("error", "build_failure")),                                  # done-but-FAILED (blocker)
    ("td_build_status", jtext({"status": "running", "started": 1}), ("unknown", None)),
    ("td_build_status", jtext({"status": "error", "error": "crash", "traceback": "..."}),
     ("error", "build_failure")),                                  # worker crash (lowercase)
    ("td_build_status", jtext({"status": "ERROR", "message": "Unknown job_id: x"}),
     ("unknown", None)),                                           # bad lookup (uppercase)
    # non-adapter / degenerate returns -> unknown, never a crash
    ("hybrid_search", jtext({"semantic_results": []}), ("unknown", None)),
    ("td_convert", jtext({"anything": [1, 2, 3]}), ("unknown", None)),
    ("capture_top_output", ImageObj(), ("unknown", None)),
    ("get_operator_info", [], ("unknown", None)),
    ("get_expert_prompt", TextObj("raw prompt, not json"), ("unknown", None)),
])
def test_classifier_matrix(tool, envelope, expect):
    env = envelope if isinstance(envelope, list) else [envelope]
    c = fc.classify(tool, env, None)
    outcome, event = expect
    assert c["outcome"] == outcome
    assert c.get("event_type") == event


def test_catchall_traceback_is_an_exception():
    env = [TextObj("Error: something broke\nTraceback (most recent call last):\n"
                   "  File x\nKeyError: 'z'")]
    c = fc.classify("query_graph", env, None)
    assert c["outcome"] == "error"
    assert c["exception"]["type"] == "KeyError"


def test_done_failed_build_is_error_end_to_end(monkeypatch):
    """The blocker, through the whole recorder: a done-but-failed status is an error."""
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")
    env = [jtext({"status": "done", "result": {"status": "ERROR", "message": "builder blew up"}})]

    async def fn(name, arguments):
        return env

    asyncio.run(_wrap(fn)("td_build_status", {"job_id": "abc"}))
    _, lines = _read_lines()
    rec = lines[1]
    assert rec["outcome"] == "error"
    assert rec["event_type"] == "build_failure"


# --------------------------------------------------------------------------- #
# Privacy scrubbing
# --------------------------------------------------------------------------- #
def test_scrub_home_and_root(monkeypatch):
    monkeypatch.setenv("TD_BUILDER_ROOT", r"C:\rel\td")
    feedback._scrub_cache = None
    s = feedback.scrub_text(r"failed at C:\rel\td\MCP\x.py and " + str(Path.home()) + r"\secret")
    assert "<ROOT>" in s and "C:\\rel\\td" not in s
    assert "<HOME>" in s


def test_args_redaction_masks_secrets_and_bounds(monkeypatch):
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")
    big = {"operators": [{"i": i} for i in range(500)]}

    async def fn(name, arguments):
        return [TextObj("ok")]

    asyncio.run(_wrap(fn)("td_build_project",
                          {"api_token": "sk-secret", "design": big, "n": 5}))
    _, lines = _read_lines()
    args = lines[1]["args"]
    assert args["api_token"] == "<redacted>"
    assert args["n"] == 5
    assert args["design"].get("_type") == "dict"        # big payload summarized, not stored


def test_exception_message_is_scrubbed(monkeypatch):
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")
    monkeypatch.setenv("TD_BUILDER_ROOT", r"C:\rel\td")
    feedback._scrub_cache = None
    home_leak = str(Path.home())

    async def fn(name, arguments):
        raise RuntimeError(f"opening {home_leak}\\file failed")

    with pytest.raises(RuntimeError):
        asyncio.run(_wrap(fn)("td_validate", {}))
    _, lines = _read_lines()
    assert home_leak not in json.dumps(lines[1])
    assert "<HOME>" in lines[1]["exception"]["message"]


# --------------------------------------------------------------------------- #
# Concurrency
# --------------------------------------------------------------------------- #
def test_concurrent_writes_are_wellformed(monkeypatch):
    """Drive the synchronous write path from many OS THREADS so threading.Lock is
    genuinely contended (a single-threaded asyncio.gather never contends it, and the
    test would pass even with the lock removed). Guards: no torn line, exactly one
    header, all N calls intact."""
    import concurrent.futures as cf
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")

    def do(i):
        feedback._emit("td-builder-test", "9.9", str(_REPO / "no_such_kb"), "rules", ("a",),
                       "hybrid_search", {"i": i}, [TextObj("ok")], None, 1.0)

    with cf.ThreadPoolExecutor(max_workers=16) as ex:
        list(ex.map(do, range(60)))

    files, lines = _read_lines()
    assert len(files) == 1
    assert sum(1 for x in lines if x.get("kind") == "session_header") == 1
    assert sum(1 for x in lines if x.get("kind") == "call") == 60   # every line intact JSON


# --------------------------------------------------------------------------- #
# No network — enforced, not just asserted
# --------------------------------------------------------------------------- #
def test_no_network_recorder_and_exporter(monkeypatch):
    """The recorder WRITE path and the exporter are both synchronous and open no
    sockets. Drive them directly (not through asyncio, whose Windows loop legitimately
    needs a socketpair) with socket/urlopen forced to raise, and assert both complete."""
    import socket

    def _boom(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")

    # Load the exporter BEFORE disabling sockets (import must not fault); then run it
    # AFTER — proving neither the write path nor the export opens a connection.
    spec = importlib.util.spec_from_file_location(
        "export_feedback", _REPO / "scripts" / "export_feedback.py")
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)

    monkeypatch.setattr(socket, "socket", _boom)
    try:
        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", _boom)
    except Exception:
        pass

    feedback._emit("td-builder-test", "9.9", str(_REPO / "no_such_kb"), "rules", ("a",),
                   "td_validate", {"network": {"x": 1}},
                   [jtext({"valid": True, "errors": []})], None, 1.0)
    _, lines = _read_lines()
    assert any(x.get("kind") == "call" for x in lines)

    out_zip = feedback.feedback_dir().parent / "bundle.zip"
    rc = exporter.main(["--out", str(out_zip)])
    assert rc == 0 and out_zip.exists()


def test_export_bundle_contents(monkeypatch):
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")

    async def fn(name, arguments):
        return [jtext({"valid": False, "errors": [{"message": "bad"}]})]

    asyncio.run(_wrap(fn)("td_validate", {"network": {"x": 1}}))

    spec = importlib.util.spec_from_file_location(
        "export_feedback", _REPO / "scripts" / "export_feedback.py")
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    out_zip = feedback.feedback_dir().parent / "bundle.zip"
    assert exporter.main(["--out", str(out_zip)]) == 0

    import zipfile
    with zipfile.ZipFile(out_zip) as z:
        names = set(z.namelist())
        assert {"REPORT.md", "records.jsonl", "sessions.jsonl"} <= names
        report = z.read("REPORT.md").decode("utf-8")
        assert "validation_error" in report


# --------------------------------------------------------------------------- #
# Twin-guard: MCP/env_identity.py must agree with eval/agent_eval/identity.py
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Integration through the REAL @app.call_tool dispatch (d4-test-01)
# --------------------------------------------------------------------------- #
def test_d4_01_neutrality_through_real_dispatch(server, monkeypatch):
    """Exercise the decorator on the ACTUAL registered mcp_server.call_tool (not a
    fake fn), so CI guards eval-neutrality against a future decorator reorder or an
    SDK re-wrap change. get_server_info is deterministic and not KB-gated, so the OFF
    and ON envelopes must be byte-identical. Uses the conftest `server` fixture ->
    auto requires_kb -> runs in the engine-kb lane, skipped in the KB-free lane."""
    d = feedback.feedback_dir()

    # OFF (flag left unset by the autouse fixture): envelope out, nothing recorded.
    off = asyncio.run(server.call_tool("get_server_info", {}))
    assert isinstance(off, list) and len(off) == 1 and getattr(off[0], "type", None) == "text"
    assert not (d.exists() and list(d.glob("*.jsonl")))

    # ON: byte-identical envelope (recorder is read-only), exactly one record.
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")
    feedback._identity_cache.clear()
    on = asyncio.run(server.call_tool("get_server_info", {}))
    assert isinstance(on, list) and len(on) == 1
    assert on[0].text == off[0].text                 # recorder added nothing to the envelope

    lines = [json.loads(x) for f in sorted(d.glob("*.jsonl"))
             for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert sum(1 for x in lines if x.get("kind") == "session_header") == 1
    calls = [x for x in lines if x.get("kind") == "call"]
    assert len(calls) == 1 and calls[0]["tool"] == "get_server_info"
    assert calls[0]["outcome"] == "unknown"          # non-adapter tool -> honestly unknown


def _load_twin():
    twin_path = _REPO / "eval" / "agent_eval" / "identity.py"
    spec = importlib.util.spec_from_file_location("eval_identity_twin", twin_path)
    twin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(twin)
    return twin


def test_env_identity_twin_agrees(tmp_path):
    twin = _load_twin()
    samples = [
        r"C:\x\.claude\worktrees\wt-1\KB\operators.json",
        r"C:\Program Files\Derivative\KB",
        "/home/u/proj/KB",
    ]
    for s in samples:
        assert env_identity.redact_path(s) == twin.redact_path(s)
    assert env_identity.sha256_text("hello") == twin.sha256_text("hello")
    assert (env_identity.tool_inventory_hash(["b", "a", "c"])
            == twin.tool_inventory_hash(["b", "a", "c"]))
    # kb_identity is the most consequential twin (its output is embedded in the
    # recorded header) — compare both the present-file and absent-file branches.
    (tmp_path / "manifest.json").write_text('{"version": "9.9"}', encoding="utf-8")
    (tmp_path / "operators.json").write_text('{"x": 1}', encoding="utf-8")
    assert env_identity.kb_identity(tmp_path) == twin.kb_identity(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert env_identity.kb_identity(empty) == twin.kb_identity(empty)


# --------------------------------------------------------------------------- #
# Config precedence (JSON layer) + privacy regressions (from adversarial review)
# --------------------------------------------------------------------------- #
def test_json_layer_default_enables(monkeypatch):
    """The search_config.json layer (feedback_enabled) must be honored when the env
    var is unset — exercised by monkeypatching the config default the loader returns."""
    monkeypatch.delenv("TD_FEEDBACK_ENABLED", raising=False)
    monkeypatch.setattr(feedback, "_config_default", lambda: "true")
    assert feedback._enabled() is True


def test_real_env_overrides_json_layer(monkeypatch):
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "false")
    monkeypatch.setattr(feedback, "_config_default", lambda: "true")
    assert feedback._enabled() is False


def test_nested_secret_is_masked(monkeypatch):
    monkeypatch.setenv("TD_FEEDBACK_ENABLED", "1")

    async def fn(name, arguments):
        return [TextObj("ok")]

    asyncio.run(_wrap(fn)("td_build_project",
                          {"config": {"api_token": "sk-live-DEEP", "n": 1},
                           "headers": {"authorization": "Bearer XYZ"}}))
    _, lines = _read_lines()
    blob = json.dumps(lines[1])
    assert "sk-live-DEEP" not in blob and "Bearer XYZ" not in blob   # nothing leaks
    args = lines[1]["args"]
    assert args["config"]["api_token"] == "<redacted>"              # masked at depth
    assert args["config"]["n"] == 1                                  # non-secret kept


def test_scrub_inferred_root_when_env_unset(monkeypatch):
    """On a real install TD_BUILDER_ROOT is often unset; the inferred release root
    must still scrub."""
    monkeypatch.delenv("TD_BUILDER_ROOT", raising=False)
    feedback._scrub_cache = None
    root = str(Path(feedback.__file__).resolve().parents[1])
    s = feedback.scrub_text(f"failed reading {root}\\KB\\operators.json")
    assert "<ROOT>" in s and root not in s


def test_scrub_bare_worktree_root(monkeypatch):
    """A path ending exactly at the worktree dir (no trailing separator) must scrub."""
    monkeypatch.delenv("TD_BUILDER_ROOT", raising=False)
    feedback._scrub_cache = None
    assert feedback.scrub_text(r"C:\dev\.claude\worktrees\wt-1") == "<ROOT>"
    assert feedback.scrub_text(r"C:\dev\.claude\worktrees\wt-1\MCP\a.py") == r"<ROOT>\MCP\a.py"
    assert "wt-1" not in feedback.scrub_text(r"dir C:\dev\.claude\worktrees\wt-1 missing")

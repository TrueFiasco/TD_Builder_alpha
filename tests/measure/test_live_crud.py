"""D4 — Live-TD CRUD round-trip.

Demonstrates the live-TD bridge end-to-end:
  create_td_node -> update_td_node_parameters -> read back -> delete_td_node
on a Constant CHOP under /test, with guaranteed try/finally cleanup so the
project is left unchanged regardless of outcome.

Scoring (CaseScore, 0..1 per step):
  - created            (node exists after create)
  - param_set          (value0 updated, no error envelope)
  - read_back          (read value within tolerance of 0.5)
  - deleted_clean      (delete OK, final existence check shows gone)
The composite score is the mean.

Falls through cleanly when TD isn't reachable: the test is skipped, the
measure run doesn't fail.
"""
from __future__ import annotations

import os
import time

import pytest

from measure.harness import CaseScore, emit

PARENT = "/test"
NODE_TYPE = "constantCHOP"
TARGET_VALUE = 0.5
READ_TOL = 1e-3


def _ensure_test_base(probe) -> bool:
    """Create /test under the project root if it doesn't already exist."""
    script = (
        'from td import baseCOMP\n'
        'parent = op("/test")\n'
        'if parent is None:\n'
        '    root_op = op("/") or op("/project1")\n'
        '    if root_op is None:\n'
        '        raise RuntimeError("cannot locate TD project root")\n'
        '    parent = root_op.create(baseCOMP, "test")\n'
        'print("TEST_BASE_OK")\n'
    )
    r = probe.call("execute_python_script", {"script": script})
    return r.ok and "TEST_BASE_OK" in (r.text or "")


def _exists(probe, path: str) -> bool:
    """Return True iff the node at `path` exists in the running TD project."""
    r = probe.call("execute_python_script",
                   {"script": f"print(op('{path}') is not None)"})
    return r.ok and "True" in (r.text or "")


def _read_value0(probe, path: str) -> float | None:
    """Return the float value of node.par.value0, or None if not readable."""
    r = probe.call("execute_python_script",
                   {"script": f"print(op('{path}').par.value0.eval())"})
    if not r.ok:
        return None
    text = (r.text or "").strip().splitlines()[-1] if r.text else ""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def run_live_crud(probe, td_live: bool, promote: bool = False) -> dict | None:
    if not td_live:
        return None
    if not _ensure_test_base(probe):
        return emit("live_crud", [CaseScore(
            "live_crud:setup", 0.0, "setup", {},
            "could not ensure /test base in live TD"
        )], promote=promote)

    name = f"td_eval_tmp_{os.getpid()}_{int(time.time())}"
    path = f"{PARENT}/{name}"
    scores: list[CaseScore] = []
    created = False
    try:
        # CREATE -------------------------------------------------------------
        c = probe.call("create_td_node", {
            "parent_path": PARENT,
            "node_type": NODE_TYPE,
            "node_name": name,
        })
        created = c.ok and _exists(probe, path)
        scores.append(CaseScore(
            "live_crud:create", 1.0 if created else 0.0, "create",
            {"latency_ms": round(c.latency_s * 1000, 1)},
            "created" if created else f"create failed: {c.text[:90]}",
        ))
        if not created:
            return emit("live_crud", scores, promote=promote)

        # UPDATE -------------------------------------------------------------
        u = probe.call("update_td_node_parameters", {
            "node_path": path,
            "properties": {"value0": TARGET_VALUE},
        })
        scores.append(CaseScore(
            "live_crud:update", 1.0 if u.ok else 0.0, "update",
            {"latency_ms": round(u.latency_s * 1000, 1)},
            "updated" if u.ok else f"update failed: {u.text[:90]}",
        ))

        # READ-BACK ----------------------------------------------------------
        val = _read_value0(probe, path)
        read_ok = val is not None and abs(val - TARGET_VALUE) < READ_TOL
        scores.append(CaseScore(
            "live_crud:read_back", 1.0 if read_ok else 0.0, "read",
            {"observed": val if val is not None else -1.0,
             "expected": TARGET_VALUE},
            f"read {val} (expected {TARGET_VALUE})"
            if val is not None else "could not read back",
        ))

    finally:
        # DELETE  (always attempted, even on prior failure) ------------------
        if created:
            d = probe.call("delete_td_node", {"node_path": path})
            gone = (d.ok or "not found" in (d.text or "").lower()) \
                and not _exists(probe, path)
            scores.append(CaseScore(
                "live_crud:delete", 1.0 if gone else 0.0, "delete",
                {"latency_ms": round(d.latency_s * 1000, 1)},
                "deleted, project unchanged" if gone
                else f"delete left node behind: {d.text[:90]}",
            ))

    return emit("live_crud", scores, promote=promote)


def test_live_crud(probe, td_live, promote):
    """D4 — runs only when TD is reachable on 127.0.0.1:9981."""
    if not td_live:
        pytest.skip("live-TD CRUD (D4) requires TouchDesigner on 127.0.0.1:9981 "
                    "with mcp_webserver_base.tox imported")
    report = run_live_crud(probe, td_live, promote)
    assert report is not None and report["n"] >= 1, \
        "no live-CRUD steps were recorded"

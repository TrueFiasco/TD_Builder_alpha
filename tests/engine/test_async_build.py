"""Round-3 Stream 3 — opt-in async build API.

td_build_project(async_build=true) returns a job id immediately and runs the build in a
background thread; td_build_status(job_id) polls it to completion. This lets long builds
avoid the MCP client's ~45s tool-call timeout. The build core is stubbed here so the test
needs no TD binary; the synchronous path is unchanged (covered by acceptance P13).
"""
import time


def _poll(probe, job_id, tries=80, delay=0.05):
    for _ in range(tries):
        st = probe.call("td_build_status", {"job_id": job_id}).json()
        if st.get("status") in ("done", "error"):
            return st
        time.sleep(delay)
    return probe.call("td_build_status", {"job_id": job_id}).json()


def test_async_build_returns_job_id_then_completes(server, probe, monkeypatch):
    async def fake_run(network_design, design, table_data, project_name, output_dir, mode):
        return {"status": "SUCCESS", "output_file": "stub.tox", "stub": True}

    # Replace the build core so no real toecollapse/TD is needed.
    monkeypatch.setattr(server, "_run_build", fake_run, raising=False)

    r = probe.call("td_build_project", {
        "design": {"operators": [{"name": "n1", "type": "noise", "family": "CHOP"}]},
        "async_build": True,
        "project_name": "async_t",
    })
    started = r.json()
    assert started.get("status") == "STARTED", started
    job_id = started.get("job_id")
    assert job_id, started

    final = _poll(probe, job_id)
    assert final.get("status") == "done", final
    assert final.get("result", {}).get("stub") is True, final
    assert "elapsed" in final


def test_build_status_unknown_job(server, probe):
    st = probe.call("td_build_status", {"job_id": "does-not-exist"}).json()
    assert st.get("status") == "ERROR", st
    assert "job_id" in (st.get("message", "").lower())


def test_sync_build_path_unchanged_validation(server, probe):
    # async_build absent -> synchronous; an invalid op type still fails fast (pre-validation),
    # confirming the sync path + B08 validation are intact.
    r = probe.call("td_build_project", {
        "design": {"operators": [{"name": "x", "type": "totallyfaketype", "family": "CHOP"}]},
        "project_name": "sync_bad",
    })
    j = r.json()
    assert j.get("status") == "ERROR", j

"""BUG-1: `td_build_project(mode="toe")` on the SIMPLE `design` path used to silently produce a
`.tox` — `_run_build`'s advanced branch honored `mode`, but the simple-design fallthrough called
the tox-only `td_build_project()` and dropped `mode`. The fix promotes a flat simple design +
mode="toe" onto the ToeBuilderBridge (advanced) path.

These drive `_run_build` directly (the same function both the sync and async tool callers use), so
they pin the wiring regardless of whether TD's toecollapse is present. The routing assertion
(`builder == "ToeBuilderBridge"`) holds even without TD; the collapsed-`.toe`-on-disk assertions
only run when toecollapse resolves (skipped in a TD-free CI lane).
"""
import asyncio

import pytest


def test_toe_mode_routes_to_toe_builder(server, tmp_path):
    if not getattr(server, "EXPERT_WORKFLOW_ENABLED", False):
        pytest.skip("EXPERT_WORKFLOW_ENABLED is False; advanced .toe path unavailable")
    design = {
        "operators": [
            {"name": "noise1", "type": "noise", "family": "CHOP"},
            {"name": "null1", "type": "null", "family": "CHOP"},
        ],
        "connections": [{"from": "noise1", "to": "null1"}],
    }
    result = asyncio.run(server._run_build(None, design, {}, "toe_wire", str(tmp_path), "toe"))
    # Core BUG-1 fix: a flat simple design + mode="toe" must reach ToeBuilderBridge, NOT the
    # tox-only simple path. True whether or not toecollapse is on this machine.
    assert result.get("builder") == "ToeBuilderBridge", result
    if result.get("status") == "SUCCESS":
        from pathlib import Path
        out = str(result["output_file"])
        assert out.endswith(".toe"), result  # a REAL .toe, never a silent .tox
        assert Path(out).exists() and Path(out).stat().st_size > 100, result
        assert (Path(str(tmp_path)) / "toe_wire.toe.dir").is_dir(), result
    else:
        pytest.skip(f"toecollapse unavailable; wiring verified, no .toe collapsed: {result.get('message')}")


def test_tox_mode_path_unchanged(server, tmp_path):
    if not getattr(server, "EXPERT_WORKFLOW_ENABLED", False):
        pytest.skip("EXPERT_WORKFLOW_ENABLED is False")
    design = {"operators": [{"name": "noise1", "type": "noise", "family": "CHOP"}]}
    result = asyncio.run(server._run_build(None, design, {}, "tox_wire", str(tmp_path), "tox"))
    # Non-regression: simple + tox is untouched — it still uses the td_build_project envelope
    # (no "builder" key) and the promotion never fires for mode="tox".
    assert "builder" not in result, result
    if result.get("status") == "SUCCESS":
        assert str(result["output_file"]).endswith(".tox"), result
    else:
        pytest.skip(f"toecollapse unavailable: {result.get('message')}")


def test_design_level_palette_rejected_identically(server, tmp_path):
    """W4a: a design-level `palette` key (the old, invalid form) must be rejected
    IDENTICALLY across ALL THREE build entry paths — they share one guard
    (`_reject_design_level_palette`), so their error envelopes can't drift:
      1. advanced/promoted-toe  (network_design=None + mode="toe" promotes onto the
         advanced path; guard fires at the _run_build chokepoint),
      2. simple-direct          (td_build_project() inline guard),
      3. simple-through-_run_build-tox (mode="tox", no promotion; the chokepoint
         catches it before the tox-only td_build_project() fallthrough).
    Previously the advanced path silently ignored a design-level palette key."""
    if not getattr(server, "EXPERT_WORKFLOW_ENABLED", False):
        # With the flag off the simple path returns the "not available" envelope
        # before the guard, so the messages wouldn't be comparable.
        pytest.skip("EXPERT_WORKFLOW_ENABLED is False")
    palette_design = {
        "operators": [{"name": "glow", "type": "noise", "family": "CHOP"}],
        "palette": "bloom",  # design-LEVEL key = the invalid form
    }
    # 1. Advanced/promoted route (mode="toe" promotes the flat design onto the
    #    advanced path, where the guard fires before any builder).
    adv = asyncio.run(server._run_build(
        None, dict(palette_design), {}, "pal_adv", str(tmp_path), "toe"))
    # 2. Simple route, direct: td_build_project is also async -> asyncio.run (a bare
    #    call returns a coroutine, not a dict).
    simple = asyncio.run(server.td_build_project(dict(palette_design)))
    # 3. Simple route THROUGH _run_build (mode="tox", no promotion): the chokepoint
    #    catches it before the tox-only td_build_project() fallthrough is reached.
    simple_via_run = asyncio.run(server._run_build(
        None, dict(palette_design), {}, "pal_simple", str(tmp_path), "tox"))
    envelopes = {"adv_toe": adv, "simple_direct": simple, "simple_via_run_tox": simple_via_run}
    for label, env in envelopes.items():
        assert env.get("status") == "ERROR", (label, env)
    # Message equality across all three is what pins symmetry — a builder failure is
    # also ERROR and would false-pass a status-only assertion.
    msgs = {label: env["message"] for label, env in envelopes.items()}
    assert len(set(msgs.values())) == 1, msgs
    assert "per-operator field" in adv["message"], adv["message"]

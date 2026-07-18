"""Re-measure the census against a RUNNING TouchDesigner (W3 Census Lock, GT7).

The committed snapshot at eval/ground_truth/td_census.json is CI's stand-in for
live TouchDesigner. This file is the other half of that contract: on a machine
with TD actually running, it re-measures `families[]` and fails if reality has
moved. The hermetic equivalents of the structural assertions live in
tests/unit/test_census_snapshot.py against the committed file; this exists so a
reviewer on a TD machine can re-check reality with one command.

Same snapshot/live split as tests/engine/test_real_palette_parse.py, with two
deliberate differences:

  * it skips on TD not RUNNING, not on TD not installed -- the census needs the
    WebServer DAT, not a file on disk. The socket probe is duplicated from
    tests/conftest.py:154 rather than imported because the `td_live` fixture is
    session-scoped and cannot drive a collection-time skipif.
  * if TD IS reachable and the census disagrees, it FAILS LOUDLY with the
    symmetric difference. It never downgrades to a skip: that disagreement is
    the drift signal this whole wave exists to surface.

NOTE the `live_td` marker is documentation only -- it is declared in
pyproject.toml but no CI lane deselects it. The socket probe below is what
actually protects hosted runners.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import capture_td_census as C  # noqa: E402

CENSUS = json.loads(
    (REPO / "eval" / "ground_truth" / "td_census.json").read_text(encoding="utf-8"))


def _td_reachable(host: str = "127.0.0.1", port: int = 9981, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


pytestmark = [
    pytest.mark.live_td,
    pytest.mark.skipif(
        not _td_reachable(),
        reason="TouchDesigner WebServer not on 127.0.0.1:9981 "
               "(NOTE: a MINIMIZED TouchDesigner accepts the socket but never "
               "answers -- if this hangs rather than skips, restore the window)"),
]


@pytest.fixture(scope="module")
def live():
    try:
        return C._exec_in_td(C.REMOTE_SNIPPET, timeout=60.0)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"TD accepted the socket but the census failed: {exc}")


def test_live_build_matches_the_snapshot(live):
    """Guard-band: compare the build FIRST. On a different build the operator sets
    legitimately differ, and dumping 647 names of noise would bury the real
    message, which is 're-capture'."""
    assert live["td_build"] == CENSUS["td_build"], (
        f"snapshot is for build {CENSUS['td_build']}, this machine runs "
        f"{live['td_build']} -- re-capture with "
        f"`python scripts/capture_td_census.py` and re-pin deliberately")


def test_live_total_and_families_match(live):
    assert live["total_operators"] == CENSUS["total_operators"]
    assert sorted(live["families_seen"]) == sorted(CENSUS["families_seen"])
    assert live["by_family"] == CENSUS["by_family"]


def test_live_operator_sets_match_exactly(live):
    """The drift signal. Reported as a symmetric difference per family so the
    failure names what changed rather than that something did."""
    for fam in sorted(CENSUS["families_seen"]):
        snap = set(CENSUS["operators"][fam])
        now = set(live["operators"].get(fam, []))
        assert snap == now, (
            f"{fam}: live-only={sorted(now - snap)} snapshot-only={sorted(snap - now)}")


def test_live_capture_has_no_malformed_names(live):
    """`families[FAM]` holds CLASSES; a repr leak would look like a plausible
    operator name rather than an error."""
    assert live["malformed"] == []

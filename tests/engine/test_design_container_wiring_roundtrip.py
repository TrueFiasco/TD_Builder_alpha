"""Wires into design-defined components survive a REAL toecollapse/toeexpand round trip.

The probe design (tests/fixtures/design_container_wiring_probe.json) is the shape a long
real-world build lost its wires on: container A with two Out ops, container B with two
In ops, wired A/out1 -> B/in1 and A/out2 -> B/in2. The offline unit tests pin the bytes
the builder writes (tests/unit/test_design_container_wiring.py); this test proves
TouchDesigner's own tools keep them: the build is collapsed to a .toe, expanded again
with toeexpand, and B.network must still carry both compinputs rows.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from paths import resolve_td_tool  # noqa: E402
from meta_agentic.execution.toe_builder_bridge import ToeBuilderBridge  # noqa: E402

pytestmark = [
    pytest.mark.requires_kb,  # the probe's parameter values resolve against KB/operators.json
    pytest.mark.skipif(
        resolve_td_tool("toeexpand") is None or resolve_td_tool("toecollapse") is None,
        reason="TouchDesigner tools (toeexpand/toecollapse) not installed",
    ),
]

FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "design_container_wiring_probe.json"


def test_probe_wires_into_component_survive_round_trip(tmp_path):
    design = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bridge = ToeBuilderBridge(tmp_path / "build", verbose=False)
    toe = bridge.build_from_design(design, "probe")
    assert toe is not None and toe.exists(), "build did not collapse to a .toe"
    assert bridge.wires_written == 3

    rt = tmp_path / "rt"
    rt.mkdir()
    shutil.copy(toe, rt / "probe.toe")
    subprocess.run([str(resolve_td_tool("toeexpand")), "probe.toe"], cwd=rt,
                   capture_output=True, text=True, timeout=120)
    d = rt / "probe.toe.dir" / "project1"
    assert (d / "B.network").read_text(encoding="utf-8") == (
        "1\ncompinputs\n{\n"
        "0 \tA/out1\n\tin1\n\tTOP\n"
        "1 \tA/out2\n\tin2\n\tCHOP\n"
        "}\nend\n")
    assert "inputs" not in (d / "B" / "in1.n").read_text(encoding="utf-8")
    assert "0\tnull1\n" in (d / "A" / "out1.n").read_text(encoding="utf-8")

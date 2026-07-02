"""Offline unit tests for palette-v2: the external-tox placeholder emission.

No TouchDesigner required (assertions read the .tox.dir plain files; the final
toecollapse step is irrelevant here). Ground truth for every byte shape asserted
below is a live TD 2025.32820 save+toeexpand of a wired external-tox COMP plus a
live loadTox round-trip of the builder's own output (2026-07-02):

  - wires INTO a palette placeholder survive ONLY as a `compinputs` block in the
    comp's .network sidecar (re-bound by INNER in-op name after the external tox
    loads); an `inputs` block in the placeholder's own .n is silently dropped;
  - wires OUT survive ONLY as consumer .n input refs that path INTO the comp
    ('analysis/out1'), never the sibling name;
  - externaltox for derivative/user sources is a parameter EXPRESSION (mode 49)
    off app.samplesFolder / app.userPaletteFolder so the path tracks the running
    install (multi-install machines, OneDrive-redirected Documents);
  - file paths are emitted RAW: _param_lines' expression auto-detection would
    silently promote constant paths containing 'ext.' ('text.tox') to mode 49.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "MCP" / "server_core")):
    if p not in sys.path:
        sys.path.insert(0, p)

from meta_agentic.execution import toe_builder_bridge as bridge  # noqa: E402
from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402

TEST_REGISTRY = {
    "components": {
        "audioAnalysis": {
            "source": "derivative",
            "tox_path": "Tools/audioAnalysis.tox",
            "wrapper": True,
            "subcompname": "audioAnalysis",
            "inner_type": "COMP:container",
            "inputs": [{"index": 0, "in_op": "in1", "family": "CHOP"}],
            "outputs": [{"index": 0, "out_op": "out1", "family": "CHOP"},
                        {"index": 1, "out_op": "out2", "family": "CHOP"}],
        },
        "myUserComp": {
            "source": "user",
            "tox_path": "myUserComp.tox",
            "wrapper": False,
            "inner_type": "COMP:base",
            "inputs": [{"index": 0, "in_op": "in1", "family": "TOP"}],
            "outputs": [{"index": 0, "out_op": "out1", "family": "TOP"}],
        },
        "projText": {
            # 'text.tox' contains the 'ext.' expression-detector false-positive.
            "source": "project",
            "tox_path": "tox/text.tox",
            "wrapper": False,
            "inner_type": "COMP:base",
            "inputs": [],
            "outputs": [],
        },
    }
}


@pytest.fixture()
def registry():
    """Inject the test component registry; restore the real-file cache after."""
    saved = bridge._PALETTE_COMPONENTS_CACHE
    bridge._PALETTE_COMPONENTS_CACHE = TEST_REGISTRY
    yield TEST_REGISTRY
    bridge._PALETTE_COMPONENTS_CACHE = saved


def _build(tmp_path: Path, design: dict, name: str) -> Path:
    """Build and return the .tox.dir/<name> content directory (collapse ignored)."""
    ToxBuilder(tmp_path, verbose=False).build_tox(design, name)
    d = tmp_path / f"{name}.tox.dir" / name
    assert d.exists(), "builder produced no expanded directory"
    return d


@pytest.fixture()
def built(registry, tmp_path):
    design = {
        "operators": [
            {"name": "srcA", "type": "noiseCHOP", "position": [0, 200]},
            {"name": "analysis", "palette": "audioAnalysis", "position": [200, 200]},
            {"name": "nullA", "type": "nullCHOP", "position": [400, 200]},
            {"name": "nullSecond", "type": "nullCHOP", "position": [400, 0]},
            {"name": "userComp", "palette": "myUserComp", "position": [200, -200]},
            {"name": "textRef", "palette": "projText", "position": [200, -400]},
            {"name": "adhoc", "external_tox": "C:/assets/text.tox", "family": "COMP",
             "type": "base", "position": [200, -600]},
        ],
        "connections": [
            {"from": "srcA", "to": "analysis"},
            {"from": "analysis", "to": "nullA"},
            {"from": "analysis/out2", "to": "nullSecond"},
        ],
    }
    return _build(tmp_path, design, "pv2")


def test_placeholder_n_inner_type_and_no_inputs_block(built):
    n = (built / "analysis.n").read_text(encoding="utf-8")
    assert n.startswith("COMP:container\n"), "placeholder .n must carry the KB inner type"
    assert "inputs" not in n, "a .n inputs block on the placeholder is dropped by TD -- must not be emitted"


def test_derivative_parm_expression_and_subcompname(built):
    parm = (built / "analysis.parm").read_text(encoding="utf-8")
    assert 'externaltox 49 "" "app.samplesFolder + \'/Palette/Tools/audioAnalysis.tox\'"' in parm
    assert "enableexternaltox 0 on" in parm
    assert "subcompname 0 audioAnalysis" in parm


def test_compinputs_network_block_bytes(built):
    net = (built / "analysis.network").read_text(encoding="utf-8")
    assert net == "1\ncompinputs\n{\n0 \tsrcA\n\tin1\n\tCHOP\n}\nend\n"


def test_consumer_refs_inner_out_ops(built):
    assert "0\tanalysis/out1\n" in (built / "nullA.n").read_text(encoding="utf-8")
    # explicit inner-out path in "from" flows through untouched (output >0 selection)
    assert "0\tanalysis/out2\n" in (built / "nullSecond.n").read_text(encoding="utf-8")


def test_user_source_expression_no_subcompname(built):
    parm = (built / "userComp.parm").read_text(encoding="utf-8")
    assert 'externaltox 49 "" "app.userPaletteFolder + \'/myUserComp.tox\'"' in parm
    assert "subcompname" not in parm, "raw (non-wrapper) components must not set subcompname"


def test_project_source_constant_survives_ext_dot_trap(built):
    parm = (built / "textRef.parm").read_text(encoding="utf-8")
    assert "externaltox 0 tox/text.tox" in parm, "project path must be a mode-0 constant"
    assert "externaltox 49" not in parm, "'text.tox' must not be promoted to an expression"
    # no declared inputs -> no compinputs sidecar
    assert not (built / "textRef.network").exists()


def test_external_tox_field_constant_survives_ext_dot_trap(built):
    parm = (built / "adhoc.parm").read_text(encoding="utf-8")
    assert "externaltox 0 C:/assets/text.tox" in parm
    assert "externaltox 49" not in parm
    assert "enableexternaltox 0 on" in parm


def test_toc_lists_network_sidecar(registry, tmp_path):
    design = {
        "operators": [
            {"name": "src", "type": "noiseCHOP", "position": [0, 0]},
            {"name": "analysis", "palette": "audioAnalysis", "position": [200, 0]},
        ],
        "connections": [{"from": "src", "to": "analysis"}],
    }
    _build(tmp_path, design, "pv2toc")
    toc = (tmp_path / "pv2toc.tox.toc").read_text(encoding="utf-8")
    assert "pv2toc/analysis.network" in toc.splitlines()


def test_unknown_palette_name_raises(registry, tmp_path):
    design = {"operators": [{"name": "x", "palette": "noSuchComponent", "position": [0, 0]}],
              "connections": []}
    with pytest.raises(ValueError, match="noSuchComponent"):
        ToxBuilder(tmp_path, verbose=False).build_tox(design, "pv2err")


def test_container_level_palette_field(registry, tmp_path):
    design = {
        "operators": [],
        "containers": [{"name": "analysis", "palette": "audioAnalysis", "position": [0, 0]}],
        "connections": [],
    }
    d = _build(tmp_path, design, "pv2cont")
    n = (d / "analysis.n").read_text(encoding="utf-8")
    assert n.startswith("COMP:container\n")
    parm = (d / "analysis.parm").read_text(encoding="utf-8")
    assert "subcompname 0 audioAnalysis" in parm


def test_shipped_registry_loads_and_has_audio_analysis():
    """The committed KB/palette_components.json parses and carries the seed entry
    with the builder-required interface fields."""
    saved = bridge._PALETTE_COMPONENTS_CACHE
    bridge._PALETTE_COMPONENTS_CACHE = None
    try:
        spec = bridge._load_palette_components()
        comp = spec.get("components", {}).get("audioAnalysis")
        assert comp, "seed entry missing from KB/palette_components.json"
        assert comp["inner_type"] == "COMP:container"
        assert comp["subcompname"] == "audioAnalysis"
        assert [o["out_op"] for o in comp["outputs"]] == ["out1", "out2"]
        assert [i["in_op"] for i in comp["inputs"]] == ["in1"]
    finally:
        bridge._PALETTE_COMPONENTS_CACHE = saved

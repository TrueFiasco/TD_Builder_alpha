"""BUG-3 integration: external_tox wiring against a REAL toeexpand manifest round trip.

Builds a genuine multi-output component .tox with ToxBuilder (in1 CHOP + two custom-named
out CHOPs — exactly the shape where 'comp/out1' defaulting is provably wrong), collapses
it, then references it via external_tox from a second design. No manifest mocking: this
exercises _resolve_external_tox_path -> toeexpand -> parse_toe_lossless ->
component_manifest -> palette_io_map -> compinputs/.n emission end to end.

Policy under test (offline manifests are NAME authorities — they name-sort):
  - bare '{"from": "fx"}' on a two-out comp fails loud naming both candidates;
  - explicit 'fx/chansOut' + a bare in-wire (single in op) emit the TD-native bytes;
  - a single-out comp auto-resolves its bare reference.
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from paths import resolve_td_tool  # noqa: E402
from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402

pytestmark = pytest.mark.skipif(
    resolve_td_tool("toeexpand") is None or resolve_td_tool("toecollapse") is None,
    reason="TouchDesigner tools (toeexpand/toecollapse) not installed",
)


def _build_component(out_dir: Path, name: str, out_names) -> str:
    """Build + collapse a real component .tox: one in CHOP, N named out CHOPs."""
    ops = [{"name": "in1", "type": "in", "family": "CHOP", "position": [0, 0]}]
    for i, out_name in enumerate(out_names):
        ops.append({"name": out_name, "type": "out", "family": "CHOP",
                    "position": [200, i * 150]})
    tox = ToxBuilder(out_dir, verbose=False).build_tox({"operators": ops}, name)
    assert tox is not None and tox.exists(), "fixture component failed to collapse"
    return str(tox).replace("\\", "/")


@pytest.fixture(scope="module")
def two_out_tox(tmp_path_factory) -> str:
    return _build_component(tmp_path_factory.mktemp("fixture2"), "fxcomp",
                            ["valueOut", "chansOut"])


@pytest.fixture(scope="module")
def one_out_tox(tmp_path_factory) -> str:
    return _build_component(tmp_path_factory.mktemp("fixture1"), "solocomp",
                            ["valueOut"])


def _design(tox_ref, conns):
    return {
        "operators": [
            {"name": "src", "type": "noise", "family": "CHOP", "position": [0, 0]},
            {"name": "fx", "external_tox": tox_ref, "position": [200, 0]},
            {"name": "null1", "type": "null", "family": "CHOP", "position": [400, 0]},
        ],
        "connections": conns,
    }


def test_bare_out_on_two_out_component_fails_naming_candidates(tmp_path, two_out_tox):
    with pytest.raises(ValueError) as ei:
        ToxBuilder(tmp_path, verbose=False).build_tox(
            _design(two_out_tox, [{"from": "fx", "to": "null1"}]), "it_bare")
    msg = str(ei.value)
    assert "never itself a data source" in msg
    assert "chansOut" in msg and "valueOut" in msg


def test_explicit_out_and_bare_in_emit_td_native_bytes(tmp_path, two_out_tox):
    ToxBuilder(tmp_path, verbose=False).build_tox(
        _design(two_out_tox, [{"from": "src", "to": "fx"},
                              {"from": "fx/chansOut", "to": "null1"}]), "it_expl")
    d = tmp_path / "it_expl.tox.dir" / "it_expl"
    n = (d / "null1.n").read_text(encoding="utf-8")
    assert "0\tfx/chansOut\n" in n, n
    net = (d / "fx.network").read_text(encoding="utf-8")
    assert net == "1\ncompinputs\n{\n0 \tsrc\n\tin1\n\tCHOP\n}\nend\n", net
    fx_n = (d / "fx.n").read_text(encoding="utf-8")
    assert "inputs" not in fx_n, "placeholder .n must carry no inputs block"


def test_single_out_component_bare_ref_auto_resolves(tmp_path, one_out_tox):
    ToxBuilder(tmp_path, verbose=False).build_tox(
        _design(one_out_tox, [{"from": "fx", "to": "null1"}]), "it_solo")
    d = tmp_path / "it_solo.tox.dir" / "it_solo"
    n = (d / "null1.n").read_text(encoding="utf-8")
    assert "0\tfx/valueOut\n" in n, n

"""Round-4 #1a — external-tox component references.

An `external_tox: "<path>"` field makes the builder write a COMP that references an
external .tox via the TD-native externaltox/enableexternaltox params (file-backed,
reusable component) instead of embedding it. Referenced components are recorded into a
per-project build-log summary (`<project>.components.md`).

Builds offline via ToxBuilder; inspects the generated .n/.parm + summary. KB-gated.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402


def test_external_tox_writes_reference_comp(tmp_path):
    design = {"operators": [
        {"name": "audio", "type": "base", "family": "COMP",
         "external_tox": "components/audioAnalysis.tox"},
    ]}
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, "extref")
    d = tmp_path / "extref.tox.dir" / "extref"
    first = (d / "audio.n").read_text(encoding="utf-8").splitlines()[0]
    assert first == "COMP:base", first
    parm = (d / "audio.parm").read_text(encoding="utf-8")
    assert "externaltox 0 components/audioAnalysis.tox" in parm, parm
    assert "enableexternaltox 0 on" in parm, parm
    # per-project component summary (build log)
    summary = (tmp_path / "extref.components.md").read_text(encoding="utf-8")
    assert "audio" in summary and "audioAnalysis.tox" in summary, summary


def test_external_tox_defaults_to_base_comp(tmp_path):
    # No COMP family given -> still a base COMP carrying the reference.
    design = {"operators": [{"name": "c", "external_tox": "lib/widget.tox"}]}
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, "e2")
    first = (tmp_path / "e2.tox.dir" / "e2" / "c.n").read_text(encoding="utf-8").splitlines()[0]
    assert first == "COMP:base", first
    parm = (tmp_path / "e2.tox.dir" / "e2" / "c.parm").read_text(encoding="utf-8")
    assert "externaltox 0 lib/widget.tox" in parm


def test_no_summary_when_no_external_comps(tmp_path):
    ToxBuilder(str(tmp_path), verbose=False).build_tox(
        {"operators": [{"name": "n1", "type": "noise", "family": "CHOP"}]}, "plain")
    assert not (tmp_path / "plain.components.md").exists()

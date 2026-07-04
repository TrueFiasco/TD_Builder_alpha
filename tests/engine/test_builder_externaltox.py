"""Round-4 #1a — external-tox component references.

An `external_tox: "<path>"` field makes the builder write a COMP that references an
external .tox via the TD-native externaltox/enableexternaltox params (file-backed,
reusable component) instead of embedding it. Referenced components are recorded into a
per-project build-log summary (`<project>.components.md`).

Builds offline via ToxBuilder; inspects the generated .n/.parm + summary. KB-gated.
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402

pytestmark = pytest.mark.requires_kb


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


# ---------------------------------------------------------------------------
# Component-import defect #1 (2026-07-02): constant externaltox paths were
# auto-promoted to mode-49 expressions by loose substring matching -- e.g.
# 'C:/components/text.tox' contains 'ext.', 'Tools/theme.tox' contains 'me.'.
# TD then evaluated the path as Python and the external tox never loaded.
# ---------------------------------------------------------------------------

def _extref_parm(tmp_path, tox_path, proj):
    design = {"operators": [{"name": "c", "type": "base", "family": "COMP",
                             "external_tox": tox_path}]}
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, proj)
    return (tmp_path / f"{proj}.tox.dir" / proj / "c.parm").read_text(encoding="utf-8")


def test_externaltox_path_with_ext_token_stays_constant(tmp_path):
    parm = _extref_parm(tmp_path, "C:/components/text.tox", "t1")
    assert "externaltox 0 C:/components/text.tox" in parm, parm
    assert "externaltox 49" not in parm, parm
    assert "enableexternaltox 0 on" in parm, parm


def test_externaltox_path_with_me_token_stays_constant(tmp_path):
    parm = _extref_parm(tmp_path, "Tools/theme.tox", "t2")
    assert "externaltox 0 Tools/theme.tox" in parm, parm
    assert "externaltox 49" not in parm, parm


def test_externaltox_dir_with_ext_token_stays_constant(tmp_path):
    # Directory segment starting with a TD-global token ('ext.') -- start-of-token
    # after '/' is excluded by the lookbehind, and externaltox is deny-listed anyway.
    parm = _extref_parm(tmp_path, "C:/ext.assets/bloom.tox", "t3")
    assert "externaltox 0 C:/ext.assets/bloom.tox" in parm, parm
    assert "externaltox 49" not in parm, parm


def test_expression_strings_still_promote(tmp_path):
    # Control: genuine TD expressions passed as plain strings keep auto-promoting.
    design = {"operators": [
        {"name": "p1", "type": "pattern", "family": "CHOP",
         "parameters": {"phase": "me.time.frame"}},
    ]}
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, "ctrl")
    parm = (tmp_path / "ctrl.tox.dir" / "ctrl" / "p1.parm").read_text(encoding="utf-8")
    assert "phase 49 0 me.time.frame" in parm, parm


def test_injected_conversion_source_still_promotes(tmp_path):
    # Control: BUG-013 auto-injects params['sop'] = "op('box1')" on wired conversion
    # ops -- the one in-code producer relying on auto-promotion.
    design = {"operators": [
        {"name": "box1", "type": "box", "family": "SOP"},
        {"name": "to_chop", "type": "sopto", "family": "CHOP"},
    ], "connections": [{"from": "box1", "to": "to_chop"}]}
    ToxBuilder(str(tmp_path), verbose=False).build_tox(design, "conv")
    parm = (tmp_path / "conv.tox.dir" / "conv" / "to_chop.parm").read_text(encoding="utf-8")
    assert "sop 49 0 op('box1')" in parm, parm


def test_is_expression_unit():
    from meta_agentic.execution.toe_builder_bridge import _is_expression

    # Real expressions promote.
    for s in ("op('a')", "me.time.frame", "absTime.frame", "parent().par.x",
              "tdu.rand(5)", "op('folder1')[0,0]", "chop('p1')[0]"):
        assert _is_expression(s), s
    # Constant paths / plain values do not (token boundaries: 'text.' != 'ext.',
    # '/ext.' is a path segment, 'loop(' != 'op(', backslash paths excluded too).
    for s in ("text.tox", "theme.tox", "C:/ext.assets/x.tox", "C:\\media\\ext.mov",
              "loop(5)", "tx ty tz", "components/audioAnalysis.tox"):
        assert not _is_expression(s), s
    # Pinned residual: a value STARTING with a TD-global token still promotes on
    # unguarded params; the file-path deny set catches it on externaltox (checked
    # against both the raw and resolved param names).
    assert _is_expression("me.jpg")
    assert not _is_expression("me.jpg", "externaltox")
    assert not _is_expression("ext.assets/x.tox", "raw_name", "externaltox")

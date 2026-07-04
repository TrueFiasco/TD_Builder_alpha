"""Round-4 #8 — make `.toe` (full project) builds first-class.

ToeBuilderBridge.build_from_design used to write thin project metadata: a `?`-delimited
`.start` (wrong format) and NO `.application`, so a built `.toe` opened with no network
editor. Ground-truthed against a real TD save+expand: `.start` is plain `cookrate`/
`realtime` lines and a `.application` desk/pane/winplacement layout is required.

Inspects the generated `.toe.dir/` (written before toecollapse, so no TD binary needed).
KB-gated by tests/conftest.py.
"""
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from meta_agentic.execution.toe_builder_bridge import ToeBuilderBridge  # noqa: E402

pytestmark = pytest.mark.requires_kb


def _build_dir(tmp_path, design, name):
    ToeBuilderBridge(Path(tmp_path), verbose=False).build_from_design(design, name)
    return Path(tmp_path) / f"{name}.toe.dir"


def test_toe_writes_application_layout(tmp_path):
    d = _build_dir(tmp_path, {"operators": [{"name": "n1", "type": "noise", "family": "CHOP"}]}, "proj")
    app_file = d / ".application"
    assert app_file.exists(), ".toe build wrote no .application (project opens with no UI)"
    app = app_file.read_text(encoding="utf-8")
    assert "neteditor" in app and "desk -p /project1" in app, app


def test_toe_start_is_correct_format(tmp_path):
    d = _build_dir(tmp_path, {"operators": [{"name": "n1", "type": "noise", "family": "CHOP"}]}, "proj2")
    start = (d / ".start").read_text(encoding="utf-8")
    assert "cookrate 60" in start and "realtime on" in start, start
    assert "?" not in start, f".start must not be a ?-delimited .parm block: {start!r}"


def test_toe_project_structure_intact(tmp_path):
    design = {
        "operators": [
            {"name": "noise1", "type": "noise", "family": "CHOP"},
            {"name": "null1", "type": "null", "family": "CHOP"},
        ],
        "connections": [{"from": "noise1", "to": "null1"}],
    }
    d = _build_dir(tmp_path, design, "proj3")
    assert (d / "project1" / "noise1.n").exists()
    assert (d / "project1" / "null1.n").exists()
    # metadata files all present in the TOC
    toc = (Path(tmp_path) / "proj3.toe.toc").read_text(encoding="utf-8")
    for f in (".application", ".start", ".root", ".grps", ".parm", ".build"):
        assert f in toc, f"{f} missing from .toc"


def test_toe_includes_perform_window(tmp_path):
    # Every TD project ships a /perform Window COMP; the build must include it.
    d = _build_dir(tmp_path, {"operators": [{"name": "n1", "type": "noise", "family": "CHOP"}]}, "pw")
    perf = d / "perform.n"
    assert perf.exists(), "no /perform window COMP written"
    assert perf.read_text(encoding="utf-8").splitlines()[0] == "COMP:window"
    parm = (d / "perform.parm").read_text(encoding="utf-8")
    assert "winop 0 project1" in parm, parm  # the perform window displays the project root
    assert "perform.n" in (Path(tmp_path) / "pw.toe.toc").read_text(encoding="utf-8")


# --- BUG-2: design flags {render,display,...} must reach the .n so a build renders ---
# Token form ground-truthed from a real TD 2025.32820 save (NewProject.toe expand): booleans
# serialize as `<name> on` except `viewer` -> `viewer 1`; `parlanguage 0` stays trailing; the
# no-flags default is byte-identical `flags =  parlanguage 0` (two spaces after `=`).

def test_toe_leaf_operator_flags_applied(tmp_path):
    # A leaf COMP (no children) is written via _write_operator -> exercises that site.
    d = _build_dir(tmp_path, {"operators": [
        {"name": "geo1", "type": "geo", "family": "COMP",
         "flags": {"render": True, "display": True}},
    ]}, "flag_leaf")
    n = (d / "project1" / "geo1.n").read_text(encoding="utf-8")
    assert "flags =  render on display on parlanguage 0" in n, n


def test_toe_container_with_children_flags_applied(tmp_path):
    # The penrose geo1/circle1 case: a COMP-with-children delegates to _write_container (the
    # container .n site), its child SOP goes through _write_operator. Both sites must honor flags.
    d = _build_dir(tmp_path, {"operators": [
        {"name": "geo1", "type": "geo", "family": "COMP",
         "flags": {"render": True, "display": True},
         "operators": [
             {"name": "circle1", "type": "circle", "family": "SOP",
              "flags": {"render": True, "display": True}},
         ]},
    ]}, "flag_cont")
    geo = (d / "project1" / "geo1.n").read_text(encoding="utf-8")       # _write_container site
    assert "flags =  render on display on parlanguage 0" in geo, geo
    circ = (d / "project1" / "geo1" / "circle1.n").read_text(encoding="utf-8")  # _write_operator site
    assert "flags =  render on display on parlanguage 0" in circ, circ


def test_toe_viewer_flag_is_numeric(tmp_path):
    # `viewer` is the one flag TD serializes numerically -> `viewer 1` (matches TD byte-for-byte).
    d = _build_dir(tmp_path, {"operators": [
        {"name": "m1", "type": "moviefilein", "family": "TOP", "flags": {"viewer": True}},
    ]}, "flag_view")
    n = (d / "project1" / "m1.n").read_text(encoding="utf-8")
    assert "flags =  viewer 1 parlanguage 0" in n, n


def test_toe_no_flags_byte_identical(tmp_path):
    # Regression guard: with no flags the line is unchanged (two spaces after `=`). The helper
    # owns the trailing separator so the empty case never grows a stray space.
    d = _build_dir(tmp_path, {"operators": [
        {"name": "n1", "type": "noise", "family": "CHOP"},
    ]}, "flag_none")
    n = (d / "project1" / "n1.n").read_text(encoding="utf-8")
    assert "flags =  parlanguage 0\n" in n, repr(n)

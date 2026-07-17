"""W1 Honest Parsers — integration proof against the REAL shipped palette.

Parses the exact comps the ultra-audit reproduced A1–A4 on, straight from the
local TouchDesigner install (toeexpand + parse_component). Skips wholesale on
machines without TD 2025.32820 — the hermetic equivalents of every assertion
live in tests/unit/test_user_components_engine.py and the committed
quotefont.tox.dir fixture; this file exists so a reviewer on a TD machine can
re-check the real-world recovery with one command.

License note: nothing from the palette is committed — the comps are read from
the user's own install at test time.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "MCP" / "server_core")):
    if p not in sys.path:
        sys.path.insert(0, p)

from kb_build import user_components as uc  # noqa: E402

PALETTE = Path("C:/Program Files/Derivative/TouchDesigner.2025.32820/Samples/Palette")

pytestmark = pytest.mark.skipif(
    not PALETTE.exists(), reason="TD 2025.32820 palette not installed")


def _parse(rel: str):
    return uc.parse_component(PALETTE / rel)


def test_masterradiomenu_escaped_quote_default_and_marker_tails():
    sk = _parse("UI/Basic Widgets/Core/masterRadioMenu.tox")
    by = {p["name"]: p for p in sk["custom_parameters"]}
    # A1: was a lone backslash with NO warning
    assert by["Menulabels"]["default"] == '"Apple" "Banana" "Kiwi" "Grape" "Hat"'
    # A1: escaped quotes inside a menu LABEL
    assert by["Tableformat"]["menu"][2]["label"] == \
        'Row 0 is header. Use "name" and "label" columns'
    # A4: '0 2 op(...).module.par()' tail — whole par was lost before
    assert [m["token"] for m in by["Value0"]["menu"]] == \
        ["apple", "banana", "kiwi", "grape", "hat"]
    # A4: the 166-entry Font menu with source-expr + quoted enable survives
    assert len(by["Font"]["menu"]) == 166


def test_movieplayer_file_override_untruncated():
    sk = _parse("Tools/moviePlayer.tox")
    by = {p["name"]: p for p in sk["custom_parameters"]}
    # A2: was '"C:/Users/greg/Desktop/Media/VJ' (truncated + quote-mangled)
    assert by["File"]["default"] == \
        "C:/Users/greg/Desktop/Media/VJ VIds iPhone 2015-2016/IMG_5661.MOV"
    assert sk["parse_warnings"] == []


def test_noise_pixel_format_menu_recovered():
    sk = _parse("Generators/noise.tox")
    by = {p["name"]: p for p in sk["custom_parameters"]}
    # A4: the entire Format par (menu, page, default) was rejected before
    assert by["Format"]["page"] == "Noise"
    assert len(by["Format"]["menu"]) == 27
    assert by["Format"]["default"] == "rgba8fixed"
    assert sk["parse_warnings"] == []


def test_changecolor_multiword_page_recovered():
    sk = _parse("ImageFilters/changeColor.tox")
    assert sk["parse_warnings"] == []
    pages = {p.get("page") for p in sk["custom_parameters"]}
    # A3: every par on the quoted multi-word page degraded before
    assert "Change Color" in pages


def test_graphplot_one_honest_warning():
    sk = _parse("Tools/graphPlot.tox")
    # 98 pars incl. 'X Units'/'Y Lines' multi-word pages (A3) and the
    # '<enable> 1 <help>' tail (A4). Exactly ONE loud degrade remains:
    # Rangeoctavesy's typecode-773198338 multi-range layout uses literal
    # `None` slot placeholders — its default is honestly OMITTED (committing
    # the string 'None' would be silent-wrong), page/order still recovered.
    assert len(sk["custom_parameters"]) >= 90
    warns = sk["parse_warnings"]
    assert len(warns) == 1 and "Rangeoctavesy" in warns[0]
    by = {p["name"]: p for p in sk["custom_parameters"]}
    assert by["Rangeoctavesy"]["page"] == "Y Units"
    assert "default" not in by["Rangeoctavesy"]

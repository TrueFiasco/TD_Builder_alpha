"""get_expert_prompt answers fit the answer budget; big prompts come in parts.

Every expert/phase prompt (phase .md + the curated expertise appended to it)
measured 41-77 KB; one at 59 KB was spilled to a file by the client in a long
real-world build and never read. Each answer must now be under 24 KB, say how
to get the next part, and the parts together must be the whole prompt — the
curated expertise still reaches the expert (Round-4 #3), just in pieces.

Hermetic: get_expert_prompt needs no KB; called through the real call_tool.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "MCP" / "server_core"))

import mcp_server as srv  # noqa: E402

BUDGET = 24 * 1024
_HEADER = re.compile(r"^\[get_expert_prompt (\S+)/(\S+): part (\d+) of (\d+)\b.*\]$")


def _call(args):
    return asyncio.run(srv.call_tool("get_expert_prompt", args))[0].text


def _cases():
    for d in sorted(p for p in srv.EXPERTS_DIR.iterdir() if p.is_dir()):
        for f in sorted(d.glob("*.md")):
            yield d.name, f.stem


@pytest.mark.parametrize("expert,phase", list(_cases()))
def test_every_part_fits_and_parts_rebuild_the_prompt(expert, phase):
    whole = srv.load_expert_prompt(expert, phase)
    first = _call({"expert_name": expert, "phase": phase})
    assert len(first.encode("utf-8")) < BUDGET
    if len(whole.encode("utf-8")) < BUDGET:
        assert first == whole  # small prompts are unchanged
        return
    m = _HEADER.match(first.split("\n", 1)[0])
    assert m, first[:300]
    n = int(m.group(4))
    assert n >= 2
    assert f"part=2" in first.split("\n", 1)[0]
    bodies = []
    for k in range(1, n + 1):
        text = first if k == 1 else _call({"expert_name": expert, "phase": phase, "part": k})
        assert len(text.encode("utf-8")) < BUDGET, (k, len(text))
        head, rest = text.split("\n", 1)
        assert _HEADER.match(head).group(3) == str(k)
        bodies.append(rest)
    assert "".join(bodies) == whole


def test_part_one_lists_where_each_expertise_file_starts():
    first = _call({"expert_name": "td_designer", "phase": "build"})
    head = first.split("\n", 1)[0]
    # td_designer's config declares expertise YAMLs; the header names them.
    assert ".yaml" in head


def test_part_out_of_range_is_an_error_naming_the_count():
    text = _call({"expert_name": "td_designer", "phase": "build", "part": 99})
    assert text.startswith("ERROR") and "part" in text and "of" in text

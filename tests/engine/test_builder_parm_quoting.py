"""Regression: .parm serialization must match TouchDesigner's whitespace-quoting.

Reproduces the "knotted looped line" session bug. TD's .parm parser is
whitespace-delimited. The single root cause was unquoted whitespace; verified
live (TD 2025.32820) an unquoted space value does two things:

  * self-truncates -- ``[3, 2, 7][me.chanIndex]`` -> ``[3,`` ("'[' was never
    closed"); ``tx ty tz`` -> ``tx``;
  * DESYNCS the line parser -- the leftover tokens drop the *following* params
    in the same .parm to their defaults. That (not the bool spelling) is what
    inverted ``specifypos``/``closed`` in the session: they sit right after an
    unquoted ``chanscope 0 tx ty tz``.

So the fix is quoting. We additionally normalize Python bools to ``on``/``off``
to match TD's own output, but TD accepts ``True``/``False``/``1``/``0`` too --
that part is hygiene, asserted below for output stability, not correctness.

Ground truth, from expanding TD's own save of the fixed component:

    numcycles 49 3 "[3, 2, 7][me.chanIndex]"
    phase 49 0 "[0.111, 0.032, 0.0][me.chanIndex]"
    chanscope 0 "tx ty tz"
    specifypos 0 off
    closed 0 on

Builds offline via the real ToxBuilder path (the one td_build_project uses). KB-gated.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402
from meta_agentic.execution.toe_builder_bridge import _td_quote_token, _td_emit_token  # noqa: E402


KNOT_DESIGN = {
    "operators": [
        {"name": "pattern1", "type": "pattern", "family": "CHOP", "parameters": {
            "channelname": "t[xyz]", "length": 600, "wavetype": "cos", "amp": 1,
            "numcycles": {"value": 3, "expr": "[3, 2, 7][me.chanIndex]"},
            "phase": {"value": 0, "expr": "[0.111, 0.032, 0.0][me.chanIndex]"},
        }},
        {"name": "knot_to_pop", "type": "chopto", "family": "POP", "parameters": {
            "chop": "pattern1", "chanssel": "spec", "chanscope": "tx ty tz",
            "attrscope": "P", "specifypos": False, "surftype": "linestrip", "closed": True,
        }},
        {"name": "out_knot", "type": "null", "family": "POP"},
    ],
    "connections": [
        {"from": "pattern1", "to": "knot_to_pop"},
        {"from": "knot_to_pop", "to": "out_knot"},
    ],
}


def _build(tmp_path):
    ToxBuilder(str(tmp_path), verbose=False).build_tox(KNOT_DESIGN, "knot")
    d = tmp_path / "knot.tox.dir" / "knot"
    return (
        (d / "pattern1.parm").read_text(encoding="utf-8"),
        (d / "knot_to_pop.parm").read_text(encoding="utf-8"),
    )


def test_space_expressions_are_quoted(tmp_path):
    pattern, _ = _build(tmp_path)
    assert 'numcycles 49 3 "[3, 2, 7][me.chanIndex]"' in pattern, pattern
    assert 'phase 49 0 "[0.111, 0.032, 0.0][me.chanIndex]"' in pattern, pattern
    # The exact corruption the session hit must NOT appear.
    assert "numcycles 49 3 [3," not in pattern, pattern


def test_space_value_is_quoted(tmp_path):
    _, chopto = _build(tmp_path)
    assert 'chanscope 0 "tx ty tz"' in chopto, chopto
    assert "chanscope 0 tx ty tz" not in chopto, chopto


def test_toggles_are_on_off_not_python_bools(tmp_path):
    _, chopto = _build(tmp_path)
    assert "specifypos 0 off" in chopto, chopto
    assert "closed 0 on" in chopto, chopto
    assert "False" not in chopto and "True" not in chopto, chopto


def test_no_space_token_left_unquoted(tmp_path):
    """Every emitted value/expression token with a space must be quoted."""
    pattern, chopto = _build(tmp_path)
    for body in (pattern, chopto):
        for line in body.splitlines():
            if line == "?" or not line.strip():
                continue
            parts = line.split(None, 2)  # name, mode, rest
            if len(parts) < 3:
                continue
            rest = parts[2]
            # A space in the value region is only legal inside double quotes.
            if " " in rest:
                assert '"' in rest, f"unquoted space in: {line!r}"


def test_helpers_unit():
    # quoting
    assert _td_quote_token("tx ty tz") == '"tx ty tz"'
    assert _td_quote_token("[3, 2, 7][me.chanIndex]") == '"[3, 2, 7][me.chanIndex]"'
    assert _td_quote_token("t[xyz]") == "t[xyz]"          # no space -> unquoted
    assert _td_quote_token('"already"') == '"already"'    # idempotent
    # toggles
    assert _td_emit_token(True) == "on"
    assert _td_emit_token(False) == "off"
    assert _td_emit_token("linestrip") == "linestrip"
    assert _td_emit_token("tx ty tz") == '"tx ty tz"'

"""Pure-function unit tests for the API-shape / param-leaf helpers (F6d + F7).

Both helpers are pure string logic with no KB dependency:
  * enhanced_graph_query._normalize_op_type_for_filter (F6d multi-word lookup bug)
  * mcp_server._strip_compound_leaf_suffix (F7 compound-leaf fallback)

Both modules import KB-free (the graph / knowledge_graph load lazily), so this whole
module runs on the KB-free lane.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SERVER_CORE = _REPO / "MCP" / "server_core"
if str(_SERVER_CORE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CORE))

import enhanced_graph_query as egq  # noqa: E402
import mcp_server as srv  # noqa: E402


# --- F6(d): multi-word operator name normalization ------------------------------
def test_normalize_multiword_wiki_name_strips_internal_space():
    # The bug: "SOP to CHOP" kept its internal space ("sop to"), so it never matched
    # the space-free node name "soptoCHOP". Post-fix it normalizes to "sopto".
    assert egq._normalize_op_type_for_filter("SOP to CHOP") == ("CHOP", "sopto")
    assert egq._normalize_op_type_for_filter("CHOP to POP") == ("POP", "chopto")


def test_normalize_single_word_and_edge_forms_unchanged():
    assert egq._normalize_op_type_for_filter("noise CHOP") == ("CHOP", "noise")
    assert egq._normalize_op_type_for_filter("constantTOP") == ("TOP", "constant")
    assert egq._normalize_op_type_for_filter("") == (None, "")


# --- F7: compound-leaf suffix stripping -----------------------------------------
def test_strip_letter_suffix_leaves_parent():
    assert srv._strip_compound_leaf_suffix("pt0posx") == "pt0pos"
    assert srv._strip_compound_leaf_suffix("constantr") == "constant"


def test_strip_digit_run_leaves_parent():
    assert srv._strip_compound_leaf_suffix("vec0value1") == "vec0value"


def test_strip_returns_candidate_even_when_parent_absent():
    # Two-stage design: the strip returns a candidate ("fontalph"); the DOWNSTREAM
    # _find_param_code then fails to find such a parent, so the fallback won't match.
    # The string transform itself still strips the trailing letter.
    assert srv._strip_compound_leaf_suffix("fontalpha") == "fontalph"


def test_strip_short_or_empty_names_return_none():
    assert srv._strip_compound_leaf_suffix("ab") is None
    assert srv._strip_compound_leaf_suffix("") is None
    assert srv._strip_compound_leaf_suffix(None) is None

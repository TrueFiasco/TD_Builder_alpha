"""Validator #3 negative-case generator.

Each mutator corrupts a known-good builder network in exactly one way and
declares which pipeline stage *should* catch it. Labels are known by
construction, so scoring is fully automatic.
"""
from __future__ import annotations

import copy
from typing import Any

# Known-good builder networks (operator-form; td_validate default layer).
GOOD_NETWORKS: dict[str, dict[str, Any]] = {
    "noise_null": {
        "meta": {"project_name": "good_noise_null", "mode": "toe"},
        "operators": [
            {"name": "noise1", "family": "CHOP", "type": "noise"},
            {"name": "null1", "family": "CHOP", "type": "null",
             "inputs": [{"index": 0, "src": "noise1"}]},
        ],
    },
    "const_math_null": {
        "meta": {"project_name": "good_chain", "mode": "toe"},
        "operators": [
            {"name": "const1", "family": "CHOP", "type": "constant"},
            {"name": "math1", "family": "CHOP", "type": "math",
             "inputs": [{"index": 0, "src": "const1"}]},
            {"name": "null1", "family": "CHOP", "type": "null",
             "inputs": [{"index": 0, "src": "math1"}]},
        ],
    },
    "movie_level": {
        "meta": {"project_name": "good_top", "mode": "toe"},
        "operators": [
            {"name": "moviein1", "family": "TOP", "type": "moviefilein"},
            {"name": "level1", "family": "TOP", "type": "level",
             "inputs": [{"index": 0, "src": "moviein1"}]},
        ],
    },
}


def good_cases() -> list[tuple[str, dict[str, Any]]]:
    return [(f"good:{k}", copy.deepcopy(v)) for k, v in GOOD_NETWORKS.items()]


def _base() -> dict[str, Any]:
    return copy.deepcopy(GOOD_NETWORKS["const_math_null"])


def negative_cases() -> list[tuple[str, dict[str, Any], set[str]]]:
    """[(case_name, mutated_net, expected_stages_that_should_flag_it), ...]."""
    cases: list[tuple[str, dict[str, Any], set[str]]] = []

    # 1. dangling reference: input points at a removed operator -> reference
    n = _base()
    n["operators"] = [o for o in n["operators"] if o["name"] != "const1"]
    cases.append(("neg:dangling_ref", n, {"reference"}))

    # 2. cycle: a -> b -> a -> logical
    n = _base()
    n["operators"] = [
        {"name": "a", "family": "CHOP", "type": "math",
         "inputs": [{"index": 0, "src": "b"}]},
        {"name": "b", "family": "CHOP", "type": "math",
         "inputs": [{"index": 0, "src": "a"}]},
    ]
    cases.append(("neg:cycle", n, {"logical"}))

    # 3. invented operator type -> semantic
    n = _base()
    n["operators"][1]["type"] = "definitelynotanoperator"
    cases.append(("neg:unknown_type", n, {"semantic"}))

    # 4. impossible family -> schema or semantic
    n = _base()
    n["operators"][0]["family"] = "ZZZ"
    cases.append(("neg:bad_family", n, {"schema", "semantic"}))

    # 5. missing required field (name) -> schema
    n = _base()
    n["operators"][1].pop("name", None)
    cases.append(("neg:missing_name", n, {"schema"}))

    # 6. self-loop -> logical
    n = _base()
    n["operators"][1]["inputs"] = [{"index": 0, "src": "math1"}]
    cases.append(("neg:self_loop", n, {"logical", "reference"}))

    return cases

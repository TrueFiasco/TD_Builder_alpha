"""Data-driven NL-prompt tests.

Every block in glsl_cases.yaml becomes its own pytest PASSED/FAILED line.
To add a test you edit the YAML — you do NOT touch this file.

    & $PY -m pytest tests/nl -v
    & $PY -m pytest tests/nl -v -k glsl_pop      # just POP cases
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

CASES_DIR = Path(__file__).parent
_WS = re.compile(r"\s+")


def _load_cases():
    cases = []
    for yml in sorted(CASES_DIR.glob("*.yaml")):
        for c in yaml.safe_load(yml.read_text(encoding="utf-8")) or []:
            cases.append(c)
    return cases


def _norm(name: str, family: str) -> tuple[str, str]:
    n = name.replace("_", " ").strip()
    fu, fl = family.upper(), family.lower()
    if n.upper().endswith(f" {fu}"):
        n = n[: -(len(fu) + 1)].strip()
    elif n.lower().endswith(fl):
        n = n[: -len(fl)]
    return fu, _WS.sub("", n).lower()


def _result_operators(data) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    if not isinstance(data, dict):
        return out
    for hit in data.get("semantic_results", []) or []:
        if not isinstance(hit, dict):
            continue
        meta = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        fam = (meta.get("family") or "").upper()
        nm = (meta.get("operator_name") or meta.get("name")
              or meta.get("operator") or meta.get("operator_type")
              or hit.get("operator_name") or hit.get("name"))
        if fam and nm:
            out.add(_norm(str(nm), fam))
    return out


_CASES = _load_cases()


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_nl_prompt(probe, case):
    r = probe.call("hybrid_search", {"query": case["prompt"], "n_results": 8})
    assert r.ok, f"hybrid_search errored: {r.text[:200]}"

    found = _result_operators(r.json())
    text = r.text.lower()

    expected = case.get("expect_operators") or []
    if expected:
        want = set()
        for e in expected:
            fam, _, typ = e.partition(":")
            want.add((fam.strip().upper(), _WS.sub("", typ.strip().lower())))
        assert want & found, (
            f"none of {sorted(want)} in top-8 results.\n"
            f"got operators: {sorted(found)}"
        )

    for kw in case.get("expect_keywords") or []:
        assert kw.lower() in text, (
            f"keyword {kw!r} not present in results for prompt:\n  {case['prompt']}"
        )

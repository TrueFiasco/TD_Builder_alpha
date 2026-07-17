"""
Predicate matching + ground-truth name-integrity for the TD Builder eval harness.

Labels in ``labeled_queries.jsonl`` reference STABLE identity fields only
(operator python_class / canonical name, parameter code, palette block name,
chunk type, __source_store, content tokens) -- never chunk ids -- so the same
labels keep working after the KB is re-chunked in Phase 1+.

A ``relevant_predicate`` is a disjunction of conjunctive clauses:

    {"clauses": [ {<field_key>: [values], ...},   # clause 1 (AND of keys)
                  {<field_key>: [values], ...} ]} # clause 2 ...

A chunk is RELEVANT iff it satisfies ANY clause (OR); a clause is satisfied iff
every field_key in it matches (AND). Supported field keys are the FIELD_MATCHERS
below; an unknown key raises (so a typo in a label fails loud, not silent).

The name-integrity gate is independent of relevance: it scans every returned
chunk and flags ones that assert an operator identity (name / operator /
operator_name / python_class) that does NOT resolve against the ground truth
(KB/operators.json + operator_ground_truth/operator_types.json), plus -- as the
documented hazard metric -- ones that surface a *retokenized* underscored
wiki-title name (e.g. ``Ableton_Link_CHOP``, ``GLSL_TOP``) as the display name.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

OP_FAMILIES = {"CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP"}

# Chunk types that, on an operator-family chunk, assert an operator identity via
# their name/operator field (used by the name-integrity gate).
_OP_IDENTITY_TYPES = {"operator", "parameter", "build_instruction", None, "", "none"}


def _norm(s: Optional[str]) -> str:
    """Collapse a name to a comparison key: lowercase, alphanumerics only.

    "Ableton Link CHOP" == "Ableton_Link_CHOP" == "abletonlinkCHOP" -> the same
    key, so spaced / underscored / token spellings all compare equal.
    """
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------
class GroundTruth:
    """Authoritative operator identity, loaded once and shared by all checks."""

    def __init__(self, operators_json: Path, operator_types_json: Path):
        self.operators_json = Path(operators_json)
        self.operator_types_json = Path(operator_types_json)

        ops = json.loads(self.operators_json.read_text(encoding="utf-8"))["operators"]
        gt = json.loads(self.operator_types_json.read_text(encoding="utf-8"))

        # operators.json -> canonical SPACED display names + python_class
        self.valid_pyclass: set[str] = set()
        self.valid_name_norm: set[str] = set()
        self.canon_display: Dict[str, str] = {}  # norm-key -> canonical spaced name
        for o in ops:
            name = o.get("name")
            pyc = o.get("python_class")
            if name:
                nk = _norm(name)
                self.valid_name_norm.add(nk)
                # operators.json names are the canonical (spaced) display form
                self.canon_display.setdefault(nk, name)
            if pyc:
                self.valid_pyclass.add(pyc.lower())

        # operator_types.json (wiki-scrape name list, NOT a live-TD capture;
        # td_create tokens are synthesized, incl. 5 phantom POPs — see
        # eval/ground_truth/README.md) -> underscored names + td_create tokens;
        # td_create + "_Class" is the derived python_class.
        for fam, entries in (gt.get("operators") or {}).items():
            for e in entries:
                nm = e.get("name")          # e.g. "Ableton_Link_CHOP"
                tdc = e.get("td_create")    # e.g. "abletonlinkCHOP"
                if nm:
                    self.valid_name_norm.add(_norm(nm))
                if tdc:
                    self.valid_name_norm.add(_norm(tdc))
                    self.valid_pyclass.add((tdc + "_Class").lower())

    # -- identity resolution -------------------------------------------------
    def pyclass_ok(self, pyclass: Optional[str]) -> bool:
        return bool(pyclass) and pyclass.lower() in self.valid_pyclass

    def name_ok(self, name: Optional[str]) -> bool:
        return bool(name) and _norm(name) in self.valid_name_norm

    def canonical_for(self, name: Optional[str]) -> Optional[str]:
        return self.canon_display.get(_norm(name)) if name else None


# ---------------------------------------------------------------------------
# Predicate matching
# ---------------------------------------------------------------------------
def _hit(chunk: Dict[str, Any], values: List[str], extractor, *, normalize=False) -> bool:
    got = extractor(chunk)
    if got is None:
        return False
    if normalize:
        allowed = {_norm(v) for v in values}
        if isinstance(got, (list, tuple, set)):
            return any(_norm(g) in allowed for g in got)
        return _norm(got) in allowed
    allowed = {str(v).lower() for v in values}
    if isinstance(got, (list, tuple, set)):
        return any(str(g).lower() in allowed for g in got)
    return str(got).lower() in allowed


def _meta(chunk):
    return chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}


def _op_name_fields(chunk):
    m = _meta(chunk)
    return [v for v in (m.get("name"), m.get("operator"), m.get("operator_name")) if v]


def _text(chunk) -> str:
    return str(chunk.get("content") or chunk.get("text") or "").lower()


# field_key -> (extractor, normalize?)  -- a clause key matches via _hit().
FIELD_MATCHERS = {
    "type_any":         (lambda c: _meta(c).get("type"), False),
    "family_any":       (lambda c: _meta(c).get("family"), False),
    "store_any":        (lambda c: _meta(c).get("__source_store"), False),
    "python_class_any": (lambda c: _meta(c).get("python_class"), False),
    "class_any":        (lambda c: _meta(c).get("class"), False),
    "method_any":       (lambda c: _meta(c).get("method"), False),
    "param_code_any":   (lambda c: _meta(c).get("parameter"), False),
    "meta_name_any":    (lambda c: _meta(c).get("name"), False),
    "term_any":         (lambda c: _meta(c).get("term"), False),
    "op_name_any":      (_op_name_fields, True),    # operator-identity, normalized
}


def _clause_matches(chunk: Dict[str, Any], clause: Dict[str, Any]) -> bool:
    for key, values in clause.items():
        if key == "text_contains_any":
            txt = _text(chunk)
            if not any(str(v).lower() in txt for v in values):
                return False
            continue
        if key not in FIELD_MATCHERS:
            raise KeyError(f"unknown predicate field '{key}' (typo in a label?)")
        extractor, normalize = FIELD_MATCHERS[key]
        if not _hit(chunk, values, extractor, normalize=normalize):
            return False
    return True


def is_relevant(chunk: Dict[str, Any], predicate: Dict[str, Any]) -> bool:
    """True iff ``chunk`` satisfies ANY clause of ``predicate`` (OR of ANDs)."""
    clauses = predicate.get("clauses")
    if not clauses:
        raise ValueError("relevant_predicate must contain a non-empty 'clauses' list")
    return any(_clause_matches(chunk, cl) for cl in clauses)


# ---------------------------------------------------------------------------
# Name-integrity gate
# ---------------------------------------------------------------------------
def check_name_integrity(chunk: Dict[str, Any], gt: GroundTruth) -> Optional[Dict[str, Any]]:
    """Classify a returned chunk's operator-name integrity.

    Returns None if the chunk asserts no operator identity. Otherwise returns a
    dict with ``status`` in {ok, unresolved, retokenized} plus the asserted
    name/class, so the caller can count + sample violations.
    """
    m = _meta(chunk)
    pyc = m.get("python_class")
    disp = next((m.get(f) for f in ("name", "operator", "operator_name") if m.get(f)), None)
    fam = m.get("family")
    ctype = (m.get("type") or "").lower() if m.get("type") is not None else None

    bears_identity = bool(pyc) or (
        bool(disp) and fam in OP_FAMILIES and (ctype in _OP_IDENTITY_TYPES)
    )
    if not bears_identity:
        return None

    resolved = gt.pyclass_ok(pyc) or gt.name_ok(disp)
    if not resolved:
        return {"status": "unresolved", "asserted": disp or pyc, "python_class": pyc,
                "family": fam, "type": m.get("type")}

    # Resolves to a real operator. Is the DISPLAY name the retokenized
    # (underscored wiki-title) form rather than the canonical spaced name?
    if disp:
        canonical = gt.canonical_for(disp) or (
            # fall back to canonical via python_class match if name didn't resolve
            None
        )
        if "_" in str(disp) and canonical is not None and disp != canonical:
            return {"status": "retokenized", "asserted": disp, "canonical": canonical,
                    "python_class": pyc, "family": fam, "type": m.get("type")}
    return {"status": "ok", "asserted": disp or pyc, "python_class": pyc}

#!/usr/bin/env python3
r"""
TRACK D -- KB-grounding guardrail (PROTOTYPE, report-only).

Grounds a builder `design`'s operator tokens against the GROUND TRUTH (the captured
live-TD `.n` token), NOT the display-derived `OperatorRegistry` key. This closes the
gap proven by the gate: today the builder emits a display-derived token (often wrong)
while the validator only recognises that same display token -- so a CORRECTLY-built op
(real token) fails `td_validate`, and a WRONGLY-built op passes. One ground-truth map,
consulted by BOTH sides, fixes both.

Two entry points (mirroring the two insertion sites in the approved plan):
  * check_design(design)  -> findings    (D2: a ValidationPipeline stage 2.5 would call this)
  * ground_design(design) -> design'      (D1: a build-time _map_op_type override)

REPORT-ONLY: this module is standalone and is NOT wired into pipeline.py or
toe_builder_bridge.py. Wiring is a reviewed follow-up (per the approved plan).

Findings:
  BUILD_TOKEN_MISMATCH -- builder_token != captured n_token (the silent space-2 bug);
                          `suggestion` carries the correct token.
  OP_NAME_NOT_GROUNDED -- (family, type) resolves to no ground-truth op (hallucination).
  NO_TD_CAPTURE        -- op is real but has no captured .tox (can't ground; warn).

Usage (demo): py -3.11 eval/build_gate/grounding_validator.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parent))
import gate_common as gc  # noqa: E402


class GroundingValidator:
    def __init__(self, canonical_map: gc.CanonicalMap | None = None):
        self.cmap = canonical_map or gc.CanonicalMap.load()
        # alias index: (family, normalized-alias) -> {n_token, op}. Aliases cover every
        # form a model might feed: the display-extracted token, the builder token's type,
        # the captured token's type, td_create (minus family), and the display name. So we
        # ground regardless of which spelling the search side handed the build side.
        self.alias = {}
        self.valid_ntokens = set()

        def _alnum(s):
            import re
            return re.sub(r"[^a-z0-9]", "", str(s or "").lower())

        for nm, r in self.cmap.operators.items():
            if not r["n_token"]:
                continue
            self.valid_ntokens.add(gc.norm_token(r["n_token"]))
            fam = r["family"]
            aliases = {r["extracted_type"],
                       r["builder_token"].split(":", 1)[-1],
                       r["n_token"].split(":", 1)[-1],
                       _alnum(nm),                                   # display name, despaced
                       _alnum(nm[:-len(fam)]) if nm.endswith(fam) else _alnum(nm)}
            if r["td_create"] and r["td_create"].endswith(fam):
                aliases.add(_alnum(r["td_create"][:-len(fam)]))     # td_create minus family
            for a in aliases:
                key = (fam, _alnum(a))
                self.alias.setdefault(key, {"n_token": r["n_token"], "op": nm, "coverage": r["coverage"]})

    def _resolve(self, type_in: str, family: str):
        """(type, family) -> (builder_token, ground_truth_n_token | None, op_name | None)."""
        import re
        bt = gc.builder_token_for(type_in, family)
        # strip a FAMILY: prefix from the fed type for alias matching
        t = type_in.split(":", 1)[-1] if ":" in type_in else type_in
        key = (family, re.sub(r"[^a-z0-9]", "", t.lower()))
        hit = self.alias.get(key)
        if hit:
            return bt, hit["n_token"], hit["op"]
        return bt, None, None

    def check_design(self, design: dict) -> list[dict]:
        findings = []
        for i, op in enumerate(design.get("operators", [])):
            type_in = op.get("type", "")
            family = op.get("family", "")
            bt, n_tok, op_name = self._resolve(type_in, family)
            loc = f"operators[{i}] type={type_in!r} family={family!r}"
            if n_tok is None:
                # already in colon form that matches a real n_token? then it's a real token, fine
                if gc.norm_token(bt) in self.valid_ntokens:
                    continue
                findings.append({"code": "OP_NAME_NOT_GROUNDED", "severity": "error",
                                 "location": loc, "builder_token": bt,
                                 "message": f"'{type_in}'/{family} -> '{bt}' resolves to no ground-truth operator"})
                continue
            if gc.norm_token(bt) != gc.norm_token(n_tok):
                findings.append({"code": "BUILD_TOKEN_MISMATCH", "severity": "error",
                                 "location": loc, "builder_token": bt, "ground_truth": n_tok,
                                 "op": op_name, "suggestion": n_tok,
                                 "message": f"builder would write '{bt}' but live TD uses '{n_tok}'"})
        return findings

    def ground_design(self, design: dict) -> dict:
        """D1 auto-correct: return a copy of design with each op's `type` replaced by the
        captured n_token (colon form) when a correction exists. Idempotent + safe (only
        overrides when the ground truth has a captured token)."""
        out = json.loads(json.dumps(design))
        for op in out.get("operators", []):
            bt, n_tok, _ = self._resolve(op.get("type", ""), op.get("family", ""))
            if n_tok and gc.norm_token(bt) != gc.norm_token(n_tok):
                op["type"] = n_tok            # colon form -> _map_op_type returns it verbatim
        return out


def _demo():
    gv = GroundingValidator()
    # feed the DISPLAY-derived tokens a KB-driven model produces (the realistic path)
    design = {"operators": [
        {"name": "a", "type": "abletonlink", "family": "CHOP"},   # abbrev -> builder CHOP:abletonlink, real CHOP:ableton
        {"name": "b", "type": "add", "family": "TOP"},           # wrong-family -> builder SOP:add, real TOP:add
        {"name": "c", "type": "camera", "family": "COMP"},       # abbrev -> builder COMP:camera, real COMP:cam
        {"name": "d", "type": "noise", "family": "CHOP"},        # clean -> CHOP:noise
        {"name": "e", "type": "totallyfakeop", "family": "TOP"}, # hallucination
    ]}
    findings = gv.check_design(design)
    print("=== GroundingValidator.check_design (report-only) ===")
    for f in findings:
        print(f"  [{f['code']}] {f['location']}  -> {f.get('message')}")
    print(f"\n  {len(findings)} finding(s) on {len(design['operators'])} ops")
    grounded = gv.ground_design(design)
    print("\n=== ground_design (D1 auto-correct) — corrected types ===")
    for o0, o1 in zip(design["operators"], grounded["operators"]):
        flag = "" if o0["type"] == o1["type"] else "  <-- corrected"
        print(f"  {o0['name']}: {o0['type']:16s} -> {o1['type']}{flag}")


if __name__ == "__main__":
    _demo()

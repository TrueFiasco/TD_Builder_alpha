#!/usr/bin/env python3
r"""
Shared foundation for the TD Builder BUILD-CORRECTNESS gate (eval/build_gate/).

This module is the DRY base imported by every track (A offline, C smoke, the
merger) and by the Track-D guardrail prototype. It exists to prove the KB's
build-critical data -- operator names, build tokens, parameter codes, defaults --
actually BUILD valid TouchDesigner, not just that it retrieves well.

It reuses the Phase-0/0.5 eval scaffolding verbatim:
  * run_eval         -- offline env (single-thread, HF offline), path resolvers
                        (resolve_kb_root strips the .claude/worktrees tail so the
                        gitignored KB is read from the MAIN tree), _main_tree().
  * predicates       -- GroundTruth, _norm, OP_FAMILIES.
  * tool_coverage    -- ParamDefaults (live-TD defaults loader), _eq_default.

THE THREE TOKEN SPACES (conflating them manufactures false mismatches):
  1. registry_key  -- OperatorRegistry._extract_type_from_name: name minus the
                      trailing " FAMILY", lowercased, spaces removed -> e.g.
                      CHOP:abletonlink, POP:pointgenerator. DISPLAY-derived.
  2. builder_token -- ToeBuilderBridge.map_op_type output (public API; grounds on
                      KB build_token, else INTERNAL_NAME_MAP + OP_TYPE_MAP); written as
                      the FIRST LINE of each op's .n. Computed here by ACTUALLY CALLING
                      the shipping public method so it can never drift from real builder
                      code (the gate imports no private builder API).
  3. n_token       -- the captured live-TD .n token (the authority for space 2),
                      read RAW from
                      operator_ground_truth/tox_expanded/{FAM}_{Name}.tox.dir/
                          sample_{Name}/op_default.n   (first line)
                      The top-level sample_{Name}.n is a COMP:base WRAPPER -- ignore it.
  (Live td_create -- the suffixed create token, e.g. abletonlinkCHOP -- is a 4th
   space used by Track B; carried here for the live round-trip.)

Run under py -3.11; KB hardlinked into the worktree (OperatorRegistry resolves it
relative to its own __file__).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# --- make eval/ importable, then pull in the Phase-0 harness (env side effects) ---
_THIS = Path(__file__).resolve()
EVAL_DIR = _THIS.parent.parent                 # eval/
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import run_eval                                  # noqa: E402  (offline env + resolvers)
from predicates import GroundTruth, OP_FAMILIES, _norm   # noqa: E402
from tool_coverage import ParamDefaults, _eq_default     # noqa: E402

REPO_ROOT = run_eval.REPO_ROOT
SERVER_CORE = run_eval.SERVER_CORE
ENGINE_ROOT = REPO_ROOT / "MCP" / "engine"

GATE_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# EXPECTED RESIDUALS — the allowlist of KNOWN, triaged, non-builder-code offline
# failures (W3a). The gate report classifies every remaining non-PASS op against
# this registry: a failure whose codes ⊆ a registered op's codes is an EXPECTED
# residual (documented, root-caused, not a builder-code defect); ANY other non-PASS
# op is a PRINCIPLED failure — an unexpected regression to investigate. A clean gate
# has ZERO principled failures. Removing an op from this registry (e.g. after the KB
# re-ground fixes its param data) simply turns any lingering failure back into a
# principled signal, which is the intent.
#
# Two residual classes remain after W3a's builder fixes (7 of the prior 14 fixed:
# Trim/Blur/HSV stale aliases + Group/Pulse/GLSL-POP/Topology resolver-collision guard):
#   * kb_param_data       — KB/operators.json ships the WRONG/typo'd param code; the
#                           resolver faithfully maps to it. Fix belongs to a KB param
#                           re-ground (operators.regrounded.json line), NOT builder code.
#   * serialization_escaping — TD escapes a backslash in a .parm STRING value ('\\t');
#                           the builder emits it raw ('\t'). A low-severity round-trip
#                           fidelity gap on backslash-bearing values; deferred rather than
#                           touch the W2b-stabilised canonical _parm_line serializer.
# ---------------------------------------------------------------------------
EXPECTED_RESIDUALS = {
    "Lookup DAT": {"cls": "kb_param_data", "codes": ["valuelocation"],
                   "reason": "KB carries typo'd code 'valueloction'; live TD uses 'valuelocation'."},
    "Rectangle SOP": {"cls": "kb_param_data", "codes": ["cameraz"],
                      "reason": "KB carries 'camz'; live TD uses 'cameraz'."},
    "Text SOP": {"cls": "kb_param_data", "codes": ["scalefonttobboxheight"],
                 "reason": "KB carries typo'd 'scalefontobboxheight'; live TD uses 'scalefonttobboxheight'."},
    "Texture SOP": {"cls": "kb_param_data", "codes": ["applyto"],
                    "reason": "KB resolves 'applyto' to the wrong code 'coord'."},
    "Bloom TOP": {"cls": "kb_param_data", "codes": ["inputimage"],
                  "reason": "KB carries 'inputimage0'; live TD uses 'inputimage'."},
    "Convert DAT": {"cls": "serialization_escaping", "codes": ["delimiters", "spacers"],
                    "reason": "backslash not escaped in .parm string value ('\\\\t' vs '\\t')."},
    "Merge DAT": {"cls": "serialization_escaping", "codes": ["spacer"],
                  "reason": "backslash not escaped in .parm string value ('\\\\t' vs '\\t')."},
}


def _failing_codes(rec: dict) -> list:
    """The codes that made an extracted-feed Track-A record fail (dropped + value-mismatch)."""
    p = rec.get("params", {}) or {}
    return list(p.get("codes_dropped", []) or []) + [
        vm.get("code") for vm in (p.get("value_mismatches", []) or []) if isinstance(vm, dict)
    ]


def classify_residual(rec: dict) -> dict:
    """Classify a non-PASS extracted-feed record: EXPECTED (documented, codes ⊆ registry)
    or PRINCIPLED (unexpected regression). PASS records classify as {"kind": "pass"}."""
    if rec.get("verdict") == "PASS":
        return {"kind": "pass"}
    op = rec.get("op")
    spec = EXPECTED_RESIDUALS.get(op)
    codes = [c for c in _failing_codes(rec) if c]
    if spec and codes and set(codes) <= set(spec["codes"]):
        return {"kind": "expected", "cls": spec["cls"], "reason": spec["reason"], "codes": codes}
    return {"kind": "principled", "codes": codes, "verdict": rec.get("verdict")}


# ---------------------------------------------------------------------------
# sys.path: BOTH import trees must coexist (mirrors mcp_server.py lines 19-23)
#   server_core -> meta_agentic.execution.tox_builder / toe_builder_bridge
#   engine      -> core.* / validation.* / api.* / builders.*
#   repo root   -> paths, eval predicates
# ---------------------------------------------------------------------------
def ensure_paths() -> None:
    for p in (str(REPO_ROOT), str(SERVER_CORE), str(ENGINE_ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Resolvers -- code from the worktree, KB DATA + ground truth from the MAIN tree
# ---------------------------------------------------------------------------
def kb_root() -> Path:
    return run_eval.resolve_kb_root(None).resolve()


def _main_tree() -> Path:
    mt = run_eval._main_tree()
    return mt if mt else REPO_ROOT


def gt_dir() -> Path:
    return _main_tree() / "New KB build" / "Resources" / "operator_ground_truth"


def operator_types_json() -> Path:
    """TRACKED eval/ground_truth/operator_types.json (corpus copy = legacy fallback).

    Deliberately NOT gt_dir()-derived: the corpus twin is untracked, so resolving
    it here made local runs and CI grade against different files the moment either
    was regenerated. gt_dir() stays corpus-pointed for params/ and tox_expanded/,
    which really do live only there.
    """
    from paths import operator_types_path
    return operator_types_path(legacy_fallback=gt_dir() / "operator_types.json")


def params_dir() -> Path:
    return gt_dir() / "params"


def tox_expanded_dir() -> Path:
    return gt_dir() / "tox_expanded"


def stage_dir() -> Path:
    d = _main_tree() / "New KB build" / "Output" / "build_gate"
    return d


def kb_operators_json() -> Path:
    """Authoritative operators.json (main tree), independent of any rebuilt KB."""
    cands = [kb_root() / "operators.json", _main_tree() / "KB" / "operators.json"]
    return next((c for c in cands if c.exists()), cands[0])


# ---------------------------------------------------------------------------
# KB / ground-truth loaders
# ---------------------------------------------------------------------------
def load_kb_operators() -> list[dict]:
    data = json.loads(kb_operators_json().read_text(encoding="utf-8"))
    return data.get("operators", [])


def load_operator_types() -> dict:
    """operator_types.json -> {(family, norm_name): td_create}."""
    raw = json.loads(operator_types_json().read_text(encoding="utf-8"))
    out: dict[tuple[str, str], str] = {}
    for fam, entries in (raw.get("operators") or {}).items():
        for e in entries:
            nm = e.get("name")
            tdc = e.get("td_create")
            if nm and tdc:
                out[(fam, _norm(nm))] = tdc
    return out


# ---------------------------------------------------------------------------
# Token derivation (replicas / shipping-code calls)
# ---------------------------------------------------------------------------
def extract_type_from_name(name: str, family: str) -> str:
    """EXACT replica of OperatorRegistry._extract_type_from_name (operator_registry.py:121):
    strip a trailing ' FAMILY', lowercase, remove spaces. 'Ableton Link CHOP'/'CHOP'
    -> 'abletonlink'; 'Point Generator POP'/'POP' -> 'pointgenerator'."""
    if family and name.endswith(f" {family}"):
        name = name[: -len(family) - 1]
    return name.lower().replace(" ", "")


_BRIDGE = None


def _bridge():
    """A throwaway ToeBuilderBridge purely for calling the SHIPPING public
    map_op_type (so builder_token cannot drift from real builder code). verbose=False
    keeps it from printing the per-call resolver trace."""
    global _BRIDGE
    if _BRIDGE is None:
        ensure_paths()
        from meta_agentic.execution.tox_builder import ToxBuilder  # subclass; inherits map_op_type
        _BRIDGE = ToxBuilder(stage_dir() / "_scratch_bridge", verbose=False)
    return _BRIDGE


def builder_token_for(type_in: str, family: str) -> str:
    """Run the SHIPPING resolver via the builder's PUBLIC API: builder input
    (type, family) -> 'FAMILY:type' .n token. The gate imports no private builder API."""
    return _bridge().map_op_type(type_in, family)


# ---------------------------------------------------------------------------
# Raw .n / .parm readers -- deliberately bypass the tolerant lossless_parser
# (it str.split()s unquoted spaces and would MASK the very serialization bugs the
#  gate exists to catch). We read the bytes TD's toeexpand wrote.
# ---------------------------------------------------------------------------
def read_n_token(n_path: Path) -> str | None:
    """First line of a .n file = the 'FAMILY:type' token. None if unreadable."""
    try:
        with open(n_path, "r", encoding="utf-8", errors="replace") as f:
            first = f.readline()
    except OSError:
        return None
    return first.rstrip("\r\n").strip() or None


def read_parm_codes(parm_path: Path) -> dict[str, tuple[str, str]]:
    """Parse a .parm file -> {code: (mode, raw_value)}.

    .parm is whitespace-delimited, '{code} {mode} {value...}', with the body
    between '?' sentinel lines. mode 0=constant, 49=python expression, etc. The
    value is taken as the remainder of the line (raw, including any quoting) so we
    compare exactly what was serialized -- not a re-normalized form.
    """
    out: dict[str, tuple[str, str]] = {}
    try:
        text = Path(parm_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s == "?":
            continue
        parts = s.split(None, 2)
        if len(parts) < 2:
            continue
        code = parts[0]
        mode = parts[1]
        val = parts[2] if len(parts) > 2 else ""
        out[code] = (mode, val)
    return out


# ---------------------------------------------------------------------------
# Token normalisation for tolerant compare (diagnostic; EXACT is the gate)
# ---------------------------------------------------------------------------
def norm_token(tok: str | None) -> str | None:
    """'CHOP:Ableton Link' -> 'chop:abletonlink' (family upper kept, type alnum-lower)."""
    if not tok:
        return None
    if ":" in tok:
        fam, typ = tok.split(":", 1)
        return f"{fam.strip().upper()}:{re.sub(r'[^a-z0-9]', '', typ.lower())}"
    return re.sub(r"[^a-z0-9]", "", tok.lower())


# ---------------------------------------------------------------------------
# Canonical map -- the heart of Track D, shared by A/B/C.
#   name -> {family, gt_name, td_create, n_token, registry_key, builder_token,
#            params_file_present, coverage}
# coverage: full | no_tox_capture | no_perturbed_file | no_td_create
# ---------------------------------------------------------------------------
class CanonicalMap:
    FILENAME = "canonical_op_map.json"

    def __init__(self, operators: dict, meta: dict | None = None):
        self.operators = operators          # KB name -> record
        self.meta = meta or {}

    # -- build -------------------------------------------------------------
    @classmethod
    def build(cls) -> "CanonicalMap":
        ensure_paths()
        kb_ops = load_kb_operators()
        td_create_idx = load_operator_types()
        texp = tox_expanded_dir()
        pdir = params_dir()

        operators: dict[str, dict] = {}
        for o in kb_ops:
            name = o.get("name")
            family = o.get("family")
            if not name or family not in OP_FAMILIES:
                continue
            gt_name = name.replace(" ", "_")
            extracted = extract_type_from_name(name, family)
            registry_key = f"{family}:{extracted}"
            try:
                btok = builder_token_for(extracted, family)
            except Exception as e:  # never let one op kill the map
                btok = f"<ERROR:{e}>"

            # captured .n token (authority): inner sample_{gt}/op_default.n
            dotdir = texp / f"{family}_{gt_name}.tox.dir"
            inner = dotdir / f"sample_{gt_name}"
            n_path = inner / "op_default.n"
            if not n_path.exists():
                n_path = inner / "op_perturbed.n"
            n_token = read_n_token(n_path) if n_path.exists() else None

            td_create = td_create_idx.get((family, _norm(name)))
            params_present = (pdir / f"{family}_{gt_name}_defaults.json").exists()
            perturbed_present = (pdir / f"{family}_{gt_name}_perturbed.json").exists()

            if n_token is None:
                coverage = "no_tox_capture"
            elif not perturbed_present:
                coverage = "no_perturbed_file"
            elif td_create is None:
                coverage = "no_td_create"
            else:
                coverage = "full"

            operators[name] = {
                "family": family,
                "gt_name": gt_name,
                "python_class": o.get("python_class"),
                "extracted_type": extracted,
                "registry_key": registry_key,
                "builder_token": btok,
                "n_token": n_token,
                "td_create": td_create,
                "params_file_present": params_present,
                "perturbed_file_present": perturbed_present,
                "coverage": coverage,
            }

        meta = {
            "gate_version": GATE_VERSION,
            "kb_operators_json": str(kb_operators_json()),
            "operator_types_json": str(operator_types_json()),
            "tox_expanded_dir": str(texp),
            "params_dir": str(pdir),
            "n_operators": len(operators),
        }
        return cls(operators, meta)

    # -- persistence -------------------------------------------------------
    def save(self, path: Path | None = None) -> Path:
        path = Path(path) if path else (stage_dir() / self.FILENAME)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"meta": self.meta, "operators": self.operators}, indent=2),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, path: Path | None = None) -> "CanonicalMap":
        path = Path(path) if path else (stage_dir() / cls.FILENAME)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data["operators"], data.get("meta", {}))

    # -- convenience -------------------------------------------------------
    def get(self, name: str) -> dict | None:
        return self.operators.get(name)

    def token_mismatches(self) -> list[dict]:
        """Ops whose builder_token != captured n_token (the offline-build defect
        census, computable WITHOUT building -- the build then confirms it)."""
        out = []
        for name, r in self.operators.items():
            if r["n_token"] is None:
                continue
            if norm_token(r["builder_token"]) != norm_token(r["n_token"]):
                out.append({"op": name, **{k: r[k] for k in
                            ("family", "registry_key", "builder_token", "n_token", "td_create")}})
        return out


# ---------------------------------------------------------------------------
# Build-on-demand convenience
# ---------------------------------------------------------------------------
def get_ground_truth() -> GroundTruth:
    return GroundTruth(operators_json=kb_operators_json(), operator_types_json=operator_types_json())


def get_param_defaults() -> ParamDefaults:
    return ParamDefaults(params_dir())


if __name__ == "__main__":
    # Build + persist the canonical map and print a one-screen sanity report.
    ensure_paths()
    cmap = CanonicalMap.build()
    out = cmap.save()
    ops = cmap.operators
    n = len(ops)
    by_cov: dict[str, int] = {}
    for r in ops.values():
        by_cov[r["coverage"]] = by_cov.get(r["coverage"], 0) + 1
    have_tdc = sum(1 for r in ops.values() if r["td_create"])
    have_ntok = sum(1 for r in ops.values() if r["n_token"])
    mism = cmap.token_mismatches()

    print("=" * 70)
    print(f"CANONICAL OP MAP  ({n} KB operators)")
    print(f"  wrote: {out}")
    print(f"  td_create present : {have_tdc}/{n}")
    print(f"  n_token present   : {have_ntok}/{n}")
    print(f"  coverage          : " + "  ".join(f"{k}={v}" for k, v in sorted(by_cov.items())))
    print(f"  token mismatches  : {len(mism)}  (builder_token != captured n_token)")
    print("-" * 70)
    # Sanity: the 7 POP INTERNAL_NAME_MAP overrides must AGREE (builder==n_token).
    pop_overrides = ["Point Generator POP", "GLSL Advanced POP", "Attribute Combine POP",
                     "Attribute Convert POP", "Lookup Attribute POP", "Lookup Channel POP",
                     "Lookup Texture POP"]
    print("  POP override agreement (expect builder_token == n_token):")
    for nm in pop_overrides:
        r = ops.get(nm)
        if r:
            ok = norm_token(r["builder_token"]) == norm_token(r["n_token"])
            print(f"    [{'OK ' if ok else 'XX '}] {nm:24s} builder={r['builder_token']:18s} n={r['n_token']}")
        else:
            print(f"    [-- ] {nm:24s} (not in KB)")
    print("  known-divergent spot checks (expect MISMATCH on ableton):")
    for nm in ["Ableton Link CHOP", "Audio Device In CHOP", "Composite TOP", "HSV Adjust TOP"]:
        r = ops.get(nm)
        if r:
            ok = norm_token(r["builder_token"]) == norm_token(r["n_token"])
            print(f"    [{'== ' if ok else 'NE '}] {nm:24s} builder={r['builder_token']:20s} n={r['n_token']}")
    print("  sample of token mismatches (first 15):")
    for m in mism[:15]:
        print(f"    {m['op']:30s} builder={m['builder_token']:22s} n={m['n_token']:22s} td_create={m['td_create']}")
    print("=" * 70)

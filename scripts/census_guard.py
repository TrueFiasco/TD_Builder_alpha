#!/usr/bin/env python3
"""Mechanical census drift guard (W3 Census Lock, board GT7).

Today's ground-truth drift -- KB 663, eval ground truth 685, live TouchDesigner
647 -- was found BY HAND, in an audit. Nothing was red. This module makes the
next drift fail a gate instead.

Five checks, against the committed census snapshot:

  (a) snapshot identity + self-consistency -- schema, build id, families seen,
      by_family agrees with the lists it summarises, inheritance chains well formed
  (b) per-family creatable counts pinned to the owner ruling
  (c) census - KB is bounded by a named allowlist of known holes, AND the inverse
      (KB - census) equals the named fossil list. Both directions: a fossil
      quietly disappearing is drift too.
  (d) every eval-ground-truth td_create exists in the census (post-GT1 this is
      0 violations by construction -- the generator sources the same registry --
      so any violation means someone hand-edited the ground truth)
  (e) count-truth: the three numbers docs may quote agree with the artifacts.
      The docs-scanning half lives in scripts/docs_lint.py, which runs in a lane
      with no KB; the KB-side half runs in tests/unit/test_census_guard.py.

THE THREE NUMBERS, which must never be conflated (owner ruling):
    647 = operators in TouchDesigner   (this census)
    640 = KB coverage                  (663 entries minus 23 fossils)
    663 = KB entries                   -- and ONLY where it literally means that
Live-verified: 663 - 23 + 7 = 647.

Checkers are pure functions returning a list of finding strings, so the negative
tests can doctor a snapshot in memory and assert the exact finding. `--self-test`
runs those same mutations and prints a transcript, which is how the red-green
demonstration is reproduced without ever committing a doctored file.

Stdlib-only. Exit 0 = clean, 1 = at least one finding, 2 = self-error.

Usage:
    python scripts/census_guard.py
    python scripts/census_guard.py --self-test
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CENSUS_PATH = REPO / "eval" / "ground_truth" / "td_census.json"
GT_PATH = REPO / "eval" / "ground_truth" / "operator_types.json"
KB_OPERATORS_PATH = REPO / "KB" / "operators.json"

EXPECTED_SCHEMA = "td_census/1"
EXPECTED_BUILD = "099.2025.32820"
EXPECTED_TOTAL = 647
EXPECTED_KB_ENTRIES = 663
EXPECTED_KB_COVERAGE = 640

# Owner ruling, live-verified 2026-07-17 and re-verified 2026-07-18.
FAMILY_PINS: dict[str, int] = {
    "CHOP": 165, "TOP": 146, "SOP": 112, "DAT": 71,
    "COMP": 40, "MAT": 13, "POP": 100,
}

# Real operators the KB has no entry for at all. Sourced from
# eval/ground_truth/README.md and re-derived live. W7c adds them; until then they
# are a KNOWN, bounded gap rather than an unbounded one.
KNOWN_HOLES: frozenset[str] = frozenset({
    "freedinCHOP", "stypeinCHOP", "tcpipDAT", "alembicoutPOP",
    "textPOP", "tracePOP", "triangulatePOP",
})

# KB entries that are not creatable in the pinned build -- deprecated classes and
# pre-rename fossils. Keyed (family, name) because that is how the KB identifies
# them; they have no OPType, which is the point. W7c retires them.
KNOWN_FOSSILS: frozenset[tuple[str, str]] = frozenset({
    ("CHOP", "Band EQ CHOP"), ("CHOP", "EtherDream CHOP"), ("CHOP", "FreeD CHOP"),
    ("CHOP", "Helios DAC CHOP"), ("CHOP", "Parametric EQ CHOP"),
    ("CHOP", "RealSense CHOP"), ("CHOP", "Scan CHOP"), ("CHOP", "Stype CHOP"),
    ("CHOP", "wrnchAI CHOP"), ("COMP", "Build a List COMP"),
    ("COMP", "Impulse Force COMP"), ("DAT", "Indices DAT"), ("DAT", "UDT In DAT"),
    ("DAT", "UDT Out DAT"), ("DAT", "Web DAT"), ("POP", "Force POP"),
    ("POP", "GLSL Create POP"), ("POP", "Line Thick POP"), ("SOP", "Font SOP"),
    ("TOP", "CUDA TOP"), ("TOP", "Layer TOP"), ("TOP", "SVG TOP"),
    ("TOP", "Simple Render TOP"),
})


def _norm(s: str | None) -> str:
    """Lowercase alphanumerics. Local copy so this stays stdlib-only and importable
    from the docs lane, which installs nothing."""
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


# ---------------------------------------------------------------------------
# (a) snapshot identity + self-consistency
# ---------------------------------------------------------------------------
def check_snapshot(census: dict, expected_build: str = EXPECTED_BUILD) -> list[str]:
    out: list[str] = []
    if census.get("_schema") != EXPECTED_SCHEMA:
        out.append(f"snapshot: _schema is {census.get('_schema')!r}, "
                   f"expected {EXPECTED_SCHEMA!r}")
    if census.get("td_build") != expected_build:
        out.append(f"snapshot: td_build mismatch -- is {census.get('td_build')!r}, "
                   f"expected {expected_build!r}")

    seen = census.get("families_seen") or []
    if sorted(seen) != sorted(FAMILY_PINS):
        out.append(f"snapshot: families_seen is {sorted(seen)}, expected "
                   f"{sorted(FAMILY_PINS)} -- a NEW FAMILY is a real event "
                   f"(POP itself was added once); re-capture and re-pin deliberately")

    ops = census.get("operators") or {}
    for fam, names in sorted(ops.items()):
        claimed = (census.get("by_family") or {}).get(fam)
        if claimed != len(names):
            out.append(f"snapshot: {fam}: list has {len(names)}, "
                       f"by_family says {claimed}")
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            out.append(f"snapshot: {fam}: duplicate entries {dupes[:5]}")
        wrong = [n for n in names if not n.endswith(fam)]
        if wrong:
            out.append(f"snapshot: {fam}: {len(wrong)} name(s) not ending in "
                       f"{fam!r}: {wrong[:5]}")

    total = sum(len(v) for v in ops.values())
    if census.get("total_operators") != total:
        out.append(f"snapshot: total_operators says "
                   f"{census.get('total_operators')}, lists hold {total}")

    # Inheritance chains: every operator resolves to its own family base and
    # terminates at OP. Catches a malformed capture, and pins the data W7c and
    # W4 inherit for the class layer / response dedup.
    inh = census.get("inherits") or {}
    for fam, names in sorted(ops.items()):
        for n in names:
            chain = inh.get(n)
            if chain is None:
                out.append(f"snapshot: {n}: no inheritance chain recorded")
            elif not chain or chain[-1] != "OP":
                out.append(f"snapshot: {n}: chain does not terminate at OP: {chain}")
            elif fam not in chain:
                out.append(f"snapshot: {n}: chain lacks its family base {fam}: {chain}")
    return out


# ---------------------------------------------------------------------------
# (b) per-family pins
# ---------------------------------------------------------------------------
def check_family_pins(census: dict, pins: dict[str, int] = None) -> list[str]:
    pins = pins or FAMILY_PINS
    out: list[str] = []
    by_fam = census.get("by_family") or {}
    for fam, expected in sorted(pins.items()):
        actual = by_fam.get(fam)
        if actual != expected:
            out.append(f"family pin: {fam} pinned at {expected}, snapshot has {actual}")
    total = census.get("total_operators")
    if total != sum(pins.values()):
        out.append(f"family pin: total_operators {total} != sum of pins "
                   f"{sum(pins.values())}")
    return out


# ---------------------------------------------------------------------------
# (c) census <-> KB reconciliation
# ---------------------------------------------------------------------------
def resolve_kb_to_census(kb_operators: list[dict], gt: dict) -> tuple[set[str], list[tuple[str, str]]]:
    """Map KB entries into census OPType space via the ground truth's name index.

    Returns (resolved OPTypes, unresolved (family, name) pairs). Unresolved means
    the KB names something the census does not contain -- i.e. a fossil.
    """
    name_idx: dict[tuple[str, str], str] = {}
    for fam, entries in (gt.get("operators") or {}).items():
        for e in entries:
            if e.get("name") and e.get("td_create"):
                name_idx[(fam, _norm(e["name"]))] = e["td_create"]
    resolved: set[str] = set()
    unresolved: list[tuple[str, str]] = []
    for o in kb_operators:
        key = (o.get("family"), _norm(o.get("name")))
        tdc = name_idx.get(key)
        if tdc:
            resolved.add(tdc)
        else:
            unresolved.append((o.get("family"), o.get("name")))
    return resolved, unresolved


def check_kb_reconciliation(census: dict, kb_operators: list[dict], gt: dict,
                            known_holes: frozenset = KNOWN_HOLES,
                            known_fossils: frozenset = KNOWN_FOSSILS) -> list[str]:
    out: list[str] = []
    census_types = {t for names in (census.get("operators") or {}).values() for t in names}
    resolved, unresolved = resolve_kb_to_census(kb_operators, gt)

    holes = census_types - resolved
    for h in sorted(holes - known_holes):
        out.append(f"reconciliation: {h} is in the census but has no KB entry and "
                   f"is not an allowlisted hole -- the KB gap grew")
    # Anti-rot: an allowlisted hole that is no longer a hole must leave the list,
    # or the allowlist silently accumulates dead entries and loses its teeth.
    for h in sorted(known_holes - holes):
        out.append(f"reconciliation: {h} is allowlisted as a KB hole but is no "
                   f"longer one -- remove it from KNOWN_HOLES")

    fossils = set(unresolved)
    for f in sorted(fossils - known_fossils):
        out.append(f"reconciliation: KB entry {f} does not exist in the census and "
                   f"is not an allowlisted fossil -- either a new fossil or a bad name")
    for f in sorted(known_fossils - fossils):
        out.append(f"reconciliation: {f} is allowlisted as a fossil but now resolves "
                   f"to the census -- remove it from KNOWN_FOSSILS")
    return out


# ---------------------------------------------------------------------------
# (d) eval ground truth is a subset of the census
# ---------------------------------------------------------------------------
def check_gt_subset(census: dict, gt: dict) -> list[str]:
    """Every ground-truth td_create must exist in the census.

    Post-GT1 this is 0 by construction (the generator sources the census), so a
    violation means the ground truth was hand-edited or regenerated from
    something else -- exactly the failure this wave removed.
    """
    out: list[str] = []
    census_types = {t for names in (census.get("operators") or {}).values() for t in names}
    census_by_fam = {fam: set(names) for fam, names in (census.get("operators") or {}).items()}
    for fam, entries in sorted((gt.get("operators") or {}).items()):
        for e in entries:
            tdc = e.get("td_create")
            if tdc not in census_types:
                out.append(f"gt-subset: {fam} {e.get('name')!r} -> {tdc!r} is not in "
                           f"the census (phantom operator?)")
            elif tdc not in census_by_fam.get(fam, set()):
                out.append(f"gt-subset: {fam} {e.get('name')!r} -> {tdc!r} exists but "
                           f"in a different family")
    return out


# ---------------------------------------------------------------------------
# (e) count truth (artifact side; the docs side lives in docs_lint.py)
# ---------------------------------------------------------------------------
def check_counts(census: dict, kb_operators: list[dict], gt: dict) -> list[str]:
    out: list[str] = []
    if census.get("total_operators") != EXPECTED_TOTAL:
        out.append(f"counts: census total {census.get('total_operators')} != "
                   f"{EXPECTED_TOTAL} (the '647 operators in TD' number)")
    if len(kb_operators) != EXPECTED_KB_ENTRIES:
        out.append(f"counts: KB has {len(kb_operators)} entries != "
                   f"{EXPECTED_KB_ENTRIES} (the '663 KB entries' number)")
    resolved, _ = resolve_kb_to_census(kb_operators, gt)
    census_types = {t for names in (census.get("operators") or {}).values() for t in names}
    coverage = len(census_types & resolved)
    if coverage != EXPECTED_KB_COVERAGE:
        out.append(f"counts: KB covers {coverage} of the census != "
                   f"{EXPECTED_KB_COVERAGE} (the '640 KB coverage' number)")
    gt_total = sum(len(v) for v in (gt.get("operators") or {}).values())
    if gt_total != EXPECTED_TOTAL:
        out.append(f"counts: ground truth holds {gt_total} entries != "
                   f"{EXPECTED_TOTAL}; it must be the census set exactly")
    return out


# ---------------------------------------------------------------------------
# Self-test: the red-green demonstration
# ---------------------------------------------------------------------------
def _mutations(census: dict, gt: dict) -> list[tuple[str, callable, str]]:
    """(label, doctor_fn, substring the resulting finding must contain)."""
    def wrong_build(c, g):
        c["td_build"] = "099.2025.32460"

    def desync_by_family(c, g):
        c["operators"]["CHOP"].pop()          # list shrinks, by_family untouched

    def break_family_pin(c, g):
        c["operators"]["CHOP"].pop()
        c["by_family"]["CHOP"] -= 1
        c["total_operators"] -= 1

    def unlisted_hole(c, g):
        c["operators"]["CHOP"].append("bogusCHOP")
        c["by_family"]["CHOP"] += 1
        c["total_operators"] += 1
        c["inherits"]["bogusCHOP"] = ["CHOP", "OP"]

    def phantom_in_gt(c, g):
        g["operators"]["POP"].append({"name": "Source_POP", "td_create": "sourcePOP"})

    def stale_allowlist(c, g):
        c["operators"]["POP"].remove("textPOP")   # textPOP stops being a hole
        c["by_family"]["POP"] -= 1
        c["total_operators"] -= 1

    return [
        ("td_build changed to the older 32460", wrong_build, "td_build mismatch"),
        ("a CHOP dropped, by_family left stale", desync_by_family, "by_family says"),
        ("a CHOP dropped consistently (pin broken)", break_family_pin, "family pin: CHOP"),
        ("bogusCHOP injected into the census", unlisted_hole, "not an allowlisted hole"),
        ("phantom Source_POP injected into the GT", phantom_in_gt, "not in the census"),
        ("textPOP removed (allowlist goes stale)", stale_allowlist, "no longer one"),
    ]


def run_all(census: dict, kb_operators: list[dict], gt: dict) -> list[str]:
    return (check_snapshot(census)
            + check_family_pins(census)
            + check_kb_reconciliation(census, kb_operators, gt)
            + check_gt_subset(census, gt)
            + check_counts(census, kb_operators, gt))


def self_test(census: dict, kb_operators: list[dict], gt: dict) -> int:
    print("census_guard --self-test: each row doctors the snapshot IN MEMORY and")
    print("asserts the guard produces the expected finding. No file is modified.\n")
    clean = run_all(census, kb_operators, gt)
    print(f"  [green] pristine snapshot -> {len(clean)} finding(s)"
          + (f": {clean}" if clean else ""))
    if clean:
        print("\n  SELF-TEST INVALID: the pristine snapshot is already failing.",
              file=sys.stderr)
        return 2

    failures = 0
    for label, doctor, expect in _mutations(census, gt):
        c2, g2 = copy.deepcopy(census), copy.deepcopy(gt)
        doctor(c2, g2)
        found = run_all(c2, kb_operators, g2)
        hit = [f for f in found if expect in f]
        status = "red " if hit else "MISS"
        print(f"  [{status}] {label}")
        if hit:
            print(f"          -> {hit[0]}")
        else:
            failures += 1
            print(f"          -> expected a finding containing {expect!r}; "
                  f"got {found[:3] or 'NOTHING'}", file=sys.stderr)

    print()
    if failures:
        print(f"  {failures} mutation(s) did NOT trip the guard -- it is not "
              f"actually guarding.", file=sys.stderr)
        return 1
    print("  all 6 mutations tripped the guard; pristine snapshot is clean.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--census", type=Path, default=CENSUS_PATH)
    ap.add_argument("--gt", type=Path, default=GT_PATH)
    ap.add_argument("--kb", type=Path, default=KB_OPERATORS_PATH)
    ap.add_argument("--self-test", action="store_true",
                    help="run the doctored-snapshot demonstration and exit")
    args = ap.parse_args()

    try:
        census = json.loads(args.census.read_text(encoding="utf-8"))
        gt = json.loads(args.gt.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"census_guard: cannot read tracked inputs: {exc}", file=sys.stderr)
        return 2

    if not args.kb.exists():
        print(f"census_guard: KB/operators.json absent ({args.kb}).\n"
              f"  The KB-dependent checks (reconciliation, counts) need it; run "
              f"`python scripts/fetch_vector_db.py` or use the KB-bearing lane.",
              file=sys.stderr)
        return 2
    try:
        kb_operators = json.loads(args.kb.read_text(encoding="utf-8"))["operators"]
    except Exception as exc:  # noqa: BLE001
        print(f"census_guard: cannot parse KB operators: {exc}", file=sys.stderr)
        return 2

    if args.self_test:
        return self_test(census, kb_operators, gt)

    findings = run_all(census, kb_operators, gt)
    print(f"  census  : {census.get('total_operators')} operators @ "
          f"{census.get('td_build')}")
    print(f"  KB      : {len(kb_operators)} entries")
    print(f"  gt      : {sum(len(v) for v in (gt.get('operators') or {}).values())} entries")
    if findings:
        print(f"\ncensus_guard: {len(findings)} finding(s) --", file=sys.stderr)
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\n  clean: census, KB and eval ground truth agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

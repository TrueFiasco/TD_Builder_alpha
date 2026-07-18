#!/usr/bin/env python3
"""Docs-consistency lint (CI KB-free lane; created by harness remediation W1).

Guards the documentation surface against the drift classes the v0.2.0
packaging/docs-truth pass (c9f8c0d) fixed by hand:

  * tool-count truth  -- the "18 offline / 22 live tools" claims across the
    docs must match the counts parsed from the actual tool registries;
  * phantom patterns  -- references to things that do not exist (console
    shims, removed config knobs, cloud providers, dotenv, deleted paths);
  * client-config venv rule -- setup snippets must not use bare "python";
  * non-negotiables drift -- restatements of rules outside their canonical
    file. Seed entries ship severity "off" (they are legitimately duplicated
    today); work item 3b single-sources them and flips severities in
    scripts/docs_lint_rules.json without touching this script.

Stdlib-only (runs before any pip install), cross-platform, line-scoped
patterns only. Exit 0 = clean (warns allowed), exit 1 = at least one
error-severity finding, exit 2 = lint self-error (bad config/registry parse).

Usage:
    python scripts/docs_lint.py [--rules scripts/docs_lint_rules.json] [--list]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# findings: list of (severity, relpath, lineno, rule_id, message)
Finding = tuple


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _rel(path: Path) -> str:
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_doc_files(rules: dict) -> list[Path]:
    excl = {e.lower() for e in rules["scan"]["exclude_dirs"]}
    files: list[Path] = []
    for p in sorted(REPO.rglob("*.md")):
        parts = {q.lower() for q in p.relative_to(REPO).parts[:-1]}
        if parts & excl:
            continue
        files.append(p)
    for extra in rules["scan"]["extra_files"]:
        p = REPO / extra
        if p.is_file():
            files.append(p)
    return files


# ---------------------------------------------------------------------------
# Tool-count truth
# ---------------------------------------------------------------------------
# `annotations=<CONST>,` may precede `name=` (W4b risk annotations) — tolerate it
# so the count still keys on the name literal.
_TOOL_NAME = re.compile(r'Tool\(\s*(?:annotations=\w+,\s*)?name="([A-Za-z0-9_]+)"')


def _parse_offline_tools(text: str) -> list[str]:
    """Tool(name=...) literals between @app.list_tools() and the next @app. decorator."""
    start = text.find("@app.list_tools()")
    if start == -1:
        return []
    end = text.find("\n@app.", start + 1)
    segment = text[start:] if end == -1 else text[start:end]
    return _TOOL_NAME.findall(segment)


def check_tool_counts(rules: dict, findings: list[Finding]) -> None:
    tc = rules["tool_counts"]
    exp_off, exp_live = tc["expected_offline"], tc["expected_live"]

    off_path = REPO / tc["offline_registry"]
    live_path = REPO / tc["live_registry"]
    if not off_path.is_file() or not live_path.is_file():
        findings.append(("error", _rel(off_path if not off_path.is_file() else live_path),
                         0, "tool-count", "tool registry file missing (rules stale?)"))
        return

    offline = _parse_offline_tools(_read(off_path))
    live = _TOOL_NAME.findall(_read(live_path))
    if len(offline) != exp_off:
        findings.append(("error", _rel(off_path), 0, "tool-count",
                         f"offline registry has {len(offline)} tools, expected {exp_off} "
                         f"(deliberate surface change? bump docs_lint_rules.json + every claim doc): "
                         f"{sorted(offline)}"))
    if len(live) != exp_live:
        findings.append(("error", _rel(live_path), 0, "tool-count",
                         f"live registry has {len(live)} tools, expected {exp_live}: {sorted(live)}"))

    allowed = {exp_off, exp_live, exp_off + exp_live}
    context = re.compile(tc["claim_context_regex"], re.IGNORECASE)
    # Tolerate markdown emphasis around the number ("**17** key-free tools").
    claim = re.compile(r"(\d+)[*_`]{0,2}\s+(?:[A-Za-z-]+\s+){0,2}tools?\b")
    saw_off = saw_live = False
    for rel in tc["claim_files"]:
        p = REPO / rel
        if not p.is_file():
            findings.append(("error", rel, 0, "tool-count",
                             "claim file missing — update docs_lint_rules.json if it moved"))
            continue
        for lineno, line in enumerate(_read(p).splitlines(), 1):
            if "tool" not in line.lower() or not context.search(line):
                continue
            for m in claim.finditer(line):
                n = int(m.group(1))
                if n == exp_off:
                    saw_off = True
                elif n == exp_live:
                    saw_live = True
                if n not in allowed:
                    findings.append(("error", rel, lineno, "tool-count",
                                     f"claims {n} tools; allowed counts are {sorted(allowed)} "
                                     f"(offline/live/total): {line.strip()!r}"))
    if not saw_off:
        findings.append(("error", tc["claim_files"][0], 0, "tool-count",
                         f"no doc claims the offline count ({exp_off}) any more — "
                         "if intentional, update claim_files/expected_offline"))
    if not saw_live:
        findings.append(("error", tc["claim_files"][0], 0, "tool-count",
                         f"no doc claims the live count ({exp_live}) any more — "
                         "if intentional, update claim_files/expected_live"))


# ---------------------------------------------------------------------------
# Operator-count truth (W3 Census Lock, board GT7 check (e))
# ---------------------------------------------------------------------------
def check_operator_counts(rules: dict, findings: list) -> None:
    """Docs' operator-count claims must match the artifacts.

    THREE numbers are legitimate and mean different things (owner ruling):
        647 = operators in TouchDesigner  (eval/ground_truth/td_census.json)
        640 = KB coverage                 (663 entries minus 23 fossils)
        663 = KB entries                  (KB/manifest.json)
    A naive "number near the word operator" rule cannot tell them apart, and
    would also fire on `636/636 operator tokens` (a build-gate metric), `Sweet 16
    operators`, and `7 real operators` -- an allowlist of every plausible number
    has no teeth.

    So this pins the SHAPE instead. PR #47 left every corrected surface with one
    rigid compound phrase carrying all three numbers AND the build in fixed
    positions ("640 of TouchDesigner 2025.32820's 647 ... operators"). Matching
    that phrase yields exactly the real claims and nothing else.

    Ground truth is read from two TRACKED files, so this runs in the KB-free
    docs-lint lane: the census snapshot, and KB/manifest.json for the entry count
    (KB/operators.json is gitignored and absent on that runner). The KB-side
    half -- len(operators) == 663 and coverage == 640 -- is asserted in
    tests/unit/test_census_guard.py, which runs in the KB-bearing lane. Same
    two-sided shape as check_tool_counts above.
    """
    oc = rules.get("operator_counts")
    if not oc:
        return

    census_path = REPO / oc["census_file"]
    census = json.loads(_read(census_path))
    exp_census = oc["expected_census"]
    exp_coverage = oc["expected_kb_coverage"]
    exp_entries = oc["expected_kb_entries"]
    exp_build = oc["expected_td_build"]

    # --- artifact side -----------------------------------------------------
    if census.get("total_operators") != exp_census:
        findings.append(("error", _rel(census_path), 0, "operator-count",
                         f"census holds {census.get('total_operators')} operators, "
                         f"expected {exp_census} (re-capture with "
                         f"scripts/capture_td_census.py, then re-pin deliberately)"))
    if census.get("td_build") != exp_build:
        findings.append(("error", _rel(census_path), 0, "operator-count",
                         f"census td_build is {census.get('td_build')!r}, "
                         f"expected {exp_build!r}"))

    man_path = REPO / oc["kb_manifest"]
    if man_path.is_file():
        man = json.loads(_read(man_path))
        node = man
        for key in oc["kb_manifest_key"]:
            node = (node or {}).get(key)
        if node != exp_entries:
            findings.append(("error", _rel(man_path), 0, "operator-count",
                             f"manifest reports {node} KB operator entries, "
                             f"expected {exp_entries}"))

    # --- docs side ---------------------------------------------------------
    claim = re.compile(oc["compound_claim_regex"])
    seen = 0
    for rel in oc["claim_files"]:
        p = REPO / rel
        if not p.is_file():
            findings.append(("error", rel, 0, "operator-count",
                             "claim file missing — update docs_lint_rules.json if it moved"))
            continue
        for lineno, line in enumerate(_read(p).splitlines(), 1):
            for m in claim.finditer(line):
                seen += 1
                coverage, build, census_n = m.group(1), m.group(2), m.group(3)
                if int(census_n) != exp_census:
                    findings.append(("error", rel, lineno, "operator-count",
                                     f"claims {census_n} operators in TouchDesigner; "
                                     f"the census says {exp_census}: {line.strip()!r}"))
                if int(coverage) != exp_coverage:
                    findings.append(("error", rel, lineno, "operator-count",
                                     f"claims {coverage} covered by the KB; "
                                     f"expected {exp_coverage}: {line.strip()!r}"))
                if build not in exp_build:
                    findings.append(("error", rel, lineno, "operator-count",
                                     f"claims TouchDesigner build {build}; the census "
                                     f"is {exp_build}: {line.strip()!r}"))

    # Reverse check -- the load-bearing half. Every stale "673" is already fixed,
    # so this rule's job is purely to stop a regression; if the claims themselves
    # were deleted the forward check would pass vacuously forever.
    if seen < oc["min_compound_claims"]:
        findings.append(("error", oc["claim_files"][0], 0, "operator-count",
                         f"only {seen} operator-count claim(s) found across "
                         f"{len(oc['claim_files'])} claim files, expected at least "
                         f"{oc['min_compound_claims']} — a surface stopped stating the "
                         f"census, or the phrasing drifted out of the pinned shape"))


# ---------------------------------------------------------------------------
# Phantom patterns + client-config rule (line-scoped scans)
# ---------------------------------------------------------------------------
def _scan_lines(path: Path, regex: re.Pattern, rule_id: str, message: str,
                severity: str, findings: list[Finding]) -> None:
    for lineno, line in enumerate(_read(path).splitlines(), 1):
        if regex.search(line):
            findings.append((severity, _rel(path), lineno, rule_id,
                             f"{message}: {line.strip()[:120]!r}"))


def check_phantoms(rules: dict, files: list[Path], findings: list[Finding]) -> None:
    for rule in rules["phantom_patterns"]:
        if rule["severity"] == "off":
            continue
        rx = re.compile(rule["regex"])
        allow = {a.lower() for a in rule.get("allow_files", [])}
        for p in files:
            if _rel(p).lower() in allow:
                continue
            _scan_lines(p, rx, rule["id"], rule["message"], rule["severity"], findings)


def check_client_configs(rules: dict, findings: list[Finding]) -> None:
    cc = rules["client_config"]
    if cc["severity"] == "off":
        return
    rx = re.compile(cc["regex"])
    for rel in cc["files"]:
        p = REPO / rel
        if p.is_file():
            _scan_lines(p, rx, "client-config-venv", cc["message"], cc["severity"], findings)


# ---------------------------------------------------------------------------
# Non-negotiables drift (3b extension point)
# ---------------------------------------------------------------------------
def check_non_negotiables(rules: dict, files: list[Path], findings: list[Finding]) -> None:
    for rule in rules["non_negotiables"]:
        if rule["severity"] == "off":
            continue
        rx = re.compile(rule["pattern"])
        canonical = rule["canonical_file"].lower()
        for p in files:
            if _rel(p).lower() == canonical:
                continue
            _scan_lines(p, rx, rule["id"],
                        f"restates a non-negotiable whose canonical home is {rule['canonical_file']}",
                        rule["severity"], findings)


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rules", default=str(REPO / "scripts" / "docs_lint_rules.json"))
    ap.add_argument("--list", action="store_true", help="print active rules and scanned files, no lint")
    args = ap.parse_args(argv)

    # Findings quote doc lines that may hold non-cp1252 characters; never let a
    # Windows console encoding kill the lint itself.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    try:
        rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"docs_lint: cannot load rules ({exc})", file=sys.stderr)
        return 2

    files = _iter_doc_files(rules)

    if args.list:
        print(f"scanned files ({len(files)}):")
        for p in files:
            print(f"  {_rel(p)}")
        for section in ("phantom_patterns", "non_negotiables"):
            for rule in rules[section]:
                print(f"rule {rule['id']:32s} severity={rule['severity']}")
        return 0

    findings: list[Finding] = []
    try:
        check_tool_counts(rules, findings)
    except Exception as exc:  # registry parse must never pass silently
        print(f"docs_lint: tool-count check crashed: {exc}", file=sys.stderr)
        return 2
    try:
        check_operator_counts(rules, findings)
    except Exception as exc:  # census/manifest parse must never pass silently
        print(f"docs_lint: operator-count check crashed: {exc}", file=sys.stderr)
        return 2
    check_phantoms(rules, files, findings)
    check_client_configs(rules, findings)
    check_non_negotiables(rules, files, findings)

    errors = [f for f in findings if f[0] == "error"]
    warns = [f for f in findings if f[0] == "warn"]
    for sev, rel, lineno, rule_id, msg in sorted(findings, key=lambda f: (f[1], f[2])):
        loc = f"{rel}:{lineno}" if lineno else rel
        print(f"{sev.upper():5s} {loc} [{rule_id}] {msg}")
    print(f"docs_lint: {len(files)} files scanned, "
          f"{len(errors)} error(s), {len(warns)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Docs-consistency lint (CI KB-free lane; created by harness remediation W1).

Guards the documentation surface against the drift classes the v0.2.0
packaging/docs-truth pass (c9f8c0d) fixed by hand:

  * tool-count truth  -- the "17 offline / 21 live tools" claims across the
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

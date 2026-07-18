#!/usr/bin/env python3
"""Capture the live TouchDesigner operator census (W3 Census Lock, board GT7).

Writes a versioned snapshot of TD's own `families[]` class registry so CI has a
stand-in for a live TouchDesigner. The snapshot is the *creatable* authority:
647 operators at build 099.2025.32820. It is NOT the same set as the `td`
module's class namespace (693 opSubclasses -- that tier includes retired
operators whose class still exists), and it is NOT the wiki scrape.

THE GOTCHA THIS SCRIPT EXISTS TO SURVIVE: `families[FAM]` holds CLASSES, not
strings. `sorted(families[fam])` raises (classes are not orderable) and
`str(c)` yields "<class 'td.abletonlinkCHOP'>". Every name must come from
`c.__name__`. Two earlier probes were silently invalidated by this -- membership
tests against the class objects returned False for every operator and the bug
looked like missing data. The remote snippet below is defensive about it and
this script HARD-FAILS on any name containing "<", "'" or a space, so a
repr-leak becomes an immediate error instead of a plausible-looking snapshot.

Also records each operator's inheritance chain (`c.__mro__` minus self and
`object`). Nothing in W3 consumes the chain; it is captured because the walk is
already happening and the class layer (W7c) plus the tool-response dedup (W4)
both need it -- attribution of an inherited member to its defining class is
impossible without it.

Stdlib-only (no pip install), talks to TD's WebServer DAT over HTTP using the
same shared-secret auth as MCP/live_client/td_live_client.py.

Exit 0 = snapshot written (or --dry-run clean), 1 = a guard tripped
(count/build mismatch, malformed name), 2 = self-error (TD unreachable, bad
response).

Usage:
    python scripts/capture_td_census.py --dry-run
    python scripts/capture_td_census.py
    python scripts/capture_td_census.py --expect-total 648 --allow-count-change \\
        --reason "TD 2025.34000 adds a family"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "eval" / "ground_truth" / "td_census.json"

# Must match MCP/live_client/td_live_client.py (TD_API_URL / TD_API_TOKEN /
# TD_API_TOKEN_FILE) and the TD side's MCP/td-webserver/modules/utils/auth.py.
TD_API_URL = os.environ.get("TD_API_URL", "http://127.0.0.1:9981")
EXEC_ENDPOINT = "/api/td/server/exec"

SCHEMA = "td_census/1"
EXPECTED_TOTAL = 647
EXPECTED_BUILD = "099.2025.32820"

# Runs inside TouchDesigner. `families` is an injected global; `me`/`parent` are
# not available (scripts run outside any node). Prints one JSON object.
REMOTE_SNIPPET = r'''
import json

fams = families
seen = sorted(fams.keys())
operators = {}
inherits = {}
malformed = []

for fam in seen:
    names = []
    for c in fams[fam]:
        # CLASSES, not strings -- see the module docstring.
        name = getattr(c, "__name__", None) or str(c)
        names.append(name)
        if ("<" in name) or ("'" in name) or (" " in name):
            malformed.append([fam, name])
            continue
        mro = getattr(c, "__mro__", ()) or ()
        chain = []
        for base in mro[1:]:
            bname = getattr(base, "__name__", None) or str(base)
            if bname == "object":
                continue
            chain.append(bname)
        inherits[name] = chain
    operators[fam] = sorted(names)

print(json.dumps({
    # app.version is only the series ("099"); app.build carries "2025.32820".
    # The build id everyone quotes is the two joined.
    "td_build": "{}.{}".format(app.version, app.build),
    "td_version_series": app.version,
    "td_build_number": app.build,
    "td_product": app.product,
    "families_seen": seen,
    "by_family": {k: len(v) for k, v in operators.items()},
    "total_operators": sum(len(v) for v in operators.values()),
    "operators": operators,
    "inherits": inherits,
    "malformed": malformed,
}))
'''


def _resolve_token() -> str | None:
    """TD_API_TOKEN env -> ~/.td_builder/api_token. Never raises."""
    env = os.environ.get("TD_API_TOKEN")
    if env and env.strip():
        return env.strip()
    override = os.environ.get("TD_API_TOKEN_FILE")
    path = Path(override.strip()) if override and override.strip() else Path.home() / ".td_builder" / "api_token"
    try:
        if path.exists():
            tok = path.read_text(encoding="utf-8").strip()
            if tok:
                return tok
    except OSError:
        pass
    return None


def _exec_in_td(script: str, timeout: float = 120.0) -> dict:
    """POST the snippet to TD's WebServer DAT and return the parsed stdout JSON."""
    payload = json.dumps({"script": script}).encode("utf-8")
    req = urllib.request.Request(
        TD_API_URL.rstrip("/") + EXEC_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    token = _resolve_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    if not body.get("success"):
        raise RuntimeError(f"TD exec failed: {body.get('error')}")
    data = body.get("data") or {}
    stderr = (data.get("stderr") or "").strip()
    if stderr:
        raise RuntimeError(f"TD exec stderr: {stderr[:500]}")
    stdout = (data.get("stdout") or "").strip()
    if not stdout:
        raise RuntimeError("TD exec produced no stdout")
    return json.loads(stdout)


def _guard(raw: dict, expect_total: int, expect_build: str | None,
           allow_count_change: bool, reason: str | None) -> list[str]:
    """Return a list of guard failures; empty means the capture is trustworthy."""
    problems: list[str] = []

    if raw.get("malformed"):
        problems.append(
            f"malformed class names (repr leak -- see the __name__ gotcha): "
            f"{raw['malformed'][:5]}"
        )

    total = raw.get("total_operators")
    if total != expect_total:
        msg = f"total_operators is {total}, expected {expect_total}"
        if allow_count_change:
            if not reason:
                problems.append(f"{msg}; --allow-count-change requires --reason")
            else:
                print(f"  ! count change accepted: {msg} -- {reason}", file=sys.stderr)
        else:
            problems.append(
                f"{msg}. The owner ruling pins 647; a mismatch usually means the "
                f"CAPTURE is wrong, not the ruling. If TD genuinely changed, "
                f"re-run with --expect-total N --allow-count-change --reason '...'"
            )

    build = raw.get("td_build")
    if expect_build and build != expect_build:
        problems.append(
            f"td_build is {build!r}, expected {expect_build!r}. Pass "
            f"--expect-build {build} once the new build is intended."
        )

    # Every operator name must end in its family key -- a cheap structural check
    # that catches a mis-keyed or truncated capture.
    for fam, names in (raw.get("operators") or {}).items():
        wrong = [n for n in names if not n.endswith(fam)]
        if wrong:
            problems.append(f"{fam}: {len(wrong)} name(s) do not end in {fam!r}: {wrong[:5]}")

    # by_family must agree with the lists it summarises.
    for fam, names in (raw.get("operators") or {}).items():
        claimed = (raw.get("by_family") or {}).get(fam)
        if claimed != len(names):
            problems.append(f"{fam}: by_family says {claimed}, list holds {len(names)}")

    return problems


def build_snapshot(raw: dict) -> dict:
    """Shape the raw capture into the committed snapshot (build id INSIDE the JSON)."""
    return {
        "_schema": SCHEMA,
        "td_build": raw["td_build"],
        "td_product": raw.get("td_product"),
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "capture_method": "families[] class registry (c.__name__); creatable tier",
        "capture_script": "scripts/capture_td_census.py",
        "notes": (
            "Creatable operators only. The td module exposes MORE classes (retired "
            "operators keep a class), so never enumerate td for a census. Names are "
            "OPTypes -- NOT the builder '.n' create token (that is 'CHOP:ableton', "
            "recorded as build_token in KB/operators.json)."
        ),
        "families_seen": raw["families_seen"],
        "total_operators": raw["total_operators"],
        "by_family": raw["by_family"],
        "operators": raw["operators"],
        "inherits": raw["inherits"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--expect-total", type=int, default=EXPECTED_TOTAL)
    ap.add_argument("--expect-build", default=EXPECTED_BUILD)
    ap.add_argument("--dry-run", action="store_true",
                    help="capture and check, write nothing")
    ap.add_argument("--allow-count-change", action="store_true",
                    help="permit a total different from --expect-total (needs --reason)")
    ap.add_argument("--reason", help="why the count legitimately changed")
    args = ap.parse_args()

    try:
        raw = _exec_in_td(REMOTE_SNIPPET)
    except urllib.error.URLError as exc:
        print(f"capture_td_census: TD unreachable at {TD_API_URL} ({exc}).\n"
              f"  TouchDesigner must be RUNNING and NOT minimized -- a minimized TD "
              f"accepts the socket but never answers.", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 -- any transport/parse failure is a self-error
        print(f"capture_td_census: capture failed: {exc}", file=sys.stderr)
        return 2

    print(f"  td_build         : {raw.get('td_build')}")
    print(f"  families_seen    : {raw.get('families_seen')}")
    print(f"  total_operators  : {raw.get('total_operators')}")
    for fam in raw.get("families_seen") or []:
        print(f"    {fam:<5}: {raw['by_family'][fam]}")

    problems = _guard(raw, args.expect_total, args.expect_build,
                      args.allow_count_change, args.reason)
    if problems:
        print("\ncapture_td_census: REFUSING to write --", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    snapshot = build_snapshot(raw)
    if args.dry_run:
        print(f"\n  dry-run: clean; would write {args.out.relative_to(REPO).as_posix()} "
              f"({len(json.dumps(snapshot, indent=2))} bytes)")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"\n  wrote {args.out.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

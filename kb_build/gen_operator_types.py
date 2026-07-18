#!/usr/bin/env python3
"""Generate eval/ground_truth/operator_types.json from the live-TD census (board GT1).

WHY THIS EXISTS. The file this generates used to come from a wiki scrape
(`extract_all_operators.py`, untracked, in a different project root) that
string-munged wiki page titles into create tokens. That scrape was wrong in
BOTH directions: it invented operators that have never existed (13 of them --
Source/Attractor/Drag/Collision/Kill/Add/Velocity POP, Analyze DAT, Fuse SOP,
Mirror SOP, Normals SOP, Scatter SOP, Gradient TOP) and it omitted 7 real ones
(freedinCHOP, stypeinCHOP, tcpipDAT, alembicoutPOP, textPOP, tracePOP,
triangulatePOP). Grounding a model against it produced confident wrong answers.

THE FIX IS STRUCTURAL, not a patch: the operator SET now comes from TD's own
`families[]` registry (the creatable authority, 647), so the ground truth is a
subset of reality BY CONSTRUCTION. Phantoms cannot come back -- there is no
longer a step that could invent one.

TWO SOURCES, each used only for what it is authoritative about:

  * `eval/ground_truth/td_census.json` -- WHICH operators exist, and their
    OPType. Captured from live TD by scripts/capture_td_census.py.
  * TouchDesigner's shipped OFFLINE HELP tree -- how each operator's name is
    SPELLED. The registry has no display names, and TD's own spelling is not
    derivable from the OPType: `rerangePOP` -> `ReRange_POP`, `oakselectPOP` ->
    `OAK_Select_POP`, `choptoPOP` -> `CHOP_to_POP`. It is also inconsistently
    cased (`NVIDIA_Flex_TOP` but `Nvidia_Flow_Emitter_COMP`), which is why the
    join normalises to alphanumerics rather than matching underscores.

The intersection is what makes both failure modes cancel: the registry excludes
phantoms and fossils (no page can resurrect a non-creatable operator), while the
help tree -- a documentation SUPERSET that still ships pages for retired ops --
guarantees every real operator has a name. Neither source alone is sufficient.

Only operator PAGES are used. Do NOT extend this to help *class* pages: that
mirror is under half complete (1,442 `*_Class` names referenced, 656 shipped)
and drawn from a different snapshot than the installed build.

FAIL-LOUD: if any census OPType has no help page the generator ABORTS. It never
falls back to synthesising a name -- synthesis is the original defect.

Deterministic: same (snapshot, help tree) always yields byte-identical output,
which tests/unit/test_operator_census.py asserts.

Usage:
    python kb_build/gen_operator_types.py              # write the tracked file
    python kb_build/gen_operator_types.py --check      # verify, write nothing
    python kb_build/gen_operator_types.py --out /tmp/x.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CENSUS = REPO / "eval" / "ground_truth" / "td_census.json"
DEFAULT_OUT = REPO / "eval" / "ground_truth" / "operator_types.json"

FAMILY_ORDER = ["CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP"]

# Last-resort fallback for a census captured before the snapshot recorded its own
# install root. NOT a default -- see resolve_help_tree(). The unversioned
# C:\...\Derivative\TouchDesigner\ directory is deliberately absent from this
# list: on a machine with several installs it is a DIFFERENT (older) build than
# the running one, which is exactly the mismatch this module must not make silently.
_LEGACY_HELP_GLOB = r"C:\Program Files\Derivative\TouchDesigner.*"
_HELP_SUBPATH = Path("Samples") / "Learn" / "OfflineHelp" / "https.docs.derivative.ca"


def resolve_help_tree(census: dict, cli: Path | None) -> tuple[Path, str]:
    """Locate the shipped docs tree matching this census. Returns (path, source).

    Resolution order, most trustworthy first:
      1. --help-tree            -- an explicit operator decision
      2. the census's own `offline_help_root` -- recorded from `app.samplesFolder`
         at capture time, so it is BY DEFINITION the tree that shipped with the
         TouchDesigner the census came from
      3. a build-matched directory under Program Files, for snapshots captured
         before the schema carried the path

    Deriving from the census is the point: a TD upgrade lands before W7c's
    rebuild, and the correct response must be `capture -> generate`, not editing
    a hardcoded version number in this file. There is no hardcoded build here.
    """
    if cli is not None:
        return cli, "cli (--help-tree)"

    recorded = census.get("offline_help_root")
    if recorded:
        return Path(recorded), "census (app.samplesFolder at capture time)"

    build = census.get("td_build", "")
    tail = build.split(".", 1)[-1]          # "099.2025.32820" -> "2025.32820"
    for root in sorted(Path(_LEGACY_HELP_GLOB).parent.glob("TouchDesigner.*")):
        if tail and tail in root.name:
            return root / _HELP_SUBPATH, f"discovered by build {tail}"
    raise SystemExit(
        f"gen_operator_types: cannot locate the offline-help tree.\n"
        f"  This census predates the schema that records it, and no install "
        f"matching build {build!r} was found.\n"
        f"  Re-capture (python scripts/capture_td_census.py) or pass --help-tree.")


def census_sha256(census_bytes: bytes) -> str:
    """sha256 of the census in its CANONICAL (LF) form -- i.e. the git blob.

    NOT the raw working-tree bytes. This repo runs `core.autocrlf=true` with no
    .gitattributes, so on Windows every tracked JSON is CRLF in the working tree
    and LF in the object store. Hashing raw bytes therefore records a
    Windows-only value that matches nothing on a Linux checkout -- the ubuntu
    hermetic lane reads LF bytes and the provenance test fails.

    Normalising here makes the recorded hash platform-independent and equal to:
        git show HEAD:eval/ground_truth/td_census.json | sha256sum
    which is also what `sha256sum` gives directly on any LF checkout. Writers use
    newline="\\n" as well, so a freshly generated tree needs no re-checkout to
    agree -- but the normalisation is what makes it durable, since autocrlf will
    re-introduce CRLF on the next Windows checkout regardless.
    """
    return hashlib.sha256(census_bytes.replace(b"\r\n", b"\n")).hexdigest()


def _rel(path: Path) -> str:
    """Repo-relative when possible; --out may legitimately point outside the tree."""
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def _norm(s: str) -> str:
    """Lowercase alphanumerics only -- the join key.

    Must tolerate TD's own inconsistent spelling: `NVIDIA_Flex_TOP` vs
    `Nvidia_Flow_Emitter_COMP`, `Art-Net_DAT`, `TCP/IP_DAT`.
    """
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def index_help_pages(help_tree: Path) -> dict[str, list[str]]:
    """norm(page name) -> [page name]. Page name is the path under the tree,
    without .htm, with separators as '/'.

    rglob (not glob) because a page whose wiki title contains a slash nests into
    a subdirectory on disk -- `TCP/IP_DAT.htm` is a real operator page.
    """
    idx: dict[str, list[str]] = defaultdict(list)
    for p in help_tree.rglob("*.htm"):
        rel = p.relative_to(help_tree).with_suffix("")
        page = "/".join(rel.parts)
        idx[_norm(page)].append(page)
    return idx


def build(census: dict, help_idx: dict[str, list[str]], census_sha: str,
          help_tree: Path, help_source: str) -> dict:
    """Join census OPTypes to help-page names. Raises on any miss or ambiguity.

    `census_sha` is census_sha256() of the snapshot -- its CANONICAL (LF) bytes,
    not the raw working-tree bytes, so the value is the same on Windows and
    Linux. Passed in rather than recomputed here.
    """
    operators: dict[str, list[dict]] = {}
    missing: list[tuple[str, str]] = []
    ambiguous: list[tuple[str, list[str]]] = []

    for fam in FAMILY_ORDER:
        entries = []
        for optype in census["operators"].get(fam, []):
            pages = help_idx.get(_norm(optype), [])
            if not pages:
                missing.append((fam, optype))
                continue
            if len(pages) > 1:
                ambiguous.append((optype, pages))
                continue
            entries.append({"name": pages[0], "td_create": optype})
        operators[fam] = sorted(entries, key=lambda e: e["name"])

    if missing or ambiguous:
        lines = ["gen_operator_types: REFUSING to generate --"]
        if missing:
            lines.append(f"  {len(missing)} census operator(s) have no help page:")
            lines += [f"    {f}: {o}" for f, o in missing[:20]]
            lines.append("  Do NOT synthesise names for these; synthesis is the "
                         "defect this generator replaces. Check the help tree path.")
        if ambiguous:
            lines.append(f"  {len(ambiguous)} ambiguous match(es):")
            lines += [f"    {o} -> {p}" for o, p in ambiguous[:20]]
        raise SystemExit("\n".join(lines))

    total = sum(len(v) for v in operators.values())

    return {
        "total_operators": total,
        "by_family": {fam: len(operators[fam]) for fam in FAMILY_ORDER},
        "provenance": {
            "generator": "kb_build/gen_operator_types.py",
            "operator_set_source": "eval/ground_truth/td_census.json "
                                   "(live families[] registry -- creatable authority)",
            "name_source": "TouchDesigner shipped OfflineHelp operator page names, "
                           "joined on lowercase-alphanumeric normalisation",
            "td_build": census["td_build"],
            "td_install_root": census.get("td_install_root"),
            # Recorded so a regeneration after a TD upgrade is auditable: which
            # docs tree supplied these names, and how it was chosen. No build
            # number is hardcoded anywhere in the generator.
            "help_tree": help_tree.as_posix(),
            "help_tree_resolved_from": help_source,
            "census_captured_utc": census["captured_utc"],
            "census_sha256": census_sha,
            "subset_of_reality": "by construction -- the operator set is the live "
                                 "registry; no step can introduce a name TD does not have",
        },
        "semantics": {
            "name": "TouchDesigner's own documentation page name (underscored "
                    "display form). NOT guaranteed to match KB display names byte "
                    "for byte -- join on normalised alphanumerics.",
            "td_create": "the OPType, i.e. families[FAM] class __name__ "
                         "(e.g. 'abletonlinkCHOP'). This is NOT the builder '.n' "
                         "create token, which for that operator is 'CHOP:ableton' "
                         "and is recorded as build_token in KB/operators.json. "
                         "Three namespaces exist; do not conflate them.",
            "python_class": "conventionally td_create + '_Class', with documented "
                            "exceptions. The live class is authoritative.",
        },
        "operators": operators,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--census", type=Path, default=CENSUS)
    ap.add_argument("--help-tree", type=Path, default=None,
                    help="offline-help root (default: the one the census recorded "
                         "from the TouchDesigner it was captured on)")
    ap.add_argument("--check", action="store_true",
                    help="generate and compare to --out; write nothing. "
                         "Exit 1 if they differ.")
    args = ap.parse_args()

    if not args.census.exists():
        print(f"gen_operator_types: census snapshot missing: {args.census}\n"
              f"  Capture it first: python scripts/capture_td_census.py",
              file=sys.stderr)
        return 2

    census_bytes = args.census.read_bytes()
    census = json.loads(census_bytes.decode("utf-8"))
    help_tree, help_source = resolve_help_tree(census, args.help_tree)

    if not help_tree.exists():
        print(f"gen_operator_types: offline help tree missing: {help_tree}\n"
              f"  (resolved from: {help_source})\n"
              f"  This generator needs a local TouchDesigner install. The tracked "
              f"output is committed, so CI does not run this.", file=sys.stderr)
        return 2

    # A stale tree paired with a newer census is THE post-upgrade hazard. The
    # 647/647 join in build() is the hard gate -- a new operator would have no
    # page and abort -- but name the suspicion up front rather than letting it
    # surface as a confusing list of unmatched operators.
    build_tail = census.get("td_build", "").split(".", 1)[-1]
    if build_tail and build_tail not in help_tree.as_posix():
        print(f"  ! help tree does not mention census build {build_tail}: "
              f"{help_tree}\n"
              f"    proceeding, but the name join must still be exact or this "
              f"aborts.", file=sys.stderr)

    help_idx = index_help_pages(help_tree)
    doc = build(census, help_idx, census_sha256(census_bytes),
                help_tree, help_source)
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"

    print(f"  td_build        : {doc['provenance']['td_build']}")
    print(f"  help tree       : {help_tree}")
    print(f"  resolved from   : {help_source}")
    print(f"  help pages      : {sum(len(v) for v in help_idx.values())}")
    print(f"  total_operators : {doc['total_operators']}")
    for fam in FAMILY_ORDER:
        print(f"    {fam:<5}: {doc['by_family'][fam]}")

    if args.check:
        if not args.out.exists():
            print(f"\n  --check: {args.out} does not exist", file=sys.stderr)
            return 1
        # read_text() already normalises newlines on read, so this
        # comparison is CRLF-insensitive by construction.
        current = args.out.read_text(encoding="utf-8")
        if current != text:
            print(f"\n  --check: {_rel(args.out)} is STALE "
                  f"(regenerate with this script)", file=sys.stderr)
            return 1
        print(f"\n  --check: {_rel(args.out)} is up to date")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Explicit LF: without it, Python's text mode writes CRLF on Windows and the
    # working tree stops matching its own git blob.
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"\n  wrote {_rel(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

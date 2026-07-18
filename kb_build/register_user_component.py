#!/usr/bin/env python3
"""Register a user .tox as a BUILDABLE component — thin CLI over the W7 engine.

All logic (offline manifest parse, harvest stamp, the G6 relative-path guard,
registry upsert) lives in kb_build/user_components.py; this script only maps
arguments and exit codes. The entry written here is buildable immediately (the
builder merges the user registry over the shipped one at load, user-wins, no
restart) but is NOT search-ingested: the search-wired add surface is the
`register_component` MCP tool (prepare → author → commit), which authors a
discriminating summary and incrementally embeds the comp's chunks into the user
store. `--emit-chunks` is retired (Wave 7 shipped the real integration).

Usage:
    py -3.11 kb_build/register_user_component.py <comp.tox> [--name N]
        [--source project|user|derivative] [--tox-path EMITTED]
        [--registry FILE] [--summary TEXT]
    py -3.11 kb_build/register_user_component.py --reindex-all [--registry FILE]
    py -3.11 kb_build/register_user_component.py --remove NAME [--registry FILE]

--reindex-all and --remove are the store-maintenance surface (BM1): --reindex-all
is the runnable remedy the A8 regime guard names when an incremental ingest is
refused after an embedding-regime change; --remove is the only supported
un-register path. Both are thin wrappers over the same kb_build engine.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
import bootstrap  # noqa: E402

bootstrap.setup()

from paths import user_components_path  # noqa: E402
from kb_build.user_components import (  # noqa: E402
    ComponentManifestError, UserComponentError, build_entry, parse_component,
    reindex_all, remove_component, upsert_registry_entry)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tox", type=Path, nargs="?",
                    help="the component .tox to register (omit for "
                         "--reindex-all/--remove)")
    # BM1: give the store-recovery internals a runnable surface. The A8 regime
    # guard refuses an incremental ingest after a regime change and names
    # --reindex-all as the remedy; --remove is the only supported un-register path.
    ap.add_argument("--reindex-all", dest="reindex_all", action="store_true",
                    help="drop every user-store vector and re-embed the whole "
                         "registry (regime change / manifest corruption recovery)")
    ap.add_argument("--remove", metavar="NAME",
                    help="remove a registered component: registry entry + its "
                         "chunks + its manifest hash")
    ap.add_argument("--name", help="registry name (default: the file stem)")
    ap.add_argument("--source", choices=("project", "user", "derivative"),
                    default="project",
                    help="path root the BUILDER emits: 'project' = plain path constant "
                         "(default; the only offline-verifiable option); 'user'/'derivative' "
                         "= app.userPaletteFolder/app.samplesFolder expressions — then "
                         "--tox-path must be relative to that palette root")
    ap.add_argument("--tox-path", dest="tox_path",
                    help="path the builder emits into projects (default: this file's "
                         "absolute path)")
    ap.add_argument("--registry", type=Path,
                    help="registry file to write (default: paths.user_components_path())")
    ap.add_argument("--summary", default=None,
                    help="one-line semantic summary stored on the entry (default: a "
                         "minimal placeholder; author a real one via the MCP "
                         "register_component tool to make the comp searchable)")
    args = ap.parse_args(argv)

    # BM1 store-maintenance modes (mutually exclusive with registration).
    if args.reindex_all or args.remove:
        if args.reindex_all and args.remove:
            print("error: --reindex-all and --remove are mutually exclusive",
                  file=sys.stderr)
            return 2
        if args.tox is not None:
            print("error: --reindex-all/--remove take no .tox argument",
                  file=sys.stderr)
            return 2
        reg_path = (args.registry or user_components_path()).resolve()
        try:
            if args.remove:
                res = remove_component(args.remove, registry_path=reg_path)
                print(f"removed '{res['name']}' "
                      f"(registry={res['removed_from_registry']}, "
                      f"chunks={res['chunks_deleted']}) -> {reg_path}")
            else:
                res = reindex_all(registry_path=reg_path)
                print(f"reindexed {res['components']} component(s), "
                      f"{res['chunks']} chunk(s) -> {reg_path}")
        except (UserComponentError, ComponentManifestError) as e:
            print(f"error [{getattr(e, 'kind', 'error')}]: {e}", file=sys.stderr)
            return 1
        return 0

    if args.tox is None:
        print("error: a .tox argument is required (or use --reindex-all/--remove)",
              file=sys.stderr)
        return 2

    tox = args.tox.resolve()
    if not tox.is_file():
        print(f"error: not a file: {tox}", file=sys.stderr)
        return 2
    name = args.name or tox.stem
    emitted = (args.tox_path or str(tox)).replace("\\", "/")

    try:
        # G6 lives IN the engine (build_entry); pre-check it here so a bad
        # invocation fails fast without needing TD tools for the expand.
        from kb_build.user_components import relative_path_guard
        relative_path_guard(args.source, emitted)
    except UserComponentError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    try:
        skeleton = parse_component(tox)
    except ComponentManifestError as e:
        print(f"error [{e.kind}]: {e}", file=sys.stderr)
        return 1

    try:
        entry, warnings = build_entry(
            skeleton, source=args.source, tox_path=emitted,
            summary=args.summary or f"{name} user-registered component.")
    except UserComponentError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    reg_path = (args.registry or user_components_path()).resolve()
    try:
        replaced = upsert_registry_entry(name, entry, registry_path=reg_path)
    except UserComponentError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    ins = [d["in_op"] for d in entry["inputs"]]
    outs = [d["out_op"] for d in entry["outputs"]]
    print(f"{'updated' if replaced else 'registered'} '{name}' -> {reg_path}")
    print(f"  source={args.source}  tox_path={emitted}")
    print(f"  in ops:  {ins or '(none)'}")
    print(f"  out ops: {outs or '(none)'}")
    if entry.get("subcompname"):
        print(f"  wrapper .tox -> subcompname={entry['subcompname']} recorded "
              f"(palette builds load the inner comp directly)")
    if entry.get("custom_parameters"):
        print(f"  custom parameters: {len(entry['custom_parameters'])} parsed "
              f"from the interface .cparm")
    for w in warnings:
        print(f"  warning: {w}")
    print("  grounding: offline manifest (NAME authority) — bare wires bind only "
          "single-connector comps; name inner ops explicitly otherwise.")
    print(f"  build with: {{\"name\": \"myNode\", \"palette\": \"{name}\"}}")
    print("  search: NOT ingested by this CLI — use the register_component MCP "
          "tool (prepare -> author -> commit) to make it retrievable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

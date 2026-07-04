#!/usr/bin/env python3
"""Register a user .tox as a BUILDABLE component (BUG-3 rider).

Writes an entry into the USER component registry (default
~/.td_builder/user_components.json, directory overridable via TD_BUILDER_USER_DIR;
never inside KB/ — the KB is a fetched, identity-hashed artifact). The builder merges
the user registry over the shipped one at load (user wins on name collision), so the
component becomes usable as a `palette` field in the very next build — no restart.

Grounding is the OFFLINE manifest (toeexpand + lossless parse + interface scoping —
the same phase the palette harvest runs): a NAME authority, not a connector-index
authority. Entries are stamped harvest.method="offline_manifest", which makes the
builder apply the strict wiring policy automatically (bare wires bind only
single-connector comps; otherwise inner ops must be named explicitly). Wrapper-style
.toxes get their subcompname recorded, so `palette` references load the inner comp
wrapper-free.

Registration is builder-only: ZERO vector-DB / search wiring. The optional
--emit-chunks flag stages ingest_palette-shaped block rows (JSONL) to a directory for
a FUTURE search integration (remediation Wave 7) — nothing reads them today.

Usage:
    py -3.11 kb_build/register_user_component.py <comp.tox> [--name N]
        [--source project|user|derivative] [--tox-path EMITTED]
        [--registry FILE] [--emit-chunks DIR]
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
import bootstrap  # noqa: E402

bootstrap.setup()

from paths import user_components_path  # noqa: E402
from core.component_manifest import (  # noqa: E402
    ComponentManifestError, manifest_from_tox, offline_entry)

REGISTRY_SKELETON = {
    "version": 1,
    "description": ("TD Builder USER component registry (register_user_component.py). "
                    "Merged over KB/palette_components.json at load; user entries win "
                    "on name collision. Offline-grounded: NAME authority only."),
    "components": {},
}


def _emit_chunks(outdir: Path, name: str, entry: dict) -> Path:
    """Stage block_overview + block_io rows (kb_build/ingest_palette.py shapes) as
    JSONL. Deliberately NO block_usecase (it needs semantic-catalog seeds a user
    registration doesn't have) and NO search wiring (Wave 7's job)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import common as C

    category = entry.get("category") or "User"
    ins = [d["in_op"] for d in entry.get("inputs", [])]
    outs = [d["out_op"] for d in entry.get("outputs", [])]
    base_meta = {
        "name": name,
        "palette_name": name,
        "category": category,
        "has_ui": False,
        "complexity": None,
        "operator_count": entry.get("operator_count"),
        "tox_path": entry.get("tox_path"),
        "wiki_url": None,
        "license_tier": "user",
    }
    oid = f"block:{C.slug(name)}:overview"
    ov = (f"USER COMPONENT: {name} [{category}] — user-registered prebuilt component"
          f" ({entry.get('operator_count')} inner operators)."
          f" Instantiate via the builder: {{\"palette\": \"{name}\"}}."
          f" Connectors: in={ins or 'none'}, out={outs or 'none'}.")
    rows = [C.make_row(oid, ov, "block_overview", C.STORE_BLOCK, dict(base_meta))]
    io_txt = (f"USER COMPONENT I/O: {name} ({category}) — in ops: {ins or 'none'};"
              f" out ops: {outs or 'none'}. Wire inner ops explicitly"
              f" ('{name}/<op>'); a component is never itself a data source.")
    rows.append(C.make_row(f"block:{C.slug(name)}:io", io_txt, "block_io",
                           C.STORE_BLOCK, dict(base_meta), parent=oid))

    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / f"{name}.blocks.jsonl"
    out_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                        encoding="utf-8")
    return out_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("tox", type=Path, help="the component .tox to register")
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
    ap.add_argument("--emit-chunks", dest="emit_chunks", type=Path,
                    help="ALSO stage search-block JSONL rows to this directory "
                         "(no search wiring — future integration point)")
    args = ap.parse_args(argv)

    tox = args.tox.resolve()
    if not tox.is_file():
        print(f"error: not a file: {tox}", file=sys.stderr)
        return 2
    name = args.name or tox.stem

    try:
        res = manifest_from_tox(tox)
    except ComponentManifestError as e:
        print(f"error [{e.kind}]: {e}", file=sys.stderr)
        return 1

    emitted = (args.tox_path or str(tox)).replace("\\", "/")
    entry = offline_entry(res["manifest"], res["inner_type"], source=args.source,
                          tox_path=emitted, subcompname=res.get("subcompname"))
    entry["harvest"] = {"method": "offline_manifest",
                        "date": datetime.date.today().isoformat()}

    reg_path = (args.registry or user_components_path()).resolve()
    spec = None
    if reg_path.is_file():
        try:
            spec = json.loads(reg_path.read_text(encoding="utf-8"))
            if not isinstance(spec.get("components"), dict):
                raise ValueError('missing "components" object')
        except Exception as e:
            print(f"error: existing registry {reg_path} is unreadable ({e}); "
                  f"fix or remove it first", file=sys.stderr)
            return 1
    if spec is None:
        spec = json.loads(json.dumps(REGISTRY_SKELETON))
    replaced = name in spec["components"]
    spec["components"][name] = entry

    reg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = reg_path.with_name(reg_path.name + ".tmp")
    tmp.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(reg_path)

    ins = [d["in_op"] for d in entry["inputs"]]
    outs = [d["out_op"] for d in entry["outputs"]]
    print(f"{'updated' if replaced else 'registered'} '{name}' -> {reg_path}")
    print(f"  source={args.source}  tox_path={emitted}")
    print(f"  in ops:  {ins or '(none)'}")
    print(f"  out ops: {outs or '(none)'}")
    if entry.get("subcompname"):
        print(f"  wrapper .tox -> subcompname={entry['subcompname']} recorded "
              f"(palette builds load the inner comp directly)")
    print("  grounding: offline manifest (NAME authority) — bare wires bind only "
          "single-connector comps; name inner ops explicitly otherwise.")
    print(f"  build with: {{\"name\": \"myNode\", \"palette\": \"{name}\"}}")

    if args.emit_chunks:
        staged = _emit_chunks(args.emit_chunks, name, entry)
        print(f"  chunks staged -> {staged} (NOT wired into search)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

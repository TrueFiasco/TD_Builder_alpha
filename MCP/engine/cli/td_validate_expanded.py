#!/usr/bin/env python3
"""
td_validate_expanded: Validate that a TouchDesigner expanded folder matches its `.toc`.

This checks the most common "why won't toecollapse work" issue:
- `.toc` references files that do not exist in the `.toe/.tox.dir` directory

It can also report extra files present on disk that are not listed in `.toc`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExpandedValidationResult:
    toc_file: Path
    dir_path: Path
    toc_entries: list[str]
    missing_toc_entries: list[str]
    extra_disk_files: list[str]


def _toc_entry_to_disk_path(toc_entry: str) -> str:
    parts = toc_entry.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        base, dup = parts[0], parts[1]
        return f"{base}.{dup}"
    return toc_entry


def _disk_rel_to_path(rel_posix: str) -> Path:
    # `.toc` uses `/` separators; on Windows these still work, but normalize anyway.
    return Path(*rel_posix.split("/"))


def _find_pair(input_path: Path) -> tuple[Path, Path]:
    """Return (toc_file, dir_path)."""
    p = input_path
    if p.is_dir() and (p.name.endswith(".toe.dir") or p.name.endswith(".tox.dir") or p.name.endswith(".dir")):
        dir_path = p
        toc_file = p.parent / f"{p.name[:-4]}.toc"
        if not toc_file.exists():
            # last resort: any `.toc` in the parent
            candidates = sorted(p.parent.glob("*.toc"))
            if candidates:
                toc_file = candidates[0]
        return toc_file, dir_path

    if p.is_file() and p.suffix.lower() == ".toc":
        toc_file = p
        dir_path = p.parent / p.name.replace(".toc", ".dir")
        return toc_file, dir_path

    raise ValueError("Input must be a `.toe/.tox.dir` directory or a `.toe/.tox.toc` file.")


def validate_expanded_pair(input_path: Path, *, strict_extra: bool) -> ExpandedValidationResult:
    toc_file, dir_path = _find_pair(input_path)

    if not toc_file.exists():
        raise FileNotFoundError(f".toc not found: {toc_file}")
    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f".dir folder not found: {dir_path}")

    toc_entries: list[str] = []
    for raw in toc_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        toc_entries.append(line)

    toc_disk_paths = [_toc_entry_to_disk_path(e) for e in toc_entries]
    toc_disk_set = set(toc_disk_paths)

    missing: list[str] = []
    for entry, disk_rel in zip(toc_entries, toc_disk_paths, strict=True):
        disk_path = dir_path / _disk_rel_to_path(disk_rel)
        if not disk_path.exists():
            missing.append(entry)

    disk_files: list[str] = []
    for fp in dir_path.rglob("*"):
        if fp.is_file():
            disk_files.append(fp.relative_to(dir_path).as_posix())
    disk_set = set(disk_files)

    extra = sorted(disk_set - toc_disk_set)

    if strict_extra and extra:
        # treated as an error by the caller (exit code 1)
        pass

    return ExpandedValidationResult(
        toc_file=toc_file,
        dir_path=dir_path,
        toc_entries=toc_entries,
        missing_toc_entries=missing,
        extra_disk_files=extra,
    )


def _to_json(result: ExpandedValidationResult) -> dict[str, Any]:
    return {
        "toc_file": str(result.toc_file),
        "dir_path": str(result.dir_path),
        "toc_entries": len(result.toc_entries),
        "missing_toc_entries": result.missing_toc_entries,
        "extra_disk_files": result.extra_disk_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate that a TouchDesigner expanded `.toe/.tox.dir` matches its `.toc` file."
    )
    parser.add_argument("input", type=Path, help="Path to `.toe/.tox.dir` folder or `.toe/.tox.toc` file")
    parser.add_argument("--strict-extra", action="store_true", help="Treat extra disk files as errors")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--max", type=int, default=50, help="Max lines to print per list (default: 50)")
    args = parser.parse_args()

    try:
        result = validate_expanded_pair(args.input, strict_extra=args.strict_extra)
    except Exception as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 2

    ok = (len(result.missing_toc_entries) == 0) and (not args.strict_extra or len(result.extra_disk_files) == 0)

    if args.json:
        payload = _to_json(result)
        payload["ok"] = ok
        payload["strict_extra"] = args.strict_extra
        print(json.dumps(payload, indent=2))
        return 0 if ok else 1

    print("TouchDesigner expanded validation")
    print("=" * 70)
    print(f".toc: {result.toc_file}")
    print(f".dir: {result.dir_path}")
    print(f"toc entries: {len(result.toc_entries)}")
    print(f"missing toc entries: {len(result.missing_toc_entries)}")
    print(f"extra disk files: {len(result.extra_disk_files)}")
    print()

    if result.missing_toc_entries:
        print("Missing (toc -> disk):")
        for entry in result.missing_toc_entries[: max(0, args.max)]:
            print(f"  - {entry}")
        if len(result.missing_toc_entries) > args.max:
            print(f"  ... ({len(result.missing_toc_entries) - args.max} more)")
        print()

    if result.extra_disk_files:
        print("Extra (disk not in toc):")
        for rel in result.extra_disk_files[: max(0, args.max)]:
            print(f"  - {rel}")
        if len(result.extra_disk_files) > args.max:
            print(f"  ... ({len(result.extra_disk_files) - args.max} more)")
        print()

    if ok:
        print("[OK] Expanded folder matches `.toc`.")
        return 0

    if args.strict_extra and result.extra_disk_files:
        print("[FAIL] Missing entries or extra files present (strict).")
    else:
        print("[FAIL] Missing entries listed in `.toc`.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


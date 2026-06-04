#!/usr/bin/env python3
"""
td-fixture-pipeline: End-to-end fixture pipeline for real TouchDesigner files.

Current goal (for reverse engineering / future abstraction work):
  toe -> toeexpand (toc/dir) -> lossless JSON -> builder JSON -> build toc/dir -> toecollapse -> toe

Notes:
- `toeexpand.exe` appears to return exit code 1 even on success (at least on some builds).
- This pipeline does not guarantee parameter correctness when opening the rebuilt `.toe` in TouchDesigner.
  It guarantees we can mechanically translate between the file/container formats and our JSON layers.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# Add unified_system to path
UNIFIED_SYSTEM_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(UNIFIED_SYSTEM_ROOT))

from core.format_converter import FormatConverter
from core.lossless_json import to_lossless_json_dict
from parsers.lossless_parser import parse_toe_lossless
from builders.toe_builder import TOEBuilder


def _find_td_tool(exe_name: str) -> Optional[Path]:
    found = shutil.which(exe_name)
    if found:
        return Path(found)

    candidates = [
        Path(r"C:\Program Files\Derivative\TouchDesigner\bin") / exe_name,
        Path(r"C:\Program Files\Derivative\TouchDesigner.2025.30060\bin") / exe_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _run(args: list[str], cwd: Optional[Path] = None, ok_returncodes: set[int] | None = None) -> int:
    ok_returncodes = ok_returncodes or {0}
    proc = subprocess.run(args, cwd=str(cwd) if cwd else None)
    if proc.returncode not in ok_returncodes:
        raise RuntimeError(f"Command failed (rc={proc.returncode}): {args}")
    return proc.returncode


def _serialize(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return {k: _serialize(v) for k, v in asdict(obj).items() if v is not None}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    return obj


def _normalize_text(s: str) -> str:
    return s.replace("\r\n", "\n")


def _verify_lossless_roundtrip(network, out_dir: Path):
    toc_order = network.lossless_data.toc_order
    toc_raw_lines = network.lossless_data.toc_raw_lines
    toc_disk_paths = network.lossless_data.toc_disk_paths
    raw_files = network.lossless_data.raw_files

    mode = network.metadata.mode or "toe"
    out_toc = out_dir / f"lossless_roundtrip.{mode}.toc"
    out_project = out_dir / f"lossless_roundtrip.{mode}"
    built_toc = TOEBuilder(network, verbose=False).build(out_project, mode=mode)
    built_dir = built_toc.parent / built_toc.name.replace(".toc", ".dir")
    if built_toc != out_toc:
        # normalize name for expected locations (keep output tidy)
        built_toc.replace(out_toc)
        built_dir.replace(out_dir / f"lossless_roundtrip.{mode}.dir")
        built_toc = out_toc
        built_dir = out_dir / f"lossless_roundtrip.{mode}.dir"

    out_toc_lines = [ln.strip() for ln in built_toc.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if out_toc_lines != toc_raw_lines:
        raise AssertionError("LOSSLESS .toc mismatch (raw lines differ)")

    for fp in toc_order:
        out_file = built_dir / toc_disk_paths.get(fp, fp)
        if not out_file.exists():
            raise FileNotFoundError(f"Missing rebuilt file: {fp}")

        data = raw_files[fp]
        if data.get("is_binary", False):
            expected = base64.b64decode(data["content"])
            got = out_file.read_bytes()
            if got != expected:
                raise AssertionError(f"Binary mismatch: {fp}")
        else:
            expected = _normalize_text(data["content"])
            got = _normalize_text(out_file.read_text(encoding="utf-8"))
            if got != expected:
                raise AssertionError(f"Text mismatch: {fp}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a full fixture pipeline for a TouchDesigner .toe/.tox file.")
    parser.add_argument("project", type=Path, help="Input .toe or .tox file")
    parser.add_argument("--out", type=Path, required=True, help="Output directory for artifacts")
    parser.add_argument("--no-verify-lossless", action="store_true", help="Skip lossless round-trip verification")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON outputs")
    args = parser.parse_args()

    if not args.project.exists():
        print(f"Error: input file not found: {args.project}", file=sys.stderr)
        return 2
    mode = args.project.suffix.lower().lstrip(".")
    if mode not in ("toe", "tox"):
        print(f"Error: input must be .toe or .tox (got: {args.project.suffix})", file=sys.stderr)
        return 2

    toeexpand = _find_td_tool("toeexpand.exe")
    toecollapse = _find_td_tool("toecollapse.exe")
    if not toeexpand or not toecollapse:
        print("Error: TouchDesigner CLI tools not found (toeexpand.exe / toecollapse.exe)", file=sys.stderr)
        return 2

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    base = args.project.stem
    work_project = out_dir / f"{base}.{mode}"
    shutil.copy2(args.project, work_project)

    # toe -> toc/dir
    print(f"[1/5] toeexpand: {work_project}")
    _run([str(toeexpand), str(work_project)], cwd=out_dir, ok_returncodes={0, 1})

    toe_dir = out_dir / f"{base}.{mode}.dir"
    if not toe_dir.exists():
        # toeexpand always uses exact input name; if input already had a different extension naming, fall back.
        toe_dir = out_dir / f"{work_project.name}.dir"

    # toc/dir -> lossless JSON
    print(f"[2/5] parse (lossless): {toe_dir}")
    network = parse_toe_lossless(toe_dir, registry=None, verbose=False)

    indent = 2 if args.pretty else None

    lossless_json_path = out_dir / f"{base}.lossless.json"
    lossless_payload = to_lossless_json_dict(network)
    lossless_json_path.write_text(json.dumps(lossless_payload, indent=indent), encoding="utf-8")
    print(f"      wrote: {lossless_json_path}")

    # Optional: verify lossless round-trip
    if not args.no_verify_lossless:
        print(f"[3/5] verify lossless round-trip")
        _verify_lossless_roundtrip(network, out_dir)
        print("      ok")
    else:
        print(f"[3/5] verify lossless round-trip (skipped)")

    # lossless -> builder JSON
    print(f"[4/5] convert -> builder JSON")
    converter = FormatConverter()
    builder_json = converter.to_builder(network)
    builder_json_path = out_dir / f"{base}.builder.json"
    builder_json_path.write_text(json.dumps(builder_json, indent=indent), encoding="utf-8")
    print(f"      wrote: {builder_json_path}")

    # builder JSON -> toc/dir -> toe
    # FIX: Use original lossless network (with raw_files), not rebuilt_network from builder JSON
    # The builder JSON doesn't have lossless_data, so rebuilt_network would use BASIC mode
    # and lose .network/.gnode/.panel files
    print(f"[5/5] build + toecollapse")
    rebuilt_project = out_dir / f"{base}.rebuilt.{mode}"
    rebuilt_toc = TOEBuilder(network, verbose=False).build(rebuilt_project, mode=mode)
    _run([str(toecollapse), str(rebuilt_toc)], cwd=out_dir)
    print(f"      wrote: {rebuilt_project}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

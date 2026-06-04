# TOEEXPAND / TOECOLLAPSE Format Notes (WIP)

## toeexpand usage
- Binary: `C:\Program Files\Derivative\TouchDesigner\bin\toeexpand.exe`
- Usage (from stdout): `toeexpand.exe [-b] filename [pattern]`
  - `-b` outputs build information directly.
  - Expands `.toe` or `.tox` into `.toe.dir`/`.tox.dir` + sibling `.toc`.
  - Example: `toeexpand.exe untitled.toe`, `toeexpand.exe filter.tox`
- toecollapse: inverse operation (not invoked yet in this doc).

## Minimal expanded example (built via NetworkBuilder -> .tox -> expand)
Sample: Constant CHOP (defval = 0.5), expanded `.tox.dir/.toc`:
- `.toc` contents (order matters):
  - `.build`, `.start`, `.root`, `.grps`, `.parm`, `.application`
  - `project1/const1.n`, `project1/const1.parm`
- Files observed:
  - `.build`: `build 0`
  - `.start`: `cookrate 60`, `realtime on`
  - `.root`: `project1` … `end`
  - `.grps`: `-2` / `0`
  - `.parm`: `?` lines (placeholder/global?)
  - `.application`: pane/layout info (neteditor config, winplacement)
  - `project1/const1.n`: operator definition
  - `project1/const1.parm`: parameter values
- Parsed JSON (lossless parser):
  - metadata: source_directory, build_version/build_number, build_date, os_name/os_version, cookrate, realtime
  - operators: path `/project1/const1`, family/type `CHOP:constant`, params `{defval: 0.5}`, parent `/project1`
  - raw_files: captured metadata/ui files
  - toc_order: preserved from `.toc`
  - connections: none

## Key format elements (from lossless parser)
- `.toc` is a plain list of relative file paths; order must be preserved.
- Operator files:
  - `<path>.n`:
    - First line: `FAMILY:specific` (e.g., `CHOP:constant`)
    - Optional lines: `v ...` (viewport), `tile ...`, `color ...`, `flags = key val ...`
    - `inputs { ... }` block: input index -> source path
  - `<path>.parm`:
    - Lines `param_name param_index value`; non-zero indices for multi-component params.
- Metadata files:
  - `.build` (version/build/os), `.start` (cookrate/realtime), `.root` (root comp names), `.grps` (group info), `.application` (desk/neteditor/winplacement).
- Connections derived from `inputs` in `.n` files; parents inferred from path.

## Gaps to close (reverse-engineering)
- Parse additional file types: `.grps` semantics, `.root` for multiple roots, `.t` (timeline), `.ui`, `.comp`, `.chan`/`.clip`, any shader/script payloads.
- Parameter typing/mode: map .parm encodings to typed values, expressions, menu modes; store TD numeric mode (td_mode) where present.
- Flags: ensure render/display/viewer/current/lock/bypass captured with defaults.
- Versioning: extract build/version reliably from `.build` and store in metadata.
- Checksums: capture sha256 per file to detect corruption.
- Connections: verify relative vs absolute paths for nested COMPs; ensure parent existence.
- Binary assets: identify and base64 encode non-text files; annotate mime/extension.

## Next steps
1) Expand small ladder of test cases (tox with 1 op; tox with connection; toe with single op; feedback TOP; instancing; POP/particle; one palette tox) and record parsed outputs.
2) Enhance parser to cover missing file types and param typing/modes; add checksums and TD version extraction.
3) Align parsed output to `lossless_v2.schema.json` (unified_system) and ensure toc_order/raw_files/operators/metadata fields match.
4) Round-trip tests: expand -> parse -> write -> toecollapse -> td-validate; compare operator/param/connection counts.

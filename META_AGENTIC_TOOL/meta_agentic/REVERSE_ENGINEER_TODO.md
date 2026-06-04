# Reverse Engineering Plan for .toe.dir/.tox.dir (expanded files)

## Current assets (old system)
- `archive/legacy_scripts/toe_to_json_LOSSLESS.py`: parses `.toc`, reads all files listed, decodes .n/.parm into ops/params, captures extra/raw files, preserves `.toc` ordering.
- `archive/legacy_scripts/json_to_dir_LOSSLESS.py` (and variants in gpt/Parsers_Builders_Embedders): writes `.toc` and files back from JSON.
- `unified_system` lossless schema (`schemas/lossless_v2.schema.json`) expects toc_order + raw_files + operators.
- MCP builder tools assume expanded `.toe.dir` + `.toc` but don’t deep-parse the file formats.

## Gaps to close
1) File coverage and semantics
   - Parse `.grps`, `.root`, `.t` (timeline), `.ui`, `.comp` (if present), `.chan`/`.clip` when listed in `.toc`.
   - Capture parameter types/modes (menu, pulse, toggles) and expressions; map `.parm` encodings to typed values.
   - Record TD version/build from `.build` + `.start` into metadata.
2) Connections and parentage
   - Confirm connection parsing for nested comps; handle relative vs absolute paths; detect missing parents.
   - Preserve flags (render/display/bypass/lock/viewer/current) per operator with explicit defaults.
3) Lossless binary handling
   - Identify binary files (.dds/.tox inside, shader blobs) and annotate encoding/base64 with mime/extension.
   - Add checksum per file to detect corruption.
4) Round-trip writer
   - Ensure `json_to_dir_LOSSLESS.py` preserves original `.toc` header/footer and ordering; write perms/time stamps (if needed).
   - Emit correct subdir structure for nested comps (respect paths from .n/.parm names).
5) Validation & tests
   - Build a small corpus of `.toe.dir`/`.tox.dir` samples (empty, simple network, feedback TOP loop, GLSL MAT).
   - Add round-trip tests: expand -> parse -> write -> toecollapse -> td-validate.
   - Compare stats (operator count, params, connections) pre/post round-trip.
6) Schema alignment
   - Align parsed output to `lossless_v2.schema.json`; ensure toc_order/raw_files/operators/metadata match expectations.
   - Add TD version + build_number to metadata consistently.

## Proposed next steps
1) Extend parser:
   - Update `toe_to_json_LOSSLESS.py` to parse `.grps`, `.root`, `.ui`, `.t` timeline markers, and attach to metadata or operators.
   - Enhance parameter parsing to include type/mode/expression where encoded; add td_mode numeric if present.
   - Add file checksum (sha256) per captured file.
2) Writer hardening:
   - Verify `json_to_dir_LOSSLESS.py` writes `.toc` exactly (header + ordering) and reconstructs directory tree; add checksum checks.
3) Test corpus + automation:
   - Collect 3–5 expanded samples under `META_AGENTIC_TOOL/temp/expanded_samples/`.
   - Add a simple pytest/PowerShell script to round-trip each sample: parse -> write -> toecollapse -> td-validate.
4) Evidence logging:
   - Log findings and fixes via meta_agentic event log (domain: file_formats) so expertise stays in sync after compaction.

## Quick wins
- Parse `.grps` and `.root` immediately (small text files) and attach to metadata.
- Add checksums and TD version extraction to metadata for every parse.
- Round-trip a simple sample (e.g., kb_pipeline/builds/toe_empty_roundtrip) to surface gaps.***

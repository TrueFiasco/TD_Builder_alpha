"""Lossless Writer - TDNetwork to .tox.dir format for perfect round-trip fidelity.

Converts a TDNetwork object back to the expanded .tox.dir/.toe.dir format
with 100% fidelity, preserving all sections and file ordering.

OUT OF SHIPPING PATH (W2b audit, 2026-07): no importers anywhere in the repo
(MCP/, tests/, eval/, scripts/). Its .parm emission is NOT quoting-aware --
values go raw into f-strings (_format_parameter/_format_parameter_value), so a
value or expression containing a space would truncate and desync TD's .parm
parser. Do NOT revive this module without routing every .parm body line through
the canonical writer: server_core/meta_agentic/execution/toe_builder_bridge._parm_line.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import base64
from typing import Dict, List, Any, Optional, Tuple

from core.models import (
    TDNetwork, Operator, ParameterValue, OperatorFamily,
    LosslessData, ExtraFile
)


class LosslessWriter:
    """
    Write TDNetwork to .tox.dir/.toe.dir format with perfect round-trip fidelity.

    Handles:
    - .n files with ALL sections in correct order
    - .parm files with proper format
    - All extra files from lossless_data.raw_files
    - TOC generation with correct ordering and versioned file handling
    """

    def __init__(self, network: TDNetwork, verbose: bool = True):
        """
        Initialize lossless writer.

        Args:
            network: TDNetwork object to write
            verbose: Print progress messages
        """
        self.network = network
        self.verbose = verbose
        self.files_written: List[str] = []
        self.toc_entries: List[str] = []

        # Build operator lookup by path
        self.operators_by_path: Dict[str, Operator] = {
            op.path: op for op in network.operators
        }

    def write(self, output_dir: Path, mode: str = "tox") -> Path:
        """
        Write TDNetwork to .tox.dir/.toe.dir format.

        Args:
            output_dir: Parent directory for output
            mode: "tox" or "toe"

        Returns:
            Path to created .toc file
        """
        self.mode = mode

        # Determine base name from metadata
        base_name = self.network.metadata.project_name

        self.dir_path = output_dir / f"{base_name}.{mode}.dir"
        self.toc_path = output_dir / f"{base_name}.{mode}.toc"

        if self.verbose:
            print(f"\nWriting {mode.upper()}: {base_name}")
            print("=" * 70)
            print(f"Output: {self.dir_path}")

        # Clean up existing output
        import shutil
        if self.dir_path.exists():
            if self.verbose:
                print(f"Removing existing {self.dir_path}")
            shutil.rmtree(self.dir_path)
        if self.toc_path.exists():
            self.toc_path.unlink()

        # Create output directory
        self.dir_path.mkdir(parents=True, exist_ok=True)

        # Check if we have lossless data for perfect round-trip
        if self.network.lossless_data and self.network.lossless_data.toc_order:
            self._write_lossless()
        else:
            self._write_from_operators()

        # Write TOC file
        self._write_toc()

        if self.verbose:
            print()
            print("=" * 70)
            print("[WRITE COMPLETE]")
            print("=" * 70)
            print(f"\n[OK] {len(self.network.operators)} operators")
            print(f"[OK] {len(self.files_written)} files written")
            print(f"\nNext step:")
            print(f"  toecollapse {self.toc_path}")

        return self.toc_path

    # =========================================================================
    # Unix line ending text writer
    # =========================================================================

    def _write_text(self, path: Path, content: str):
        """Write text file with Unix line endings (LF only)."""
        # Ensure Unix line endings
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)

    def _write_binary(self, path: Path, data: bytes):
        """Write binary file."""
        path.write_bytes(data)

    # =========================================================================
    # Lossless mode - use stored raw files and TOC order
    # =========================================================================

    def _write_lossless(self):
        """Write using lossless data for perfect round-trip."""
        if self.verbose:
            print(f"\nWriting files in original order (LOSSLESS)...")

        lossless = self.network.lossless_data
        toc_order = lossless.toc_order
        toc_disk_paths = lossless.toc_disk_paths or {}
        raw_files = lossless.raw_files or {}

        for idx, toc_entry in enumerate(toc_order, 1):
            if self.verbose and idx % 100 == 0:
                print(f"  Progress: {idx}/{len(toc_order)}")

            # Get disk path (handles versioned files)
            disk_path = toc_disk_paths.get(toc_entry, toc_entry)

            # Determine file type and write accordingly
            if toc_entry.endswith('.n') or self._is_versioned_n_file(toc_entry):
                # Write .n file - regenerate from operator for modifications
                self._write_n_file(toc_entry, disk_path, raw_files)
            elif toc_entry.endswith('.parm') or self._is_versioned_parm_file(toc_entry):
                # Write .parm file - regenerate from operator for modifications
                self._write_parm_file(toc_entry, disk_path, raw_files)
            elif toc_entry in raw_files:
                # Write raw file exactly as stored
                self._write_raw_file(toc_entry, disk_path, raw_files[toc_entry])
            else:
                if self.verbose:
                    print(f"  WARNING: File not found in raw_files: {toc_entry}")
                continue

            self.toc_entries.append(toc_entry)

    def _is_versioned_n_file(self, toc_entry: str) -> bool:
        """Check if TOC entry is a versioned .n file (e.g., 'snare.n 2')."""
        parts = toc_entry.rsplit(' ', 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0].endswith('.n')
        return False

    def _is_versioned_parm_file(self, toc_entry: str) -> bool:
        """Check if TOC entry is a versioned .parm file (e.g., 'snare.parm 2')."""
        parts = toc_entry.rsplit(' ', 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0].endswith('.parm')
        return False

    def _write_n_file(self, toc_entry: str, disk_path: str, raw_files: Dict):
        """Write .n file for an operator."""
        # Get operator path from toc entry
        op_path = self._toc_entry_to_operator_path(toc_entry, '.n')

        full_path = self.dir_path / disk_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if op_path in self.operators_by_path:
            # Regenerate from operator (allows modifications)
            op = self.operators_by_path[op_path]
            content = self._generate_n_content(op)
            self._write_text(full_path, content)
        elif toc_entry in raw_files:
            # Fall back to raw content
            self._write_raw_file(toc_entry, disk_path, raw_files[toc_entry])
        else:
            if self.verbose:
                print(f"  WARNING: Operator not found: {op_path}")
            return

        self.files_written.append(disk_path)

    def _write_parm_file(self, toc_entry: str, disk_path: str, raw_files: Dict):
        """Write .parm file for an operator."""
        # Get operator path from toc entry
        op_path = self._toc_entry_to_operator_path(toc_entry, '.parm')

        full_path = self.dir_path / disk_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if op_path in self.operators_by_path:
            # Regenerate from operator (allows modifications)
            op = self.operators_by_path[op_path]
            content = self._generate_parm_content(op.parameters)
            self._write_text(full_path, content)
        elif toc_entry in raw_files:
            # Fall back to raw content
            self._write_raw_file(toc_entry, disk_path, raw_files[toc_entry])
        else:
            # Empty .parm file
            self._write_text(full_path, "?\n?\n")

        self.files_written.append(disk_path)

    def _write_raw_file(self, toc_entry: str, disk_path: str, file_data: Dict):
        """Write file from stored raw data."""
        full_path = self.dir_path / disk_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        content = file_data['content']
        is_binary = file_data.get('is_binary', False)

        if is_binary:
            # Decode base64 and write as binary
            binary_data = base64.b64decode(content)
            self._write_binary(full_path, binary_data)
        else:
            self._write_text(full_path, content)

        self.files_written.append(disk_path)

    def _toc_entry_to_operator_path(self, toc_entry: str, extension: str) -> str:
        """Convert TOC entry to operator path.

        Examples:
            'project1/noise1.n' -> '/project1/noise1'
            'project1/snare.n 2' -> '/project1/snare'
        """
        # Handle versioned files (e.g., 'snare.n 2')
        parts = toc_entry.rsplit(' ', 1)
        if len(parts) == 2 and parts[1].isdigit():
            toc_entry = parts[0]

        # Remove extension and add leading slash
        path_without_ext = toc_entry
        if path_without_ext.endswith(extension):
            path_without_ext = path_without_ext[:-len(extension)]

        return '/' + path_without_ext

    # =========================================================================
    # Generate from operators mode (no lossless data)
    # =========================================================================

    def _write_from_operators(self):
        """Write files from operator data when no lossless data available."""
        if self.verbose:
            print(f"\nGenerating from operators...")

        # Write metadata files
        self._write_metadata_files()

        # Write operator files
        for op in self.network.operators:
            self._write_operator_files(op)

        if self.verbose:
            print(f"  [OK] Wrote {len(self.network.operators)} operators")

    def _write_metadata_files(self):
        """Write metadata files (.build, .start, etc.)."""
        meta = self.network.metadata

        # .build
        lines = []
        if meta.td_version:
            lines.append(f"version {meta.td_version}")
        if meta.build_number:
            lines.append(f"build {meta.build_number}")
        if meta.build_date:
            lines.append(f"time {meta.build_date}")

        if lines:
            content = '\n'.join(lines) + '\n'
            self._write_text(self.dir_path / '.build', content)
            self.files_written.append('.build')
            self.toc_entries.append('.build')

        # .start (for .toe mode)
        if self.mode == "toe":
            lines = [
                f"cookrate {meta.cookrate}",
                f"realtime {'on' if meta.realtime else 'off'}"
            ]
            content = '\n'.join(lines) + '\n'
            self._write_text(self.dir_path / '.start', content)
            self.files_written.append('.start')
            self.toc_entries.append('.start')

            # .root
            content = f"{meta.root_comp}\nend\n"
            self._write_text(self.dir_path / '.root', content)
            self.files_written.append('.root')
            self.toc_entries.append('.root')

            # .grps
            content = "-2\n0\n"
            self._write_text(self.dir_path / '.grps', content)
            self.files_written.append('.grps')
            self.toc_entries.append('.grps')

            # .parm (root)
            content = "?\n?\n"
            self._write_text(self.dir_path / '.parm', content)
            self.files_written.append('.parm')
            self.toc_entries.append('.parm')

    def _write_operator_files(self, op: Operator):
        """Write .n and .parm files for an operator."""
        # Convert path to file path
        relative_path = op.path.lstrip('/')

        # Write .n file
        n_path = f"{relative_path}.n"
        full_n_path = self.dir_path / n_path
        full_n_path.parent.mkdir(parents=True, exist_ok=True)

        content = self._generate_n_content(op)
        self._write_text(full_n_path, content)
        self.files_written.append(n_path)
        self.toc_entries.append(n_path)

        # Write .parm file
        parm_path = f"{relative_path}.parm"
        full_parm_path = self.dir_path / parm_path
        full_parm_path.parent.mkdir(parents=True, exist_ok=True)

        content = self._generate_parm_content(op.parameters)
        self._write_text(full_parm_path, content)
        self.files_written.append(parm_path)
        self.toc_entries.append(parm_path)

        # Write extra files
        for ext, extra_file in op.extra_files.items():
            extra_path = f"{relative_path}.{ext}"
            full_extra_path = self.dir_path / extra_path
            full_extra_path.parent.mkdir(parents=True, exist_ok=True)

            if extra_file.is_binary:
                binary_data = base64.b64decode(extra_file.content)
                self._write_binary(full_extra_path, binary_data)
            else:
                self._write_text(full_extra_path, extra_file.content)

            self.files_written.append(extra_path)
            self.toc_entries.append(extra_path)

    # =========================================================================
    # .n file generation - ALL sections in correct order
    # =========================================================================

    def _generate_n_content(self, op: Operator) -> str:
        """
        Generate .n file content with ALL sections in correct order.

        Section order:
        1. Line 1: FAMILY:type
        2. v: viewport position (optional)
        3. tile: tile x y w h
        4. flags: flags = key value key value...
        5. inputs: inputs { idx \t source ... }
        6. exports: exports { name1 name2 ... }
        7. color: color r g b
        8. dict: dict HEXDATA
        9. end: end
        """
        lines = []

        # 1. FAMILY:type (Line 1)
        lines.append(op.op_type)

        # 2. v: viewport position (optional)
        if op.position and op.position.viewport:
            vp = op.position.viewport
            # Format with proper spacing
            if len(vp) >= 3:
                lines.append(f"v {vp[0]} {vp[1]} {vp[2]}")
            elif len(vp) == 2:
                lines.append(f"v {vp[0]} {vp[1]} 0")

        # 3. tile: tile x y w h
        if op.position and op.position.tile:
            tp = op.position.tile
            if len(tp) >= 4:
                lines.append(f"tile {tp[0]} {tp[1]} {tp[2]} {tp[3]}")

        # 4. flags: flags = key value key value...
        flags_parts = self._build_flags_parts(op)
        if flags_parts:
            lines.append(f"flags = {' '.join(flags_parts)}")

        # 5. inputs: inputs { idx \t source ... }
        if op.inputs:
            lines.append("inputs")
            lines.append("{")
            for inp in sorted(op.inputs, key=lambda x: x.index):
                # Use tab separator as in original format
                lines.append(f"{inp.index}\t{inp.src}")
            lines.append("}")

        # 6. exports: exports { name1 name2 ... }
        exports = op.custom_data.get('exports', [])
        if exports:
            lines.append("exports")
            lines.append("{")
            for export_name in exports:
                lines.append(export_name)
            lines.append("}")

        # 7. color: color r g b
        color = op.custom_data.get('color')
        if color:
            if len(color) >= 3:
                lines.append(f"color {color[0]} {color[1]} {color[2]}")
        elif op.appearance and op.appearance.color:
            c = op.appearance.color
            lines.append(f"color {c[0]} {c[1]} {c[2]}")

        # 8. dict: dict HEXDATA
        dict_data = op.custom_data.get('dict')
        if dict_data:
            lines.append(f"dict {dict_data}")

        # 9. end
        lines.append("end")

        return '\n'.join(lines) + '\n'

    def _build_flags_parts(self, op: Operator) -> List[str]:
        """Build flags key-value pairs for .n file."""
        parts = []

        # Use raw_flags if available for lossless round-trip
        if op.custom_data and 'raw_flags' in op.custom_data:
            raw_flags = op.custom_data['raw_flags']
            for key, value in raw_flags.items():
                parts.append(key)
                parts.append(str(value))
            return parts

        # Fall back to building from Flags object
        if op.flags:
            if op.flags.display:
                parts.append("display")
                parts.append("on")
            if op.flags.render:
                parts.append("render")
                parts.append("on")
            if op.flags.bypass:
                parts.append("bypass")
                parts.append("on")
            if op.flags.lock:
                parts.append("lock")
                parts.append("on")
            if op.flags.viewer:
                parts.append("viewer")
                parts.append("on")
            if op.flags.current:
                parts.append("current")
                parts.append("on")

            # Add TD-specific metadata from custom_data
            if op.custom_data:
                if "parlanguage" in op.custom_data and 'raw_flags' not in op.custom_data:
                    parts.append("parlanguage")
                    parts.append(str(op.custom_data['parlanguage']))

        return parts

    # =========================================================================
    # .parm file generation
    # =========================================================================

    def _generate_parm_content(self, parameters: Dict[str, Any]) -> str:
        """
        Generate .parm file content.

        Format: paramname MODE value [expression]

        Where MODE is:
        - 0: constant value
        - Non-zero (e.g., 17): expression mode with constant fallback
        """
        lines = ['?']

        for param_name, param_value in parameters.items():
            line = self._format_parameter(param_name, param_value)
            if line:
                lines.append(line)

        lines.append('?')
        return '\n'.join(lines) + '\n'

    def _format_parameter(self, name: str, value: Any) -> Optional[str]:
        """Format a single parameter for .parm file."""
        if isinstance(value, ParameterValue):
            return self._format_parameter_value(name, value)
        elif isinstance(value, dict):
            # Multi-component parameter (e.g., {0: "x", 1: "y"})
            # Write each component as separate line
            result_lines = []
            for idx, comp_value in value.items():
                result_lines.append(f"{name} {idx} {comp_value}")
            return '\n'.join(result_lines) if result_lines else None
        else:
            # Simple constant value (mode 0)
            return f"{name} 0 {value}"

    def _format_parameter_value(self, name: str, pv: ParameterValue) -> str:
        """Format ParameterValue object for .parm file."""
        # Get TD mode number
        td_mode = pv.td_mode if pv.td_mode is not None else 0

        if pv.expression and pv.mode.value == 'expression':
            # Expression mode: paramname MODE constant expression
            const_val = pv.value if pv.value is not None else 0
            return f"{name} {td_mode} {const_val} {pv.expression}"
        else:
            # Constant mode: paramname MODE value
            return f"{name} {td_mode} {pv.value}"

    # =========================================================================
    # TOC generation with correct ordering
    # =========================================================================

    def _write_toc(self):
        """
        Write .toc file with correct ordering.

        Ordering rules:
        - .n first, then .cparm, then .parm, then .panel, then others
        - Versioned files: TOC uses "snare.n 2" but disk uses "snare.n.2"
        """
        # If we have original TOC raw lines, use them for perfect round-trip
        if (self.network.lossless_data and
            self.network.lossless_data.toc_raw_lines):
            content = '\n'.join(self.network.lossless_data.toc_raw_lines) + '\n'
            self._write_text(self.toc_path, content)
            if self.verbose:
                print(f"\n[OK] Wrote {self.toc_path} (original TOC preserved)")
            return

        # Otherwise, generate TOC with correct ordering
        toc_lines = self._sort_toc_entries(self.toc_entries)

        # Add header comment
        header = "# 4 0 0 0 1"
        content = header + '\n' + '\n'.join(toc_lines) + '\n'

        self._write_text(self.toc_path, content)

        if self.verbose:
            print(f"\n[OK] Wrote {self.toc_path} ({len(toc_lines)} entries)")

    def _sort_toc_entries(self, entries: List[str]) -> List[str]:
        """
        Sort TOC entries with correct ordering.

        Order:
        1. Metadata files (.build, .start, .root, .grps, .parm, .application)
        2. Per-operator files grouped together:
           - .n first
           - .cparm
           - .parm
           - .panel
           - others (alphabetically)
        """
        # Metadata files always come first in specific order
        metadata_order = ['.build', '.start', '.root', '.grps', '.parm', '.application']
        metadata_entries = []
        operator_entries = []

        for entry in entries:
            if entry in metadata_order:
                metadata_entries.append(entry)
            else:
                operator_entries.append(entry)

        # Sort metadata by predefined order
        sorted_metadata = sorted(
            metadata_entries,
            key=lambda x: metadata_order.index(x) if x in metadata_order else len(metadata_order)
        )

        # Group operator files by base path
        operator_groups: Dict[str, List[str]] = {}
        for entry in operator_entries:
            base_path = self._get_base_path(entry)
            if base_path not in operator_groups:
                operator_groups[base_path] = []
            operator_groups[base_path].append(entry)

        # Sort each group with extension priority
        extension_priority = {'.n': 0, '.cparm': 1, '.parm': 2, '.panel': 3}

        def get_extension_priority(entry: str) -> Tuple[int, str]:
            for ext, priority in extension_priority.items():
                if entry.endswith(ext) or self._entry_has_extension(entry, ext):
                    return (priority, entry)
            return (len(extension_priority), entry)

        sorted_operator_entries = []
        for base_path in sorted(operator_groups.keys()):
            group = operator_groups[base_path]
            sorted_group = sorted(group, key=get_extension_priority)
            sorted_operator_entries.extend(sorted_group)

        return sorted_metadata + sorted_operator_entries

    def _get_base_path(self, entry: str) -> str:
        """Get base path from TOC entry (remove extension and version)."""
        # Handle versioned files (e.g., "snare.n 2" -> "snare")
        parts = entry.rsplit(' ', 1)
        if len(parts) == 2 and parts[1].isdigit():
            entry = parts[0]

        # Remove known extensions
        for ext in ['.n', '.cparm', '.parm', '.panel', '.table', '.text', '.dat']:
            if entry.endswith(ext):
                return entry[:-len(ext)]

        # Remove last extension
        if '.' in entry:
            return entry.rsplit('.', 1)[0]

        return entry

    def _entry_has_extension(self, entry: str, ext: str) -> bool:
        """Check if TOC entry has given extension (handles versioned files)."""
        # Handle versioned files (e.g., "snare.n 2")
        parts = entry.rsplit(' ', 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0].endswith(ext)
        return entry.endswith(ext)


def write_tox_lossless(
    network: TDNetwork,
    output_dir: Path,
    mode: str = "tox",
    verbose: bool = True
) -> Path:
    """
    Convenience function to write TDNetwork to .tox.dir/.toe.dir format.

    Args:
        network: TDNetwork object to write
        output_dir: Parent directory for output
        mode: "tox" or "toe"
        verbose: Print progress messages

    Returns:
        Path to created .toc file
    """
    writer = LosslessWriter(network, verbose=verbose)
    return writer.write(output_dir, mode=mode)


if __name__ == '__main__':
    import json

    print("Lossless Writer - TDNetwork to .tox.dir format")
    print()
    print("Usage:")
    print("  from writers.lossless_writer import LosslessWriter, write_tox_lossless")
    print()
    print("  # Using class")
    print("  writer = LosslessWriter(network)")
    print("  toc_path = writer.write(output_dir, mode='tox')")
    print()
    print("  # Using convenience function")
    print("  toc_path = write_tox_lossless(network, output_dir)")
    print()
    print("Then run: toecollapse <toc_file>")

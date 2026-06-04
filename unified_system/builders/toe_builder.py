"""TOE/TOX Builder - Build .toe/.tox files from TDNetwork JSON.

Supports two modes:
1. LOSSLESS: Perfect round-trip from lossless_data (100% file reconstruction)
2. BASIC: Generate minimal .toe from operators/connections (new networks)

Usage:
    builder = TOEBuilder(network)
    builder.build("output.toe")
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import base64
import shutil
from typing import Dict, List, Any, Optional
from datetime import datetime

from core.models import TDNetwork, Operator, Connection, FormatLayer, OperatorFamily


class TOEBuilder:
    """Build .toe/.tox files from TDNetwork objects."""

    def __init__(self, network: TDNetwork, verbose: bool = True):
        """
        Initialize TOE builder.

        Args:
            network: TDNetwork object
            verbose: Print progress messages
        """
        self.network = network
        self.verbose = verbose
        self.files_written = []

        # Detect mode
        self.is_lossless = (
            network.lossless_data is not None and
            network.lossless_data.toc_order is not None
        )

    def build(self, output_path: Path, mode: str = "toe"):
        """
        Build .toe or .tox file.

        Args:
            output_path: Output file path (e.g. "project.toe")
            mode: "toe" or "tox"

        Returns:
            Path to created .toc file
        """
        output_path = Path(output_path)
        base_name = output_path.stem
        self.mode = mode

        self.output_dir = output_path.parent / f"{base_name}.{mode}.dir"
        self.toc_file = output_path.parent / f"{base_name}.{mode}.toc"

        if self.verbose:
            print(f"\nBuilding {mode.upper()}: {base_name}")
            print("=" * 70)
            print(f"Mode: {'LOSSLESS' if self.is_lossless else 'BASIC'}")
            print(f"Output: {self.output_dir}")

        # Clean up existing output
        if self.output_dir.exists():
            if self.verbose:
                print(f"Removing existing {self.output_dir}")
            shutil.rmtree(self.output_dir)
        if self.toc_file.exists():
            self.toc_file.unlink()

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Build based on mode
        if self.is_lossless:
            self._build_lossless()
        else:
            self._build_basic()

        # Write .toc file
        self._write_toc()

        if self.verbose:
            print()
            print("=" * 70)
            print(f"[BUILD COMPLETE]")
            print("=" * 70)
            print(f"\n[OK] {len(self.network.operators)} operators")
            print(f"[OK] {len(self.network.connections)} connections")
            print(f"[OK] {len(self.files_written)} files written")
            print(f"\nNext step:")
            print(f"  toecollapse {self.toc_file}")

        return self.toc_file

    def _build_lossless(self):
        """Build using lossless data for perfect round-trip."""
        if self.verbose:
            print(f"\nWriting files in original order (LOSSLESS)...")

        toc_order = self.network.lossless_data.toc_order
        toc_disk_paths = self.network.lossless_data.toc_disk_paths or {}
        raw_files = self.network.lossless_data.raw_files or {}

        # Create operator lookup
        operators_by_path = {op.path: op for op in self.network.operators}

        for idx, file_path in enumerate(toc_order, 1):
            if self.verbose and idx % 100 == 0:
                print(f"  Progress: {idx}/{len(toc_order)}")

            # If we have the raw file content, write it exactly (perfect round-trip)
            if file_path in raw_files:
                disk_path = toc_disk_paths.get(file_path, file_path)
                self._write_file_from_data(disk_path, raw_files[file_path])
                continue

            # Metadata files
            if file_path in ['.build', '.start', '.grps', '.root', '.parm', '.application']:
                self._write_metadata_file(file_path, raw_files)

            # Operator .n files
            elif file_path.endswith('.n'):
                self._write_operator_n_file(file_path, operators_by_path)

            # Operator .parm files
            elif file_path.endswith('.parm'):
                self._write_operator_parm_file(file_path, operators_by_path)

            # Extra/raw files
            else:
                self._write_extra_or_raw_file(file_path, operators_by_path, raw_files)

    def _build_basic(self):
        """Build basic .toe from operators/connections (no lossless data)."""
        if self.verbose:
            print(f"\nGenerating basic structure...")

        # Write metadata files
        self._write_basic_metadata()

        # Write operator files
        for op in self.network.operators:
            self._write_basic_operator(op)

        if self.verbose:
            print(f"  [OK] Wrote {len(self.network.operators)} operators")

    def _write_text_file(self, path: Path, content: str):
        """Write text file with Unix line endings (LF only)."""
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)

    # =========================================================================
    # LOSSLESS MODE - Perfect reconstruction
    # =========================================================================

    def _write_metadata_file(self, file_path: str, raw_files: Dict):
        """Write metadata files from lossless data."""
        if file_path == '.build':
            meta = self.network.metadata
            lines = []
            if meta.td_version:
                lines.append(f"version {meta.td_version}")
            if meta.build_number:
                lines.append(f"build {meta.build_number}")
            if meta.build_date:
                lines.append(f"time {meta.build_date}")

            content = '\n'.join(lines) + '\n' if lines else '\n'
            self._write_text_file(self.output_dir / '.build', content)
            self.files_written.append('.build')
            return

        elif file_path == '.start':
            meta = self.network.metadata
            lines = [
                f"cookrate {meta.cookrate}",
                f"realtime {'on' if meta.realtime else 'off'}"
            ]
            content = '\n'.join(lines) + '\n'
            self._write_text_file(self.output_dir / '.start', content)
            self.files_written.append('.start')
            return

        # Other metadata files from raw_files
        if file_path in raw_files:
            self._write_file_from_data(file_path, raw_files[file_path])
        elif self.verbose:
            print(f"  WARNING: Metadata file {file_path} not in raw_files")

    def _write_operator_n_file(self, file_path: str, operators_by_path: Dict):
        """Write operator .n file."""
        # Determine operator path
        op_path = self._file_path_to_operator_path(file_path, '.n')

        if op_path not in operators_by_path:
            if self.verbose:
                print(f"  WARNING: Operator not found: {op_path}")
            return

        op = operators_by_path[op_path]

        # Create directory if needed
        if '/' in file_path:
            (self.output_dir / Path(file_path).parent).mkdir(parents=True, exist_ok=True)

        # Generate .n content
        content = self._generate_n_content(op)
        self._write_text_file(self.output_dir / file_path, content)
        self.files_written.append(file_path)

    def _write_operator_parm_file(self, file_path: str, operators_by_path: Dict):
        """Write operator .parm file."""
        op_path = self._file_path_to_operator_path(file_path, '.parm')

        if op_path not in operators_by_path:
            return

        op = operators_by_path[op_path]

        if op.parameters:
            content = self._generate_parm_content(op.parameters)
            self._write_text_file(self.output_dir / file_path, content)
            self.files_written.append(file_path)

    def _write_extra_or_raw_file(self, file_path: str, operators_by_path: Dict, raw_files: Dict):
        """Write extra file from operator or raw files."""
        # Determine operator path
        base_path = file_path.rsplit('.', 1)[0]
        op_path = '/' + base_path
        extension = file_path.split('.')[-1]

        # Create directory if needed
        if '/' in file_path:
            (self.output_dir / Path(file_path).parent).mkdir(parents=True, exist_ok=True)

        # Try operator extra_files
        if op_path in operators_by_path:
            op = operators_by_path[op_path]
            if extension in op.extra_files:
                file_data = op.extra_files[extension]
                self._write_file_from_data(file_path, file_data)
                return

        # Try raw_files
        if file_path in raw_files:
            self._write_file_from_data(file_path, raw_files[file_path])
        elif self.verbose:
            print(f"  WARNING: File not found: {file_path}")

    def _write_file_from_data(self, file_path: str, file_data: Dict):
        """Write file from stored data (handles text/binary)."""
        content = file_data['content']
        is_binary = file_data.get('is_binary', False)

        full_path = self.output_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if is_binary:
            # Decode base64 and write as binary
            binary_data = base64.b64decode(content)
            full_path.write_bytes(binary_data)
        else:
            # Write as text with Unix line endings
            self._write_text_file(full_path, content)

        self.files_written.append(file_path)

    # =========================================================================
    # BASIC MODE - Generate from scratch
    # =========================================================================

    def _write_basic_metadata(self):
        """Write basic metadata files."""
        # .build (common to tox/toe)
        meta = self.network.metadata
        lines = []
        if meta.td_version:
            lines.append(f"version {meta.td_version}")
        if meta.build_number:
            lines.append(f"build {meta.build_number}")
        else:
            lines.append("build 0")  # Default
        if not meta.td_version:
            # Provide a sane default version string (matches palette sample)
            lines.insert(0, "version 099")

        content = '\n'.join(lines) + '\n' if lines else "build 0\n"
        self._write_text_file(self.output_dir / '.build', content)
        self.files_written.append('.build')

        # For .toe we need runtime metadata; for .tox we keep minimal
        if getattr(self, "mode", "toe") == "toe":
            # .start
            lines = [
                f"cookrate {meta.cookrate}",
                f"realtime {'on' if meta.realtime else 'off'}"
            ]
            content = '\n'.join(lines) + '\n'
            self._write_text_file(self.output_dir / '.start', content)
            self.files_written.append('.start')

            # .root (project root operator)
            root_content = f"{meta.root_comp}\nend\n"
            self._write_text_file(self.output_dir / '.root', root_content)
            self.files_written.append('.root')

            # .grps (groups file)
            grps_content = "-2\n0\n"
            self._write_text_file(self.output_dir / '.grps', grps_content)
            self.files_written.append('.grps')

            # .parm (root parameters)
            parm_content = "?\n?\n"
            self._write_text_file(self.output_dir / '.parm', parm_content)
            self.files_written.append('.parm')

            # .application (UI layout and settings)
            app_content = """
#Desk..
# layout
desk -c *
desk -n pane1 *

#pane1
desk -p /project1 pane1
desk -t neteditor pane1
desk -k 0 pane1
neteditor -c 0 -e 0 -G 0.75 -o 0 -r 1 -P 0.8 -s 0 -w 0 -x 0 -t 1 -d 1 -g 0 -p pane1

winplacement ontop=0 mode=auto posx=0 posy=0 sizex=1024 sizey=768 enable=1 perform.path=/perform perform.start=0
"""
            self._write_text_file(self.output_dir / '.application', app_content)
            self.files_written.append('.application')

    def _write_basic_operator(self, op: Operator):
        """Write operator files (basic mode)."""
        # Convert absolute path to relative file path
        # /project1 -> project1.n (root level)
        # /project1/audio -> project1/audio.n (child)
        relative_path = op.path.lstrip('/')

        # Check if this is a root-level component (no slashes in relative path)
        is_root_level = '/' not in relative_path

        # Build file path
        file_path = f"{relative_path}.n"

        # Create parent directory if needed (but NOT for root-level operators)
        if not is_root_level and '/' in file_path:
            (self.output_dir / Path(file_path).parent).mkdir(parents=True, exist_ok=True)

        # Write .n file
        content = self._generate_n_content(op)
        output_path = self.output_dir / file_path

        # Ensure we're writing to the correct location
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self._write_text_file(output_path, content)
        self.files_written.append(file_path)

        # Write .parm file (even if empty) to mirror TD output
        parm_file_path = f"{relative_path}.parm"
        parm_output_path = self.output_dir / parm_file_path
        parm_output_path.parent.mkdir(parents=True, exist_ok=True)
        parm_content = self._generate_parm_content(op.parameters) if op.parameters else "?\n?\n"
        self._write_text_file(parm_output_path, parm_content)
        self.files_written.append(parm_file_path)

        # Write .panel file for COMP operators
        if op.family == OperatorFamily.COMP:
            panel_file_path = f"{relative_path}.panel"
            panel_output_path = self.output_dir / panel_file_path
            panel_output_path.parent.mkdir(parents=True, exist_ok=True)
            panel_content = """1
3
6
u 0.54
v 0.720528
trueu 0.54
truev 0.720528
screenw 400
screenh 300
"""
            self._write_text_file(panel_output_path, panel_content)
            self.files_written.append(panel_file_path)

        # Write extra files (fixture passthrough, e.g. `.table` / `.text`)
        if op.extra_files:
            for ext, extra_file in op.extra_files.items():
                extra_path = f"{relative_path}.{ext}"
                full_path = self.output_dir / extra_path
                full_path.parent.mkdir(parents=True, exist_ok=True)

                if extra_file.is_binary:
                    binary_data = base64.b64decode(extra_file.content)
                    full_path.write_bytes(binary_data)
                else:
                    self._write_text_file(full_path, extra_file.content)

                self.files_written.append(extra_path)

        # Write text content for DAT operators (tableDAT, textDAT, scriptDAT)
        if op.text is not None:
            # Table DAT uses .table with binary format, others use .text
            is_table_dat = op.op_type.lower().endswith('table') or 'table' in op.op_type.lower()
            if is_table_dat:
                table_path = f"{relative_path}.table"
                full_table_path = self.output_dir / table_path
                full_table_path.parent.mkdir(parents=True, exist_ok=True)
                binary_content = self._generate_binary_table(op.text)
                full_table_path.write_bytes(binary_content)
                self.files_written.append(table_path)
            else:
                text_path = f"{relative_path}.text"
                full_text_path = self.output_dir / text_path
                full_text_path.parent.mkdir(parents=True, exist_ok=True)
                binary_content = self._generate_binary_text(op.text)
                full_text_path.write_bytes(binary_content)
                self.files_written.append(text_path)

    # =========================================================================
    # Content generation
    # =========================================================================

    def _generate_n_content(self, op: Operator) -> str:
        """Generate .n file content from Operator."""
        lines = []

        # Operator type
        lines.append(op.op_type)

        # Position
        if op.position:
            if op.position.viewport:
                vp = op.position.viewport
                lines.append(f"v {vp[0]} {vp[1]} {vp[2]}")
            if op.position.tile:
                tp = op.position.tile
                lines.append(f"tile {tp[0]} {tp[1]} {tp[2]} {tp[3]}")

        # Flags (+ TD-specific metadata)
        flags_parts = []
        if op.flags:
            if op.flags.display:
                flags_parts.append("display on")
            if op.flags.render:
                flags_parts.append("render on")
            if op.flags.bypass:
                flags_parts.append("bypass on")
            if op.flags.lock:
                flags_parts.append("lock on")
            if op.flags.viewer:
                flags_parts.append("viewer on")
            if op.flags.current:
                flags_parts.append("current on")

        if op.custom_data and "parlanguage" in op.custom_data:
            flags_parts.append(f"parlanguage {op.custom_data['parlanguage']}")

        if flags_parts:
            lines.append(f"flags = {' '.join(flags_parts)}")

        # Inputs
        if op.inputs:
            lines.append("inputs")
            lines.append("{")
            for inp in op.inputs:
                # Use src (local name) for inputs
                lines.append(f"{inp.index} \t{inp.src}")
            lines.append("}")

        # Appearance (color)
        if op.appearance and op.appearance.color:
            c = op.appearance.color
            lines.append(f"color {c[0]} {c[1]} {c[2]}")

        lines.append("end")

        return '\n'.join(lines) + '\n'

    def _expand_array_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Expand array parameters into individual indexed/suffixed parameters.

        TouchDesigner uses individual parameters, not arrays:
        - t: [0, 1, 0] → tx: 0, ty: 1, tz: 0
        - fromrange: [0, 1] → fromrange1: 0, fromrange2: 1
        """
        # Expansion rules
        XYZ_PARAMS = {'t', 'r', 's', 'p', 'scale'}  # → tx, ty, tz
        INDEXED_PARAMS = {'fromrange', 'torange', 'const', 'fills'}  # → fromrange1, fromrange2

        expanded = {}

        for param_name, param_value in parameters.items():
            # Check if it's a list/tuple that needs expansion
            if isinstance(param_value, (list, tuple)):
                base_name = param_name.rstrip('0123456789')  # Remove trailing numbers

                if base_name in XYZ_PARAMS and len(param_value) >= 2:
                    # XYZ expansion: t → tx, ty, tz
                    suffixes = ['x', 'y', 'z', 'w'][:len(param_value)]
                    for suffix, val in zip(suffixes, param_value):
                        expanded[f"{base_name}{suffix}"] = val

                elif base_name in INDEXED_PARAMS and len(param_value) >= 2:
                    # Indexed expansion: fromrange → fromrange1, fromrange2
                    for i, val in enumerate(param_value):
                        expanded[f"{base_name}{i+1}"] = val

                elif len(param_value) == 3:
                    # Default: assume RGB or XYZ for 3-element arrays
                    suffixes = ['x', 'y', 'z'] if param_name not in {'color', 'rgb'} else ['r', 'g', 'b']
                    for suffix, val in zip(suffixes, param_value):
                        expanded[f"{param_name}{suffix}"] = val

                elif len(param_value) == 2:
                    # Default: assume indexed for 2-element arrays
                    for i, val in enumerate(param_value):
                        expanded[f"{param_name}{i+1}"] = val
                else:
                    # Can't expand, keep as-is (will likely fail but preserves intent)
                    expanded[param_name] = param_value
            else:
                # Not an array, keep as-is
                expanded[param_name] = param_value

        return expanded

    def _generate_parm_content(self, parameters: Dict[str, Any]) -> str:
        """Generate .parm file content from parameters dict."""
        # First, expand any array parameters
        parameters = self._expand_array_parameters(parameters)

        lines = ['?']

        for param_name, param_value in parameters.items():
            # Handle ParameterValue objects
            from core.models import ParameterValue
            if isinstance(param_value, ParameterValue):
                if param_value.mode.value == 'expression':
                    # Expression mode - TD uses an integer mode plus a constant fallback and expression payload.
                    # Format: paramname <mode:int> <constant> <expression>
                    mode_num = param_value.td_mode if getattr(param_value, "td_mode", None) is not None else 17
                    const_val = param_value.value if param_value.value is not None else 0
                    lines.append(f"{param_name} {mode_num} {const_val} {param_value.expression}")
                else:
                    # Constant mode - usually mode 0, but preserve TD's numeric mode when present.
                    mode_num = param_value.td_mode if getattr(param_value, "td_mode", None) is not None else 0
                    lines.append(f"{param_name} {mode_num} {param_value.value}")

            # Handle dict (multi-component parameters)
            elif isinstance(param_value, dict):
                for index, value in param_value.items():
                    lines.append(f"{param_name} {index} {value}")

            # Handle simple values
            else:
                lines.append(f"{param_name} 0 {param_value}")

        lines.append('?')
        return '\n'.join(lines) + '\n'

    def _write_toc(self):
        """Write .toc file."""
        if self.is_lossless:
            # Prefer exact reproduction if we have raw .toc lines (including headers/comments)
            toc_raw_lines = getattr(self.network.lossless_data, "toc_raw_lines", None)
            if toc_raw_lines:
                content = '\n'.join(toc_raw_lines) + '\n'
                self._write_text_file(self.toc_file, content)
                if self.verbose:
                    print(f"\n[OK] Wrote {self.toc_file} ({len(toc_raw_lines)} entries)")
                return

            # Fallback: use file ordering
            toc_order = self.network.lossless_data.toc_order
            final_toc = [f for f in toc_order if f in self.files_written]
        else:
            # Use files in order written and ensure metadata/root are present first
            if getattr(self, "mode", "toe") == "toe":
                metadata_preface = ['.build', '.start', '.root', '.grps', '.parm', '.application']
            else:
                metadata_preface = ['.build']
            written = list(dict.fromkeys(self.files_written))  # de-dupe preserve order
            final_toc = [f for f in metadata_preface if f in written] + [f for f in written if f not in metadata_preface]

        content = '\n'.join(final_toc) + '\n'
        # Add header line for basic mode to align with TD tox/toc samples
        if not self.is_lossless:
            header = "# 4 0 0 0 1\n"  # Observed in TD-generated .tox .toc
            content = header + content

        self._write_text_file(self.toc_file, content)

        if self.verbose:
            print(f"\n[OK] Wrote {self.toc_file} ({len(final_toc)} entries)")

    # =========================================================================
    # Utilities
    # =========================================================================

    def _generate_binary_text(self, content: str) -> bytes:
        """Generate binary .text file content for DAT operators.

        TD .text binary format (reverse-engineered):
        - "2\\n" (version marker, 2 bytes)
        - uint32 LE = 42 (magic, 4 bytes)
        - uint32 LE = 1 (metadata, 4 bytes each x 4 = 16 bytes)
        - uint16 LE = 2 (type marker, 2 bytes)
        - uint8 = 0 (padding, 1 byte)
        - uint16 BE = content length (2 bytes)
        - UTF-8 encoded content
        Total header: 27 bytes
        """
        import struct
        content_bytes = content.encode('utf-8')
        content_len = len(content_bytes)

        version = b"2\n"                              # 2 bytes
        magic = struct.pack('<I', 42)                 # 4 bytes LE
        metadata = struct.pack('<4I', 1, 1, 1, 1)     # 16 bytes LE
        type_marker = struct.pack('<H', 2)            # 2 bytes LE
        padding = b'\x00'                             # 1 byte
        length_bytes = struct.pack('>H', content_len) # 2 bytes BE

        return version + magic + metadata + type_marker + padding + length_bytes + content_bytes

    def _generate_binary_table(self, content: str) -> bytes:
        """Generate binary .table file content for Table DAT operators.

        TD .table binary format (reverse-engineered from working files):
        - "1\\n*" (version marker + binary indicator, 3 bytes)
        - 3 padding bytes (to 4-byte align)
        - uint32 LE = 1 (unknown field)
        - uint32 LE = num_rows
        - uint32 LE = num_cols
        - uint32 LE = 0 (unknown field)
        - For each cell: type(4) + length(1) + content + padding(3)
        """
        import struct

        # Parse TSV content into rows
        lines = content.strip().split("\n") if content.strip() else [""]
        rows = [line.split("\t") for line in lines]
        num_rows = len(rows)
        num_cols = max(len(row) for row in rows) if rows else 1

        # Build cell data
        cell_data = bytearray()
        for row in rows:
            for col_idx in range(num_cols):
                cell = row[col_idx] if col_idx < len(row) else ""
                cell_bytes = cell.encode("utf-8")
                cell_len = len(cell_bytes)

                # Cell type (2 = string), then length byte, then content, then 3-byte padding
                cell_data.extend(struct.pack("<I", 2))  # type = 2 (string)
                cell_data.append(cell_len)  # length byte
                cell_data.extend(cell_bytes)  # string content
                cell_data.extend(b"\x00\x00\x00")  # 3-byte padding

        # Build header: "1\n*" + 3 padding + 4 uint32 fields
        header = bytearray()
        header.extend(b"1\n*")  # Version line with binary marker
        header.extend(b"\x00\x00\x00")  # 3 padding bytes
        header.extend(struct.pack("<I", 1))  # Unknown field = 1
        header.extend(struct.pack("<I", num_rows))
        header.extend(struct.pack("<I", num_cols))
        header.extend(struct.pack("<I", 0))  # Unknown field = 0

        return bytes(header + cell_data)

    def _file_path_to_operator_path(self, file_path: str, extension: str) -> str:
        """Convert file path to operator path."""
        # project1/noise1.n -> /project1/noise1
        # project1/base/filter1.n -> /project1/base/filter1
        path_without_ext = file_path.replace(extension, '')
        return '/' + path_without_ext


def build_toe_from_json(json_path: Path, output_name: str, verbose: bool = True) -> Path:
    """
    Build .toe from JSON file (convenience function).

    Args:
        json_path: Path to JSON file
        output_name: Output name (without extension)
        verbose: Print progress

    Returns:
        Path to created .toc file
    """
    import json
    from core.format_converter import FormatConverter
    from core.operator_registry import OperatorRegistry

    # Load JSON
    with open(json_path, encoding='utf-8') as f:
        json_data = json.load(f)

    # Convert to TDNetwork if needed
    if 'nodes' in json_data:  # Builder JSON
        registry = OperatorRegistry()
        converter = FormatConverter(registry)
        network = converter.from_builder(json_data)
    else:  # Already TDNetwork-like
        # TODO: Implement proper deserialization
        raise NotImplementedError("Direct TDNetwork deserialization not yet implemented")

    # Build
    builder = TOEBuilder(network, verbose=verbose)
    return builder.build(Path(f"{output_name}.toe"))


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("TOE Builder - Build .toe/.tox files from JSON")
        print()
        print("Usage:")
        print("  python toe_builder.py <input.json> <output_name>")
        print()
        print("Example:")
        print("  python toe_builder.py project.json test_output")
        print()
        print("Creates: test_output.toe.dir/ and test_output.toe.toc")
        print("Then run: toecollapse test_output.toe.toc")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    output_name = sys.argv[2]

    if not json_path.exists():
        print(f"Error: {json_path} not found")
        sys.exit(1)

    try:
        toc_file = build_toe_from_json(json_path, output_name)
        print(f"\n[SUCCESS] Run: toecollapse {toc_file}")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

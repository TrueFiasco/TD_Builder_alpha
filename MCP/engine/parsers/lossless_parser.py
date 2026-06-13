"""Lossless Parser - .toe.dir to Extended JSON with perfect round-trip fidelity.

Migrated from C:/TD_Projects/gpt/toe_to_json_LOSSLESS.py
Adapted to use unified system data models and schema.
"""

import json
import base64
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

import sys
from pathlib import Path as PathLib
sys.path.insert(0, str(PathLib(__file__).parent.parent))

from core.models import (
    TDNetwork, Operator, Connection, Metadata, Position, Flags,
    OperatorFamily, FormatLayer, LosslessData, Statistics, ExtraFile, Input
)
from core.models import ParameterValue, ExpressionLanguage, ParameterMode
from core.operator_registry import OperatorRegistry


class LosslessParser:
    """
    Parse .toe.dir to Extended JSON (Layer 4: Lossless format).

    Captures EVERY file for 100% round-trip fidelity:
    - Reads .toc to get complete file list
    - Captures ALL files (not just .n and .parm)
    - Handles binary files via base64 encoding
    - Preserves exact .toc ordering
    """

    def __init__(
        self,
        toe_dir: Path,
        registry: Optional[OperatorRegistry] = None,
        unwrap_palette: bool = False,
    ):
        """
        Initialize lossless parser.

        Args:
            toe_dir: Path to .toe.dir or .tox.dir directory
            registry: Optional OperatorRegistry for validation
            unwrap_palette: When True, unwrap the `/name/name` palette
                wrapper structure (icon+help wrapper around the inner
                component). Used by the palette-embedding pipeline.
        """
        self.toe_dir = Path(toe_dir)
        self.registry = registry
        self.unwrap_palette = unwrap_palette

        self.operators: Dict[str, Operator] = {}  # Key: path
        self.raw_files: Dict[str, Dict[str, Any]] = {}
        self.toc_order: List[str] = []
        self.toc_raw_lines: List[str] = []
        self.toc_disk_paths: Dict[str, str] = {}
        self.metadata: Optional[Metadata] = None

    def parse(self, verbose: bool = True) -> TDNetwork:
        """
        Parse .toe.dir to TDNetwork (Extended JSON format).

        Args:
            verbose: Print progress messages

        Returns:
            TDNetwork with format_layer="lossless"
        """
        if verbose:
            print(f"Parsing {self.toe_dir} (LOSSLESS MODE)")
            print("=" * 70)

        # Find and parse .toc
        toc_file = self._find_toc_file()
        if not toc_file:
            raise FileNotFoundError(f"No .toc file found for {self.toe_dir}")

        if verbose:
            print(f"Reading: {toc_file}")

        all_files = self._parse_toc(toc_file)

        if verbose:
            print(f"Found {len(all_files)} files in .toc")

        # Parse metadata
        self._parse_metadata()

        # Capture ALL files
        self._capture_all_files(all_files, verbose)

        # Build hierarchy
        self._build_hierarchy()

        # Unwrap palette wrapper if requested (palette TOXs nest the real
        # component inside a /name/name wrapper with icon + help children).
        if self.unwrap_palette:
            self._unwrap_palette_structure(verbose=verbose)

        # Extract connections
        connections = self._extract_connections()

        # Generate statistics
        statistics = self._generate_statistics()

        if verbose:
            print(f"\n[OK] Parsed {len(self.operators)} operators")
            print(f"[OK] Captured {len(self.raw_files)} raw files")

        # Assemble TDNetwork
        network = TDNetwork(
            format_version="2.0.0",
            format_layer=FormatLayer.LOSSLESS,
            metadata=self.metadata,
            operators=list(self.operators.values()),
            connections=connections,
            lossless_data=LosslessData(
                raw_files=self.raw_files,
                toc_order=self.toc_order,
                toc_raw_lines=self.toc_raw_lines,
                toc_disk_paths=self.toc_disk_paths,
            ),
            statistics=statistics
        )

        return network

    def _find_toc_file(self) -> Optional[Path]:
        """Find the .toc file (same level as .toe.dir)."""
        parent = self.toe_dir.parent
        dir_name = self.toe_dir.name

        # Try standard naming
        if dir_name.endswith('.toe.dir'):
            toc_file = parent / f"{dir_name[:-4]}.toc"
            if toc_file.exists():
                return toc_file

        if dir_name.endswith('.tox.dir'):
            toc_file = parent / f"{dir_name[:-4]}.toc"
            if toc_file.exists():
                return toc_file

        if dir_name.endswith('.dir'):
            toc_file = parent / f"{dir_name[:-4]}.toc"
            if toc_file.exists():
                return toc_file

        # Search for any .toc in parent
        for file in parent.glob('*.toc'):
            return file

        return None

    def _parse_toc(self, toc_file: Path) -> List[str]:
        """Parse .toc and preserve raw lines + duplicate filename mapping.

        TouchDesigner `.toc` can include duplicate disambiguators like:
          `project1/audioAnalysis/snare.n 2`

        In expanded `.toe.dir`/`.tox.dir`, those files appear on disk as:
          `project1/audioAnalysis/snare.n.2`
        """
        content = toc_file.read_text(encoding='utf-8')

        toc_raw_lines: List[str] = []
        toc_order: List[str] = []
        toc_disk_paths: Dict[str, str] = {}

        for raw in content.splitlines():
            line = raw.strip()
            if not line:
                continue

            toc_raw_lines.append(line)

            # Header/comment lines are preserved but not treated as files
            if line.startswith('#'):
                continue

            disk_path = self._toc_line_to_disk_path(line)
            toc_order.append(line)
            toc_disk_paths[line] = disk_path

        self.toc_raw_lines = toc_raw_lines
        self.toc_order = toc_order
        self.toc_disk_paths = toc_disk_paths
        return toc_order

    def _toc_line_to_disk_path(self, toc_line: str) -> str:
        """Map a `.toc` entry to the on-disk file name inside `.toe.dir`."""
        parts = toc_line.rsplit(' ', 1)
        if len(parts) == 2 and parts[1].isdigit():
            base_path, dup = parts[0], parts[1]
            return f"{base_path}.{dup}"
        return toc_line

    def _parse_metadata(self):
        """Parse metadata from special files (.build, .start)."""
        # Determine mode
        mode = "toe" if self.toe_dir.name.endswith('.toe.dir') else "tox"
        project_name = self.toe_dir.name.replace('.toe.dir', '').replace('.tox.dir', '').replace('.dir', '')

        metadata_dict = {
            "project_name": project_name,
            "mode": mode,
            "root_comp": ("project1" if mode == "toe" else project_name),
            "cookrate": 60,
            "realtime": True
        }

        # Parse .build
        build_file = self.toe_dir / '.build'
        if build_file.exists():
            for line in build_file.read_text(encoding='utf-8').strip().split('\n'):
                parts = line.split(None, 1)
                if len(parts) == 2:
                    key, value = parts
                    if key == 'version':
                        metadata_dict['td_version'] = value
                    elif key == 'build':
                        metadata_dict['build_number'] = value
                    elif key == 'time':
                        metadata_dict['build_date'] = value

        # Parse .start
        start_file = self.toe_dir / '.start'
        if start_file.exists():
            for line in start_file.read_text(encoding='utf-8').strip().split('\n'):
                parts = line.split()
                if len(parts) >= 2:
                    if parts[0] == 'cookrate':
                        metadata_dict['cookrate'] = int(parts[1])
                    elif parts[0] == 'realtime':
                        metadata_dict['realtime'] = parts[1] == 'on'

        # Add timestamp
        metadata_dict['created_at'] = datetime.now().isoformat()

        self.metadata = Metadata(**metadata_dict)

    def _capture_all_files(self, all_files: List[str], verbose: bool):
        """Capture EVERY file from .toc."""
        if verbose:
            print("\nCapturing files...")

        for idx, file_path in enumerate(all_files, 1):
            if verbose and idx % 100 == 0:
                print(f"  Progress: {idx}/{len(all_files)}")

            if not file_path:
                continue

            disk_path = self.toc_disk_paths.get(file_path) or self._toc_line_to_disk_path(file_path)

            # Metadata files
            if file_path in ['.build', '.start', '.grps', '.root', '.parm', '.application']:
                self._capture_raw_file(file_path, disk_path=disk_path)
                continue

            # Operator definition files
            if file_path.endswith('.n'):
                # Capture raw .n for perfect round-trip
                self._capture_raw_file(file_path, disk_path=disk_path)
                self._parse_operator(file_path, disk_path=disk_path)
                continue

            # Operator parameter files
            if file_path.endswith('.parm'):
                # Capture raw .parm for perfect round-trip
                self._capture_raw_file(file_path, disk_path=disk_path)
                continue

            # All other files
            self._capture_extra_or_raw_file(file_path, disk_path=disk_path)

    def _capture_raw_file(self, toc_path: str, disk_path: Optional[str] = None):
        """Capture a file from `.toc` (store under toc_path, read from disk_path)."""
        disk_path = disk_path or toc_path
        full_path = self.toe_dir / disk_path
        if not full_path.exists():
            return

        try:
            content = full_path.read_text(encoding='utf-8')
            is_binary = False
        except UnicodeDecodeError:
            content = base64.b64encode(full_path.read_bytes()).decode('ascii')
            is_binary = True

        self.raw_files[toc_path] = {
            'content': content,
            'is_binary': is_binary
        }

    def _capture_extra_or_raw_file(self, toc_path: str, disk_path: Optional[str] = None):
        """Capture extra file (attached to operator or standalone)."""
        # Determine if this belongs to an operator
        base_path = toc_path.rsplit('.', 1)[0]
        op_path = '/' + base_path if not base_path.startswith('/') else base_path

        disk_path = disk_path or toc_path
        full_path = self.toe_dir / disk_path
        if not full_path.exists():
            return

        # Read file
        try:
            content = full_path.read_text(encoding='utf-8')
            is_binary = False
        except UnicodeDecodeError:
            content = base64.b64encode(full_path.read_bytes()).decode('ascii')
            is_binary = True

        extension = toc_path.split('.')[-1]
        extra_file = ExtraFile(content=content, is_binary=is_binary)

        # Always store in raw_files for true lossless round-trip
        self.raw_files[toc_path] = {
            'content': content,
            'is_binary': is_binary
        }

        # Try to attach to operator
        if op_path in self.operators:
            self.operators[op_path].extra_files[extension] = extra_file
        # else: already stored in raw_files above

    def _parse_operator(self, node_path: str, disk_path: Optional[str] = None):
        """Parse operator from .n file."""
        disk_path = disk_path or self._toc_line_to_disk_path(node_path)
        node_file = self.toe_dir / disk_path
        if not node_file.exists():
            return

        # Extract operator name/path (ignore duplicate suffix in `.toc` line)
        node_path_for_name = node_path
        dup_parts = node_path_for_name.rsplit(' ', 1)
        if len(dup_parts) == 2 and dup_parts[1].isdigit():
            node_path_for_name = dup_parts[0]

        if '/' in node_path_for_name:
            parts = node_path_for_name.rsplit('/', 1)
            parent_path = '/' + parts[0]
            op_name = parts[1].replace('.n', '')
            full_path = f"{parent_path}/{op_name}"
        else:
            op_name = node_path_for_name.replace('.n', '')
            full_path = f"/{op_name}"
            parent_path = None

        content = node_file.read_text(encoding='utf-8')
        lines = content.strip().split('\n')

        if not lines:
            return

        # Parse operator type
        op_type_line = lines[0].strip()
        if ':' in op_type_line:
            family_str, specific_type = op_type_line.split(':', 1)
            family_str = family_str.upper()
        else:
            family_str = "UNKNOWN"
            specific_type = op_type_line

        # Convert to OperatorFamily
        try:
            family = OperatorFamily(family_str)
        except ValueError:
            # Skip unknown families
            return

        # Create operator
        operator = Operator(
            path=full_path,
            name=op_name,
            family=family,
            type=specific_type.lower(),
            parent=parent_path,
            flags=Flags()
        )

        # Parse .n file content
        i = 1
        viewport_pos = None
        tile_pos = None

        while i < len(lines):
            line = lines[i].strip()
            i += 1

            if not line or line == 'end':
                continue

            if line.startswith('v '):
                parts = line.split()[1:]
                viewport_pos = [float(x) for x in parts]
            elif line.startswith('tile '):
                parts = line.split()[1:]
                tile_pos = [int(x) for x in parts]
            elif line.startswith('flags ='):
                flags_str = line.replace('flags =', '').strip()
                parts = flags_str.split()
                flags_dict = {}
                for j in range(0, len(parts), 2):
                    if j + 1 < len(parts):
                        flags_dict[parts[j]] = parts[j + 1]

                operator.flags = Flags(
                    display=flags_dict.get('display', 'off') == 'on',
                    render=flags_dict.get('render', 'off') == 'on',
                    bypass=flags_dict.get('bypass', 'off') == 'on',
                    lock=flags_dict.get('lock', 'off') == 'on',
                    viewer=flags_dict.get('viewer', 'off') in ('on', '1', 'true', 'True'),
                    current=flags_dict.get('current', 'off') in ('on', '1', 'true', 'True'),
                )

                # Store ALL flags for lossless round-trip (preserves unknown flags like 'activate')
                operator.custom_data['raw_flags'] = flags_dict

                # Preserve important non-flag metadata needed for expression evaluation
                if 'parlanguage' in flags_dict:
                    try:
                        operator.custom_data['parlanguage'] = int(flags_dict['parlanguage'])
                    except ValueError:
                        operator.custom_data['parlanguage'] = flags_dict['parlanguage']
            elif line == 'inputs' or line == 'inputs:':
                i = self._parse_inputs_block(lines, i, operator)
            elif line == 'exports' or line == 'exports:':
                # Parse exports block - list of exported operators/parameters
                i, exports_list = self._parse_exports_block(lines, i)
                if exports_list:
                    operator.custom_data['exports'] = exports_list
            elif line.startswith('dict '):
                # dict line contains hex-encoded pickle data
                dict_data = line[5:].strip()  # Skip "dict " prefix
                if dict_data:
                    operator.custom_data['dict'] = dict_data
            elif line.startswith('color '):
                # color r g b [a] - preserve for round-trip
                color_parts = line[6:].strip().split()
                if color_parts:
                    operator.custom_data['color'] = [float(c) for c in color_parts]

        # Set position if found
        if viewport_pos or tile_pos:
            operator.position = Position(viewport=viewport_pos, tile=tile_pos)

        # Parse parameters (derive `.parm` toc-path from `.n` toc-path)
        parm_toc_path = node_path_for_name.replace('.n', '.parm')
        parm_disk_path = self.toc_disk_paths.get(parm_toc_path) or self._toc_line_to_disk_path(parm_toc_path)
        parm_file = self.toe_dir / parm_disk_path
        if parm_file.exists():
            self._parse_parameters(parm_file, operator)

        self.operators[full_path] = operator

    def _parse_inputs_block(self, lines: List[str], start_idx: int, operator: Operator) -> int:
        """Parse inputs block."""
        i = start_idx
        while i < len(lines) and lines[i].strip() != '{':
            i += 1
        i += 1

        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if line == '}':
                break
            if line and not line.startswith('#'):
                parts = line.split(None, 1)
                if len(parts) >= 2:
                    index = int(parts[0])
                    source = parts[1].strip()
                    operator.inputs.append(Input(
                        index=index,
                        src=source
                    ))
        return i

    def _parse_exports_block(self, lines: List[str], start_idx: int) -> tuple:
        """Parse exports block - returns (new_index, list_of_exports).

        Format:
            exports
            {
            ExportName1
            ExportName2
            }
        """
        i = start_idx
        exports = []

        # Find opening brace
        while i < len(lines) and lines[i].strip() != '{':
            i += 1
        i += 1  # Skip the '{'

        # Read export names until closing brace
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if line == '}':
                break
            if line and not line.startswith('#'):
                exports.append(line)

        return i, exports

    def _parse_parameters(self, parm_file: Path, operator: Operator):
        """Parse parameters from .parm file."""
        content = parm_file.read_text(encoding='utf-8')
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if line == '?' or not line:
                continue

            # .parm line format (observed):
            #   <name> <mode:int> <value>
            #   <name> <mode:int> <const> <expr...>   (expression/bind/export-like modes)
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue

            param_name = parts[0]
            mode_token = parts[1]

            try:
                td_mode = int(mode_token)
            except ValueError:
                # Legacy fallback: treat second token as a component index.
                param_index = mode_token
                param_value = parts[2]
                if param_index != '0':
                    if param_name not in operator.parameters or not isinstance(operator.parameters.get(param_name), dict):
                        operator.parameters[param_name] = {}
                    operator.parameters[param_name][param_index] = param_value
                else:
                    operator.parameters[param_name] = param_value
                continue

            # TD mode 0 is a plain constant; keep it as a raw string for builder friendliness.
            if td_mode == 0:
                operator.parameters[param_name] = parts[2]
                continue

            # Non-zero modes: preserve the TD mode integer and (when present) the expression payload.
            parts4 = line.split(None, 3)
            if len(parts4) >= 4:
                const_val = parts4[2]
                expr_val = parts4[3]
                operator.parameters[param_name] = ParameterValue(
                    value=const_val,
                    expression=expr_val,
                    language=ExpressionLanguage.PYTHON,
                    mode=ParameterMode.EXPRESSION,
                    td_mode=td_mode,
                )
            else:
                operator.parameters[param_name] = ParameterValue(
                    value=parts[2],
                    language=ExpressionLanguage.PYTHON,
                    mode=ParameterMode.CONSTANT,
                    td_mode=td_mode,
                )

    def _build_hierarchy(self):
        """Build parent-child relationships."""
        for op in self.operators.values():
            if op.parent and op.parent in self.operators:
                parent_op = self.operators[op.parent]
                child_path = op.path
                if child_path not in parent_op.children:
                    parent_op.children.append(child_path)

    def _extract_connections(self) -> List[Connection]:
        """Extract connections from operator inputs."""
        connections = []
        for op in self.operators.values():
            for input_obj in op.inputs:
                # Resolve source path
                source_path = input_obj.src
                if not source_path.startswith('/'):
                    # Relative path - resolve to parent
                    if op.parent:
                        source_path = f"{op.parent}/{source_path}"
                    else:
                        source_path = f"/{source_path}"

                connections.append(Connection(
                    source=source_path,
                    target=op.path,
                    target_input=input_obj.index
                ))
        return connections

    def _unwrap_palette_structure(self, verbose: bool = True) -> None:
        """Unwrap the /name/name palette wrapper structure.

        Palette TOX files have an outer wrapper component that contains the
        real component plus 'icon' and 'help' children, e.g.:
            /audioAnalysis/audioAnalysis/...   (the real component)
            /audioAnalysis/icon                (wrapper-level icon)
            /audioAnalysis/help                (wrapper-level help)

        This method flattens to:
            /audioAnalysis/...

        Removes the wrapper-level icon/help operators, hoists the inner
        component to the root path, and remaps every child path,
        toc_order entry, raw_files key, and toc_disk_paths key
        accordingly.

        Ported from `td_builder_workspace/parsers/toe_to_json_LOSSLESS.py`
        (BUG-004: Complete lossless parser for palette TOX embedding).
        """
        # Find the single root operator (path with exactly one slash).
        root_paths = [p for p in self.operators.keys() if p.count('/') == 1]
        if len(root_paths) != 1:
            if verbose:
                print(f"  [UNWRAP] Cannot unwrap: found {len(root_paths)} root operators")
            return

        root_path = root_paths[0]                 # e.g. "/audioAnalysis"
        root_name = root_path[1:]                 # e.g. "audioAnalysis"
        inner_path = f"{root_path}/{root_name}"   # e.g. "/audioAnalysis/audioAnalysis"

        if inner_path not in self.operators:
            if verbose:
                print(f"  [UNWRAP] No inner component at {inner_path}")
            return

        # Identify wrapper-level extras to remove (icon, help).
        wrapper_items = ['icon', 'help']
        removed_paths: List[str] = []
        for item in wrapper_items:
            item_path = f"{root_path}/{item}"
            if item_path in self.operators:
                removed_paths.append(item_path)
                del self.operators[item_path]

        # Remap operators: hoist inner to root, prefix-rewrite descendants,
        # drop the original outer wrapper (replaced by the inner content).
        new_operators: Dict[str, Operator] = {}
        for path, op in self.operators.items():
            if path == root_path:
                inner_op = self.operators[inner_path]
                inner_op.path = root_path
                inner_op.name = root_name
                inner_op.parent = None
                inner_op.children = [c for c in inner_op.children if c not in wrapper_items]
                new_operators[root_path] = inner_op
            elif path == inner_path:
                # Skip — already moved to root_path above.
                continue
            elif path.startswith(inner_path + '/'):
                new_path = root_path + path[len(inner_path):]
                op.path = new_path
                op.parent = new_path.rsplit('/', 1)[0] if '/' in new_path[1:] else None
                new_operators[new_path] = op
            else:
                # Outside the wrapper subtree — keep as-is. Should not normally
                # happen for a well-formed palette but defend anyway.
                new_operators[path] = op
        self.operators = new_operators

        # Remap toc_order. Strip wrapper icon/help entries; rewrite inner-
        # component paths to root level. Normalise duplicate-suffix lines
        # ('snare.n 2') to bare names since we already parsed the .2 file.
        inner_file_prefix = f"{root_name}/{root_name}"   # e.g. "audioAnalysis/audioAnalysis"
        new_toc: List[str] = []
        for entry in self.toc_order:
            if entry.startswith('#'):
                new_toc.append(entry)
                continue

            normalized = re.sub(r' \d+$', '', entry)

            # Skip wrapper icon/help.
            if any(normalized.startswith(f"{root_name}/{item}.") or normalized.startswith(f"{root_name}/{item}/")
                   for item in wrapper_items):
                continue
            # Skip wrapper's own .n / .parm (replaced by inner component's).
            if normalized == f"{root_name}.n" or normalized == f"{root_name}.parm":
                continue
            # Hoist inner component .n / .parm to root.
            if normalized == f"{inner_file_prefix}.n":
                new_toc.append(f"{root_name}.n")
            elif normalized == f"{inner_file_prefix}.parm":
                new_toc.append(f"{root_name}.parm")
            # Hoist inner descendants: 'audioAnalysis/audioAnalysis/foo' → 'audioAnalysis/foo'.
            elif normalized.startswith(inner_file_prefix + '/'):
                new_toc.append(root_name + normalized[len(inner_file_prefix):])
            elif normalized.startswith(inner_file_prefix + '.'):
                new_toc.append(root_name + normalized[len(inner_file_prefix):])
            else:
                new_toc.append(normalized)
        self.toc_order = new_toc

        # Remap raw_files keys to match the new toc_order.
        new_raw_files: Dict[str, Dict[str, Any]] = {}
        for file_path, file_data in self.raw_files.items():
            if any(file_path.startswith(f"{root_name}/{item}.") or file_path.startswith(f"{root_name}/{item}/")
                   for item in wrapper_items):
                continue
            if file_path == f"{root_name}.n" or file_path == f"{root_name}.parm":
                continue
            if file_path == f"{inner_file_prefix}.n":
                new_raw_files[f"{root_name}.n"] = file_data
            elif file_path == f"{inner_file_prefix}.parm":
                new_raw_files[f"{root_name}.parm"] = file_data
            elif file_path.startswith(inner_file_prefix + '/'):
                new_raw_files[root_name + file_path[len(inner_file_prefix):]] = file_data
            elif file_path.startswith(inner_file_prefix + '.'):
                new_raw_files[root_name + file_path[len(inner_file_prefix):]] = file_data
            else:
                new_raw_files[file_path] = file_data
        self.raw_files = new_raw_files

        # Remap toc_disk_paths to match. The values (disk paths) need the
        # same prefix rewrite the keys (toc paths) just got.
        new_disk: Dict[str, str] = {}
        for toc_key, disk_value in self.toc_disk_paths.items():
            normalized_key = re.sub(r' \d+$', '', toc_key)
            if any(normalized_key.startswith(f"{root_name}/{item}.") or normalized_key.startswith(f"{root_name}/{item}/")
                   for item in wrapper_items):
                continue
            if normalized_key == f"{root_name}.n" or normalized_key == f"{root_name}.parm":
                continue
            if normalized_key == f"{inner_file_prefix}.n":
                new_disk[f"{root_name}.n"] = f"{root_name}.n"
            elif normalized_key == f"{inner_file_prefix}.parm":
                new_disk[f"{root_name}.parm"] = f"{root_name}.parm"
            elif normalized_key.startswith(inner_file_prefix + '/') or normalized_key.startswith(inner_file_prefix + '.'):
                new_key = root_name + normalized_key[len(inner_file_prefix):]
                new_disk[new_key] = new_key
            else:
                new_disk[normalized_key] = disk_value
        self.toc_disk_paths = new_disk

        if verbose:
            print(f"  [UNWRAP] Removed wrapper extras: {removed_paths}")
            print(f"  [UNWRAP] Remapped {len(new_operators)} operators")

    def _generate_statistics(self) -> Statistics:
        """Generate network statistics."""
        by_family = {}
        by_type = {}
        max_depth = 0
        total_params = 0

        for op in self.operators.values():
            family = op.family.value
            by_family[family] = by_family.get(family, 0) + 1

            op_type = op.op_type
            by_type[op_type] = by_type.get(op_type, 0) + 1

            depth = op.path.count('/')
            max_depth = max(max_depth, depth)

            total_params += len(op.parameters)

        return Statistics(
            total_operators=len(self.operators),
            total_connections=sum(len(op.inputs) for op in self.operators.values()),
            total_parameters=total_params,
            max_depth=max_depth,
            by_family=by_family,
            by_type=by_type
        )


def parse_toe_lossless(toe_dir: Path, registry: Optional[OperatorRegistry] = None, verbose: bool = True) -> TDNetwork:
    """
    Convenience function to parse .toe.dir to TDNetwork (lossless).

    Args:
        toe_dir: Path to .toe.dir or .tox.dir
        registry: Optional OperatorRegistry
        verbose: Print progress

    Returns:
        TDNetwork with lossless data
    """
    parser = LosslessParser(toe_dir, registry)
    return parser.parse(verbose=verbose)

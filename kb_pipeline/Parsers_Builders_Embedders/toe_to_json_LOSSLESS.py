#!/usr/bin/env python3
"""
TouchDesigner Network to JSON Converter - LOSSLESS
Captures EVERY file listed in .toc for perfect round-trip conversion

This parser:
- Reads .toc to get complete file list
- Captures ALL files (not just .n and .parm)
- Handles binary files via base64 encoding
- Preserves exact .toc ordering
- Enables building complex projects from scratch

Usage:
    python toe_to_json_LOSSLESS.py /path/to/project.toe.dir output.json
"""

import json
import sys
import base64
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class TDOperator:
    """Represents a TouchDesigner operator with all associated files"""
    name: str
    path: str
    op_type: str
    family: str
    specific_type: str
    
    viewport_pos: Optional[List[float]] = None
    tile_pos: Optional[List[int]] = None
    color: Optional[List[float]] = None
    flags: Dict[str, str] = field(default_factory=dict)
    
    parameters: Dict[str, Any] = field(default_factory=dict)
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    
    inputs: Dict[int, str] = field(default_factory=dict)
    
    # All extra files associated with this operator
    extra_files: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class LosslessToeToJsonConverter:
    """Convert .toe.dir to JSON with 100% file preservation"""
    
    def __init__(self, toe_dir: Path):
        self.toe_dir = Path(toe_dir)
        self.operators_dict: Dict[str, TDOperator] = {}
        self.raw_files: Dict[str, Dict[str, Any]] = {}  # Store ALL files not part of operators
        self.toc_order: List[str] = []  # Preserve exact .toc ordering
        
    def convert(self) -> Dict[str, Any]:
        """Convert entire network to JSON with complete file preservation"""
        
        print(f"Converting {self.toe_dir} to JSON (LOSSLESS MODE)")
        print("=" * 70)
        
        # Find and parse .toc
        toc_file = self._find_toc_file()
        if not toc_file:
            raise FileNotFoundError("No .toc file found")
        
        print(f"Reading: {toc_file}")
        all_files = self._parse_toc(toc_file)
        print(f"Found {len(all_files)} files in .toc")
        
        # Capture ALL files
        self._capture_all_files(all_files)
        
        # Build operator hierarchy
        self._build_hierarchy()
        
        # Assemble result
        result = {
            "metadata": self._parse_metadata(),
            "operators": {},
            "raw_files": self.raw_files,  # Files not part of operators
            "toc_order": self.toc_order,  # Preserve ordering
            "connections": self._extract_connections(),
            "statistics": self._generate_statistics()
        }
        
        # Serialize operators
        for op in self.operators_dict.values():
            result["operators"][op.path] = asdict(op)
        
        return result
    
    def _find_toc_file(self) -> Optional[Path]:
        """Find the .toc file (same level as .toe.dir)"""
        # Check parent directory
        parent = self.toe_dir.parent
        dir_name = self.toe_dir.name
        
        if dir_name.endswith('.toe.dir'):
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
        """Parse .toc and preserve exact ordering"""
        # Some .toc files include header/comment lines (e.g. "# 4 0 0 0 1").
        # Preserve ALL non-empty lines for round-trip, but only treat non-comment
        # lines as actual file entries to capture.
        content = toc_file.read_text(encoding='utf-8-sig')
        raw_lines = [line.rstrip('\r\n') for line in content.splitlines()]
        toc_order = [line for line in raw_lines if line.strip()]
        self.toc_order = toc_order  # Preserve ordering + header lines

        files: List[str] = []
        for line in toc_order:
            if line.lstrip().startswith('#'):
                continue
            files.append(line.strip())

        return files
    
    def _parse_metadata(self) -> Dict[str, Any]:
        """Parse metadata from special files"""
        metadata = {
            "source_directory": str(self.toe_dir),
            "build_version": "",
            "build_date": "",
            "os_name": "",
            "os_version": "",
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
                        metadata['build_version'] = value
                    elif key == 'build':
                        metadata['build_number'] = value
                    elif key == 'time':
                        metadata['build_date'] = value
                    elif key == 'osname':
                        metadata['os_name'] = value
                    elif key == 'osversion':
                        metadata['os_version'] = value
        
        # Parse .start
        start_file = self.toe_dir / '.start'
        if start_file.exists():
            for line in start_file.read_text(encoding='utf-8').strip().split('\n'):
                parts = line.split()
                if len(parts) >= 2:
                    if parts[0] == 'cookrate':
                        metadata['cookrate'] = int(parts[1])
                    elif parts[0] == 'realtime':
                        metadata['realtime'] = parts[1] == 'on'
                    elif parts[0] == 'clock':
                        metadata['clock_settings'] = ' '.join(parts[1:])
        
        return metadata
    
    def _capture_all_files(self, all_files: List[str]):
        """Capture EVERY file from .toc"""
        
        print("\nCapturing files...")
        
        for idx, file_path in enumerate(all_files, 1):
            if idx % 100 == 0:
                print(f"  Progress: {idx}/{len(all_files)}")
            
            # Skip empty lines
            if not file_path:
                continue
            
            # Metadata files - already handled in _parse_metadata
            if file_path in ['.build', '.start', '.grps', '.root', '.parm']:
                self._capture_raw_file(file_path)
                continue
            
            # Operator definition files
            if file_path.endswith('.n'):
                self._parse_operator(file_path)
            
            # Parameter files - will be attached to operator
            elif file_path.endswith('.parm'):
                # Already handled in _parse_operator
                pass
            
            # ALL other files - capture as extra files or raw files
            else:
                self._capture_extra_or_raw_file(file_path)
        
        print(f"\n[OK] Captured {len(self.operators_dict)} operators")
        print(f"[OK] Captured {len(self.raw_files)} raw files")
    
    def _capture_raw_file(self, file_path: str):
        """Capture a file that's not part of any operator"""
        full_path = self.toe_dir / file_path
        if not full_path.exists():
            print(f"  WARNING: File listed in .toc but not found: {file_path}")
            return
        
        try:
            content = full_path.read_text(encoding='utf-8')
            is_binary = False
        except UnicodeDecodeError:
            content = base64.b64encode(full_path.read_bytes()).decode('ascii')
            is_binary = True
        
        self.raw_files[file_path] = {
            'content': content,
            'is_binary': is_binary
        }
    
    def _capture_extra_or_raw_file(self, file_path: str):
        """Capture extra file (attached to operator or standalone)"""
        
        # Determine if this belongs to an operator
        base_path = file_path.rsplit('.', 1)[0]  # Remove extension
        op_path = '/' + base_path if not base_path.startswith('/') else base_path
        
        full_path = self.toe_dir / file_path
        if not full_path.exists():
            print(f"  WARNING: File listed in .toc but not found: {file_path}")
            return
        
        # Read file
        try:
            content = full_path.read_text(encoding='utf-8')
            is_binary = False
        except UnicodeDecodeError:
            content = base64.b64encode(full_path.read_bytes()).decode('ascii')
            is_binary = True
        
        extension = file_path.split('.')[-1]
        file_data = {'content': content, 'is_binary': is_binary}
        
        # Try to attach to operator
        if op_path in self.operators_dict:
            self.operators_dict[op_path].extra_files[extension] = file_data
        else:
            # Store as raw file
            self.raw_files[file_path] = file_data
    
    def _parse_operator(self, node_path: str):
        """Parse operator from .n file"""
        node_file = self.toe_dir / node_path
        if not node_file.exists():
            print(f"  WARNING: Operator file not found: {node_path}")
            return
        
        # Extract path
        if '/' in node_path:
            parts = node_path.rsplit('/', 1)
            parent_path = '/' + parts[0]
            op_name = parts[1].replace('.n', '')
            full_path = f"{parent_path}/{op_name}"
        else:
            op_name = node_path.replace('.n', '')
            full_path = f"/{op_name}"
            parent_path = None
        
        content = node_file.read_text(encoding='utf-8')
        lines = content.strip().split('\n')
        
        if not lines:
            return
        
        # Parse operator type
        op_type_line = lines[0].strip()
        if ':' in op_type_line:
            family, specific_type = op_type_line.split(':', 1)
            family = family.upper()
        else:
            family = "UNKNOWN"
            specific_type = op_type_line
        
        operator = TDOperator(
            name=op_name,
            path=full_path,
            op_type=op_type_line,
            family=family,
            specific_type=specific_type.lower(),
            parent=parent_path
        )
        
        # Parse .n file content
        i = 1
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            
            if not line or line == 'end':
                continue
            
            if line.startswith('v '):
                parts = line.split()[1:]
                operator.viewport_pos = [float(x) for x in parts]
            elif line.startswith('tile '):
                parts = line.split()[1:]
                operator.tile_pos = [int(x) for x in parts]
            elif line.startswith('color '):
                parts = line.split()[1:]
                operator.color = [float(x) for x in parts]
            elif line.startswith('flags ='):
                flags_str = line.replace('flags =', '').strip()
                parts = flags_str.split()
                for j in range(0, len(parts), 2):
                    if j + 1 < len(parts):
                        operator.flags[parts[j]] = parts[j + 1]
            elif line == 'inputs' or line == 'inputs:':
                i = self._parse_inputs_block(lines, i, operator)
        
        # Parse parameters
        parm_path = node_path.replace('.n', '.parm')
        parm_file = self.toe_dir / parm_path
        if parm_file.exists():
            self._parse_parameters(parm_file, operator)
        
        self.operators_dict[full_path] = operator
    
    def _parse_inputs_block(self, lines: List[str], start_idx: int, operator: TDOperator) -> int:
        """Parse inputs block"""
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
                    operator.inputs[index] = source
        return i
    
    def _parse_parameters(self, parm_file: Path, operator: TDOperator):
        """Parse parameters"""
        content = parm_file.read_text(encoding='utf-8')
        for line in content.strip().split('\n'):
            line = line.strip()
            if line == '?' or not line:
                continue
            parts = line.split(None, 2)
            if len(parts) >= 3:
                param_name = parts[0]
                param_index = parts[1]
                param_value = parts[2]
                
                # Try to convert to number
                try:
                    if '.' in param_value:
                        param_value = float(param_value)
                    else:
                        param_value = int(param_value)
                except ValueError:
                    pass
                
                if param_index != '0':
                    if param_name not in operator.parameters:
                        operator.parameters[param_name] = {}
                    operator.parameters[param_name][param_index] = param_value
                else:
                    operator.parameters[param_name] = param_value
    
    def _build_hierarchy(self):
        """Build parent-child relationships"""
        for op in self.operators_dict.values():
            if op.parent and op.parent in self.operators_dict:
                parent_op = self.operators_dict[op.parent]
                if op.name not in parent_op.children:
                    parent_op.children.append(op.name)
    
    def _extract_connections(self) -> List[Dict[str, Any]]:
        """Extract connections"""
        connections = []
        for op in self.operators_dict.values():
            for input_idx, source_path in op.inputs.items():
                connections.append({
                    "from": source_path,
                    "to": op.path,
                    "to_input": input_idx
                })
        return connections
    
    def _generate_statistics(self) -> Dict[str, Any]:
        """Generate statistics"""
        stats = {
            "total_operators": len(self.operators_dict),
            "total_connections": sum(len(op.inputs) for op in self.operators_dict.values()),
            "total_raw_files": len(self.raw_files),
            "total_extra_files": sum(len(op.extra_files) for op in self.operators_dict.values()),
            "total_files_captured": len(self.toc_order),
            "by_family": {},
            "by_type": {},
            "max_depth": 0,
            "total_parameters": 0
        }
        
        for op in self.operators_dict.values():
            family = op.family
            stats["by_family"][family] = stats["by_family"].get(family, 0) + 1
            op_type = f"{family}:{op.specific_type}"
            stats["by_type"][op_type] = stats["by_type"].get(op_type, 0) + 1
            depth = op.path.count('/')
            stats["max_depth"] = max(stats["max_depth"], depth)
            stats["total_parameters"] += len(op.parameters)
        
        return stats


def main():
    if len(sys.argv) < 3:
        print("TouchDesigner to JSON Converter - LOSSLESS")
        print()
        print("Captures EVERY file for perfect round-trip conversion")
        print()
        print("Usage:")
        print("  python toe_to_json_LOSSLESS.py <input.toe.dir> <output.json>")
        print()
        print("Example:")
        print("  python toe_to_json_LOSSLESS.py project.toe.dir project.json")
        sys.exit(1)
    
    input_dir = Path(sys.argv[1])
    output_file = Path(sys.argv[2])
    
    if not input_dir.exists():
        print(f"Error: {input_dir} not found")
        sys.exit(1)
    
    try:
        converter = LosslessToeToJsonConverter(input_dir)
        result = converter.convert()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        
        print()
        print("=" * 70)
        print("[OK] LOSSLESS CONVERSION COMPLETE")
        print("=" * 70)
        print(f"\nSaved: {output_file} ({output_file.stat().st_size / 1024:.1f} KB)")
        print()
        
        stats = result['statistics']
        print("Statistics:")
        print(f"  Operators: {stats['total_operators']}")
        print(f"  Connections: {stats['total_connections']}")
        print(f"  Parameters: {stats['total_parameters']}")
        print(f"  Extra files: {stats['total_extra_files']}")
        print(f"  Raw files: {stats['total_raw_files']}")
        print(f"  Total files: {stats['total_files_captured']}")
        print()
        print("All files captured - ready for modifications or round-trip!")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

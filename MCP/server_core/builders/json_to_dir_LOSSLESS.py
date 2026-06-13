#!/usr/bin/env python3
"""
JSON to TouchDesigner .dir Converter - LOSSLESS (LINE ENDING FIX)
Reconstructs EVERY file for perfect round-trip conversion

CRITICAL FIX: Uses Unix line endings (LF) not Windows (CRLF)

Usage:
    python json_to_dir_LOSSLESS.py input.json output_name
"""

import json
import sys
import base64
from pathlib import Path
from typing import Dict, List, Any


class LosslessJsonToToeConverter:
    """Convert JSON to .dir format with 100% file reconstruction"""

    def __init__(self, json_path: Path, base_name: str):
        self.json_path = Path(json_path)
        self.base_name = base_name
        self.output_dir = Path(f"{base_name}.dir")
        self.toc_file = Path(f"{base_name}.toc")

        print(f"Loading: {json_path}")
        with open(json_path, encoding='utf-8') as f:
            self.network = json.load(f)

        self.files_written = []

        # Case collision handling: maps operator path -> version suffix (or None)
        self.version_suffixes = {}
        self._detect_case_collisions()

    def _detect_case_collisions(self):
        """Detect operators that would collide on case-insensitive filesystems.

        On Windows/macOS, 'Snare.n' and 'snare.n' are the same file.
        TouchDesigner handles this with version suffixes: 'snare.n 2' -> 'snare.n.2'
        """
        operators = self.network.get('operators', {})

        # Group operators by parent directory
        by_parent = {}
        for op_path in operators:
            parts = op_path.rsplit('/', 1)
            if len(parts) == 2:
                parent, name = parts
            else:
                parent = ''
                name = op_path.lstrip('/')

            if parent not in by_parent:
                by_parent[parent] = []
            by_parent[parent].append((name, op_path))

        # Find case collisions within each parent
        collision_count = 0
        for parent, ops in by_parent.items():
            # Group by lowercase name
            by_lower = {}
            for name, op_path in ops:
                lower = name.lower()
                if lower not in by_lower:
                    by_lower[lower] = []
                by_lower[lower].append((name, op_path))

            # Assign version suffixes to colliding names
            for lower, group in by_lower.items():
                if len(group) > 1:
                    # Sort to ensure consistent ordering (original case first, then alphabetically)
                    group.sort(key=lambda x: (x[0].lower() != x[0], x[0]))

                    collision_count += len(group)
                    print(f"  [COLLISION] Case collision detected: {[g[0] for g in group]} in {parent or '/'}")

                    # First one gets no suffix, subsequent ones get version 2, 3, etc.
                    for idx, (name, op_path) in enumerate(group):
                        if idx == 0:
                            self.version_suffixes[op_path] = None
                        else:
                            self.version_suffixes[op_path] = idx + 1
                            print(f"    -> {name} will use version suffix .{idx + 1}")

        if collision_count > 0:
            print(f"\n[INFO] Found {collision_count} operators with case collisions")
        else:
            print("[OK] No case collisions detected")

    def _get_versioned_paths(self, op_path: str, extension: str) -> tuple:
        """Get disk path and TOC entry for an operator file, handling version suffixes.

        Returns (disk_path, toc_entry) tuple.
        Example: op_path='/audioAnalysis/snare', extension='n', version=2
                 -> ('audioAnalysis/snare.n.2', 'audioAnalysis/snare.n 2')
        """
        # Convert op_path to relative file path
        rel_path = op_path.lstrip('/') + '.' + extension

        version = self.version_suffixes.get(op_path)
        if version:
            disk_path = f"{rel_path}.{version}"
            toc_entry = f"{rel_path} {version}"
        else:
            disk_path = rel_path
            toc_entry = rel_path

        return (disk_path, toc_entry)

    def convert(self):
        """Convert JSON to .dir with complete file reconstruction"""
        
        print(f"\nConverting to {self.output_dir} (LOSSLESS MODE)")
        print("=" * 70)
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Write ALL files in order
        self._write_all_files()
        
        # Write .toc with preserved ordering
        self._write_toc()
        
        print()
        print("=" * 70)
        print("[OK] LOSSLESS RECONSTRUCTION COMPLETE")
        print("=" * 70)
        
        stats = self.network['statistics']
        print(f"\n[OK] {stats['total_operators']} operators")
        print(f"[OK] {stats['total_connections']} connections")
        print(f"[OK] {stats['total_raw_files']} raw files")
        print(f"[OK] {stats['total_extra_files']} extra files")
        print(f"[OK] {len(self.files_written)} total files written")
        print()
        print("Next step:")
        # toecollapse expects a base filename; it will read <base>.dir and <base>.toc
        print(f"  toecollapse {self.base_name}")
    
    def _write_text_file(self, path: Path, content: str):
        """Write text file with Unix line endings (LF only)"""
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
    
    def _write_all_files(self):
        """Write all files in the order they appeared in original .toc"""

        toc_order = self.network.get('toc_order', [])
        operators = self.network['operators']
        raw_files = self.network.get('raw_files', {})

        # Build mapping from original TOC entry to operator path
        # This handles versioned entries like 'snare.n 2' -> '/audioAnalysis/snare'
        toc_to_op = self._build_toc_to_operator_map(toc_order, operators)

        print(f"\nWriting {len(toc_order)} files...")

        for idx, file_path in enumerate(toc_order, 1):
            if idx % 100 == 0:
                print(f"  Progress: {idx}/{len(toc_order)}")

            # Metadata files
            if file_path in ['.build', '.start', '.grps', '.root', '.parm', '.application']:
                self._write_metadata_file(file_path)

            # Operator files
            elif file_path.endswith('.n') or self._is_versioned_n_file(file_path):
                self._write_operator_n_file(file_path, operators, toc_to_op)

            # Parameter files
            elif file_path.endswith('.parm') or self._is_versioned_parm_file(file_path):
                self._write_operator_parm_file(file_path, operators, toc_to_op)

            # Extra/raw files
            else:
                self._write_extra_or_raw_file(file_path, operators, raw_files, toc_to_op)

    def _is_versioned_n_file(self, file_path: str) -> bool:
        """Check if file is a versioned .n file like 'snare.n 2'"""
        import re
        return bool(re.match(r'.*\.n \d+$', file_path))

    def _is_versioned_parm_file(self, file_path: str) -> bool:
        """Check if file is a versioned .parm file like 'snare.parm 2'"""
        import re
        return bool(re.match(r'.*\.parm \d+$', file_path))

    def _build_toc_to_operator_map(self, toc_order: List[str], operators: Dict) -> Dict[str, str]:
        """Build mapping from TOC entries to operator paths.

        Handles versioned entries like 'audioAnalysis/snare.n 2' -> '/audioAnalysis/snare'
        """
        import re
        toc_to_op = {}

        for toc_entry in toc_order:
            # Skip non-operator files
            if not (toc_entry.endswith('.n') or re.match(r'.*\.n \d+$', toc_entry)):
                continue

            # Extract operator path from TOC entry
            # Remove version suffix and extension
            clean = re.sub(r' \d+$', '', toc_entry)  # 'snare.n 2' -> 'snare.n'
            clean = re.sub(r'\.n$', '', clean)        # 'snare.n' -> 'snare'
            op_path = '/' + clean

            if op_path in operators:
                toc_to_op[toc_entry] = op_path

        return toc_to_op
    
    def _write_metadata_file(self, file_path: str):
        """Write metadata files (.build, .start, .grps, .root, .parm, .application)"""
        
        if file_path == '.build':
            meta = self.network['metadata']
            lines = []
            if meta.get('build_version'):
                lines.append(f"version {meta['build_version']}")
            if meta.get('build_number'):
                lines.append(f"build {meta['build_number']}")
            if meta.get('build_date'):
                lines.append(f"time {meta['build_date']}")
            if meta.get('os_name'):
                lines.append(f"osname {meta['os_name']}")
            if meta.get('os_version'):
                lines.append(f"osversion {meta['os_version']}")
            
            content = '\n'.join(lines) + '\n'
            self._write_text_file(self.output_dir / '.build', content)
            self.files_written.append('.build')
            return
        
        elif file_path == '.start':
            meta = self.network['metadata']
            lines = [
                f"cookrate {meta.get('cookrate', 60)}",
                f"realtime {'on' if meta.get('realtime', True) else 'off'}"
            ]
            if meta.get('clock_settings'):
                lines.append(f"clock {meta['clock_settings']}")
            
            content = '\n'.join(lines) + '\n'
            self._write_text_file(self.output_dir / '.start', content)
            self.files_written.append('.start')
            return
        
        # Other metadata files (.grps, .root, .parm, .application) come from raw_files
        raw_files = self.network.get('raw_files', {})
        if file_path in raw_files:
            self._write_file_from_data(file_path, raw_files[file_path])
            self.files_written.append(file_path)
        else:
            print(f"  WARNING: Metadata file {file_path} not in raw_files")
    
    def _write_operator_n_file(self, toc_entry: str, operators: Dict, toc_to_op: Dict):
        """Write operator .n file, handling version suffixes for case collisions"""
        import re

        # Get operator path from mapping, or calculate from TOC entry
        if toc_entry in toc_to_op:
            op_path = toc_to_op[toc_entry]
        else:
            # Calculate from TOC entry (remove version suffix and extension)
            clean = re.sub(r' \d+$', '', toc_entry)
            if '/' in clean:
                parts = clean.rsplit('/', 1)
                op_path = '/' + parts[0] + '/' + parts[1].replace('.n', '')
            else:
                op_path = '/' + clean.replace('.n', '')

        if op_path not in operators:
            print(f"  WARNING: Operator not found in JSON: {op_path}")
            return

        op = operators[op_path]

        # Get versioned paths (handles case collisions)
        disk_path, new_toc_entry = self._get_versioned_paths(op_path, 'n')

        # Create directory if needed
        if '/' in disk_path:
            (self.output_dir / Path(disk_path).parent).mkdir(parents=True, exist_ok=True)

        # Generate .n content
        content = self._generate_n_content(op)
        self._write_text_file(self.output_dir / disk_path, content)
        self.files_written.append(new_toc_entry)
    
    def _write_operator_parm_file(self, toc_entry: str, operators: Dict, toc_to_op: Dict):
        """Write operator .parm file, handling version suffixes for case collisions"""
        import re

        # Get operator path from mapping, or calculate from TOC entry
        # First try to find the corresponding .n entry in toc_to_op
        n_entry = re.sub(r'\.parm( \d+)?$', '.n\\1', toc_entry)
        if n_entry in toc_to_op:
            op_path = toc_to_op[n_entry]
        else:
            # Calculate from TOC entry
            clean = re.sub(r' \d+$', '', toc_entry)
            if '/' in clean:
                parts = clean.rsplit('/', 1)
                op_path = '/' + parts[0] + '/' + parts[1].replace('.parm', '')
            else:
                op_path = '/' + clean.replace('.parm', '')

        if op_path not in operators:
            return

        op = operators[op_path]

        if op.get('parameters'):
            # Get versioned paths (handles case collisions)
            disk_path, new_toc_entry = self._get_versioned_paths(op_path, 'parm')

            # Create directory if needed
            if '/' in disk_path:
                (self.output_dir / Path(disk_path).parent).mkdir(parents=True, exist_ok=True)

            content = self._generate_parm_content(op['parameters'])
            self._write_text_file(self.output_dir / disk_path, content)
            self.files_written.append(new_toc_entry)
    
    def _write_extra_or_raw_file(self, toc_entry: str, operators: Dict, raw_files: Dict, toc_to_op: Dict):
        """Write extra file (from operator or raw files), handling version suffixes"""
        import re

        # Handle versioned entries like 'snare.cparm 2'
        clean_entry = re.sub(r' \d+$', '', toc_entry)

        # Determine if this belongs to an operator
        base_path = clean_entry.rsplit('.', 1)[0]
        op_path = '/' + base_path
        extension = clean_entry.split('.')[-1]

        # Try to find the operator (may need to check case-insensitive match)
        actual_op_path = None
        if op_path in operators:
            actual_op_path = op_path
        else:
            # Check toc_to_op for a matching .n entry
            for n_entry, mapped_path in toc_to_op.items():
                mapped_base = mapped_path.lstrip('/')
                if mapped_base.lower() == base_path.lower():
                    actual_op_path = mapped_path
                    break

        # Try to get from operator
        if actual_op_path and actual_op_path in operators:
            op = operators[actual_op_path]
            if extension in op.get('extra_files', {}):
                file_data = op['extra_files'][extension]

                # Get versioned paths
                disk_path, new_toc_entry = self._get_versioned_paths(actual_op_path, extension)

                # Create directory if needed
                if '/' in disk_path:
                    (self.output_dir / Path(disk_path).parent).mkdir(parents=True, exist_ok=True)

                self._write_file_from_data(disk_path, file_data)
                self.files_written.append(new_toc_entry)
                return

        # Get from raw files (use original toc_entry as key)
        if toc_entry in raw_files:
            # Create directory if needed
            if '/' in clean_entry:
                (self.output_dir / Path(clean_entry).parent).mkdir(parents=True, exist_ok=True)
            self._write_file_from_data(clean_entry, raw_files[toc_entry])
            self.files_written.append(clean_entry)
        elif clean_entry in raw_files:
            if '/' in clean_entry:
                (self.output_dir / Path(clean_entry).parent).mkdir(parents=True, exist_ok=True)
            self._write_file_from_data(clean_entry, raw_files[clean_entry])
            self.files_written.append(clean_entry)
        else:
            print(f"  WARNING: File not found in JSON: {toc_entry}")
    
    def _write_file_from_data(self, file_path: str, file_data: Dict):
        """Write file from stored data (handles text/binary)

        Note: Caller is responsible for adding to files_written with correct TOC entry.
        """
        content = file_data['content']
        is_binary = file_data.get('is_binary', False)

        full_path = self.output_dir / file_path

        if is_binary:
            # Decode base64 and write as binary
            binary_data = base64.b64decode(content)
            full_path.write_bytes(binary_data)
        else:
            # Write as text with Unix line endings
            self._write_text_file(full_path, content)
    
    def _generate_n_content(self, op: Dict[str, Any]) -> str:
        """Generate .n file content"""
        lines = []

        lines.append(op['op_type'])

        # Write tags if present (e.g., "tags 0 1 TDBasicWidget")
        if op.get('tags'):
            lines.append(f"tags {op['tags']}")

        if op.get('viewport_pos'):
            vp = op['viewport_pos']
            lines.append(f"v {vp[0]} {vp[1]} {vp[2]}")

        if op.get('tile_pos'):
            tp = op['tile_pos']
            lines.append(f"tile {tp[0]} {tp[1]} {tp[2]} {tp[3]}")

        if op.get('flags'):
            flags_parts = []
            for key, value in op['flags'].items():
                flags_parts.append(f"{key} {value}")
            if flags_parts:
                lines.append(f"flags = {' '.join(flags_parts)}")

        if op.get('inputs'):
            lines.append("inputs")
            lines.append("{")
            inputs = op['inputs']
            if isinstance(inputs, dict):
                for input_idx in sorted(inputs.keys(), key=lambda x: int(x)):
                    source_path = inputs[input_idx]
                    lines.append(f"{input_idx} \t{source_path}")
            lines.append("}")

        if op.get('color'):
            c = op['color']
            lines.append(f"color {c[0]} {c[1]} {c[2]}")

        # Write dock reference (docked operator relationship)
        if op.get('dock'):
            lines.append(f"dock {op['dock']}")

        # Write exports block (custom parameter exports)
        if op.get('exports'):
            lines.append("exports")
            lines.append("{")
            for export_line in op['exports']:
                lines.append(export_line)
            lines.append("}")

        # Write dict data (hex-encoded instance data)
        if op.get('dict_data'):
            lines.append(f"dict {op['dict_data']}")

        lines.append("end")

        return '\n'.join(lines) + '\n'
    
    def _generate_parm_content(self, parameters: Dict[str, Any]) -> str:
        """Generate .parm file content"""
        lines = ['?']
        
        for param_name, param_value in parameters.items():
            if isinstance(param_value, dict):
                for index, value in param_value.items():
                    lines.append(f"{param_name} {index} {value}")
            else:
                lines.append(f"{param_name} 0 {param_value}")
        
        lines.append('?')
        return '\n'.join(lines) + '\n'
    
    def _write_toc(self):
        """Write .toc file with preserved ordering, handling version suffixes"""
        import re

        # Use original .toc ordering as template
        toc_order = self.network.get('toc_order', [])

        # Build mapping from base entry (without version) to actual written entry
        # e.g., 'audioAnalysis/Snare.n' -> 'audioAnalysis/Snare.n 2'
        written_by_base = {}
        for entry in self.files_written:
            # Get base name without version suffix
            base = re.sub(r' \d+$', '', entry)
            # Also handle case-insensitive matching for disk path
            base_lower = base.lower()
            written_by_base[base] = entry
            written_by_base[base_lower] = entry

        # Only include files we actually wrote, but preserve header/comment lines
        final_toc = []
        for entry in toc_order:
            if isinstance(entry, str) and entry.lstrip().startswith('#'):
                final_toc.append(entry.rstrip('\r\n'))
            else:
                # Check if we wrote this file (possibly with version suffix)
                base = re.sub(r' \d+$', '', entry)
                if base in written_by_base:
                    actual_entry = written_by_base[base]
                    if actual_entry not in final_toc:  # Avoid duplicates
                        final_toc.append(actual_entry)
                elif base.lower() in written_by_base:
                    actual_entry = written_by_base[base.lower()]
                    if actual_entry not in final_toc:
                        final_toc.append(actual_entry)

        content = '\n'.join(final_toc) + '\n'
        self._write_text_file(self.toc_file, content)

        print(f"\n[OK] Wrote {self.toc_file} ({len(final_toc)} entries)")


def main():
    if len(sys.argv) < 3:
        print("JSON to TouchDesigner Converter - LOSSLESS")
        print()
        print("Reconstructs EVERY file for perfect round-trip")
        print()
        print("Usage:")
        print("  python json_to_dir_LOSSLESS.py <input.json> <output_name>")
        print()
        print("Example:")
        print("  python json_to_dir_LOSSLESS.py project.json test_output")
        print()
        print("Creates: test_output.dir/ and test_output.toc")
        print("Then run: toecollapse test_output")
        sys.exit(1)
    
    json_path = Path(sys.argv[1])
    base_name = sys.argv[2]
    
    if not json_path.exists():
        print(f"Error: {json_path} not found")
        sys.exit(1)
    
    # Clean up existing output
    output_dir = Path(f"{base_name}.dir")
    toc_file = Path(f"{base_name}.toc")
    
    if output_dir.exists():
        import shutil
        print(f"Removing existing {output_dir}")
        shutil.rmtree(output_dir)
    if toc_file.exists():
        toc_file.unlink()
    
    try:
        converter = LosslessJsonToToeConverter(json_path, base_name)
        converter.convert()
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

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
        
        print(f"\nWriting {len(toc_order)} files...")
        
        for idx, file_path in enumerate(toc_order, 1):
            if idx % 100 == 0:
                print(f"  Progress: {idx}/{len(toc_order)}")
            
            # Metadata files
            if file_path in ['.build', '.start', '.grps', '.root', '.parm', '.application']:
                self._write_metadata_file(file_path)
            
            # Operator files
            elif file_path.endswith('.n'):
                self._write_operator_n_file(file_path, operators)
            
            # Parameter files
            elif file_path.endswith('.parm'):
                self._write_operator_parm_file(file_path, operators)
            
            # Extra/raw files
            else:
                self._write_extra_or_raw_file(file_path, operators, raw_files)
    
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
        else:
            print(f"  WARNING: Metadata file {file_path} not in raw_files")
    
    def _write_operator_n_file(self, file_path: str, operators: Dict):
        """Write operator .n file"""
        
        # Determine operator path
        if '/' in file_path:
            parts = file_path.rsplit('/', 1)
            op_path = '/' + parts[0] + '/' + parts[1].replace('.n', '')
        else:
            op_path = '/' + file_path.replace('.n', '')
        
        if op_path not in operators:
            print(f"  WARNING: Operator not found in JSON: {op_path}")
            return
        
        op = operators[op_path]
        
        # Create directory if needed
        if '/' in file_path:
            (self.output_dir / Path(file_path).parent).mkdir(parents=True, exist_ok=True)
        
        # Generate .n content
        content = self._generate_n_content(op)
        self._write_text_file(self.output_dir / file_path, content)
        self.files_written.append(file_path)
    
    def _write_operator_parm_file(self, file_path: str, operators: Dict):
        """Write operator .parm file"""
        
        # Determine operator path
        if '/' in file_path:
            parts = file_path.rsplit('/', 1)
            op_path = '/' + parts[0] + '/' + parts[1].replace('.parm', '')
        else:
            op_path = '/' + file_path.replace('.parm', '')
        
        if op_path not in operators:
            return
        
        op = operators[op_path]
        
        if op.get('parameters'):
            content = self._generate_parm_content(op['parameters'])
            self._write_text_file(self.output_dir / file_path, content)
            self.files_written.append(file_path)
    
    def _write_extra_or_raw_file(self, file_path: str, operators: Dict, raw_files: Dict):
        """Write extra file (from operator or raw files)"""
        
        # Determine if this belongs to an operator
        base_path = file_path.rsplit('.', 1)[0]
        op_path = '/' + base_path
        extension = file_path.split('.')[-1]
        
        # Create directory if needed
        if '/' in file_path:
            (self.output_dir / Path(file_path).parent).mkdir(parents=True, exist_ok=True)
        
        # Try to get from operator
        if op_path in operators:
            op = operators[op_path]
            if extension in op.get('extra_files', {}):
                file_data = op['extra_files'][extension]
                self._write_file_from_data(file_path, file_data)
                return
        
        # Get from raw files
        if file_path in raw_files:
            self._write_file_from_data(file_path, raw_files[file_path])
        else:
            print(f"  WARNING: File not found in JSON: {file_path}")
    
    def _write_file_from_data(self, file_path: str, file_data: Dict):
        """Write file from stored data (handles text/binary)"""
        
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
        
        self.files_written.append(file_path)
    
    def _generate_n_content(self, op: Dict[str, Any]) -> str:
        """Generate .n file content"""
        lines = []
        
        lines.append(op['op_type'])
        
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
        """Write .toc file with preserved ordering"""
        
        # Use original .toc ordering
        toc_order = self.network.get('toc_order', [])
        
        # Only include files we actually wrote, but ALWAYS preserve header/comment lines.
        final_toc = []
        for entry in toc_order:
            if isinstance(entry, str) and entry.lstrip().startswith('#'):
                final_toc.append(entry.rstrip('\r\n'))
            elif entry in self.files_written:
                final_toc.append(entry)
        
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

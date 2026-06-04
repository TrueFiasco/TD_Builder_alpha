#!/usr/bin/env python3
"""
TouchDesigner .tox Builder
===========================
Creates valid .tox files from high-level JSON specifications.

Features:
- Validates operators against known types
- Validates parameters against ground-truth schemas
- Generates .toc, .n, .parm files
- Calls toecollapse to create final .tox

Usage:
    from builder import ToxBuilder

    spec = {
        "name": "my_component",
        "operators": [
            {"path": "noise1", "type": "noiseCHOP", "parameters": {"amp": 2.0}}
        ],
        "connections": [
            {"from": "noise1", "to": "math1", "input": 0}
        ]
    }

    builder = ToxBuilder()
    tox_path = builder.build(spec, output_dir="./output")
"""

import json
import os
import re
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


# Paths to data files
DATA_DIR = Path(__file__).parent.parent / "operator_ground_truth"
OPERATOR_TYPES_PATH = DATA_DIR / "operator_types.json"
PARAM_CATALOG_PATH = DATA_DIR / "param_catalog.json"

# TouchDesigner tools
TOECOLLAPSE = r"C:\Program Files\Derivative\TouchDesigner\bin\toecollapse.exe"


@dataclass
class ValidationError:
    """Represents a validation error."""
    code: str
    message: str
    path: Optional[str] = None
    suggestion: Optional[str] = None

    def __str__(self):
        loc = f" at {self.path}" if self.path else ""
        sug = f" (Suggestion: {self.suggestion})" if self.suggestion else ""
        return f"[{self.code}]{loc}: {self.message}{sug}"


@dataclass
class OperatorSpec:
    """Specification for an operator."""
    path: str
    type: str
    family: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    position: Tuple[int, int] = (0, 0)
    flags: Dict[str, str] = field(default_factory=dict)
    inputs: List[str] = field(default_factory=list)
    extra_files: Dict[str, str] = field(default_factory=dict)


class OperatorRegistry:
    """Registry of valid operator types."""

    def __init__(self):
        self.operators = {}  # kb_name -> {family, td_create_name}
        self.by_create_name = {}  # td_create_name -> kb_name
        self.families = set()
        self._load()

    def _load(self):
        """Load operator types from JSON."""
        if not OPERATOR_TYPES_PATH.exists():
            print(f"WARNING: Operator types file not found: {OPERATOR_TYPES_PATH}")
            return

        with open(OPERATOR_TYPES_PATH, encoding='utf-8') as f:
            data = json.load(f)

        for family, ops in data.get('operators', {}).items():
            self.families.add(family)
            for op in ops:
                kb_name = op['name']
                # Try both td_create and td_create_name for compatibility
                td_name = op.get('td_create') or op.get('td_create_name', kb_name.lower())

                self.operators[kb_name] = {
                    'family': family,
                    'td_create_name': td_name
                }
                self.by_create_name[td_name.lower()] = kb_name

    def is_valid_type(self, op_type: str) -> bool:
        """Check if operator type is valid."""
        # Check by TD create name (e.g., noiseCHOP)
        if op_type.lower() in self.by_create_name:
            return True
        # Check by KB name (e.g., Noise_CHOP)
        if op_type in self.operators:
            return True
        return False

    def get_family(self, op_type: str) -> Optional[str]:
        """Get operator family."""
        # By TD create name
        kb_name = self.by_create_name.get(op_type.lower())
        if kb_name:
            return self.operators[kb_name]['family']
        # By KB name
        if op_type in self.operators:
            return self.operators[op_type]['family']
        return None

    # Operators with shortened .n type names (TD create name -> .n base name)
    # These map from the TD create name (lowercase) to the base name used in .n files
    N_TYPE_OVERRIDES = {
        # TOPs - composite/converter types use shortened names
        'compositetop': 'comp',
        'chromakeytop': 'chroma',
        'choptotop': 'chopto',
        # CHOPs
        'compositechop': 'comp',
        # SOPs
        'choptosop': 'chopto',
        'soptochop': 'sopto',
        'soptodat': 'sopto',
        'poptosop': 'popto',
        # DATs
        'choptodat': 'chopto',
        'dattodat': 'datto',
        'dattochop': 'datto',
        # MATs
        'mattop': 'mat',
        'pointspritemat': 'pointsprite',
        # COMPs - special shortened names
        'cameracomp': 'cam',      # cameraCOMP -> COMP:cam (not COMP:camera)
        'geocomp': 'geo',         # geoCOMP -> COMP:geo (verified correct)
        'lightcomp': 'light',     # lightCOMP -> COMP:light
        # Note: forcePOP and forceradialPOP are SEPARATE operators in TD
        # forcePOP -> POP:force (general directional force)
        # forceradialPOP -> POP:forceradial (radial force toward/away from point)
        # WARNING: dragPOP appears to not work via .tox creation (no ground truth)
    }

    def get_n_type(self, op_type: str) -> Optional[str]:
        """Get the FAMILY:type string for .n file."""
        family = self.get_family(op_type)
        if not family:
            return None

        type_lower = op_type.lower()

        # Check for overrides first
        if type_lower in self.N_TYPE_OVERRIDES:
            base = self.N_TYPE_OVERRIDES[type_lower]
            return f"{family}:{base}"

        # Extract base type name
        # noiseCHOP -> noise
        # constantCHOP -> constant
        for suffix in ['chop', 'top', 'sop', 'dat', 'mat', 'comp', 'pop']:
            if type_lower.endswith(suffix):
                base = type_lower[:-len(suffix)]
                return f"{family}:{base}"

        return None


class ToxBuilder:
    """Build .tox files from JSON specifications."""

    def __init__(self, validate: bool = True, verbose: bool = True):
        """
        Initialize builder.

        Args:
            validate: Whether to validate against known operators/params
            verbose: Print progress messages
        """
        self.validate = validate
        self.verbose = verbose
        self.registry = OperatorRegistry()
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []

    def build(self, spec: Dict[str, Any], output_dir: str = ".") -> Optional[Path]:
        """
        Build .tox file from specification.

        Args:
            spec: Network specification dict
            output_dir: Directory to create output files

        Returns:
            Path to created .tox file, or None if failed
        """
        self.errors = []
        self.warnings = []

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Extract name
        name = spec.get('name', 'component')
        container_name = f"sample_{name}"

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"Building TOX: {name}")
            print(f"{'=' * 60}")

        # Validate spec
        if self.validate:
            self._validate_spec(spec)
            if self.errors:
                print(f"\nValidation failed with {len(self.errors)} errors:")
                for err in self.errors:
                    print(f"  {err}")
                return None

        # Create output structure
        tox_name = f"{name}.tox"
        dir_path = output_dir / f"{tox_name}.dir"
        toc_path = output_dir / f"{tox_name}.toc"

        # Clean existing
        if dir_path.exists():
            shutil.rmtree(dir_path)
        if toc_path.exists():
            toc_path.unlink()

        dir_path.mkdir(parents=True)

        # Build files
        files_written = []

        # 1. .build
        build_content = self._generate_build()
        self._write_file(dir_path / '.build', build_content)
        files_written.append('.build')

        # 2. Container .n file
        container_n = self._generate_container_n(container_name)
        self._write_file(dir_path / f'{container_name}.n', container_n)
        files_written.append(f'{container_name}.n')

        # 3. Container .parm (minimal)
        self._write_file(dir_path / f'{container_name}.parm', '?\n?\n')
        files_written.append(f'{container_name}.parm')

        # 4. Create container subdirectory for operators
        container_dir = dir_path / container_name
        container_dir.mkdir()

        # 5. Process operators
        operators = spec.get('operators', [])
        for idx, op_spec in enumerate(operators):
            op_files = self._build_operator(op_spec, container_name, container_dir, idx)
            for f in op_files:
                files_written.append(f'{container_name}/{f}')

        # 6. Write .toc
        toc_content = self._generate_toc(files_written)
        self._write_file(toc_path, toc_content)

        if self.verbose:
            print(f"\n[OK] Created {len(files_written)} files")
            print(f"[OK] Written to: {dir_path}")

        # 7. Collapse to .tox
        tox_path = self._collapse(toc_path, output_dir / tox_name)

        if tox_path and self.verbose:
            print(f"\n{'=' * 60}")
            print(f"[SUCCESS] Created: {tox_path}")
            print(f"{'=' * 60}")

        return tox_path

    def _validate_spec(self, spec: Dict[str, Any]):
        """Validate specification against known operators."""
        operators = spec.get('operators', [])

        for idx, op in enumerate(operators):
            path = f"operators[{idx}]"

            # Check required fields
            if 'type' not in op:
                self.errors.append(ValidationError(
                    code="MISSING_TYPE",
                    message="Operator missing 'type' field",
                    path=path
                ))
                continue

            op_type = op['type']

            # Validate operator type
            if not self.registry.is_valid_type(op_type):
                self.errors.append(ValidationError(
                    code="UNKNOWN_OPERATOR",
                    message=f"Unknown operator type: {op_type}",
                    path=path,
                    suggestion="Check operator_types.json for valid types"
                ))

    def _generate_build(self) -> str:
        """Generate .build file content."""
        return "version 099\nbuild 2023.11880\n"

    def _generate_container_n(self, name: str) -> str:
        """Generate container COMP .n file."""
        return f"""COMP:base
tile 0 0 130 90
flags = parlanguage 0
color 0.55 0.55 0.55
end
"""

    def _generate_toc(self, files: List[str]) -> str:
        """Generate .toc file content."""
        lines = ['# 4 0 0 0 1']
        lines.extend(files)
        return '\n'.join(lines) + '\n'

    def _build_operator(self, op_spec: Dict, container: str, container_dir: Path, idx: int) -> List[str]:
        """Build files for a single operator."""
        files = []

        # Extract info
        op_type = op_spec.get('type', 'constantCHOP')
        op_name = op_spec.get('name', op_spec.get('path', f'op{idx}'))
        params = op_spec.get('parameters', {})
        position = op_spec.get('position', (idx * 150, 0))
        inputs = op_spec.get('inputs', [])
        content = op_spec.get('content', None)  # Text content for DATs
        custom_data = op_spec.get('custom_data', {})  # exports, dict, color

        # Get .n type string
        n_type = self.registry.get_n_type(op_type)
        if not n_type:
            # Fallback: try to construct from type
            family = self.registry.get_family(op_type) or 'CHOP'
            base = op_type.lower()
            for suffix in ['chop', 'top', 'sop', 'dat', 'mat', 'comp', 'pop']:
                if base.endswith(suffix):
                    base = base[:-len(suffix)]
                    break
            n_type = f"{family}:{base}"

        # Generate .n file
        n_content = self._generate_operator_n(n_type, position, inputs, custom_data)
        self._write_file(container_dir / f'{op_name}.n', n_content)
        files.append(f'{op_name}.n')

        # Generate .parm file (if params)
        if params:
            parm_content = self._generate_parm(params)
            self._write_file(container_dir / f'{op_name}.parm', parm_content)
            files.append(f'{op_name}.parm')

        # Generate .text file for DAT content (binary format)
        if content is not None:
            text_bytes = self._generate_binary_text(content)
            self._write_binary_file(container_dir / f'{op_name}.text', text_bytes)
            files.append(f'{op_name}.text')

        return files

    def _generate_binary_text(self, content: str) -> bytes:
        """Generate binary .text file content for DATs.

        TD .text binary format (reverse-engineered from working TD exports):
        - "2\\n" (2 bytes version marker)
        - uint32 LE = 42 (4 bytes) - magic number
        - uint32 LE = 1 (4 bytes)
        - uint32 LE = 1 (4 bytes)
        - uint32 LE = 1 (4 bytes)
        - uint32 LE = 1 (4 bytes)
        - uint16 LE = 2 (2 bytes) - type marker
        - uint8 = 0 (1 byte padding)
        - uint16 BE = content length (2 bytes)
        - UTF-8 encoded content
        Total header: 27 bytes
        """
        content_bytes = content.encode('utf-8')
        content_len = len(content_bytes)

        # Build the 27-byte header
        version = b"2\n"                              # 2 bytes
        magic = struct.pack('<I', 42)                 # 4 bytes LE (0x2a = '*')
        metadata = struct.pack('<4I', 1, 1, 1, 1)     # 16 bytes LE
        type_marker = struct.pack('<H', 2)            # 2 bytes LE
        padding = b'\x00'                             # 1 byte
        length_bytes = struct.pack('>H', content_len) # 2 bytes BE

        return version + magic + metadata + type_marker + padding + length_bytes + content_bytes

    def _write_binary_file(self, path: Path, content: bytes):
        """Write binary file."""
        with open(path, 'wb') as f:
            f.write(content)

    def _generate_operator_n(self, n_type: str, position: Tuple[int, int], inputs: List[str], custom_data: Dict = None) -> str:
        """Generate operator .n file content."""
        if custom_data is None:
            custom_data = {}

        lines = [n_type]
        lines.append(f'tile {position[0]} {position[1]} 130 90')
        lines.append('flags = parlanguage 0')

        if inputs:
            lines.append('inputs')
            lines.append('{')
            for idx, inp in enumerate(inputs):
                lines.append(f'{idx} \t{inp}')
            lines.append('}')

        # Handle exports block from custom_data
        if 'exports' in custom_data:
            exports = custom_data['exports']
            lines.append('exports')
            lines.append('{')
            for export_name in exports:
                lines.append(export_name)
            lines.append('}')

        # Handle dict line from custom_data
        if 'dict' in custom_data:
            lines.append(f'dict {custom_data["dict"]}')

        # Handle color from custom_data, otherwise use default
        if 'color' in custom_data:
            color = custom_data['color']
            lines.append(f'color {color[0]} {color[1]} {color[2]}')
        else:
            lines.append('color 0.55 0.55 0.55')

        lines.append('end')

        return '\n'.join(lines) + '\n'

    def _generate_parm(self, params: Dict[str, Any]) -> str:
        """Generate .parm file content.

        Values can be:
        - Simple values (int, float, bool, str): mode 0 (constant)
        - Dict with 'expr' key: mode 17 (expression)
          e.g., {"value": 0.0, "expr": "op('mouse')['tx']"}
        """
        lines = ['?']

        for name, value in params.items():
            # Check if this is an expression binding
            if isinstance(value, dict) and 'expr' in value:
                # Expression mode (17)
                val = value.get('value', 0)
                expr = value['expr']
                if isinstance(val, bool):
                    val_str = 'on' if val else 'off'
                else:
                    val_str = str(val)
                lines.append(f'{name} 17 {val_str} {expr}')
            elif isinstance(value, bool):
                val_str = 'on' if value else 'off'
                lines.append(f'{name} 0 {val_str}')
            elif isinstance(value, (int, float)):
                lines.append(f'{name} 0 {value}')
            else:
                lines.append(f'{name} 0 {value}')

        lines.append('?')
        return '\n'.join(lines) + '\n'

    def _write_file(self, path: Path, content: str):
        """Write file with Unix line endings."""
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)

    def _collapse(self, toc_path: Path, output_path: Path) -> Optional[Path]:
        """Collapse directory to .tox file."""
        if not Path(TOECOLLAPSE).exists():
            if self.verbose:
                print(f"\nWARNING: toecollapse not found at {TOECOLLAPSE}")
                print(f"Run manually: toecollapse {toc_path}")
            return None

        try:
            # toecollapse expects the .toc file
            result = subprocess.run(
                [TOECOLLAPSE, str(toc_path)],
                capture_output=True,
                text=True,
                timeout=60
            )

            if output_path.exists():
                if self.verbose:
                    print(f"\n[OK] Collapsed to: {output_path}")
                return output_path
            else:
                if self.verbose:
                    print(f"\nERROR: toecollapse failed")
                    print(f"  stdout: {result.stdout}")
                    print(f"  stderr: {result.stderr}")
                return None

        except Exception as e:
            if self.verbose:
                print(f"\nERROR: toecollapse failed: {e}")
            return None


def build_from_json(json_path: str, output_dir: str = ".") -> Optional[Path]:
    """Build .tox from JSON file."""
    with open(json_path, encoding='utf-8') as f:
        spec = json.load(f)

    builder = ToxBuilder()
    return builder.build(spec, output_dir)


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("TOX Builder - Create .tox files from JSON")
        print()
        print("Usage:")
        print("  python builder.py <spec.json> [output_dir]")
        print()
        print("Example spec.json:")
        print("""
{
  "name": "my_audio",
  "operators": [
    {"name": "noise1", "type": "noiseCHOP", "parameters": {"amp": 2.0}},
    {"name": "math1", "type": "mathCHOP", "inputs": ["noise1"]}
  ]
}
""")
        sys.exit(1)

    json_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    result = build_from_json(json_path, output_dir)
    sys.exit(0 if result else 1)

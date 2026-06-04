#!/usr/bin/env python3
"""
TouchDesigner .tox Builder v2
==============================
Enhanced builder with fixes for GLSL shaders, binary .text format,
custom parameters, and initialization scripts.

New features:
- Binary .text format for proper shader loading
- Support for dock attribute on textDATs
- Expression mode parameters (mode 17)
- GLSL TOP uniform configuration
- Initialization scripts for custom parameters
"""

import json
import os
import re
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

# Import base classes from original builder
from builder import OperatorRegistry, ValidationError, TOECOLLAPSE


class ToxBuilderV2:
    """Enhanced .tox builder with GLSL and custom parameter support."""

    def __init__(self, validate: bool = True, verbose: bool = True):
        self.validate = validate
        self.verbose = verbose
        self.registry = OperatorRegistry()
        self.errors: List[ValidationError] = []
        self.warnings: List[ValidationError] = []

    def build(self, spec: Dict[str, Any], output_dir: str = ".") -> Optional[Path]:
        """Build .tox file from specification."""
        self.errors = []
        self.warnings = []

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        name = spec.get('name', 'component')
        container_name = f"sample_{name}"

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"Building TOX v2: {name}")
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

        files_written = []

        # 1. .build
        build_content = self._generate_build()
        self._write_file(dir_path / '.build', build_content)
        files_written.append('.build')

        # 2. Container .n file
        container_n = self._generate_container_n(container_name)
        self._write_file(dir_path / f'{container_name}.n', container_n)
        files_written.append(f'{container_name}.n')

        # 3. Container .parm
        container_parm = self._generate_container_parm(spec.get('custom_pars', {}))
        self._write_file(dir_path / f'{container_name}.parm', container_parm)
        files_written.append(f'{container_name}.parm')

        # 4. Create container subdirectory
        container_dir = dir_path / container_name
        container_dir.mkdir()

        # 5. Process operators
        operators = spec.get('operators', [])
        for idx, op_spec in enumerate(operators):
            op_files = self._build_operator(op_spec, container_name, container_dir, idx)
            for f in op_files:
                files_written.append(f'{container_name}/{f}')

        # 6. Add init script if custom parameters defined
        if spec.get('custom_pars'):
            init_files = self._create_init_script(spec.get('custom_pars', {}), container_dir)
            for f in init_files:
                files_written.append(f'{container_name}/{f}')

        # 7. Write .toc
        toc_content = self._generate_toc(files_written)
        self._write_file(toc_path, toc_content)

        if self.verbose:
            print(f"\n[OK] Created {len(files_written)} files")
            print(f"[OK] Written to: {dir_path}")

        # 8. Collapse to .tox
        tox_path = self._collapse(toc_path, output_dir / tox_name)

        if tox_path and self.verbose:
            print(f"\n{'=' * 60}")
            print(f"[SUCCESS] Created: {tox_path}")
            print(f"{'=' * 60}")

        return tox_path

    def _validate_spec(self, spec: Dict[str, Any]):
        """Validate specification."""
        operators = spec.get('operators', [])
        for idx, op in enumerate(operators):
            path = f"operators[{idx}]"
            if 'type' not in op:
                self.errors.append(ValidationError(
                    code="MISSING_TYPE",
                    message="Operator missing 'type' field",
                    path=path
                ))
                continue
            op_type = op['type']
            if not self.registry.is_valid_type(op_type):
                self.warnings.append(ValidationError(
                    code="UNKNOWN_OPERATOR",
                    message=f"Unknown operator type: {op_type}",
                    path=path,
                    suggestion="May still work if valid TD operator"
                ))

    def _generate_build(self) -> str:
        return "version 099\nbuild 2023.11880\n"

    def _generate_container_n(self, name: str) -> str:
        return f"""COMP:base
tile 0 0 130 90
flags = parlanguage 0
color 0.55 0.55 0.55
end
"""

    def _generate_container_parm(self, custom_pars: Dict) -> str:
        """Generate container .parm with custom parameters placeholder."""
        return "?\n?\n"

    def _generate_toc(self, files: List[str]) -> str:
        lines = ['# 4 0 0 0 1']
        lines.extend(files)
        return '\n'.join(lines) + '\n'

    def _build_operator(self, op_spec: Dict, container: str, container_dir: Path, idx: int) -> List[str]:
        """Build files for an operator."""
        files = []

        op_type = op_spec.get('type', 'constantCHOP')
        op_name = op_spec.get('name', op_spec.get('path', f'op{idx}'))
        params = op_spec.get('parameters', {})
        position = op_spec.get('position', (idx * 150, 0))
        inputs = op_spec.get('inputs', [])
        content = op_spec.get('content', None)
        flags = op_spec.get('flags', {})
        dock = op_spec.get('dock', None)
        custom_data = op_spec.get('custom_data', {})  # exports, dict, color

        # Get .n type string
        n_type = self.registry.get_n_type(op_type)
        if not n_type:
            family = self.registry.get_family(op_type) or 'CHOP'
            base = op_type.lower()
            for suffix in ['chop', 'top', 'sop', 'dat', 'mat', 'comp', 'pop']:
                if base.endswith(suffix):
                    base = base[:-len(suffix)]
                    break
            n_type = f"{family}:{base}"

        # Generate .n file
        n_content = self._generate_operator_n(n_type, position, inputs, flags, dock, custom_data)
        self._write_file(container_dir / f'{op_name}.n', n_content)
        files.append(f'{op_name}.n')

        # Generate .parm file
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

    def _generate_operator_n(self, n_type: str, position: Tuple[int, int],
                             inputs: List[str], flags: Dict = None, dock: str = None, custom_data: Dict = None) -> str:
        """Generate operator .n file with extended options."""
        if custom_data is None:
            custom_data = {}

        lines = [n_type]
        lines.append(f'tile {position[0]} {position[1]} 130 90')

        # Build flags string
        flag_parts = []
        if flags:
            if flags.get('viewer'):
                flag_parts.append('viewer 1')
            if flags.get('activate'):
                flag_parts.append('activate on')
        flag_parts.append('parlanguage 0')
        lines.append(f'flags =  {" ".join(flag_parts)}')

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
            lines.append('color 0.55 0.55 0.55 ')

        # Add dock attribute for textDATs linked to glslTOPs
        if dock:
            lines.append(f'dock {dock}')

        lines.append('end')
        return '\n'.join(lines) + '\n'

    def _generate_parm(self, params: Dict[str, Any]) -> str:
        """Generate .parm file with expression support."""
        lines = ['?']

        for name, value in params.items():
            if isinstance(value, dict) and 'expr' in value:
                # Expression mode (17)
                val = value.get('value', 0)
                expr = value['expr']
                val_str = 'on' if isinstance(val, bool) and val else ('off' if isinstance(val, bool) else str(val))
                lines.append(f'{name} 17 {val_str} {expr}')
            elif isinstance(value, bool):
                lines.append(f'{name} 0 {"on" if value else "off"}')
            elif isinstance(value, (int, float)):
                lines.append(f'{name} 0 {value}')
            elif isinstance(value, str):
                # Quote strings if they contain spaces
                if ' ' in value or value == '':
                    lines.append(f'{name} 0 "{value}"')
                else:
                    lines.append(f'{name} 0 {value}')
            else:
                lines.append(f'{name} 0 {value}')

        lines.append('?')
        return '\n'.join(lines) + '\n'

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

    def _create_init_script(self, custom_pars: Dict, container_dir: Path) -> List[str]:
        """Create initialization script for custom parameters."""
        files = []

        # Generate Python code to add custom parameters
        init_code = '''# Auto-generated initialization script
# Adds custom parameters to parent COMP

def onStart():
    """Called when component starts."""
    me = op('..')
    page = me.customPages[0] if me.customPages else me.appendCustomPage('Custom')

'''
        for par_name, par_spec in custom_pars.items():
            par_type = par_spec.get('type', 'Float')
            default = par_spec.get('default', 0)
            min_val = par_spec.get('min', 0)
            max_val = par_spec.get('max', 1)
            label = par_spec.get('label', par_name)

            if par_type == 'Float':
                init_code += f'''    if not hasattr(me.par, '{par_name}'):
        p = page.appendFloat('{par_name}', label='{label}')
        p[0].default = {default}
        p[0].min = {min_val}
        p[0].max = {max_val}
        p[0].val = {default}
'''
            elif par_type == 'XY':
                init_code += f'''    if not hasattr(me.par, '{par_name}x'):
        p = page.appendXY('{par_name}', label='{label}')
        p[0].default = {par_spec.get('default_x', 0)}
        p[1].default = {par_spec.get('default_y', 0)}
'''

        init_code += '''
onStart()
'''

        # Create the init DAT
        init_n = """DAT:text
tile 0 -200 130 90
flags =  viewer 1 parlanguage 0
color 0.55 0.55 0.55
end
"""
        self._write_file(container_dir / 'init_script.n', init_n)
        files.append('init_script.n')

        init_parm = """?
language 0 python
extension 0 py
?
"""
        self._write_file(container_dir / 'init_script.parm', init_parm)
        files.append('init_script.parm')

        init_bytes = self._generate_binary_text(init_code)
        self._write_binary_file(container_dir / 'init_script.text', init_bytes)
        files.append('init_script.text')

        return files

    def _write_file(self, path: Path, content: str):
        """Write text file with Unix line endings."""
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)

    def _write_binary_file(self, path: Path, content: bytes):
        """Write binary file."""
        with open(path, 'wb') as f:
            f.write(content)

    def _collapse(self, toc_path: Path, output_path: Path) -> Optional[Path]:
        """Collapse directory to .tox file."""
        if not Path(TOECOLLAPSE).exists():
            if self.verbose:
                print(f"\nWARNING: toecollapse not found at {TOECOLLAPSE}")
            return None

        try:
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


def create_glsl_network(name: str, shader_code: str, uniforms: Dict[str, Any],
                        custom_pars: Dict[str, Any], output_dir: str) -> Optional[Path]:
    """
    Convenience function to create a GLSL-based TOX.

    Args:
        name: Component name
        shader_code: GLSL fragment shader code
        uniforms: Dict of uniform name -> value or expression
        custom_pars: Dict of custom parameter definitions
        output_dir: Output directory

    Returns:
        Path to created .tox file
    """
    # Build uniform parameters for glslTOP
    glsl_params = {
        'pixeldat': 'pixel_shader',
        'resolutionw': 1920,
        'resolutionh': 1080,
    }

    # Add uniforms
    for idx, (uname, uval) in enumerate(uniforms.items()):
        glsl_params[f'vec{idx}name'] = uname
        if isinstance(uval, dict) and 'expr' in uval:
            glsl_params[f'vec{idx}valuex'] = uval
        else:
            glsl_params[f'vec{idx}valuex'] = uval

    spec = {
        'name': name,
        'custom_pars': custom_pars,
        'operators': [
            # Mouse input
            {
                'name': 'mouse_in',
                'type': 'mouseinCHOP',
                'position': (0, 0)
            },
            # Math to normalize mouse
            {
                'name': 'mouse_math',
                'type': 'mathCHOP',
                'position': (150, 0),
                'inputs': ['mouse_in'],
                'parameters': {
                    'postoff': -0.5,
                    'gain': 2
                }
            },
            # Shader text DAT
            {
                'name': 'pixel_shader',
                'type': 'textDAT',
                'position': (0, -150),
                'content': shader_code,
                'dock': 'render',
                'flags': {'viewer': True},
                'parameters': {
                    'language': 'glsl',
                    'extension': 'frag'
                }
            },
            # GLSL TOP
            {
                'name': 'render',
                'type': 'glslTOP',
                'position': (300, 0),
                'flags': {'viewer': True},
                'parameters': glsl_params
            },
            # Output
            {
                'name': 'out1',
                'type': 'outTOP',
                'position': (450, 0),
                'inputs': ['render']
            }
        ]
    }

    builder = ToxBuilderV2()
    return builder.build(spec, output_dir)


if __name__ == '__main__':
    # Test with a simple shader
    test_shader = """// Test shader
uniform float uTime;
uniform vec2 uMouse;

layout(location = 0) out vec4 fragColor;

void main()
{
    vec2 uv = vUV.st;
    vec3 col = 0.5 + 0.5 * cos(uTime + uv.xyx + vec3(0,2,4));
    fragColor = TDOutputSwizzle(vec4(col, 1.0));
}
"""

    result = create_glsl_network(
        name='test_glsl',
        shader_code=test_shader,
        uniforms={'uTime': {'expr': "absTime.seconds"}, 'uMouse': 0},
        custom_pars={
            'Temperature': {'type': 'Float', 'default': 0.5, 'min': 0, 'max': 1},
            'Energy': {'type': 'Float', 'default': 0.5, 'min': 0, 'max': 1},
        },
        output_dir='./output'
    )

    if result:
        print(f"Created: {result}")

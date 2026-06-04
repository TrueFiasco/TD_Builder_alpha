#!/usr/bin/env python3
"""
TouchDesigner .toe Builder v4
==============================
Creates proper TOE project files with:
- Root-level system files (.start, .grps, .root)
- COMP:container main project container
- Proper custom parameters via .cparm files
- Embedded nested COMPs for scenes
"""

import os
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Path to toecollapse executable
TOECOLLAPSE = r"C:\Program Files\Derivative\TouchDesigner\bin\toecollapse.exe"


@dataclass
class CustomParameter:
    """Defines a custom parameter for a COMP."""
    name: str
    label: str
    par_type: str = 'Float'  # Float, Int, Toggle, Menu, String
    default: Any = 0.0
    min_val: float = 0.0
    max_val: float = 1.0
    page: str = 'Custom'
    order: int = 0


class ToeBuilder:
    """Builder for TouchDesigner .toe project files."""

    # Type IDs for .cparm file
    CPARM_TYPE_IDS = {
        'Float': -1374678783,     # Float slider with range
        'Int': -1374678782,       # Int slider with range
        'Toggle': 772935939,      # Boolean toggle
        'Pulse': 772804869,       # Pulse button
        'String': 772804868,      # String field
    }

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def build(self, spec: Dict[str, Any], output_dir: str = ".") -> Optional[Path]:
        """Build .toe file from specification."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        name = spec.get('name', 'project')
        project_name = spec.get('project_name', 'project1')  # Main container name

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"Building TOE: {name}")
            print(f"{'=' * 60}")

        # Create output structure
        toe_name = f"{name}.toe"
        dir_path = output_dir / f"{toe_name}.dir"
        toc_path = output_dir / f"{toe_name}.toc"

        # Clean existing
        if dir_path.exists():
            shutil.rmtree(dir_path)
        if toc_path.exists():
            toc_path.unlink()

        dir_path.mkdir(parents=True)

        toc_entries = []

        # 1. Root-level system files
        toc_entries.extend(self._write_system_files(dir_path))

        # 2. Main project container
        toc_entries.extend(self._write_project_container(dir_path, project_name, spec))

        # 3. Write .toc file
        toc_content = '\n'.join(toc_entries) + '\n'
        self._write_file(toc_path, toc_content)

        if self.verbose:
            print(f"\n[OK] Created {len(toc_entries)} files")

        # 4. Collapse to .toe
        toe_path = self._collapse(toc_path, output_dir / toe_name)

        if toe_path and self.verbose:
            print(f"\n{'=' * 60}")
            print(f"[SUCCESS] Created: {toe_path}")
            print(f"{'=' * 60}")

        return toe_path

    def _write_system_files(self, dir_path: Path) -> List[str]:
        """Write root-level TOE system files."""
        files = []

        # .build
        build_content = "version 099\nbuild 2023.11880\n"
        self._write_file(dir_path / '.build', build_content)
        files.append('.build')

        # .start - timing and playback settings
        start_content = """cookrate 60
clock -f 1 -s 1 -o 0 -w 0
realtime on
viewers off
resetaudioondevicechange off
"""
        self._write_file(dir_path / '.start', start_content)
        files.append('.start')

        # .grps - group info
        grps_content = "-2\n0\n"
        self._write_file(dir_path / '.grps', grps_content)
        files.append('.grps')

        # .root - root marker
        root_content = "end\n"
        self._write_file(dir_path / '.root', root_content)
        files.append('.root')

        # .parm - root-level params
        parm_content = "?\n?\n"
        self._write_file(dir_path / '.parm', parm_content)
        files.append('.parm')

        return files

    def _write_project_container(self, dir_path: Path, project_name: str,
                                  spec: Dict[str, Any]) -> List[str]:
        """Write the main project container and all its contents."""
        files = []

        # Main container .n file (COMP:container with special flags)
        container_n = """COMP:container
v 500 400 1.0
tile 200 100 400 244
flags =  picked on current on viewer 1 parlanguage 0
color 0.56 0.56 0.56
end
"""
        self._write_file(dir_path / f'{project_name}.n', container_n)
        files.append(f'{project_name}.n')

        # Main container .parm file
        container_parm = """?
pageindex 0 1
w 0 1920
h 0 1080
top 0 ./out1
borderover 0 off
parentshortcut 0 Project
?
"""
        self._write_file(dir_path / f'{project_name}.parm', container_parm)
        files.append(f'{project_name}.parm')

        # Main container .panel file
        container_panel = """1
3
6
u 0.5
v 0.5
trueu 0.5
truev 0.5
screenw 400
screenh 300
"""
        self._write_file(dir_path / f'{project_name}.panel', container_panel)
        files.append(f'{project_name}.panel')

        # Create project container directory
        project_dir = dir_path / project_name
        project_dir.mkdir()

        # Build operators inside project container
        operators = spec.get('operators', [])
        for idx, op_spec in enumerate(operators):
            op_files = self._build_operator(op_spec, project_dir, idx)
            for f in op_files:
                files.append(f'{project_name}/{f}')

        # Build nested COMPs (scenes, control center)
        nested_comps = spec.get('nested_comps', [])
        for comp_spec in nested_comps:
            comp_files = self._build_nested_comp(comp_spec, project_dir)
            for f in comp_files:
                files.append(f'{project_name}/{f}')

        return files

    def _build_nested_comp(self, comp_spec: Dict, parent_dir: Path) -> List[str]:
        """Build a nested COMP with its own operators."""
        files = []

        comp_name = comp_spec.get('name', 'nested')
        position = comp_spec.get('position', (0, 0))
        inputs = comp_spec.get('inputs', [])
        operators = comp_spec.get('operators', [])
        custom_pars = comp_spec.get('custom_pars', [])

        # COMP .n file
        n_lines = ['COMP:base']
        n_lines.append(f'tile {position[0]} {position[1]} 200 120')
        n_lines.append('flags =  viewer 1 parlanguage 0')

        # Add inputs if any
        if inputs:
            n_lines.append('inputs')
            n_lines.append('{')
            for idx, inp in enumerate(inputs):
                n_lines.append(f'{idx} \t{inp}')
            n_lines.append('}')

        n_lines.append('color 0.55 0.55 0.55')
        n_lines.append('end')

        self._write_file(parent_dir / f'{comp_name}.n', '\n'.join(n_lines) + '\n')
        files.append(f'{comp_name}.n')

        # COMP .cparm (if has custom params)
        if custom_pars:
            cparm_content = self._generate_cparm(custom_pars)
            self._write_file(parent_dir / f'{comp_name}.cparm', cparm_content)
            files.append(f'{comp_name}.cparm')

        # COMP .parm
        parm_content = self._generate_container_parm(custom_pars)
        self._write_file(parent_dir / f'{comp_name}.parm', parm_content)
        files.append(f'{comp_name}.parm')

        # Create COMP subdirectory
        comp_dir = parent_dir / comp_name
        comp_dir.mkdir(exist_ok=True)

        # Build operators inside the COMP
        for idx, op_spec in enumerate(operators):
            op_files = self._build_operator(op_spec, comp_dir, idx)
            for f in op_files:
                files.append(f'{comp_name}/{f}')

        return files

    def _generate_cparm(self, custom_pars: List[CustomParameter]) -> str:
        """Generate .cparm file for custom parameters."""
        lines = ['?']

        # Collect unique page names
        pages = []
        for par in custom_pars:
            if par.page not in pages:
                pages.append(par.page)

        # Pages line
        lines.append(f'pages {len(pages)} ' + ' '.join(pages))

        # Generate parameter entries
        for par in custom_pars:
            if par.par_type in ['Float', 'Slider']:
                type_id = self.CPARM_TYPE_IDS.get('Float', -1374678783)
                line = f'{type_id} {par.name} "{par.label}" 1 1 0 {par.min_val} 1 1 {par.max_val} 0 {par.default} "" {par.page} {par.order}'
            elif par.par_type == 'Int':
                type_id = self.CPARM_TYPE_IDS.get('Int', -1374678782)
                line = f'{type_id} {par.name} "{par.label}" 1 1 0 {int(par.min_val)} 1 1 {int(par.max_val)} 0 {int(par.default)} "" {par.page} {par.order}'
            elif par.par_type == 'Toggle':
                type_id = self.CPARM_TYPE_IDS.get('Toggle', 772935939)
                val = 1 if par.default else 0
                line = f'{type_id} {par.name} "{par.label}" 1 1 0 0 1 1 1 0 {val} "" {par.page} {par.order}'
            else:
                # Default to float
                type_id = self.CPARM_TYPE_IDS.get('Float', -1374678783)
                line = f'{type_id} {par.name} "{par.label}" 1 1 0 0 1 1 1 0 {par.default} "" {par.page} {par.order}'

            lines.append(line)

        lines.append('?')
        return '\n'.join(lines) + '\n'

    def _generate_container_parm(self, custom_pars: List[CustomParameter]) -> str:
        """Generate container .parm file with custom parameter values."""
        lines = ['?']

        # Set initial values for custom parameters
        for par in custom_pars:
            if par.par_type == 'Toggle':
                val = 'on' if par.default else 'off'
            else:
                val = par.default
            lines.append(f'{par.name} 0 {val}')

        lines.append('?')
        return '\n'.join(lines) + '\n'

    def _build_operator(self, op_spec: Dict, container_dir: Path, idx: int) -> List[str]:
        """Build files for an operator.

        Supports shader DATs with special handling:
        - shader_type: 'glsl', 'python', 'tscript'
        - shader_extension: 'frag', 'vert', 'comp', 'pixel'
        - dock: Parent GLSL operator name to link to
        """
        files = []

        op_type = op_spec.get('type', 'constantCHOP')
        op_name = op_spec.get('name', f'op{idx}')
        params = op_spec.get('parameters', {})
        position = op_spec.get('position', (idx * 150, 0))
        inputs = op_spec.get('inputs', [])
        content = op_spec.get('content', None)
        flags = op_spec.get('flags', {})

        # Shader-specific options
        shader_type = op_spec.get('shader_type', None)
        shader_extension = op_spec.get('shader_extension', None)
        dock_target = op_spec.get('dock', None)

        # Add dock to flags if specified
        if dock_target:
            flags['dock'] = dock_target
            flags['showDocked'] = False  # Hide docked operators by default

        # Determine operator family and base type
        n_type = self._get_n_type(op_type)

        # Generate .n file
        n_content = self._generate_operator_n(n_type, position, inputs, flags)
        self._write_file(container_dir / f'{op_name}.n', n_content)
        files.append(f'{op_name}.n')

        # Generate .parm file
        if shader_type:
            # Shader DAT - use shader-specific parm generation
            parm_content = self._generate_shader_parm(shader_type, shader_extension or 'frag')
            self._write_file(container_dir / f'{op_name}.parm', parm_content)
            files.append(f'{op_name}.parm')
        elif params:
            # Regular operator
            parm_content = self._generate_parm(params)
            self._write_file(container_dir / f'{op_name}.parm', parm_content)
            files.append(f'{op_name}.parm')

        # Generate .text file for DAT content
        if content is not None:
            text_bytes = self._generate_binary_text(content)
            self._write_binary_file(container_dir / f'{op_name}.text', text_bytes)
            files.append(f'{op_name}.text')

        return files

    def _get_n_type(self, op_type: str) -> str:
        """Convert operator type to .n file type string."""
        type_map = {
            # CHOPs
            'audiodeviceinCHOP': 'CHOP:audioDeviceIn',
            'audiospectCHOP': 'CHOP:audioSpect',
            'lagCHOP': 'CHOP:lag',
            'speedCHOP': 'CHOP:speed',
            'mergeCHOP': 'CHOP:merge',
            'mathCHOP': 'CHOP:math',
            'constantCHOP': 'CHOP:constant',
            'noiseCHOP': 'CHOP:noise',
            'filterCHOP': 'CHOP:filter',
            'lfoCHOP': 'CHOP:lfo',
            'selectCHOP': 'CHOP:select',
            'nullCHOP': 'CHOP:null',
            'outCHOP': 'CHOP:out',
            'inCHOP': 'CHOP:in',
            'springCHOP': 'CHOP:spring',
            'analyzeCHOP': 'CHOP:analyze',
            'resampleCHOP': 'CHOP:resample',
            # TOPs
            'choptoTOP': 'TOP:chopTo',
            'noiseTOP': 'TOP:noise',
            'feedbackTOP': 'TOP:feedback',
            'glslTOP': 'TOP:glslmulti',
            'renderTOP': 'TOP:render',
            'blurTOP': 'TOP:blur',
            'levelTOP': 'TOP:level',
            'compositeTOP': 'TOP:composite',
            'switchTOP': 'TOP:switch',
            'outTOP': 'TOP:out',
            'inTOP': 'TOP:in',
            'nullTOP': 'TOP:null',
            'rgbaTOP': 'TOP:rgba',
            'rampTOP': 'TOP:ramp',
            # SOPs
            'sphereSOP': 'SOP:sphere',
            'gridSOP': 'SOP:grid',
            'facetSOP': 'SOP:facet',
            'transformSOP': 'SOP:transform',
            'metaballSOP': 'SOP:metaball',
            'tubeSOP': 'SOP:tube',
            'switchSOP': 'SOP:switch',
            'outSOP': 'SOP:out',
            'noiseSOP': 'SOP:noise',
            # DATs
            'textDAT': 'DAT:text',
            'selectDAT': 'DAT:select',
            'nullDAT': 'DAT:null',
            # COMPs
            'baseCOMP': 'COMP:base',
            'containerCOMP': 'COMP:container',
            'geoCOMP': 'COMP:geometry',
            'camCOMP': 'COMP:camera',
            'lightCOMP': 'COMP:light',
        }

        if op_type in type_map:
            return type_map[op_type]

        # Try to infer from naming convention
        for suffix, family in [('CHOP', 'CHOP'), ('TOP', 'TOP'), ('SOP', 'SOP'),
                                ('DAT', 'DAT'), ('COMP', 'COMP'), ('MAT', 'MAT')]:
            if op_type.endswith(suffix):
                base = op_type[:-len(suffix)]
                return f'{family}:{base[0].lower() + base[1:]}'

        return f'CHOP:{op_type}'

    def _generate_operator_n(self, n_type: str, position: Tuple[int, int],
                              inputs: List[str], flags: Dict = None) -> str:
        """Generate operator .n file."""
        lines = [n_type]
        lines.append(f'tile {position[0]} {position[1]} 130 90')

        # Build flags
        flag_parts = []
        if flags:
            if flags.get('viewer'):
                flag_parts.append('viewer 1')
            if flags.get('activate'):
                flag_parts.append('activate on')
            if flags.get('showDocked') is False:
                flag_parts.append('showDocked off')
        flag_parts.append('parlanguage 0')
        lines.append(f'flags =  {" ".join(flag_parts)}')

        # Dock attribute for shader DATs linked to GLSL operators
        if flags and flags.get('dock'):
            lines.append(f'dock {flags["dock"]}')

        # Inputs
        if inputs:
            lines.append('inputs')
            lines.append('{')
            for idx, inp in enumerate(inputs):
                lines.append(f'{idx} \t{inp}')
            lines.append('}')

        lines.append('color 0.55 0.55 0.55')
        lines.append('end')
        return '\n'.join(lines) + '\n'

    def _generate_parm(self, params: Dict[str, Any]) -> str:
        """Generate .parm file.

        Handles special shader parameters:
        - language: Shader language (0 = glsl, other values for different languages)
        - extension: Shader file extension (frag, vert, comp, etc.)
        """
        lines = ['?']

        for name, value in params.items():
            if isinstance(value, dict) and 'expr' in value:
                # Expression mode (17)
                default_val = value.get('value', 0)
                expr = value['expr']
                lines.append(f'{name} 17 {default_val} {expr}')
            elif isinstance(value, bool):
                lines.append(f'{name} 0 {"on" if value else "off"}')
            elif isinstance(value, (int, float)):
                lines.append(f'{name} 0 {value}')
            elif isinstance(value, str):
                if ' ' in value or value == '':
                    lines.append(f'{name} 0 "{value}"')
                else:
                    lines.append(f'{name} 0 {value}')
            else:
                lines.append(f'{name} 0 {value}')

        lines.append('?')
        return '\n'.join(lines) + '\n'

    def _generate_shader_parm(self, shader_type: str = 'glsl', extension: str = 'frag') -> str:
        """Generate .parm file specifically for shader DATs.

        Args:
            shader_type: Shader language ('glsl', 'python', 'tscript')
            extension: Shader file extension ('frag', 'vert', 'comp', 'pixel', etc.)

        Returns:
            .parm file content for shader DAT
        """
        language_map = {'glsl': 0, 'python': 1, 'tscript': 2}
        lang_value = language_map.get(shader_type.lower(), 0)

        lines = ['?']
        lines.append(f'language 0 {shader_type}')
        if extension:
            lines.append(f'extension 0 {extension}')
        lines.append('?')
        return '\n'.join(lines) + '\n'

    def _generate_binary_text(self, content: str) -> bytes:
        """Generate binary .text file for DATs."""
        content_bytes = content.encode('utf-8')
        content_len = len(content_bytes)

        # Binary header (27 bytes)
        version = b"2\n"
        magic = struct.pack('<I', 42)
        metadata = struct.pack('<4I', 1, 1, 1, 1)
        type_marker = struct.pack('<H', 2)
        padding = b'\x00'
        length_bytes = struct.pack('>H', content_len)

        return version + magic + metadata + type_marker + padding + length_bytes + content_bytes

    def _write_file(self, path: Path, content: str):
        """Write text file with Unix line endings."""
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)

    def _write_binary_file(self, path: Path, content: bytes):
        """Write binary file."""
        with open(path, 'wb') as f:
            f.write(content)

    def _collapse(self, toc_path: Path, output_path: Path) -> Optional[Path]:
        """Collapse directory to .toe file."""
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
                    if result.stdout:
                        print(f"  stdout: {result.stdout}")
                    if result.stderr:
                        print(f"  stderr: {result.stderr}")
                return None

        except Exception as e:
            if self.verbose:
                print(f"\nERROR: toecollapse failed: {e}")
            return None


if __name__ == '__main__':
    # Test with a minimal project
    test_pars = [
        CustomParameter(name='intensity', label='Intensity', par_type='Float',
                       default=0.8, min_val=0, max_val=1, page='Main', order=0),
        CustomParameter(name='speed', label='Speed', par_type='Float',
                       default=0.5, min_val=0, max_val=2, page='Main', order=1),
    ]

    spec = {
        'name': 'test_toe',
        'project_name': 'project1',
        'operators': [
            {
                'name': 'noise1',
                'type': 'noiseTOP',
                'position': (0, 0),
                'flags': {'viewer': True},
            },
            {
                'name': 'out1',
                'type': 'outTOP',
                'position': (200, 0),
                'inputs': ['noise1'],
            },
        ],
        'nested_comps': [
            {
                'name': 'control',
                'position': (0, -200),
                'custom_pars': test_pars,
                'operators': [
                    {'name': 'lfo1', 'type': 'lfoCHOP', 'position': (0, 0)},
                    {'name': 'out1', 'type': 'outCHOP', 'position': (200, 0), 'inputs': ['lfo1']},
                ],
            },
        ],
    }

    builder = ToeBuilder()
    result = builder.build(spec, './output')
    if result:
        print(f"\nTest passed: {result}")

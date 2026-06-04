#!/usr/bin/env python3
"""
TouchDesigner .tox/.toe Builder v3
===================================
Fixed builder with:
- Proper .cparm files for custom parameters
- Embedded content (no external TOX references)
- Correct network connections
- Scene to control center wiring
"""

import json
import os
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

# Path to toecollapse executable
TOECOLLAPSE = r"C:\Program Files\Derivative\TouchDesigner\bin\toecollapse.exe"


@dataclass
class CustomParameter:
    """Defines a custom parameter for a COMP."""
    name: str
    label: str
    par_type: str = 'Float'  # Float, Int, Toggle, Menu, String, RGB
    default: Any = 0.0
    min_val: float = 0.0
    max_val: float = 1.0
    page: str = 'Custom'
    order: int = 0
    menu_items: Optional[Dict[str, str]] = None  # For Menu type: {value: label}


class ToxBuilderV3:
    """Enhanced builder with proper custom parameters and embedded content."""

    # Type IDs for .cparm file (discovered from TD palette components)
    CPARM_TYPE_IDS = {
        'Float': 772804865,      # 0x2E120001
        'Int': 772804866,        # 0x2E120002
        'String': 772804868,     # 0x2E120004 (read-only label)
        'Pulse': 772804869,      # 0x2E120005
        'Toggle': 772935939,     # 0x2E120083
        'RGB': 772809473,        # 0x2E121001
        'Menu': -1374678769,     # Menu dropdown
        'Slider': -1374678783,   # Float slider with range
        'IntSlider': -1374678782, # Int slider with range
    }

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def build(self, spec: Dict[str, Any], output_dir: str = ".") -> Optional[Path]:
        """Build .tox file from specification."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        name = spec.get('name', 'component')
        container_name = name  # Use name directly, not sample_ prefix

        if self.verbose:
            print(f"\n{'=' * 60}")
            print(f"Building TOX v3: {name}")
            print(f"{'=' * 60}")

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

        toc_entries = []

        # 1. .build file
        build_content = "version 099\nbuild 2023.11880\n"
        self._write_file(dir_path / '.build', build_content)
        toc_entries.append('.build')

        # 2. Container .n file
        container_n = self._generate_container_n(spec)
        self._write_file(dir_path / f'{container_name}.n', container_n)
        toc_entries.append(f'{container_name}.n')

        # 3. Container .cparm file (custom parameters)
        custom_pars = spec.get('custom_pars', [])
        if custom_pars:
            cparm_content = self._generate_cparm(custom_pars)
            self._write_file(dir_path / f'{container_name}.cparm', cparm_content)
            toc_entries.append(f'{container_name}.cparm')

        # 4. Container .parm file
        container_parm = self._generate_container_parm(custom_pars)
        self._write_file(dir_path / f'{container_name}.parm', container_parm)
        toc_entries.append(f'{container_name}.parm')

        # 5. Create container subdirectory for operators
        container_dir = dir_path / container_name
        container_dir.mkdir()

        # 6. Process all operators
        operators = spec.get('operators', [])
        for idx, op_spec in enumerate(operators):
            op_files = self._build_operator(op_spec, container_dir, idx)
            for f in op_files:
                toc_entries.append(f'{container_name}/{f}')

        # 7. Process nested COMPs (scenes with their own operators)
        nested_comps = spec.get('nested_comps', [])
        for comp_spec in nested_comps:
            comp_files = self._build_nested_comp(comp_spec, container_dir)
            for f in comp_files:
                toc_entries.append(f'{container_name}/{f}')

        # 8. Write .toc file (no header, just file list)
        toc_content = '\n'.join(toc_entries) + '\n'
        self._write_file(toc_path, toc_content)

        if self.verbose:
            print(f"\n[OK] Created {len(toc_entries)} files")

        # 9. Collapse to .tox
        tox_path = self._collapse(toc_path, output_dir / tox_name)

        if tox_path and self.verbose:
            print(f"\n{'=' * 60}")
            print(f"[SUCCESS] Created: {tox_path}")
            print(f"{'=' * 60}")

        return tox_path

    def _generate_container_n(self, spec: Dict) -> str:
        """Generate container .n file."""
        lines = ['COMP:base']
        lines.append('tile 0 0 200 120')
        lines.append('flags =  viewer 1 parlanguage 0')
        lines.append('color 0.55 0.55 0.55')
        lines.append('end')
        return '\n'.join(lines) + '\n'

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
        for idx, par in enumerate(custom_pars):
            if par.par_type in ['Float', 'Slider']:
                # Float/Slider parameter
                # Format: type_id Name "Label" flags... default "" PageName order
                type_id = self.CPARM_TYPE_IDS.get('Slider', -1374678783)
                # flags: normMin normMax clampMin minVal clampMax maxVal sliderMin sliderMax
                line = f'{type_id} {par.name} "{par.label}" 1 1 0 {par.min_val} 1 1 {par.max_val} 0 {par.default} "" {par.page} {par.order}'
            elif par.par_type == 'Int':
                type_id = self.CPARM_TYPE_IDS.get('IntSlider', -1374678782)
                line = f'{type_id} {par.name} "{par.label}" 1 1 0 {int(par.min_val)} 1 1 {int(par.max_val)} 0 {int(par.default)} "" {par.page} {par.order}'
            elif par.par_type == 'Toggle':
                type_id = self.CPARM_TYPE_IDS.get('Toggle', 772935939)
                val = 1 if par.default else 0
                line = f'{type_id} {par.name} "{par.label}" 1 1 0 0 1 1 1 0 {val} "" {par.page} {par.order}'
            else:
                # Default to float
                type_id = self.CPARM_TYPE_IDS.get('Float', 772804865)
                line = f'{type_id} {par.name} "{par.label}" 1 1 0 0 1 1 2 0 {par.default} "" {par.page} {par.order}'

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
        """Build files for an operator."""
        files = []

        op_type = op_spec.get('type', 'constantCHOP')
        op_name = op_spec.get('name', f'op{idx}')
        params = op_spec.get('parameters', {})
        position = op_spec.get('position', (idx * 150, 0))
        inputs = op_spec.get('inputs', [])
        content = op_spec.get('content', None)
        flags = op_spec.get('flags', {})

        # Determine operator family and base type
        n_type = self._get_n_type(op_type)

        # Generate .n file
        n_content = self._generate_operator_n(n_type, position, inputs, flags)
        self._write_file(container_dir / f'{op_name}.n', n_content)
        files.append(f'{op_name}.n')

        # Generate .parm file
        if params:
            parm_content = self._generate_parm(params)
            self._write_file(container_dir / f'{op_name}.parm', parm_content)
            files.append(f'{op_name}.parm')

        # Generate .text file for DAT content
        if content is not None:
            text_bytes = self._generate_binary_text(content)
            self._write_binary_file(container_dir / f'{op_name}.text', text_bytes)
            files.append(f'{op_name}.text')

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

    def _get_n_type(self, op_type: str) -> str:
        """Convert operator type to .n file type string."""
        # Common mappings
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
            'choptoTOP': 'TOP:chopTo',
            # TOPs
            'noiseTOP': 'TOP:noise',
            'feedbackTOP': 'TOP:feedback',
            'glslTOP': 'TOP:glsl',
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
            'voronoifractureSOP': 'SOP:voronoiFracture',
            # DATs
            'textDAT': 'DAT:text',
            'selectDAT': 'DAT:select',
            'nullDAT': 'DAT:null',
            # COMPs
            'baseCOMP': 'COMP:base',
            'containerCOMP': 'COMP:container',
            'geoCOMP': 'COMP:geo',
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
                # Convert camelCase to proper format
                return f'{family}:{base[0].lower() + base[1:]}'

        return f'CHOP:{op_type}'  # Default to CHOP

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
        flag_parts.append('parlanguage 0')
        lines.append(f'flags =  {" ".join(flag_parts)}')

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
        """Generate .parm file."""
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
                    if result.stdout:
                        print(f"  stdout: {result.stdout}")
                    if result.stderr:
                        print(f"  stderr: {result.stderr}")
                return None

        except Exception as e:
            if self.verbose:
                print(f"\nERROR: toecollapse failed: {e}")
            return None


def build_project_with_scenes(
    name: str,
    control_center_pars: List[CustomParameter],
    control_operators: List[Dict],
    scenes: List[Dict],
    output_dir: str
) -> Optional[Path]:
    """
    Build a complete project with control center and multiple scenes.

    Args:
        name: Project name
        control_center_pars: List of CustomParameter for control center
        control_operators: Operators inside control center
        scenes: List of scene specs, each with 'name', 'operators'
        output_dir: Output directory

    Returns:
        Path to created .tox file
    """
    # Build nested comp specs for scenes
    nested_comps = []
    for scene in scenes:
        scene_spec = {
            'name': scene['name'],
            'position': scene.get('position', (300, 0)),
            'inputs': ['control_center/out1'],  # Wire to control center output
            'operators': scene.get('operators', []),
            'custom_pars': scene.get('custom_pars', []),
        }
        nested_comps.append(scene_spec)

    # Build control center as a nested comp
    control_spec = {
        'name': 'control_center',
        'position': (0, 0),
        'operators': control_operators,
        'custom_pars': control_center_pars,
    }
    nested_comps.insert(0, control_spec)

    # Main project spec
    spec = {
        'name': name,
        'custom_pars': [],  # Main container doesn't need custom pars
        'operators': [
            # Scene selector
            {
                'name': 'scene_select',
                'type': 'switchTOP',
                'position': (600, 0),
                'inputs': [f'{s["name"]}/out1' for s in scenes],
            },
            # Output
            {
                'name': 'out1',
                'type': 'outTOP',
                'position': (800, 0),
                'inputs': ['scene_select'],
            },
        ],
        'nested_comps': nested_comps,
    }

    builder = ToxBuilderV3()
    return builder.build(spec, output_dir)


if __name__ == '__main__':
    # Test with a simple component
    test_pars = [
        CustomParameter(name='intensity', label='Intensity', par_type='Float',
                       default=0.8, min_val=0, max_val=1, page='Main', order=0),
        CustomParameter(name='speed', label='Speed', par_type='Float',
                       default=0.5, min_val=0, max_val=2, page='Main', order=1),
        CustomParameter(name='count', label='Count', par_type='Int',
                       default=10, min_val=1, max_val=100, page='Main', order=2),
    ]

    spec = {
        'name': 'test_v3',
        'custom_pars': test_pars,
        'operators': [
            {
                'name': 'noise1',
                'type': 'noiseTOP',
                'position': (0, 0),
                'flags': {'viewer': True},
            },
            {
                'name': 'level1',
                'type': 'levelTOP',
                'position': (200, 0),
                'inputs': ['noise1'],
                'parameters': {
                    'opacity': {'expr': 'parent().par.intensity', 'value': 1},
                },
            },
            {
                'name': 'out1',
                'type': 'outTOP',
                'position': (400, 0),
                'inputs': ['level1'],
            },
        ]
    }

    builder = ToxBuilderV3()
    result = builder.build(spec, './output')
    if result:
        print(f"\nTest passed: {result}")

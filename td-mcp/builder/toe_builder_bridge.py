"""
TOE Builder Bridge

Converts TD Designer's JSON output to actual TOE files.
Uses the file-driven pattern from build_teardrop.py.
Uses ground truth for parameter validation.
"""

import shutil
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml
import logging

from .ground_truth import get_ground_truth

logger = logging.getLogger(__name__)

# Paths
TOECOLLAPSE = r"C:\Program Files\Derivative\TouchDesigner\bin\toecollapse.exe"
TOEEXPAND = r"C:\Program Files\Derivative\TouchDesigner\bin\toeexpand.exe"
PALETTE_DIR = Path(r"C:\TD_Projects\Learn\Palette\Tools")
TD_PALETTE_DIR = Path(r"C:\Program Files\Derivative\TouchDesigner\Samples\Palette")
EXPERTISE_DIR = Path(__file__).parent / "expertise"


def load_conversion_op_expertise() -> dict:
    """Load conversion operator requirements from expertise file.

    This makes the builder self-improving - update the YAML to change behavior.
    """
    expertise_file = EXPERTISE_DIR / "td_network_building.yaml"
    conversion_ops = {}

    try:
        if expertise_file.exists():
            with open(expertise_file, 'r', encoding='utf-8') as f:
                expertise = yaml.safe_load(f)

            # Find the conversion operator params rule
            for rule in expertise.get("build_rules", []):
                if "conversion_operator_params" in rule:
                    for op_name, op_info in rule["conversion_operator_params"].items():
                        td_type = op_info.get("td_type", "")
                        required = op_info.get("required_param", "")
                        desc = op_info.get("description", "")
                        if td_type and required:
                            conversion_ops[td_type] = {
                                "required": required,
                                "description": desc
                            }
                    break
    except Exception as e:
        logger.warning(f"Could not load expertise: {e}, using defaults")

    # Fallback defaults if expertise not loaded
    if not conversion_ops:
        conversion_ops = {
            "CHOP:sopto": {"required": "sop", "description": "SOP operator path to convert"},
            "CHOP:topto": {"required": "top", "description": "TOP operator path to convert"},
            "CHOP:datto": {"required": "dat", "description": "DAT operator path to convert"},
            "TOP:chopto": {"required": "chop", "description": "CHOP operator path to convert"},
            "SOP:chopto": {"required": "chop", "description": "CHOP operator path to convert"},
            "DAT:chopto": {"required": "chop", "description": "CHOP operator path to convert"},
            "DAT:sopto": {"required": "sop", "description": "SOP operator path to convert"},
        }

    return conversion_ops


# Load once at module init, can be reloaded by calling load_conversion_op_expertise()
CONVERSION_OP_REQUIRED_PARAMS = load_conversion_op_expertise()


# Parameter name mapping (human-readable -> TD internal)
PARAM_NAME_MAP = {
    # Noise TOP
    "amplitude": "amp",
    "exponent": "exp",
    "harmonics": "harmon",
    "roughness": "rough",
    # Level TOP
    "brightness": "bright",
    "gamma": "gamma1",
    # Blur TOP
    "filtersize": "filterwidth",
    "size": "filterwidth",
    # Displace TOP
    "displaceamplitude": "displaceweight",
    # Bloom TOP
    "strength": "bloomstrength",
    "threshold": "bloomthresh",
    # Audio Filter CHOP
    "cutofffreq": "cutoff",
    "highfreq": "cutoffhigh",
    "filtertype": "filter",
    # Particles GPU
    "maxparticles": "maxparts",
    "emitrate": "birthrate",
    # Point Render
    "rendersize": "pointsize",
    "colorr": "cr",
    "colorg": "cg",
    "colorb": "cb",
    "alpha": "ca",
    # Force GPU
    "forcetype": "type",
    # Ramp TOP
    "type": "type",
    # Composite TOP
    "operand": "operand",
    "opacity": "opacity",
    # Resolution params
    "resolution": None,  # Special handling needed
    "numchannels": "channels",
    "device": "device",
    # Feedback
    "targetop": "top",
    # Lookup
    "colorlookup": "method",
    "preset": "preset",

    # === VANTA additions ===

    # Constant CHOP - channel names and values (TD uses const0name, const0value format)
    "name0": "const0name",
    "value0": "const0value",
    "name1": "const1name",
    "value1": "const1value",
    "name2": "const2name",
    "value2": "const2value",
    "name3": "const3name",
    "value3": "const3value",

    # Particle SOP
    "birthrate": "birthrate",
    "life": "life",
    "lifedur": "lifevar",
    "inherit": "inheritvel",

    # Force SOP
    "forcex": "forcex",
    "forcey": "forcey",
    "forcez": "forcez",

    # Add SOP
    "points": "points",

    # Limit SOP
    "miny": "miny",
    "minx": "minx",
    "minz": "minz",
    "maxy": "maxy",
    "maxx": "maxx",
    "maxz": "maxz",

    # Tube SOP
    "rad": "rad1",

    # Noise CHOP
    "channels": "channelname",

    # LFO CHOP
    "freq": "freq",

    # HSV Adjust TOP
    "satmult": "satmult",
    "valmult": "valmult",
    "huemult": "huemult",
    "hueoffset": "hueoff",
    "satoffset": "satoff",
    "valoffset": "valoff",
}

# Menu value mapping (label -> internal value)
MENU_VALUE_MAP = {
    # Noise types
    "perlin noise": "perlin2d",
    "perlin": "perlin2d",
    "simplex": "simplex3d",
    "sparse convolution": "sparse",
    "sparse": "sparse",
    # Ramp types
    "radial": "radial",
    "circular": "radial",
    "linear": "linear",
    # Analyze functions
    "average": "average",
    "maximum": "maximum",
    "minimum": "minimum",
    "rms": "rmspower",
    "rms power": "rmspower",
    # Audio filter types
    "bandpass": "bandpass",
    "lowpass": "lowpass",
    "highpass": "highpass",
    # Composite operands
    "add": "add",
    "over": "over",
    "screen": "screen",
    "multiply": "multiply",
    # Blur filter types
    "gaussian": "gaussian",
    "box": "box",
    "directional": "directional",
    # Force types
    "curl noise": "curlnoise",
    "curl": "curlnoise",
    # Lookup methods
    "preset": "preset",
    "dat": "dat",
}

# Operator type mapping (TD Designer type -> TouchDesigner family:type)
OP_TYPE_MAP = {
    # CHOPs
    "audiodevicein": "CHOP:audioDeviceIn",
    "audiospectrum": "CHOP:audioSpect",
    "audiofilter": "CHOP:audioFilter",
    "analyze": "CHOP:analyze",
    "beat": "CHOP:beat",
    "null": "CHOP:null",  # Default to CHOP, will be overridden by context
    "math": "CHOP:math",
    "lag": "CHOP:lag",
    "filter": "CHOP:filter",
    "select": "CHOP:select",
    "merge": "CHOP:merge",
    "constant_chop": "CHOP:constant",
    "noise_chop": "CHOP:noise",
    "out_chop": "CHOP:out",

    # TOPs
    "noise": "TOP:noise",
    "ramp": "TOP:ramp",
    "constant": "TOP:constant",
    "level": "TOP:level",
    "composite": "TOP:composite",
    "feedback": "TOP:feedback",
    "blur": "TOP:blur",
    "displace": "TOP:displace",
    "lookup": "TOP:lookup",
    "hsvadjust": "TOP:hsvAdjust",
    "hsvAdjust": "TOP:hsvAdjust",
    "bloom": "TOP:bloom",
    "out": "TOP:out",
    "null_top": "TOP:null",
    "switch": "TOP:switch",
    "threshold": "TOP:threshold",
    "reorder": "TOP:reorder",
    "render": "TOP:render",

    # SOPs
    "sphere": "SOP:sphere",
    "grid": "SOP:grid",
    "box": "SOP:box",
    "transform": "SOP:transform",
    "noise_sop": "SOP:noise",
    "particle": "SOP:particle",
    "force": "SOP:force",
    "add": "SOP:add",
    "limit": "SOP:limit",
    "tube": "SOP:tube",
    "point": "SOP:point",
    "convert": "SOP:convert",
    "circle": "SOP:circle",
    "line": "SOP:line",
    "copy": "SOP:copy",

    # COMPs
    "container": "COMP:container",
    "geo": "COMP:geometry",
    "geometry": "COMP:geometry",
    "camera": "COMP:camera",
    "light": "COMP:light",
    "base": "COMP:base",

    # CHOPs (additional)
    "lfo": "CHOP:lfo",
    "midiinCHOP": "CHOP:midiIn",
    "midiin": "CHOP:midiIn",

    # TOPs (additional)
    "resolution": "TOP:resolution",
    "transform_top": "TOP:transform",

    # DATs
    "text": "DAT:text",
    "table": "DAT:table",
    "script": "DAT:script",
    # DAT aliases for invented/alternate names
    "tabledatcreate": "DAT:table",
    "tabledat": "DAT:table",
    "createtable": "DAT:table",
    "textdat": "DAT:text",
    "scriptdat": "DAT:script",

    # Conversion operators (family-to-family)
    # DAT to CHOP
    "datto": "CHOP:datto",
    "dattochop": "CHOP:datto",
    # SOP to CHOP
    "sopto": "CHOP:sopto",
    "soptochop": "CHOP:sopto",
    # TOP to CHOP
    "topto": "CHOP:topto",
    "toptochop": "CHOP:topto",
    # CHOP to TOP
    "chopto": "TOP:chopto",
    "choptotop": "TOP:chopto",
    # CHOP to SOP
    "choptosop": "SOP:chopto",
    # CHOP to DAT
    "choptodat": "DAT:chopto",
    # SOP to DAT
    "soptodat": "DAT:sopto",

    # Particles (GPU)
    "particlesgpu": "COMP:particlesGpu",
    "forcegpu": "TOP:forceGpu",
    "pointrender": "TOP:pointRender",
}

# NOTE: CONVERSION_OP_REQUIRED_PARAMS is loaded from expertise at module init (see top of file)


class ToeBuilderBridge:
    """Bridge between TD Designer JSON and TOE file generation."""

    def __init__(self, output_dir: Path, verbose: bool = True):
        self.output_dir = Path(output_dir)
        self.verbose = verbose
        self.toc_entries = []
        self.project_dir = None
        self.connections = {}  # target_op -> [source_ops]
        self.expressions = {}  # op/param -> expression

    def log(self, msg: str):
        if self.verbose:
            print(msg)
        logger.info(msg)

    def build_from_design(self, design: dict, project_name: str = None) -> Optional[Path]:
        """
        Convert TD Designer's network_design JSON to TOE file.

        Args:
            design: The network_design dict from TD Designer output
            project_name: Override project name (default: from design)

        Returns:
            Path to generated .toe file, or None if failed
        """
        self.log("\n" + "=" * 60)
        self.log("Building TOE from TD Designer output")
        self.log("=" * 60)

        # Extract design data
        network = design.get("network_design", design)
        project_name = project_name or network.get("project", "untitled")

        # Setup directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.project_dir = self.output_dir / f"{project_name}.toe.dir"
        if self.project_dir.exists():
            shutil.rmtree(self.project_dir)
        self.project_dir.mkdir(parents=True)
        self.toc_entries = []

        # Build connection map
        self._build_connection_map(network.get("connections", []))

        # Build expression map
        self._build_expression_map(network.get("expressions", []))

        # 1. Write system files
        self._write_system_files()

        # 2. Write project container
        self._write_project_container(network)

        # 3. Write containers and operators
        containers = network.get("containers", [])
        for container in containers:
            self._write_container(container, "project1")

        # 3b. Write flat operators (directly under project1, no container)
        flat_operators = network.get("operators", [])
        if flat_operators:
            self.log(f"[3b/5] Writing {len(flat_operators)} flat operators...")
            for idx, op in enumerate(flat_operators):
                self._write_operator(op, "project1", idx)

        # 4. Write TOC
        toc_path = self._write_toc(project_name)

        # 5. Collapse to TOE
        toe_path = self._collapse(project_name)

        if toe_path:
            self.log("\n" + "=" * 60)
            self.log(f"[SUCCESS] Created: {toe_path}")
            self.log(f"         Size: {toe_path.stat().st_size} bytes")
            self.log("=" * 60)

        return toe_path

    def _build_connection_map(self, connections: list):
        """Build a map of target -> [sources] from connections list."""
        self.connections = {}
        for conn in connections:
            src = conn.get("from", "")
            dst = conn.get("to", "")
            if dst and src:
                if dst not in self.connections:
                    self.connections[dst] = []
                self.connections[dst].append(src)

    def _build_expression_map(self, expressions: list):
        """Build a map of op/param -> expression."""
        self.expressions = {}
        for expr in expressions:
            param_path = expr.get("parameter", "")
            expression = expr.get("expression", "")
            if param_path and expression:
                self.expressions[param_path] = expression

    def _write_system_files(self):
        """Write root-level system files for TOE."""
        self.log("\n[1/5] Writing system files...")

        self._write_file(".build", "version 099\nbuild 2023.11880\n")
        self._write_file(".start", "?\nperform 0 on\nrealtime 0 on\ncookrate 0 60\n?\n")
        self._write_file(".grps", "-2\n0\n")
        self._write_file(".root", "end\n")
        self._write_file(".parm", "?\n?\n")

        self.log("  Created 5 system files")

    def _write_project_container(self, network: dict):
        """Create main project container."""
        self.log("\n[2/5] Creating project container...")

        resolution = network.get("resolution", [1920, 1080])

        self._write_file("project1.n", """COMP:container
tile 0 0 500 400
flags =  parlanguage 0
end
""")
        self._write_file("project1.parm", f"""?
w 0 {resolution[0]}
h 0 {resolution[1]}
?
""")
        self._write_file("project1.panel", f"""?
screenw 0 {resolution[0]}
screenh 0 {resolution[1]}
?
""")

        (self.project_dir / "project1").mkdir(exist_ok=True)
        self.log("  Created project container")

    def _write_container(self, container: dict, parent_path: str):
        """Write a container and its operators."""
        name = container.get("name", "container")
        position = container.get("position", [0, 0])
        operators = container.get("operators", [])

        container_path = f"{parent_path}/{name}"

        self.log(f"  Creating container: {name} ({len(operators)} operators)")

        # Write container .n file
        self._write_file(f"{container_path}.n", f"""COMP:container
tile {position[0]} {position[1]} 200 150
flags =  parlanguage 0
end
""")

        # Write container .parm file
        self._write_file(f"{container_path}.parm", "?\n?\n")

        # Create container directory
        (self.project_dir / container_path).mkdir(parents=True, exist_ok=True)

        # Process container-internal connections (copy-paste friendly)
        # Expand local names to full paths and add to global connection map
        container_connections = container.get("connections", [])
        for conn in container_connections:
            src = conn.get("from", "")
            dst = conn.get("to", "")
            if src and dst:
                # Expand to full path if not already qualified
                if "/" not in src:
                    src = f"{name}/{src}"
                if "/" not in dst:
                    dst = f"{name}/{dst}"
                # Add to connection map
                if dst not in self.connections:
                    self.connections[dst] = []
                if src not in self.connections[dst]:
                    self.connections[dst].append(src)

        if container_connections:
            self.log(f"    Added {len(container_connections)} container connections")

        # Write operators
        for idx, op in enumerate(operators):
            self._write_operator(op, container_path, idx)

    def _write_operator(self, op: dict, container_path: str, idx: int):
        """Write a single operator."""
        name = op.get("name", f"op{idx}")
        op_type = op.get("type", "null")
        params = op.get("parameters", {})
        position = op.get("position", [idx * 150, 0])

        # Check for embed_tox - embeds a palette component
        embed_tox = op.get("embed_tox")
        if embed_tox:
            self._embed_palette_tox(embed_tox, name, container_path, position)
            return

        # Map to TouchDesigner type
        td_type = self._map_op_type(op_type, container_path)

        # Warn if conversion operator is missing required source parameter
        if td_type in CONVERSION_OP_REQUIRED_PARAMS:
            req_info = CONVERSION_OP_REQUIRED_PARAMS[td_type]
            req_param = req_info["required"]
            param_keys_lower = [p.lower() for p in params.keys()]
            if req_param not in params and req_param.lower() not in param_keys_lower:
                self.log(f"    [WARNING] {name} ({td_type}) missing required '{req_param}' parameter")
                self.log(f"              Hint: Add \"{req_param}\": \"<source_operator_name>\" to parameters")

        # Get inputs from connection map
        full_path = f"{container_path}/{name}"
        # Try multiple path formats for connection lookup
        short_path = full_path.replace("project1/", "")
        inputs = (self.connections.get(full_path, []) or
                  self.connections.get(short_path, []) or
                  self.connections.get(name, []))  # Also try just the operator name

        # Build .n file content
        n_content = f"""{td_type}
tile {position[0]} {position[1]} 130 90
flags =  parlanguage 0
"""

        if inputs:
            n_content += "inputs\n{\n"
            for i, src in enumerate(inputs):
                # Convert connection path to relative within container
                # container_path is like "project1/two_chops"
                # src from YAML is like "two_chops/noise1" or "julia1/out1"
                
                # Get container name without project1 prefix
                container_name = container_path.split("/")[-1] if "/" in container_path else container_path
                
                if src.startswith(container_name + "/"):
                    # Same container - strip container prefix
                    src_name = src[len(container_name) + 1:]
                elif "/" in src:
                    # Nested reference (e.g., "julia1/out1") - keep as-is
                    src_name = src
                else:
                    # Simple operator name
                    src_name = src
                n_content += f"{i}\t{src_name}\n"
            n_content += "}\n"

        n_content += "end\n"

        self._write_file(f"{full_path}.n", n_content)

        # Build .parm file content using ground truth validation
        parm_lines = ["?"]
        gt = get_ground_truth()

        for param_name, param_value in params.items():
            # Handle resolution specially
            if param_name.lower() == "resolution" and isinstance(param_value, (list, tuple)):
                parm_lines.append(f"resolutionw 0 {param_value[0]}")
                parm_lines.append(f"resolutionh 0 {param_value[1]}")
                continue

            # Handle vector parameter expansion: t, r, s, p, pivot → tx/ty/tz, rx/ry/rz, etc.
            vector_params = {
                # 3-component vectors (XYZ)
                't': ['tx', 'ty', 'tz'],
                'r': ['rx', 'ry', 'rz'],
                's': ['sx', 'sy', 'sz'],
                'p': ['px', 'py', 'pz'],
                'pivot': ['pivotx', 'pivoty', 'pivotz'],
                'scale': ['sx', 'sy', 'sz'],
                'translate': ['tx', 'ty', 'tz'],
                'rotate': ['rx', 'ry', 'rz'],
                'center': ['centerx', 'centery', 'centerz'],
                'size': ['sizex', 'sizey', 'sizez'],
                # 4-component vectors (RGBA)
                'color': ['colorr', 'colorg', 'colorb', 'colora'],
                'rgb': ['colorr', 'colorg', 'colorb'],
                'rgba': ['colorr', 'colorg', 'colorb', 'colora'],
                'bgcolor': ['bgcolorr', 'bgcolorg', 'bgcolorb', 'bgcolora'],
                # 2-component vectors (UV, WH)
                'uv': ['u', 'v'],
                'offset': ['offsetx', 'offsety'],
            }
            # Indexed params: fromrange, torange, const, fills → fromrange1/2, torange1/2, etc.
            indexed_params = {
                'fromrange': 'fromrange',
                'torange': 'torange',
                'const': 'const',
                'fills': 'fills',
            }
            # Expression patterns for detecting expression strings
            expr_patterns = ['op(', 'me.', 'parent.', 'parent(', 'mod.', 'ext.', 'iop.', 'ipar.',
                             'tdu.', 'absTime', 'me.time', "op('", 'op("', "chop('", 'chop("']

            if param_name.lower() in vector_params and isinstance(param_value, (list, tuple)):
                component_names = vector_params[param_name.lower()]
                for i, comp_name in enumerate(component_names):
                    if i < len(param_value):
                        comp_value = param_value[i]
                        # Check if component value is an expression
                        if isinstance(comp_value, str) and any(p in comp_value for p in expr_patterns):
                            parm_lines.append(f"{comp_name} 49 0 {comp_value}")
                        else:
                            td_value = self._format_param_value(comp_value)
                            parm_lines.append(f"{comp_name} 0 {td_value}")
                continue

            # Handle indexed params like fromrange: [0, 1] → fromrange1: 0, fromrange2: 1
            if param_name.lower() in indexed_params and isinstance(param_value, (list, tuple)):
                base_name = indexed_params[param_name.lower()]
                for i, val in enumerate(param_value):
                    indexed_name = f"{base_name}{i+1}"
                    if isinstance(val, str) and any(p in val for p in expr_patterns):
                        parm_lines.append(f"{indexed_name} 49 0 {val}")
                    else:
                        td_value = self._format_param_value(val)
                        parm_lines.append(f"{indexed_name} 0 {td_value}")
                continue

            # Handle expression dict format: {"expr": "...", "value": ...} or {"expression": "..."}
            inline_expression = None
            if isinstance(param_value, dict):
                inline_expression = param_value.get("expr") or param_value.get("expression")
                if inline_expression:
                    # Extract the constant value if provided, otherwise use 0
                    param_value = param_value.get("value", 0)
            elif isinstance(param_value, str):
                # Auto-detect expression strings containing TD Python patterns
                expr_patterns = ['op(', 'me.', 'parent.', 'parent(', 'mod.', 'ext.', 'iop.', 'ipar.',
                                 'tdu.', 'absTime', 'me.time', "op('", 'op("', "chop('", 'chop("']
                if any(pattern in param_value for pattern in expr_patterns):
                    inline_expression = param_value
                    param_value = 0  # Default value for expression parameters

            # Extract family from TD type (e.g., "CHOP:analyze" -> "CHOP")
            family = td_type.split(":")[0] if ":" in td_type else None

            # Validate parameter against ground truth
            validation = gt.validate_param(op_type, param_name, param_value, family=family)

            if not validation["valid"]:
                # Try fallback to manual map
                td_param_name = PARAM_NAME_MAP.get(param_name.lower())
                if td_param_name is None:
                    self.log(f"    Skipping unknown param: {param_name} for {op_type}")
                    continue
                td_value = self._format_param_value(param_value)
            else:
                td_param_name = validation["td_name"]
                td_value = validation["td_value"]
                if td_value is None:
                    td_value = self._format_param_value(param_value)
                elif isinstance(td_value, bool):
                    td_value = "on" if td_value else "off"
                else:
                    td_value = str(td_value)

            # Check if there's an expression for this param (inline or from expressions map)
            expr_key = f"{full_path.replace('project1/', '')}/{param_name}"
            alt_expr_key = f"{container_path.replace('project1/', '')}/{name}/{param_name}"

            expression = inline_expression or self.expressions.get(expr_key) or self.expressions.get(alt_expr_key)

            if expression:
                # Mode 49 = Python expression (mode 17 is for CHOP expressions)
                parm_lines.append(f"{td_param_name} 49 {td_value} {expression}")
            else:
                # Mode 0 = constant
                parm_lines.append(f"{td_param_name} 0 {td_value}")

        parm_lines.append("?")
        self._write_file(f"{full_path}.parm", "\n".join(parm_lines) + "\n")

        # Write .text file for DATs with script/text content
        script = op.get("script", "") or op.get("text", "")
        if script and "DAT" in td_type:
            # Table DAT uses binary .table file format
            if "table" in td_type.lower():
                # Parse TSV text into rows
                rows = []
                for line in script.strip().split('\n'):
                    rows.append(line.split('\t'))
                self._write_binary_table(f"{full_path}.table", rows)
            else:
                self._write_file(f"{full_path}.text", script)

        # Write .table file for Table DATs with content (2D array)
        # Accept multiple field names: content, rows, data, tableData
        content = op.get("content") or op.get("rows") or op.get("data") or op.get("tableData") or []
        if content and "DAT" in td_type and isinstance(content, list):
            self._write_binary_table(f"{full_path}.table", content)


    def _embed_palette_tox(self, tox_path: str, name: str, container_path: str, position: list):
        """Embed a palette TOX component by copying its expanded structure."""
        import tempfile
        
        # Resolve the tox path
        tox_file = Path(tox_path)
        if not tox_file.exists():
            # Try TD palette directory
            tox_file = TD_PALETTE_DIR / tox_path
        if not tox_file.exists():
            self.log(f"    [WARN] TOX not found: {tox_path}")
            return
        
        self.log(f"    Embedding palette TOX: {tox_file.name} as {name}")
        
        # Create temp directory for expansion
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            temp_tox = temp_path / tox_file.name
            shutil.copy(tox_file, temp_tox)
            
            # Expand the TOX
            result = subprocess.run(
                [TOEEXPAND, str(temp_tox)],
                capture_output=True,
                text=True,
                cwd=temp_path
            )
            
            expanded_dir = temp_path / f"{tox_file.name}.dir"
            if not expanded_dir.exists():
                self.log(f"    [ERROR] Failed to expand TOX: {result.stderr}")
                return
            
            # Find the root component directory (e.g., "julia")
            root_dirs = [d for d in expanded_dir.iterdir() if d.is_dir()]
            if not root_dirs:
                self.log("    [ERROR] No root component found in expanded TOX")
                return
            
            root_comp = root_dirs[0]
            root_comp_name = root_comp.name
            
            # Target path for the embedded component
            full_path = f"{container_path}/{name}"
            target_dir = self.project_dir / full_path
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy the inner content (e.g., julia/julia/* -> target/)
            inner_dir = root_comp / root_comp_name
            if inner_dir.exists() and inner_dir.is_dir():
                for item in inner_dir.iterdir():
                    if item.is_file():
                        rel_path = item.relative_to(expanded_dir)
                        # Adjust path: replace root/root with our target
                        dest_path = target_dir / item.name
                        shutil.copy(item, dest_path)
                        self.toc_entries.append(f"{full_path}/{item.name}")
                    elif item.is_dir():
                        dest_subdir = target_dir / item.name
                        shutil.copytree(item, dest_subdir)
                        for f in dest_subdir.rglob("*"):
                            if f.is_file():
                                rel = f.relative_to(self.project_dir)
                                self.toc_entries.append(str(rel).replace("\\", "/"))
            
            # Write the component .n file
            n_content = f"""COMP:base
tile {position[0]} {position[1]} 160 130
flags =  parlanguage 0
end
"""
            self._write_file(f"{full_path}.n", n_content)
            
            # Copy .cparm and .parm from root component (in root_comp/)
            for ext in [".cparm", ".parm", ".panel"]:
                src_file = root_comp / f"{root_comp_name}{ext}"
                if src_file.exists():
                    dest_file = self.project_dir / f"{full_path}{ext}"
                    shutil.copy(src_file, dest_file)
                    self.toc_entries.append(f"{full_path}{ext}")

    def _map_op_type(self, op_type: str, container_path: str) -> str:
        """Map TD Designer type to TouchDesigner family:type."""
        # Already in FAMILY:type format - return as-is
        families = ["CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP"]
        for family in families:
            if op_type.upper().startswith(f"{family}:"):
                # Already formatted, just normalize case: "chop:noise" -> "CHOP:noise"
                return f"{family}:{op_type[len(family)+1:]}"

        # Direct lookup
        if op_type in OP_TYPE_MAP:
            return OP_TYPE_MAP[op_type]

        # Try lowercase
        op_lower = op_type.lower()
        if op_lower in OP_TYPE_MAP:
            return OP_TYPE_MAP[op_lower]

        # Handle combined format like "noiseCHOP", "levelTOP", "mathCHOP", etc.
        # Pattern: {operatorName}{FAMILY} -> FAMILY:{operatorName}
        for family in families:
            if op_type.upper().endswith(family):
                base_type = op_type[:-len(family)]
                if base_type:
                    return f"{family}:{base_type}"
            # Also check lowercase suffix (e.g., "noiseChop")
            if op_lower.endswith(family.lower()):
                base_type = op_type[:-len(family)]
                if base_type:
                    return f"{family}:{base_type}"

        # Infer family from container name
        container_name = container_path.split("/")[-1].lower()
        if "audio" in container_name:
            return f"CHOP:{op_type}"
        elif "particle" in container_name:
            return f"TOP:{op_type}"
        elif any(x in container_name for x in ["visual", "core", "ray", "glitch", "composite"]):
            return f"TOP:{op_type}"

        # Default to TOP
        return f"TOP:{op_type}"

    def _format_param_value(self, value: Any) -> str:
        """Format parameter value for .parm file."""
        if isinstance(value, bool):
            return "on" if value else "off"
        elif isinstance(value, (list, tuple)):
            return " ".join(str(v) for v in value)
        elif isinstance(value, str):
            # Handle boolean-like strings
            if value.lower() in ["on", "off", "true", "false"]:
                return value.lower()
            # Map menu labels to internal values
            normalized = value.lower().strip()
            if normalized in MENU_VALUE_MAP:
                return MENU_VALUE_MAP[normalized]
            # Return lowercase for menu values (most TD menus use lowercase)
            return normalized
        else:
            return str(value)

    def _write_file(self, rel_path: str, content: str):
        """Write a file and add to TOC."""
        file_path = self.project_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8', newline='\n')
        self.toc_entries.append(rel_path)

    def _write_binary_table(self, rel_path: str, rows: list):
        """Write a binary .table file for Table DAT in TD's native format.

        Format discovered from working TD files:
        - Header: "1\n*" + 3 padding bytes + 4 uint32 fields (unknown1, rows, cols, unknown2)
        - Cell data: For each cell: type(4 bytes) + length(1 byte) + content + padding(3 bytes)
        """
        import struct

        file_path = self.project_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Ensure rows is 2D list
        if not rows:
            rows = [[""]]
        if not isinstance(rows[0], list):
            rows = [[str(cell) for cell in rows]]

        num_rows = len(rows)
        num_cols = max(len(row) for row in rows) if rows else 1

        # Build cell data
        cell_data = bytearray()
        for row in rows:
            for col_idx in range(num_cols):
                cell = str(row[col_idx]) if col_idx < len(row) else ""
                cell_bytes = cell.encode('utf-8')
                cell_len = len(cell_bytes)

                # Cell type (2 = string), then length byte, then string, then 3-byte padding
                cell_data.extend(struct.pack('<I', 2))  # type = 2 (string)
                cell_data.append(cell_len)  # length byte
                cell_data.extend(cell_bytes)  # string content
                # TD uses 3-byte padding after each cell content
                cell_data.extend(b'\x00\x00\x00')

        # Build header: "1\n*" + 3 padding + 4 uint32 fields
        header = bytearray()
        header.extend(b'1\n*')  # Version line with binary marker
        header.extend(b'\x00\x00\x00')  # 3 padding bytes to 4-byte align
        header.extend(struct.pack('<I', 1))  # Unknown field = 1
        header.extend(struct.pack('<I', num_rows))
        header.extend(struct.pack('<I', num_cols))
        header.extend(struct.pack('<I', 0))  # Unknown field = 0

        # Write binary file
        with open(file_path, 'wb') as f:
            f.write(header)
            f.write(cell_data)

        self.toc_entries.append(rel_path)

    def _write_toc(self, project_name: str) -> Path:
        """Write TOC file with correct ordering."""
        self.log("\n[4/5] Writing TOC...")

        def toc_sort_key(filepath):
            ext_priority = {'.n': 0, '.cparm': 1, '.parm': 2, '.panel': 3, '.network': 4}
            parts = filepath.rsplit('.', 1)
            if len(parts) == 2:
                ext = '.' + parts[1]
                base = parts[0]
            else:
                ext = ''
                base = filepath
            priority = ext_priority.get(ext, 5)
            depth = filepath.count('/') + filepath.count('\\')
            return (depth, base, priority, filepath)

        sorted_entries = sorted(self.toc_entries, key=toc_sort_key)
        toc_content = '\n'.join(sorted_entries) + '\n'

        toc_path = self.output_dir / f"{project_name}.toe.toc"
        toc_path.write_text(toc_content, encoding='utf-8', newline='\n')

        self.log(f"  Created TOC with {len(sorted_entries)} entries")
        return toc_path

    def _collapse(self, project_name: str) -> Optional[Path]:
        """Collapse to TOE file using toecollapse.exe."""
        self.log("\n[5/5] Collapsing to TOE...")

        toe_path = self.output_dir / f"{project_name}.toe"
        if toe_path.exists():
            toe_path.unlink()

        if not Path(TOECOLLAPSE).exists():
            self.log(f"[ERROR] toecollapse not found at: {TOECOLLAPSE}")
            return None

        # Pass the .toc file path, not the .dir directory
        toc_path = self.output_dir / f"{project_name}.toe.toc"
        result = subprocess.run(
            [TOECOLLAPSE, str(toc_path)],
            capture_output=True,
            text=True
        )

        # Check for subprocess errors
        if result.returncode != 0:
            self.log(f"[ERROR] toecollapse failed with return code {result.returncode}")
            if result.stderr:
                self.log(f"  stderr: {result.stderr}")
            return None

        if toe_path.exists() and toe_path.stat().st_size > 100:
            return toe_path
        else:
            self.log(f"[ERROR] Collapse failed: {result.stderr}")
            return None


def build_toe_from_design(
    design: dict,
    output_dir: Path,
    project_name: str = None
) -> Optional[Path]:
    """
    Convenience function to build TOE from TD Designer output.

    Args:
        design: TD Designer's network_design output (dict or YAML)
        output_dir: Directory to write output
        project_name: Optional project name override

    Returns:
        Path to generated .toe file, or None if failed
    """
    builder = ToeBuilderBridge(output_dir)
    return builder.build_from_design(design, project_name)


def build_toe_from_yaml(
    yaml_path: Path,
    output_dir: Path = None
) -> Optional[Path]:
    """
    Build TOE from TD Designer YAML output file.

    Args:
        yaml_path: Path to TD Designer YAML output
        output_dir: Output directory (default: same as yaml)

    Returns:
        Path to generated .toe file, or None if failed
    """
    with open(yaml_path, 'r') as f:
        design = yaml.safe_load(f)

    if output_dir is None:
        output_dir = yaml_path.parent

    return build_toe_from_design(design, output_dir)


# CLI for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python toe_builder_bridge.py <yaml_file> [output_dir]")
        sys.exit(1)

    yaml_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else yaml_path.parent

    result = build_toe_from_yaml(yaml_path, output_dir)

    if result:
        print(f"\nSuccess! Created: {result}")
    else:
        print("\nBuild failed!")
        sys.exit(1)

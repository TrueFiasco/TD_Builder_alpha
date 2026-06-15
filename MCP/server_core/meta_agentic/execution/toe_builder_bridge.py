"""
TOE Builder Bridge

Converts TD Designer's JSON output to actual TOE files.
Uses the file-driven pattern from build_teardrop.py.
Uses ground truth for parameter validation.
"""

import shutil
import subprocess
import re
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml
import logging

from .ground_truth import get_ground_truth
from .param_name_resolver import resolve_param_name, resolve_menu_value

logger = logging.getLogger(__name__)

# Paths
from paths import resolve_td_tool, td_tool_missing_error
TD_PALETTE_DIR = Path(r"C:\Program Files\Derivative\TouchDesigner\Samples\Palette")
EXPERTISE_DIR = Path(__file__).resolve().parents[4] / "Agents" / "expertise"

# DOCKED_DATS: the helper DATs each op auto-creates + docks during a live create().
# Live TD does this automatically; the offline builder didn't (F6 was a partial,
# info-only stop-gap). The full per-op spec (all 73 docked ops, captured from a live
# census) now lives in the KB at KB/docked_dats.json and is loaded by
# _load_docked_dats(); this dict is only the fallback used if that file is missing.
# Content DATs are file-backed (file + syncfile + loadonstart) so the shader/script
# lives on disk and is edited there, not poked through the MCP.
#   suffix/dat  : the docked op, named <host><suffix> to match TD
#   host_param  : host parameter that points at the child (host.pixeldat = child)
#   child_param : child parameter that points back at the host (info.op = host)
#   file_*/extension/stub : file-backing for content DATs; file_dir None = fileless
DOCKED_DATS = {
    "TOP:glsl": [
        {"suffix": "_pixel", "dat": "text", "host_param": "pixeldat",
         "file_dir": "shaders", "file_ext": "glsl", "extension": "frag", "flags": "viewer 1",
         "content": "pixel",
         "stub": "out vec4 fragColor;\nvoid main()\n{\n\tfragColor = vec4(0.0, 0.0, 0.0, 1.0);\n}\n"},
        {"suffix": "_info", "dat": "info", "child_param": "op",
         "file_dir": None, "flags": "viewer 1"},
        {"suffix": "_compute", "dat": "text", "host_param": "computedat",
         "file_dir": "shaders", "file_ext": "glsl", "extension": "comp",
         "flags": "viewer 1 showDocked off", "content": "compute",
         "stub": "layout (local_size_x = 8, local_size_y = 8) in;\nvoid main()\n{\n}\n"},
    ],
}

# KB path for the docked-DAT specs (companion to operators.json, PR-reviewable).
DOCKED_DATS_PATH = Path(__file__).resolve().parents[4] / "KB" / "docked_dats.json"
_DOCKED_DATS_CACHE = None


def _load_docked_dats() -> dict:
    """Load the per-op docked-DAT specs from KB/docked_dats.json (cached), mirroring
    param_name_resolver._load_kb(). Keyed by 'FAMILY:type' (e.g. 'TOP:glsl'). Falls
    back to the built-in DOCKED_DATS (TOP:glsl only) if the KB file is missing."""
    global _DOCKED_DATS_CACHE
    if _DOCKED_DATS_CACHE is None:
        try:
            with open(DOCKED_DATS_PATH, "r", encoding="utf-8") as f:
                _DOCKED_DATS_CACHE = json.load(f)
        except Exception as e:
            logger.warning("docked_dats.json not loaded (%s); using built-in fallback", e)
            _DOCKED_DATS_CACHE = DOCKED_DATS
    return _DOCKED_DATS_CACHE


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
    # CHOPs - Audio operators (TD internal names are LOWERCASE)
    # CRITICAL: TD requires lowercase internal names like CHOP:audiodevin, not CHOP:audioDeviceIn
    "audiodevicein": "CHOP:audiodevin",
    "audiodeviceinchop": "CHOP:audiodevin",  # OPSnippets/wiki format
    "audioDeviceIn": "CHOP:audiodevin",
    "AudioDeviceIn": "CHOP:audiodevin",
    "audio_device_in": "CHOP:audiodevin",
    "Audio_Device_In": "CHOP:audiodevin",  # Wiki doc format
    "audiodevice": "CHOP:audiodevin",  # Common abbreviation
    "audiodevin": "CHOP:audiodevin",  # Direct TD internal name
    "audiospectrum": "CHOP:audiospect",
    "audiospect": "CHOP:audiospect",  # Direct TD internal name
    "audiofilter": "CHOP:audiofilter",
    "audiofilein": "CHOP:audiofilein",
    "audiofileout": "CHOP:audiofileout",
    "audiodeviceout": "CHOP:audiodevout",
    "audiodevout": "CHOP:audiodevout",  # Direct TD internal name
    "audiobandeq": "CHOP:audiobandeq",
    "audiodynamics": "CHOP:audiodynamics",
    "audioparaeq": "CHOP:audioparaeq",
    "audiorender": "CHOP:audiorender",
    "audiooscillator": "CHOP:audioosc",
    "audioosc": "CHOP:audioosc",  # Direct TD internal name
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
    "composite": "TOP:comp",  # TD internal name is "comp", not "composite"
    "feedback": "TOP:feedback",
    "blur": "TOP:blur",
    "displace": "TOP:displace",
    "lookup": "TOP:lookup",
    "hsvadjust": "TOP:hsvadj",
    "hsvAdjust": "TOP:hsvadj",
    "hsvadj": "TOP:hsvadj",  # Direct TD internal name
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
    "null_sop": "SOP:null",
    "out_sop": "SOP:out",

    # COMPs
    "container": "COMP:container",
    "geo": "COMP:geometry",
    "geometry": "COMP:geometry",
    "camera": "COMP:camera",
    "light": "COMP:light",
    "base": "COMP:base",

    # CHOPs (additional)
    "lfo": "CHOP:lfo",
    "midiinCHOP": "CHOP:midiin",
    "midiin": "CHOP:midiin",
    "midiIn": "CHOP:midiin",  # Common variant
    "midiinmap": "CHOP:midiinmap",
    "midiout": "CHOP:midiout",

    # Family-specific aliases for ambiguous operators (40+ operators exist in multiple families)
    # These allow explicit type selection: noise_chop, constant_chop, etc.

    # CRITICAL: null (7 families), select (7 families)
    "null_top": "TOP:null",
    "null_chop": "CHOP:null",
    "null_sop": "SOP:null",
    "null_dat": "DAT:null",
    "null_comp": "COMP:null",
    "null_mat": "MAT:null",
    "select_chop": "CHOP:select",
    "select_top": "TOP:select",
    "select_sop": "SOP:select",
    "select_dat": "DAT:select",

    # HIGH: in, out, switch (6 families each)
    "in_chop": "CHOP:in",
    "in_top": "TOP:in",
    "in_sop": "SOP:in",
    "in_dat": "DAT:in",
    "out_chop": "CHOP:out",
    "out_top": "TOP:out",
    "out_sop": "SOP:out",
    "out_dat": "DAT:out",
    "switch_chop": "CHOP:switch",
    "switch_top": "TOP:switch",
    "switch_sop": "SOP:switch",
    "switch_dat": "DAT:switch",

    # MODERATE: blend, merge, noise, transform, script, limit, text, sort, glsl
    "blend_chop": "CHOP:blend",
    "blend_top": "TOP:blend",
    "blend_mat": "MAT:blend",
    "merge_chop": "CHOP:merge",
    "merge_sop": "SOP:merge",
    "noise_chop": "CHOP:noise",
    "noise_sop": "SOP:noise",
    "noise_top": "TOP:noise",
    "transform_sop": "SOP:transform",
    "transform_chop": "CHOP:transform",
    "script_chop": "CHOP:script",
    "script_sop": "SOP:script",
    "limit_chop": "CHOP:limit",
    "limit_sop": "SOP:limit",
    "text_top": "TOP:text",
    "text_sop": "SOP:text",
    "sort_chop": "CHOP:sort",
    "sort_sop": "SOP:sort",
    "sort_dat": "DAT:sort",
    # GLSL operators - many naming variants (Bug #1 fix)
    "glsl_top": "TOP:glsl",
    "glslTOP": "TOP:glsl",  # CamelCase variant
    "glsltop": "TOP:glsl",  # lowercase variant
    "glslTop": "TOP:glsl",  # mixed case variant
    "glsl": "TOP:glsl",     # base name defaults to TOP
    "glslmulti": "TOP:glslmulti",
    "glslmultiTOP": "TOP:glslmulti",
    "glslmulti_top": "TOP:glslmulti",
    "glsl_mat": "MAT:glsl",
    "glslMAT": "MAT:glsl",  # CamelCase variant
    "glslmat": "MAT:glsl",  # lowercase variant
    "cplusplus_chop": "CHOP:cplusplus",
    "cplusplus_top": "TOP:cplusplus",
    "cplusplus_sop": "SOP:cplusplus",
    "cplusplus_dat": "DAT:cplusplus",

    # COMMON: analyze, constant, level, math, lookup, cache, feedback
    "analyze_chop": "CHOP:analyze",
    "analyze_top": "TOP:analyze",
    "constant_chop": "CHOP:constant",
    "constant_top": "TOP:constant",
    "constant_mat": "MAT:constant",
    "level_chop": "CHOP:level",
    "level_top": "TOP:level",
    "math_chop": "CHOP:math",
    "math_sop": "SOP:math",
    "lookup_chop": "CHOP:lookup",
    "lookup_top": "TOP:lookup",
    "cache_chop": "CHOP:cache",
    "cache_top": "TOP:cache",
    "cache_sop": "SOP:cache",
    "feedback_chop": "CHOP:feedback",
    "feedback_top": "TOP:feedback",
    "copy_sop": "SOP:copy",
    "copy_dat": "DAT:copy",
    "delete_chop": "CHOP:delete",
    "delete_sop": "SOP:delete",
    "trail_chop": "CHOP:trail",
    "trail_sop": "SOP:trail",
    "convert_chop": "CHOP:convert",
    "convert_sop": "SOP:convert",
    "circle_sop": "SOP:circle",
    "circle_top": "TOP:circle",
    "line_chop": "CHOP:line",
    "line_sop": "SOP:line",
    "line_mat": "MAT:line",
    "clip_chop": "CHOP:clip",
    "clip_sop": "SOP:clip",
    "clip_top": "TOP:clip",
    "attribute_chop": "CHOP:attribute",
    "attribute_sop": "SOP:attribute",
    "reorder_chop": "CHOP:reorder",
    "reorder_top": "TOP:reorder",
    "force_sop": "SOP:force",

    # 2 FAMILIES but commonly confused
    # Composite TOP - TD internal name is "comp" (BUG-011 fix)
    "composite_top": "TOP:comp",
    "compositeTOP": "TOP:comp",
    "compTOP": "TOP:comp",
    "comp_top": "TOP:comp",
    "cross_chop": "CHOP:cross",
    "cross_sop": "SOP:cross",
    "function_chop": "CHOP:function",
    "grid_sop": "SOP:grid",
    "grid_top": "TOP:grid",
    "pattern_chop": "CHOP:pattern",
    "pattern_top": "TOP:pattern",
    "render_top": "TOP:render",
    "render_pass": "TOP:renderPass",
    "slope_chop": "CHOP:slope",
    "slope_sop": "SOP:slope",
    "sphere_sop": "SOP:sphere",

    # TOPs (additional)
    "resolution": "TOP:resolution",

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
        self.palette_io_map = {}  # Maps palette_name -> {"inputs": [...], "outputs": [...], "path": ...}
        self.container_io_map = {}  # BUG-C FIX: Maps container_name -> {"outputs": [...]} for regular containers

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

        # =================================================================
        # BUG-012 FIX: Extract table_data map for Table DAT operators
        # table_data is specified at design level, needs merging into operators
        # =================================================================
        self.table_data_map = network.get("table_data", {})

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
        """Build a map of target -> [sources] from connections list.

        BUG-B FIX: Also stores normalized palette paths.
        If dst is 'audioAnalysis/in1', also store under 'audioAnalysis'
        so palette embedding can find connections to palette inputs.
        """
        self.connections = {}
        for conn in connections:
            src = conn.get("from", "")
            dst = conn.get("to", "")
            if dst and src:
                if dst not in self.connections:
                    self.connections[dst] = []
                self.connections[dst].append(src)

                # BUG-B FIX: Normalize palette input paths
                # If dst contains /in followed by number or end, also store under base name
                # e.g., "audioAnalysis/in1" -> also store under "audioAnalysis"
                import re
                match = re.match(r'^(.+)/in\d*$', dst)
                if match:
                    base_name = match.group(1)
                    if base_name not in self.connections:
                        self.connections[base_name] = []
                    if src not in self.connections[base_name]:
                        self.connections[base_name].append(src)

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

        self._write_file(".build", "version 099\nbuild 2025.31760\ntime Fri Dec 20 10:00:00 2025\nosname Windows\nosversion 10\n")
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

        # Support flat, nested, and children formats:
        # Flat: {"operators": [...], "connections": [...]}
        # Nested: {"network": {"operators": [...], "connections": [...]}}
        # Children: {"children": [...]} - alternative operator specification
        network = container.get("network", {})
        # BUG-002 FIX: Also check for "children" field as alternative to "operators"
        operators = (container.get("operators", []) or
                     network.get("operators", []) or
                     container.get("children", []))

        container_path = f"{parent_path}/{name}"

        # Handle palette field - embed from KB lossless JSON
        palette_name = container.get("palette")
        if palette_name:
            self.log(f"  Embedding palette '{palette_name}' as container '{name}'")
            success = self._embed_palette_from_kb(palette_name, name, parent_path, position)
            if success:
                return  # Palette embedded, no need to create empty container
            else:
                self.log(f"    [WARN] Failed to embed palette '{palette_name}', creating empty container")

        self.log(f"  Creating container: {name} ({len(operators)} operators)")

        # Write container .n file
        self._write_file(f"{container_path}.n", f"""COMP:container
tile {position[0]} {position[1]} 200 150
flags =  parlanguage 0
end
""")

        # Write container .parm file
        self._write_file(f"{container_path}.parm", "?\n?\n")

        # BUG-K FIX: Write custom parameters if specified
        custom_pars = container.get("customPars", []) or container.get("custom_pars", [])
        if custom_pars:
            self._write_custom_parameters(container_path, custom_pars)

        # Create container directory
        (self.project_dir / container_path).mkdir(parents=True, exist_ok=True)

        # Process container-internal connections (copy-paste friendly)
        # Expand local names to full paths and add to global connection map
        # Support both flat and nested network format
        container_connections = container.get("connections", []) or network.get("connections", [])
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

        # Write operators and track out operators for BUG-C
        out_operators = []
        for idx, op in enumerate(operators):
            self._write_operator(op, container_path, idx)
            # Track out operators for container output resolution
            op_type = op.get("type", "").lower()
            if op_type in ["out", "out1"]:
                out_operators.append({"name": op.get("name", f"out{idx}"), "family": op.get("family", "")})

        # BUG-C FIX: Store container output info for source resolution
        if out_operators:
            self.container_io_map[name] = {"outputs": out_operators}
            self.log(f"    Tracked {len(out_operators)} out operators in container '{name}'")

        # BUG-J FIX: Recursively process nested containers
        nested_containers = container.get("containers", []) or network.get("containers", [])
        for nested in nested_containers:
            self._write_container(nested, container_path)

    def _write_operator(self, op: dict, container_path: str, idx: int):
        """Write a single operator."""
        name = op.get("name", f"op{idx}")
        op_type = op.get("type", "null")
        op_family = op.get("family")  # Extract explicit family field
        params = op.get("parameters", {}).copy()  # Copy to avoid mutating original
        position = op.get("position", [idx * 150, 0])

        # =================================================================
        # BUG-002 FIX PART 2: Detect COMP operators with children
        # If operator is a container type (container, panel, geo, base, etc.)
        # AND has children/operators, delegate to _write_container
        # =================================================================
        comp_types = ["container", "panel", "geo", "geometry", "base", "light", "camera",
                      "null_comp", "window", "widget", "field", "button", "slider", "list"]
        has_children = op.get("children", []) or op.get("operators", []) or op.get("network", {})
        is_comp_type = (op_type.lower() in comp_types or
                        op_type.lower().startswith("comp:") or
                        (op_family and op_family.upper() == "COMP"))

        if is_comp_type and has_children:
            self.log(f"    Detected COMP with children: {name} - delegating to _write_container")
            self._write_container(op, container_path)
            return

        # =================================================================
        # OPERATOR-LEVEL EXPRESSIONS - Merge into params with expression mode
        # Supports: {"expressions": {"sx": "op('null1')['scale']", ...}}
        # =================================================================
        op_expressions = op.get("expressions", {})
        for param_name, expr in op_expressions.items():
            if param_name not in params:
                # New param with expression, default value 0
                params[param_name] = {"expr": expr, "value": 0}
            elif isinstance(params[param_name], dict):
                # Already a dict, add/override expression
                params[param_name]["expr"] = expr
            else:
                # Preserve existing constant value, add expression
                params[param_name] = {"expr": expr, "value": params[param_name]}

        # =================================================================
        # PALETTE EMBEDDING - Three options in priority order
        # =================================================================

        # Option 1: "palette" field - PRIMARY method using KB lossless JSON (264 components)
        # Usage: {"name": "audio", "palette": "audioAnalysis"}
        palette_component = op.get("palette")
        if palette_component:
            success = self._embed_palette_from_kb(palette_component, name, container_path, position)
            if success:
                return
            else:
                self.log(f"    [WARN] Palette '{palette_component}' not in KB, trying legacy embed_tox")
                # Fall through to try legacy method or create placeholder

        # Option 2: "embed_tox" field - LEGACY method (unreliable, requires tox expansion)
        # Usage: {"name": "audio", "embed_tox": "Tools/audioAnalysis.tox"}
        embed_tox = op.get("embed_tox")
        if embed_tox:
            self.log(f"    [WARN] embed_tox is UNRELIABLE - prefer 'palette' field for KB embedding")
            self._embed_palette_tox(embed_tox, name, container_path, position)
            return

        # Option 3: "palette_runtime" field - Python script loading at TD startup
        # Usage: {"name": "audio", "palette_runtime": {"component": "audioAnalysis", "path": "Tools/audioAnalysis.tox"}}
        # This creates a Text DAT that loads the palette when the project opens
        palette_runtime = op.get("palette_runtime")
        if palette_runtime:
            self._create_palette_loader_dat(container_path, [
                {
                    "name": palette_runtime.get("component", name),
                    "path": palette_runtime.get("path", f"Tools/{name}.tox"),
                    "target_name": name,
                    "x": position[0],
                    "y": position[1]
                }
            ])
            return

        # =================================================================
        # STANDARD OPERATOR BUILDING
        # =================================================================

        # Map to TouchDesigner type (pass explicit family if provided)
        td_type = self._map_op_type(op_type, container_path, op_family)

        # Warn if conversion operator is missing required source parameter
        if td_type in CONVERSION_OP_REQUIRED_PARAMS:
            req_info = CONVERSION_OP_REQUIRED_PARAMS[td_type]
            req_param = req_info["required"]
            param_keys_lower = [p.lower() for p in params.keys()]
            if req_param not in params and req_param.lower() not in param_keys_lower:
                self.log(f"    [WARNING] {name} ({td_type}) missing required '{req_param}' parameter")
                self.log(f"              Hint: Add \"{req_param}\": \"<source_operator_name>\" to parameters")

        # Check for GLSL TOP with uniforms - use special parm builder
        glsl_uniforms = op.get("uniforms", [])
        is_glsl_top = td_type in ("TOP:glsl", "TOP:glslmulti", "TOP:glslTOP")

        # Live create() auto-docks an op's helper DATs (GLSL shader/info DATs, callback
        # script DATs, table DATs, ...); the offline builder must replicate it. Driven by
        # the docked_dats KB (KB/docked_dats.json) for ANY op with a spec -- the builder
        # creates + docks + file-links the children and wires the host's link params
        # (callbacks/pixeldat/dat/...) to them; experts only author the content. Wiring is
        # collected here and written raw into the host .parm below (see docked_wiring).
        docked_wiring = {}
        docked_specs = _load_docked_dats().get(td_type)
        if docked_specs:
            docked_wiring = self._write_docked_dats(name, container_path, position, td_type, op)
            for hp, child in docked_wiring.items():
                op.setdefault("parameters", {})[hp] = child   # for _build_glsl_parm (reads op[...])
        elif "glsl" in td_type.lower():
            self._write_docked_info_dat(name, container_path, position)  # defensive: glsl needs an info DAT

        # Get inputs from connection map
        full_path = f"{container_path}/{name}"
        # Try multiple path formats for connection lookup
        short_path = full_path.replace("project1/", "")

        # =================================================================
        # BUG-011 FIX: Container-relative path lookup
        # Connections stored as "container_name/op_name" (e.g., "test_container/math1")
        # But lookup uses full path (e.g., "project/test_container/math1")
        # Add container-relative path to lookup chain
        # =================================================================
        container_name = container_path.split("/")[-1] if "/" in container_path else container_path
        container_relative = f"{container_name}/{name}"

        inputs = (self.connections.get(full_path, []) or
                  self.connections.get(short_path, []) or
                  self.connections.get(container_relative, []) or  # BUG-011 FIX
                  self.connections.get(name, []))  # Also try just the operator name

        # Resolve palette sources to internal output operators
        if inputs:
            inputs = [self._resolve_palette_source(src) for src in inputs]

        # =================================================================
        # BUG-013 FIX: Auto-populate conversion operator params from wire inputs
        # Conversion operators (sopToCHOP, chopToTOP, etc.) need explicit source
        # parameter. If wired but param not set, auto-populate from first input.
        # =================================================================
        if td_type in CONVERSION_OP_REQUIRED_PARAMS and inputs:
            req_info = CONVERSION_OP_REQUIRED_PARAMS[td_type]
            req_param = req_info["required"]
            param_keys_lower = [p.lower() for p in params.keys()]

            if req_param not in params and req_param.lower() not in param_keys_lower:
                # Extract source operator name from first input
                source_path = inputs[0]
                source_name = source_path.split("/")[-1] if "/" in source_path else source_path
                # REGRESSION FIX: Wrap in op('...') for expression mode (mode 49)
                # Conversion operator params (dat, sop, chop, top) need expression syntax
                params[req_param] = f"op('{source_name}')"
                self.log(f"    Auto-populated {name}.{req_param} = op('{source_name}') from wire input")

        # =================================================================
        # BUG FIX: sopToCHOP default to Position-only sampling
        # Unless attribscope is already set, default to "P" (position only)
        # This prevents unwanted normal/UV channels from being generated
        # =================================================================
        if td_type == "CHOP:sopto":
            if "attribscope" not in params and "attscope" not in params:
                params["attribscope"] = "P"
                self.log(f"    Auto-set {name}.attribscope = P (position-only default)")

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

        # GLSL TOP with uniforms: Use special parm builder
        if is_glsl_top and glsl_uniforms:
            self._build_glsl_parm(op, full_path)
            return  # Skip regular parm generation

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

            # BUG-001 FIX: Use KB-derived param name resolver
            # Correctly maps user-friendly names to TD internal names
            op_type_short = op_type.split(':')[-1] if ':' in op_type else op_type
            td_param_name = resolve_param_name(op_type_short, family or "", param_name)

            # Validate parameter against ground truth (using resolved name)
            validation = gt.validate_param(op_type, td_param_name, param_value, family=family)

            if not validation["valid"]:
                # Use resolved name directly and format value
                td_value = self._format_param_value(param_value)
                # Handle menu values (convert int to string for menu params)
                td_value = resolve_menu_value(td_param_name, param_value)
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

        # Wire host -> its docked children (callbacks/pixeldat/computedat/dat/...). Written
        # raw (mode 0, sibling name) to match TD's serialization (e.g. `dat 0 ramp1_keys`),
        # bypassing param validation -- these are builder-owned links, not authored params.
        for hp, child in docked_wiring.items():
            parm_lines.append(f"{hp} 0 {child}")

        parm_lines.append("?")
        self._write_file(f"{full_path}.parm", "\n".join(parm_lines) + "\n")

        # Write .text file for DATs with script/text content
        # Accept multiple field names: script, text, textContent, content
        script = op.get("script", "") or op.get("text", "") or op.get("textContent", "") or op.get("content", "") or ""
        if script and "DAT" in td_type:
            # Table DAT uses binary .table file format
            if "table" in td_type.lower():
                # Parse TSV text into rows
                rows = []
                for line in script.strip().split('\n'):
                    rows.append(line.split('\t'))
                self._write_binary_table(f"{full_path}.table", rows)
            else:
                # Use binary format for .text files (required for GLSL shaders)
                self._write_binary_text(f"{full_path}.text", script)

        # Write .table file for Table DATs with content (2D array)
        # Accept multiple field names: content, rows, data, tableData
        # BUG-012 FIX: Also check design-level table_data_map
        content = (op.get("content") or op.get("rows") or op.get("data") or 
                   op.get("tableData") or 
                   getattr(self, 'table_data_map', {}).get(name, []))
        if content and "DAT" in td_type and isinstance(content, list):
            self._write_binary_table(f"{full_path}.table", content)

        # BUG-003 FIX: Write custom parameters if operator is a base COMP
        # Custom parameters are stored in .cparm files and only apply to base COMPs
        if td_type == "COMP:base" or "base" in td_type.lower():
            custom_pars = op.get("customPages", []) or op.get("customPars", [])
            if custom_pars:
                self._write_custom_parameters(full_path, custom_pars)
                self.log(f"    Created {len(custom_pars)} custom parameters on {name}")

    def _write_docked_dats(self, host_name, container_path, position, td_type, op):
        """Create + dock the helper DATs a live create() makes for this op, per the
        docked_dats KB spec (KB/docked_dats.json). Generalizes the original GLSL-only F6:
          - text DATs  (shaders/scripts): file-backed, language spec-driven (glsl/python/text)
          - table DATs (data):            file-backed (file + syncfile + loadonstart), no language
          - info DATs:                    fileless, child.op -> host
          - other (e.g. dmxmap):          fileless, child_param -> host (best-effort)
        Content/table DATs are file-backed so they live on disk and are edited there. The
        author-provided content (the expert's shader/script) goes to the matching role; every
        other child gets the spec's default stub. Returns {host_param: child} for the caller
        to wire the host's link params (written raw into the host .parm).
        """
        specs = _load_docked_dats().get(td_type, [])
        wiring = {}
        if not specs:
            return wiring
        family = td_type.split(":")[0] if ":" in td_type else "DAT"
        pos = position or [0, 0]
        offsets = [(0, -120), (160, -120), (320, -120), (480, -120)]
        for i, spec in enumerate(specs):
            child = host_name + spec["suffix"]
            child_rel = f"{container_path}/{child}"
            if (self.project_dir / f"{child_rel}.n").exists():
                continue  # don't clobber a DAT the design already provided
            # Respect design-provided wiring: if the design already set this child's link
            # param (e.g. pixeldat -> a hand-authored Text DAT), don't auto-dock a competing
            # child for that role -- otherwise the host .parm gets two `pixeldat` lines and
            # TD's last-wins leaves the host pointing at our stub. (The shader-field path
            # doesn't set the link param, so it still auto-docks normally.)
            hp = spec.get("host_param")
            if hp and (op.get("parameters") or {}).get(hp):
                self.log(f"    [docking] {host_name}: design sets {hp}={op['parameters'][hp]}; "
                         f"skipping auto-dock of {spec['suffix']}")
                continue
            ox, oy = offsets[i] if i < len(offsets) else (160 * i, -120)
            ix, iy = pos[0] + ox, pos[1] + oy
            flags = spec.get("flags", "viewer 1")
            dat = spec["dat"]
            if dat == "info":
                n = (f"DAT:info\ntile {ix} {iy} 130 90\nflags =  {flags} parlanguage 0\n"
                     f"color 0.67 0.67 0.67 \ndock {host_name}\nend\n")
                parm = f"?\nop 0 {host_name}\nlanguage 0 text\n?\n"
            elif dat in ("text", "table"):
                content = self._authored_for_role(op, spec.get("role", "")) or spec.get("stub", "")
                fdir = self.output_dir / spec["file_dir"]
                fdir.mkdir(parents=True, exist_ok=True)
                fpath = fdir / f"{child}.{spec['file_ext']}"
                fpath.write_text(content, encoding="utf-8", newline="\n")
                fabs = str(fpath.resolve()).replace("\\", "/")
                n = (f"DAT:{dat}\ntile {ix} {iy} 130 90\nflags =  {flags} parlanguage 0\n"
                     f"color 0.67 0.67 0.67 \ndock {host_name}\nend\n")
                parm = f"?\nfile 0 {fabs}\nsyncfile 0 on\nloadonstart 0 on\n"
                if dat == "text":
                    parm += f"language 0 {spec.get('language') or 'text'}\n"
                    if spec.get("extension"):
                        parm += f"extension 0 {spec['extension']}\n"
                parm += "?\n"
            else:
                # special docked op (e.g. dmxmap): fileless, child points back at host
                n = (f"{family}:{dat}\ntile {ix} {iy} 130 90\nflags =  {flags} parlanguage 0\n"
                     f"color 0.67 0.67 0.67 \ndock {host_name}\nend\n")
                parm = "?\n"
                if spec.get("child_param"):
                    parm += f"{spec['child_param']} 0 {host_name}\n"
                parm += "?\n"
                self.log(f"    [docking] note: special docked type '{dat}' on {host_name} "
                         f"({child}) written best-effort -- verify")
            self._write_file(f"{child_rel}.n", n)
            self._write_file(f"{child_rel}.parm", parm)
            if spec.get("host_param"):
                wiring[spec["host_param"]] = child
        self.log(f"    [docking] {host_name}: {[s['suffix'] for s in specs]}")
        return wiring

    def _authored_for_role(self, op: dict, role: str):
        """Return the author-provided content for a docked child's role (the shader/script
        the expert wrote in the design), or None to fall back to the spec's default stub.
        The design may name it by role or a common alias (e.g. role 'pixel' <- op['shader'])."""
        role_fields = {
            "pixel":     ["shader", "pixel", "pixelshader", "fragment", "frag", "text"],
            "compute":   ["compute", "computeshader"],
            "vertex":    ["vertex", "vertexshader", "vert"],
            "callbacks": ["callbacks", "script", "callback"],
            "rules":     ["rules"],
        }
        for field in role_fields.get(role, [role]):
            val = op.get(field)
            if val:
                return val
        return None

    def _write_docked_info_dat(self, host_name: str, container_path: str, host_position: list):
        """Emit a docked Info DAT for a GLSL op (F6).

        TouchDesigner auto-creates a docked Info DAT (plus the shader DATs) whenever
        a GLSL TOP/POP/MAT is made via create(). The offline builder serializes the
        .tox directly and never calls create(), so it omitted the Info DAT -- the one
        place GLSL compile errors surface. This writes the same docked Info DAT the UI
        would: a `.n` carrying `dock <host>` and a `.parm` carrying `op 0 <host>`, with
        the host referenced by relative sibling name (matches TD's own serialization).
        """
        if not hasattr(self, "_auto_info_hosts"):
            self._auto_info_hosts = set()
        key = f"{container_path}/{host_name}"
        if key in self._auto_info_hosts:
            return
        info_rel = f"{container_path}/{host_name}_info"
        # Don't clobber an Info DAT the design already provided for this op.
        if (self.project_dir / f"{info_rel}.n").exists():
            return
        self._auto_info_hosts.add(key)
        pos = host_position or [0, 0]
        ix, iy = pos[0] + 160, pos[1] - 120
        n_content = (
            "DAT:info\n"
            f"tile {ix} {iy} 130 90\n"
            "flags =  viewer 1 parlanguage 0\n"
            "color 0.67 0.67 0.67 \n"
            f"dock {host_name}\n"
            "end\n"
        )
        parm_content = f"?\nop 0 {host_name}\nlanguage 0 text\n?\n"
        self._write_file(f"{info_rel}.n", n_content)
        self._write_file(f"{info_rel}.parm", parm_content)
        self.log(f"    [F6] Auto-added docked Info DAT '{host_name}_info' -> {host_name}")

    def _build_glsl_parm(self, op: dict, full_path: str):
        """Build .parm file for GLSL TOP with uniforms.

        GLSL TOP uniforms use special format in .parm files (Bug #8 fix):
        - vec{N}name: Uniform name (mode 0)
        - vec{N}valuex/y/z/w: 4 components for vec4

        Mode values:
        - 0 = constant
        - 32 = default/reference value (seen in TD examples)
        - 49 = Python expression

        Example from TD OPSnippets (glslTOP.tox.dir/glslTOP/glsl4.parm):
            vec0name 0 iResolution
            vec0valuex 32 1
            vec0valuey 32 1.5
            vec0valuez 32 0
            vec0valuew 32 0
            vec2name 0 iGlobalTime
            vec2valuex 49 1 absTime.seconds/100
        """
        lines = ["?"]
        params = op.get("parameters", {})
        uniforms = op.get("uniforms", [])

        self.log(f"    Building GLSL parm with {len(uniforms)} uniforms")

        # Shader DAT reference (pixeldat or shader_dat)
        shader_dat = params.get("pixeldat") or params.get("shader_dat") or op.get("shader_dat")
        if shader_dat:
            lines.append(f"pixeldat 0 {shader_dat}")

        # Resolution
        if "resolutionw" in params:
            lines.append(f"resolutionw 0 {params['resolutionw']}")
        if "resolutionh" in params:
            lines.append(f"resolutionh 0 {params['resolutionh']}")

        # Other standard parameters
        for pname, pval in params.items():
            if pname not in ("pixeldat", "shader_dat", "resolutionw", "resolutionh"):
                lines.append(f"{pname} 0 {pval}")

        # Process uniforms array -> vec#name, vec#valuex/y/z/w format
        for idx, uni in enumerate(uniforms):
            name = uni.get("name", f"uniform{idx}")
            value = uni.get("value", 0)
            expr = uni.get("expr") or uni.get("expression")

            # Normalize value to 4-component list
            if isinstance(value, (int, float)):
                values = [value, 0, 0, 0]
            elif isinstance(value, (list, tuple)):
                values = list(value) + [0] * (4 - len(value))
            else:
                values = [0, 0, 0, 0]

            # Uniform name: vec{N}name
            lines.append(f"vec{idx}name 0 {name}")

            # Value components: vec{N}valuex, vec{N}valuey, vec{N}valuez, vec{N}valuew
            for i, comp in enumerate(['x', 'y', 'z', 'w']):
                v = values[i] if i < len(values) else 0

                # Check for expression (single string applies to first component)
                comp_expr = None
                if isinstance(expr, str) and i == 0:
                    comp_expr = expr
                elif isinstance(expr, dict):
                    comp_expr = expr.get(comp)
                elif isinstance(expr, list) and i < len(expr):
                    comp_expr = expr[i]

                if comp_expr:
                    # Mode 49 = Python expression
                    lines.append(f"vec{idx}value{comp} 49 {v} {comp_expr}")
                else:
                    # Mode 0 = constant (TD sometimes uses 32 for reference values)
                    lines.append(f"vec{idx}value{comp} 0 {v}")

        lines.append("?")
        self._write_file(f"{full_path}.parm", "\n".join(lines) + "\n")

    # =========================================================================
    # KB PALETTE EMBEDDING (Primary method - uses pre-parsed lossless JSON)
    # =========================================================================

    def _load_palette_from_kb(self, component_name: str) -> dict:
        """Load pre-parsed palette component from KB lossless JSON.

        Args:
            component_name: Name of the palette component (e.g., 'audioAnalysis', 'noise', 'bloom')

        Returns:
            dict: Lossless JSON data or None if not found
        """
        # Local KB path (self-contained in META_AGENTIC_TOOL/data/)
        # Use relative path from this file's location
        project_root = Path(__file__).parent.parent.parent
        kb_path = project_root / "data" / "palette_lossless"

        # Try gzipped format first (new format), then plain JSON (legacy)
        import gzip
        import json
        gz_file = kb_path / f"{component_name}.json.gz"
        json_file = kb_path / f"{component_name}_lossless.json"

        if gz_file.exists():
            try:
                with gzip.open(gz_file, 'rt', encoding='utf-8') as f:
                    data = json.load(f)
                    self.log(f"    Loaded palette from KB: {gz_file.name}")
                    return data
            except Exception as e:
                self.log(f"    [WARN] Failed to load KB palette: {e}")
        elif json_file.exists():
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.log(f"    Loaded palette from KB: {json_file.name}")
                    return data
            except Exception as e:
                self.log(f"    [WARN] Failed to load KB palette: {e}")

        self.log(f"    [WARN] Palette component '{component_name}' not found in KB")
        return None

    def _embed_palette_from_kb(self, component_name: str, target_name: str, container_path: str, position: list):
        """Embed palette component from KB lossless JSON.

        This is the PRIMARY method for embedding palette components. It uses
        pre-parsed lossless JSON from the knowledge base which contains all
        operator data, parameters, and extra files (text content, etc.).

        Args:
            component_name: KB palette component name (e.g., 'audioAnalysis')
            target_name: Name to give the component in the network
            container_path: Parent container path (e.g., 'project1')
            position: [x, y] position in the network
        """
        palette_data = self._load_palette_from_kb(component_name)
        if not palette_data:
            self.log(f"    [ERROR] Cannot embed '{component_name}' - not found in KB")
            return False

        operators = palette_data.get("operators", {})
        if not operators:
            self.log(f"    [ERROR] No operators in palette data for '{component_name}'")
            return False

        # Palette structure: /componentName is root, /componentName/... are children
        root_path = f"/{component_name}"

        # Target path for embedded component
        full_target_path = f"{container_path}/{target_name}"
        target_dir = self.project_dir / full_target_path
        target_dir.mkdir(parents=True, exist_ok=True)

        self.log(f"    Embedding palette from KB: {component_name} -> {target_name}")

        # Detect in/out operators from direct children (path depth = 2, e.g., /audioAnalysis/in1)
        in_operators = []
        out_operators = []
        for op_path, op_data in operators.items():
            # Only check direct children (2 path segments: /root/child)
            if op_path.count('/') == 2 and op_path.startswith(root_path + "/"):
                op_type = op_data.get('op_type', '')
                op_name = op_data.get('name', '')

                # Detect input operators (CHOP:in, TOP:in, etc.) but not info operators
                if ':in' in op_type.lower() and 'info' not in op_type.lower():
                    family = op_type.split(':')[0]
                    in_operators.append({'name': op_name, 'family': family, 'type': op_type})
                # Detect output operators (CHOP:out, TOP:out, etc.)
                elif ':out' in op_type.lower():
                    family = op_type.split(':')[0]
                    out_operators.append({'name': op_name, 'family': family, 'type': op_type})

        # Store palette I/O info for connection resolution
        self.palette_io_map[target_name] = {
            'inputs': sorted(in_operators, key=lambda x: x['name']),  # Sort by name (in1, in2, etc.)
            'outputs': sorted(out_operators, key=lambda x: x['name']),
            'path': full_target_path
        }

        if in_operators or out_operators:
            self.log(f"    Detected I/O: {len(in_operators)} inputs, {len(out_operators)} outputs")

        # Process each operator from the lossless JSON
        ops_written = 0
        for op_path, op_data in operators.items():
            if op_path == root_path:
                # Root component - write with position
                self._write_operator_from_lossless(
                    full_target_path, op_data, position, is_root=True
                )
                ops_written += 1
            elif op_path.startswith(root_path + "/"):
                # Child operator - strip root prefix and write
                rel_path = op_path[len(root_path) + 1:]  # Strip "/componentName/"
                child_path = f"{full_target_path}/{rel_path}"
                self._write_operator_from_lossless(child_path, op_data, None)
                ops_written += 1
            # else: skip paths that don't match (shouldn't happen)

        self.log(f"    Wrote {ops_written} operators from palette KB")

        # Write .network file to route external connections to internal in operators
        self._write_palette_network_file(target_name, container_path, in_operators)

        return True

    def _write_palette_network_file(self, palette_name: str, container_path: str, in_operators: list):
        """Write .network file to route external connections to palette's internal in operators.

        Format (verified from human examples):
        ```
        1
        compinputs
        {
        0 	external_source_op
        	in1
        	TOP
        }
        end
        ```
        """
        full_path = f"{container_path}/{palette_name}"

        # Check for external connections TO this palette
        external_sources = self.connections.get(palette_name, [])

        # Also try with full path variations
        if not external_sources:
            short_path = full_path.replace("project1/", "")
            external_sources = self.connections.get(short_path, [])

        if not external_sources or not in_operators:
            return  # No external connections or no in operators

        lines = ["1", "compinputs", "{"]

        for idx, source in enumerate(external_sources):
            if idx < len(in_operators):
                in_op = in_operators[idx]
                # Format: index<tab>source, then indented target, then indented family
                lines.append(f"{idx} \t{source}")
                lines.append(f"\t{in_op['name']}")
                lines.append(f"\t{in_op['family']}")

        lines.extend(["}", "end"])

        self._write_file(f"{full_path}.network", "\n".join(lines) + "\n")
        self.log(f"    Wrote .network file with {len(external_sources)} external connection(s)")

    def _resolve_palette_source(self, source: str) -> str:
        """Resolve a palette or container source to its internal output operator.

        When an operator connects FROM a palette/container, the source needs to be
        resolved to the internal output operator (e.g., out1).

        BUG-C FIX: Also handles regular containers, not just palettes.

        Args:
            source: Source operator name (e.g., 'audioAnalysis', 'show_controls')

        Returns:
            Resolved path (e.g., 'audioAnalysis/out1') or original source if not found
        """
        # Check palettes first
        if source in self.palette_io_map:
            io_info = self.palette_io_map[source]
            outputs = io_info.get('outputs', [])

            if outputs:
                out_op = outputs[0]['name']
                resolved = f"{source}/{out_op}"
                self.log(f"    Resolved palette source: {source} -> {resolved}")
                return resolved

        # BUG-C FIX: Check regular containers
        if source in self.container_io_map:
            io_info = self.container_io_map[source]
            outputs = io_info.get('outputs', [])

            if outputs:
                out_op = outputs[0]['name']
                resolved = f"{source}/{out_op}"
                self.log(f"    Resolved container source: {source} -> {resolved}")
                return resolved

        return source

    def _write_custom_parameters(self, container_path: str, custom_pars: list):
        """Write .cparm file for custom parameters on a container.

        BUG-K FIX: Implements custom parameter support for base COMPs.

        Format based on TD's .cparm file structure:
        ?
        pages N Page1 Page2 ...
        hash ParamName "DisplayName" type subtype min_norm max_norm ... default "" "" PageName order
        ?

        Supported parameter types in JSON input:
        - Float: {"name": "Speed", "type": "Float", "default": 1.0, "min": 0, "max": 10, "page": "Controls"}
        - Int: {"name": "Count", "type": "Int", "default": 5, "min": 1, "max": 100, "page": "Controls"}
        - Toggle: {"name": "Active", "type": "Toggle", "default": True, "page": "Controls"}
        - String: {"name": "Label", "type": "String", "default": "Hello", "page": "Controls"}
        - Menu: {"name": "Mode", "type": "Menu", "default": 0, "menuItems": ["Off", "On", "Auto"], "page": "Controls"}
        """
        if not custom_pars:
            return

        # Collect pages
        pages = {}
        for idx, par in enumerate(custom_pars):
            page = par.get("page", "Custom")
            if page not in pages:
                pages[page] = []
            pages[page].append((idx, par))

        # Build cparm content
        lines = ["?"]

        # Pages line
        page_names = list(pages.keys())
        page_str = " ".join(f'"{p}"' if " " in p else p for p in page_names)
        lines.append(f"pages {len(page_names)} {page_str}")

        # Type hashes (observed from TD files)
        TYPE_HASH = {
            "float": 772804865,
            "int": 772804865,
            "toggle": -1374678781,
            "string": 772804868,
            "menu": 772804865,
        }

        # Parameter lines
        for page_name, pars in pages.items():
            for order, (global_idx, par) in enumerate(pars):
                name = par.get("name", f"Par{global_idx}")
                display = par.get("label", par.get("display", name))
                par_type = par.get("type", "Float").lower()
                default = par.get("default", 0)
                min_val = par.get("min", 0)
                max_val = par.get("max", 1)
                enable_expr = par.get("enable", "")

                hash_val = TYPE_HASH.get(par_type, 772804865)

                if par_type == "float":
                    # Float: hash Name "Display" 1 3 min_norm max_norm 1 min max 2 default "" "" Page order
                    line = f'{hash_val} {name} "{display}" 1 3 {min_val} {min_val} 1 {max_val} {max_val} 2 {default} "" "" "{page_name}" {order}'
                elif par_type == "int":
                    # Int: similar to float but with integer values
                    line = f'{hash_val} {name} "{display}" 1 1 {int(min_val)} {int(min_val)} 1 {int(max_val)} {int(max_val)} 2 {int(default)} "" "" "{page_name}" {order}'
                elif par_type == "toggle":
                    # Toggle: hash Name "Display" 1 1 0 0 1 1 1 2 default "" "" Page order
                    def_val = 1 if default else 0
                    line = f'{hash_val} {name} "{display}" 1 1 0 0 1 1 1 2 {def_val} "" "" "{page_name}" {order}'
                elif par_type == "string":
                    # String: hash Name "Display" 1 1 0 0 1 1 1 2 0 "default" "" Page order
                    line = f'{hash_val} {name} "{display}" 1 1 0 0 1 1 1 2 0 "{default}" "" "{page_name}" {order}'
                elif par_type == "menu":
                    # Menu: More complex, need menu items
                    menu_items = par.get("menuItems", par.get("menu_items", ["Option1", "Option2"]))
                    # For now, use simplified format
                    line = f'{hash_val} {name} "{display}" 1 1 0 0 1 {len(menu_items)-1} {len(menu_items)-1} 2 {int(default)} "" "" "{page_name}" {order}'
                else:
                    # Default to float
                    line = f'{hash_val} {name} "{display}" 1 3 {min_val} {min_val} 1 {max_val} {max_val} 2 {default} "" "" "{page_name}" {order}'

                # Add enable expression if provided
                if enable_expr:
                    line += f" {enable_expr}"

                lines.append(line)

        lines.append("?")

        self._write_file(f"{container_path}.cparm", "\n".join(lines) + "\n")
        self.log(f"    Created custom parameters: {len(custom_pars)} params on {len(pages)} page(s)")

    def _write_operator_from_lossless(self, op_path: str, op_data: dict, position: list = None, is_root: bool = False):
        """Write operator files from lossless JSON data.

        Args:
            op_path: Full path for the operator (e.g., 'project1/audio')
            op_data: Operator data from lossless JSON
            position: Optional [x, y] position (for root component)
            is_root: Whether this is the root component
        """
        name = op_data.get("name", op_path.split("/")[-1])
        op_type = op_data.get("op_type", "COMP:base")

        # Track written paths for case collision detection (Windows is case-insensitive)
        if not hasattr(self, '_written_paths_lower'):
            self._written_paths_lower = {}
        if not hasattr(self, '_path_renames'):
            self._path_renames = {}  # Maps old_prefix -> new_prefix for children
        if not hasattr(self, '_written_types'):
            self._written_types = {}  # Maps path -> op_type for collision decision
        if not hasattr(self, '_name_renames'):
            self._name_renames = {}  # Maps old_name -> new_name for expression fixing

        # Apply any parent renames to this path
        for old_prefix, new_prefix in self._path_renames.items():
            if op_path.startswith(old_prefix + '/') or op_path == old_prefix:
                op_path = new_prefix + op_path[len(old_prefix):]
                name = op_path.split('/')[-1]
                break

        # Check for case collision
        op_path_lower = op_path.lower()
        if op_path_lower in self._written_paths_lower:
            existing = self._written_paths_lower[op_path_lower]
            if existing != op_path:
                # Case collision! Rename the simpler operator (non-COMP preferred to rename)
                existing_type = self._written_types.get(existing, '')
                current_is_comp = op_type.startswith('COMP:')
                existing_is_comp = existing_type.startswith('COMP:')

                if current_is_comp and not existing_is_comp:
                    # Current is COMP, existing is simpler - rename existing (already written)
                    # Can't rename already written, so rename current but note this is suboptimal
                    pass  # Fall through to rename current

                # Append type suffix to avoid overwrite
                type_suffix = op_type.split(':')[1].lower() if ':' in op_type else op_type.lower()
                new_name = f"{name}_{type_suffix}"
                old_path = op_path
                op_path = op_path.rsplit('/', 1)[0] + '/' + new_name if '/' in op_path else new_name
                # Track rename so children get updated too
                self._path_renames[old_path] = op_path
                # Track simple name rename for expression fixing
                self._name_renames[name] = new_name
                self.log(f"    [WARN] Case collision: '{name}' renamed to '{new_name}' (Windows case-insensitive)")

        self._written_paths_lower[op_path.lower()] = op_path
        self._written_types[op_path] = op_type

        # Ensure parent directory exists
        parent_dir = self.project_dir / Path(op_path).parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        # Get position from op_data or use provided
        # Lossless format uses tile_pos: [x, y, width, height]
        if position:
            x, y = position[0], position[1]
            tile_w, tile_h = (160, 130) if op_type.startswith("COMP:") else (130, 90)
        else:
            tile_pos = op_data.get("tile_pos", [0, 0, 130, 90])
            if tile_pos and len(tile_pos) >= 4:
                x, y, tile_w, tile_h = tile_pos[0], tile_pos[1], tile_pos[2], tile_pos[3]
            else:
                x, y = 0, 0
                tile_w, tile_h = (160, 130) if op_type.startswith("COMP:") else (130, 90)

        # Write .n file with actual operator type
        flags_data = op_data.get("flags", {})
        if isinstance(flags_data, dict):
            # Convert {"viewer": "1", "parlanguage": "0"} to "viewer 1 parlanguage 0"
            flags_str = " ".join(f"{k} {v}" for k, v in flags_data.items())
        else:
            flags_str = str(flags_data) if flags_data else "viewer 1 parlanguage 0"

        n_lines = [
            op_type,
            f"tile {x} {y} {tile_w} {tile_h}",
            f"flags = {flags_str}",
        ]

        # Add inputs if present (lossless format: {"0": "opname", "1": "opname2"} or empty {})
        inputs_data = op_data.get("inputs", {})
        if inputs_data and isinstance(inputs_data, dict) and len(inputs_data) > 0:
            n_lines.append("inputs")
            n_lines.append("{")
            for idx, inp_name in sorted(inputs_data.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
                n_lines.append(f"{idx}\t{inp_name}")
            n_lines.append("}")

        # Add exports if present (format: exports\n{\nexport_name\n})
        exports = op_data.get("exports", [])
        if exports:
            n_lines.append("exports")
            n_lines.append("{")
            for exp in exports:
                n_lines.append(exp)
            n_lines.append("}")
            n_lines.append("")  # Empty line after exports block

        # Add color if present (lossless format: [0.55, 0.55, 0.55])
        color = op_data.get("color")
        if color and isinstance(color, list):
            color_str = " ".join(str(c) for c in color)
            n_lines.append(f"color {color_str}")

        # Add dict if present (instance data - hex encoded pickle)
        dict_data = op_data.get("dict_data")
        if dict_data:
            n_lines.append(f"dict {dict_data}")

        n_lines.append("end")
        self._write_file(f"{op_path}.n", "\n".join(n_lines) + "\n")

        # Write .parm file from parameters
        parameters = op_data.get("parameters", {})
        if parameters:
            self._write_parm_from_lossless(op_path, parameters)

        # Write extra files (text content, etc.)
        extra_files = op_data.get("extra_files", {})
        for ext, file_data in extra_files.items():
            self._write_extra_file_from_lossless(op_path, ext, file_data)

    def _fix_expression_renames(self, value: str) -> str:
        """Fix operator references in expressions after case collision renames.

        Replaces op('oldname') and op("oldname") with renamed operator names.
        """
        if not hasattr(self, '_name_renames') or not self._name_renames:
            return value

        import re
        result = value
        for old_name, new_name in self._name_renames.items():
            # Match op('name') or op("name") patterns
            # Also handle op('./name') and op("./name") for relative refs
            patterns = [
                (rf"op\('{re.escape(old_name)}'\)", f"op('{new_name}')"),
                (rf'op\("{re.escape(old_name)}"\)', f'op("{new_name}")'),
                (rf"op\('\./'{re.escape(old_name)}'\)", f"op('./{new_name}')"),
                (rf'op\("\./"{re.escape(old_name)}"\)', f'op("./{new_name}")'),
            ]
            for pattern, replacement in patterns:
                result = re.sub(pattern, replacement, result)

        return result

    def _write_parm_from_lossless(self, op_path: str, parameters: dict):
        """Write .parm file from lossless parameter data.

        Lossless format uses: {"parm_name": {"mode": value}} or {"parm_name": {"mode": "value expr"}}
        Where mode is the TD parameter mode as a string key (e.g., "67108864" for constant, "0" for default).
        """
        lines = ["?"]  # Start with ?

        for parm_name, parm_data in parameters.items():
            if isinstance(parm_data, dict):
                # Lossless format: {"67108864": value} or {"0": value} or {"49": "value expr"}
                for mode_str, value in parm_data.items():
                    try:
                        mode = int(mode_str)
                        # Mode 67108864 is constant mode in TD internal format, treat as 0
                        if mode == 67108864:
                            mode = 0

                        # Fix any renamed operator references in expressions
                        if isinstance(value, str):
                            value = self._fix_expression_renames(value)

                        if isinstance(value, str) and ' ' in value and mode in [17, 49]:
                            # Expression mode with space - value includes expression
                            lines.append(f"{parm_name} {mode} {value}")
                        else:
                            lines.append(f"{parm_name} {mode} {value}")
                    except ValueError:
                        # Non-numeric key, treat as simple value
                        if isinstance(value, str):
                            value = self._fix_expression_renames(value)
                        lines.append(f"{parm_name} 0 {value}")
            else:
                # Simple value
                if isinstance(parm_data, str):
                    parm_data = self._fix_expression_renames(parm_data)
                lines.append(f"{parm_name} 0 {parm_data}")

        lines.append("?")
        self._write_file(f"{op_path}.parm", "\n".join(lines) + "\n")

    def _write_extra_file_from_lossless(self, op_path: str, ext: str, file_data: dict):
        """Write extra file (text, network, etc.) from lossless data."""
        if isinstance(file_data, dict):
            content = file_data.get("content", "")
            is_binary = file_data.get("is_binary", False)

            if is_binary and content:
                # Decode base64 binary content
                import base64
                try:
                    binary_data = base64.b64decode(content)
                    file_path = self.project_dir / f"{op_path}.{ext}"
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_path, 'wb') as f:
                        f.write(binary_data)
                    self.toc_entries.append(f"{op_path}.{ext}")
                except Exception as e:
                    self.log(f"    [WARN] Failed to write binary file {ext}: {e}")
            elif content:
                self._write_file(f"{op_path}.{ext}", content)
        elif isinstance(file_data, str):
            self._write_file(f"{op_path}.{ext}", file_data)

    # =========================================================================
    # LEGACY TOX EMBEDDING (Fallback when KB not available)
    # =========================================================================

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
            toeexpand = resolve_td_tool("toeexpand")
            if toeexpand is None:
                self.log(f"    [ERROR] {td_tool_missing_error('toeexpand')}")
                return
            result = subprocess.run(
                [str(toeexpand), str(temp_tox)],
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
            for ext in [".cparm", ".parm", ".panel", ".network"]:
                src_file = root_comp / f"{root_comp_name}{ext}"
                if src_file.exists():
                    dest_file = self.project_dir / f"{full_path}{ext}"
                    shutil.copy(src_file, dest_file)
                    self.toc_entries.append(f"{full_path}{ext}")

    # =========================================================================
    # PYTHON RUNTIME LOADING (Alternative fallback for interactive use)
    # =========================================================================

    def _generate_palette_init_script(self, components: list) -> str:
        """Generate Text DAT init script that loads palettes at runtime.

        This is a FALLBACK method for when:
        1. KB lossless JSON is not available for the component
        2. Dynamic loading is preferred over static embedding

        Args:
            components: List of dicts with keys:
                - name: Palette component name (e.g., 'audioAnalysis')
                - path: Relative path in TD palette (e.g., 'Tools/audioAnalysis.tox')
                - target_name: Name to give the component
                - x, y: Optional position coordinates

        Returns:
            str: Python script content for Text DAT
        """
        script_lines = [
            "# Auto-generated palette loader - runs at project start",
            "# Generated by TD Builder",
            "",
            "def onStart():",
            "    root = parent()",
            "    palette_base = 'C:/Program Files/Derivative/TouchDesigner/Palette'",
            "",
        ]

        for comp in components:
            name = comp.get('name', '')
            path = comp.get('path', f"Tools/{name}.tox")
            target = comp.get('target_name', name)
            x = comp.get('x', 0)
            y = comp.get('y', 0)

            script_lines.extend([
                f"    # Load {name}",
                f"    try:",
                f"        tox_path = f'{{palette_base}}/{path}'",
                f"        loaded = root.loadTox(tox_path)",
                f"        if loaded:",
                f"            # Navigate to inner component if nested",
                f"            inner = loaded.op('{name}') if loaded.op('{name}') else loaded",
                f"            inner.name = '{target}'",
                f"            inner.nodeX = {x}",
                f"            inner.nodeY = {y}",
                f"            debug(f'Loaded palette: {name} -> {target}')",
                f"    except Exception as e:",
                f"        debug(f'Failed to load {name}: {{e}}')",
                "",
            ])

        script_lines.append("    debug('Palette components loaded')")
        return "\n".join(script_lines)

    def _create_palette_loader_dat(self, container_path: str, components: list):
        """Create a Text DAT with palette loading script.

        Args:
            container_path: Container to add the Text DAT
            components: List of palette components to load
        """
        script_content = self._generate_palette_init_script(components)

        # Write the script content as a text file
        dat_name = "palette_loader"
        full_path = f"{container_path}/{dat_name}"

        # Write .n file for Text DAT
        n_content = """DAT:text
tile -200 -200 130 90
flags =  viewer 1 parlanguage 0
end
"""
        self._write_file(f"{full_path}.n", n_content)

        # Write .text file with the script
        self._write_file(f"{full_path}.text", script_content)

        # Write .parm to enable execOnStart (this makes it run on project load)
        parm_content = """syncfile 0
loadonstartpulse 0
execonstart 0 1
?
"""
        self._write_file(f"{full_path}.parm", parm_content)

        self.log(f"    Created palette loader DAT: {dat_name}")

    # Internal name overrides - user name -> TD internal name (BUG-011 fix)
    # These are operators where the user-friendly name differs from TD's internal name
    INTERNAL_NAME_MAP = {
        "composite": "comp",  # Composite TOP internal name is "comp"
        "hsvadjust": "hsvadj",  # HSV Adjust TOP
        "audiospectrum": "audiospect",  # Audio Spectrum CHOP
        "audiodevicein": "audiodevin",  # Audio Device In CHOP
        "audiodeviceout": "audiodevout",  # Audio Device Out CHOP
        "audiooscillator": "audioosc",  # Audio Oscillator CHOP
    }

    # Operators that exist in multiple families - require explicit family or alias
    # CRITICAL (7 families): null, select
    # HIGH (6 families): in, out, switch
    # MODERATE (4+ families): blend, merge, noise, transform, script, limit, text, sort, glsl
    # LOW (3 families): analyze, constant, level, math, lookup, cache, feedback, copy, delete, trail, etc.
    AMBIGUOUS_OPERATORS = {
        # Critical - exist in almost all families
        "null", "select",
        # High - 6 families
        "in", "out", "switch",
        # Moderate - 4-5 families
        "blend", "merge", "noise", "transform", "script", "limit", "text", "sort", "glsl", "cplusplus",
        # Common - 3 families
        "analyze", "constant", "level", "math", "lookup", "cache", "feedback", "copy", "delete",
        "trail", "convert", "circle", "line", "clip", "attribute", "reorder", "force",
        # 2 families but commonly confused
        "composite", "cross", "function", "grid", "pattern", "render", "slope", "sphere",
    }

    def _map_op_type(self, op_type: str, container_path: str, explicit_family: str = None) -> str:
        """Map TD Designer type to TouchDesigner family:type.

        Args:
            op_type: The operator type (e.g., "noise", "noiseCHOP", "CHOP:noise")
            container_path: Container path for context-based inference
            explicit_family: Explicit family field from design JSON (e.g., "CHOP")
        """
        families = ["CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP"]

        self.log(f"  _map_op_type: input='{op_type}' family='{explicit_family}'")

        # Normalize input: strip whitespace and convert "Audio Device In" to "audiodevicein"
        op_type_normalized = op_type.replace(" ", "").replace("_", "").strip()

        # Already in FAMILY:type format - return as-is
        for family in families:
            if op_type.upper().startswith(f"{family}:"):
                # Already formatted, just normalize case: "chop:noise" -> "CHOP:noise"
                result = f"{family}:{op_type[len(family)+1:]}"
                self.log(f"  _map_op_type: already formatted -> {result}")
                return result

        op_lower = op_type.lower()
        op_normalized_lower = op_type_normalized.lower()

        # PRIORITY 1: Explicit family OVERRIDES OP_TYPE_MAP for ambiguous operators
        # This fixes: {"type": "noise", "family": "CHOP"} -> CHOP:noise (not TOP:noise)
        if explicit_family and (op_lower in self.AMBIGUOUS_OPERATORS or op_normalized_lower in self.AMBIGUOUS_OPERATORS):
            family_upper = explicit_family.upper()
            # BUG-011 FIX: Use internal name if different from user name
            internal_name = self.INTERNAL_NAME_MAP.get(op_lower, op_type)
            self.log(f"  Using explicit family {family_upper} for ambiguous operator '{op_type}' -> {internal_name}")
            return f"{family_upper}:{internal_name}"

        # PRIORITY 2: Direct lookup in OP_TYPE_MAP
        if op_type in OP_TYPE_MAP:
            mapped = OP_TYPE_MAP[op_type]
            mapped_family = mapped.split(":")[0]
            self.log(f"  _map_op_type: found in OP_TYPE_MAP -> {mapped}")
            # Warn if ambiguous operator used without explicit family
            if op_lower in self.AMBIGUOUS_OPERATORS and not explicit_family:
                self.log(f"  [WARN] '{op_type}' exists in multiple families - defaulting to {mapped_family}")
                self.log(f"         Add 'family' field to specify: CHOP, TOP, SOP, or DAT")
            # Warn if user provided conflicting family for non-ambiguous operator
            elif explicit_family and explicit_family.upper() != mapped_family:
                self.log(f"  [WARN] '{op_type}' only exists as {mapped_family}, ignoring family='{explicit_family}'")
            return mapped

        # Try lowercase
        if op_lower in OP_TYPE_MAP:
            mapped = OP_TYPE_MAP[op_lower]
            mapped_family = mapped.split(":")[0]
            self.log(f"  _map_op_type: found lowercase in OP_TYPE_MAP -> {mapped}")
            # Warn if ambiguous operator used without explicit family
            if op_lower in self.AMBIGUOUS_OPERATORS and not explicit_family:
                self.log(f"  [WARN] '{op_type}' exists in multiple families - defaulting to {mapped_family}")
                self.log(f"         Add 'family' field to specify: CHOP, TOP, SOP, or DAT")
            # Warn if user provided conflicting family for non-ambiguous operator
            elif explicit_family and explicit_family.upper() != mapped_family:
                self.log(f"  [WARN] '{op_type}' only exists as {mapped_family}, ignoring family='{explicit_family}'")
            return mapped

        # Try normalized (spaces/underscores removed): "Audio Device In" -> "audiodevicein"
        if op_normalized_lower in OP_TYPE_MAP:
            mapped = OP_TYPE_MAP[op_normalized_lower]
            mapped_family = mapped.split(":")[0]
            self.log(f"  _map_op_type: found normalized in OP_TYPE_MAP -> {mapped}")
            return mapped

        # PRIORITY 3: Explicit family for unknown operators (not in map)
        if explicit_family:
            family_upper = explicit_family.upper()
            # BUG-011 FIX: Use internal name if different from user name
            internal_name = self.INTERNAL_NAME_MAP.get(op_lower, op_type)
            self.log(f"  Using explicit family {family_upper} for unknown operator '{op_type}' -> {internal_name}")
            return f"{family_upper}:{internal_name}"

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
        # BUG-011 FIX: Always use internal name for inferred/default cases
        internal_name = self.INTERNAL_NAME_MAP.get(op_lower, op_type)

        if "audio" in container_name:
            result = f"CHOP:{internal_name}"
            self.log(f"  _map_op_type: inferred from container 'audio' -> {result}")
            return result
        elif "particle" in container_name:
            result = f"TOP:{internal_name}"
            self.log(f"  _map_op_type: inferred from container 'particle' -> {result}")
            return result
        elif any(x in container_name for x in ["visual", "core", "ray", "glitch", "composite"]):
            result = f"TOP:{internal_name}"
            self.log(f"  _map_op_type: inferred from container name -> {result}")
            return result

        # Default to TOP
        self.log(f"  [WARN] _map_op_type: '{op_type}' NOT FOUND in OP_TYPE_MAP - defaulting to TOP:{internal_name}")
        return f"TOP:{internal_name}"

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

    def _write_binary_text(self, rel_path: str, content: str):
        """Write a binary .text file for Text DAT in TD's native format.

        Format discovered from working TD files:
        - Header: "2\\n*" (bytes: 0x32 0x0A 0x2A)
        - Metadata: 5 x 4-byte big-endian integers [1, 1, 1, 1, 2]
        - Content length: 4-byte big-endian integer
        - Content: UTF-8 encoded text

        This is essential for GLSL shaders to load correctly in glslTOP.
        """
        import struct

        file_path = self.project_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content_bytes = content.encode('utf-8')

        # Build binary data
        header = b"2\n*"
        metadata = struct.pack('>5I', 1, 1, 1, 1, 2)
        length_bytes = struct.pack('>I', len(content_bytes))

        with open(file_path, 'wb') as f:
            f.write(header)
            f.write(metadata)
            f.write(length_bytes)
            f.write(content_bytes)

        self.toc_entries.append(rel_path)
        self.log(f"    Wrote binary .text file: {rel_path} ({len(content_bytes)} bytes)")

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

        toecollapse = resolve_td_tool("toecollapse")
        if toecollapse is None:
            self.log(f"[ERROR] {td_tool_missing_error('toecollapse')}")
            return None

        # Pass the .toc file path, not the .dir directory
        toc_path = self.output_dir / f"{project_name}.toe.toc"
        result = subprocess.run(
            [str(toecollapse), str(toc_path)],
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

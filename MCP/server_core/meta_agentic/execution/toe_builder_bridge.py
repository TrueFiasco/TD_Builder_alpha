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

from .param_name_resolver import resolve_param_name, resolve_menu_value

logger = logging.getLogger(__name__)

# Paths -- resolved via the canonical repo-root paths module (honors the
# TD_BUILDER_ROOT relocation knob). paths is importable here because
# param_name_resolver (imported above) self-bootstraps it onto sys.path.
from paths import (resolve_td_tool, td_tool_missing_error, KB_OPERATORS,
                   KB_PALETTE_COMPONENTS, KB_DOCKED_DATS, REPO_ROOT)
EXPERTISE_DIR = REPO_ROOT / "Agents" / "expertise"

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
DOCKED_DATS_PATH = KB_DOCKED_DATS
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


# Pre-built component registry (KB/palette_components.json): per-item reference +
# interface metadata for the `palette` field. The builder writes a PLACEHOLDER COMP
# (enableexternaltox/externaltox/subcompname) that loads the component from the user's
# own TD install / palette / project when the file opens -- no Derivative content is
# embedded or redistributed. The interface metadata (inner in/out op names + families)
# is what lets wires to/from the placeholder survive external loading: TD re-binds
# compinputs .network entries and 'name/out1' path-form input refs by INNER op name
# (verified live 2025.32820; sibling-name refs to a not-yet-loaded COMP are dropped).
_PALETTE_COMPONENTS_CACHE = None
_PALETTE_COMPONENTS_CACHE_KEY = None


def _registry_file_sig(path) -> tuple:
    """(path, mtime_ns, size) — or (path, None, None) when absent/unreadable."""
    try:
        st = Path(path).stat()
        return (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(path), None, None)


def _valid_user_component(spec) -> bool:
    """Shape-check ONE user-registry component so a malformed hand-edit is skipped at
    MERGE time instead of crashing resolution (loader contract: a user registry must
    never fail a build). Guards the crash vectors _palette_io_entry relies on: inputs/
    outputs must be lists of dicts (its index-sort calls item.get(...)), and harvest,
    if present, must be a dict (index_authority reads harvest.method). A natural bad
    edit — inputs as a list of bare strings ["in1"] — is exactly what this rejects."""
    if not isinstance(spec, dict):
        return False
    for key in ("inputs", "outputs"):
        v = spec.get(key)
        if v is None:
            continue
        if not isinstance(v, list) or not all(isinstance(it, dict) for it in v):
            return False
    h = spec.get("harvest")
    if h is not None and not isinstance(h, dict):
        return False
    return True


def _load_palette_components() -> dict:
    """Load the component registry: shipped KB/palette_components.json merged with the
    USER registry (paths.user_components_path(), default ~/.td_builder/, override via
    TD_BUILDER_USER_DIR) — the ONE loader seam. User entries win per component name.

    The cache is keyed on (path, mtime_ns, size) of BOTH files, so a registration made
    while the MCP server is running (register_user_component.py, an external process)
    is visible on the very next build — no restart. The merge builds a FRESH dict per
    (re)load; the shipped spec is never mutated in place. A malformed user file warns
    and falls back to shipped-only (a user registry must never fail a build).

    Tests may still inject a registry by assigning _PALETTE_COMPONENTS_CACHE directly:
    an injected cache is returned as long as the underlying files haven't changed
    since the key was computed (or no key exists yet)."""
    global _PALETTE_COMPONENTS_CACHE, _PALETTE_COMPONENTS_CACHE_KEY
    from paths import user_components_path
    user_path = user_components_path()
    key = (_registry_file_sig(KB_PALETTE_COMPONENTS), _registry_file_sig(user_path))
    if _PALETTE_COMPONENTS_CACHE is not None and (
            _PALETTE_COMPONENTS_CACHE_KEY is None or _PALETTE_COMPONENTS_CACHE_KEY == key):
        return _PALETTE_COMPONENTS_CACHE

    try:
        with open(KB_PALETTE_COMPONENTS, "r", encoding="utf-8") as f:
            shipped = json.load(f)
    except Exception as e:
        logger.warning("palette_components.json not loaded (%s); palette field disabled", e)
        shipped = {"components": {}}

    merged = dict(shipped)
    merged["components"] = dict(shipped.get("components") or {})
    if key[1][1] is not None:  # user file exists
        try:
            with open(user_path, "r", encoding="utf-8") as f:
                user_spec = json.load(f)
            user_components = user_spec.get("components")
            if not isinstance(user_components, dict):
                raise ValueError('missing/invalid top-level "components" object')
            # Per-entry shape validation (G5): a malformed hand-edit must NOT crash a
            # build (the loader contract). Skip bad entries with a warning so an
            # unreferenced one is inert and a referenced one degrades to the clean
            # unknown-component error instead of an AttributeError at resolution.
            clean = {}
            for cname, cspec in user_components.items():
                if _valid_user_component(cspec):
                    clean[cname] = cspec
                else:
                    logger.warning(
                        "user registry entry %r is malformed (inputs/outputs must be "
                        "lists of {index, in_op/out_op, family} objects, harvest must be "
                        "an object); skipping it", cname)
            collisions = set(clean) & set(merged["components"])
            if collisions:
                logger.info("user registry overrides %d shipped component(s): %s",
                            len(collisions), sorted(collisions))
            merged["components"].update(clean)
        except Exception as e:
            logger.warning("user component registry %s not loaded (%s); using shipped "
                           "registry only", user_path, e)

    _PALETTE_COMPONENTS_CACHE = merged
    _PALETTE_COMPONENTS_CACHE_KEY = key
    return merged


# BUG-3: build-time interface manifests for external_tox components. The manifest logic
# lives in MCP/engine/core/component_manifest.py (shared with the server's expand tool);
# it is imported lazily because this module must keep importing in sys.path-minimal
# contexts (tests/unit adds only repo root + server_core) and the manifest is only needed
# when a design actually wires an external .tox.
_EXTERNAL_MANIFEST_CACHE = {}


def _import_manifest_module():
    """Import engine core.component_manifest; fall back to loading it by absolute file
    path — a foreign 'core' package already on sys.path would shadow a path insert."""
    try:
        from core import component_manifest as cm
        if hasattr(cm, "manifest_from_tox"):
            return cm
    except Exception:
        pass
    import importlib.util
    p = Path(__file__).resolve().parents[3] / "engine" / "core" / "component_manifest.py"
    spec = importlib.util.spec_from_file_location("td_builder_component_manifest", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_external_manifest(resolved_path: Path) -> dict:
    """manifest_from_tox with a (path, mtime_ns, size)-keyed cache — the MCP server
    process is long-lived and a rebuilt .tox at the same path must not serve a stale
    manifest. Raises ComponentManifestError (kind in {tool_missing, timeout,
    expand_failed, parse_failed}). Unit tests monkeypatch THIS function (the seam)."""
    st = resolved_path.stat()
    key = (str(resolved_path), st.st_mtime_ns, st.st_size)
    hit = _EXTERNAL_MANIFEST_CACHE.get(key)
    if hit is None:
        hit = _import_manifest_module().manifest_from_tox(resolved_path)
        _EXTERNAL_MANIFEST_CACHE[key] = hit
    return hit


# Build-token grounding index (the SOURCE fix): KB/operators.json carries the live-real
# `.n` token per op as `build_token` (added by the re-grounding step from operator_ground_truth).
# We index (FAMILY, alnum-alias) -> build_token so _map_op_type can return the live-faithful
# token instead of the wiki-display-derived one. Empty when operators.json predates re-grounding
# (no build_token field) -> grounding is a no-op and the builder falls back to its old logic
# (fully backward-compatible).
_BUILD_TOKEN_INDEX = None


def _alnum(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _load_build_token_index() -> dict:
    global _BUILD_TOKEN_INDEX
    if _BUILD_TOKEN_INDEX is None:
        _BUILD_TOKEN_INDEX = {}
        try:
            with open(KB_OPERATORS, "r", encoding="utf-8") as f:
                data = json.load(f)
            for o in data.get("operators", []):
                bt = o.get("build_token")
                fam = o.get("family")
                name = o.get("name")
                if not bt or not fam or not name or ":" not in bt:
                    continue
                aliases = set()
                base = name[: -len(fam)].strip() if name.endswith(fam) else name
                aliases.add(_alnum(base))                       # display-derived token
                aliases.add(_alnum(bt.split(":", 1)[1]))        # the build token's own type
                tdc = o.get("python_class") or ""
                if tdc.endswith("_Class"):
                    cls_base = tdc[: -len("_Class")]
                    # strip the family only as a trailing suffix; a global replace would
                    # mangle any class name containing the family string mid-word
                    if cls_base.endswith(fam):
                        cls_base = cls_base[: -len(fam)]
                    aliases.add(_alnum(cls_base))               # td_create base
                for a in aliases:
                    if not a:
                        continue
                    key = (fam.upper(), a)
                    prev = _BUILD_TOKEN_INDEX.setdefault(key, bt)   # first-wins
                    if prev != bt:
                        logger.warning(
                            "build_token alias collision: %s -> %s kept, %s (from %r) ignored"
                            " — check python_class grounding in operators.json",
                            key, prev, bt, name)
        except Exception as e:
            logger.error("build_token index not loaded (%s); grounded build tokens DISABLED"
                         " — builder falls back to legacy OP_TYPE_MAP tokens", e)
            _BUILD_TOKEN_INDEX = {}
        if not _BUILD_TOKEN_INDEX:
            logger.error("build_token index is EMPTY (operators.json missing build_token"
                         " fields?); grounded build tokens DISABLED — builder falls back"
                         " to legacy OP_TYPE_MAP tokens")
    return _BUILD_TOKEN_INDEX


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
    # TD's Geometry COMP OPType is "geo" (NOT "geometry"); writing COMP:geometry makes TD
    # fall back to a base COMP on import (BUG 2). Both aliases resolve to the real token.
    "geo": "COMP:geo",
    "geometry": "COMP:geo",
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


def _td_quote_token(token: str) -> str:
    """Quote a .parm value/expression token the way TouchDesigner does.

    TD's .parm parser is whitespace-delimited, so any value or expression that
    contains a space must be wrapped in double quotes. Two failures result from an
    unquoted space, verified live against TD 2025.32820:
      1. self-truncation -- ``[3, 2, 7][me.chanIndex]`` becomes ``[3,`` ("'[' was
         never closed"); ``tx ty tz`` becomes ``tx``;
      2. parser DESYNC -- the leftover tokens (``2, 7]...`` / ``ty tz``) knock the
         line parser out of sync, so the *following* params in the same .parm are
         dropped and silently revert to their defaults. This is what actually
         inverted ``specifypos``/``closed`` in the knot session -- they sit right
         after an unquoted ``chanscope 0 tx ty tz`` line.
    Tokens that are already quoted are returned untouched so we never double-quote
    a pre-quoted value. Verified against TD's own output:
    ``numcycles 49 3 "[3, 2, 7][me.chanIndex]"`` and ``chanscope 0 "tx ty tz"``.
    """
    s = str(token)
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s  # already quoted
    if s == '' or any(ch.isspace() for ch in s):
        return '"' + s.replace('"', '\\"') + '"'
    return s


def _td_emit_token(value: Any) -> str:
    """Normalize a constant .parm value token to TouchDesigner's on-disk form.

    Python booleans become TD's canonical toggle literals (``True`` -> ``on``,
    ``False`` -> ``off``) to match what TD itself writes. (TD's loader also
    accepts ``True``/``False``/``1``/``0`` for toggles, so this is output hygiene,
    not a correctness fix -- the real corruption is unquoted whitespace, see
    :func:`_td_quote_token`.) All other values are whitespace-quoted.
    """
    if isinstance(value, bool):
        return 'on' if value else 'off'
    return _td_quote_token(str(value))


def _parm_line(code: str, mode, value, expr=None) -> str:
    """Serialize ONE .parm body line -- the only way the bridge emits one (W2b).

    ``'{code} {mode} {token}'`` for constants, ``'{code} {mode} {token} {expr}'``
    for expression modes (the caller supplies the mode; this function never picks
    one). The constant token goes through :func:`_td_emit_token` (bool -> on/off,
    whitespace/empty -> double-quoted, pre-quoted untouched) and the expression
    through :func:`_td_quote_token`, so no value can truncate itself or desync the
    whitespace-delimited .parm parser (see _td_quote_token for the failure mode).
    Every .parm emission site must route through here -- including the paths that
    deliberately bypass _param_lines' validation/auto-promotion (GLSL uniforms,
    externaltox, docked-DAT links): "raw" means no KB name resolution and no
    expression auto-detection, never unquoted serialization.
    """
    token = _td_emit_token(value)
    if expr is not None:
        return f"{code} {mode} {token} {_td_quote_token(str(expr))}"
    return f"{code} {mode} {token}"


def _py_str_literal(s: str) -> str:
    """A single-quoted Python string literal for `s`, safe to embed in a TD parameter
    EXPRESSION that _parm_line then double-quotes for the .parm line (G6).

    The externaltox expression for user/derivative sources is
    `app.userPaletteFolder + '<seg>'`; a raw f-string breaks on an apostrophe in the
    path ("/my's/comp.tox" -> unbalanced quotes -> TD load error). _td_quote_token
    wraps the whole expression in double quotes and escapes only `"`, so the inner
    literal must stay single-quoted and escape backslash + single quote for the Python
    layer. For an apostrophe-free path this is byte-identical to the old `'/{seg}'`
    form, so pinned tests are unaffected."""
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


# Auto-promotion of plain-string params to mode-49 expressions. The old check was a
# loose substring list ('ext.', 'me.', 'op(', ...) that corrupted constant file paths:
# 'C:/components/text.tox' contains 'ext.', 'Tools/theme.tox' contains 'me.' -- both
# were silently emitted as Python expressions and the external tox never loaded. The
# lookbehind excludes identifier, filename and path characters (the ``\\`` covers
# ``C:\`` paths -- load-bearing, do not simplify away), so a TD global only counts
# when it starts a token: 'me.time.frame' promotes, 'theme.tox' does not.
_EXPR_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_./\\:])"
    r"(?:(?:op|parent|chop)\s*\(|(?:me|parent|mod|ext|iop|ipar|tdu|absTime)\.)"
)

# File-path params are never auto-promoted, even for values that START with a TD
# global token ('ext.assets/x.tox', 'me.tox'). Explicit {"expr": ...} remains the
# escape hatch for expression-driven paths (e.g. app.samplesFolder-relative loads).
_NEVER_EXPR_PARAMS = {"externaltox"}


def _is_expression(value: str, *param_names: str) -> bool:
    """True when a plain string param value should auto-promote to a mode-49 expression."""
    if any(n.lower() in _NEVER_EXPR_PARAMS for n in param_names):
        return False
    return bool(_EXPR_TOKEN_RE.search(value))


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
        self.external_components = []  # Round-4 #1: external-tox refs, for the build-log summary

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

        # BUG-3: prime component interfaces before ANY op writes (design order is
        # arbitrary; a consumer may be written before its palette/external_tox comp).
        self._prepass_component_io(network)

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

        # 2b. Write the /perform Window COMP every TD project ships
        self._write_perform_window()

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

        # 4b. External-tox component summary (build log)
        self._write_component_summary(project_name)

        # 5. Collapse to TOE
        toe_path = self._collapse(project_name)

        if toe_path:
            self.log("\n" + "=" * 60)
            self.log(f"[SUCCESS] Created: {toe_path}")
            self.log(f"         Size: {toe_path.stat().st_size} bytes")
            self.log("=" * 60)

        return toe_path

    def _write_component_summary(self, project_name: str):
        """Write a per-project build-log summary of the external-tox components a build
        references (Round-4 #1) — `<project>.components.md` in the output dir. Each entry is
        a reusable, file-backed component; this makes the project self-documenting and is the
        place a component manifest (inputs/outputs/params) is surfaced (extended in #1b)."""
        comps = getattr(self, "external_components", None)
        if not comps:
            return
        lines = [f"# {project_name} — external components ({len(comps)})", ""]
        for c in comps:
            lines.append(f"- **{c['name']}** (`{c['td_type']}`) -> `{c['tox']}`  _(at `{c['path']}`)_")
        summary_path = self.output_dir / f"{project_name}.components.md"
        summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.log(f"  Wrote component summary: {summary_path.name} ({len(comps)} components)")

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
        """Write root-level system files for a `.toe` project (Round-4 #8 — make `.toe`
        first-class).

        Ground-truthed against a real TD-saved `.toe`: `.start` is plain `cookrate`/`realtime`
        lines (NOT a `?`-delimited .parm block, which the bridge used to write), and a
        `.application` (desk/pane/winplacement) layout is REQUIRED — without it the project
        opens with no network editor. The displayed pane targets `/project1` (the bridge nests
        the build under a `project1` container)."""
        self.log("\n[1/5] Writing system files...")

        self._write_file(".build", "version 099\nbuild 2025.31760\ntime Fri Dec 20 10:00:00 2025\nosname Windows\nosversion 10\n")
        self._write_file(".start", "cookrate 60\nrealtime on\n")
        self._write_file(".grps", "-2\n0\n")
        self._write_file(".root", "end\n")
        self._write_file(".parm", "?\n?\n")
        self._write_file(".application",
                         "\n#Desk..\n# layout \ndesk -c * \ndesk -n pane1 *\n\n"
                         "#pane1\ndesk -p /project1 pane1\ndesk -t neteditor pane1\ndesk -k 0 pane1\n"
                         "neteditor -c 0 -e 1 -G 0.75 -o 0 -r 1 -P 0.8 -s 0 -w 0 -x 0 -t 1 -d 1 -g 0 -p pane1\n\n"
                         "winplacement ontop=0 mode=auto posx=0 posy=0 sizex=1280 sizey=720 "
                         "enable=1 perform.path=/perform perform.start=0\n")

        self.log("  Created 6 system files")

    def _write_project_container(self, network: dict):
        """Create main project container."""
        self.log("\n[2/5] Creating project container...")

        resolution = network.get("resolution", [1920, 1080])

        self._write_file("project1.n", """COMP:container
tile 0 0 500 400
flags =  parlanguage 0
end
""")
        self._write_file("project1.parm",
                         "?\n" + _parm_line("w", 0, resolution[0]) + "\n"
                         + _parm_line("h", 0, resolution[1]) + "\n?\n")
        # .panel shares the .parm line grammar; same emitter.
        self._write_file("project1.panel",
                         "?\n" + _parm_line("screenw", 0, resolution[0]) + "\n"
                         + _parm_line("screenh", 0, resolution[1]) + "\n?\n")

        (self.project_dir / "project1").mkdir(exist_ok=True)
        self.log("  Created project container")

    def _write_perform_window(self):
        """Write the /perform Window COMP at the project root (ground-truthed from a TD
        save+expand). Every TD project ships one; its `winop` points at the project root
        (project1) so the Performance window displays the build. Without it a built .toe
        opens with no perform window."""
        self._write_file("perform.n",
                         "COMP:window\ntile -200 40 160 130\n"
                         "flags =  viewer 1 parlanguage 0\ncolor 0.67 0.67 0.67 \nend\n")
        self._write_file("perform.parm",
                         "?\n" + _parm_line("winop", 0, "project1") + "\n"
                         + _parm_line("justifyh", 0, "center") + "\n"
                         + _parm_line("justifyv", 0, "center") + "\n?\n")
        (self.project_dir / "perform").mkdir(exist_ok=True)
        self.log("  Created /perform window COMP")

    def _flags_tokens(self, flags: dict) -> str:
        """A design operator/container `flags` dict -> the TD `.n` `flags` tokens, returned
        trailing-space-terminated so a call site writes `flags =  {tokens}parlanguage 0` and
        collapses to the historical `flags =  parlanguage 0` byte-for-byte when no flags are set.

        Ground-truthed from a real TD 2025.32820 save (NewProject.toe expanded via toeexpand):
        node flags serialize as `<name> on` EXCEPT `viewer`, which is numeric `viewer 1`
        (e.g. real geo1.n: `flags =  picked on current on render on display on parlanguage 0`;
        a default viewer op: `flags =  viewer 1 parlanguage 0`). Emit order follows TD's observed
        order (current, viewer, render, display, ...); `parlanguage 0` stays the trailing token at
        the call site. `bypass`/`lock` were not present in that sample and use the boolean `on`
        convention shared by every other boolean flag (they are not exercised by the release path).
        """
        if not flags:
            return ""
        parts = []
        for key in ("current", "viewer", "render", "display", "bypass", "lock"):
            if flags.get(key):
                parts.append(f"{key} 1" if key == "viewer" else f"{key} on")
        return (" ".join(parts) + " ") if parts else ""

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

        # Palette / pre-built component reference: the container IS a registered
        # component -> write the external-tox placeholder instead (raises on unknown).
        palette_name = container.get("palette")
        if palette_name:
            self.log(f"  Palette component '{palette_name}' as '{name}'")
            self._embed_palette_v2(palette_name, name, parent_path, position)
            return

        # BUG 2: honour the container's type/family (e.g. type:"geometry",family:"COMP")
        # instead of always writing a generic COMP:container, and apply its `parameters`
        # (instancing/instanceop/instancetx.../material) the same way operators do. Falls
        # back to COMP:container when no type is given (legacy copy-paste containers).
        td_type = self._map_op_type(container.get("type", "container"),
                                    parent_path, container.get("family"))

        self.log(f"  Creating container: {name} ({td_type}, {len(operators)} operators)")

        # Write container .n file (honor the container's render/display/... flags — BUG-2)
        self._write_file(f"{container_path}.n", f"""{td_type}
tile {position[0]} {position[1]} 200 150
flags =  {self._flags_tokens(container.get("flags", {}) or {})}parlanguage 0
end
""")

        # Write container .parm file (apply the container's own parameters via the shared loop)
        container_params = container.get("parameters", {}) or {}
        parm_lines = ["?"]
        parm_lines += self._param_lines(container_params, td_type, container.get("type", "container"),
                                        container_path, parent_path, name)
        parm_lines.append("?")
        self._write_file(f"{container_path}.parm", "\n".join(parm_lines) + "\n")

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

    def _param_lines(self, params, td_type, op_type, full_path, container_path, name) -> list:
        """Build the .parm body lines (between the leading/trailing '?') from a builder
        `parameters` dict: ground-truth validation + name resolution, vector/indexed
        expansion, expression detection and the expression-map overlay. Shared by
        _write_operator and _write_container so COMP containers apply their `parameters`
        (instancing/instanceop/instancetx.../material) the same way operators do (BUG 2)."""
        lines = []

        # Sibling-collision guard: the set of codes the design fed verbatim. A fed code
        # whose KB alias remaps it onto ANOTHER fed sibling (e.g. Group POP `group` ->
        # `grname`, which is also fed) is a spurious remap — emitting both writes the same
        # .parm line twice and TD's last-wins parse silently zeroes the real value. When
        # that happens we keep the code as-is (identity). Normal single-form aliasing
        # (only the display name fed, not the real code) is untouched.
        fed_codes_lower = {str(k).lower() for k in params}

        for param_name, param_value in params.items():
            # Handle resolution specially
            if param_name.lower() == "resolution" and isinstance(param_value, (list, tuple)):
                lines.append(_parm_line("resolutionw", 0, param_value[0]))
                lines.append(_parm_line("resolutionh", 0, param_value[1]))
                continue

            # Handle vector parameter expansion: t, r, s, p, pivot → tx/ty/tz, rx/ry/rz, etc.
            vector_params = {
                # 3-component vectors (XYZ)
                't': ['tx', 'ty', 'tz'],
                'r': ['rx', 'ry', 'rz'],
                's': ['sx', 'sy', 'sz'],
                'p': ['px', 'py', 'pz'],
                'pivot': ['pivotx', 'pivoty', 'pivotz'],
                # NOTE: 'scale' intentionally NOT expanded -- on many ops (Camera COMP,
                # Transform COMP, ...) `scale` is a SCALAR "Uniform Scale" param; mapping it
                # to sx/sy/sz clobbered/dropped it (gate finding). Use 's' for a 3-vector.
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
            if param_name.lower() in vector_params and isinstance(param_value, (list, tuple)) and len(param_value) > 1:
                component_names = vector_params[param_name.lower()]
                for i, comp_name in enumerate(component_names):
                    if i < len(param_value):
                        comp_value = param_value[i]
                        # Check if component value is an expression
                        if isinstance(comp_value, str) and _is_expression(comp_value):
                            lines.append(_parm_line(comp_name, 49, 0, comp_value))
                        else:
                            td_value = self._format_param_value(comp_value)
                            lines.append(_parm_line(comp_name, 0, td_value))
                continue

            # Handle indexed params like fromrange: [0, 1] → fromrange1: 0, fromrange2: 1
            if param_name.lower() in indexed_params and isinstance(param_value, (list, tuple)):
                base_name = indexed_params[param_name.lower()]
                for i, val in enumerate(param_value):
                    indexed_name = f"{base_name}{i+1}"
                    if isinstance(val, str) and _is_expression(val):
                        lines.append(_parm_line(indexed_name, 49, 0, val))
                    else:
                        td_value = self._format_param_value(val)
                        lines.append(_parm_line(indexed_name, 0, td_value))
                continue

            # Extract family from TD type (e.g., "CHOP:analyze" -> "CHOP")
            family = td_type.split(":")[0] if ":" in td_type else None

            # BUG-001 FIX: Use KB-derived param name resolver
            # Correctly maps user-friendly names to TD internal names
            op_type_short = op_type.split(':')[-1] if ':' in op_type else op_type
            td_param_name = resolve_param_name(op_type_short, family or "", param_name)

            # Sibling-collision guard (see fed_codes_lower above): if the resolver remapped
            # this code onto a DIFFERENT code the design also fed verbatim, honor the code
            # as given rather than duplicate the sibling's .parm line.
            if (td_param_name != param_name
                    and str(td_param_name).lower() in fed_codes_lower
                    and str(td_param_name).lower() != str(param_name).lower()):
                td_param_name = param_name

            # Handle expression dict format: {"expr": "...", "value": ...} or {"expression": "..."}
            inline_expression = None
            if isinstance(param_value, dict):
                inline_expression = param_value.get("expr") or param_value.get("expression")
                if inline_expression:
                    # Extract the constant value if provided, otherwise use 0
                    param_value = param_value.get("value", 0)
            elif isinstance(param_value, str):
                # Auto-detect expression strings containing TD Python patterns; both
                # the raw and resolved names are checked against _NEVER_EXPR_PARAMS
                # so constant file paths (externaltox) are never promoted.
                if _is_expression(param_value, param_name, td_param_name):
                    inline_expression = param_value
                    param_value = 0  # Default value for expression parameters

            # Resolve the value to TD's serialized form (menu label -> internal value,
            # bool -> on/off). The former ground_truth.py param-schema validation layer was
            # INERT since birth (it pointed at a never-shipped corpus and every lookup
            # fail-soft returned "invalid", so this menu-resolve branch always ran); it was
            # quarantined in W3a. Name resolution is done above by resolve_param_name against
            # the shipped KB — the single source of truth. See quarantine/README.md.
            td_value = resolve_menu_value(td_param_name, param_value)

            # Check if there's an expression for this param (inline or from expressions map)
            expr_key = f"{full_path.replace('project1/', '')}/{param_name}"
            alt_expr_key = f"{container_path.replace('project1/', '')}/{name}/{param_name}"

            expression = inline_expression or self.expressions.get(expr_key) or self.expressions.get(alt_expr_key)

            if expression:
                # Mode 49 = Python expression (mode 17 is for CHOP expressions).
                lines.append(_parm_line(td_param_name, 49, td_value, expression))
            else:
                # Mode 0 = constant
                lines.append(_parm_line(td_param_name, 0, td_value))

        return lines

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

        if is_comp_type and has_children and not (op.get("external_tox") or op.get("externaltox")):
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
        # PALETTE / PRE-BUILT COMPONENT REFERENCE
        # Usage: {"name": "audio", "palette": "audioAnalysis"}
        # Writes an external-tox placeholder from KB/palette_components.json; raises
        # on unknown names. (The legacy embed_tox / palette_runtime fields are gone --
        # reference unregistered .tox files with 'external_tox' instead.)
        # =================================================================
        palette_component = op.get("palette")
        if palette_component:
            self._embed_palette_v2(palette_component, name, container_path, position)
            return

        # =================================================================
        # STANDARD OPERATOR BUILDING
        # =================================================================

        # Map to TouchDesigner type (pass explicit family if provided)
        td_type = self._map_op_type(op_type, container_path, op_family)

        # Round-4 #1 — external-tox component reference. The op points at an external .tox
        # file instead of embedding it: write a COMP whose externaltox/enableexternaltox
        # params load that file's contents on open (a compartmentalised, reusable, file-backed
        # component). Defaults to a base COMP unless the design gives an explicit COMP type.
        # Recorded for the per-project build-log component summary.
        # The path is emitted RAW (mode 0, quoted), NOT through _param_lines: its expression
        # auto-detection false-positives on substrings like 'ext.' in 'text.tox' and would
        # silently promote a constant file path to a broken mode-49 expression.
        external_raw_lines = []
        external_tox = op.get("external_tox") or op.get("externaltox")
        if external_tox:
            if not (op_family and op_family.upper() == "COMP"):
                td_type = "COMP:base"
            tox_ref = str(external_tox).replace("\\", "/")
            external_raw_lines.append(_parm_line("externaltox", 0, tox_ref))
            external_raw_lines.append(_parm_line("enableexternaltox", 0, "on"))
            # subcompname loads a wrapper .tox's inner comp directly (palette-proven
            # mechanism); emitted RAW like externaltox — never through _param_lines
            # expression auto-detection.
            for pkey in list(params.keys()):
                if pkey.lower() == "subcompname":
                    external_raw_lines.append(
                        _parm_line("subcompname", 0, str(params.pop(pkey))))
                    break
            comp_path = f"{container_path}/{name}".replace("project1/", "")
            self.external_components.append(
                {"name": name, "path": comp_path, "tox": tox_ref, "td_type": td_type})
            # Contents load from the .tox at runtime; create an empty dir to load into.
            (self.project_dir / f"{container_path}/{name}").mkdir(parents=True, exist_ok=True)
            # BUG-3: interface entry primed by _prepass_component_io; record the real path.
            if name in self.palette_io_map:
                self.palette_io_map[name]["path"] = f"{container_path}/{name}"

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
        # BUG 4: a GLSL POP's `uniforms` must also become Vectors-page uniforms. Unlike the
        # GLSL TOP (which uses the _build_glsl_parm early-return path), a glslPOP keeps its
        # normal parm flow (outputattrs / Create-Attributes / computedat wiring) and we
        # append the uniform lines into it below. GLSL POP + GLSL Advanced POP carry the
        # Vectors page.
        is_glsl_pop = td_type in ("POP:glsl", "POP:glsladv")

        # Live create() auto-docks an op's helper DATs (GLSL shader/info DATs, callback
        # script DATs, table DATs, ...); the offline builder must replicate it. Driven by
        # the docked_dats KB (KB/docked_dats.json) for ANY op with a spec -- the builder
        # creates + docks + file-links the children and wires the host's link params
        # (callbacks/pixeldat/dat/...) to them; experts only author the content. Wiring is
        # collected here and written into the host .parm below via _parm_line, bypassing
        # param validation (see docked_wiring).
        docked_wiring = {}
        docked_specs = _load_docked_dats().get(td_type)
        if docked_specs:
            docked_wiring = self._write_docked_dats(name, container_path, position, td_type, op)
            # docked_wiring (host_param -> child DAT name) is handed to _build_glsl_parm
            # explicitly below; it must NOT be written back into `op["parameters"]`.
            # `op` is the CALLER's design dict — persisting the docked children there makes
            # a REUSED design lose them on a second build (the _write_docked_dats skip at
            # `(op.get("parameters") or {}).get(host_param)` fires the 2nd time). See the
            # double-build regression test.
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

        # BUG-3: an external-tox placeholder's own .n must carry NO inputs block — TD
        # silently drops sibling-name inputs on a COMP whose connectors don't exist until
        # its external tox loads (palette parity). Its in-wires serialize instead as the
        # TD-native compinputs block in <name>.network, written after the .parm below.
        if external_tox:
            inputs = []

        # Resolve palette sources to internal output operators
        if inputs:
            inputs = [self._resolve_palette_source(src, consumer=name) for src in inputs]

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

        # Builder-convenience: a GLSL POP imported with outputattrs='' leaves P undeclared
        # and fails to compile. Default outputattrs='P' when the design omits it (mirrors the
        # sopToCHOP attribscope default above); an explicit value is preserved.
        if is_glsl_pop and "outputattrs" not in params:
            params["outputattrs"] = "P"
            self.log(f"    Auto-set {name}.outputattrs = P (GLSL POP default)")

        # Build .n file content (honor the operator's render/display/... flags — BUG-2)
        n_content = f"""{td_type}
tile {position[0]} {position[1]} 130 90
flags =  {self._flags_tokens(op.get("flags", {}) or {})}parlanguage 0
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

        # GLSL TOP with uniforms: Use special parm builder. Pass docked_wiring so the
        # host's docked-DAT links (e.g. pixeldat -> <op>_pixel) land in its .parm without
        # mutating the caller's design dict.
        if is_glsl_top and glsl_uniforms:
            self._build_glsl_parm(op, full_path, docked_wiring)
            return  # Skip regular parm generation

        # Build .parm file content using ground truth validation. The per-param loop is
        # shared with containers via _param_lines() so a geometry/base COMP applies its
        # `parameters` the same way an operator does (BUG 2).
        parm_lines = ["?"]
        parm_lines += self._param_lines(params, td_type, op_type, full_path, container_path, name)

        # Wire host -> its docked children (callbacks/pixeldat/computedat/dat/...). Raw =
        # bypasses param validation (builder-owned links, not authored params) to match
        # TD's serialization (e.g. `dat 0 ramp1_keys`); serialization itself stays
        # quoting-aware via _parm_line.
        for hp, child in docked_wiring.items():
            parm_lines.append(_parm_line(hp, 0, child))

        # external-tox reference lines (raw, see the external_tox block above).
        parm_lines.extend(external_raw_lines)

        # BUG 4: GLSL POP Vectors-page uniforms (vec{N}name / vec{N}type / vec{N}value{x..}).
        if is_glsl_pop and glsl_uniforms:
            parm_lines.extend(self._glsl_pop_uniform_lines(glsl_uniforms))

        parm_lines.append("?")
        self._write_file(f"{full_path}.parm", "\n".join(parm_lines) + "\n")

        # BUG-3: wires INTO an external-tox comp -> TD-native compinputs block in
        # <name>.network (same machinery as palette placeholders; policy inside).
        if external_tox:
            self._write_palette_network_file(name, container_path)

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
        # A compute-only GLSL op (e.g. glslPOP) may author its shader under the generic
        # `shader`/`content` field; allow that fallback for the compute role ONLY when this
        # op has no separate pixel DAT, so a GLSL TOP's pixel shader is never duplicated
        # into its compute DAT (BUG 3).
        has_pixel = any(s.get("role") == "pixel" for s in specs)
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
                parm = ("?\n" + _parm_line("op", 0, host_name) + "\n"
                        + _parm_line("language", 0, "text") + "\n?\n")
            elif dat in ("text", "table"):
                content = self._authored_for_role(op, spec.get("role", ""), allow_generic=not has_pixel) or spec.get("stub", "")
                fdir = self.output_dir / spec["file_dir"]
                fdir.mkdir(parents=True, exist_ok=True)
                fpath = fdir / f"{child}.{spec['file_ext']}"
                fpath.write_text(content, encoding="utf-8", newline="\n")
                # Absolute path: _parm_line quotes it when the output root contains
                # a space -- unquoted it truncated AND dropped the params below it.
                fabs = str(fpath.resolve()).replace("\\", "/")
                n = (f"DAT:{dat}\ntile {ix} {iy} 130 90\nflags =  {flags} parlanguage 0\n"
                     f"color 0.67 0.67 0.67 \ndock {host_name}\nend\n")
                parm = ("?\n" + _parm_line("file", 0, fabs) + "\n"
                        + _parm_line("syncfile", 0, "on") + "\n"
                        + _parm_line("loadonstart", 0, "on") + "\n")
                if dat == "text":
                    parm += _parm_line("language", 0, spec.get("language") or "text") + "\n"
                    if spec.get("extension"):
                        parm += _parm_line("extension", 0, spec["extension"]) + "\n"
                parm += "?\n"
            else:
                # special docked op (e.g. dmxmap): fileless, child points back at host
                n = (f"{family}:{dat}\ntile {ix} {iy} 130 90\nflags =  {flags} parlanguage 0\n"
                     f"color 0.67 0.67 0.67 \ndock {host_name}\nend\n")
                parm = "?\n"
                if spec.get("child_param"):
                    parm += _parm_line(spec["child_param"], 0, host_name) + "\n"
                parm += "?\n"
                self.log(f"    [docking] note: special docked type '{dat}' on {host_name} "
                         f"({child}) written best-effort -- verify")
            self._write_file(f"{child_rel}.n", n)
            self._write_file(f"{child_rel}.parm", parm)
            if spec.get("host_param"):
                wiring[spec["host_param"]] = child
        self.log(f"    [docking] {host_name}: {[s['suffix'] for s in specs]}")
        return wiring

    def _authored_for_role(self, op: dict, role: str, allow_generic: bool = False):
        """Return the author-provided content for a docked child's role (the shader/script
        the expert wrote in the design), or None to fall back to the spec's default stub.
        The design may name it by role or a common alias (e.g. role 'pixel' <- op['shader']).

        allow_generic: when True the compute role ALSO accepts the generic `shader`/
        `content`/`text` fields. This is the GLSL-POP case (BUG 3) -- a compute-only op
        whose shader the experts author under `shader`/`content` (the TOP `pixel` role
        already accepts `shader`). It is gated off for ops that also have a separate pixel
        DAT (a GLSL TOP) so a TOP's pixel `shader` is never duplicated into its compute
        DAT -- the caller passes allow_generic=not has_pixel (see _write_docked_dats)."""
        role_fields = {
            "pixel":     ["shader", "pixel", "pixelshader", "fragment", "frag", "text"],
            "compute":   ["compute", "computeshader"],
            "vertex":    ["vertex", "vertexshader", "vert"],
            "callbacks": ["callbacks", "script", "callback"],
            "rules":     ["rules"],
        }
        fields = list(role_fields.get(role, [role]))
        if allow_generic and role == "compute":
            fields += ["shader", "content", "text"]
        for field in fields:
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
        parm_content = ("?\n" + _parm_line("op", 0, host_name) + "\n"
                        + _parm_line("language", 0, "text") + "\n?\n")
        self._write_file(f"{info_rel}.n", n_content)
        self._write_file(f"{info_rel}.parm", parm_content)
        self.log(f"    [F6] Auto-added docked Info DAT '{host_name}_info' -> {host_name}")

    def _build_glsl_parm(self, op: dict, full_path: str, docked_wiring: dict = None):
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
        # Local view only — never mutate the caller's design dict. docked_wiring carries the
        # builder-owned docked-DAT links (host_param -> child), which _write_docked_dats only
        # emits for children the design didn't already provide, so a plain merge is safe.
        params = dict(op.get("parameters", {}))
        if docked_wiring:
            params.update(docked_wiring)
        uniforms = op.get("uniforms", [])

        self.log(f"    Building GLSL parm with {len(uniforms)} uniforms")

        # Shader DAT reference (pixeldat or shader_dat)
        shader_dat = params.get("pixeldat") or params.get("shader_dat") or op.get("shader_dat")
        if shader_dat:
            lines.append(_parm_line("pixeldat", 0, shader_dat))

        # Resolution
        if "resolutionw" in params:
            lines.append(_parm_line("resolutionw", 0, params["resolutionw"]))
        if "resolutionh" in params:
            lines.append(_parm_line("resolutionh", 0, params["resolutionh"]))

        # Other standard parameters. Raw = no KB validation/auto-promotion (this early-
        # return path deliberately bypasses _param_lines); serialization stays
        # quoting-aware via _parm_line so a spaced value can't desync the file.
        for pname, pval in params.items():
            if pname not in ("pixeldat", "shader_dat", "resolutionw", "resolutionh"):
                lines.append(_parm_line(pname, 0, pval))

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
            lines.append(_parm_line(f"vec{idx}name", 0, name))

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
                    # Mode 49 = Python expression (quoted -- a spaced expression
                    # otherwise truncates AND desyncs every following param).
                    lines.append(_parm_line(f"vec{idx}value{comp}", 49, v, comp_expr))
                else:
                    # Mode 0 = constant (TD sometimes uses 32 for reference values)
                    lines.append(_parm_line(f"vec{idx}value{comp}", 0, v))

        lines.append("?")
        self._write_file(f"{full_path}.parm", "\n".join(lines) + "\n")

    def _glsl_pop_uniform_lines(self, uniforms) -> list:
        """Build GLSL POP Vectors-page uniform .parm lines (BUG 4).

        Accepts the dict form ``{name: value}`` (what the GAPS report passes) and the list
        form ``[{"name","value"[, "type","expr"]}]``. Scalars and component lists are both
        supported. Emits, per uniform N:
            vec{N}name 0 <name>
            vec{N}type 0 <float|vec2|vec3|vec4>     # inferred from #components unless given
            vec{N}value{x,y,z,w} <mode> <value> [expr]
        `vec{N}type` is required on a GLSL POP to declare the uniform (the GLSL TOP path in
        _build_glsl_parm omits it). Returns the lines (no leading/trailing `?`)."""
        if isinstance(uniforms, dict):
            items = [{"name": k, "value": v} for k, v in uniforms.items()]
        elif isinstance(uniforms, list):
            items = [u for u in uniforms if isinstance(u, dict)]
        else:
            return []

        type_by_n = {1: "float", 2: "vec2", 3: "vec3", 4: "vec4"}
        suffixes = ["x", "y", "z", "w"]
        lines = []
        for idx, uni in enumerate(items):
            name = uni.get("name", f"uniform{idx}")
            value = uni.get("value", 0)
            expr = uni.get("expr") or uni.get("expression")

            comps = list(value) if isinstance(value, (list, tuple)) else [value]
            comps = comps[:4] if comps else [0]
            utype = uni.get("type") or type_by_n.get(len(comps), "float")

            lines.append(_parm_line(f"vec{idx}name", 0, name))
            lines.append(_parm_line(f"vec{idx}type", 0, utype))
            for i, comp in enumerate(comps):
                # Per-component expression: a single string applies to x; a list/dict maps
                # by index/component (mode 49 = Python expression, else mode 0 = constant).
                comp_expr = None
                if isinstance(expr, str) and i == 0:
                    comp_expr = expr
                elif isinstance(expr, (list, tuple)) and i < len(expr):
                    comp_expr = expr[i]
                elif isinstance(expr, dict):
                    comp_expr = expr.get(suffixes[i])
                if comp_expr:
                    lines.append(_parm_line(f"vec{idx}value{suffixes[i]}", 49, comp, comp_expr))
                else:
                    lines.append(_parm_line(f"vec{idx}value{suffixes[i]}", 0, comp))
        return lines

    # =========================================================================
    # PALETTE / PRE-BUILT COMPONENT REFERENCE (v2 -- external-tox placeholder)
    # =========================================================================

    def _prepass_component_io(self, network: dict):
        """BUG-3: prime palette_io_map for every palette/external_tox component BEFORE
        any operator is written. Op writing is sequential over design order, so a
        consumer listed before its component would otherwise resolve against an empty
        map (latent for palette, the actual wire drop for external_tox). No file writes
        here; wiring policy is enforced at the consumption points
        (_resolve_palette_source / _write_palette_network_file), which run after the
        relevant connections are registered — container-local connections only enter
        self.connections during _write_container."""
        def walk(ops, containers, parent=None):
            for o in ops or []:
                yield o, parent
            for c in containers or []:
                yield c, parent  # container-level palette reference (dict shape compatible)
                inner = c.get("network", {}) or {}
                yield from walk(
                    c.get("operators") or inner.get("operators") or c.get("children") or [],
                    c.get("containers") or inner.get("containers") or [],
                    c.get("name"))

        for op, parent in walk(network.get("operators", []), network.get("containers", [])):
            if not isinstance(op, dict):
                continue
            name = op.get("name")
            if not name or name in self.palette_io_map:
                continue  # bare-name keying: first definition wins (documented limitation)
            palette_component = op.get("palette")
            external_tox = op.get("external_tox") or op.get("externaltox")
            if palette_component:
                entry = self._palette_io_entry(palette_component)
            elif external_tox:
                entry = self._external_io_entry(name, op, external_tox)
            else:
                continue
            # rel_path = how a sibling wire to this comp is expanded by _write_container
            # ('<immediate container>/<name>'), or the bare name at top level. The
            # container-qualified source fallback in _resolve_palette_source matches on
            # this exact string so a plain op whose basename collides with a registered
            # comp is NOT silently rewritten to '<container>/<comp>/out1' (G3/G4).
            entry["rel_path"] = f"{parent}/{name}" if parent else name
            self.palette_io_map[name] = entry

    def _palette_io_entry(self, component_name: str) -> dict:
        """Registry-backed io_map entry for a `palette` reference (raises the unknown-name
        ValueError). index_authority: shipped registry entries are live-harvested, so their
        index order is connector truth and a bare wire may bind index 0; entries stamped
        harvest.method "offline_manifest" (user registrations) are NAME authority only and
        get the strict single-connector policy. An absent stamp defaults to index trust
        (pre-stamp registries + test fixtures keep their pinned behavior)."""
        registry = _load_palette_components().get("components", {})
        spec = registry.get(component_name)
        if spec is None:
            known = sorted(registry.keys())
            hint = ", ".join(known[:10]) + ("..." if len(known) > 10 else "")
            raise ValueError(
                f"Unknown palette component '{component_name}': not in KB/palette_components.json "
                f"({len(known)} registered{': ' + hint if known else ''}). Use an exact registered "
                f"name, or reference an unregistered .tox file directly with 'external_tox'."
            )
        in_operators = []
        for item in sorted(spec.get("inputs", []) or [], key=lambda x: x.get("index", 0)):
            in_operators.append({"name": item.get("in_op"), "family": item.get("family", "")})
        out_operators = []
        for item in sorted(spec.get("outputs", []) or [], key=lambda x: x.get("index", 0)):
            out_operators.append({"name": item.get("out_op"), "family": item.get("family", "")})
        method = (spec.get("harvest") or {}).get("method", "")
        offline_only = method == "offline_manifest"
        return {
            "inputs": in_operators,
            "outputs": out_operators,
            "path": None,  # accurate container path recorded at op-write time
            "index_authority": not offline_only,
            "origin": "user_registry" if offline_only else "palette",
            "tox": str(spec.get("tox_path", f"{component_name}.tox")).replace("\\", "/"),
            "unavailable_message": None,
        }

    def _resolve_external_tox_path(self, tox_ref: str):
        """Locate the referenced .tox at build time. Absolute paths stand alone; relative
        paths anchor to output_dir ONLY (TD resolves them against the project folder at
        load, and the project lands in output_dir — a CWD fallback would make builds
        machine-state-dependent). Returns (resolved_path_or_None, tried_paths)."""
        p = Path(tox_ref)
        tried = [p] if p.is_absolute() else [self.output_dir / tox_ref]
        for cand in tried:
            try:
                if cand.is_file():
                    return cand, tried
            except OSError:
                pass
        return None, tried

    def _external_io_entry(self, name: str, op: dict, external_tox) -> dict:
        """Manifest-backed io_map entry for an external_tox reference (BUG-3).

        Best-effort: a missing/unreadable manifest (or an unresolvable wrapper) primes an
        UNUSABLE entry (inputs/outputs None) carrying the composed failure message; the
        consumption points raise it only when the comp is actually wired, so an unwired
        placeholder keeps building exactly as before (pinned behavior). The offline
        manifest name-sorts — it is a NAME authority only, so index_authority is always
        False and a bare wire binds only a single-connector comp."""
        tox_ref = str(external_tox).replace("\\", "/")
        entry = {
            "inputs": None,
            "outputs": None,
            "path": None,
            "index_authority": False,
            "origin": "external_tox",
            "tox": tox_ref,
            "unavailable_message": None,
        }
        resolved, tried = self._resolve_external_tox_path(tox_ref)
        if resolved is None:
            entry["unavailable_message"] = (
                f"external_tox component '{name}' is wired but its .tox was not found "
                f"(tried {', '.join(repr(str(t)) for t in tried)}). The builder needs the file "
                f"at build time to resolve the component's inner in/out ops — a component is "
                f"never itself a data source. Fix the path, or wire only explicit out-op paths "
                f"('{name}/<outOp>') with no inputs into '{name}'.")
        else:
            try:
                res = _load_external_manifest(resolved)
            except Exception as e:
                kind = getattr(e, "kind", "expand_failed")
                if kind == "tool_missing":
                    entry["unavailable_message"] = (
                        f"external_tox component '{name}' is wired but its interface cannot be "
                        f"read: {e} Alternatively wire only explicit out-op paths "
                        f"('{name}/<outOp>') with no inputs into '{name}'.")
                elif kind == "timeout":
                    entry["unavailable_message"] = (
                        f"external_tox component '{name}': {e}. The file may be very large or "
                        f"damaged; expand it once manually (expand_toe_file) to inspect it.")
                else:
                    entry["unavailable_message"] = (
                        f"external_tox component '{name}': '{tox_ref}' could not be read ({e}). "
                        f"Re-save the .tox from TouchDesigner, or wire only explicit out-op "
                        f"paths with no inputs.")
            else:
                man = res.get("manifest") or {}
                has_subcomp = any(k.lower() == "subcompname"
                                  for k in (op.get("parameters") or {}))
                if man.get("wrapper") and not has_subcomp:
                    inner = (res.get("subcompname")
                             or (man.get("interface_path") or "").split("/")[-1])
                    entry["unavailable_message"] = (
                        f"'{name}' references a wrapper-style .tox ({tox_ref}; interface at "
                        f"'{man.get('interface_path')}'): its in/out ops are not direct children "
                        f"of the loaded root, so wires cannot bind. Set \"parameters\": "
                        f"{{\"subcompname\": \"{inner}\"}} on '{name}' so TouchDesigner loads "
                        f"the inner component directly, or register the component in the user "
                        f"registry (registration records its subcompname, and the \"palette\" "
                        f"field then emits it automatically; a raw external_tox reference still "
                        f"needs the explicit parameter).")
                else:
                    entry["inputs"] = [
                        {"name": d["name"], "family": (d.get("op_type") or "").split(":")[0]}
                        for d in man.get("inputs", [])]
                    entry["outputs"] = [
                        {"name": d["name"], "family": (d.get("op_type") or "").split(":")[0]}
                        for d in man.get("outputs", [])]
        if entry["unavailable_message"]:
            logger.warning("%s; building the placeholder unwired.", entry["unavailable_message"])
        return entry

    def _embed_palette_v2(self, component_name: str, target_name: str, container_path: str, position: list) -> bool:
        """Write a placeholder COMP that loads a registered pre-built component.

        The placeholder carries enableexternaltox + externaltox + subcompname, so the
        component's contents load from the USER'S OWN TD install / palette / project
        when the file opens (nothing is embedded -- no redistribution). subcompname
        loads the inner comp of Derivative's metadata-wrapper .tox directly and TD
        retypes the node; the KB inner_type keeps the offline .n token truthful.

        Wiring survives external loading ONLY in TD's native serialization (verified
        live, TD 2025.32820):
          - wires INTO the comp   -> compinputs block in <comp>.network, re-bound by
                                     INNER in-op name (_write_palette_network_file);
          - wires OUT of the comp -> consumers reference '<comp>/<inner out-op>' in
                                     their .n inputs (_resolve_palette_source via
                                     palette_io_map).
        A plain sibling-name wire to the placeholder is silently DROPPED by TD (its
        connectors don't exist until the external tox loads), so the placeholder .n
        carries NO inputs block.

        The externaltox value is emitted RAW (never through _param_lines expression
        auto-detection, which false-positives on paths like 'text.tox'): derivative and
        user sources are parameter EXPRESSIONS off app.samplesFolder /
        app.userPaletteFolder (portable across installs and OneDrive-redirected
        Documents folders); project sources are project-relative constants.

        Raises ValueError when the component is not in KB/palette_components.json --
        a silently-empty placeholder would be a wrong-output trap.
        """
        registry = _load_palette_components().get("components", {})
        spec = registry.get(component_name)
        if spec is None:
            known = sorted(registry.keys())
            hint = ", ".join(known[:10]) + ("..." if len(known) > 10 else "")
            raise ValueError(
                f"Unknown palette component '{component_name}': not in KB/palette_components.json "
                f"({len(known)} registered{': ' + hint if known else ''}). Use an exact registered "
                f"name, or reference an unregistered .tox file directly with 'external_tox'."
            )

        source = spec.get("source", "derivative")
        tox_path = str(spec.get("tox_path", f"{component_name}.tox")).replace("\\", "/")
        inner_type = spec.get("inner_type") or "COMP:base"
        full_path = f"{container_path}/{target_name}"

        self.log(f"    Palette '{component_name}' -> placeholder '{target_name}' "
                 f"({inner_type}, source={source})")

        # Placeholder .n: inner-type token, NO inputs block (see docstring).
        self._write_file(f"{full_path}.n",
                         f"{inner_type}\ntile {position[0]} {position[1]} 130 90\n"
                         f"flags =  parlanguage 0\nend\n")

        # Placeholder .parm: raw = bypasses _param_lines auto-detection; serialization
        # via _parm_line (quoting-aware).
        parm_lines = ["?"]
        if source == "user":
            expr = f"app.userPaletteFolder + {_py_str_literal('/' + tox_path)}"
            parm_lines.append(_parm_line("externaltox", 49, "", expr))
        elif source == "project":
            parm_lines.append(_parm_line("externaltox", 0, tox_path))
        else:  # derivative (default)
            expr = f"app.samplesFolder + {_py_str_literal('/Palette/' + tox_path)}"
            parm_lines.append(_parm_line("externaltox", 49, "", expr))
        parm_lines.append(_parm_line("enableexternaltox", 0, "on"))
        if spec.get("wrapper") and spec.get("subcompname"):
            parm_lines.append(_parm_line("subcompname", 0, str(spec["subcompname"])))
        parm_lines.append("?")
        self._write_file(f"{full_path}.parm", "\n".join(parm_lines) + "\n")

        # Contents load from the external .tox at open; create the empty dir to load into.
        (self.project_dir / full_path).mkdir(parents=True, exist_ok=True)

        # Interface metadata -> palette_io_map, so downstream consumers resolve
        # 'name' -> 'name/<out op>' and the compinputs .network block can be written.
        # Normally primed by _prepass_component_io (a consumer may be written first);
        # rebuilt here as a safety net for direct calls.
        entry = self.palette_io_map.get(target_name) or self._palette_io_entry(component_name)
        entry["path"] = full_path
        # Normally the pre-pass stamps rel_path (container-aware); a direct _embed call
        # (no pre-pass) defaults to the top-level bare name so the collision guard has a
        # value to match against.
        entry.setdefault("rel_path", target_name)
        self.palette_io_map[target_name] = entry

        # Wires INTO the placeholder: TD-native compinputs block in <comp>.network.
        self._write_palette_network_file(target_name, container_path)

        # Build-log component summary (same record the external_tox path keeps).
        self.external_components.append({
            "name": target_name,
            "path": full_path.replace("project1/", ""),
            "tox": f"palette:{component_name} ({source}: {tox_path})",
            "td_type": inner_type,
        })
        return True

    def _write_palette_network_file(self, comp_name: str, container_path: str):
        """Write the TD-native compinputs block routing in-wires to a component's INNER
        in ops (`<comp>.network`); TD re-binds each row by inner in-op NAME + family
        after the external tox loads. In-op names + families come from the comp's
        palette_io_map entry (registry or build-time manifest).

        Wire assignment (BUG-3 policy):
          - explicit `"to": "<comp>/<inOp>"` claims that named in-op (custom names
            included — the connection-map regex only normalizes in\\d*); an unknown
            inner name fails loud (it can never bind);
          - bare `"to": "<comp>"`: index-authority entries (live-harvested registry)
            fill unclaimed in-ops positionally in connector-index order — byte-identical
            to the legacy positional mapping; name-authority entries (external_tox
            manifests, offline user registrations) bind only a single-in-op comp,
            otherwise fail loud listing the candidates;
          - wired but interface unavailable (missing/unreadable .tox, unresolved
            wrapper) fails loud with the stored reason; a wired comp with zero in ops
            fails loud (the legacy silent drop is exactly the BUG-3 class);
          - sources are themselves resolved (comp -> comp/<out op>) — a comp is never
            a data source in a compinputs row either.

        Format (live-verified, byte shape pinned in tests):
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
        entry = self.palette_io_map.get(comp_name)
        if entry is None:
            return
        full_path = f"{container_path}/{comp_name}"
        short_path = full_path.replace("project1/", "")
        container_name = container_path.split("/")[-1] if "/" in container_path else container_path
        keys = []
        for k in (comp_name, short_path, full_path, f"{container_name}/{comp_name}"):
            if k not in keys:
                keys.append(k)

        # Explicit inner-name targets: '<key>/<suffix>' dsts.
        explicit = {}
        for k in keys:
            prefix = k + "/"
            for dst, srcs in self.connections.items():
                if dst.startswith(prefix):
                    suffix = dst[len(prefix):]
                    bucket = explicit.setdefault(suffix, [])
                    bucket.extend(s for s in srcs if s not in bucket)

        bare = []
        for k in keys:
            got = self.connections.get(k)
            if got:
                bare = list(got)
                break
        # The connection map double-stores '<comp>/inN' sources under the base key
        # (BUG-B); a source wired both ways keeps its explicit binding.
        claimed = {s for srcs in explicit.values() for s in srcs}
        bare = [s for s in bare if s not in claimed]

        if not explicit and not bare:
            return  # nothing wired in

        tox = entry.get("tox") or ""
        if entry.get("outputs") is None:  # manifest unavailable / wrapper unresolved
            raise ValueError(entry.get("unavailable_message")
                             or f"component '{comp_name}' is wired but its interface is "
                                f"unavailable at build time.")
        in_ops = entry.get("inputs") or []
        in_names = [d["name"] for d in in_ops]
        if not in_ops:
            src0 = (bare or [s for ss in explicit.values() for s in ss])[0]
            raise ValueError(
                f"Cannot wire '{src0}' into component '{comp_name}': '{comp_name}' ({tox}) "
                f"contains no in operators; it accepts no wired inputs.")
        for suffix in explicit:
            if suffix not in in_names:
                raise ValueError(
                    f"Connection targets '{comp_name}/{suffix}', but '{comp_name}' ({tox}) "
                    f"has no in op named '{suffix}'. Its in ops: {in_names}.")

        assign = {n: list(explicit.get(n, [])) for n in in_names}
        if bare:
            if entry.get("index_authority", True):
                unclaimed = [n for n in in_names if not assign[n]]
                # G1: index-authority comps used to positionally fill and SILENTLY drop
                # the overflow (self.log only) while name-authority comps fail loud for
                # the identical over-wire — a silent drop the fix exists to kill. Fail
                # loud symmetrically; correctly-counted wires keep the byte-identical fill.
                if len(bare) > len(unclaimed):
                    raise ValueError(
                        f"Cannot wire {len(bare)} bare input(s) into component "
                        f"'{comp_name}': '{comp_name}' ({tox}) has {len(unclaimed)} "
                        f"unclaimed in op(s) {unclaimed} of {in_names}. Name each target "
                        f"explicitly, e.g. \"to\": \"{comp_name}/{(unclaimed or in_names)[0]}\".")
                for n, s in zip(unclaimed, bare):
                    assign[n].append(s)
            else:
                if len(in_ops) == 1 and len(bare) == 1 and not explicit:
                    assign[in_names[0]].append(bare[0])
                else:
                    raise ValueError(
                        f"Cannot wire '{bare[0]}' into component '{comp_name}': '{comp_name}' "
                        f"({tox}) has {len(in_ops)} in ops: {in_names}. Name the target "
                        f"explicitly, e.g. \"to\": \"{comp_name}/{in_names[0]}\".")

        lines = ["1", "compinputs", "{"]
        idx = 0
        for d in in_ops:
            for src in assign[d["name"]]:
                resolved = self._resolve_palette_source(src, consumer=comp_name)
                # compinputs sources are sibling-relative to the comp's parent — strip a
                # same-container prefix (mirrors the .n inputs writer normalization).
                if resolved.startswith(container_name + "/"):
                    resolved = resolved[len(container_name) + 1:]
                lines.append(f"{idx} \t{resolved}")
                lines.append(f"\t{d['name']}")
                lines.append(f"\t{d['family']}")
                idx += 1
        if idx == 0:
            return
        lines.extend(["}", "end"])

        self._write_file(f"{full_path}.network", "\n".join(lines) + "\n")
        self.log(f"    Wrote .network file with {idx} external connection(s)")

    def _resolve_palette_source(self, source: str, consumer: str = None) -> str:
        """Resolve a palette/external/container COMP source to its inner out op.

        A component is never itself a data source — what it OUTPUTS lives on an inner
        out op, so a bare comp name in a source position can never bind (TD drops it
        at load). Resolution policy (BUG-3, evidence-driven):
          - index-authority entries (live-harvested registry): outputs[0] IS live
            connector 0 — legacy behavior, byte-compatible;
          - name-authority entries (build-time external_tox manifests, offline user
            registrations): auto-resolve ONLY a single out op — the offline manifest
            name-sorts, so outputs[0] of a multi-out comp would silently mis-wire;
            multiple candidates fail loud listing them;
          - zero out ops, or a wired comp whose interface is unavailable (missing/
            unreadable .tox, unresolved wrapper): fail loud;
          - explicit '<comp>/<op>' paths never reach the maps — verbatim pass-through.
        Container-qualified sources ('C/comp' from container-local connection
        expansion) resolve only when the qualified path EQUALS the comp's recorded
        rel_path (stamped in the pre-pass), so a plain op whose basename collides with a
        registered comp is never mis-rewritten to '<container>/<comp>/out1' (G3/G4).

        BUG-C FIX retained: in-design containers resolve via container_io_map.
        """
        entry = self.palette_io_map.get(source)
        if entry is None and "/" in source:
            # Container-qualified source ('C/fx' from container-local expansion): resolve
            # via the comp's RECORDED location, not a bare basename match — a plain op
            # whose name collides with a registered palette/external comp must not be
            # rewritten to '<container>/<comp>/out1' (G3/G4). rel_path is stamped in the
            # pre-pass to exactly the container-expanded form, so equality is precise.
            cand = self.palette_io_map.get(source.rsplit("/", 1)[-1])
            if cand is not None and cand.get("rel_path") == source:
                entry = cand
        if entry is not None:
            who = f"'{consumer}'" if consumer else "consumer"
            tox = entry.get("tox") or ""
            outputs = entry.get("outputs")
            if outputs is None:  # manifest unavailable / wrapper unresolved
                raise ValueError(entry.get("unavailable_message")
                                 or f"component '{source}' is wired but its interface is "
                                    f"unavailable at build time.")
            if not outputs:
                raise ValueError(
                    f"Cannot wire {who} from component '{source}': a component is never "
                    f"itself a data source, and '{source}' ({tox}) contains no out "
                    f"operators. Add an Out op inside the .tox, or remove this connection.")
            if entry.get("index_authority", True) or len(outputs) == 1:
                out_op = outputs[0]['name']
                resolved = f"{source}/{out_op}"
                self.log(f"    Resolved component source: {source} -> {resolved}")
                return resolved
            names = [d["name"] for d in outputs]
            raise ValueError(
                f"Cannot wire {who} from component '{source}': a component is never itself "
                f"a data source; reference its inner out op. '{source}' ({tox}) has "
                f"{len(names)} out ops: {names}. Use an explicit source, e.g. "
                f"\"from\": \"{source}/{names[0]}\".")

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

    # Internal name overrides - user name -> TD internal name (BUG-011 fix)
    # These are operators where the user-friendly name differs from TD's internal name
    INTERNAL_NAME_MAP = {
        "composite": "comp",  # Composite TOP internal name is "comp"
        "hsvadjust": "hsvadj",  # HSV Adjust TOP
        "audiospectrum": "audiospect",  # Audio Spectrum CHOP
        "audiodevicein": "audiodevin",  # Audio Device In CHOP
        "audiodeviceout": "audiodevout",  # Audio Device Out CHOP
        "audiooscillator": "audioosc",  # Audio Oscillator CHOP
        # POP operators whose TD .n token differs from the wiki/display-derived name
        # (BUG 1). Verified against a live TD save+expand of all 100 POPs: only these 7
        # differ; the rest match their basename. Without these, the builder writes e.g.
        # POP:pointgenerator and TD imports it as a base COMP (dropping numpoints).
        "pointgenerator": "pointgen",   # Point Generator POP
        "glsladvanced": "glsladv",      # GLSL Advanced POP
        "attributecombine": "attcombine",   # Attribute Combine POP
        "attributeconvert": "attconvert",   # Attribute Convert POP
        "lookupattribute": "lookupatt",     # Lookup Attribute POP
        "lookupchannel": "lookupchan",      # Lookup Channel POP
        "lookuptexture": "lookuptex",       # Lookup Texture POP
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

    def map_op_type(self, op_type: str, family: str = None) -> str:
        """Public, stable API: resolve a design ``(type, family)`` to the ``FAMILY:type``
        token the builder writes as the first line of an operator's ``.n`` file.

        This is the builder's authoritative op-token mapping — first the shipped
        ``KB/operators.json`` ``build_token`` grounding index (live-real tokens), then a
        legacy display-derived heuristic fallback for ungrounded ops. Pass the explicit
        ``family`` (``CHOP``/``TOP``/``SOP``/``DAT``/``COMP``/``MAT``/``POP``); a colon-form
        ``op_type`` (``"CHOP:noise"``) is returned normalized. Tools and the build gate must
        use THIS method — the private ``_map_op_type`` also does container-name family
        inference, which is a builder-internal heuristic, not part of the public contract.
        """
        return self._map_op_type(op_type, "", family)

    def _map_op_type(self, op_type: str, container_path: str, explicit_family: str = None) -> str:
        """Resolve a TD Designer type to the TouchDesigner ``FAMILY:type`` token written
        to the op's ``.n`` file.

        GROUNDING (the source fix): first consult the live-real ``build_token`` index
        (from the re-grounded ``operators.json``). When the op is grounded, return the
        captured live token directly -- this fixes BOTH the abbreviation mismatches
        (Camera ``COMP:camera`` -> ``COMP:cam``) and the wrong-family mismatches
        (Add ``SOP:add`` -> ``TOP:add``, where ``OP_TYPE_MAP`` used to override the
        explicit family). Falls back to the legacy derivation when the op isn't grounded
        (e.g. operators.json predates re-grounding, or a brand-new op)."""
        grounded = self._grounded_build_token(op_type, explicit_family)
        if grounded:
            self.log(f"  _map_op_type: grounded '{op_type}'/{explicit_family} -> {grounded}")
            return grounded
        return self._map_op_type_raw(op_type, container_path, explicit_family)

    def _grounded_build_token(self, op_type: str, explicit_family: str = None):
        """Look up the live-real build token for (family, op_type) in the grounding index.
        Returns None when not grounded (index empty or op absent).

        This is the BUILD-TIME half of the grounding override: it rewrites the emitted
        .n token to the captured live token per op. The validation-side half —
        engine/validation/grounding_validator.py (GroundingValidator.ground_design /
        .validate) — reads the SAME KB source (KB/operators.json build_token) so the
        builder and td_validate agree on grounding by construction."""
        idx = _load_build_token_index()
        if not idx:
            return None
        fam = (explicit_family or "").upper()
        t = op_type.split(":", 1)[1] if ":" in op_type else op_type
        if not fam and ":" in op_type:
            fam = op_type.split(":", 1)[0].upper()
        if not fam:
            return None
        key = _alnum(t)
        hit = idx.get((fam, key))
        if hit:
            return hit
        # OPType-style types carry the family as a suffix ("renameCHOP"); the
        # grounding aliases are family-stripped, so retry without it. Otherwise
        # the lookup misses and the legacy map emits an invalid .n token
        # (proven live: type "renameCHOP" imported as a baseCOMP placeholder).
        if key.endswith(fam.lower()) and len(key) > len(fam):
            return idx.get((fam, key[: -len(fam)]))
        return None

    def _map_op_type_raw(self, op_type: str, container_path: str, explicit_family: str = None) -> str:
        """Legacy wiki-display-derived resolver (INTERNAL_NAME_MAP + OP_TYPE_MAP + family
        inference). Used as the fallback when grounding has no entry for the op."""
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
        # BUG 1: also override whenever family is POP. OP_TYPE_MAP has ZERO POP entries, so
        # a POP basename that collides with a mapped SOP/TOP (box/tube/point/particle ->
        # SOP:box ...) would otherwise mis-resolve to the wrong family despite family:"POP".
        if explicit_family and (
            op_lower in self.AMBIGUOUS_OPERATORS
            or op_normalized_lower in self.AMBIGUOUS_OPERATORS
            or explicit_family.upper() == "POP"
        ):
            family_upper = explicit_family.upper()
            # BUG-011 FIX: Use internal name if different from user name
            internal_name = self.INTERNAL_NAME_MAP.get(op_lower, op_type)
            self.log(f"  Using explicit family {family_upper} for operator '{op_type}' -> {internal_name}")
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

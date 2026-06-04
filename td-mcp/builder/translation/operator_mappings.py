"""Operator type and parameter name mappings for TouchDesigner.

Merged from META_AGENTIC_TOOL/meta_agentic/execution/toe_builder_bridge.py
with all VANTA additions and bug fixes.
"""

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
    "lfo": "CHOP:lfo",
    "midiinCHOP": "CHOP:midiIn",
    "midiin": "CHOP:midiIn",

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
    "hsvAdjust": "TOP:hsvAdjust",  # Preserve case variant
    "bloom": "TOP:bloom",
    "out": "TOP:out",
    "null_top": "TOP:null",
    "switch": "TOP:switch",
    "threshold": "TOP:threshold",
    "reorder": "TOP:reorder",
    "render": "TOP:render",
    "resolution": "TOP:resolution",
    "transform_top": "TOP:transform",

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
    "particlesgpu": "COMP:particlesGpu",

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
    "forcegpu": "TOP:forceGpu",
    "pointrender": "TOP:pointRender",
}

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

# Conversion operator required parameters
CONVERSION_OP_REQUIRED_PARAMS = {
    "CHOP:sopto": {"required": "sop", "description": "SOP operator path to convert"},
    "CHOP:topto": {"required": "top", "description": "TOP operator path to convert"},
    "CHOP:datto": {"required": "dat", "description": "DAT operator path to convert"},
    "TOP:chopto": {"required": "chop", "description": "CHOP operator path to convert"},
    "SOP:chopto": {"required": "chop", "description": "CHOP operator path to convert"},
    "DAT:chopto": {"required": "chop", "description": "CHOP operator path to convert"},
    "DAT:sopto": {"required": "sop", "description": "SOP operator path to convert"},
}

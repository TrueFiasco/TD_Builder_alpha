#!/usr/bin/env python3
"""
Consolidate all operator semantic summaries into final YAML file.
Merges data from:
1. Existing partial file
2. Extracted wiki JSON files (for factual parameter names)
3. Session-generated summaries
"""

import json
import yaml
from pathlib import Path

OUTPUT_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_output")
FACTS_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts")

# All operator summaries generated in this session
SESSION_OPERATORS = {
    # Audio CHOPs
    "Analyze_CHOP": {
        "summary": "Analyzes input channel data and computes statistical measures like min, max, RMS, and average.",
        "parameters": {"function": "Type of analysis to perform", "minmax": "Compute min/max values", "rms": "Calculate root mean square", "average": "Calculate mean value"}
    },
    "Audio_Band_EQ_CHOP": {
        "summary": "Multi-band audio equalizer for independent frequency control across up to 8 bands.",
        "parameters": {"numbands": "Number of active EQ bands", "freq1": "Center frequency per band", "gain1": "Boost/cut level in dB", "q1": "Bandwidth/resonance factor"}
    },
    "Audio_Device_In_CHOP": {
        "summary": "Captures audio from system input devices like microphones and line-in.",
        "parameters": {"device": "Audio input device", "rate": "Sample rate in Hz", "channels": "Number of channels", "length": "Buffer length"}
    },
    "Audio_Device_Out_CHOP": {
        "summary": "Sends audio to system output devices like speakers.",
        "parameters": {"device": "Audio output device", "rate": "Sample rate", "channels": "Number of channels", "volume": "Output level"}
    },
    "Audio_Dynamics_CHOP": {
        "summary": "Compressor/expander/limiter for audio dynamics processing.",
        "parameters": {"threshold": "Level for processing", "ratio": "Compression ratio", "attack": "Response time", "release": "Recovery time", "makeup": "Gain compensation"}
    },
    "Audio_Filter_CHOP": {
        "summary": "Filters audio frequencies with lowpass, highpass, bandpass types.",
        "parameters": {"filtertype": "Filter topology", "cutoff": "Cutoff frequency", "q": "Resonance", "gain": "Output level"}
    },
    "Audio_Spectrum_CHOP": {
        "summary": "Analyzes audio frequency content via FFT for spectrum visualization.",
        "parameters": {"fftsize": "FFT window size", "samplerate": "Sample rate", "highfreq": "Upper frequency limit", "lowfreq": "Lower frequency limit"}
    },

    # Core CHOPs
    "Beat_CHOP": {
        "summary": "Detects beats and tempo in audio input by analyzing rhythm patterns.",
        "parameters": {"threshold": "Energy level for beat detection", "bpm": "Beats per minute", "tap": "Manual tempo input"}
    },
    "Bind_CHOP": {
        "summary": "Binds CHOP channels to parameters for bi-directional control.",
        "parameters": {"target": "Target parameter/CHOP", "method": "Binding method", "bindmode": "Uni/bi-directional"}
    },
    "Blend_CHOP": {
        "summary": "Blends between multiple input CHOPs using interpolation.",
        "parameters": {"blendweight": "Interpolation weight 0-1", "sequence": "Blend order/timing"}
    },
    "Clock_CHOP": {
        "summary": "Generates time-based channels from system or custom clocks.",
        "parameters": {"timeslice": "Time per sample", "clocksource": "Clock source", "rate": "Playback rate", "start": "Start time", "length": "Duration"}
    },
    "Constant_CHOP": {
        "summary": "Outputs constant channel values for static data.",
        "parameters": {"name0": "Channel name", "value0": "Channel value"}
    },
    "Copy_CHOP": {
        "summary": "Copies and transforms channel data multiple times.",
        "parameters": {"copies": "Number of copies", "cumulative": "Cumulative transforms", "translate": "Value offset"}
    },
    "Count_CHOP": {
        "summary": "Counts trigger events or time increments.",
        "parameters": {"threshold": "Trigger threshold", "limittype": "Limit behavior", "limitmin": "Min count", "limitmax": "Max count", "overflow": "Overflow behavior"}
    },
    "Cross_CHOP": {
        "summary": "Crossfades between CHOP inputs over time.",
        "parameters": {"crosstime": "Crossfade duration", "ease": "Easing function"}
    },
    "Cycle_CHOP": {
        "summary": "Cycles/loops channel data within time range.",
        "parameters": {"start": "Loop start", "end": "Loop end", "cycles": "Number of cycles", "mirror": "Bidirectional looping"}
    },
    "Delay_CHOP": {
        "summary": "Delays channel data by time or samples.",
        "parameters": {"delay": "Delay amount", "delayunit": "Unit (seconds/samples)"}
    },

    # Control CHOPs
    "Envelope_CHOP": {
        "summary": "Creates ADSR envelope shapes from triggers for amplitude control.",
        "parameters": {"attack": "Attack time", "decay": "Decay time", "sustain": "Sustain level", "release": "Release time", "peak": "Peak level"}
    },
    "Expression_CHOP": {
        "summary": "Evaluates Python expressions to generate channel values.",
        "parameters": {"expr0": "Expression for channel 0", "numchans": "Number of channels", "channame": "Channel names"}
    },
    "Fan_CHOP": {
        "summary": "Fans channel values into output range distribution.",
        "parameters": {"fanop": "Fan operation", "onoff": "On/off mode", "negoff": "Negative offset"}
    },
    "Feedback_CHOP": {
        "summary": "Creates feedback loop with previous frame's data.",
        "parameters": {"delay": "Feedback delay"}
    },
    "Filter_CHOP": {
        "summary": "Smooths channel data with various filter types.",
        "parameters": {"filtertype": "Filter type", "filterwidth": "Filter width", "timeslice": "Time slice mode"}
    },
    "Function_CHOP": {
        "summary": "Applies mathematical functions to channel values.",
        "parameters": {"func": "Math function", "align": "Channel alignment", "resample": "Resample method"}
    },
    "Hold_CHOP": {
        "summary": "Holds channel value when triggered.",
        "parameters": {"hold": "Hold trigger", "reset": "Reset trigger", "outputval": "Output value"}
    },

    # Input CHOPs
    "Info_CHOP": {
        "summary": "Outputs operator information as channels.",
        "parameters": {"op": "Target operator", "infochop": "Info type"}
    },
    "Interpolate_CHOP": {
        "summary": "Interpolates between channel keyframes.",
        "parameters": {"interp": "Interpolation type", "tension": "Curve tension", "bias": "Curve bias"}
    },
    "Keyboard_In_CHOP": {
        "summary": "Captures keyboard input as channel data.",
        "parameters": {"keys": "Keys to capture", "toggle": "Toggle mode", "momentary": "Momentary mode"}
    },
    "Lag_CHOP": {
        "summary": "Applies lag/smoothing to channel changes.",
        "parameters": {"lag": "Lag amount", "overshoot": "Overshoot factor", "method": "Lag method"}
    },
    "LFO_CHOP": {
        "summary": "Low frequency oscillator generating periodic waveforms.",
        "parameters": {"wavetype": "Waveform shape", "freq": "Frequency", "amp": "Amplitude", "offset": "DC offset", "phase": "Phase offset"}
    },
    "Limit_CHOP": {
        "summary": "Limits channel values to specified range.",
        "parameters": {"type": "Limit type", "min": "Minimum value", "max": "Maximum value", "clampmethod": "Clamp method"}
    },
    "Logic_CHOP": {
        "summary": "Performs logical operations on channels.",
        "parameters": {"preop": "Pre-operation", "convert": "Conversion", "channelop": "Channel operation", "combine": "Combine method"}
    },
    "Lookup_CHOP": {
        "summary": "Remaps values through lookup table.",
        "parameters": {"table": "Lookup table", "lookup": "Lookup method", "index": "Index channel"}
    },

    # Communication CHOPs
    "MIDI_In_CHOP": {
        "summary": "Receives MIDI messages from devices/software.",
        "parameters": {"device": "MIDI device", "channel": "MIDI channel", "noteon": "Note on messages", "noteoff": "Note off messages", "control": "Control changes"}
    },
    "MIDI_Out_CHOP": {
        "summary": "Sends MIDI messages to devices/software.",
        "parameters": {"device": "MIDI device", "channel": "MIDI channel", "type": "Message type"}
    },
    "Mouse_In_CHOP": {
        "summary": "Captures mouse position and button states.",
        "parameters": {"absrel": "Absolute/relative mode", "monitorindex": "Monitor index", "buttons": "Include buttons"}
    },
    "Noise_CHOP": {
        "summary": "Generates irregular non-repeating waves for animation and procedural motion.",
        "parameters": {"type": "Noise algorithm", "amp": "Amplitude", "period": "Time period", "seed": "Random seed", "roughness": "Detail level"}
    },
    "OSC_In_CHOP": {
        "summary": "Receives Open Sound Control messages.",
        "parameters": {"port": "Listen port", "address": "OSC address pattern", "type": "Data type"}
    },
    "OSC_Out_CHOP": {
        "summary": "Sends Open Sound Control messages.",
        "parameters": {"network": "Network address", "port": "Destination port", "address": "OSC address"}
    },

    # Processing CHOPs
    "Math_CHOP": {
        "summary": "Performs math operations on channel values.",
        "parameters": {"preoff": "Pre-offset", "gain": "Multiply factor", "postoff": "Post-offset", "chanop": "Channel operation", "combine": "Combine method"}
    },
    "Merge_CHOP": {
        "summary": "Merges multiple CHOP inputs.",
        "parameters": {"duplicate": "Handle duplicates", "match": "Match method"}
    },
    "Parameter_CHOP": {
        "summary": "Exports parameter values as channels.",
        "parameters": {"ops": "Target operators", "parameters": "Parameter names", "scope": "Parameter scope"}
    },
    "Pattern_CHOP": {
        "summary": "Generates mathematical waveform patterns.",
        "parameters": {"type": "Pattern type", "size": "Pattern size", "taper": "Taper factor", "fromval": "Start value", "toval": "End value"}
    },
    "Rename_CHOP": {
        "summary": "Renames channels using patterns.",
        "parameters": {"renamefrom": "Match pattern", "renameto": "Replace pattern", "match": "Match method"}
    },
    "Resample_CHOP": {
        "summary": "Resamples channel data to new rate.",
        "parameters": {"method": "Resample method", "rate": "New sample rate", "start": "Start time", "end": "End time"}
    },
    "Script_CHOP": {
        "summary": "Custom Python for generating channels dynamically.",
        "parameters": {"callbacks": "Callback DAT", "language": "Script language"}
    },
    "Timer_CHOP": {
        "summary": "Versatile timer with segments, cues, and callbacks.",
        "parameters": {"length": "Timer duration", "play": "Playback state", "cue": "Cue points"}
    },

    # Core TOPs
    "Add_TOP": {
        "summary": "Adds/composites multiple TOP inputs using arithmetic operations.",
        "parameters": {"operand": "Math operation", "prefit": "Auto-scale inputs", "postformat": "Output format"}
    },
    "Anti_Alias_TOP": {
        "summary": "Applies anti-aliasing to reduce jagged edges.",
        "parameters": {"samples": "Samples per pixel", "method": "AA algorithm"}
    },
    "Blob_Track_TOP": {
        "summary": "Tracks blobs/objects in video for motion analysis and interactive installations.",
        "parameters": {"threshold": "Detection threshold", "minarea": "Minimum blob area", "maxarea": "Maximum blob area", "maxblobs": "Max tracked blobs"}
    },
    "Blur_TOP": {
        "summary": "Applies Gaussian or box blur for softening, glow, or noise reduction.",
        "parameters": {"filtertype": "Blur algorithm", "filterwidth": "Blur radius", "extend": "Edge handling"}
    },
    "Cache_TOP": {
        "summary": "Caches frames for playback, time manipulation, or feedback effects.",
        "parameters": {"length": "Frames to cache", "start": "Start frame", "end": "End frame"}
    },
    "Channel_Mix_TOP": {
        "summary": "Remixes RGBA channels between inputs for color grading.",
        "parameters": {"red": "Red source", "green": "Green source", "blue": "Blue source", "alpha": "Alpha source"}
    },
    "Chroma_Key_TOP": {
        "summary": "Removes background color for green/blue screen compositing.",
        "parameters": {"keycolor": "Color to remove", "softness": "Edge softness", "spill": "Spill suppression"}
    },
    "Circle_TOP": {
        "summary": "Generates circular or elliptical shapes.",
        "parameters": {"radius": "Circle radius", "center": "Center position", "fill": "Fill color", "border": "Border style"}
    },
    "Composite_TOP": {
        "summary": "Composites layers with selectable blend modes.",
        "parameters": {"operand": "Blend mode", "prefit": "Auto-fit inputs"}
    },
    "Constant_TOP": {
        "summary": "Generates solid color or gradient output.",
        "parameters": {"color": "Output color", "alpha": "Alpha value", "resolution": "Image size"}
    },
    "Crop_TOP": {
        "summary": "Crops image to specified region.",
        "parameters": {"cropleft": "Left crop", "cropright": "Right crop", "croptop": "Top crop", "cropbottom": "Bottom crop"}
    },
    "Cross_TOP": {
        "summary": "Crossfades between two TOP inputs.",
        "parameters": {"cross": "Crossfade amount", "ease": "Easing function"}
    },
    "Depth_TOP": {
        "summary": "Extracts or processes depth buffer data from 3D renders.",
        "parameters": {"depth": "Depth range", "near": "Near plane", "far": "Far plane"}
    },
    "Displace_TOP": {
        "summary": "Displaces pixels based on displacement map.",
        "parameters": {"displaceweight": "Displacement strength", "offset": "Offset value"}
    },
    "Edge_TOP": {
        "summary": "Detects edges using Sobel, Laplacian, or other algorithms.",
        "parameters": {"method": "Edge algorithm", "threshold": "Detection threshold"}
    },

    # Processing TOPs
    "Feedback_TOP": {
        "summary": "Creates video feedback loops with previous frame.",
        "parameters": {"target": "Feedback target", "opacity": "Blend opacity"}
    },
    "Fit_TOP": {
        "summary": "Fits/resizes image to target resolution.",
        "parameters": {"fit": "Fit mode", "justify": "Alignment", "extend": "Edge mode"}
    },
    "Flip_TOP": {
        "summary": "Flips image horizontally or vertically.",
        "parameters": {"flipx": "Horizontal flip", "flipy": "Vertical flip"}
    },
    "GLSL_TOP": {
        "summary": "Custom GPU shaders using GLSL code for advanced effects.",
        "parameters": {"pixeldat": "Pixel shader DAT", "outputresolution": "Output size", "format": "Pixel format"}
    },
    "Gradient_TOP": {
        "summary": "Generates color gradient images.",
        "parameters": {"type": "Gradient type", "phase": "Phase offset", "period": "Repeat period"}
    },
    "HSV_Adjust_TOP": {
        "summary": "Adjusts hue, saturation, value of images.",
        "parameters": {"hueoffset": "Hue shift", "satmult": "Saturation multiplier", "valmult": "Value multiplier"}
    },
    "Layout_TOP": {
        "summary": "Arranges multiple TOPs in grid layout.",
        "parameters": {"layout": "Layout type", "rows": "Grid rows", "cols": "Grid columns"}
    },
    "Level_TOP": {
        "summary": "Adjusts brightness, contrast, gamma for color correction.",
        "parameters": {"brightness": "Brightness", "contrast": "Contrast", "gamma": "Gamma", "invert": "Invert colors"}
    },
    "Lookup_TOP": {
        "summary": "Remaps colors through lookup table.",
        "parameters": {"indexfield": "Index source", "table": "Lookup table"}
    },
    "Math_TOP": {
        "summary": "Performs math operations on pixel values.",
        "parameters": {"integer": "Integer mode", "preoff": "Pre-offset", "gain": "Multiply", "postoff": "Post-offset"}
    },
    "Mirror_TOP": {
        "summary": "Mirrors image along axis.",
        "parameters": {"flipx": "Mirror X", "flipy": "Mirror Y", "offset": "Mirror offset"}
    },
    "Monochrome_TOP": {
        "summary": "Converts to grayscale with channel weights.",
        "parameters": {"red": "Red weight", "green": "Green weight", "blue": "Blue weight"}
    },
    "Movie_File_In_TOP": {
        "summary": "Plays video files from disk.",
        "parameters": {"file": "Video file path", "play": "Playback state", "speed": "Playback speed", "index": "Frame index", "loop": "Loop mode"}
    },
    "Noise_TOP": {
        "summary": "Generates procedural noise textures.",
        "parameters": {"type": "Noise type", "amp": "Amplitude", "period": "Noise period", "offset": "Position offset", "seed": "Random seed"}
    },
    "Null_TOP": {
        "summary": "Pass-through for network organization and referencing.",
        "parameters": {}
    },
    "Over_TOP": {
        "summary": "Composites foreground over background with alpha.",
        "parameters": {"prefit": "Auto-fit", "premult": "Premultiplied alpha"}
    },
    "Ramp_TOP": {
        "summary": "Creates color ramp/gradient images.",
        "parameters": {"type": "Ramp type", "phase": "Phase", "dat": "Color lookup DAT"}
    },
    "Rectangle_TOP": {
        "summary": "Generates rectangular shapes.",
        "parameters": {"sizex": "Width", "sizey": "Height", "centerx": "Center X", "centery": "Center Y"}
    },
    "Render_TOP": {
        "summary": "Renders 3D scene to texture.",
        "parameters": {"geometry": "Geometry COMP", "camera": "Camera COMP", "lights": "Light COMPs"}
    },
    "Resolution_TOP": {
        "summary": "Changes image resolution.",
        "parameters": {"resolution": "Resolution preset", "resolutionw": "Width", "resolutionh": "Height"}
    },
    "Select_TOP": {
        "summary": "References another TOP's output.",
        "parameters": {"top": "Source TOP"}
    },
    "Switch_TOP": {
        "summary": "Switches between multiple inputs.",
        "parameters": {"index": "Input index", "blend": "Blend between"}
    },
    "Text_TOP": {
        "summary": "Renders text with fonts and formatting.",
        "parameters": {"text": "Text content", "font": "Font family", "fontsize": "Font size", "alignx": "Horizontal align"}
    },
    "Transform_TOP": {
        "summary": "Transforms image position, rotation, scale.",
        "parameters": {"tx": "Translate X", "ty": "Translate Y", "rotate": "Rotation", "scalex": "Scale X", "scaley": "Scale Y"}
    },

    # Core SOPs
    "Add_SOP": {
        "summary": "Adds points, polygons, or primitives to geometry.",
        "parameters": {"points": "Points to add", "polygons": "Polygons to add", "prims": "Primitives to add"}
    },
    "Attribute_Create_SOP": {
        "summary": "Creates custom attributes on geometry.",
        "parameters": {"name": "Attribute name", "class": "Point/prim/vertex", "type": "Data type", "value": "Default value"}
    },
    "Boolean_SOP": {
        "summary": "Performs boolean operations (union, intersect, subtract) between geometries.",
        "parameters": {"operation": "Boolean operation", "asurf": "Surface A", "bsurf": "Surface B"}
    },
    "Box_SOP": {
        "summary": "Creates box/cube primitive geometry.",
        "parameters": {"sizex": "Width", "sizey": "Height", "sizez": "Depth", "divsx": "X divisions", "divsy": "Y divisions", "divsz": "Z divisions"}
    },
    "Circle_SOP": {
        "summary": "Creates circle or arc primitives.",
        "parameters": {"radius": "Radius", "arc": "Arc angle", "divisions": "Segments", "type": "Primitive type"}
    },
    "Convert_SOP": {
        "summary": "Converts between geometry types (mesh, NURBS, Bezier).",
        "parameters": {"totype": "Target type", "lodu": "U detail", "lodv": "V detail"}
    },
    "Copy_SOP": {
        "summary": "Copies geometry onto template points for instancing.",
        "parameters": {"ncy": "Number of copies", "templategroup": "Template points", "cumulative": "Cumulative transforms"}
    },
    "Delete_SOP": {
        "summary": "Deletes points, primitives, or edges by selection.",
        "parameters": {"entity": "Entity type", "filter": "Selection filter", "operation": "Delete/keep"}
    },
    "Divide_SOP": {
        "summary": "Subdivides geometry into smaller pieces.",
        "parameters": {"divsu": "U divisions", "divsv": "V divisions", "avoidsmall": "Avoid small faces"}
    },
    "Extrude_SOP": {
        "summary": "Extrudes faces along normal or direction.",
        "parameters": {"dist": "Extrude distance", "inset": "Face inset", "divisions": "Divisions"}
    },
    "Facet_SOP": {
        "summary": "Controls faceting and normal computation.",
        "parameters": {"unique": "Unique points", "consolidate": "Merge points", "cusp": "Cusp angle"}
    },
    "Fit_SOP": {
        "summary": "Fits geometry to bounding box dimensions.",
        "parameters": {"sizex": "Target width", "sizey": "Target height", "sizez": "Target depth", "center": "Center position"}
    },
    "Fuse_SOP": {
        "summary": "Fuses nearby points together.",
        "parameters": {"dist": "Fuse distance", "snap": "Snap method", "consolidate": "Consolidate"}
    },
    "Grid_SOP": {
        "summary": "Creates flat grid mesh geometry.",
        "parameters": {"sizex": "Width", "sizey": "Height", "rows": "Row count", "cols": "Column count"}
    },
    "Group_SOP": {
        "summary": "Creates and manages point/primitive groups.",
        "parameters": {"groupname": "Group name", "grouptype": "Group type", "pattern": "Selection pattern"}
    },
    "Line_SOP": {
        "summary": "Creates line primitive geometry.",
        "parameters": {"origin": "Start point", "direction": "Line direction", "length": "Line length", "points": "Point count"}
    },
    "Merge_SOP": {
        "summary": "Combines multiple geometry inputs.",
        "parameters": {}
    },
    "Mirror_SOP": {
        "summary": "Mirrors geometry across plane.",
        "parameters": {"origin": "Mirror origin", "direction": "Mirror direction", "consolidate": "Merge seam"}
    },
    "Noise_SOP": {
        "summary": "Deforms geometry with procedural noise.",
        "parameters": {"type": "Noise type", "amp": "Amplitude", "freq": "Frequency", "offset": "Noise offset"}
    },
    "Normals_SOP": {
        "summary": "Recomputes geometry normals.",
        "parameters": {"method": "Normal method", "cusp": "Cusp angle"}
    },
    "Null_SOP": {
        "summary": "Pass-through for network organization.",
        "parameters": {}
    },
    "Object_Merge_SOP": {
        "summary": "Imports geometry from other operators.",
        "parameters": {"soppath": "Source SOP path", "xformtype": "Transform mode"}
    },
    "Point_SOP": {
        "summary": "Modifies point attributes with expressions.",
        "parameters": {"tx": "Position X", "ty": "Position Y", "tz": "Position Z", "docolor": "Modify color"}
    },
    "Scatter_SOP": {
        "summary": "Scatters points randomly on surface.",
        "parameters": {"npts": "Number of points", "seed": "Random seed", "relax": "Relaxation iterations"}
    },
    "Select_SOP": {
        "summary": "References another SOP's output.",
        "parameters": {"sop": "Source SOP"}
    },
    "Sphere_SOP": {
        "summary": "Creates sphere primitive geometry.",
        "parameters": {"type": "Sphere type", "radius": "Radius", "freq": "Frequency", "rows": "Rows", "cols": "Columns"}
    },
    "Sort_SOP": {
        "summary": "Sorts points/primitives by various criteria.",
        "parameters": {"ptsort": "Point sort method", "pointseed": "Random seed"}
    },
    "Subdivide_SOP": {
        "summary": "Subdivides geometry for smoothing.",
        "parameters": {"iterations": "Subdivision iterations", "depth": "Subdivision depth"}
    },
    "Switch_SOP": {
        "summary": "Switches between geometry inputs.",
        "parameters": {"index": "Input index", "blend": "Blend factor"}
    },
    "Transform_SOP": {
        "summary": "Transforms geometry position/rotation/scale.",
        "parameters": {"tx": "Translate X", "ty": "Translate Y", "tz": "Translate Z", "rx": "Rotate X", "ry": "Rotate Y", "rz": "Rotate Z", "sx": "Scale X", "sy": "Scale Y", "sz": "Scale Z"}
    },
    "Tube_SOP": {
        "summary": "Creates tube/cylinder geometry.",
        "parameters": {"radscale1": "Top radius", "radscale2": "Bottom radius", "height": "Height", "rows": "Rows", "cols": "Columns"}
    },

    # Core DATs
    "Analyze_DAT": {
        "summary": "Analyzes table data statistics.",
        "parameters": {"input": "Input data", "columns": "Columns to analyze"}
    },
    "CHOP_Execute_DAT": {
        "summary": "Runs callbacks when CHOP values change.",
        "parameters": {"chops": "Source CHOPs", "onvaluechange": "Value change callback", "onofftoOn": "Off-to-on callback"}
    },
    "CHOP_to_DAT": {
        "summary": "Converts CHOP channels to table.",
        "parameters": {"chop": "Source CHOP", "format": "Output format"}
    },
    "DAT_Execute_DAT": {
        "summary": "Runs callbacks when DAT changes.",
        "parameters": {"dats": "Source DATs", "active": "Active state"}
    },
    "Evaluate_DAT": {
        "summary": "Evaluates Python expressions in table cells.",
        "parameters": {"expression": "Expression to evaluate", "scope": "Variable scope"}
    },
    "Execute_DAT": {
        "summary": "Runs callbacks for system events.",
        "parameters": {"active": "Active state", "onstart": "Start callback", "oncreate": "Create callback"}
    },
    "Fifo_DAT": {
        "summary": "First-in-first-out buffer for table rows.",
        "parameters": {"maxrows": "Maximum rows", "keepfirstrow": "Keep header"}
    },
    "File_In_DAT": {
        "summary": "Reads text/data files from disk.",
        "parameters": {"file": "File path", "refresh": "Refresh mode", "syncfile": "Sync with file"}
    },
    "File_Out_DAT": {
        "summary": "Writes table data to disk files.",
        "parameters": {"file": "Output path", "append": "Append mode"}
    },
    "Folder_DAT": {
        "summary": "Lists folder contents as table.",
        "parameters": {"folder": "Folder path", "extension": "File extension filter", "recursive": "Include subfolders"}
    },
    "JSON_DAT": {
        "summary": "Parses and generates JSON data.",
        "parameters": {"input": "JSON input", "output": "Output format", "format": "JSON formatting"}
    },
    "Merge_DAT": {
        "summary": "Merges multiple DAT tables together.",
        "parameters": {"how": "Merge method", "match": "Match columns"}
    },
    "MQTT_Client_DAT": {
        "summary": "MQTT messaging protocol client.",
        "parameters": {"broker": "Broker address", "port": "Port number", "topic": "Topic", "subscribe": "Subscribe topics"}
    },
    "Null_DAT": {
        "summary": "Pass-through for network organization.",
        "parameters": {}
    },
    "OSC_In_DAT": {
        "summary": "Receives OSC messages as table rows.",
        "parameters": {"port": "Listen port", "address": "Address filter", "format": "Output format"}
    },
    "OSC_Out_DAT": {
        "summary": "Sends table data as OSC messages.",
        "parameters": {"network": "Network address", "port": "Port", "address": "OSC address"}
    },
    "Panel_Execute_DAT": {
        "summary": "Runs callbacks for panel events.",
        "parameters": {"panel": "Source panel", "active": "Active state"}
    },
    "Parameter_DAT": {
        "summary": "Lists operator parameters as table.",
        "parameters": {"ops": "Source operators", "includeflags": "Include flags"}
    },
    "Script_DAT": {
        "summary": "Custom Python for table generation.",
        "parameters": {"callbacks": "Callback methods"}
    },
    "Select_DAT": {
        "summary": "Selects rows/columns from input.",
        "parameters": {"rowindexstart": "Start row", "rowindexend": "End row", "cols": "Column selection"}
    },
    "Serial_DAT": {
        "summary": "Serial port communication.",
        "parameters": {"port": "Serial port", "baud": "Baud rate", "databits": "Data bits"}
    },
    "SOP_to_DAT": {
        "summary": "Converts SOP geometry to table.",
        "parameters": {"sop": "Source SOP", "attribs": "Attributes to export"}
    },
    "Table_DAT": {
        "summary": "Manual table data entry and storage.",
        "parameters": {"rows": "Number of rows", "cols": "Number of columns"}
    },
    "TCP_IP_DAT": {
        "summary": "TCP network communication.",
        "parameters": {"protocol": "TCP mode", "address": "Server address", "port": "Port"}
    },
    "Text_DAT": {
        "summary": "Stores and edits text content.",
        "parameters": {"text": "Text content", "file": "External file"}
    },
    "UDP_In_DAT": {
        "summary": "Receives UDP network data.",
        "parameters": {"port": "Listen port", "address": "Address filter"}
    },
    "UDP_Out_DAT": {
        "summary": "Sends UDP network data.",
        "parameters": {"address": "Destination address", "port": "Destination port"}
    },
    "Web_DAT": {
        "summary": "Fetches web content via HTTP.",
        "parameters": {"url": "URL to fetch", "method": "HTTP method", "contenttype": "Content type"}
    },
    "Web_Server_DAT": {
        "summary": "Creates HTTP server endpoint.",
        "parameters": {"port": "Server port", "onhttprequest": "Request callback"}
    },
    "XML_DAT": {
        "summary": "Parses and generates XML data.",
        "parameters": {"input": "XML input", "format": "Output format"}
    },

    # Core COMPs
    "Base_COMP": {
        "summary": "Container for custom networks and extensions.",
        "parameters": {"externaltox": "External TOX file", "extension": "Extension class"}
    },
    "Button_COMP": {
        "summary": "Interactive UI button widget.",
        "parameters": {"buttontype": "Button behavior", "value0": "Current value", "label": "Button label"}
    },
    "Camera_COMP": {
        "summary": "3D camera for scene viewing and rendering.",
        "parameters": {"tx": "Position X", "ty": "Position Y", "tz": "Position Z", "rx": "Rotation X", "ry": "Rotation Y", "rz": "Rotation Z", "fov": "Field of view"}
    },
    "Container_COMP": {
        "summary": "Panel container for UI layout.",
        "parameters": {"alignorder": "Alignment order", "hmode": "Horizontal mode", "vmode": "Vertical mode"}
    },
    "Field_COMP": {
        "summary": "Text input field widget.",
        "parameters": {"field": "Current text", "default": "Default value"}
    },
    "Geo_COMP": {
        "summary": "3D geometry container for rendering.",
        "parameters": {"render": "Render flag", "material": "Material", "instanceop": "Instance operator"}
    },
    "Light_COMP": {
        "summary": "Scene lighting source.",
        "parameters": {"lighttype": "Light type", "dimmer": "Intensity", "color": "Light color"}
    },
    "List_COMP": {
        "summary": "Scrollable list display widget.",
        "parameters": {"rows": "Number of rows", "cols": "Number of columns", "callbacks": "Callback DAT"}
    },
    "Null_COMP": {
        "summary": "Pass-through for network organization.",
        "parameters": {}
    },
    "Replicator_COMP": {
        "summary": "Creates copies of template COMP.",
        "parameters": {"template": "Template COMP", "numreplicants": "Number of copies", "callbacks": "Callback DAT"}
    },
    "Slider_COMP": {
        "summary": "Interactive slider control widget.",
        "parameters": {"slidertype": "Slider style", "value0": "Current value", "rangel": "Range low", "ranger": "Range high"}
    },
    "Text_COMP": {
        "summary": "UI text display widget.",
        "parameters": {"text": "Display text", "fontsizex": "Font size", "alignx": "Horizontal align"}
    },
    "Time_COMP": {
        "summary": "Custom timeline for sequencing.",
        "parameters": {"length": "Timeline length", "rate": "Frame rate", "play": "Play state"}
    },
    "Window_COMP": {
        "summary": "Creates separate display window.",
        "parameters": {"winopen": "Window open", "winoffsetx": "Window X position", "winoffsety": "Window Y position"}
    },

    # Materials
    "Constant_MAT": {
        "summary": "Flat color material with no shading.",
        "parameters": {"color": "Surface color", "alpha": "Transparency"}
    },
    "GLSL_MAT": {
        "summary": "Custom GLSL shader material.",
        "parameters": {"vertexdat": "Vertex shader DAT", "pixeldat": "Pixel shader DAT", "uniforms": "Shader uniforms"}
    },
    "PBR_MAT": {
        "summary": "Physically based rendering material.",
        "parameters": {"basecolor": "Base color", "metallic": "Metallic factor", "roughness": "Surface roughness"}
    },
    "Phong_MAT": {
        "summary": "Classic Phong shading material.",
        "parameters": {"diff": "Diffuse color", "spec": "Specular color", "emit": "Emission", "shininess": "Specular power"}
    },
    "Point_Sprite_MAT": {
        "summary": "Material for point rendering as sprites.",
        "parameters": {"texture": "Sprite texture", "scale": "Point scale"}
    },
    "Wireframe_MAT": {
        "summary": "Renders geometry as wireframe.",
        "parameters": {"linewidth": "Line width", "color": "Wire color"}
    },

    # POPs
    "Add_POP": {
        "summary": "Adds particles to the system.",
        "parameters": {"birthrate": "Particles per second", "life": "Particle lifespan", "position": "Birth position"}
    },
    "Attractor_POP": {
        "summary": "Attracts particles toward points/geometry.",
        "parameters": {"force": "Attraction strength", "type": "Attractor type", "falloff": "Distance falloff"}
    },
    "Collision_POP": {
        "summary": "Handles particle collision with geometry.",
        "parameters": {"soppath": "Collision geometry", "behavior": "Collision response", "friction": "Surface friction"}
    },
    "Drag_POP": {
        "summary": "Applies drag force to slow particles.",
        "parameters": {"airresist": "Air resistance", "windx": "Wind X", "windy": "Wind Y", "windz": "Wind Z"}
    },
    "Force_POP": {
        "summary": "Applies forces to particle motion.",
        "parameters": {"forcex": "Force X", "forcey": "Force Y", "forcez": "Force Z", "type": "Force type"}
    },
    "Kill_POP": {
        "summary": "Removes particles meeting conditions.",
        "parameters": {"rule": "Kill condition", "mintarget": "Min threshold", "maxtarget": "Max threshold"}
    },
    "Limit_POP": {
        "summary": "Constrains particles within bounds.",
        "parameters": {"xmin": "Min X", "xmax": "Max X", "ymin": "Min Y", "ymax": "Max Y", "behavior": "Boundary behavior"}
    },
    "Source_POP": {
        "summary": "Defines particle emission source.",
        "parameters": {"geometry": "Source geometry", "velocity": "Initial velocity", "scatter": "Scatter amount"}
    },
    "Velocity_POP": {
        "summary": "Sets/modifies particle velocity.",
        "parameters": {"vx": "Velocity X", "vy": "Velocity Y", "vz": "Velocity Z"}
    },
}


def load_existing_partial():
    """Load existing partial file if it exists."""
    partial_path = OUTPUT_DIR / "operator_wiki_semantics_partial.yaml"
    if partial_path.exists():
        with open(partial_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Skip comment lines at start
            lines = content.split('\n')
            yaml_start = 0
            for i, line in enumerate(lines):
                if line.strip() and not line.strip().startswith('#'):
                    yaml_start = i
                    break
            yaml_content = '\n'.join(lines[yaml_start:])
            try:
                return yaml.safe_load(yaml_content) or {}
            except:
                return {}
    return {}


def load_wiki_facts():
    """Load factual parameter data from extracted wiki JSON files."""
    facts = {}
    for json_file in FACTS_DIR.glob("*_operators_wiki.json"):
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for op in data.get('operators', []):
                name = op['name'].replace(' ', '_')

                # Include ALL parameters, organized by section (skip Common Page)
                params_by_section = {}
                for p in op.get('parameters', []):
                    if not p.get('code'):
                        continue
                    section = p.get('section', 'Parameters')
                    # Skip Common Page params (shared across all ops)
                    if 'Common Page' in section:
                        continue

                    # Clean up description - remove wiki formatting artifacts
                    desc = p.get('description', '')
                    desc = desc.replace('⊞ - ', '').strip()
                    if len(desc) > 150:
                        desc = desc[:147] + '...'

                    params_by_section[p['code']] = {
                        'description': desc,
                        'section': section.replace('Parameters - ', '').replace(' Page', '')
                    }

                # Get full summary
                summary = op.get('summary', '')
                if len(summary) > 300:
                    summary = summary[:297] + '...'

                facts[name] = {
                    'family': op.get('family', ''),
                    'python_class': op.get('python_class', ''),
                    'summary': summary,
                    'parameters': params_by_section
                }
    return facts


def main():
    print("Loading existing data...")
    existing = load_existing_partial()
    wiki_facts = load_wiki_facts()

    print(f"Existing partial: {len(existing)} operators")
    print(f"Wiki facts: {len(wiki_facts)} operators")
    print(f"Session operators: {len(SESSION_OPERATORS)} operators")

    # Merge all sources - wiki facts as base, session summaries overlay
    all_operators = {}

    # Start with wiki facts as base (has full parameter lists)
    for name, data in wiki_facts.items():
        all_operators[name] = data

    # Overlay session summaries (better semantic descriptions)
    for name, data in SESSION_OPERATORS.items():
        if name in all_operators:
            # Keep wiki parameters, use session summary
            all_operators[name]['summary'] = data.get('summary', all_operators[name].get('summary', ''))
        else:
            all_operators[name] = {
                'family': '',
                'python_class': '',
                'summary': data.get('summary', ''),
                'parameters': data.get('parameters', {})
            }

    # Organize by family
    by_family = {'CHOP': {}, 'TOP': {}, 'SOP': {}, 'DAT': {}, 'COMP': {}, 'MAT': {}, 'POP': {}}

    for name, data in all_operators.items():
        # Determine family from name suffix
        family = None
        for fam in ['CHOP', 'TOP', 'SOP', 'DAT', 'COMP', 'MAT', 'POP']:
            if name.endswith(f'_{fam}'):
                family = fam
                break

        if not family:
            family = data.get('family', 'UNKNOWN')

        if family in by_family:
            # Build clean parameter dict
            params = data.get('parameters', {})
            clean_params = {}
            for pcode, pdata in params.items():
                if isinstance(pdata, dict):
                    clean_params[pcode] = {
                        'description': pdata.get('description', ''),
                        'section': pdata.get('section', '')
                    }
                else:
                    # Simple string description
                    clean_params[pcode] = {'description': str(pdata), 'section': ''}

            by_family[family][name] = {
                'summary': data.get('summary', ''),
                'python_class': data.get('python_class', ''),
                'parameters': clean_params
            }

    # Save combined file
    output_path = OUTPUT_DIR / "all_operator_wiki_semantics.yaml"
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(by_family, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)

    # Count totals and params
    total = sum(len(ops) for ops in by_family.values())
    total_params = sum(
        len(op.get('parameters', {}))
        for ops in by_family.values()
        for op in ops.values()
    )
    print(f"\n=== Consolidation Complete ===")
    print(f"Total operators: {total}")
    print(f"Total parameters: {total_params}")
    for family, ops in by_family.items():
        param_count = sum(len(op.get('parameters', {})) for op in ops.values())
        print(f"  {family}: {len(ops)} ops, {param_count} params")
    print(f"\nOutput: {output_path}")


if __name__ == '__main__':
    main()

"""
§6.6 Recipes / Patterns / Guides — the goal-shaped how-to layer (howto 0 -> up).

Two sources:
  * AUTHORED recipe_chunks — a curated set of canonical TD techniques, each an
    ordered operator chain + load-bearing params with type-traps + a hydrate
    pointer. These are publicly-known build patterns (no licensing concern) and
    are grounded in real operator names from the Identity registry. They are the
    primary answer to intent queries ("make trails", "raymarch an SDF").
  * REAL pattern_chunks — the validated workflows in td_network_patterns.yaml
    (typical_chain + key_parameters + confidence/validated), normalized to a
    searchable pattern chunk.

Chunk type ∈ {recipe, pattern} — both in the harness's howto-relevant set.
These chunks assert NO operator identity field, so they stay clean through the
name-integrity gate.
"""
from __future__ import annotations

import yaml

import common as C

# --- AUTHORED canonical recipes (one per major intent; tokens chosen to match
#     real goal-shaped queries). Grounded in canonical operator names. ---
RECIPES = [
    {
        "id": "raymarch_sdf",
        "title": "Raymarch a signed-distance field (SDF) in a GLSL TOP",
        "text": "RECIPE — Raymarch an SDF in a GLSL TOP. Write a fragment shader that ray marches a "
                "signed distance field: per pixel (vUV) march a ray, evaluate the SDF (sphere/box "
                "distance functions), step until a hit, then shade by the surface normal (the gradient "
                "of the SDF). Chain: GLSL TOP (the raymarcher) -> Null TOP. Type-trap: a GLSL TOP does "
                "NOT auto-declare Vectors-page uniforms — declare scalar uniforms explicitly (uniform "
                "float uTime;). Use a Constant CHOP / parameter to feed camera + time uniforms. "
                "Keywords: raymarch, ray march, signed distance, sdf, distance field, ray marching.",
        "ops": ["GLSL TOP", "Null TOP"],
        "hydrate": "Write_a_GLSL_TOP",
    },
    {
        "id": "feedback_trails",
        "title": "Feedback trails that fade over time",
        "text": "RECIPE — Make feedback trails that fade over time. Loop: source TOP -> Composite TOP "
                "-> Feedback TOP -> Level TOP (opacity < 1 to fade) -> back into Composite input 2. "
                "The Feedback TOP needs a real WIRE input, not just its .top parameter. Level opacity "
                "0.90-0.97 sets trail decay; Composite operand='over' (a STRING; 'add' blows out); set "
                "format=rgba16float on every TOP in the loop. Keywords: feedback trail, trails, fade "
                "loop, motion trails, decay.",
        "ops": ["Feedback TOP", "Composite TOP", "Level TOP"],
        "hydrate": "find_operator_examples('feedbackTOP_Class')",
    },
    {
        "id": "gpu_particles_pops",
        "title": "GPU particle system / swarm with POPs",
        "text": "RECIPE — Build a GPU particle system (swarm) with POPs. Use a ping-pong Feedback POP "
                "(or GLSL POP) that updates per-particle position+velocity on the GPU each frame, seeded "
                "from a Point Generator / SOP-to-POP, then render the points with a Geometry COMP "
                "(instancing) or a POP-to-TOP. Pulse init/start/play to drive the sim. Keywords: gpu "
                "particle, particle system, particle swarm, swarm, boids, flocking, gpu particles.",
        "ops": ["Feedback POP", "GLSL POP", "Geometry COMP"],
        "hydrate": "find_operator_examples('feedbackPOP_Class')",
    },
    {
        "id": "audio_reactive",
        "title": "Audio-reactive visuals driven by music",
        "text": "RECIPE — Create audio-reactive visuals driven by music. Chain: Audio Device In CHOP "
                "(live) or Audio File In CHOP (file) -> Analyze CHOP (RMS Power) and/or Audio Spectrum "
                "CHOP (frequency bands) -> Math/Lag CHOP to smooth -> reference the channel in target "
                "parameter expressions. Beat detection via Beat CHOP. Keywords: audio-reactive, audio "
                "reactive, music reactive, beat, spectrum, rms, sound responsive visuals.",
        "ops": ["Audio Device In CHOP", "Analyze CHOP", "Audio Spectrum CHOP", "Math CHOP"],
        "hydrate": "get_network_patterns('audio_reactive_visuals')",
    },
    {
        "id": "instance_geo_from_chop",
        "title": "Instance geometry from CHOP channel data",
        "text": "RECIPE — Instance geometry from CHOP channel data. Build a CHOP whose samples are the "
                "per-instance transforms (Constant/Pattern/Noise CHOP -> Merge/Join -> Null CHOP), then "
                "on the Geometry COMP set instancing=on, instanceop=<null CHOP>, and map "
                "instancetx/instancety/instancetz (and rotate/scale) to the channel names. Keywords: "
                "instance, instancing, instance geometry, per-instance, scatter, clone.",
        "ops": ["Geometry COMP", "Constant CHOP", "Null CHOP"],
        "hydrate": "get_network_patterns('instancing_workflow')",
    },
    {
        "id": "projection_mapping",
        "title": "Projection mapping onto a 3D surface",
        "text": "RECIPE — Set up projection mapping onto a 3D surface. Render the content with a Camera "
                "COMP + Render TOP matched to the projector, then warp/align with the kantanMapper "
                "palette component or a Corner Pin (cornerPinTOP/cornerPinSOP). Calibrate the camera to "
                "the real projector frustum. Keywords: projection map, projection mapping, mapping, "
                "projector, warp, calibration, kantan.",
        "ops": ["Camera COMP", "Render TOP"],
        "hydrate": "Palette:kantanMapper",
    },
    {
        "id": "glsl_material_pbr",
        "title": "Write a GLSL Material with PBR lighting",
        "text": "RECIPE — Write a GLSL Material (GLSL MAT) with PBR lighting. Assign a GLSL MAT to a "
                "Geometry COMP and implement physically based rendering in the material shader using "
                "TouchDesigner's TDLighting / TD PBR helper functions (albedo, metallic, roughness, "
                "normal). Feed lights via Light COMPs. Keywords: glsl material, glsl mat, pbr, "
                "physically based rendering, lighting, shading, metallic roughness.",
        "ops": ["GLSL MAT", "Geometry COMP", "Light COMP"],
        "hydrate": "Write_a_GLSL_Material",
    },
    {
        "id": "optimize_network",
        "title": "Optimize a slow network for performance",
        "text": "RECIPE — Optimize a slow network for better performance. Lower TOP resolution and use "
                "16-bit float instead of 32-bit; minimize per-frame cooking (Null/Cache, selective "
                "cooking, Time Slice); prefer GPU instancing over many copies; collapse redundant TOP "
                "chains; watch the Performance Monitor + probe with the cook-time profiler. Keywords: "
                "optimize, optimise, performance, faster, slow network, fps, cook time, speed up.",
        "ops": ["Cache TOP", "Null TOP"],
        "hydrate": "Optimize",
    },
    {
        "id": "displacement_feedback",
        "title": "Displacement feedback effect",
        "text": "RECIPE — Create a displacement feedback effect. Drive a Displace TOP (or a GLSL TOP "
                "sampling an offset map) with a Feedback TOP loop so each frame displaces the previous "
                "one, building flowing distortion. Keep the loop at rgba16float and clamp the "
                "displacement amount. Keywords: displace, displacement, displacement map, warp, "
                "distortion feedback, flow.",
        "ops": ["Displace TOP", "Feedback TOP"],
        "hydrate": "find_operator_examples('displaceTOP_Class')",
    },
    {
        "id": "render_to_movie",
        "title": "Render a 3D scene out to a movie file",
        "text": "RECIPE — Render a 3D scene out to a movie file. Chain: Geometry COMP + Camera COMP + "
                "Light COMP -> Render TOP -> Movie File Out TOP. On the Movie File Out TOP set the file "
                "path + codec and toggle Record to write/export the output to disk. Keywords: render to "
                "movie, export movie, movie file out, record the output, export video, write mp4.",
        "ops": ["Render TOP", "Movie File Out TOP"],
        "hydrate": "find_operator_examples('moviefileoutTOP_Class')",
    },
    {
        "id": "lfo_drive_param",
        "title": "Drive a parameter with an LFO oscillator",
        "text": "RECIPE — Drive a parameter with an LFO oscillator. Add an LFO CHOP (set type + "
                "frequency + amplitude) -> Null CHOP, then bind the target parameter to it with an "
                "expression like op('null1')['chan1'] (or export the channel). Keywords: lfo, "
                "oscillator, sine wave, modulate parameter, animate parameter, periodic.",
        "ops": ["LFO CHOP", "Null CHOP"],
        "hydrate": "find_operator_examples('lfoCHOP_Class')",
    },
    {
        "id": "blend_modes_composite",
        "title": "Composite layers using blend modes",
        "text": "RECIPE — Composite layers using different blend modes. Stack layers with a Composite "
                "TOP (or Over/Add/Multiply TOP); the Composite operand menu selects the blend mode "
                "(over, add, multiply, screen, difference). operand is a STRING menu code. Keywords: "
                "blend mode, blending, compositing, composite layers, over add multiply screen, layer.",
        "ops": ["Composite TOP", "Over TOP"],
        "hydrate": "find_parameter_usage('compositeTOP_Class', 'operand')",
    },
]


def _patterns_from_yaml() -> list[dict]:
    rows = []
    data = yaml.safe_load((C.EXPERT / "td_network_patterns.yaml").read_text(encoding="utf-8")) or {}
    wf = data.get("workflows", data)
    for name, body in wf.items():
        if not isinstance(body, dict) or "typical_chain" not in body:
            continue
        desc = " ".join(str(body.get("description") or "").split())
        chain = []
        for step in body.get("typical_chain", []):
            ops = ", ".join(step.get("operators", []))
            role = step.get("role", "")
            chain.append(f"{step.get('step', '?')}. {role} ({ops})")
        kp = []
        for k in body.get("key_parameters", []) or []:
            kp.append(f"{k.get('operator', '')}.{k.get('param', '')}={k.get('typical_values', '')}")
        conf = body.get("confidence")
        val = body.get("validated")
        text = (f"PATTERN — {name.replace('_', ' ')}: {desc}. Pipeline: " + " -> ".join(chain)
                + (". Key params: " + "; ".join(kp[:6]) if kp else "")
                + f". (validated={val}, confidence={conf}; derived from Derivative workflow templates.)")
        rows.append(C.make_row(
            f"pattern:{C.slug(name)}", text, "pattern", C.STORE_RECIPE,
            {"name": name, "pattern_name": name, "confidence": conf, "validated": bool(val),
             "license_tier": "derived-public"}))
    return rows


def build(idn: C.Identity) -> list[dict]:
    rows: list[dict] = []
    for r in RECIPES:
        rows.append(C.make_row(
            f"recipe:{r['id']}", r["text"], "recipe", C.STORE_RECIPE,
            {"name": r["id"], "title": r["title"], "operators": r.get("ops", []),
             "hydrate": r.get("hydrate", ""), "license_tier": "public"}))
    rows.extend(_patterns_from_yaml())
    return rows


# td_glsl.yaml was pinned here but never read (dead pin polluting sources.lock)
INPUTS = [C.EXPERT / "td_network_patterns.yaml"]

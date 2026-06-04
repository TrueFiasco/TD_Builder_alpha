#!/usr/bin/env python3
"""
Add scraped UserGuide content to embedding documents.
Adds glossary terms and workflow tutorials to improve KB coverage.
"""

import json
from pathlib import Path

SCRAPED_PATH = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\scraped_content\userguide_content.json")
EMBEDDING_DOCS_PATH = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\embedding_docs\all_embedding_docs.json")


def load_scraped_content():
    with open(SCRAPED_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_existing_docs():
    with open(EMBEDDING_DOCS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_glossary_docs(content):
    """Generate embedding documents from glossary terms."""
    docs = []
    glossary = content.get('glossary', {})

    for term, definition in glossary.items():
        doc_id = f"glossary_{term.replace(' ', '_').replace('.', '_').replace('/', '_')}"

        # Create searchable text combining term and definition
        text = f"{term}: {definition}"

        docs.append({
            "id": doc_id,
            "type": "glossary",
            "family": "concept",
            "text": text,
            "metadata": {
                "term": term,
                "source": "derivative.ca/UserGuide"
            }
        })

    return docs


def generate_tutorial_docs(content):
    """Generate embedding documents from tutorials."""
    docs = []
    tutorials = content.get('tutorials', {})

    # First Things to Know sections
    ftk = tutorials.get('first_things_to_know', {})
    for section in ftk.get('sections', []):
        doc_id = f"tutorial_ftk_{section['id']}"
        text = f"Tutorial: {section['title']} - {section['topic']}. Learn how to {section['title'].lower()} in TouchDesigner."

        docs.append({
            "id": doc_id,
            "type": "tutorial",
            "family": "workflow",
            "text": text,
            "metadata": {
                "tutorial": "First Things to Know",
                "section": section['id'],
                "topic": section['topic'],
                "source": "derivative.ca/UserGuide"
            }
        })

    # Operator introduction workflows
    for key in ['intro_to_tops', 'intro_to_chops', 'intro_to_sops']:
        tutorial = tutorials.get(key, {})
        if not tutorial:
            continue

        title = tutorial.get('title', '')
        workflow = tutorial.get('workflow', '')
        operators = tutorial.get('key_operators', [])
        concepts = tutorial.get('concepts', [])

        # Main workflow document
        text = f"{title}: {workflow}. Key operators: {', '.join(operators)}. Concepts covered: {', '.join(concepts)}."

        docs.append({
            "id": f"workflow_{key}",
            "type": "workflow",
            "family": "tutorial",
            "text": text,
            "metadata": {
                "tutorial": title,
                "operators": ", ".join(operators),
                "concepts": ", ".join(concepts),
                "source": "derivative.ca/UserGuide"
            }
        })

        # Individual concept documents for better search
        for concept in concepts:
            docs.append({
                "id": f"workflow_{key}_{concept.replace(' ', '_').replace('/', '_')}",
                "type": "workflow_concept",
                "family": "tutorial",
                "text": f"How to: {concept} in TouchDesigner. Part of {title} tutorial. {workflow}",
                "metadata": {
                    "tutorial": title,
                    "concept": concept,
                    "source": "derivative.ca/UserGuide"
                }
            })

    return docs


def generate_howto_docs():
    """Generate 'how to' style documents for common tasks."""
    howtos = [
        # Original how-tos
        {
            "id": "howto_blur_image",
            "text": "How to blur an image in TouchDesigner: Use the Blur TOP operator. Connect your image source to its input. Adjust the Size parameter for blur amount. Use Pre-Shrink for performance optimization on large blurs.",
            "family": "TOP"
        },
        {
            "id": "howto_smooth_values",
            "text": "How to smooth or filter CHOP values in TouchDesigner: Use the Filter CHOP to smooth rapid changes. Types include Box, Gaussian, and One Euro filter. Alternatively use Lag CHOP for simple smoothing with separate lag up/down times.",
            "family": "CHOP"
        },
        {
            "id": "howto_feedback_effect",
            "text": "How to create a feedback effect in TouchDesigner: Use the Feedback TOP. Connect your source to input 0. The Feedback TOP outputs the previous frame, enabling trails, echoes and accumulation effects. Use with Composite TOP for decay.",
            "family": "TOP"
        },
        {
            "id": "howto_audio_reactive",
            "text": "How to make audio reactive visuals in TouchDesigner: Use Audio File In CHOP or Audio Device In CHOP for input. Use Audio Spectrum CHOP to analyze frequencies. Export CHOP values to TOP parameters like scale, color, or position.",
            "family": "CHOP"
        },
        {
            "id": "howto_particle_system",
            "text": "How to create a particle system in TouchDesigner: Use Particle SOP for CPU particles or POP operators for GPU particles. Add Force SOP/POP for movement. Use Geometry COMP and Render TOP to visualize. Instance geometry for rendering many particles.",
            "family": "POP"
        },
        {
            "id": "howto_connect_operators",
            "text": "How to connect operators with wires in TouchDesigner: Click and drag from an output connector (right side) to an input connector (left side). Or select source node, hold W key, and click destination. Use Shift+W for multiple connections.",
            "family": "workflow"
        },
        {
            "id": "howto_export_video",
            "text": "How to export video to file in TouchDesigner: Use Movie File Out TOP. Connect your final composite to its input. Set the File parameter for output path. Choose codec and format. Pulse Record to start, pulse again to stop.",
            "family": "TOP"
        },
        {
            "id": "howto_python_op",
            "text": "How to use op() function in Python TouchDesigner: op('nodename') returns reference to an operator. Use op('../nodename') for sibling, op('/project1/nodename') for absolute path. Access parameters with op('name').par.parametername.",
            "family": "python"
        },
        {
            "id": "howto_realtime_performance",
            "text": "How to optimize for realtime 60fps in TouchDesigner: Use Performance Monitor to identify slow operators. Reduce TOP resolutions where possible. Use GPU operators over CPU. Minimize Python in cook loops. Use Time Slicing for CHOPs.",
            "family": "workflow"
        },
        {
            "id": "howto_glsl_shader",
            "text": "How to write a GLSL shader in TouchDesigner: Use GLSL TOP for image processing or GLSL MAT for materials. Access inputs with texture(sTD2DInputs[0], vUV). Output to fragColor. Use TD helpers like TDTexture2D and TD2DInfos for resolution.",
            "family": "GLSL"
        },
        {
            "id": "howto_instancing",
            "text": "How to instance geometry in TouchDesigner: Enable Instancing on Geometry COMP. Provide instance transforms via CHOP (tx, ty, tz, rx, ry, rz, sx, sy, sz channels). Use Instance CHOP page to map channels. Renders thousands of copies efficiently on GPU.",
            "family": "COMP"
        },
        {
            "id": "howto_read_file",
            "text": "How to read data from a file in TouchDesigner: Use File In DAT for text files. Use Table DAT for CSV. Use Movie File In TOP for images/video. Use Audio File In CHOP for audio. Use CHOP/TOP File In for specialized formats.",
            "family": "DAT"
        },
        # Audio CHOPs content (from scraped high-value article)
        {
            "id": "howto_audio_synthesis",
            "text": "How to create synthesized audio in TouchDesigner: Use Audio Oscillator CHOP for waveforms (sine, square, triangle, sawtooth, pulse). Use Audio Para EQ CHOP for equalization. Use Audio Filter CHOP for low/high/band pass filtering. Set sample rate via project.cookRate.",
            "family": "CHOP"
        },
        {
            "id": "howto_audio_playback",
            "text": "How to play audio files in TouchDesigner: Use Audio File In CHOP to load audio files. Use Audio Play CHOP to control playback with loop, speed, and cue parameters. Connect to Audio Device Out CHOP for speaker output. Use Audio Render CHOP for complex mixes.",
            "family": "CHOP"
        },
        {
            "id": "howto_3d_audio",
            "text": "How to create 3D spatial audio in TouchDesigner: Use Audio 3D CHOP with head and source position inputs. Set listener position/orientation for accurate spatialization. Connect multiple sources for immersive soundscapes. Use Audio Device Out CHOP for multi-channel output.",
            "family": "CHOP"
        },
        {
            "id": "howto_audio_analysis",
            "text": "How to analyze audio for visualization in TouchDesigner: Use Audio Spectrum CHOP for frequency bands. Use Audio Band EQ CHOP for specific frequency isolation. Use Math CHOP to scale values. Export to TOP parameters for audio-reactive visuals.",
            "family": "CHOP"
        },
        # GLSL Material content (from scraped high-value article)
        {
            "id": "howto_glsl_material",
            "text": "How to write a GLSL material shader in TouchDesigner: Create GLSL MAT, write vertex shader and pixel shader in attached DATs. Use TDDeform() for vertex transformation, TDLighting() for built-in lighting, TDOutputSwizzle() for correct output. Access uniforms via sUniforms structure.",
            "family": "MAT"
        },
        {
            "id": "howto_glsl_vertex",
            "text": "How to write a GLSL vertex shader in TouchDesigner: Start with TDDeform(P) to get deformed position. Access attributes: uv[0-7], Cd (color), N (normal). Transform normals with TDDeformNorm(N). Use TDInstanceID() for instancing. Output to gl_Position.",
            "family": "GLSL"
        },
        {
            "id": "howto_glsl_pixel",
            "text": "How to write a GLSL pixel shader in TouchDesigner: Use TDLighting() for standard lighting. Sample textures with texture(sTD2DInputs[n], vUV.st). Access camera info via uTDMats. Use TDOutputSwizzle() before fragColor assignment. Enable depth output with TDAlphaTest().",
            "family": "GLSL"
        },
        {
            "id": "howto_glsl_uniforms",
            "text": "How to pass uniforms to GLSL shaders in TouchDesigner: Access built-in uniforms via uTDMats (matrices), uTDGeneral (time, resolution), uTDLights (lighting). Create custom uniforms on GLSL MAT Vectors page. Use sUniforms.uMyVector in shader code.",
            "family": "GLSL"
        },
        # Shadow rendering content (from scraped high-value article)
        {
            "id": "howto_shadows",
            "text": "How to render shadows in TouchDesigner: 1) Enable Cast Shadows on geometry Render tab. 2) Enable Receive Shadows on receiving geometry. 3) Enable Shadow on Light COMP. 4) Enable Shadow in Render TOP. Use Shadow Map Resolution for quality vs performance tradeoff.",
            "family": "rendering"
        },
        {
            "id": "howto_shadow_quality",
            "text": "How to improve shadow quality in TouchDesigner: Increase Shadow Map Resolution on Light COMP (512-4096). Adjust Shadow Map Bias to prevent self-shadowing artifacts. Use Shadow Softness for softer edges. Use Variance Shadow Maps for smoother gradients.",
            "family": "rendering"
        },
        {
            "id": "howto_shadow_artifacts",
            "text": "How to fix shadow artifacts in TouchDesigner: Shadow acne (dots) - increase Shadow Map Bias. Peter panning (detached shadows) - decrease Shadow Map Bias. Pixelated edges - increase Shadow Map Resolution. Light bleeding - use smaller shadow frustum or higher resolution.",
            "family": "rendering"
        },
        # Python scripting content (from scraped guides)
        {
            "id": "howto_python_chop_values",
            "text": "How to get CHOP channel values in Python TouchDesigner: Use op('chop1')['chan1'] for single value. Use op('chop1')['chan1'].eval() explicitly. Use op('chop1').numSamples for sample count. Use op('chop1').numChans for channel count. Iterate with for c in op('chop1').chans().",
            "family": "python"
        },
        {
            "id": "howto_python_table_dat",
            "text": "How to work with Table DAT in Python TouchDesigner: Use op('table1')[row,col] for cell value. Use op('table1').numRows and .numCols for dimensions. Use op('table1').appendRow(['a','b']) to add rows. Use op('table1').row(0) for row reference.",
            "family": "python"
        },
        {
            "id": "howto_python_parameters",
            "text": "How to set parameters via Python in TouchDesigner: Use op('node').par.Size = 5 for direct assignment. Use .val for current value, .eval() to evaluate expressions. Use op('node').pars() to iterate all parameters. Use op('node').par.Size.default for default value.",
            "family": "python"
        },
        {
            "id": "howto_python_callbacks",
            "text": "How to use callbacks in Python TouchDesigner: Create DAT with callback functions. Common callbacks: onValueChange(par, val, prev) for parameters, onCook(dat) for DAT cooking. Use Execute DAT for timed callbacks. Use Panel Execute DAT for UI events.",
            "family": "python"
        },
        {
            "id": "howto_python_extensions",
            "text": "How to create Python extensions in TouchDesigner: Add Extension Object parameter on COMP. Create Text DAT with class extending extension class. Define __init__(self, ownerComp). Access via op('comp1').MyMethod(). Use self.ownerComp to reference the component.",
            "family": "python"
        },
        # Expression cookbook content
        {
            "id": "howto_expressions_time",
            "text": "How to use time expressions in TouchDesigner: Use absTime.seconds for absolute time. Use me.time.frame for current frame. Use op('timeline1').time.seconds for timeline time. Use math.sin(absTime.seconds) for oscillation. Use absTime.frame % 60 for frame cycling.",
            "family": "python"
        },
        {
            "id": "howto_expressions_random",
            "text": "How to generate random values in TouchDesigner: Use tdu.rand(seed) for deterministic random 0-1. Use absTime.frame as seed for per-frame random. Use op('noise1')['chan1'] for smooth noise. Use tdu.remap(val, 0, 1, min, max) to scale range.",
            "family": "python"
        },
        {
            "id": "howto_expressions_conditional",
            "text": "How to use conditional expressions in TouchDesigner: Use Python ternary: 5 if op('chop1')['chan1'] > 0.5 else 0. Use tdu.clamp(val, min, max) for range limiting. Use max(0, val) for floor. Use abs(val) for absolute value.",
            "family": "python"
        }
    ]

    docs = []
    for howto in howtos:
        docs.append({
            "id": howto["id"],
            "type": "howto",
            "family": howto["family"],
            "text": howto["text"],
            "metadata": {
                "source": "synthesized",
                "type": "procedural_howto"
            }
        })

    return docs


def main():
    print("Loading scraped content...")
    scraped = load_scraped_content()

    print("Loading existing embedding docs...")
    existing = load_existing_docs()
    existing_docs = existing.get('documents', [])
    existing_ids = {d['id'] for d in existing_docs}

    print(f"Existing documents: {len(existing_docs)}")

    # Generate new documents
    new_docs = []

    print("\nGenerating glossary documents...")
    glossary_docs = generate_glossary_docs(scraped)
    for doc in glossary_docs:
        if doc['id'] not in existing_ids:
            new_docs.append(doc)
    print(f"  New glossary terms: {len([d for d in glossary_docs if d['id'] not in existing_ids])}")

    print("Generating tutorial documents...")
    tutorial_docs = generate_tutorial_docs(scraped)
    for doc in tutorial_docs:
        if doc['id'] not in existing_ids:
            new_docs.append(doc)
    print(f"  New tutorial docs: {len([d for d in tutorial_docs if d['id'] not in existing_ids])}")

    print("Generating how-to documents...")
    howto_docs = generate_howto_docs()
    for doc in howto_docs:
        if doc['id'] not in existing_ids:
            new_docs.append(doc)
    print(f"  New how-to docs: {len([d for d in howto_docs if d['id'] not in existing_ids])}")

    # Merge
    all_docs = existing_docs + new_docs

    # Save
    output = {
        "total": len(all_docs),
        "documents": all_docs
    }

    with open(EMBEDDING_DOCS_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n=== Complete ===")
    print(f"Previous documents: {len(existing_docs)}")
    print(f"New documents added: {len(new_docs)}")
    print(f"Total documents: {len(all_docs)}")
    print(f"\nRun create_embeddings.py --create to regenerate embeddings")


if __name__ == '__main__':
    main()

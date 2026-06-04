#!/usr/bin/env python3
"""
Prepare Workflow Prompts for Subagent Execution

This script prepares the KB context and expert prompts for a workflow,
outputting them in a format that Claude Code can use to spawn subagents.

Usage:
    python prepare_workflow.py --spec "path/to/spec.md" --strategy v2
    python prepare_workflow.py --spec-text "Create audio reactive visuals..."
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from meta_agentic.execution import (
    get_default_kb,
    EXPERT_CONFIGS,
)
from meta_agentic.execution.strategy_runner import query_knowledge_base_comprehensive


def prepare_workflow(spec: str, strategy: str = "v2", output_path: str = None) -> dict:
    """
    Prepare the workflow prompts and KB context.

    Args:
        spec: The creative/technical specification
        strategy: Workflow strategy (v2-v6)
        output_path: Optional path to save output JSON

    Returns:
        Dictionary with KB context and expert prompts
    """
    timestamp = datetime.now().isoformat()

    # Query knowledge base
    print("Querying knowledge base...")
    kb = get_default_kb()
    kb_results = query_knowledge_base_comprehensive(kb, spec, timestamp)

    print(f"  Found {len(kb_results.get('palette_recommendations', []))} palette items")
    print(f"  Found {len(kb_results.get('operators', {}))} operator families")
    print(f"  Found {len(kb_results.get('patterns', []))} patterns")
    print(f"  Found {len(kb_results.get('glsl', {}))} GLSL entries")
    print(f"  Found {len(kb_results.get('python', {}))} Python entries")

    # Format KB context for prompts
    kb_context = format_kb_context(kb_results)

    # Prepare expert prompts
    prompts = prepare_expert_prompts(spec, kb_context, strategy)

    result = {
        "timestamp": timestamp,
        "strategy": strategy,
        "spec": spec,
        "kb_results": {
            "palette_count": len(kb_results.get('palette_recommendations', [])),
            "palette_items": [p.get('name', str(p)) for p in kb_results.get('palette_recommendations', [])[:10]],
            "operator_families": list(kb_results.get('operators', {}).keys()),
            "patterns": [p.get('category', str(p)) if isinstance(p, dict) else str(p) for p in kb_results.get('patterns', [])],
            "glsl_entries": list(kb_results.get('glsl', {}).keys()),
            "python_entries": list(kb_results.get('python', {}).keys()),
        },
        "kb_context": kb_context,
        "prompts": prompts,
    }

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved to: {output_path}")

    return result


def format_kb_context(kb_results: dict) -> str:
    """Format KB results into a context string for expert prompts."""
    sections = []

    # Palette recommendations
    palette = kb_results.get('palette_recommendations', [])
    if palette:
        sections.append("## Available Palette Components (Pre-built TOX files)")
        sections.append("CHECK THESE FIRST before building custom operators:")
        for p in palette[:15]:
            if isinstance(p, dict):
                name = p.get('name', 'unknown')
                purpose = p.get('purpose', p.get('summary', ''))
                tox_path = p.get('tox_path', '')
                sections.append(f"- **{name}**: {purpose}")
                if tox_path:
                    sections.append(f"  Path: {tox_path}")
            else:
                sections.append(f"- {p}")
        sections.append("")

    # Operators
    operators = kb_results.get('operators', {})
    if operators:
        sections.append("## TouchDesigner Operators")
        for family, ops in operators.items():
            sections.append(f"### {family.upper()}")
            if isinstance(ops, list):
                for op in ops[:5]:
                    if isinstance(op, dict):
                        sections.append(f"- {op.get('name', op)}: {op.get('purpose', '')}")
                    else:
                        sections.append(f"- {op}")
            sections.append("")

    # Patterns
    patterns = kb_results.get('patterns', [])
    if patterns:
        sections.append("## Network Patterns")
        for p in patterns[:5]:
            if isinstance(p, dict):
                sections.append(f"- **{p.get('category', 'pattern')}**: {p.get('description', '')}")
            else:
                sections.append(f"- {p}")
        sections.append("")

    # GLSL
    glsl = kb_results.get('glsl', {})
    if glsl:
        sections.append("## GLSL Expertise")
        for key in list(glsl.keys())[:3]:
            sections.append(f"- {key}")
        sections.append("")

    # Python
    python = kb_results.get('python', {})
    if python:
        sections.append("## Python Expertise")
        for key in list(python.keys())[:3]:
            sections.append(f"- {key}")
        sections.append("")

    return "\n".join(sections)


def prepare_expert_prompts(spec: str, kb_context: str, strategy: str) -> dict:
    """Prepare prompts for each expert phase."""

    # Creative Expert prompt
    creative_prompt = f"""You are a Creative Vision Expert for TouchDesigner projects.

{kb_context}

## Your Task
Analyze this specification and develop the creative vision:

{spec}

## Output Format
Provide your creative vision as structured YAML:
```yaml
vision:
  concept: "Core creative concept"
  mood: "Emotional tone"
  references: ["Visual references"]

color_palette:
  primary: "#hexcode - description"
  secondary: "#hexcode - description"
  accent: "#hexcode - description"

visual_elements:
  - name: "Element name"
    description: "What it does"
    behavior: "How it reacts"

audio_mapping:
  - frequency_range: "20-80Hz"
    drives: "What visual element"
    behavior: "How it responds"

sections:
  - time: "0:00-0:30"
    name: "Section name"
    description: "What happens"
    intensity: 0.0-1.0
```"""

    # Technical Expert prompt
    technical_prompt = f"""You are a Technical Architecture Expert for TouchDesigner projects.

{kb_context}

## Your Task
Design the technical architecture for this specification:

{spec}

## Output Format
Provide your technical design as structured YAML:
```yaml
architecture:
  overview: "High-level architecture description"

operators:
  - name: "operatorName"
    type: "TOP/CHOP/SOP/etc"
    purpose: "What it does"
    parameters:
      - param: value
    connections:
      - from: "source"
        to: "destination"

audio_analysis:
  - name: "audioAnalysisCHOP"
    type: "audioSpectrum/audioDeviceIn/etc"
    purpose: "Frequency analysis"
    outputs:
      - name: "lowFreq"
        range: "20-80Hz"

render_pipeline:
  resolution: "1920x1080"
  fps: 60
  stages:
    - name: "Stage name"
      operators: ["list of operators"]
```"""

    # Design Expert prompt
    design_prompt = f"""You are a Network Design Expert for TouchDesigner projects.

{kb_context}

## Your Task
Design the detailed operator network for this specification:

{spec}

## Output Format
Provide your network design as structured YAML:
```yaml
network:
  name: "project_name"

containers:
  - name: "containerName"
    purpose: "What this container does"
    operators:
      - name: "opName"
        type: "operatorType"
        parameters:
          param1: value1

connections:
  - from: "container1/op1"
    to: "container2/op2"

glsl_shaders:
  - name: "shaderName"
    type: "glslTOP"
    purpose: "What the shader does"
    uniforms:
      - name: "uniformName"
        type: "float/vec2/vec3/vec4"
        source: "CHOP path"

python_scripts:
  - name: "scriptName"
    purpose: "What the script does"
    triggers: ["When it runs"]
```"""

    # Critic prompt
    critic_prompt = f"""You are a Quality Critic for TouchDesigner projects.

Review the following outputs and score them:

## Specification
{spec}

## Output Format
Provide your critique as structured YAML:
```yaml
scores:
  creative: 0.0-1.0
  technical: 0.0-1.0
  design: 0.0-1.0
  overall: 0.0-1.0

issues:
  - category: "creative/technical/design"
    severity: "critical/major/minor"
    description: "What's wrong"
    suggestion: "How to fix"

strengths:
  - "What's done well"

recommendations:
  - priority: 1-5
    action: "What to improve"
```"""

    return {
        "creative": creative_prompt,
        "technical": technical_prompt,
        "design": design_prompt,
        "critic": critic_prompt,
    }


# Teardrop spec for quick testing
TEARDROP_SPEC = """
# TEARDROP - Massive Attack Visual System

## Project Overview
Artist: Massive Attack
Track: "Teardrop"
Duration: 5:29
Context: Intimate venue, single large rear projection + subtle floor projection.

## Creative Vision
Abstract emergence - warmth in void - heartbeat as architecture.
Reimagining the iconic original video's theme of life forming and vulnerability,
but abstracted for live performance.

## Audio Analysis Requirements
- Low frequency (20-80Hz): Heartbeat pulse, drives central glow
- Mid frequency (250Hz-2kHz): Vocal presence, drives tendril growth
- High frequency (4-16kHz): Harpsichord/texture, drives glitch effects
- Beat detection: 80 BPM approximate

## Visual Elements
1. Central Pulse (Heartbeat) - warm amber to gold glow
2. Particle Tendrils - neural-like streams responding to vocal pitch
3. Membrane Surface - curved forms with displacement/noise
4. Glitch/Interference - brief digital artifacts on harpsichord

## Technical Requirements
- Resolution: 1920x1080 minimum, 4K preferred
- Frame rate: 60fps target
"""


def main():
    parser = argparse.ArgumentParser(description="Prepare workflow prompts")
    parser.add_argument('--spec', '-s', help='Path to spec file')
    parser.add_argument('--spec-text', '-t', help='Spec text directly')
    parser.add_argument('--teardrop', action='store_true', help='Use Teardrop spec')
    parser.add_argument('--strategy', default='v2', choices=['v2', 'v3', 'v4', 'v5', 'v6'])
    parser.add_argument('--output', '-o', help='Output JSON path')

    args = parser.parse_args()

    # Get spec
    if args.teardrop:
        spec = TEARDROP_SPEC
    elif args.spec:
        with open(args.spec, 'r', encoding='utf-8') as f:
            spec = f.read()
    elif args.spec_text:
        spec = args.spec_text
    else:
        print("Error: Provide --spec, --spec-text, or --teardrop")
        sys.exit(1)

    # Default output path
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(__file__).parent / "test_output" / "workflow_prompts"
        output_dir.mkdir(parents=True, exist_ok=True)
        args.output = str(output_dir / f"prompts_{args.strategy}_{timestamp}.json")

    result = prepare_workflow(spec, args.strategy, args.output)

    print("\n" + "="*60)
    print("WORKFLOW PROMPTS PREPARED")
    print("="*60)
    print(f"Strategy: {args.strategy}")
    print(f"Experts: {list(result['prompts'].keys())}")
    print(f"\nTo execute, ask Claude Code to:")
    print(f"  'Run the {args.strategy} workflow using {args.output}'")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Generate haiku prompts for Palette components.
Different from snippets - focus on what the component DOES as a tool.
"""

import yaml
from pathlib import Path

def main():
    facts_path = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts\palette_facts.yaml")
    output_dir = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_prompts")
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(facts_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    output_path = output_dir / "palette_prompt.txt"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# TouchDesigner Palette Component Descriptions\n\n")
        f.write("Write a 1-2 sentence description for each component.\n")
        f.write("Focus on WHAT the component does and its PURPOSE.\n")
        f.write("Use the category and internal operators to understand the function.\n")
        f.write("DO NOT describe individual operators - describe the component as a whole.\n\n")
        f.write("Output format:\n")
        f.write("```yaml\n")
        f.write("category:\n")
        f.write("  component_name: \"description...\"\n")
        f.write("```\n\n")
        f.write("---\n\n")

        total = 0
        for category, cat_data in data['categories'].items():
            f.write(f"## {category}\n\n")

            for comp in cat_data['components']:
                name = comp['name']
                network = comp['network']

                f.write(f"### {name}\n")
                f.write(f"Category: {category}\n")

                # Summarize operators by type
                type_dist = network.get('type_distribution', {})
                if type_dist:
                    types_str = ", ".join(f"{k}:{v}" for k, v in sorted(type_dist.items()))
                    f.write(f"Operators: {network['operator_count']} ({types_str})\n")

                # List key operators
                ops = network.get('operators', [])
                if ops:
                    op_list = [f"{op['name']}({op['type']})" for op in ops[:8]]
                    f.write(f"Contains: {', '.join(op_list)}")
                    if len(ops) > 8:
                        f.write(f" +{len(ops)-8} more")
                    f.write("\n")

                # Connections
                conns = network.get('connections', [])
                if conns:
                    f.write(f"Connections: {network['connection_count']}\n")

                f.write("\n")
                total += 1

    print(f"Generated prompt for {total} palette components")
    print(f"Saved: {output_path}")

if __name__ == '__main__':
    main()

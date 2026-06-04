"""
Generate compact prompts for haiku to write network descriptions.
Outputs one prompt file per family.
"""
import yaml
from pathlib import Path


def summarize_example(example: dict) -> str:
    """Create compact summary for haiku prompt."""
    name = example['example_name']
    ops = example.get('operators', [])
    conns = example.get('connections', [])
    topo = example.get('topology', {})
    curator = example.get('curator_text', '')

    # Group ops by role
    by_role = {'input': [], 'processor': [], 'output': [], 'isolated': []}
    for op in ops:
        role = op.get('role', 'isolated')
        op_str = f"{op['name']}({op['type']})"
        by_role[role].append(op_str)

    # Build compact summary
    lines = [f"### {name}"]
    if curator:
        lines.append(f"Curator: {curator[:200]}")

    for role in ['input', 'processor', 'output', 'isolated']:
        if by_role[role]:
            lines.append(f"{role.upper()}: {', '.join(by_role[role][:10])}")
            if len(by_role[role]) > 10:
                lines.append(f"  ...and {len(by_role[role])-10} more")

    if conns:
        conn_strs = [f"{c['from']}->{c['to']}" for c in conns[:8]]
        lines.append(f"FLOW: {', '.join(conn_strs)}")
        if len(conns) > 8:
            lines.append(f"  ...and {len(conns)-8} more connections")

    lines.append(f"TOPO: {topo.get('operator_count',0)} ops, {topo.get('connection_count',0)} conns, chain={topo.get('max_chain_length',1)}")
    lines.append("")

    return '\n'.join(lines)


def main():
    facts_dir = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts\by_family")
    prompts_dir = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_prompts")
    prompts_dir.mkdir(exist_ok=True)

    for yaml_file in facts_dir.glob("*_facts.yaml"):
        family = yaml_file.stem.replace('_facts', '')

        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # Build prompt
        prompt_lines = [
            f"# {family} Network Descriptions",
            "",
            "Write ONLY a 1-2 sentence network_description for each example.",
            "Describe the DATA FLOW based on the operators and connections.",
            "DO NOT explain what operators do. DO NOT explain parameter values.",
            "",
            "Output format:",
            "```yaml",
            "operator_type:",
            "  example_name: \"description...\"",
            "```",
            "",
            "---",
            ""
        ]

        example_count = 0
        for op in data.get('operators', []):
            op_type = op['operator_type']
            prompt_lines.append(f"## {op_type}")

            for ex in op.get('examples', []):
                prompt_lines.append(summarize_example(ex))
                example_count += 1

        # Save prompt
        prompt_path = prompts_dir / f"{family}_prompt.txt"
        with open(prompt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(prompt_lines))

        print(f"{family}: {example_count} examples -> {prompt_path}")


if __name__ == '__main__':
    main()

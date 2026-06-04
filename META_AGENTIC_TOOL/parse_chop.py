#!/usr/bin/env python3
import re
import yaml

# Read the CHOP prompt file
with open(r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_prompts\CHOP_prompt.txt", "r", encoding="utf-8") as f:
    content = f.read()

# Dictionary to store results
results = {}

# Split by operator sections (## operatorCHOP)
operator_pattern = r'^## ([a-zA-Z]+CHOP)'
example_pattern = r'^### (example\d+)'
curator_pattern = r'^Curator: (.+?)$'
flow_pattern = r'^FLOW: (.+?)$'

lines = content.split('\n')
current_operator = None
current_example = None
current_data = {}

for i, line in enumerate(lines):
    # Check for operator type
    op_match = re.match(operator_pattern, line)
    if op_match:
        current_operator = op_match.group(1)
        if current_operator not in results:
            results[current_operator] = {}
        current_example = None
        current_data = {}
        continue

    # Check for example
    ex_match = re.match(example_pattern, line)
    if ex_match:
        current_example = ex_match.group(1)
        current_data = {}
        continue

    # Check for Curator line (description)
    if current_example and current_operator:
        if line.startswith('Curator:'):
            curator_text = line.replace('Curator: ', '').strip()
            current_data['curator'] = curator_text
        elif line.startswith('INPUT:'):
            current_data['input'] = line.replace('INPUT: ', '').strip()
        elif line.startswith('FLOW:'):
            flow_text = line.replace('FLOW: ', '').strip()
            current_data['flow'] = flow_text
            # Store the data when we see FLOW (end of example)
            if current_operator and current_example:
                # Create a description from curator and flow
                description = current_data.get('curator', '')
                results[current_operator][current_example] = description

# Output YAML
output = {}
for operator, examples in sorted(results.items()):
    if examples:  # Only include operators with examples
        output[operator] = {}
        for example_name in sorted(examples.keys()):
            output[operator][example_name] = examples[example_name]

# Write to output file
output_path = r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_output\CHOP_descriptions.yaml"
with open(output_path, 'w', encoding='utf-8') as f:
    yaml.dump(output, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

print(f"Generated YAML with {len(output)} operators")
print(f"Output saved to {output_path}")

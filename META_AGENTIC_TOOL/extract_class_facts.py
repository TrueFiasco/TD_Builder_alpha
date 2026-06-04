#!/usr/bin/env python3
"""
Extract structured facts from _Class.htm files.
Separates: base classes vs operator-specific classes
Outputs: structured facts JSON + Haiku prompt for semantic descriptions
"""

import re
import json
import yaml
from pathlib import Path
from collections import defaultdict

# Base classes that apply to all operators in a family
BASE_CLASSES = ['OP', 'CHOP', 'TOP', 'SOP', 'DAT', 'MAT', 'COMP', 'POP', 'ObjectCOMP', 'PanelCOMP']


def clean_html(text: str) -> str:
    """Remove HTML tags and clean text."""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_items(content: str) -> list:
    """Extract members/methods from HTML content."""
    items = []

    # Pattern for members/methods - handles optional <b>(Read Only)</b> and other tags
    # Also handles newlines between </p> and <blockquote>
    # Arrow can be: → or → or &#8594; (HTML entity)
    # May have &#160; (nbsp) before colon
    # Return type may contain HTML tags (spans, links, etc)
    arrow_pattern = r'(?:→|→|&#8594;)'
    patterns = [
        # Standard pattern with optional style and colon before </p>
        rf'<div id="([^"]+)"[^>]*></div>\s*<p>\s*<code class="python">([^<]+)</code>\s*{arrow_pattern}\s*<code class="return">(.*?)</code>([^<]*(?:<[^>]+>[^<]*)*?)(?:&#160;)?:\s*</p>\s*<blockquote><p>([^<]+)',
        # Pattern without colon
        rf'<div id="([^"]+)"[^>]*></div>\s*<p>\s*<code class="python">([^<]+)</code>\s*{arrow_pattern}\s*<code class="return">(.*?)</code>([^<]*(?:<[^>]+>[^<]*)*?)</p>\s*<blockquote><p>([^<]+)',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, content, re.DOTALL):
            name = match.group(1)
            signature = match.group(2).strip()
            return_type = clean_html(match.group(3).strip())  # May contain HTML tags
            modifiers = match.group(4).strip()  # e.g., "(Read Only)"
            description = clean_html(match.group(5))

            # Skip if we already have this item
            if any(i['name'] == name for i in items):
                continue

            is_readonly = 'Read Only' in modifiers
            is_method = '(' in signature

            item = {
                'name': name,
                'signature': signature,
                'return_type': return_type,
                'description': description,
                'readonly': is_readonly,
                'type': 'method' if is_method else 'member'
            }

            # Extract parameters for methods
            if is_method:
                param_match = re.search(r'\(([^)]*)\)', signature)
                if param_match:
                    params_str = param_match.group(1)
                    if params_str:
                        item['parameters'] = [p.strip() for p in params_str.split(',') if p.strip()]

            items.append(item)

    return items


def extract_callbacks(content: str) -> list:
    """Extract callback function names and their parameters."""
    callbacks = []

    # Find callback section
    callback_match = re.search(r'<h2><span class="mw-headline" id="Callbacks">.*?<pre[^>]*>(.*?)</pre>', content, re.DOTALL)
    if callback_match:
        callback_code = callback_match.group(1)
        # Find function definitions
        for func_match in re.finditer(r'def\s+(\w+)\s*\(([^)]*)\)', callback_code):
            func_name = func_match.group(1)
            params_str = func_match.group(2)
            params = [p.strip() for p in params_str.split(',') if p.strip()]
            callbacks.append({
                'name': func_name,
                'parameters': params
            })

    return callbacks


def extract_class(htm_path: Path) -> dict:
    """Extract all data from a _Class.htm file."""
    content = htm_path.read_text(encoding='utf-8', errors='ignore')

    class_name = htm_path.stem.replace('_Class', '')

    # Determine if this is a base class or operator-specific
    is_base = class_name in BASE_CLASSES

    # Determine family
    family = ''
    if not is_base:
        for fam in ['CHOP', 'SOP', 'TOP', 'DAT', 'MAT', 'COMP', 'POP']:
            if fam in class_name:
                family = fam
                break
    else:
        family = class_name  # Base class IS the family

    # Extract inheritance
    inherits = ''
    inherit_match = re.search(r'inherits from the.*?<a[^>]*>([^<]+)</a>', content)
    if inherit_match:
        inherits = inherit_match.group(1).strip().replace(' class', '_Class')

    # Find where inherited content starts
    inherited_section = re.search(r'<h1><span class="mw-headline" id="(CHOP|SOP|TOP|DAT|MAT|COMP|POP|OP|ObjectCOMP|PanelCOMP)_Class">', content)
    if inherited_section:
        class_content = content[:inherited_section.start()]
    else:
        class_content = content

    # Check for unique content
    has_unique_members = 'No operator specific members' not in class_content
    has_unique_methods = 'No operator specific methods' not in class_content

    # Extract items from class-specific section
    items = extract_items(class_content)
    members = [i for i in items if i['type'] == 'member']
    methods = [i for i in items if i['type'] == 'method']

    # Extract callbacks
    callbacks = extract_callbacks(class_content)

    # For base classes, extract from their own file (content before OP_Class section)
    if is_base:
        # For base class files, content is at TOP before any inherited h1 sections
        # Find where OP_Class or other parent starts
        parent_section = re.search(r'<h1><span class="mw-headline" id="OP_Class">', content)
        if parent_section:
            base_content = content[:parent_section.start()]
        else:
            base_content = content

        items = extract_items(base_content)
        members = [i for i in items if i['type'] == 'member']
        methods = [i for i in items if i['type'] == 'method']
        callbacks = extract_callbacks(base_content)

    return {
        'class_name': class_name + '_Class',
        'operator': class_name if not is_base else None,
        'is_base_class': is_base,
        'family': family,
        'inherits': inherits,
        'has_unique_members': has_unique_members,
        'has_unique_methods': has_unique_methods,
        'members': members,
        'methods': methods,
        'callbacks': callbacks
    }


def generate_haiku_prompt(classes: list, output_path: Path):
    """Generate prompt for Haiku to create semantic descriptions."""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# TouchDesigner Python API - Semantic Descriptions\n\n")
        f.write("For each method/member below, write a 1-2 sentence semantic description.\n")
        f.write("Focus on WHAT it does and WHEN you'd use it.\n")
        f.write("Write for someone searching 'how do I...' - use natural language.\n\n")
        f.write("Output format:\n```yaml\nclass_name:\n  method_name: \"description...\"\n```\n\n")
        f.write("---\n\n")

        count = 0
        for cls in classes:
            if not cls['members'] and not cls['methods'] and not cls['callbacks']:
                continue

            f.write(f"## {cls['class_name']}\n")
            if cls['is_base_class']:
                f.write(f"Base class for all {cls['family']} operators\n\n")
            else:
                f.write(f"Operator: {cls['operator']} ({cls['family']})\n\n")

            if cls['members']:
                f.write("### Members\n")
                for m in cls['members']:
                    f.write(f"- `{m['signature']}` → {m['return_type']}")
                    if m['readonly']:
                        f.write(" (read-only)")
                    f.write(f"\n  Raw: {m['description'][:200]}\n\n")
                    count += 1

            if cls['methods']:
                f.write("### Methods\n")
                for m in cls['methods']:
                    f.write(f"- `{m['signature']}` → {m['return_type']}\n")
                    f.write(f"  Raw: {m['description'][:200]}\n\n")
                    count += 1

            if cls['callbacks']:
                f.write("### Callbacks\n")
                for cb in cls['callbacks']:
                    params = ', '.join(cb['parameters'])
                    f.write(f"- `{cb['name']}({params})`\n")
                    count += 1
                f.write("\n")

        print(f"Generated prompt for {count} items")


def main():
    htm_dir = Path(r"C:\TD_Projects\Learn\OfflineHelp\https.docs.derivative.ca")
    output_dir = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts")
    output_dir.mkdir(parents=True, exist_ok=True)

    class_files = sorted(htm_dir.glob("*_Class.htm"))
    print(f"Found {len(class_files)} _Class.htm files")

    all_classes = []
    base_classes = []
    operator_classes = defaultdict(list)

    stats = {
        'total': 0,
        'base_classes': 0,
        'with_unique_content': 0,
        'total_members': 0,
        'total_methods': 0,
        'total_callbacks': 0
    }

    for i, htm_path in enumerate(class_files, 1):
        if i % 100 == 0:
            print(f"  Progress: {i}/{len(class_files)}")

        try:
            data = extract_class(htm_path)
            all_classes.append(data)

            stats['total'] += 1
            stats['total_members'] += len(data['members'])
            stats['total_methods'] += len(data['methods'])
            stats['total_callbacks'] += len(data['callbacks'])

            if data['is_base_class']:
                base_classes.append(data)
                stats['base_classes'] += 1
            else:
                family = data['family'] or 'Other'
                operator_classes[family].append(data)
                if data['members'] or data['methods'] or data['callbacks']:
                    stats['with_unique_content'] += 1

        except Exception as e:
            print(f"  Error processing {htm_path.name}: {e}")

    # Save base classes separately (high value)
    base_output = output_dir / "base_classes.json"
    with open(base_output, 'w', encoding='utf-8') as f:
        json.dump({
            'description': 'Base classes with methods available to all operators in family',
            'count': len(base_classes),
            'classes': base_classes
        }, f, indent=2)
    print(f"Saved {len(base_classes)} base classes -> {base_output.name}")

    # Save operator-specific classes by family
    for family, classes in operator_classes.items():
        # Filter to only those with unique content
        with_content = [c for c in classes if c['members'] or c['methods'] or c['callbacks']]

        output_path = output_dir / f"{family}_operator_classes.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'family': family,
                'total': len(classes),
                'with_unique_content': len(with_content),
                'classes': with_content  # Only save those with content
            }, f, indent=2)
        print(f"Saved {family}: {len(with_content)}/{len(classes)} with unique content")

    # Generate Haiku prompt for base classes (highest priority)
    haiku_dir = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\haiku_prompts")
    haiku_dir.mkdir(parents=True, exist_ok=True)

    generate_haiku_prompt(base_classes, haiku_dir / "base_class_prompt.txt")

    # Generate Haiku prompt for operator classes with unique content
    unique_op_classes = [c for c in all_classes if not c['is_base_class'] and (c['members'] or c['methods'] or c['callbacks'])]
    generate_haiku_prompt(unique_op_classes, haiku_dir / "operator_class_prompt.txt")

    print(f"\n=== Summary ===")
    print(f"Total classes: {stats['total']}")
    print(f"Base classes: {stats['base_classes']}")
    print(f"Operator classes with unique content: {stats['with_unique_content']}")
    print(f"Total members: {stats['total_members']}")
    print(f"Total methods: {stats['total_methods']}")
    print(f"Total callbacks: {stats['total_callbacks']}")


if __name__ == '__main__':
    main()

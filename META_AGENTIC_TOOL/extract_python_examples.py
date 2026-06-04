#!/usr/bin/env python3
"""
Extract Python code examples from TouchDesigner wiki HTM files.
Creates semantic descriptions for code search.
"""

import re
import json
import yaml
from pathlib import Path
from collections import defaultdict

HTM_DIR = Path(r"C:\TD_Projects\Learn\OfflineHelp\https.docs.derivative.ca")
OUTPUT_DIR = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts")


def clean_code(html_code: str) -> str:
    """Remove HTML tags and clean up code."""
    # Remove span tags but keep content
    code = re.sub(r'<span[^>]*>', '', html_code)
    code = re.sub(r'</span>', '', code)
    # Remove other tags
    code = re.sub(r'<[^>]+>', '', code)
    # Decode entities
    code = code.replace('&lt;', '<').replace('&gt;', '>')
    code = code.replace('&amp;', '&').replace('&quot;', '"')
    code = code.replace('&#39;', "'")
    # Clean whitespace but preserve indentation
    lines = code.split('\n')
    lines = [line.rstrip() for line in lines]
    # Remove empty lines at start/end
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return '\n'.join(lines)


def detect_apis(code: str) -> list:
    """Detect which TD APIs are used in the code."""
    apis = set()

    patterns = {
        'op()': r'\bop\s*\(',
        'ops()': r'\bops\s*\(',
        'parent()': r'\bparent\s*\(',
        'me': r'\bme\.',
        'mod': r'\bmod\.',
        'ext': r'\bext\.',
        'par': r'\.par\.',
        'pars()': r'\.pars\s*\(',
        'cook()': r'\.cook\s*\(',
        'eval()': r'\.eval\s*\(',
        'run()': r'\.run\s*\(',
        'store': r'\.store\b',
        'fetch': r'\.fetch\b',
        'CHOP': r'CHOP|\.chans|\.numChans|\.numpyArray',
        'TOP': r'TOP|\.width|\.height|\.sample\s*\(|\.save\s*\(',
        'SOP': r'SOP|\.points|\.prims|\.numPoints',
        'DAT': r'DAT|\.numRows|\.numCols|\.cell|\.row\s*\(|\.col\s*\(',
        'COMP': r'COMP|\.create\s*\(|\.findChildren|\.loadTox',
        'MAT': r'MAT',
        'Matrix': r'\bMatrix\b|\.translate|\.rotate|\.scale',
        'Position': r'\bPosition\b|tdu\.Position',
        'Vector': r'\bVector\b|tdu\.Vector',
        'absTime': r'\babsTime\b',
        'project': r'\bproject\b',
        'ui': r'\bui\.',
        'callbacks': r'\bdef\s+on[A-Z]',
        'tdu': r'\btdu\.',
        'td': r'\btd\.',
    }

    for api, pattern in patterns.items():
        if re.search(pattern, code):
            apis.add(api)

    return sorted(apis)


def categorize_example(code: str, apis: list) -> str:
    """Categorize the type of example."""
    code_lower = code.lower()

    if re.search(r'\bdef\s+on[A-Z]', code):
        return 'callback'
    if re.search(r'\.create\s*\(', code):
        return 'create'
    if re.search(r'\.copy\s*\(', code):
        return 'copy'
    if re.search(r'\.destroy\s*\(', code):
        return 'destroy'
    if re.search(r'\.save\s*\(|\.saveTox', code):
        return 'save'
    if re.search(r'\.load|\.loadTox', code):
        return 'load'
    if re.search(r'for\s+\w+\s+in\s+', code):
        return 'iteration'
    if re.search(r'\.append|\.insert|\.delete', code):
        return 'modify'
    if '=' in code and not '==' in code:
        if re.search(r'\.par\.\w+\s*=', code):
            return 'set_parameter'
        return 'assignment'
    if re.search(r'\[\s*[\'\"0-9]', code):
        return 'access'

    return 'reference'


def extract_examples(htm_path: Path) -> list:
    """Extract all Python examples from an HTM file."""
    content = htm_path.read_text(encoding='utf-8', errors='ignore')
    examples = []

    # Pattern for MediaWiki syntax-highlighted Python
    pattern = r'<div class="mw-highlight mw-highlight-lang-python[^"]*"[^>]*><pre[^>]*>(.*?)</pre></div>'

    for match in re.finditer(pattern, content, re.DOTALL):
        raw_code = match.group(1)
        code = clean_code(raw_code)

        # Skip very short or empty examples
        if not code or len(code) < 5:
            continue

        # Skip if it's just a comment
        if code.startswith('#') and '\n' not in code:
            continue

        apis = detect_apis(code)
        category = categorize_example(code, apis)

        examples.append({
            'code': code,
            'source': htm_path.stem,
            'apis': apis,
            'category': category,
            'lines': code.count('\n') + 1
        })

    return examples


def generate_semantic_description(example: dict) -> str:
    """Generate a semantic search description for an example."""
    code = example['code']
    apis = example['apis']
    category = example['category']

    # Build description based on what the code does
    parts = []

    # Category-based prefix
    category_phrases = {
        'callback': 'Callback function that handles',
        'create': 'Create operators using',
        'copy': 'Copy operators with',
        'destroy': 'Delete operators using',
        'save': 'Save to file using',
        'load': 'Load from file using',
        'iteration': 'Loop through',
        'modify': 'Modify data in',
        'set_parameter': 'Set parameter values on',
        'assignment': 'Access and assign values from',
        'access': 'Read values from',
        'reference': 'Reference'
    }
    parts.append(category_phrases.get(category, 'Example using'))

    # API-based content
    if 'CHOP' in apis:
        parts.append('CHOP channels')
    elif 'TOP' in apis:
        parts.append('TOP textures')
    elif 'SOP' in apis:
        parts.append('SOP geometry')
    elif 'DAT' in apis:
        parts.append('DAT tables')
    elif 'COMP' in apis:
        parts.append('components')
    elif 'par' in apis:
        parts.append('parameters')
    elif 'op()' in apis:
        parts.append('operators')

    return ' '.join(parts) + '.'


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Find all HTM files
    htm_files = list(HTM_DIR.glob('*.htm'))
    print(f"Scanning {len(htm_files)} HTM files...")

    all_examples = []
    by_source = defaultdict(list)
    by_category = defaultdict(list)
    by_api = defaultdict(list)

    for i, htm_path in enumerate(htm_files, 1):
        if i % 100 == 0:
            print(f"  Progress: {i}/{len(htm_files)}")

        examples = extract_examples(htm_path)
        all_examples.extend(examples)

        for ex in examples:
            by_source[ex['source']].append(ex)
            by_category[ex['category']].append(ex)
            for api in ex['apis']:
                by_api[api].append(ex)

    print(f"\nExtracted {len(all_examples)} Python examples")

    # Stats
    print(f"\nBy Category:")
    for cat, exs in sorted(by_category.items(), key=lambda x: -len(x[1])):
        print(f"  {cat}: {len(exs)}")

    print(f"\nTop APIs:")
    for api, exs in sorted(by_api.items(), key=lambda x: -len(x[1]))[:15]:
        print(f"  {api}: {len(exs)}")

    # Save structured data
    output_path = OUTPUT_DIR / "python_examples.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(all_examples),
            'examples': all_examples
        }, f, indent=2)
    print(f"\nSaved to: {output_path}")

    # Generate semantic descriptions for Haiku processing
    # Group by API for batch processing
    semantic_data = {}
    for ex in all_examples:
        key = f"{ex['source']}_{hash(ex['code']) % 10000}"
        semantic_data[key] = {
            'code': ex['code'][:500],  # Truncate long examples
            'apis': ex['apis'],
            'category': ex['category'],
            'auto_description': generate_semantic_description(ex)
        }

    semantic_path = OUTPUT_DIR / "python_examples_for_haiku.json"
    with open(semantic_path, 'w', encoding='utf-8') as f:
        json.dump(semantic_data, f, indent=2)
    print(f"Haiku input saved to: {semantic_path}")

    # Also save a simple code->description mapping for direct embedding
    simple_mapping = {}
    for ex in all_examples:
        if len(ex['code']) < 300:  # Only short examples
            simple_mapping[ex['code']] = generate_semantic_description(ex)

    simple_path = OUTPUT_DIR / "python_examples_simple.yaml"
    with open(simple_path, 'w', encoding='utf-8') as f:
        yaml.dump(simple_mapping, f, default_flow_style=False, allow_unicode=True)
    print(f"Simple mapping saved to: {simple_path}")


if __name__ == '__main__':
    main()

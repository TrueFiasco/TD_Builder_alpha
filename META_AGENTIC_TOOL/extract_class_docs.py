#!/usr/bin/env python3
"""
Extract Python class documentation from _Class.htm files.
Extracts: members, methods, descriptions, code examples.
"""

import re
import json
from pathlib import Path
from html.parser import HTMLParser
from collections import defaultdict

class ClassDocExtractor(HTMLParser):
    """Extract structured data from _Class.htm files."""

    def __init__(self):
        super().__init__()
        self.data = {
            'class_name': '',
            'inherits_from': '',
            'members': [],
            'methods': []
        }
        self.current_section = None
        self.current_item = None
        self.in_code = False
        self.in_blockquote = False
        self.text_buffer = []
        self.code_buffer = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == 'h1':
            self.current_section = 'title'
            self.text_buffer = []
        elif tag == 'h2':
            self.current_section = 'h2'
            self.text_buffer = []
        elif tag == 'code':
            self.in_code = True
            self.code_buffer = []
        elif tag == 'blockquote':
            self.in_blockquote = True
            self.text_buffer = []
        elif tag == 'div' and 'id' in attrs_dict:
            # New member/method definition
            self.current_item = {'name': attrs_dict['id'], 'description': '', 'signature': ''}

    def handle_endtag(self, tag):
        if tag == 'h1':
            text = ''.join(self.text_buffer).strip()
            if 'Class' in text:
                self.data['class_name'] = text.replace(' Class', '').strip()
            self.current_section = None
        elif tag == 'h2':
            text = ''.join(self.text_buffer).strip()
            if text == 'Members':
                self.current_section = 'members'
            elif text == 'Methods':
                self.current_section = 'methods'
            else:
                self.current_section = None
        elif tag == 'code':
            self.in_code = False
            code_text = ''.join(self.code_buffer).strip()
            if self.current_item and code_text:
                if not self.current_item['signature']:
                    self.current_item['signature'] = code_text
        elif tag == 'blockquote':
            self.in_blockquote = False
            desc = ''.join(self.text_buffer).strip()
            if self.current_item and desc:
                self.current_item['description'] = desc
                # Save the item
                if self.current_section == 'members':
                    self.data['members'].append(self.current_item.copy())
                elif self.current_section == 'methods':
                    self.data['methods'].append(self.current_item.copy())
                self.current_item = None

    def handle_data(self, data):
        if self.in_code:
            self.code_buffer.append(data)
        elif self.in_blockquote or self.current_section in ['title', 'h2']:
            self.text_buffer.append(data)


def extract_class_simple(htm_path: Path) -> dict:
    """Simple regex-based extraction - only class-specific members, not inherited."""
    content = htm_path.read_text(encoding='utf-8', errors='ignore')

    result = {
        'file': htm_path.name,
        'class_name': htm_path.stem.replace('_Class', ''),
        'family': '',
        'inherits': '',
        'callbacks': [],
        'members': [],
        'methods': [],
        'has_unique_members': False,
        'has_unique_methods': False
    }

    # Determine family
    name = result['class_name']
    for fam in ['CHOP', 'SOP', 'TOP', 'DAT', 'MAT', 'COMP', 'POP']:
        if fam in name:
            result['family'] = fam
            break

    # Extract inheritance
    inherit_match = re.search(r'inherits from the.*?<a[^>]*>([^<]+)</a>', content)
    if inherit_match:
        result['inherits'] = inherit_match.group(1).strip()

    # Find where the inherited class sections start (e.g., "CHOP Class", "OP Class")
    # We only want content BEFORE these sections
    inherited_section = re.search(r'<h1><span class="mw-headline" id="(CHOP|SOP|TOP|DAT|MAT|COMP|POP|OP)_Class">', content)
    if inherited_section:
        # Only search in content before inherited sections
        content_to_search = content[:inherited_section.start()]
    else:
        content_to_search = content

    # Check for "No operator specific members/methods"
    if 'No operator specific members' in content_to_search:
        result['has_unique_members'] = False
    else:
        result['has_unique_members'] = True

    if 'No operator specific methods' in content_to_search:
        result['has_unique_methods'] = False
    else:
        result['has_unique_methods'] = True

    # Extract callbacks section
    callback_match = re.search(r'<h2><span class="mw-headline" id="Callbacks">.*?<pre[^>]*>(.*?)</pre>', content_to_search, re.DOTALL)
    if callback_match:
        # Extract callback function names
        callback_code = clean_html(callback_match.group(1))
        func_names = re.findall(r'def\s+(\w+)\s*\(', callback_code)
        result['callbacks'] = func_names

    # Extract class-specific members and methods
    # Pattern handles both "→" entity and "→" character
    # Blockquote may contain multiple <p> tags and <ul> elements, so we capture just the first paragraph
    item_pattern = r'<div id="([^"]+)"[^>]*></div><p><code class="python">([^<]+)</code>\s*(?:→|→)\s*<code class="return">([^<]+)</code>[^<]*</p>\s*<blockquote><p>([^<]+)'

    for match in re.finditer(item_pattern, content_to_search, re.DOTALL):
        name = match.group(1)
        sig = match.group(2).strip()
        ret_type = match.group(3).strip()
        desc = clean_html(match.group(4))

        if not desc or len(desc) < 3:
            continue

        item = {
            'name': name,
            'signature': sig,
            'return_type': ret_type,
            'description': desc
        }

        # Methods have parentheses in signature
        if '(' in sig:
            result['methods'].append(item)
        else:
            result['members'].append(item)

    return result


def clean_html(text: str) -> str:
    """Remove HTML tags and clean text."""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def main():
    htm_dir = Path(r"C:\TD_Projects\Learn\OfflineHelp\https.docs.derivative.ca")
    output_dir = Path(r"C:\TD_Projects\META_AGENTIC_TOOL\extracted_facts")
    output_dir.mkdir(parents=True, exist_ok=True)

    class_files = sorted(htm_dir.glob("*_Class.htm"))
    print(f"Found {len(class_files)} _Class.htm files")

    # Group by family
    by_family = defaultdict(list)
    stats = {'total': 0, 'with_unique_members': 0, 'with_unique_methods': 0, 'with_callbacks': 0}

    for i, htm_path in enumerate(class_files, 1):
        if i % 100 == 0:
            print(f"  Progress: {i}/{len(class_files)}")

        try:
            data = extract_class_simple(htm_path)
            family = data['family'] or 'Other'
            by_family[family].append(data)

            stats['total'] += 1
            if data['has_unique_members'] and data['members']:
                stats['with_unique_members'] += 1
            if data['has_unique_methods'] and data['methods']:
                stats['with_unique_methods'] += 1
            if data['callbacks']:
                stats['with_callbacks'] += 1
        except Exception as e:
            print(f"  Error processing {htm_path.name}: {e}")

    # Save by family
    for family, classes in by_family.items():
        output_path = output_dir / f"{family}_classes.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                'family': family,
                'count': len(classes),
                'classes': classes
            }, f, indent=2)
        print(f"Saved {family}: {len(classes)} classes -> {output_path.name}")

    # Save combined
    all_classes = []
    for classes in by_family.values():
        all_classes.extend(classes)

    output_path = output_dir / "all_classes.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(all_classes),
            'stats': stats,
            'by_family': {k: len(v) for k, v in by_family.items()},
            'classes': all_classes
        }, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"Total classes: {stats['total']}")
    print(f"With unique members: {stats['with_unique_members']}")
    print(f"With unique methods: {stats['with_unique_methods']}")
    print(f"With callbacks: {stats['with_callbacks']}")
    print(f"\nBy family:")
    for fam, classes in sorted(by_family.items()):
        print(f"  {fam}: {len(classes)}")


if __name__ == '__main__':
    main()

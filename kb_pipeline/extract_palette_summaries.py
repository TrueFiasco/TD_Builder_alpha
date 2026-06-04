#!/usr/bin/env python3
"""
Extract palette component summaries from wiki HTML files.

Maps palette HTML documentation to palette semantic JSON files.
"""

import json
import re
from pathlib import Path
from typing import Dict, Optional
from html.parser import HTMLParser


class PaletteSummaryParser(HTMLParser):
    """Extract summary text from palette wiki HTML."""

    def __init__(self):
        super().__init__()
        self.in_summary = False
        self.in_summary_p = False
        self.summary_text = []
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        # Check for Summary heading
        if tag == "h2":
            for attr_name, attr_value in attrs:
                if attr_name == "id" and attr_value == "Summary":
                    self.in_summary = True
        # Check for paragraph after summary heading
        elif tag == "p" and self.in_summary:
            self.in_summary_p = True

    def handle_endtag(self, tag):
        if tag == "p" and self.in_summary_p:
            self.in_summary_p = False
            self.in_summary = False  # Stop after first paragraph
        self.current_tag = None

    def handle_data(self, data):
        if self.in_summary_p and self.current_tag == "p":
            # Clean up the text
            text = data.strip()
            if text and text not in ['edit', 'Summary']:
                self.summary_text.append(text)

    def get_summary(self) -> str:
        """Get extracted summary text."""
        # Join and clean up
        summary = " ".join(self.summary_text)
        # Remove multiple spaces
        summary = re.sub(r'\s+', ' ', summary)
        return summary.strip()


def extract_palette_summary(html_path: Path) -> Optional[str]:
    """Extract summary from a palette HTML file using regex."""
    if not html_path.exists():
        return None

    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # Find Summary section and extract first paragraph after it
        # Pattern: <span ... id="Summary">...</span> ... <p>summary text</p>
        summary_pattern = r'id="Summary".*?<p>(.*?)</p>'
        match = re.search(summary_pattern, html_content, re.DOTALL)

        if not match:
            return None

        # Extract and clean the summary
        summary_html = match.group(1)

        # Remove HTML tags
        summary_text = re.sub(r'<[^>]+>', ' ', summary_html)

        # Remove <br> tags
        summary_text = summary_text.replace('<br>', ' ')
        summary_text = summary_text.replace('<br/>', ' ')
        summary_text = summary_text.replace('<br />', ' ')

        # Remove extra whitespace
        summary_text = re.sub(r'\s+', ' ', summary_text)

        # Decode HTML entities
        summary_text = summary_text.replace('&amp;', '&')
        summary_text = summary_text.replace('&lt;', '<')
        summary_text = summary_text.replace('&gt;', '>')
        summary_text = summary_text.replace('&quot;', '"')
        summary_text = summary_text.replace('&#39;', "'")

        return summary_text.strip()
    except Exception as e:
        print(f"Error parsing {html_path.name}: {e}")
        return None


def map_palette_name_to_html(palette_name: str) -> str:
    """
    Map palette semantic JSON filename to wiki HTML filename.

    Examples:
        bloom_semantic.json -> Palette-bloom.htm
        3DScope_semantic.json -> Palette-3DScope.htm
    """
    # Remove _semantic suffix
    base_name = palette_name.replace('_semantic.json', '').replace('_semantic', '')

    # Special cases for naming
    # Most are lowercase in wiki but camelCase in semantic files
    # We'll try exact match first, then lowercase

    return f"Palette-{base_name}.htm"


def collect_palette_summaries(
    wiki_dir: Path,
    sem_dir: Path
) -> Dict[str, Dict]:
    """
    Collect all palette component summaries from wiki docs.

    Returns:
        Dict mapping palette_name -> {summary, html_file, sem_file}
    """
    summaries = {}

    if not wiki_dir.exists():
        print(f"Warning: Wiki dir not found: {wiki_dir}")
        return summaries

    if not sem_dir.exists():
        print(f"Warning: Semantic dir not found: {sem_dir}")
        return summaries

    # Iterate through semantic files to know which palettes exist
    for sem_path in sem_dir.glob("*_semantic.json"):
        palette_name = sem_path.stem.replace('_semantic', '')

        # Try to find corresponding HTML file
        html_filename = map_palette_name_to_html(sem_path.name)
        html_path = wiki_dir / html_filename

        # Try alternate capitalization if not found
        if not html_path.exists():
            # Try all lowercase
            html_filename_lower = f"Palette-{palette_name.lower()}.htm"
            html_path = wiki_dir / html_filename_lower

        # Extract summary if HTML exists
        summary = None
        if html_path.exists():
            summary = extract_palette_summary(html_path)

        summaries[palette_name] = {
            'summary': summary,
            'html_file': html_path.name if html_path.exists() else None,
            'sem_file': sem_path.name,
            'has_wiki_docs': html_path.exists(),
            'has_summary': bool(summary)
        }

    return summaries


def collect_palette_chunks(wiki_dir: Path, sem_dir: Path, enriched_index_path: Path = None) -> list:
    """
    Collect palette components as chunks for embedding.

    Args:
        wiki_dir: Path to wiki HTML files (for legacy summaries)
        sem_dir: Path to semantic JSON files (for legacy mode)
        enriched_index_path: Path to enriched_index.json (preferred, with operator lists)

    Returns:
        List of chunk dicts with id, text, meta
    """
    chunks = []

    # Try enriched index first (new format with operator lists and use-cases)
    if enriched_index_path and enriched_index_path.exists():
        return _collect_chunks_from_enriched_index(enriched_index_path, wiki_dir)

    # Fallback to legacy wiki-only extraction
    palette_summaries = collect_palette_summaries(wiki_dir, sem_dir)

    for palette_name, info in palette_summaries.items():
        summary = info['summary']

        if not summary:
            # Skip if no wiki summary available
            continue

        # Build chunk text
        text_parts = [
            f"Palette: {palette_name}",
            f"Description: {summary}"
        ]

        chunk_id = f"palette::{palette_name}"

        chunks.append({
            'id': chunk_id,
            'text': '\n'.join(text_parts),
            'chunk_type': 'palette_component',
            'parent_chunk': None,
            'meta': {
                'source': 'palette',
                'palette_name': palette_name,
                'wiki_file': info['html_file'],
                'tier': 1,  # Top-level palette component
                'chunk_type': 'palette_component'
            }
        })

    return chunks


def _collect_chunks_from_enriched_index(enriched_index_path: Path, wiki_dir: Path) -> list:
    """
    Collect palette chunks from enriched index (new format).

    Includes operator lists and use-cases for better semantic search.
    """
    chunks = []

    with open(enriched_index_path, 'r', encoding='utf-8') as f:
        index = json.load(f)

    palettes = index.get('palettes', {})
    print(f"  Loading {len(palettes)} palettes from enriched index...")

    for palette_name, info in palettes.items():
        # Try to get wiki summary
        wiki_summary = None
        html_filename = f"Palette-{palette_name}.htm"
        html_path = wiki_dir / html_filename
        if not html_path.exists():
            html_path = wiki_dir / f"Palette-{palette_name.lower()}.htm"
        if html_path.exists():
            wiki_summary = extract_palette_summary(html_path)

        # Get enriched data
        category = info.get('category', 'General')
        contained_ops = info.get('contained_operators', [])
        use_cases = info.get('use_cases', [])
        complexity = info.get('complexity', 'unknown')
        operator_count = info.get('operator_count', 0)

        # Build rich chunk text for better embedding matches
        text_parts = [f"Palette: {palette_name}"]

        if wiki_summary:
            text_parts.append(f"Description: {wiki_summary}")

        text_parts.append(f"Category: {category}")

        if contained_ops:
            # Include top operators for semantic matching
            ops_text = ', '.join(contained_ops[:20])
            text_parts.append(f"Contains operators: {ops_text}")

        if use_cases:
            text_parts.append(f"Use cases: {', '.join(use_cases)}")

        text_parts.append(f"Complexity: {complexity} ({operator_count} operators)")

        chunk_id = f"palette::{palette_name}"

        chunks.append({
            'id': chunk_id,
            'text': '\n'.join(text_parts),
            'chunk_type': 'palette_component',
            'parent_chunk': None,
            'meta': {
                'source': 'palette',
                'palette_name': palette_name,
                'category': category,
                'wiki_file': html_path.name if html_path.exists() else None,
                'tier': 1,
                'chunk_type': 'palette_component',
                'contained_operators': contained_ops[:10],  # Top 10 for metadata
                'use_cases': use_cases,
                'complexity': complexity,
                'operator_count': operator_count
            }
        })

    return chunks


if __name__ == '__main__':
    # Test the extraction - use local kb_pipeline data
    kb_root = Path(__file__).parent
    wiki_dir = kb_root / "data" / "palette_wiki"
    sem_dir = kb_root / "data" / "palette_semantic"

    print("Extracting palette summaries...")
    summaries = collect_palette_summaries(wiki_dir, sem_dir)

    print(f"\nFound {len(summaries)} palette components")

    # Show statistics
    with_wiki = sum(1 for info in summaries.values() if info['has_wiki_docs'])
    with_summary = sum(1 for info in summaries.values() if info['has_summary'])

    print(f"  With wiki docs: {with_wiki}")
    print(f"  With summary extracted: {with_summary}")

    # Show sample
    print("\nSample summaries:")
    for palette_name, info in list(summaries.items())[:5]:
        if info['summary']:
            print(f"\n{palette_name}:")
            print(f"  {info['summary'][:150]}...")

    # Generate chunks
    print("\n" + "="*80)
    chunks = collect_palette_chunks(wiki_dir, sem_dir)
    print(f"Generated {len(chunks)} palette chunks")

    # Save to JSON for inspection
    output = Path("C:/TD_Projects/kb_pipeline/palette_summaries.json")
    with open(output, 'w', encoding='utf-8') as f:
        json.dump({
            'summaries': summaries,
            'chunks': chunks
        }, f, indent=2)

    print(f"\nSaved to: {output}")

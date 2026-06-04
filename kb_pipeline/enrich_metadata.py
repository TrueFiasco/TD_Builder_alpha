#!/usr/bin/env python3
"""
Metadata Enrichment - Phase 4

Adds semantic tags, categories, and usage patterns to chunks for better search.
"""

import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Set

KB_ROOT = Path(__file__).parent
VECTOR_INDEX = KB_ROOT / "vector_db" / "vector_index.json"


class MetadataEnricher:
    """Enrich chunks with semantic metadata."""

    def __init__(self):
        # Predefined semantic categories
        self.categories = {
            'animation': ['speed', 'play', 'animate', 'keyframe', 'motion', 'timeline', 'sequence'],
            'rendering': ['render', 'material', 'light', 'shadow', 'texture', 'shader', 'geometry'],
            'effects': ['blur', 'glow', 'bloom', 'feedback', 'distort', 'filter', 'composite'],
            'particles': ['particle', 'emit', 'force', 'collision', 'trail', 'instance'],
            'audio': ['audio', 'sound', 'spectrum', 'fft', 'analyze', 'beat', 'music'],
            'video': ['movie', 'video', 'playback', 'frame', 'codec', 'stream'],
            'data': ['table', 'csv', 'json', 'xml', 'database', 'script', 'text'],
            'network': ['osc', 'midi', 'udp', 'tcp', 'websocket', 'dmx', 'artnet'],
            'geometry': ['point', 'polygon', 'mesh', 'surface', 'curve', 'transform', 'deform'],
            'color': ['color', 'rgb', 'hsv', 'level', 'correct', 'grade', 'lookup'],
            'ui': ['button', 'slider', 'panel', 'container', 'widget', 'interface'],
            'control': ['trigger', 'logic', 'switch', 'sequence', 'condition', 'state'],
            'camera': ['camera', 'view', 'perspective', 'lens', 'focal', 'viewport'],
            'noise': ['noise', 'random', 'pattern', 'procedural', 'perlin', 'fractal'],
        }

        # Operator family mappings
        self.family_difficulty = {
            'TOP': 'beginner',
            'CHOP': 'intermediate',
            'SOP': 'intermediate',
            'DAT': 'intermediate',
            'COMP': 'advanced',
            'POP': 'advanced',
            'MAT': 'intermediate'
        }

    def extract_semantic_tags(self, chunk: Dict) -> List[str]:
        """
        Extract semantic tags from chunk text and metadata.

        Args:
            chunk: Chunk dictionary

        Returns:
            List of semantic tags
        """
        tags = set()
        text = chunk.get('text', '').lower()
        meta = chunk.get('meta', {})

        # Category matching
        for category, keywords in self.categories.items():
            for keyword in keywords:
                if keyword in text:
                    tags.add(category)
                    break

        # Source-specific tags
        source = meta.get('source', '')
        if source:
            tags.add(f'source:{source}')

        # Operator family tags
        op_name = meta.get('operator_name', '')
        if op_name:
            # Extract family from operator name
            for family in ['TOP', 'CHOP', 'SOP', 'DAT', 'COMP', 'POP', 'MAT']:
                if family in op_name.upper():
                    tags.add(f'family:{family}')
                    break

        # Tier tags (for hierarchical chunks)
        tier = meta.get('tier')
        if tier:
            if tier == 1:
                tags.add('level:overview')
            elif tier == 2:
                tags.add('level:group')
            elif tier == 3:
                tags.add('level:detail')
            elif tier == 4:
                tags.add('level:example')

        # Curator summary tag
        if meta.get('has_curator_summary'):
            tags.add('quality:curated')

        return sorted(list(tags))

    def calculate_popularity_score(self, chunk: Dict, all_chunks: List[Dict]) -> float:
        """
        Calculate a popularity score based on various factors.

        Args:
            chunk: Chunk dictionary
            all_chunks: All chunks for context

        Returns:
            Popularity score (0.0-1.0)
        """
        score = 0.5  # Base score

        meta = chunk.get('meta', {})
        source = meta.get('source', '')

        # Boost for curated content
        if meta.get('has_curator_summary'):
            score += 0.2

        # Boost for overview chunks (tier 1)
        if meta.get('tier') == 1:
            score += 0.15

        # Boost for palette components (curated by Derivative)
        if source == 'palette':
            score += 0.1

        # Boost for real examples
        if meta.get('chunk_type') == 'real_example':
            score += 0.1

        # Normalize to 0-1 range
        return min(1.0, max(0.0, score))

    def enrich_chunk(self, chunk: Dict, all_chunks: List[Dict]) -> Dict:
        """
        Enrich a single chunk with metadata.

        Args:
            chunk: Chunk dictionary
            all_chunks: All chunks for context

        Returns:
            Enriched chunk
        """
        enriched = chunk.copy()
        meta = enriched.get('meta', {})

        # Add semantic tags
        tags = self.extract_semantic_tags(chunk)
        meta['semantic_tags'] = tags

        # Add popularity score
        popularity = self.calculate_popularity_score(chunk, all_chunks)
        meta['popularity_score'] = popularity

        # Add difficulty level
        op_name = meta.get('operator_name', '')
        if op_name:
            for family, difficulty in self.family_difficulty.items():
                if family in op_name.upper():
                    meta['difficulty_level'] = difficulty
                    break

        # Add use case categories (from semantic tags)
        use_cases = [tag for tag in tags if not tag.startswith(('source:', 'family:', 'level:', 'quality:'))]
        meta['use_case_categories'] = use_cases

        enriched['meta'] = meta
        return enriched

    def enrich_all_chunks(self):
        """Enrich all chunks in the vector index."""
        print("=" * 80)
        print("METADATA ENRICHMENT")
        print("=" * 80)

        # Load chunks
        print(f"\nLoading chunks from: {VECTOR_INDEX}")
        with open(VECTOR_INDEX, 'r', encoding='utf-8') as f:
            chunks = json.load(f)

        print(f"Total chunks: {len(chunks)}")

        # Enrich each chunk
        print("\nEnriching metadata...")
        enriched_chunks = []
        for chunk in chunks:
            enriched = self.enrich_chunk(chunk, chunks)
            enriched_chunks.append(enriched)

        # Analyze enrichment
        all_tags = []
        popularity_scores = []
        for chunk in enriched_chunks:
            meta = chunk.get('meta', {})
            all_tags.extend(meta.get('semantic_tags', []))
            popularity_scores.append(meta.get('popularity_score', 0.0))

        # Statistics
        tag_counts = Counter(all_tags)
        avg_popularity = sum(popularity_scores) / len(popularity_scores)

        print("\n" + "=" * 80)
        print("ENRICHMENT STATISTICS")
        print("=" * 80)
        print(f"\nTotal chunks enriched: {len(enriched_chunks)}")
        print(f"Average popularity score: {avg_popularity:.3f}")
        print(f"\nTop 10 semantic tags:")
        for tag, count in tag_counts.most_common(10):
            percentage = (count / len(enriched_chunks)) * 100
            print(f"  {tag}: {count} ({percentage:.1f}%)")

        # Save enriched chunks
        output_path = VECTOR_INDEX.parent / "vector_index_enriched.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(enriched_chunks, f, indent=2)

        print(f"\n[OK] Saved enriched chunks to: {output_path}")

        # Also update the main index
        backup_path = VECTOR_INDEX.parent / "vector_index_backup.json"
        VECTOR_INDEX.rename(backup_path)
        output_path.rename(VECTOR_INDEX)

        print(f"[OK] Backed up original to: {backup_path}")
        print(f"[OK] Updated main index: {VECTOR_INDEX}")

        return enriched_chunks


if __name__ == '__main__':
    enricher = MetadataEnricher()
    enriched_chunks = enricher.enrich_all_chunks()

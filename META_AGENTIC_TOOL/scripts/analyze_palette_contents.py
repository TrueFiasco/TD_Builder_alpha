"""
Palette Content Analyzer

Extracts semantic metadata from lossless palette JSON files:
- Operator types contained
- Use-case categories
- Complexity rating

Output: enriched_index.json with full searchable metadata
"""

import gzip
import json
from pathlib import Path
from collections import Counter
import re

# Use-case inference rules based on operator types and names
USE_CASE_RULES = {
    # Audio
    "audio": ["audio", "sound", "music", "beat", "spectrum", "fft", "analyze"],
    "midi": ["midi", "note", "velocity", "channel"],
    # Video
    "video": ["movie", "video", "playback", "frame"],
    "camera": ["camera", "kinect", "azure", "webcam", "capture"],
    # Visual Effects
    "particles": ["particle", "pop", "emit", "point"],
    "shader": ["glsl", "shader", "render", "material"],
    "image_filter": ["blur", "bloom", "edge", "filter", "composite", "level"],
    "generator": ["noise", "ramp", "pattern", "procedural", "fractal"],
    # UI
    "ui": ["button", "slider", "widget", "field", "menu", "list", "control"],
    # Mapping
    "mapping": ["project", "blend", "corner", "calibrat", "mapper"],
    # Data
    "data": ["table", "dat", "json", "xml", "text", "parse"],
    "network": ["osc", "tcp", "udp", "websocket", "ndi", "syphon"],
    # VR/AR
    "vr": ["vr", "quest", "hmd", "controller", "vive", "oculus"],
    # Integration
    "ableton": ["ableton", "live", "clip", "track"],
    "bitwig": ["bitwig"],
}

# Complexity thresholds
COMPLEXITY_THRESHOLDS = {
    "simple": 20,       # <= 20 operators
    "intermediate": 100, # <= 100 operators
    "advanced": 500,    # <= 500 operators
    "complex": float('inf')  # > 500 operators
}


def extract_operator_types(operators: dict) -> list[str]:
    """Extract unique operator type names from operators dict."""
    op_types = set()
    for op_path, op_data in operators.items():
        if isinstance(op_data, dict):
            op_type = op_data.get('op_type', '')
            if ':' in op_type:
                # Extract base type (e.g., "CHOP:noise" -> "noiseCHOP")
                family, name = op_type.split(':', 1)
                op_types.add(f"{name}{family}")
            elif op_type:
                op_types.add(op_type)
    return sorted(list(op_types))


def infer_use_cases(palette_name: str, category: str, operator_types: list[str]) -> list[str]:
    """Infer use-cases from palette name, category, and operator types."""
    use_cases = set()

    # Combine all text to search
    search_text = f"{palette_name} {category} {' '.join(operator_types)}".lower()

    for use_case, keywords in USE_CASE_RULES.items():
        for keyword in keywords:
            if keyword in search_text:
                use_cases.add(use_case)
                break

    # Category-based defaults
    category_map = {
        "Generators": "generator",
        "ImageFilters": "image_filter",
        "Mapping": "mapping",
        "POPs": "particles",
        "UI": "ui",
        "Tools": "utility",
        "Techniques": "technique",
        "TDVR": "vr",
        "TDAbleton": "ableton",
        "TDBitwig": "bitwig",
        "WebRTC": "network",
        "Vive": "vr",
    }
    if category in category_map:
        use_cases.add(category_map[category])

    return sorted(list(use_cases)) if use_cases else ["general"]


def calculate_complexity(operator_count: int) -> str:
    """Calculate complexity rating based on operator count."""
    for level, threshold in COMPLEXITY_THRESHOLDS.items():
        if operator_count <= threshold:
            return level
    return "complex"


def analyze_palette(gz_path: Path, base_info: dict) -> dict:
    """Analyze a single palette file and return enriched metadata."""
    try:
        with gzip.open(gz_path, 'rt', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  Error reading {gz_path.name}: {e}")
        return base_info

    operators = data.get('operators', {})
    operator_types = extract_operator_types(operators)

    # Build enriched entry
    enriched = {
        **base_info,
        "contained_operators": operator_types[:50],  # Limit to top 50 unique types
        "use_cases": infer_use_cases(
            base_info.get('name', gz_path.stem),
            base_info.get('category', ''),
            operator_types
        ),
        "complexity": calculate_complexity(base_info.get('operator_count', 0)),
        "unique_operator_types": len(operator_types),
    }

    return enriched


def main():
    """Main entry point."""
    data_dir = Path(__file__).parent.parent / "data" / "palette_lossless"
    index_path = data_dir / "index.json"
    output_path = data_dir / "enriched_index.json"

    # Load existing index
    if not index_path.exists():
        print(f"Error: index.json not found at {index_path}")
        return

    with open(index_path, 'r', encoding='utf-8') as f:
        index = json.load(f)

    palettes = index.get('palettes', {})
    print(f"Analyzing {len(palettes)} palettes...")

    enriched_palettes = {}

    for name, info in palettes.items():
        gz_file = data_dir / info.get('file', f"{name}.json.gz")
        if not gz_file.exists():
            print(f"  Warning: {gz_file.name} not found")
            enriched_palettes[name] = {**info, "name": name}
            continue

        enriched = analyze_palette(gz_file, {"name": name, **info})
        enriched_palettes[name] = enriched

        # Progress indicator
        if len(enriched_palettes) % 50 == 0:
            print(f"  Processed {len(enriched_palettes)}/{len(palettes)}...")

    # Build enriched index
    enriched_index = {
        "version": "2.0",
        "generated": index.get('generated'),
        "count": len(enriched_palettes),
        "format": "enriched_lossless",
        "palettes": enriched_palettes
    }

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(enriched_index, f, indent=2)

    print(f"\nWrote enriched index to {output_path}")
    print(f"  Total palettes: {len(enriched_palettes)}")

    # Stats
    use_case_counts = Counter()
    for p in enriched_palettes.values():
        for uc in p.get('use_cases', []):
            use_case_counts[uc] += 1

    print("\nUse-case distribution:")
    for uc, count in use_case_counts.most_common(15):
        print(f"  {uc}: {count}")


if __name__ == "__main__":
    main()

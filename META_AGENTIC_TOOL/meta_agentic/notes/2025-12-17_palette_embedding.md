# Palette Component Embedding - TODO for 2025-12-18

## Problem
- `loadTox()` creates nested wrapper containers
- Palette TOXes have showcase structure that adds extra nesting
- Need to embed palette components directly in builder output

## Available Data (Verified)

### Lossless JSON - FULL STRUCTURE
```
C:\TD_Projects\kb_pipeline\data\palette_semantic\audioAnalysis_lossless.json
```
- **1218 operators** with: path, op_type, tile_pos, parameters, children, parent
- **416 connections** with: from, to, to_input
- **3088 files** in toc_order
- Everything needed to rebuild the component

Example operator structure:
```json
{
  "name": "audioAnalysis",
  "path": "/audioAnalysis",
  "op_type": "COMP:base",
  "tile_pos": [475, -50, 162, 130],
  "parameters": {...},
  "children": ["help", "icon", "audioAnalysis"],
  "inputs": {}
}
```

### Palette Summaries
```
C:\TD_Projects\kb_pipeline\palette_summaries.json
```
- **264 components** total
- **121 with LLM summaries**
- **133 with wiki docs**

audioAnalysis summary: "A component to analyze an input audio waveform for its properties such as Low-, Mid-, High-Level, Kick and Snare detection, Rythm, Spectral Centroid as well as Slow- and Fast- Spectral Density."

### Wiki Documentation
```
C:\TD_Projects\kb_pipeline\data\palette_wiki\Palette-audioAnalysis.htm
```

### Expanded TOX Directory
```
C:\TD_Projects\Learn\Palette\Tools\audioAnalysis.tox.dir
```

## TODO
1. Check palette component summaries in kb_pipeline data
2. Review embeddings for palette components
3. Build approach: copy expanded .tox.dir files directly into builder output
4. Test embedding audioAnalysis directly (no runtime loadTox)

## Approach

### Primary: Build from lossless JSON
The builder should:
1. Read `{component}_lossless.json` from `C:\TD_Projects\kb_pipeline\data\palette_semantic\`
2. Parse operator structure, connections, parameters
3. Build each operator with:
   - Exact connections and wiring
   - Correct comp type (base, container, geo, etc.)
   - Same inputs/outputs
4. Generate .n, .parm, .panel files for each operator

```python
# Example approach
def build_from_lossless(json_path, output_dir, prefix):
    with open(json_path) as f:
        data = json.load(f)

    for op_data in data['operators']:
        # Create .n file with correct type
        write_op_n(output_dir, op_data['name'], op_data['type'],
                   op_data['inputs'], op_data['position'])
        # Create .parm file with parameters
        write_op_parm(output_dir, op_data['name'], op_data['parameters'])
```

### Fallback: Runtime loadTox (if reliable import achieved)
Only use `loadTox()` if we solve the wrapper nesting issue.

### Key insight
Building from JSON gives us full control over structure - no wrapper containers, exact comp types, precise wiring.

## ISSUE DISCOVERED (2025-12-17)

The `*_lossless.json` files are **NOT truly lossless**!

Missing from .n files:
- `exports { ... }` blocks
- `dict` lines (hex-encoded instance data)

Example - original add.n has:
```
COMP:slider
tile 654 73 160 155
flags =  viewer 1 render on parlanguage 0
exports
{
./script_export
}
color 0.55 0.55 0.55
dict 8004954B000000...
end
```

But JSON only captures: op_type, tile_pos, flags, color, parameters

### Fix Options
1. **Update kb_pipeline extractor** to capture full .n file content (exports, dict, etc.)
2. **Copy raw files** from expanded .tox.dir instead of rebuilding from JSON ✓ WORKING
3. **Hybrid approach** - use JSON for structure, copy raw .n files for content

## SOLUTION IMPLEMENTED (2025-12-17)

Created `build_from_expanded.py` that:
1. Copies raw files from `C:\TD_Projects\Learn\Palette\Tools\{component}.tox.dir`
2. Skips wrapper levels (default 2 for palette: `/comp/comp/content` -> `/content`)
3. Preserves all exports, dict, and binary content exactly as TD exported

**Result**: `audioAnalysis_unwrapped.tox` - 136KB, 3081 files
- exports and dict sections preserved in .n files
- Binary .text files copied verbatim
- Ready for TD testing

### Usage
```python
from build_from_expanded import build_from_expanded
build_from_expanded("audioAnalysis", "audioAnalysis_unwrapped", skip_levels=2)
```

## EXPERTISE UPDATED (2025-12-17)

Added to expertise files:
1. **palette_expertise.yaml** - `embedded_structure` section with full working approach
2. **td_file_formats.yaml** - `PER_OPERATOR_ORDER_CRITICAL` section

Key discoveries documented:
- Lossless JSON is NOT truly lossless (missing exports, dict)
- TOC file order is CRITICAL: .n → .cparm → .parm → .panel
- Alphabetical sort breaks custom parameters
- Working approach: copy raw files from expanded .tox.dir

## VALIDATED COMPONENTS

| Component | Files | Size | Status |
|-----------|-------|------|--------|
| audioAnalysis | 3081 | 137KB | Working (2 transient errors in snare) |
| blendModes | 2236 | 41KB | Built, pending TD test |

# .tox/.toe File Format Research Guide

**Practical guide for reverse engineering TouchDesigner file format**

---

## Quick Start: Examining a .tox File

### Step 1: Extract the Archive

.tox and .toe files are ZIP archives. Extract them:

```bash
# Windows
mkdir extracted_tox
cd extracted_tox
tar -xf path/to/component.tox

# Or rename to .zip and extract
cp component.tox component.zip
# Extract with Windows Explorer or 7-Zip
```

### Step 2: Examine the Structure

Typical structure you'll find:

```
component.tox (extracted)/
├── component.toc          # Main table of contents
├── component1/            # First component directory
│   ├── component1.toc
│   ├── nodeName1/
│   │   └── nodeName1.toc
│   └── nodeName2/
│       └── nodeName2.toc
├── component.png          # Thumbnail (optional)
└── component.python       # Python code (if any)
```

### Step 3: Analyze .toc Files

.toc files contain the core structure. They appear to be in a custom format.

**Example structure to look for:**
- Operator definitions
- Parameter values
- Connection information
- Parent-child relationships
- Position/layout data

---

## Research Tasks

### Task 1: Extract All Palette .tox Files

Use Python to batch extract all palette components:

```python
import zipfile
from pathlib import Path

PALETTE_DIR = Path("C:/TD_Projects/kb_pipeline/data/palette_semantic")
OUTPUT_DIR = Path("C:/TD_Projects/tox_analysis/extracted")

# Find all .tox files referenced in semantic JSONs
for json_file in PALETTE_DIR.glob("*.json"):
    # Parse JSON to find .tox file path
    # Extract to OUTPUT_DIR
    # Document structure
    pass
```

### Task 2: Parse .toc File Format

**Goal:** Understand the .toc file structure

**Method:**
1. Extract several simple palette components
2. Compare .toc files side by side
3. Identify patterns:
   - Header/version information
   - Operator blocks
   - Parameter blocks
   - Connection blocks
   - Metadata blocks

**Questions to answer:**
- Is it binary or text?
- Is it XML, JSON, or custom format?
- How are operators identified (name, ID, type)?
- How are parameters stored (key-value, structured)?
- How are connections represented (indices, paths)?

### Task 3: Map Operator Types

**Goal:** Create complete list of all operator types found in palette

**Method:**
```python
import json

operator_types = set()

for toc_file in Path("C:/TD_Projects/tox_analysis/extracted").rglob("*.toc"):
    # Parse .toc file
    # Extract operator types
    # Add to set
    pass

# Cross-reference with knowledge base
kb_operators = json.load(open("C:/TD_Projects/kb_pipeline/data/wiki_docs/td_universal_parsed.json"))

print(f"Found in palette: {len(operator_types)}")
print(f"Documented in KB: {len(kb_operators)}")
print(f"Missing from KB: {operator_types - set(kb_operators.keys())}")
```

### Task 4: Analyze Parameter Serialization

**Goal:** Understand how each parameter type is stored

**Method:**
1. Find operators with known parameters in palette
2. Check KB for parameter schema
3. Compare .toc representation

**Example:**
```python
# From KB: moviefileinTOP has parameter "file" (str)
# Find in .toc: How is string parameter stored?
# From KB: noiseTOP has parameter "amplitude" (float)
# Find in .toc: How is float parameter stored?
# From KB: mathCHOP has parameter "combine" (menu)
# Find in .toc: How is menu parameter stored?
```

**Parameter types to document:**
- `int` - Integer values
- `float` - Floating point values
- `str` - String values
- `toggle` - Boolean values
- `menu` - Enumeration (dropdown)
- `pulse` - Button/trigger
- `python` - Python code
- `xyz` - 3D vector
- `rgba` - Color
- `wh` - Width/Height
- `uv` - UV coordinates

### Task 5: Connection Format

**Goal:** Understand wire/connection representation

**Method:**
1. Find palette component with known connections
2. Identify connection data in .toc
3. Document format

**Questions:**
- How is source operator referenced?
- How is target operator referenced?
- How is output index stored?
- How is input index stored?
- How are multi-input connections handled?

### Task 6: Hierarchy Analysis

**Goal:** Understand COMP nesting rules

**Method:**
1. Find palette component with nested COMPs
2. Trace parent-child relationships in .toc
3. Document hierarchy representation

**Questions:**
- How are parent-child links stored?
- How are absolute vs. relative paths used?
- What's the root level structure?
- How deep can nesting go?

---

## Analysis Tools

### Tool 1: .toc Parser

```python
class TocParser:
    """Parse .toc files to extract structure."""

    def __init__(self, toc_path: str):
        self.path = Path(toc_path)
        self.data = None

    def parse(self):
        """Parse .toc file."""
        with open(self.path, 'rb') as f:
            # Detect format (binary vs. text)
            header = f.read(100)

            if header.startswith(b'<?xml'):
                self.data = self._parse_xml(f)
            elif header.startswith(b'{'):
                self.data = self._parse_json(f)
            else:
                self.data = self._parse_custom(f)

    def extract_operators(self):
        """Extract all operator definitions."""
        pass

    def extract_parameters(self):
        """Extract all parameters."""
        pass

    def extract_connections(self):
        """Extract all connections."""
        pass

    def to_json(self):
        """Convert to standardized JSON format."""
        pass
```

### Tool 2: Structure Comparator

```python
def compare_toc_files(file1: Path, file2: Path):
    """Compare two .toc files to find differences."""

    parser1 = TocParser(file1)
    parser2 = TocParser(file2)

    parser1.parse()
    parser2.parse()

    # Compare structures
    diff = {
        'operators': compare_operators(parser1, parser2),
        'parameters': compare_parameters(parser1, parser2),
        'connections': compare_connections(parser1, parser2)
    }

    return diff
```

### Tool 3: Validation Pattern Extractor

```python
def extract_validation_patterns():
    """
    Extract validation patterns from all palette components.

    Finds:
    - Common parameter value patterns
    - Connection type patterns
    - Naming conventions
    - Layout patterns
    """

    patterns = {
        'naming': {},
        'parameters': {},
        'connections': {},
        'layout': {}
    }

    for toc_file in Path("extracted").rglob("*.toc"):
        parser = TocParser(toc_file)
        parser.parse()

        # Extract patterns
        # ...

    return patterns
```

---

## Expected Findings

### Operator Definition Format

Likely contains:
```
{
  "type": "noiseTOP",
  "name": "noise1",
  "id": "1234",
  "parent": "/project1",
  "position": [100, 200],
  "parameters": { ... },
  "viewer": { "active": true }
}
```

### Parameter Format

Likely varies by type:
```python
# Float parameter
{"name": "amplitude", "value": 1.5, "mode": "constant"}

# Menu parameter
{"name": "noisetype", "value": "perlin", "index": 0}

# Expression parameter
{"name": "speed", "expression": "absTime.seconds", "mode": "expression"}

# Vector parameter
{"name": "translate", "value": [0.0, 0.0, 0.0]}
```

### Connection Format

Likely structured:
```python
{
  "source": "/project1/noise1",
  "source_output": 0,
  "target": "/project1/render1",
  "target_input": 0
}
```

---

## Pattern Documentation Template

For each pattern discovered, document:

```markdown
## Pattern: [Name]

**Category:** Operator | Parameter | Connection | Layout

**Description:**
[What this pattern represents]

**Format:**
[Exact format found in .toc]

**Examples:**
[2-3 examples from different palette components]

**Validation Rules:**
- [Rule 1]
- [Rule 2]
- [Rule 3]

**Edge Cases:**
- [Edge case 1]
- [Edge case 2]

**Version Notes:**
[Any version-specific variations]
```

---

## Research Deliverables

### 1. Format Specification Document

**Contents:**
- Complete .toc file format specification
- Field-by-field documentation
- Type definitions
- Example structures

**Format:** Markdown with code examples

### 2. Operator Type Catalog

**Contents:**
- All operator types found
- Parameter schemas for each
- Valid parent types
- Connection rules

**Format:** JSON schema

### 3. Validation Rules Database

**Contents:**
- All validation rules discovered
- Categorized by type
- Priority (error vs. warning)
- Test cases for each rule

**Format:** Structured JSON

### 4. Reference Implementation

**Contents:**
- Parser for .toc files
- Converter to standardized JSON
- Validator against rules
- Builder from JSON

**Format:** Python code

### 5. Test Dataset

**Contents:**
- Extracted palette components
- Annotated examples
- Edge cases
- Invalid examples (for negative testing)

**Format:** Directory structure with docs

---

## Common Pitfalls to Avoid

### ❌ Don't:
- Assume format is documented anywhere
- Expect consistency across all files
- Ignore version differences
- Parse without validation
- Generate files without testing in actual TD

### ✅ Do:
- Compare multiple examples
- Document every variation found
- Test with real TouchDesigner
- Keep version compatibility in mind
- Build incrementally (simple → complex)

---

## Incremental Testing Strategy

### Phase 1: Minimal Valid File
Create the simplest possible valid .toe:
- Single project1
- One operator (e.g., noiseTOP)
- No connections
- Default parameters

**Goal:** Understand minimum requirements

### Phase 2: Basic Network
Add complexity:
- Two operators
- One connection
- Modified parameters

**Goal:** Understand connections and parameters

### Phase 3: Nested Structure
Add hierarchy:
- Container COMP
- Child operators
- Connections across levels

**Goal:** Understand hierarchy and scoping

### Phase 4: Complex Features
Add advanced features:
- Multiple networks
- Feedback loops
- External resources
- Python code

**Goal:** Understand advanced features

### Phase 5: Real-World Validation
Test with:
- All 121 palette components
- Generated projects
- Edge cases

**Goal:** Validate completeness

---

## Quick Reference: File Locations

```bash
# Palette semantic JSONs (metadata)
C:\TD_Projects\kb_pipeline\data\palette_semantic\

# Palette wiki docs (descriptions)
C:\TD_Projects\kb_pipeline\data\palette_wiki\

# Operator documentation
C:\TD_Projects\kb_pipeline\data\wiki_docs\td_universal_parsed.json

# Knowledge graph
C:\TD_Projects\kb_pipeline\graph\td_knowledge_graph_simple.json

# Output directory for analysis
C:\TD_Projects\tox_analysis\
├── extracted\      # Extracted .tox files
├── parsed\         # Parsed .toc data
├── patterns\       # Documented patterns
└── tests\          # Test cases
```

---

## Next Steps After Research

1. **Compile findings** into formal specification
2. **Create JSON schema** based on findings
3. **Implement parser** to read existing files
4. **Implement validator** against discovered rules
5. **Implement builder** to create new files
6. **Test** with real TouchDesigner

---

**Remember:** The goal is not just to understand the format, but to create a **100% reliable builder** that never generates invalid files.

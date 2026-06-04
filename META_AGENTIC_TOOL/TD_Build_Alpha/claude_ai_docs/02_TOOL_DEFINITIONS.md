# Tool Definitions Per Agent

This document describes what tools each agent has access to and their descriptions.

## Execution Modes

### Mode 1: Subagent Execution (Current Primary Mode)

When running via Claude Code, experts are spawned as Task agents. Each Task agent has access to:

```
Tools Available to Task Agents:
- Read: Read files from the filesystem
- Write: Write files to the filesystem
- Edit: Edit existing files
- Glob: Find files by pattern
- Grep: Search file contents
- Bash: Execute shell commands
- WebFetch: Fetch web content
- WebSearch: Search the web
```

The orchestrator (Claude Code main session) spawns experts as needed and collects their outputs.

### Mode 2: API Execution (LLMExecutor)

When running via direct API calls (AnthropicExecutor), experts are pure LLM calls with no tool access - they receive a prompt and return structured YAML.

---

## Expert Tool Access Matrix

| Expert | KB Read | File Read | File Write | Shell | Web |
|--------|---------|-----------|------------|-------|-----|
| creative_expert | ✅ | ✅ | ❌ | ❌ | ❌ |
| cg_expert | ✅ | ✅ | ❌ | ❌ | ❌ |
| td_designer | ✅ | ✅ | ❌ | ❌ | ❌ |
| td_glsl_expert | ✅ | ✅ | ❌ | ❌ | ❌ |
| td_python_expert | ✅ | ✅ | ❌ | ❌ | ❌ |
| critic | ✅ | ✅ | ❌ | ❌ | ❌ |
| network_builder | ✅ | ✅ | ✅ | ✅ | ❌ |
| summary_generator | ✅ | ✅ | ✅ | ❌ | ❌ |

**Note**: Only `network_builder` has write access because it generates actual TOX/TOE files.

---

## KB Query Tools

All experts can query the Knowledge Base via Python functions:

### KnowledgeBase Class Methods

```python
class KnowledgeBase:
    def load_expertise(self, file_name: str) -> dict
        """Load and parse a YAML expertise file."""

    def query_operators(self, filter_params: dict) -> list[dict]
        """Query operators with filters: family, name, purpose_contains."""

    def query_patterns(self, category: str) -> list[dict]
        """Query network patterns by category."""

    def query_glsl(self, shader_type: str) -> dict
        """Query GLSL expertise by shader type."""

    def query_palette(self, component_type: str) -> list[dict]
        """Query palette components."""

    def query_palette_catalog(
        self,
        keywords: list[str],
        category: str = None,
        max_results: int = 15
    ) -> list[dict]
        """Semantic search across 278 palette components."""

    def validate_operator(self, op_type: str, op_name: str) -> bool
        """Anti-hallucination: verify operator exists."""

    def validate_parameter(self, op_type: str, op_name: str, param: str) -> bool
        """Anti-hallucination: verify parameter exists."""

    def validate_network_design(self, network_json: dict) -> ValidationResult
        """Validate entire network design for hallucinations."""
```

### Module-Level Convenience Functions

```python
# Available without instantiating KnowledgeBase
from meta_agentic.execution.kb_query import (
    get_default_kb,
    get_operators_for_family,
    get_patterns_for_category,
    validate_operator,
    validate_parameter
)
```

---

## Blackboard Access Tools

Each expert reads/writes to specific blackboard sections via the Blackboard class:

```python
class Blackboard:
    def read(self, section_id: SectionID) -> dict
        """Read current content from a section."""

    def write(self, section_id: SectionID, content: dict, author: str, score: float = None)
        """Write new content to a section."""

    def lock(self, section_id: SectionID, reason: str)
        """Lock section to prevent further writes."""

    def add_blocking_issue(self, section_id, severity, classification, description)
        """Flag a blocking issue."""

    def get_context_for_expert(self, expert_id: str) -> dict
        """Get all relevant sections for an expert."""
```

### Section Access per Expert

```python
access_map = {
    "creative_expert": [REQUIREMENTS],
    "cg_expert": [REQUIREMENTS, CREATIVE_VISION],
    "td_designer": [REQUIREMENTS, CREATIVE_VISION, TECHNICAL_APPROACH, AVAILABLE_RESOURCES],
    "td_glsl_expert": [TECHNICAL_APPROACH, NETWORK_DESIGN],
    "td_python_expert": [TECHNICAL_APPROACH, NETWORK_DESIGN],
    "network_builder": [NETWORK_DESIGN],
    "summary_generator": [NETWORK_DESIGN, BUILD_ARTIFACTS],
    "critic": [REQUIREMENTS, CREATIVE_VISION, TECHNICAL_APPROACH, AVAILABLE_RESOURCES, NETWORK_DESIGN],
    "creative_orchestrator": [ALL_SECTIONS],
}
```

---

## Builder Tools

The `network_builder` expert has access to additional build tools:

### ToeBuilder Class

```python
from tox_builder.builder_v4 import ToeBuilder

builder = ToeBuilder(
    project_name="my_project",
    output_dir=Path("./output")
)

# Add containers
builder.add_container("main", None, {"tx": 0, "ty": 0})

# Add operators
builder.add_operator(
    container="main",
    op_name="noise1",
    op_type="noiseTOP",
    params={"type": "sparse", "amp": 1.0}
)

# Add connections
builder.add_connection("noise1", "comp1", input_index=0)

# Build the file
toe_path = builder.build()  # Returns Path to .toe file
```

### Palette Embedding

```python
from build_from_expanded import copy_expanded_tox_contents

# Embed a palette component
copy_expanded_tox_contents(
    source_expanded_dir=Path("audioAnalysis.tox.dir"),
    dest_container_path=Path("project/audio"),
    skip_wrapper_levels=2  # Critical for palette components
)
```

---

## Tool Descriptions Seen by Agents

When spawned as Task agents, experts see standard Claude Code tool descriptions:

### Read Tool
```
Reads a file from the local filesystem. You can access any file directly.
The file_path parameter must be an absolute path.
```

### Write Tool
```
Writes a file to the local filesystem.
This tool will overwrite existing files.
You MUST use the Read tool first to read existing file contents.
```

### Glob Tool
```
Fast file pattern matching tool.
Supports glob patterns like "**/*.py" or "src/**/*.yaml"
Returns matching file paths sorted by modification time.
```

### Grep Tool
```
Powerful search tool built on ripgrep.
Supports full regex syntax.
Output modes: content, files_with_matches, count.
```

---

## Validation Tools

### ValidationResult Class

```python
@dataclass
class ValidationResult:
    valid: bool
    missing: list[str]      # Missing operators
    errors: list[str]       # Blocking errors
    warnings: list[str]     # Non-blocking warnings
```

### Usage

```python
kb = get_default_kb()

# Validate a network design
result = kb.validate_network_design(network_json)
if not result.valid:
    print(f"Errors: {result.errors}")
    print(f"Missing operators: {result.missing}")
```

# TD-MCP: TouchDesigner Knowledge Base & Builder

**Alpha Release v0.1.0**

MCP (Model Context Protocol) server providing AI-powered TouchDesigner assistance. Enables Claude Desktop to search documentation, validate networks, and build .toe files.

## Quick Start

### 1. Install Dependencies

```bash
cd C:\TD_Projects\td-mcp
pip install -r requirements.txt
```

Note: First run downloads SentenceTransformer model (~1.5GB).

### 2. Configure API Key

```bash
copy .env.template .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### 3. Configure Claude Desktop

Copy `config/claude_desktop_config.json` to:
```
%APPDATA%\Claude\claude_desktop_config.json
```

Or merge with existing config:
```json
{
  "mcpServers": {
    "td-mcp": {
      "command": "python",
      "args": ["C:\\TD_Projects\\td-mcp\\server.py"],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### 4. Restart Claude Desktop

The TD-MCP tools will be available in Claude Desktop.

## Available Tools

### Knowledge Base Tools

| Tool | Description |
|------|-------------|
| `hybrid_search` | Semantic search across 670 operators + knowledge graph |
| `get_operator_info` | Get complete info for a specific operator |
| `query_graph` | Query knowledge graph (params, related, family) |
| `list_pop_operators` | List all POP (particle) operators |

### Example Discovery Tools

| Tool | Description |
|------|-------------|
| `find_operator_examples` | Find real examples using a specific operator |
| `find_operator_combination` | Find examples with specific operator combos |
| `find_parameter_usage` | See how parameters are used in practice |
| `find_similar_networks` | Find networks with similar patterns |
| `get_network_patterns` | Get common operator chain patterns |

### Builder Tools

| Tool | Description |
|------|-------------|
| `td_validate` | Validate network JSON (5-stage pipeline) |
| `td_convert` | Convert between format layers |
| `td_build_network` | Generate .toe/.tox files |

### Agent Tools

| Tool | Description |
|------|-------------|
| `spawn_engineer` | Spawn specialized extraction agents |

#### Engineer Types

- **snippet_extractor** - Extract knowledge from .tox files
- **workflow_analyzer** - Find operator chain patterns in .toe files
- **concept_generator** - Generate semantic taxonomy from operators
- **knowledge_validator** - Validate extracted knowledge
- **data_source_auditor** - Audit data sources and plan extraction

## Directory Structure

```
td-mcp/
├── server.py                    # MCP entry point
├── requirements.txt             # Python dependencies
├── .env.template                # API key template
│
├── knowledge_base/              # Search & retrieval
│   ├── retrieval.py             # Hybrid search engine
│   ├── graph.py                 # Knowledge graph queries
│   ├── cache/                   # Query caching
│   ├── data/
│   │   ├── operators.json       # 670 operator specs (31MB)
│   │   ├── palette_summaries.json
│   │   └── snippets/            # Semantic snippets
│   ├── vector_db/               # Embeddings (~50MB)
│   └── graph/                   # Knowledge graph (5MB)
│
├── builder/                     # Network construction
│   ├── models.py                # Data models
│   ├── registry.py              # Operator registry
│   └── translation/             # TD format conversion
│       ├── operator_mappings.py
│       ├── parameter_expansion.py
│       └── expression_detector.py
│
├── mcp/
│   └── schemas/                 # JSON schemas
│
├── agents/                      # Engineer skill definitions
│   ├── snippet_extractor.md
│   ├── workflow_analyzer.md
│   ├── concept_generator.md
│   ├── knowledge_validator.md
│   └── data_source_auditor.md
│
└── config/
    └── claude_desktop_config.json
```

## Data Sources

| Source | Size | Contents |
|--------|------|----------|
| operators.json | 31MB | 670 operator specifications |
| vector_db/ | ~50MB | Semantic embeddings |
| knowledge_graph.json | 4.8MB | 16,814 nodes, 18,084 edges |
| snippets/semantic/ | 5.5MB | 180 operator example files |
| palette_summaries.json | 152KB | 278 palette components |

## Example Usage in Claude Desktop

```
"How do I create audio-reactive visuals in TouchDesigner?"

"What operators work well with the Noise CHOP?"

"Show me examples of Filter CHOP parameter usage"

"Validate this network: {operators: [{name: 'noise1', family: 'CHOP', type: 'noise'}]}"
```

## Requirements

- Python 3.10+
- TouchDesigner (for .toe building)
- Claude Desktop
- Anthropic API key (for agent features)

## Known Limitations

- First startup takes ~30s to load embeddings
- .toe building requires TouchDesigner's toecollapse.exe
- Agent spawning requires ANTHROPIC_API_KEY

## License

MIT License

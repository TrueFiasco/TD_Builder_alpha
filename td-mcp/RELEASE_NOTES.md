# TD-MCP Alpha Release Notes

**Version:** 0.1.0-alpha
**Date:** 2025-12-20

## Overview

First alpha release of TD-MCP - a Model Context Protocol server providing AI-powered TouchDesigner assistance through Claude Desktop.

## What's Included

### 13 MCP Tools

**Knowledge Base (5 tools)**
- `hybrid_search` - Semantic + graph-enhanced search
- `get_operator_info` - Complete operator specifications
- `query_graph` - Knowledge graph traversal
- `list_pop_operators` - POP family listing

**Example Discovery (5 tools)**
- `find_operator_examples` - Real usage examples
- `find_operator_combination` - Multi-operator patterns
- `find_parameter_usage` - Parameter value examples
- `find_similar_networks` - Pattern matching
- `get_network_patterns` - Common chains

**Builder (3 tools)**
- `td_validate` - 5-stage validation pipeline
- `td_convert` - Format layer conversion
- `td_build_network` - .toe/.tox generation

### 5 Specialized Agents

Engineer agents for knowledge extraction:
- `snippet_extractor` - Extract from .tox files
- `workflow_analyzer` - Analyze .toe patterns
- `concept_generator` - Build semantic taxonomy
- `knowledge_validator` - Validate against docs
- `data_source_auditor` - Plan extraction strategy

### Knowledge Base

- **670 operators** with full parameter specs
- **16,814 nodes** / **18,084 edges** in knowledge graph
- **20,477 vector chunks** for semantic search
- **180 semantic snippet files** with examples
- **278 palette component summaries**

### Builder Utilities

- **76 operator type mappings** (Designer → TD format)
- **16 vector parameter expansions** (t→tx,ty,tz, etc.)
- **Expression detection** (mode 49 for Python expressions)
- **5-stage validation pipeline**

## Installation

1. `pip install -r requirements.txt`
2. Copy `.env.template` to `.env`, add API key
3. Copy `config/claude_desktop_config.json` to `%APPDATA%\Claude\`
4. Restart Claude Desktop

## Known Issues

- First startup loads ~100MB of data (30s+ on slow disks)
- SentenceTransformer model downloaded on first run (~1.5GB)
- .toe building requires TouchDesigner installation
- Agent spawning requires valid ANTHROPIC_API_KEY

## Consolidated From

This release consolidates three previous projects:
- `kb_pipeline/` - Knowledge base and retrieval
- `unified_system/` - Builder and validation
- `META_AGENTIC_TOOL/` - Advanced builder utilities

All code now lives in a single `td-mcp/` directory.

## File Sizes

| Component | Size |
|-----------|------|
| knowledge_base/data/ | ~40MB |
| knowledge_base/vector_db/ | ~50MB |
| knowledge_base/graph/ | ~5MB |
| Python code | ~500KB |
| **Total** | **~96MB** |

## Next Steps

- [ ] Performance optimization for cold start
- [ ] Add caching for frequent queries
- [ ] Expand operator examples coverage
- [ ] Improve .toe building reliability
- [ ] Add more agent types

## Feedback

Report issues at: https://github.com/anthropics/claude-code/issues

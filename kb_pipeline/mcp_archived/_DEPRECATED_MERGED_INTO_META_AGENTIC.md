# DEPRECATED - MERGED INTO META_AGENTIC_TOOL

**Date**: 2024-12-27
**Reason**: Consolidated into META_AGENTIC_TOOL/mcp_server.py for TouchBuilder v0.2

## What happened
- All unique tools merged into META_AGENTIC_TOOL/mcp_server.py
- Contents archived to archive/kb_pipeline_mcp_backup/
- Claude Desktop config already points to META_AGENTIC_TOOL

## Tools merged
- td_validate -> META_AGENTIC_TOOL/mcp_server.py
- td_convert -> META_AGENTIC_TOOL/mcp_server.py
- td_compact_expertise -> META_AGENTIC_TOOL/mcp_server.py
- td_build_network -> merged into td_build_project

## To delete manually
1. Verify META_AGENTIC_TOOL server works in Claude Desktop
2. Run: `rm -rf C:/TD_Projects/kb_pipeline/mcp`

## Keep kb_pipeline/data/
The knowledge base data (wiki_docs, snippets, etc.) is still used by META_AGENTIC_TOOL.

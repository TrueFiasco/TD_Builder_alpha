# Felix's Visual Feedback Services

These services provide visual debugging capability for TD networks.

## Architecture

```
Claude Desktop / MCP Server
    ↓ (HTTP on port 9981)
TouchDesigner WebServer DAT
    ↓ (Python)
capture_service.py / error_monitor.py
```

## Services

### capture_service.py
- `capture_top_output()` - Render TOP as base64 PNG
- `capture_op_viewer()` - Universal op capture (any family)
- `capture_network_layout()` - Get network graph data

### error_monitor.py
- `get_cook_errors()` - List all cook errors
- `get_error_summary()` - Error counts by severity
- `get_python_exceptions()` - Python error details

## Setup Required

1. Run TD with WebServer DAT on port 9981
2. Load Felix's network-editor-mcp project
3. MCP tools will communicate via HTTP

## Source

Copied from: `C:\TD_Projects_FELIX\network-editor-mcp\td\modules\mcp\services\`
Original work by Felix (feature/network-editor-mcp branch)

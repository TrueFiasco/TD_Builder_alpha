# META_AGENTIC_TOOL Installation Guide

## Prerequisites

- **Python >=3.10,<3.14** (3.11 recommended for TouchDesigner 2023+)
  - BUG-018: Python 3.14+ is NOT supported (ChromaDB uses Pydantic V1)
- TouchDesigner 2023+ (for .toe/.tox building)
- Claude Desktop (for MCP integration)

## Quick Install

### 1. Install Python Dependencies

```bash
cd META_AGENTIC_TOOL
pip install -r requirements.txt
```

### 2. Configure Claude Desktop

Copy the config template to your Claude Desktop config location:

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Edit the config and replace `PATH_TO_META_AGENTIC_TOOL` with the actual path:

```json
{
  "mcpServers": {
    "touchdesigner": {
      "command": "python",
      "args": ["C:/path/to/META_AGENTIC_TOOL/mcp_server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### 3. Set API Key

Set your Anthropic API key as an environment variable:

**Windows (PowerShell):**
```powershell
$env:ANTHROPIC_API_KEY = "your-api-key-here"
```

**Windows (CMD):**
```cmd
set ANTHROPIC_API_KEY=your-api-key-here
```

**macOS/Linux:**
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

### 4. Verify Installation

```bash
cd META_AGENTIC_TOOL
python -c "from meta_agentic.execution.expert_executor import EXPERT_CONFIGS; print('Experts:', list(EXPERT_CONFIGS.keys()))"
```

Expected output:
```
Experts: ['creative_expert', 'cg_expert', 'critic', 'td_designer', 'td_glsl_expert', 'network_builder', 'summary_generator', 'td_python_expert']
```

### 5. Restart Claude Desktop

After configuring, restart Claude Desktop to load the MCP server.

## Available Tools

Once configured, Claude Desktop will have access to:

| Tool | Description |
|------|-------------|
| `td_run_expert` | Run a TD expert agent (creative, cg, designer, etc.) |
| `td_build_tox` | Build a .tox component from design |
| `td_build_toe` | Build a complete .toe project |
| `td_get_operator_types` | List available operator types |
| `td_get_expertise` | Query expertise files |
| `td_get_workflow` | Get workflow documentation |

## Troubleshooting

### Import Errors
Ensure all dependencies are installed:
```bash
pip install -r requirements.txt
```

### MCP Server Not Found
Verify the path in claude_desktop_config.json is correct and uses forward slashes.

### API Key Issues
Ensure ANTHROPIC_API_KEY is set in the environment where Claude Desktop runs.

## Data Locations

All data is self-contained within META_AGENTIC_TOOL:

```
META_AGENTIC_TOOL/
  data/
    wiki_docs/           # 673 operator specs
    snippets/            # 479 example networks
    palette_semantic/    # 264 palette components
  chroma_db/             # Vector embeddings
  meta_agentic/
    expertise/           # Knowledge files
    experts/             # Agent configurations
```

---

*Version: 0.1.0-alpha*
*Updated: 2024-12-23*

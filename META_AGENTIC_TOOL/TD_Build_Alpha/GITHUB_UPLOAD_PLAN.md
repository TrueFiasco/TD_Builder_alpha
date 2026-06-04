# GitHub Upload Plan - META_AGENTIC_TOOL

## Overview

This plan outlines how to upload META_AGENTIC_TOOL to GitHub for alpha testers.

---

## Pre-Upload Checklist

### 1. Files to Create

| File | Purpose | Status |
|------|---------|--------|
| `requirements.txt` | Python dependencies | Needs creation |
| `.gitignore` | Exclude build artifacts, secrets | Needs creation |
| `README.md` | Project overview and install instructions | Needs creation |
| `INSTALL.md` | Detailed installation guide | Needs creation |
| `LICENSE` | Open source license | Needs creation |
| `pyproject.toml` | Modern Python packaging (optional) | Needs creation |

### 2. Dependencies to Document

**Python packages:**
```
anthropic>=0.18.0      # Claude API
pyyaml>=6.0            # YAML parsing
```

**System requirements:**
- Python 3.10+
- TouchDesigner 2023.11880+ (for toecollapse.exe)
- Windows (toecollapse is Windows-only)

### 3. Files/Folders to EXCLUDE from Git

```
# Build outputs
test_output/
*.toe
*.tox
*.toe.dir/
*.tox.dir/

# Python
__pycache__/
*.pyc
*.pyo
.eggs/
*.egg-info/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Secrets (none currently, but good practice)
.env
*.key
*.pem
```

---

## Step-by-Step Upload Instructions

### Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `meta-agentic-tool` (or your preferred name)
3. Description: "AI-powered TouchDesigner project generator using Claude"
4. Choose: **Public** (for alpha testers) or **Private** (invite only)
5. Do NOT initialize with README (we'll push from local)
6. Click "Create repository"

### Step 2: Initialize Git Locally

Open terminal in `C:\TD_Projects\META_AGENTIC_TOOL`:

```bash
# Initialize git repo
git init

# Set user info (if not set globally)
git config user.name "Your Name"
git config user.email "your@email.com"
```

### Step 3: Create .gitignore

I'll create this file for you with the exclusions listed above.

### Step 4: Create requirements.txt

I'll create this file with the Python dependencies.

### Step 5: Stage and Commit

```bash
# Add all files (respecting .gitignore)
git add .

# First commit
git commit -m "Initial commit: META_AGENTIC_TOOL alpha release

- Multi-agent system for TouchDesigner project generation
- Expert agents: creative, CG, TD designer, critic, builder
- Knowledge base with 600+ operators, 278 palette components
- TOE file generation via toecollapse

🤖 Generated with Claude Code"
```

### Step 6: Push to GitHub

```bash
# Add remote (replace with your repo URL)
git remote add origin https://github.com/YOUR_USERNAME/meta-agentic-tool.git

# Push to main branch
git branch -M main
git push -u origin main
```

---

## Repository Structure for Alpha Testers

```
meta-agentic-tool/
├── README.md              # Overview, quick start
├── INSTALL.md             # Detailed installation
├── LICENSE                # MIT recommended for TD community
├── requirements.txt       # Python deps
├── .gitignore            # Exclusions
│
├── meta_agentic/         # Core Python package
│   ├── experts/          # Agent prompts (plan.md, build.md, etc.)
│   ├── expertise/        # Knowledge base YAML files
│   └── execution/        # Python execution layer
│
├── TD_Build_Alpha/       # Alpha documentation
│   └── claude_ai_docs/   # Technical documentation
│
├── tox_builder/          # TOX/TOE building utilities
│
└── examples/             # (Create) Example prompts and outputs
```

---

## README.md Structure

```markdown
# META_AGENTIC_TOOL

AI-powered TouchDesigner project generator using Claude.

## What it does

Converts text prompts like "audio-reactive particle system with beat detection"
into working TouchDesigner .toe files.

## Quick Start

1. Clone: `git clone https://github.com/...`
2. Install: `pip install -r requirements.txt`
3. Set API key: `export ANTHROPIC_API_KEY=your_key`
4. Run: `python -m meta_agentic.run "your prompt"`

## Requirements

- Python 3.10+
- TouchDesigner 2023.11880+
- Anthropic API key (Claude)

## Alpha Status

This is an alpha release. Known issues:
- Audio channel paths may need manual verification
- Some expressions require TD runtime to validate

## Contributing

Open issues or PRs on GitHub.
```

---

## Anthropic Plugin Option

You mentioned packaging as an Anthropic/Claude plugin. Options:

### Option A: MCP Server (Recommended)

Model Context Protocol servers let Claude access the tool:

```python
# meta_agentic/mcp_server.py
from mcp import Server

server = Server("meta-agentic-tool")

@server.tool("generate_toe")
async def generate_toe(prompt: str) -> dict:
    """Generate a TouchDesigner .toe file from a prompt."""
    # ... implementation
```

This would let users:
1. Install the MCP server
2. Connect Claude to it
3. Ask Claude to "generate a TouchDesigner project for..."

### Option B: Claude Code Skill

Create a skill file for Claude Code users:

```yaml
# .claude/skills/td-generator.yaml
name: td-generator
description: Generate TouchDesigner projects
command: python -m meta_agentic.run "$PROMPT"
```

### My Recommendation

Start with GitHub repository for alpha testers. The MCP server or skill can be added later as a separate integration layer. This keeps the core tool accessible to anyone with Python + TD.

---

## Estimated Repository Size

| Component | Size |
|-----------|------|
| Python code | ~500KB |
| Expert prompts | ~200KB |
| Expertise YAML | ~2MB |
| Documentation | ~100KB |
| **Total** | ~3MB |

This is well within GitHub's limits (100MB per file, unlimited total for reasonable projects).

---

## Next Steps

1. **I will create:** `.gitignore`, `requirements.txt`
2. **You will:** Create GitHub repo and get URL
3. **I will update:** README.md with your repo URL
4. **Together:** First commit and push

Let me know when you're ready to proceed!

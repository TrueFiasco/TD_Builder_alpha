# TD-Build

AI-powered TouchDesigner project generator using Claude.

Convert text prompts into working `.toe` files with multi-agent collaboration.

## Features

- **Multi-Agent System**: Creative, CG, TD Designer, Critic, and Builder agents collaborate
- **Knowledge Base**: 600+ TouchDesigner operators, 278 palette components
- **TOE Generation**: Produces actual `.toe` files via `toecollapse.exe`
- **Audio-Reactive**: Built-in patterns for audio visualization
- **Workflow Strategies**: V2-V6 strategies with quality gates and iteration

## Requirements

- Python 3.10+
- TouchDesigner 2023.11880+ (Windows only, for `toecollapse.exe`)
- Anthropic API key

## Installation

```bash
# Clone the repo
git clone https://github.com/TrueFiasco/TD-Build.git
cd TD-Build

# Install dependencies
pip install -r requirements.txt

# Set your API key
set ANTHROPIC_API_KEY=your_key_here
```

## Quick Start

```python
from pathlib import Path
from meta_agentic.execution.toe_builder_bridge import build_toe_from_yaml

# Build TOE from a TD Designer YAML output
toe_path = build_toe_from_yaml(
    Path("test_output/teardrop_v2_subagent/04_td_designer.yaml"),
    Path("output/")
)
print(f"Created: {toe_path}")
```

Or test the integration:

```bash
python test_strategy_integration.py
```

## Project Structure

```
TD-Build/
├── meta_agentic/
│   ├── experts/          # Agent prompts (plan.md, build.md, etc.)
│   ├── expertise/        # Knowledge base YAML files
│   └── execution/        # Python execution layer
│       ├── strategy_runner.py    # V2-V6 workflow orchestration
│       ├── toe_builder_bridge.py # JSON to TOE conversion
│       ├── blackboard.py         # State management
│       └── expert_executor.py    # Agent execution
├── tox_builder/          # TOX/TOE building utilities
├── TD_Build_Alpha/       # Alpha documentation
│   └── claude_ai_docs/   # Technical deep-dive docs
├── requirements.txt
└── CLAUDE.md             # Instructions for Claude Code
```

## Alpha Status

This is an alpha release. What works:

- TOE file generation from network designs
- Multi-container projects with operators
- Connections between operators
- Expression-driven parameters (audio-reactive)

Known limitations:

- Audio channel paths may need manual verification in TD
- Some expressions require TD runtime to validate
- Windows only (toecollapse.exe dependency)

## Example Output

The Teardrop project generates:
- 6 containers (audio, core, particles, rays, glitch, composite_final)
- 45 operators with connections
- Audio-reactive expressions

## Reporting Issues

Open an issue at: https://github.com/TrueFiasco/TD-Build/issues

Include:
- Your prompt/input
- Error message or unexpected behavior
- Python and TD versions

## License

MIT

"""TD Builder MCP server — alpha consolidated entry point.

Launches the offline MCP server (MCP/server_core/mcp_server.py) with the
correct engine import roots. The server module is intentionally left in place
so its __file__-relative resolution of the consolidated KB bundle
(<root>/KB via Path(__file__).parent.parent/"KB") and its sibling search-stack
loads continue to work exactly as verified.

Register THIS file as the MCP server command in your client, e.g.:

  "td-builder-alpha": {
    "command": "python",
    "args": ["C:/TD_builder_alpha/MCP/python/server.py"]
  }
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # release root
sys.path.insert(0, str(ROOT))

import bootstrap  # noqa: E402  (repo-root module)

bootstrap.setup()

# Run the real server as __main__ so its asyncio entrypoint executes and its
# __file__ stays the true module path (KB resolves to <root>/KB).
runpy.run_path(str(ROOT / "MCP" / "server_core" / "mcp_server.py"), run_name="__main__")

"""td_validate_expanded launcher — bootstraps the engine and audits an expanded .toe/.tox.dir against its .toc. Run directly with python (no console command is installed)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # release root (Tools/offline Builder tools/ -> root)
sys.path.insert(0, str(ROOT))
import bootstrap  # noqa: E402

bootstrap.setup()
from cli.td_validate_expanded import main  # noqa: E402  (MCP/engine/cli)


if __name__ == "__main__":
    raise SystemExit(main())

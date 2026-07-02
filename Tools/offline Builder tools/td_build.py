"""td_build launcher — bootstraps the engine and runs the .toe/.tox builder. Run directly with python (no console command is installed)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # release root (Tools/offline Builder tools/ -> root)
sys.path.insert(0, str(ROOT))
import bootstrap  # noqa: E402

bootstrap.setup()
from cli.td_build import main  # noqa: E402  (unified_system/cli)


if __name__ == "__main__":
    main()

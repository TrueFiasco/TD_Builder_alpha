"""
Configuration for the KB search stack — ONE config story (see Config/SETTINGS.md).

Precedence, highest first:
  1. Real environment variables (e.g. set in the MCP client config's "env" block)
  2. `.env` at the release root (copy of Config/.env.template)
     — legacy fallback: MCP/server_core/.env
  3. `Config/search_config.json`
     — legacy fallback: MCP/server_core/config/search_config.json
  4. The code defaults below

The release root is TD_BUILDER_ROOT if set, else three levels above this file
(config/ -> server_core -> MCP -> root). Relative configured paths resolve
against the release root, never the process CWD.

Key-free: local embeddings only. There are no cloud providers and no API keys.
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = (
    Path(os.environ["TD_BUILDER_ROOT"]).resolve()
    if os.environ.get("TD_BUILDER_ROOT")
    else Path(__file__).resolve().parents[3]
)


def _load_env_file(path: Path) -> None:
    """Minimal KEY=VALUE .env loader ('#' comments, optional quotes). Values only
    fill unset keys, so real environment variables keep precedence. Deliberately
    dependency-free — python-dotenv is not a declared dependency."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
    except Exception as e:  # noqa: BLE001 — config must never kill the server
        print(f"Warning: could not read {path}: {e}")


for _env_path in (_ROOT / ".env", Path(__file__).parent.parent / ".env"):
    if _env_path.exists():
        _load_env_file(_env_path)
        break

_CONFIG: Dict[str, Any] = {}
for _cfg_path in (_ROOT / "Config" / "search_config.json",
                  Path(__file__).parent / "search_config.json"):
    if _cfg_path.exists():
        try:
            with open(_cfg_path, "r", encoding="utf-8") as f:
                _CONFIG = json.load(f)
        except Exception as e:  # noqa: BLE001
            print(f"Warning: could not parse {_cfg_path}: {e}")
        break


# D4 feedback spine (opt-in, local-only). Master-switch DEFAULT from the JSON layer;
# the real env var TD_FEEDBACK_ENABLED (read at CALL time in MCP/feedback.py) and the
# root `.env` still override it via the same precedence as everything else. Off by
# default. See Config/SETTINGS.md.
FEEDBACK_ENABLED_DEFAULT = str(_CONFIG.get("feedback_enabled", "false"))


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else _ROOT / path


class SearchConfig:
    """Configuration for the search/embedding system (key-free, local-only)."""

    # Embedding — local only. The shipped vector store was built with
    # all-MiniLM-L6-v2; KB/manifest.json is authoritative for the model id,
    # these values are the fallback when the manifest doesn't self-declare.
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", _CONFIG.get("embedding_provider", "local"))
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", _CONFIG.get("embedding_model", "all-MiniLM-L6-v2"))

    # Paths (relative entries resolve against the release root)
    VECTOR_DB_PATH = _resolve(os.getenv("UNIFIED_VECTORDB_PATH", _CONFIG.get("vector_db_path", "KB/vector_db")))
    GRAPH_DATA_PATH = _resolve(os.getenv("GRAPH_DATA_PATH", _CONFIG.get("graph_path", "KB/knowledge_graph_enhanced.gpickle")))

    @classmethod
    def validate(cls) -> tuple[bool, Optional[str]]:
        """Returns (is_valid, error_message)."""
        if cls.EMBEDDING_PROVIDER != "local":
            return False, (
                f"EMBEDDING_PROVIDER={cls.EMBEDDING_PROVIDER!r} is not supported: this release "
                "is key-free/local-only (the shipped vector store was embedded with a local "
                "model, so cloud query embeddings would not match it). Set EMBEDDING_PROVIDER=local."
            )
        return True, None

    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        """Get a summary of current configuration."""
        return {
            "embedding_provider": cls.EMBEDDING_PROVIDER,
            "embedding_model": cls.EMBEDDING_MODEL,
            "vector_db_path": str(cls.VECTOR_DB_PATH),
            "graph_path": str(cls.GRAPH_DATA_PATH),
        }


# Validate configuration on import
is_valid, error = SearchConfig.validate()
if not is_valid:
    print(f"Warning: Configuration validation failed: {error}")
    print("Continuing with local embeddings (all-MiniLM-L6-v2)")

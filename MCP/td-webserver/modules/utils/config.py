"""
TouchDesigner MCP Web Server Configuration Module
Provides API endpoint definitions and HTTP status code settings
"""

import os


def _env_flag(name: str, default: bool) -> bool:
	"""Parse a boolean environment flag (1/true/yes/on → True)."""
	raw = os.environ.get(name)
	if raw is None:
		return default
	return raw.strip().lower() in ("1", "true", "yes", "on")


# LogLevel.DEBUG logging — OFF by default (was hardcoded True, which logged full
# response payloads to the textport). Opt in with TD_API_DEBUG=1.
DEBUG = _env_flag("TD_API_DEBUG", False)

"""Measurement & improvement suite for the td-builder MCP server.

Not a pass/fail gate: each module emits a scalar metric over a dataset,
persists a baseline, prints a ranked worst-case backlog, and reports the
delta vs the last baseline. See tests/README.md.
"""

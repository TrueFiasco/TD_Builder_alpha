# Legacy Builders Archived

**Date**: 2024-12-27
**Reason**: Consolidated into meta_agentic/execution/ for TouchBuilder v0.2

## What happened
- builder.py, builder_v2.py, builder_v3.py, builder_v4.py moved to archive/tox_builder_legacy/
- Canonical implementation is now `meta_agentic/execution/tox_builder.py`
- Bridge to unified_system: `meta_agentic/execution/toe_builder_bridge.py`

## Remaining files
- mcp_smoke_test.py - Keep for testing
- test_build.json - Test fixture
- tests/ - Test suite
- output/ - Build outputs

## Canonical implementation
Use these instead:
- `meta_agentic.execution.tox_builder.ToxBuilder`
- `meta_agentic.execution.toe_builder_bridge.ToeBuilderBridge`

# Test Coverage Matrix

**Created By**: QUEENIE (QA Tester)
**Date**: 2024-12-23

---

## Test Suite Inventory

### 1. tests/basic_builds/ (Basic Build Tests)

| File | Purpose | Status | Last Run |
|------|---------|--------|----------|
| `run_basic_tests.py` | Test runner for YAML-based build fixtures | FOUND | UNKNOWN |
| `test_06_build_toxs.py` | Build .tox files | FOUND | UNKNOWN |
| `test_07_combined_toe.py` | Combined .toe builds | FOUND | UNKNOWN |
| `test_08_julia_wrapper.py` | Julia wrapper tests | FOUND | UNKNOWN |
| `test_09_combined_with_julia.py` | Combined Julia builds | FOUND | UNKNOWN |
| `test_10_final_combined.py` | Final combined tests | FOUND | UNKNOWN |

**Coverage**: Basic build operations with YAML fixtures

---

### 2. tox_builder/tests/ (ToxBuilder Unit Tests)

| File | Purpose | Status | Test Count |
|------|---------|--------|------------|
| `test_all_operators.py` | Stress test 685 operators | FOUND | 685 ops |
| `test_networks.py` | Network topology tests (linear, branch, mesh) | FOUND | 13 tests |
| `test_parameters.py` | Parameter type tests (bool, int, float, string, menu) | FOUND | ~25 tests |
| `test_roundtrip.py` | Round-trip validation | FOUND | UNKNOWN |
| `run_stress_tests.py` | Stress test runner | FOUND | - |
| `emit_stress_test_results.py` | Results emitter | FOUND | - |
| `mcp_smoke_test.py` | MCP tool smoke tests | FOUND | 3-20 tests |

**Coverage**:
- All 685 operator types
- 13 network topologies (empty, single, chains, branches, mesh, multi-family)
- 7 parameter categories (boolean, integer, float, string, menu, multi, mixed)
- Smoke tests with 3 fixture levels (minimal, standard, full)

---

### 3. meta_agentic/tests/ (Meta-Agentic Tests)

| File | Purpose | Status | Notes |
|------|---------|--------|-------|
| `test_creative_orchestration.py` | Full 6-stage creative workflow simulation | FOUND | Comprehensive |
| `output/test_roundtrip.py` | Round-trip testing | FOUND | - |

**Coverage**:
- 6-stage orchestration flow: creative_expert → cg_expert → critic → td_designer → network_builder
- Expertise loading
- Context preparation
- Design spec generation
- .tox assembly

---

### 4. Root-Level Tests (Standalone)

| File | Purpose | Status | Notes |
|------|---------|--------|-------|
| `test_infrastructure.py` | Import validation, file existence, config | FOUND | No API calls |
| `test_kb_integration.py` | KnowledgeBase + ExpertExecutor integration | FOUND | 6 experts tested |
| `test_strategy_integration.py` | Strategy runner integration | FOUND | - |
| `test_toe_builder_bridge.py` | TOE builder bridge | FOUND | - |
| `test_critic_fix.py` | Critic module fix validation | FOUND | - |
| `test_ruth_v0_v6.py` | Ruth strategy v0-v6 | FOUND | - |
| `test_ruth_v2.py` | Ruth strategy v2 | FOUND | - |
| `run_ruth_test.py` | Ruth test runner | FOUND | - |
| `run_teardrop_test.py` | Teardrop test runner | FOUND | - |
| `run_angel_test.py` | Angel test runner | FOUND | - |
| `run_minimal_test.py` | Minimal test runner | FOUND | - |

---

## Coverage Summary by Component

| Component | Test Files | Test Count | Status |
|-----------|------------|------------|--------|
| ToxBuilder (operators) | 1 | 685 | EXISTS |
| ToxBuilder (networks) | 1 | 13 | EXISTS |
| ToxBuilder (params) | 1 | ~25 | EXISTS |
| MCP Smoke Tests | 1 | 3-20 | EXISTS |
| Basic Builds | 5 | UNKNOWN | EXISTS |
| Meta-Agentic Orchestration | 1 | 1 | EXISTS |
| Infrastructure | 1 | 6 | EXISTS |
| KB Integration | 1 | 6 | EXISTS |
| Strategy Integration | 4+ | UNKNOWN | EXISTS |

---

## Gaps Identified

### HIGH Priority (Blocking Alpha)

| Gap | Description | Recommendation |
|-----|-------------|----------------|
| MCP Tool Tests | No dedicated test for `td_run_expert`, `td_build_tox`, `td_build_toe` | Create MCP tool test suite |
| Prompt-to-Build Tests | No tests for natural language prompts | Create 50 prompts (PETER's task) |
| Test Results Tracking | No centralized test results file | Create TEST_RESULTS.md |
| Automated Test Runner | No single "run all tests" script | Create unified runner |

### MEDIUM Priority

| Gap | Description | Recommendation |
|-----|-------------|----------------|
| Claude Desktop Integration | No integration tests | Add after Alpha |
| Error Handling Tests | Few edge case / error path tests | Add negative tests |
| Performance Benchmarks | Stress tests exist but no baseline | Establish baselines |

### LOW Priority

| Gap | Description | Recommendation |
|-----|-------------|----------------|
| Code Coverage Report | No coverage tooling | Add pytest-cov |
| Test Documentation | Tests exist but not documented | Add docstrings |

---

## Test Execution Status

### Last Known Run Status

| Test Suite | Status | Pass Rate | Notes |
|------------|--------|-----------|-------|
| tox_builder/tests/ | UNKNOWN | ? | Need to run |
| tests/basic_builds/ | UNKNOWN | ? | Need to run |
| meta_agentic/tests/ | UNKNOWN | ? | Need to run |
| Root tests | UNKNOWN | ? | Need to run |

---

## Recommended Next Actions

1. **IMMEDIATE**: Run all existing tests to establish baseline
   ```bash
   cd META_AGENTIC_TOOL
   python tox_builder/tests/test_all_operators.py --family CHOP
   python test_infrastructure.py
   ```

2. **SHORT-TERM**: Create unified test runner
   ```bash
   # Create run_all_tests.py that runs all test suites
   ```

3. **FOR PETER**: Create test prompt library at `tests/prompts/`
   - 10 basic prompts
   - 20 intermediate prompts
   - 20 advanced prompts

4. **FOR QUEENIE**: Execute tests and populate TEST_RESULTS.md

---

## Quality Gates (from CLAUDE.md)

### Alpha Exit Criteria
- [ ] 50 test prompts created
- [ ] >50% pass rate on basic prompts
- [ ] All HIGH bugs fixed
- [ ] No CRITICAL bugs

### Current Status
- [ ] Test prompts: 0/50 (PETER working on it)
- [ ] Pass rate: UNKNOWN (need to run tests)
- [ ] HIGH bugs: 1 open (BUG-001 .parm format)
- [ ] CRITICAL bugs: 0

---

*Last Updated: 2024-12-23 by QUEENIE*

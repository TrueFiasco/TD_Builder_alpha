"""D3 (W6a) live authorization tiering — CI safety tests (plan §5.3).

Hermetic (no KB, no live TD): all three tiering guarantees are checkable offline.

  1. NO-DRIFT   — the client's Tool annotations agree, per tool, with the canonical
                  operationId->class map (MCP/live_tool_risk.json).
  2. COVERAGE   — every operationId the live surface registers (OpenAPI schema +
                  feedback handlers + D3 session handlers) has a class entry, and
                  the map has no orphan rows. Read-only mode fails CLOSED, so a
                  missing classification would silently 403 a read otherwise.
  3. READ-ONLY  — the policy decision (tier_policy.read_only_denial): READ_ONLY is
     MATRIX       allowed; DESTRUCTIVE, WRITE_CHECKPOINT, unmatched and unclassified
                  are denied; the flag toggles via env. (The HTTP-403 early-return
                  wiring in api_controller is statically guarded by
                  test_readonly_wiring_guard.py and exercised at runtime by the
                  GATE-B live matrix.)

api_controller itself imports the live `mcp` package (which collides with the
installed MCP SDK under test), so the decision logic lives in the dependency-free
tier_policy module, loaded here by file path.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULES = REPO / "MCP" / "td-webserver" / "modules"
CONTROLLERS = MODULES / "mcp" / "controllers"
LIVE_CLIENT = REPO / "MCP" / "live_client"
SCHEMA = MODULES / "td_server" / "openapi_server" / "openapi" / "openapi.yaml"
RISK_JSON = REPO / "MCP" / "live_tool_risk.json"


def _load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec and spec.loader, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# tier_policy is stdlib-only -> load it directly by file path (avoids the mcp collision).
tier_policy = _load_by_path("td_tier_policy_under_test", CONTROLLERS / "tier_policy.py")


@pytest.fixture(scope="module")
def live():
    if str(LIVE_CLIENT) not in sys.path:
        sys.path.insert(0, str(LIVE_CLIENT))
    import td_live_client  # noqa: E402
    return td_live_client


def _risk_map() -> dict:
    return json.loads(RISK_JSON.read_text(encoding="utf-8"))


def _dyn_operation_ids(module_file: Path) -> set:
    """operationIds for a dynamically-registered handler module, derived from its
    *_ROUTES dict VALUES (FEEDBACK_ROUTES / SESSION_ROUTES) — the actual registration
    source (api_controller registers each route value's handler.__name__). R5c: was
    __all__-based, but a handler added to a ROUTES dict without an __all__ entry
    would silently escape the coverage gate; the ROUTES dict cannot lie."""
    tree = ast.parse((CONTROLLERS / module_file).read_text(encoding="utf-8"))
    out: set = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Dict)
            and any(
                isinstance(t, ast.Name) and t.id.endswith("_ROUTES")
                for t in node.targets
            )
        ):
            for value in node.value.values:
                if isinstance(value, ast.Name):
                    out.add(value.id)
    assert out, f"no *_ROUTES dict with handler values found in {module_file}"
    return out


def _registered_operation_ids() -> set:
    """Every operationId the runtime router (_routes_by_operation_id) will hold:
    OpenAPI schema + feedback handlers + D3 session handlers."""
    ops: set = set()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for _path, item in schema["paths"].items():
        for method, op in item.items():
            if method.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH") and op.get("operationId"):
                ops.add(op["operationId"])
    ops |= _dyn_operation_ids("feedback_handlers.py")
    ops |= _dyn_operation_ids("session_handlers.py")
    return ops


def _ann_class(ann) -> str:
    if ann.readOnlyHint is True:
        return "READ_ONLY"
    if ann.destructiveHint is True:
        return "DESTRUCTIVE"
    if ann.destructiveHint is False and ann.idempotentHint is True:
        return "WRITE_CHECKPOINT"
    return "UNKNOWN"


# --------------------------------------------------------------------------
# 1. No-drift: client annotations <-> canonical JSON, per tool
# --------------------------------------------------------------------------

def test_no_drift_client_annotations_match_risk_map(live):
    risk = _risk_map()["operations"]
    tools = {t.name: t for t in live.TD_LIVE_TOOLS}
    for op_id, entry in risk.items():
        ct = entry["client_tool"]
        assert ct in tools, f"{op_id} maps to unknown client tool {ct!r}"
        assert _ann_class(tools[ct].annotations) == entry["class"], (
            f"annotation drift for {ct} ({op_id}): "
            f"{_ann_class(tools[ct].annotations)} != {entry['class']}"
        )


def test_every_client_tool_is_mapped_one_to_one(live):
    risk = _risk_map()["operations"]
    mapped = {e["client_tool"] for e in risk.values()}
    tool_names = {t.name for t in live.TD_LIVE_TOOLS}
    assert mapped == tool_names, (
        f"client<->map mismatch: only-in-map={mapped - tool_names}, "
        f"only-in-tools={tool_names - mapped}"
    )
    assert len(risk) == len(tool_names) == 22  # W-A2 added get_glsl_status


# --------------------------------------------------------------------------
# 2. Total coverage / fail-closed
# --------------------------------------------------------------------------

def test_risk_map_covers_every_registered_operation():
    registered = _registered_operation_ids()
    mapped = set(_risk_map()["operations"].keys())
    missing = registered - mapped
    orphan = mapped - registered
    assert not missing, f"unclassified operationIds (read-only mode would 403 these): {missing}"
    assert not orphan, f"risk-map rows with no registered route: {orphan}"


def test_load_tier_map_matches_json_classes():
    tm, err = tier_policy.load_tier_map()
    assert err is None
    ops = _risk_map()["operations"]
    assert tm == {op_id: e["class"] for op_id, e in ops.items()}
    assert set(tm.values()) <= {"READ_ONLY", "WRITE_CHECKPOINT", "DESTRUCTIVE"}


# --------------------------------------------------------------------------
# 3. Read-only-mode decision matrix (tier_policy.read_only_denial)
# --------------------------------------------------------------------------

def test_read_only_denial_matrix():
    tm, _ = tier_policy.load_tier_map()
    # READ_ONLY -> allowed (None)
    assert tier_policy.read_only_denial(tm, "get_td_info") is None
    assert tier_policy.read_only_denial(tm, "get_nodes") is None
    assert tier_policy.read_only_denial(tm, "getMutationStatus") is None
    # DESTRUCTIVE -> denied
    assert tier_policy.read_only_denial(tm, "create_node")
    assert tier_policy.read_only_denial(tm, "exec_python_script")
    # WRITE_CHECKPOINT -> denied (an observe-only machine rejects remote-forced writes)
    assert tier_policy.read_only_denial(tm, "saveProject")
    # unmatched route (op_id None) and unclassified -> fail CLOSED
    assert tier_policy.read_only_denial(tm, None)
    assert tier_policy.read_only_denial(tm, "no_such_operation")


def test_read_only_denial_fails_closed_on_empty_map():
    # A missing/broken map + read-only mode => everything denied (safe misconfig posture).
    assert tier_policy.read_only_denial({}, "get_td_info")
    assert tier_policy.read_only_denial({}, "saveProject")


def test_read_only_enabled_env_toggle(monkeypatch):
    monkeypatch.delenv(tier_policy.READONLY_ENV, raising=False)
    assert tier_policy.read_only_enabled() is False
    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv(tier_policy.READONLY_ENV, truthy)
        assert tier_policy.read_only_enabled() is True
    for falsy in ("0", "false", "", "no"):
        monkeypatch.setenv(tier_policy.READONLY_ENV, falsy)
        assert tier_policy.read_only_enabled() is False


def test_tier_map_file_override_and_missing(monkeypatch, tmp_path):
    # Override path is honored; success reports no error.
    custom = tmp_path / "risk.json"
    custom.write_text(json.dumps({"operations": {"x": {"class": "READ_ONLY"}}}), encoding="utf-8")
    monkeypatch.setenv(tier_policy.RISK_FILE_ENV, str(custom))
    assert tier_policy.load_tier_map() == ({"x": "READ_ONLY"}, None)
    # Missing file -> ({}, err) (never raises), err says NOT FOUND (R4: the boot
    # warning must distinguish a partial install from a corrupt file).
    monkeypatch.setenv(tier_policy.RISK_FILE_ENV, str(tmp_path / "does_not_exist.json"))
    tm, err = tier_policy.load_tier_map()
    assert tm == {} and "not found" in err
    # Malformed file -> ({}, err) (never raises), err says MALFORMED, not missing.
    broken = tmp_path / "broken.json"
    broken.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv(tier_policy.RISK_FILE_ENV, str(broken))
    tm, err = tier_policy.load_tier_map()
    assert tm == {} and "malformed" in err and "not found" not in err

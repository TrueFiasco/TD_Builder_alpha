"""R6 (PR #23 review rider): static wiring guard for the read-only 403 tiering.

The D3 read-only mode is enforced by ONE architectural checkpoint: api_controller's
``onHTTPRequest`` calls ``self._read_only_denial(method, path)`` and early-returns a
real HTTP 403 BEFORE ``self.router.route_request(...)`` ever runs. Because the check
sits in front of the single dispatch path (and the tier map fails CLOSED on
unmatched/unclassified operationIds — see test_live_tool_risk.py), every mutating
route is covered without per-route wiring. That also means the whole guarantee
hinges on THREE structural facts a refactor could silently break:

  1. the denial check exists in ``onHTTPRequest`` and its denial branch sets
     statusCode 403 and returns — before routing;
  2. ``route_request`` has EXACTLY ONE call site, inside ``onHTTPRequest`` (no side
     door that skips the checkpoint);
  3. ``_read_only_denial`` really delegates to the unit-tested tier_policy pieces
     (``read_only_enabled`` gate, ``read_only_denial(self._tier_map, ...)``
     decision, operationId resolved via the router's own ``match``).

This test pins all three over COMMITTED SOURCE. It cannot import api_controller
(it imports the live ``mcp`` package, which collides with the installed MCP SDK
under test — the same reason the decision logic lives in tier_policy), so it
parses the source with ``ast`` instead.

LIMITS (documented on purpose): AST matches the literal source spellings
(``self._read_only_denial``, ``self.router.route_request``, a constant ``403``).
It does NOT prove the check fires at runtime (an aliased dispatch or a monkeypatch
would evade it) — runtime enforcement is exercised by the GATE-B live 403 matrix.
Pattern mirrors tests/unit/test_no_save_dialog_guard.py (AST tripwire + matcher
has-teeth self-tests).
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API_CONTROLLER = (
    REPO / "MCP" / "td-webserver" / "modules" / "mcp" / "controllers"
    / "api_controller.py"
)


def _controller_tree() -> ast.Module:
    return ast.parse(API_CONTROLLER.read_text(encoding="utf-8"))


def _find_method(tree: ast.Module, cls_name: str, method: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method:
                    return item
    raise AssertionError(f"{cls_name}.{method} not found in {API_CONTROLLER}")


def _is_self_call(call: ast.Call, attr: str) -> bool:
    """``self.<attr>(...)``"""
    f = call.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr == attr
        and isinstance(f.value, ast.Name)
        and f.value.id == "self"
    )


def _is_router_call(call: ast.Call, attr: str) -> bool:
    """``self.router.<attr>(...)``"""
    f = call.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr == attr
        and isinstance(f.value, ast.Attribute)
        and f.value.attr == "router"
        and isinstance(f.value.value, ast.Name)
        and f.value.value.id == "self"
    )


def _calls(node: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Call)]


def _denial_gate(func: ast.FunctionDef) -> "ast.If | None":
    """The If that gates on the variable assigned from ``self._read_only_denial(...)``
    and whose body BOTH sets a constant 403 and returns. None when absent/broken."""
    denial_var = None
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and _is_self_call(node.value, "_read_only_denial")
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            denial_var = node.targets[0].id
            break
    if denial_var is None:
        return None
    for node in ast.walk(func):
        if not isinstance(node, ast.If):
            continue
        names = {
            n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)
        }
        if denial_var not in names:
            continue
        sets_403 = any(
            isinstance(sub, ast.Assign)
            and isinstance(sub.value, ast.Constant)
            and sub.value.value == 403
            for sub in ast.walk(node)
        )
        returns = any(isinstance(sub, ast.Return) for sub in ast.walk(node))
        if sets_403 and returns:
            return node
    return None


# --------------------------------------------------------------------------
# The three wiring invariants
# --------------------------------------------------------------------------

def test_denial_gate_exists_and_precedes_routing():
    """onHTTPRequest: the 403 early-return gate exists and sits BEFORE the router
    dispatch — a mutating request in read-only mode never reaches route_request."""
    func = _find_method(_controller_tree(), "APIControllerOpenAPI", "onHTTPRequest")
    gate = _denial_gate(func)
    assert gate is not None, (
        "onHTTPRequest lost its read-only 403 gate: expected "
        "`<var> = self._read_only_denial(...)` followed by an `if <var> ...:` "
        "branch that sets statusCode 403 and returns"
    )
    route_calls = [c for c in _calls(func) if _is_router_call(c, "route_request")]
    assert route_calls, "onHTTPRequest no longer calls self.router.route_request"
    assert gate.lineno < min(c.lineno for c in route_calls), (
        f"the read-only 403 gate (line {gate.lineno}) must run BEFORE "
        f"route_request (line {min(c.lineno for c in route_calls)})"
    )


def test_route_request_has_single_gated_call_site():
    """The checkpoint covers every route only if routing has NO side door: exactly
    one route_request call in the whole controller, inside onHTTPRequest."""
    tree = _controller_tree()
    all_sites = [
        c for c in _calls(tree) if _is_router_call(c, "route_request")
    ]
    func = _find_method(tree, "APIControllerOpenAPI", "onHTTPRequest")
    gated_sites = [c for c in _calls(func) if _is_router_call(c, "route_request")]
    assert len(all_sites) == 1 and len(gated_sites) == 1, (
        f"expected exactly one route_request call site (in onHTTPRequest, behind "
        f"the read-only gate); found {len(all_sites)} in the module at lines "
        f"{[c.lineno for c in all_sites]}"
    )


def test_read_only_denial_delegates_to_tier_policy():
    """_read_only_denial wires the unit-tested pieces together: the per-request
    read_only_enabled() gate, the router's own match() for the operationId, and
    tier_policy.read_only_denial(self._tier_map, ...) for the decision."""
    func = _find_method(
        _controller_tree(), "APIControllerOpenAPI", "_read_only_denial"
    )
    calls = _calls(func)
    assert any(
        isinstance(c.func, ast.Name) and c.func.id == "read_only_enabled"
        for c in calls
    ), "_read_only_denial no longer consults read_only_enabled()"
    assert any(_is_router_call(c, "match") for c in calls), (
        "_read_only_denial no longer resolves the operationId via self.router.match"
    )
    policy_calls = [
        c for c in calls
        if isinstance(c.func, ast.Name) and c.func.id == "read_only_denial"
    ]
    assert policy_calls, "_read_only_denial no longer calls tier_policy.read_only_denial"
    first_arg = policy_calls[0].args[0] if policy_calls[0].args else None
    assert (
        isinstance(first_arg, ast.Attribute)
        and first_arg.attr == "_tier_map"
        and isinstance(first_arg.value, ast.Name)
        and first_arg.value.id == "self"
    ), "read_only_denial must be passed self._tier_map (the boot-loaded map)"


# --------------------------------------------------------------------------
# Matcher has-teeth self-tests (synthetic sources)
# --------------------------------------------------------------------------

_GOOD = """
class C:
    def onHTTPRequest(self, w, request, response):
        denial = self._read_only_denial(m, p)
        if denial is not None:
            response["statusCode"] = 403
            return response
        result = self.router.route_request(m, p, q, b)
        return response
"""

_NO_RETURN = """
class C:
    def onHTTPRequest(self, w, request, response):
        denial = self._read_only_denial(m, p)
        if denial is not None:
            response["statusCode"] = 403
        result = self.router.route_request(m, p, q, b)
        return response
"""

_WRONG_CODE = """
class C:
    def onHTTPRequest(self, w, request, response):
        denial = self._read_only_denial(m, p)
        if denial is not None:
            response["statusCode"] = 200
            return response
        result = self.router.route_request(m, p, q, b)
        return response
"""

_GATE_AFTER_ROUTING = """
class C:
    def onHTTPRequest(self, w, request, response):
        result = self.router.route_request(m, p, q, b)
        denial = self._read_only_denial(m, p)
        if denial is not None:
            response["statusCode"] = 403
            return response
        return response
"""


def _gate_of(src: str) -> "ast.If | None":
    return _denial_gate(_find_method(ast.parse(src), "C", "onHTTPRequest"))


def test_denial_gate_matcher_has_teeth():
    """The gate finder accepts the real shape and rejects the broken ones, so the
    tripwire above cannot pass vacuously."""
    assert _gate_of(_GOOD) is not None
    assert _gate_of(_NO_RETURN) is None       # 403 set but request continues
    assert _gate_of(_WRONG_CODE) is None      # returns, but not a 403
    # An out-of-order gate is FOUND (it exists) — the ORDERING assert catches it:
    gate = _gate_of(_GATE_AFTER_ROUTING)
    func = _find_method(ast.parse(_GATE_AFTER_ROUTING), "C", "onHTTPRequest")
    route_line = min(
        c.lineno for c in _calls(func) if _is_router_call(c, "route_request")
    )
    assert gate is not None and gate.lineno > route_line


def test_call_matchers_have_teeth():
    """self-call vs router-call matchers fire on the exact spellings only."""
    call = ast.parse("self._read_only_denial(m, p)", mode="eval").body
    assert _is_self_call(call, "_read_only_denial")
    assert not _is_self_call(call, "route_request")
    other = ast.parse("obj._read_only_denial(m, p)", mode="eval").body
    assert not _is_self_call(other, "_read_only_denial")   # receiver isn't self
    route = ast.parse("self.router.route_request(m, p, q, b)", mode="eval").body
    assert _is_router_call(route, "route_request")
    assert not _is_router_call(route, "match")
    bare = ast.parse("router.route_request(m)", mode="eval").body
    assert not _is_router_call(bare, "route_request")      # not self.router

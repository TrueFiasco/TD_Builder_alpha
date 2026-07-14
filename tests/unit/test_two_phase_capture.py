"""Unit tests for W-B — two-phase opviewerTOP capture + POP info sidecar.

opviewerTOP renders progressively and only fully populates a real frame after
wiring, so a single same-frame pull can never capture a POP point cloud (report
L11 / prior F16). The fix splits capture into prime (create+wire+prime, return a
handle) and pull (force-cook to byte-size stability + destroy), with a client-side
wait — asyncio.sleep on the client thread, never TD's — between the two HTTP
requests. These stub-lane tests drive the pure Python of capture_service and the
client's two-step orchestration.

The real 10k-point pointgenerator capture is a LIVE-LANE test (post-deploy).
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
from unittest import mock

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODULES_DIR = os.path.join(_REPO_ROOT, "MCP", "td-webserver", "modules")
_CAPTURE_PY = os.path.join(_MODULES_DIR, "mcp", "services", "capture_service.py")
_LIVE_CLIENT_DIR = os.path.join(_REPO_ROOT, "MCP", "live_client")
_LIVE_CLIENT_PY = os.path.join(_LIVE_CLIENT_DIR, "td_live_client.py")


# ---------------------------------------------------------------------------
# capture_service — prime / pull / pop info
# ---------------------------------------------------------------------------


class _Vec:
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class _BBox:
    def __init__(self):
        self.min = _Vec(-1, -1, -1)
        self.max = _Vec(1, 1, 1)
        self.center = _Vec(0, 0, 0)
        self.size = _Vec(2, 2, 2)


class FakeViewer:
    """A temp opviewerTOP whose saveByteArray yields a scripted size progression."""

    OPType = "opviewerTOP"

    def __init__(self, path, sizes, parent):
        self.path = path
        self.name = path.rsplit("/", 1)[-1]
        self.valid = True
        self.width = 512
        self.height = 512
        self.par = types.SimpleNamespace()
        self.nodeX = 0
        self.nodeY = 0
        self._parent = parent
        self._sizes = list(sizes)
        self._i = 0
        self.cook_calls = 0
        self.destroyed = False

    def cook(self, force=False):
        self.cook_calls += 1

    def saveByteArray(self, ext, quality=1.0):
        if self._i < len(self._sizes):
            size = self._sizes[self._i]
            self._i += 1
        else:
            size = self._sizes[-1] if self._sizes else 0
        return b"x" * size

    def destroy(self):
        self.destroyed = True
        self.valid = False
        self._parent._remove(self)


class FakePop:
    family = "POP"
    OPType = "pointgeneratorPOP"

    def __init__(self, path, parent, num_points=10000, bbox=True):
        self.path = path
        self.name = path.rsplit("/", 1)[-1]
        self.valid = True
        self.numPoints = num_points
        self.nodeX = 0
        self.nodeY = 0
        self._parent = parent
        if bbox:
            self.pointBoundingBox = _BBox()

    def parent(self):
        return self._parent


class FakeTop:
    family = "TOP"
    OPType = "noiseTOP"

    def __init__(self, path):
        self.path = path
        self.name = path.rsplit("/", 1)[-1]
        self.valid = True
        self.width = 256
        self.height = 256

    def cook(self, force=False):
        pass

    def saveByteArray(self, ext, quality=1.0):
        return b"y" * 1024


class FakeParent:
    family = "COMP"
    OPType = "containerCOMP"

    def __init__(self, registry, path="/project1", viewer_sizes=None):
        self.path = path
        self.name = "project1"
        self.valid = True
        self._children = {}
        self._registry = registry
        self._viewer_sizes = viewer_sizes or [2274, 55000, 55000]
        self.created = []

    def op(self, name):
        return self._children.get(name)

    def add(self, op_obj):
        self._children[op_obj.name] = op_obj
        self._registry[op_obj.path] = op_obj
        return op_obj

    def create(self, optype, name):
        v = FakeViewer(f"{self.path}/{name}", self._viewer_sizes, self)
        self._children[name] = v
        self._registry[v.path] = v
        self.created.append(v)
        return v

    def _remove(self, op_obj):
        self._children.pop(op_obj.name, None)
        self._registry.pop(op_obj.path, None)


def _load_capture(monkeypatch, registry):
    if str(_MODULES_DIR) not in sys.path:
        sys.path.append(str(_MODULES_DIR))
    td_stub = types.ModuleType("td")
    td_stub.op = lambda path: registry.get(path)
    monkeypatch.setitem(sys.modules, "td", td_stub)
    spec = importlib.util.spec_from_file_location("td_capture_service_undertest", _CAPTURE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prime_returns_handle_and_does_not_destroy(monkeypatch):
    registry = {}
    parent = FakeParent(registry)
    pop = FakePop("/project1/pts", parent)
    parent.add(pop)
    mod = _load_capture(monkeypatch, registry)
    svc = mod.CaptureService()

    r = svc.capture_op_viewer("/project1/pts", prime_only=True)
    assert r["success"] is True, r.get("error")
    d = r["data"]
    assert d["two_phase"] is True
    assert d["handle"] == "/project1/temp_opviewer_capture_pts"   # per-target name
    assert d["operator_path"] == "/project1/pts"
    # primed but NOT destroyed — phase 2 owns cleanup
    assert parent.created[0].destroyed is False


def test_pull_converges_and_destroys_and_merges_pop_info(monkeypatch):
    registry = {}
    parent = FakeParent(registry, viewer_sizes=[2274, 55000, 55000])
    pop = FakePop("/project1/pts", parent, num_points=10000)
    parent.add(pop)
    mod = _load_capture(monkeypatch, registry)
    svc = mod.CaptureService()

    prime = svc.capture_op_viewer("/project1/pts", prime_only=True)
    handle = prime["data"]["handle"]
    viewer = parent.created[0]

    r = svc.pull_op_viewer(handle, operator_path="/project1/pts", format="png")
    assert r["success"] is True, r.get("error")
    d = r["data"]
    assert d["type"] == "image"
    assert d["family"] == "POP"
    assert d["bytes_raw"] == 55000            # the full frame, not the 2 KB plateau
    assert d["two_phase"] is True
    # POP info sidecar merged
    assert d["num_points"] == 10000
    assert d["bounds"]["min"] == [-1, -1, -1]
    assert d["bounds"]["max"] == [1, 1, 1]
    # size-stability: stopped after two equal 55000 pulls (did not exhaust 6)
    assert d["pulls"] == 2
    # temp viewer destroyed (no leak) and gone from the parent
    assert viewer.destroyed is True
    assert parent.op("temp_opviewer_capture_pts") is None


def test_pull_missing_handle_errors_without_leak(monkeypatch):
    registry = {}
    parent = FakeParent(registry)
    mod = _load_capture(monkeypatch, registry)
    svc = mod.CaptureService()

    r = svc.pull_op_viewer("/project1/does_not_exist", operator_path="/project1/pts")
    assert r["success"] is False
    assert "handle not found" in r["error"].lower()


def test_prime_cleans_up_stale_viewer_first(monkeypatch):
    registry = {}
    parent = FakeParent(registry)
    pop = FakePop("/project1/pts", parent)
    parent.add(pop)
    # a leaked viewer for THIS target from a prior aborted call, under its per-target name
    stale = FakeViewer("/project1/temp_opviewer_capture_pts", [1], parent)
    parent._children[stale.name] = stale
    registry[stale.path] = stale
    mod = _load_capture(monkeypatch, registry)
    svc = mod.CaptureService()

    svc.capture_op_viewer("/project1/pts", prime_only=True)
    assert stale.destroyed is True            # cleaned up before create()


def test_overlapping_sibling_primes_do_not_cross_wire(monkeypatch):
    # Two two-phase captures of SIBLING ops (same parent) whose prime phases overlap
    # must NOT collide: priming ptsB must not destroy ptsA's still-primed viewer, and
    # the two handles must differ so ptsA's phase-2 pull can only ever resolve ptsA's
    # own viewer. Regression for the deterministic per-parent name that let one
    # capture return the other operator's image mislabeled with the first op's path.
    registry = {}
    parent = FakeParent(registry)
    pop_a = FakePop("/project1/ptsA", parent)
    pop_b = FakePop("/project1/ptsB", parent)
    parent.add(pop_a)
    parent.add(pop_b)
    mod = _load_capture(monkeypatch, registry)
    svc = mod.CaptureService()

    prime_a = svc.capture_op_viewer("/project1/ptsA", prime_only=True)
    viewer_a = parent.created[0]
    prime_b = svc.capture_op_viewer("/project1/ptsB", prime_only=True)

    handle_a = prime_a["data"]["handle"]
    handle_b = prime_b["data"]["handle"]
    # distinct node paths per target -> no shared name for the sibling prime to clobber
    assert handle_a == "/project1/temp_opviewer_capture_ptsA"
    assert handle_b == "/project1/temp_opviewer_capture_ptsB"
    assert handle_a != handle_b
    # priming the sibling did NOT destroy ptsA's still-primed viewer
    assert viewer_a.destroyed is False

    # ptsA's phase-2 pull resolves ptsA's OWN viewer and is labeled ptsA (not ptsB)
    r = svc.pull_op_viewer(handle_a, operator_path="/project1/ptsA", format="png")
    assert r["success"] is True, r.get("error")
    assert r["data"]["operator_path"] == "/project1/ptsA"
    assert viewer_a.destroyed is True                              # its own pull cleaned it up
    # ptsB's viewer is untouched by ptsA's pull, still available for ptsB's own pull
    assert parent.op("temp_opviewer_capture_ptsB") is not None


def test_top_prime_is_direct_no_two_phase(monkeypatch):
    registry = {}
    top = FakeTop("/project1/noise1")
    registry[top.path] = top
    mod = _load_capture(monkeypatch, registry)
    svc = mod.CaptureService()

    r = svc.capture_op_viewer("/project1/noise1", prime_only=True)
    assert r["success"] is True, r.get("error")
    assert r["data"]["type"] == "image"
    assert not r["data"].get("two_phase")     # TOP returns full result in phase 1


def test_capture_pop_info_shape(monkeypatch):
    registry = {}
    parent = FakeParent(registry)
    pop = FakePop("/project1/pts", parent, num_points=42)
    parent.add(pop)
    mod = _load_capture(monkeypatch, registry)
    svc = mod.CaptureService()

    r = svc._capture_pop_info(pop)
    assert r["success"] is True
    assert r["data"]["family"] == "POP"
    assert r["data"]["num_points"] == 42
    assert r["data"]["bounds"]["size"] == [2, 2, 2]


# ---------------------------------------------------------------------------
# td_live_client.capture_op_viewer — two-step orchestration
# ---------------------------------------------------------------------------


def _load_client():
    if str(_LIVE_CLIENT_DIR) not in sys.path:
        sys.path.insert(0, str(_LIVE_CLIENT_DIR))
    spec = importlib.util.spec_from_file_location("td_live_client_twophase_undertest", _LIVE_CLIENT_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["td_live_client_twophase_undertest"] = module
    spec.loader.exec_module(module)
    return module


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _PhaseClient:
    """Fake TDClient: returns a scripted payload per POST based on the 'phase' field."""

    def __init__(self, prime_payload, pull_payload=None):
        self.prime_payload = prime_payload
        self.pull_payload = pull_payload
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, endpoint, json=None):
        self.posts.append(json)
        if json.get("phase") == "pull":
            return _Resp(self.pull_payload)
        return _Resp(self.prime_payload)


@pytest.fixture(scope="module")
def client_mod():
    return _load_client()


def test_client_two_phase_sleeps_then_pulls(client_mod, monkeypatch):
    prime = {"success": True, "data": {"two_phase": True, "handle": "/project1/temp_opviewer_capture",
                                       "operator_path": "/project1/pts", "family": "POP"}}
    pull = {"success": True, "data": {"type": "image", "image_base64": "AAAA", "format": "png",
                                      "width": 512, "height": 512, "family": "POP",
                                      "operator_path": "/project1/pts", "num_points": 10000,
                                      "bounds": {"min": [-1, -1, -1], "max": [1, 1, 1]},
                                      "two_phase": True, "pulls": 2, "pull_sizes": [2274, 55000]}}
    fake = _PhaseClient(prime, pull)
    monkeypatch.setattr(client_mod, "TDClient", lambda *a, **k: fake)

    slept = {}

    async def _fake_sleep(secs):
        slept["secs"] = secs

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fake_sleep)

    out = asyncio.run(client_mod.capture_op_viewer({"operator_path": "/project1/pts"}))
    # slept between the two requests, on our own thread
    assert slept.get("secs") and slept["secs"] > 0
    # two requests: prime then pull
    assert [p.get("phase") for p in fake.posts] == ["prime", "pull"]
    assert fake.posts[1]["handle"] == "/project1/temp_opviewer_capture"
    # rendered image + POP caption
    kinds = [type(item).__name__ for item in out]
    assert "ImageContent" in kinds
    caption = [i.text for i in out if type(i).__name__ == "TextContent"][0]
    assert "POP points: 10000" in caption


def test_client_direct_family_no_sleep_no_pull(client_mod, monkeypatch):
    # A TOP returns a full image on phase 1 (no two_phase) -> no wait, no 2nd request.
    prime = {"success": True, "data": {"type": "image", "image_base64": "BBBB", "format": "jpeg",
                                       "width": 256, "height": 256, "family": "TOP",
                                       "operator_path": "/project1/noise1"}}
    fake = _PhaseClient(prime)
    monkeypatch.setattr(client_mod, "TDClient", lambda *a, **k: fake)

    called = {"sleep": False}

    async def _fake_sleep(secs):
        called["sleep"] = True

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fake_sleep)

    out = asyncio.run(client_mod.capture_op_viewer({"operator_path": "/project1/noise1"}))
    assert called["sleep"] is False
    assert [p.get("phase") for p in fake.posts] == ["prime"]
    assert any(type(i).__name__ == "ImageContent" for i in out)


# ---------------------------------------------------------------------------
# W-B addendum — warming handshake (growth-guarded pull) + SOP image capture
# ---------------------------------------------------------------------------


def test_pull_without_growth_returns_warming_and_keeps_viewer(monkeypatch):
    # UI hasn't drawn since the prime: every pull returns the prime-size blank.
    # The pull must NOT accept that plateau — it hands back a warming receipt
    # and keeps the viewer alive for the client's retry.
    registry = {}
    parent = FakeParent(registry, viewer_sizes=[2274, 2274, 2274, 2274, 2274, 2274])
    pop = FakePop("/project1/pts", parent)
    parent.add(pop)
    svc_mod = _load_capture(monkeypatch, registry)
    svc = svc_mod.CaptureService()

    r1 = svc.capture_op_viewer(pop.path, prime_only=True)
    handle = r1["data"]["handle"]
    primed = r1["data"]["primed_bytes"]
    assert primed == 2274

    r2 = svc.pull_op_viewer(handle, operator_path=pop.path, primed_bytes=primed)
    assert r2["success"] is True
    assert r2["data"]["type"] == "op_viewer_warming"
    viewer = registry.get(handle)
    assert viewer is not None and viewer.valid and not viewer.destroyed

    # Best-effort final attempt (no primed_bytes) accepts stability + destroys.
    r3 = svc.pull_op_viewer(handle, operator_path=pop.path)
    assert r3["success"] is True
    assert r3["data"]["type"] == "image"
    assert registry.get(handle) is None


def test_pull_with_growth_accepts_and_destroys(monkeypatch):
    registry = {}
    parent = FakeParent(registry, viewer_sizes=[2274, 55000, 55000])
    pop = FakePop("/project1/pts", parent)
    parent.add(pop)
    svc_mod = _load_capture(monkeypatch, registry)
    svc = svc_mod.CaptureService()

    r1 = svc.capture_op_viewer(pop.path, prime_only=True)
    r2 = svc.pull_op_viewer(
        r1["data"]["handle"], operator_path=pop.path,
        primed_bytes=r1["data"]["primed_bytes"],
    )
    assert r2["data"]["type"] == "image"
    assert r2["data"]["bytes_raw"] == 55000
    assert registry.get(r1["data"]["handle"]) is None


class FakeSop:
    family = "SOP"
    OPType = "boxSOP"

    def __init__(self, path, parent):
        self.path = path
        self.name = path.rsplit("/", 1)[-1]
        self.valid = True
        self.numPoints = 8
        self.numPrims = 6
        self.numVertices = 24
        self.pointBoundingBox = _BBox()
        self.nodeX = 0
        self.nodeY = 0
        self._parent = parent

    def parent(self):
        return self._parent


def test_sop_routes_two_phase_with_info_sidecar(monkeypatch):
    # SOPs render a real image via the op-viewer path (proven live 2026-07-14);
    # the old text-only geometry info rides along as a sidecar like POPs.
    registry = {}
    parent = FakeParent(registry, viewer_sizes=[2274, 61000, 61000])
    sop = FakeSop("/project1/box1", parent)
    parent.add(sop)
    svc_mod = _load_capture(monkeypatch, registry)
    svc = svc_mod.CaptureService()

    r1 = svc.capture_op_viewer(sop.path, prime_only=True)
    assert r1["success"] is True
    assert r1["data"].get("two_phase") is True

    r2 = svc.pull_op_viewer(
        r1["data"]["handle"], operator_path=sop.path,
        primed_bytes=r1["data"]["primed_bytes"],
    )
    d = r2["data"]
    assert d["type"] == "image"
    assert d["family"] == "SOP"
    assert d["num_points"] == 8
    assert d["num_prims"] == 6
    assert d["num_vertices"] == 24
    assert d["bounds"]["size"] == [2, 2, 2]


class _SeqPhaseClient(_PhaseClient):
    """Pull payloads consumed in order (warming ... then the final image)."""

    def __init__(self, prime_payload, pull_payloads):
        super().__init__(prime_payload)
        self.pull_payloads = list(pull_payloads)

    async def post(self, endpoint, json=None):
        self.posts.append(json)
        if json.get("phase") == "pull":
            return _Resp(self.pull_payloads.pop(0))
        return _Resp(self.prime_payload)


def test_client_retries_on_warming_then_renders(client_mod, monkeypatch):
    prime = {"success": True, "data": {"two_phase": True,
                                       "handle": "/project1/temp_opviewer_capture_pts",
                                       "operator_path": "/project1/pts", "family": "POP",
                                       "primed_bytes": 2274}}
    warming = {"success": True, "data": {"type": "op_viewer_warming", "two_phase": True,
                                         "handle": "/project1/temp_opviewer_capture_pts",
                                         "operator_path": "/project1/pts",
                                         "primed_bytes": 2274, "pull_sizes": [2274, 2274]}}
    full = {"success": True, "data": {"type": "image", "image_base64": "AAAA", "format": "png",
                                      "width": 512, "height": 512, "family": "POP",
                                      "operator_path": "/project1/pts",
                                      "two_phase": True, "pulls": 1, "pull_sizes": [70400]}}
    fake = _SeqPhaseClient(prime, [warming, full])
    monkeypatch.setattr(client_mod, "TDClient", lambda *a, **k: fake)

    sleeps = []

    async def _fake_sleep(secs):
        sleeps.append(secs)

    monkeypatch.setattr(client_mod.asyncio, "sleep", _fake_sleep)

    out = asyncio.run(client_mod.capture_op_viewer({"operator_path": "/project1/pts"}))
    assert any(type(i).__name__ == "ImageContent" for i in out)
    pulls = [p for p in fake.posts if p.get("phase") == "pull"]
    assert len(pulls) == 2
    # growth-guarded attempts carry the prime size forward
    assert pulls[0]["primed_bytes"] == 2274
    # first wait is the short one (0.1 s, not the old 0.5 s), retries slightly longer
    assert len(sleeps) == 2
    assert sleeps[0] == pytest.approx(0.1)
    assert sleeps[1] == pytest.approx(0.15)

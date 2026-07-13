"""Wave 5 — server<->KB version-compat pure logic + the mismatched-manifest fixture.

Exercises the branches the shipped happy path (0.2.0 == 0.2.0) never reaches: minor/major
mismatches, and every malformed version form degrading to "unknown" WITHOUT raising at boot.
KB-free (pure functions + a temp manifest) -- no server load, runs on the CI KB-free lane.
"""
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/unit/ -> repo root
_SERVER_CORE = _REPO_ROOT / "MCP" / "server_core"
if str(_SERVER_CORE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CORE))

import compat  # noqa: E402


@pytest.mark.parametrize("server,kb,expected", [
    ("0.2.0", "0.2.0", True),   # happy path
    ("0.2.0", "0.2.1", True),   # patch difference ignored
    ("0.2.0", "0.2.99", True),
    ("0.2.0", "0.3.0", False),  # minor bump == breaking (pre-1.0 semantics)
    ("0.2.0", "1.2.0", False),  # major bump
    ("1.4.0", "1.4.7", True),
])
def test_semver_minor_comparison(server, kb, expected):
    r = compat.compat_status(server, kb)
    assert r["compatible"] is expected
    assert r["status"] == ("compatible" if expected else "incompatible")
    assert r["policy"] == "warn"
    assert r["server_version"] == server and r["kb_version"] == kb


@pytest.mark.parametrize("bad", [
    None, "", "0", "0.2", "0.2.0-alpha", "0.2.0.1", "0.99.2025.32460",
    "x.y.z", "v0.2.0", "0.2.x", 42, 0.2,
])
def test_unparseable_version_is_unknown_never_raises(bad):
    # bad in the KB slot ...
    r = compat.compat_status("0.2.0", bad)
    assert r["compatible"] is None and r["status"] == "unknown"
    # ... and symmetrically in the server slot.
    r2 = compat.compat_status(bad, "0.2.0")
    assert r2["compatible"] is None and r2["status"] == "unknown"


def test_td_build_is_informational_never_parsed():
    """A 4-part td_build string passes through untouched and never affects the verdict."""
    r = compat.compat_status("0.2.0", "0.2.0", td_build="0.99.2025.32460")
    assert r["compatible"] is True
    assert r["kb_td_build"] == "0.99.2025.32460"
    # td_build shape in the version slot is 'unknown', proving it is not treated as semver.
    assert compat.compat_status("0.2.0", "0.99.2025.32460")["status"] == "unknown"
    # F4: an advisory notice is present and quotes the build; the verdict is untouched.
    assert isinstance(r["td_build_notice"], str) and r["td_build_notice"]
    assert "0.99.2025.32460" in r["td_build_notice"]
    assert "get_td_info" in r["td_build_notice"]


def test_td_build_notice_absent_when_no_build():
    """F4: no td_build supplied => notice is None; existing verdict fields unchanged."""
    r = compat.compat_status("0.2.0", "0.2.0")
    assert r["td_build_notice"] is None
    assert r["compatible"] is True and r["status"] == "compatible"


def test_read_kb_version_roundtrip_and_missing(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"version": "9.9.0"}), encoding="utf-8")
    assert compat.read_kb_version(tmp_path) == "9.9.0"
    # missing dir / unreadable -> None, never raises
    assert compat.read_kb_version(tmp_path / "nope") is None
    # malformed manifest (not JSON) -> None
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    assert compat.read_kb_version(tmp_path) is None
    # manifest without a version key -> None
    (tmp_path / "manifest.json").write_text(json.dumps({"td_build": "x"}), encoding="utf-8")
    assert compat.read_kb_version(tmp_path) is None


def test_mismatched_manifest_fixture_fires(tmp_path):
    """Required 'mismatched-manifest' fixture: a temp manifest.json whose version differs
    from the server flags incompatible through the same pipeline the server boots."""
    (tmp_path / "manifest.json").write_text(
        json.dumps({"version": "9.9.0", "td_build": "0.99.2025.32460"}), encoding="utf-8")
    kb_version = compat.read_kb_version(tmp_path)
    r = compat.compat_status("0.2.0", kb_version, td_build="0.99.2025.32460")
    assert r["compatible"] is False
    assert r["status"] == "incompatible"
    assert r["kb_version"] == "9.9.0"

"""Registration CLI end-to-end (BUG-3 rider; W7 rework).

Builds a real component .tox with ToxBuilder, registers it via
kb_build/register_user_component.py (subprocess — the actual user entry point),
and checks the written registry entry (offline grounding stamp included).

W7: `--emit-chunks` is retired — the real search integration is the engine
(kb_build/user_components.py). The chunk-shape assertions now run the engine's
component_block_rows over the CLI-written entry (`user:`-namespaced ids, meta
contract); the ingest/retrieval halves live in tests/retrieval_user/ (local
kb-full lane) and tests/unit/test_user_components_engine.py (hermetic).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from paths import resolve_td_tool  # noqa: E402
from meta_agentic.execution.tox_builder import ToxBuilder  # noqa: E402
from kb_build import user_components as uc  # noqa: E402

pytestmark = [
    pytest.mark.requires_kb,
    pytest.mark.skipif(
        resolve_td_tool("toeexpand") is None or resolve_td_tool("toecollapse") is None,
        reason="TouchDesigner tools (toeexpand/toecollapse) not installed",
    ),
]

SCRIPT = _REPO_ROOT / "kb_build" / "register_user_component.py"


@pytest.fixture(scope="module")
def fixture_tox(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("regfix")
    ops = [
        {"name": "in1", "type": "in", "family": "CHOP", "position": [0, 0]},
        {"name": "valueOut", "type": "out", "family": "CHOP", "position": [200, 0]},
        {"name": "chansOut", "type": "out", "family": "CHOP", "position": [200, 150]},
    ]
    tox = ToxBuilder(out, verbose=False).build_tox({"operators": ops}, "myComp")
    assert tox is not None and tox.exists()
    return tox


def test_register_writes_entry(fixture_tox, tmp_path):
    reg = tmp_path / "user_components.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(fixture_tox), "--registry", str(reg)],
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr or proc.stdout

    spec = json.loads(reg.read_text(encoding="utf-8"))
    entry = spec["components"]["myComp"]
    assert entry["source"] == "project"
    assert entry["tox_path"].endswith("myComp.tox")
    assert entry["harvest"]["method"] == "offline_manifest", \
        "offline grounding stamp drives the builder's strict wiring policy"
    assert [d["in_op"] for d in entry["inputs"]] == ["in1"]
    # offline manifests NAME-SORT: chansOut before valueOut, indexes are name order
    assert [d["out_op"] for d in entry["outputs"]] == ["chansOut", "valueOut"]
    assert entry["wrapper"] is False
    # W7: the CLI writes the semantic half too (placeholder summary; the MCP
    # tool is the authored + ingested surface)
    assert entry["summary"]
    assert entry["contained_operators"], "interface-scoped inventory recorded"

    # engine rows over the CLI-written entry (replaces the --emit-chunks check)
    rows = uc.component_block_rows("myComp", entry)
    assert [r["chunk_type"] for r in rows] == \
        ["block_overview", "block_usecase", "block_io"]
    assert rows[0]["id"] == "user:block:mycomp:overview"
    for r in rows:
        assert set(r) >= {"id", "text", "chunk_type", "parent_chunk", "meta"}
        assert r["meta"]["type"] == r["chunk_type"]
        assert r["meta"]["__source_store"] == "td_block"
        assert r["meta"]["license_tier"] == "user"
    assert rows[1]["parent_chunk"] == rows[0]["id"]


def test_emit_chunks_flag_is_retired(fixture_tox, tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(fixture_tox),
         "--registry", str(tmp_path / "r.json"),
         "--emit-chunks", str(tmp_path / "chunks")],
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 2, "argparse must reject the retired flag"


def test_reregister_updates_in_place(fixture_tox, tmp_path):
    reg = tmp_path / "user_components.json"
    for expected in ("registered", "updated"):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(fixture_tox), "--registry", str(reg)],
            capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr or proc.stdout
        assert expected in proc.stdout
    spec = json.loads(reg.read_text(encoding="utf-8"))
    assert list(spec["components"]) == ["myComp"]

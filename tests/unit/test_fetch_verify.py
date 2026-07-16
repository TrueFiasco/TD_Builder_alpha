"""W2d — fetch_vector_db.py verifies BEFORE extracting, on BOTH download paths.

Hermetic: downloads are stubbed (no network, no gh); the "release zip" is
built in tmp. Locks in the fetch-side half of the trust boundary:
  - zip sha256 mismatch -> SystemExit with NOTHING extracted (HTTPS and gh);
  - artifact pins checked after extract (publishing-skew tripwire);
  - a receipt is written for the verified extraction.
"""
import hashlib
import importlib.util
import json
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

import kb_integrity as ki  # noqa: E402

GPICKLE = "knowledge_graph_enhanced.gpickle"
BM25 = "lexical_index/bm25.pkl"


@pytest.fixture()
def fetch(monkeypatch, tmp_path):
    """A fresh fetch_vector_db module wired to a tmp repo layout."""
    spec = importlib.util.spec_from_file_location(
        "_w2d_fetch", str(_REPO_ROOT / "scripts" / "fetch_vector_db.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_w2d_fetch"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "KB_DIR", tmp_path / "KB")
    monkeypatch.setattr(mod, "MANIFEST", tmp_path / "vector_db_release.json")
    monkeypatch.setattr(mod, "_kb_integrity", lambda: ki)
    return mod


def _make_zip(tmp_path) -> tuple[Path, dict]:
    """Build a fake release zip; return (zip_path, correct artifact pins)."""
    src = tmp_path / "zip_src"
    (src / "lexical_index").mkdir(parents=True)
    (src / GPICKLE).write_bytes(b"graph-bytes-v1")
    (src / BM25).write_bytes(b"bm25-bytes-v1")
    zp = tmp_path / "kb.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.write(src / GPICKLE, GPICKLE)
        zf.write(src / BM25, BM25)
    pins = {GPICKLE: hashlib.sha256(b"graph-bytes-v1").hexdigest(),
            BM25: hashlib.sha256(b"bm25-bytes-v1").hexdigest()}
    return zp, pins


def _manifest(fetch, zp: Path, pins=None, sha=None):
    m = {"repo": "x/y", "tag": "vT", "asset": "kb.zip",
         "sha256": sha if sha is not None else ki.sha256_file(zp)}
    if pins is not None:
        m["artifact_sha256"] = pins
    fetch.MANIFEST.write_text(json.dumps(m), encoding="utf-8")


def _stub_https(fetch, monkeypatch, zp: Path, succeed=True):
    calls = []

    def fake(url, dest):
        calls.append(url)
        if succeed:
            shutil.copyfile(zp, dest)
        return succeed

    monkeypatch.setattr(fetch, "_download_https", fake)
    return calls


def _stub_gh(fetch, monkeypatch, zp: Path, succeed=True):
    calls = []

    def fake(repo, tag, asset, out_dir):
        calls.append((repo, tag, asset))
        if succeed:
            shutil.copyfile(zp, Path(out_dir) / asset)
        return succeed

    monkeypatch.setattr(fetch, "_download_gh", fake)
    return calls


def test_https_good_sha_extracts_and_receipts(fetch, monkeypatch, tmp_path, capsys):
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins)
    _stub_https(fetch, monkeypatch, zp)
    assert fetch.main() == 0
    assert (fetch.KB_DIR / GPICKLE).exists() and (fetch.KB_DIR / BM25).exists()
    out = capsys.readouterr().out
    assert "SHA256 verified" in out and "Artifact pins verified" in out
    receipt = json.loads((fetch.KB_DIR / ki.RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt["source"] == "fetch_vector_db"
    assert receipt["artifacts"][GPICKLE]["sha256"] == pins[GPICKLE]


def test_https_bad_sha_refuses_before_extract(fetch, monkeypatch, tmp_path):
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins, sha="0" * 64)
    _stub_https(fetch, monkeypatch, zp)
    with pytest.raises(SystemExit) as exc:
        fetch.main()
    assert "SHA256 mismatch" in str(exc.value)
    assert not (fetch.KB_DIR / GPICKLE).exists()   # nothing extracted
    assert not (fetch.KB_DIR / ki.RECEIPT_NAME).exists()


def test_gh_fallback_good_sha_extracts_and_receipts(fetch, monkeypatch, tmp_path):
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins)
    _stub_https(fetch, monkeypatch, zp, succeed=False)
    gh_calls = _stub_gh(fetch, monkeypatch, zp)
    assert fetch.main() == 0
    assert gh_calls == [("x/y", "vT", "kb.zip")]
    assert (fetch.KB_DIR / GPICKLE).exists()
    assert (fetch.KB_DIR / ki.RECEIPT_NAME).exists()


def test_gh_fallback_bad_sha_refuses_before_extract(fetch, monkeypatch, tmp_path):
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins, sha="f" * 64)
    _stub_https(fetch, monkeypatch, zp, succeed=False)
    _stub_gh(fetch, monkeypatch, zp)
    with pytest.raises(SystemExit) as exc:
        fetch.main()
    assert "SHA256 mismatch" in str(exc.value)
    assert not (fetch.KB_DIR / GPICKLE).exists()


def test_artifact_pin_skew_fails_loud_and_unreceipted(fetch, monkeypatch, tmp_path):
    """Zip verifies but a pin disagrees = the manifest and the published zip
    drifted (publishing mistake). Fail the fetch; leave no receipt behind."""
    zp, pins = _make_zip(tmp_path)
    pins[BM25] = "a" * 64
    _manifest(fetch, zp, pins)
    _stub_https(fetch, monkeypatch, zp)
    with pytest.raises(SystemExit) as exc:
        fetch.main()
    assert "pin mismatch" in str(exc.value)
    assert not (fetch.KB_DIR / ki.RECEIPT_NAME).exists()


def test_no_pins_warns_but_receipts(fetch, monkeypatch, tmp_path, capsys):
    """Older manifest without artifact_sha256: fetch still succeeds and the
    receipt becomes the only load-time anchor."""
    zp, _ = _make_zip(tmp_path)
    _manifest(fetch, zp, pins=None)
    _stub_https(fetch, monkeypatch, zp)
    assert fetch.main() == 0
    assert "no artifact_sha256 pins" in capsys.readouterr().out
    assert (fetch.KB_DIR / ki.RECEIPT_NAME).exists()


# ---------------------------------------------------------------------------
# KB health gate — _already_populated must not say "nothing to do" on a
# vector_db that holds zero documents (the loop-trap: the MCP server says
# "run fetch_vector_db.py", this script said "already populated").
# ---------------------------------------------------------------------------

def _populate_kb(fetch, *, sqlite=True):
    """Full file-level KB layout; contents are stand-ins, health comes from
    the (monkeypatched) _vector_db_doc_count seam."""
    kb = fetch.KB_DIR
    vdb = kb / "vector_db"
    vdb.mkdir(parents=True)
    (vdb / ("chroma.sqlite3" if sqlite else "stray.bin")).write_bytes(b"x")
    (kb / "operators.json").write_text("{}", encoding="utf-8")
    (kb / "lexical_index").mkdir()
    (kb / "lexical_index" / "bm25.pkl").write_bytes(b"x")
    (kb / "models" / "ms-marco-MiniLM-L-6-v2").mkdir(parents=True)
    (kb / "models" / "ms-marco-MiniLM-L-6-v2" / "config.json").write_text("{}", encoding="utf-8")
    return vdb


def test_already_populated_false_on_zero_count(fetch, monkeypatch):
    _populate_kb(fetch)
    monkeypatch.setattr(fetch, "_vector_db_doc_count", lambda vdb: 0)
    assert fetch._already_populated() is False


def test_already_populated_true_on_healthy_count(fetch, monkeypatch, capsys):
    _populate_kb(fetch)
    monkeypatch.setattr(fetch, "_vector_db_doc_count", lambda vdb: 4321)
    assert fetch._already_populated() is True
    # main() short-circuits before ever loading the (absent) manifest.
    assert fetch.main() == 0
    assert "already populated" in capsys.readouterr().out


def test_already_populated_false_when_unmeasurable(fetch, monkeypatch):
    """Seam None = chroma.sqlite3 absent (sqlite-probe contract). The old
    'no chromadb: fall back to the file-level answer' case is gone — the
    stdlib probe needs no installed deps. Unmeasurable is not populated."""
    _populate_kb(fetch)
    monkeypatch.setattr(fetch, "_vector_db_doc_count", lambda vdb: None)
    assert fetch._already_populated() is False


def test_already_populated_false_without_chroma_sqlite(fetch, monkeypatch):
    """A non-empty vector_db that is not a Chroma store is not populated —
    the caller short-circuits on the missing sqlite without consulting the
    count seam."""
    _populate_kb(fetch, sqlite=False)

    def _must_not_measure(vdb):
        raise AssertionError("count seam consulted despite missing chroma.sqlite3")

    monkeypatch.setattr(fetch, "_vector_db_doc_count", _must_not_measure)
    assert fetch._already_populated() is False


# ---------------------------------------------------------------------------
# The real _vector_db_doc_count seam — stdlib sqlite READ-ONLY probe (review
# F1). The chromadb probe it replaced kept chroma.sqlite3 open for process
# lifetime (no close API), so on Windows _retire_unhealthy_vector_db's rename
# failed against the script's OWN handle (WinError 5) while the error blamed
# a phantom running MCP server. Schema mimic below is derived from the two
# real stores on the machine that hit the trap (broken: chroma tables present
# but no td_unified row; healthy: td_unified + one row per doc in embeddings).
# ---------------------------------------------------------------------------

def _make_chroma_sqlite(vdb: Path, *, docs: int = 0, collection: str | None = "td_unified"):
    """Minimal stand-in for Chroma's sqlite, mirroring exactly the schema
    slice the probe queries: collections(id, name), segments(id, collection),
    embeddings(id, segment_id). Built with stdlib sqlite3 — no binary fixture,
    no chromadb."""
    vdb.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(vdb / "chroma.sqlite3"))
    try:
        conn.executescript(
            "CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT);"
            "CREATE TABLE segments (id TEXT PRIMARY KEY, type TEXT, scope TEXT,"
            "                       collection TEXT);"
            "CREATE TABLE embeddings (id INTEGER PRIMARY KEY, segment_id TEXT,"
            "                         embedding_id TEXT);"
        )
        if collection is not None:
            conn.execute("INSERT INTO collections (id, name) VALUES ('col-1', ?)",
                         (collection,))
            conn.execute("INSERT INTO segments VALUES "
                         "('seg-meta', 'urn:chroma:segment/metadata/sqlite',"
                         " 'METADATA', 'col-1')")
            conn.execute("INSERT INTO segments VALUES "
                         "('seg-vec', 'urn:chroma:segment/vector/hnsw-local-persisted',"
                         " 'VECTOR', 'col-1')")
            conn.executemany(
                "INSERT INTO embeddings (segment_id, embedding_id) VALUES ('seg-meta', ?)",
                [(f"doc-{i}",) for i in range(docs)])
        conn.commit()
    finally:
        conn.close()


def test_doc_count_none_when_sqlite_absent(fetch, tmp_path):
    """Contract: None = chroma.sqlite3 does not exist (nothing to measure)."""
    vdb = tmp_path / "vector_db"
    vdb.mkdir()
    (vdb / "stray.bin").write_bytes(b"x")
    assert fetch._vector_db_doc_count(vdb) is None


def test_doc_count_zero_when_td_unified_missing(fetch, tmp_path):
    """The real broken-store shape: chroma schema present, td_unified never
    created -> measured 0."""
    vdb = tmp_path / "vector_db"
    _make_chroma_sqlite(vdb, collection=None)
    assert fetch._vector_db_doc_count(vdb) == 0


def test_doc_count_zero_on_empty_collection(fetch, tmp_path):
    vdb = tmp_path / "vector_db"
    _make_chroma_sqlite(vdb, docs=0)
    assert fetch._vector_db_doc_count(vdb) == 0


def test_doc_count_measures_td_unified_embeddings(fetch, tmp_path):
    vdb = tmp_path / "vector_db"
    _make_chroma_sqlite(vdb, docs=7)
    assert fetch._vector_db_doc_count(vdb) == 7


def test_doc_count_zero_on_non_sqlite_garbage(fetch, tmp_path):
    """Corrupt/not-a-database file = measured unusable (0), matching the old
    chroma-level-failure semantics — never an exception, never None."""
    vdb = tmp_path / "vector_db"
    vdb.mkdir()
    (vdb / "chroma.sqlite3").write_bytes(b"this is not a sqlite database")
    assert fetch._vector_db_doc_count(vdb) == 0


def test_doc_count_zero_on_foreign_sqlite_schema(fetch, tmp_path):
    """Valid sqlite that is not a Chroma store (no chroma tables) -> 0."""
    vdb = tmp_path / "vector_db"
    vdb.mkdir()
    conn = sqlite3.connect(str(vdb / "chroma.sqlite3"))
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()
    assert fetch._vector_db_doc_count(vdb) == 0


def test_doc_count_probe_releases_handle_for_rename(fetch, tmp_path):
    """F1 regression: probe then rename IN THE SAME PROCESS must succeed.
    The chromadb probe kept the sqlite handle for process lifetime, so this
    exact sequence died with WinError 5 on Windows."""
    vdb = tmp_path / "vector_db"
    _make_chroma_sqlite(vdb, collection=None)   # the broken-store shape
    assert fetch._vector_db_doc_count(vdb) == 0
    graveyard = vdb.with_name("vector_db.bad-test")
    vdb.rename(graveyard)                        # PermissionError before the fix
    assert (graveyard / "chroma.sqlite3").exists()
    assert not vdb.exists()


def test_main_retires_empty_vector_db_before_extract(fetch, monkeypatch, tmp_path, capsys):
    """The trap dir is moved aside (never deleted) after sha-verify, pre-extract."""
    vdb = _populate_kb(fetch)
    monkeypatch.setattr(fetch, "_vector_db_doc_count", lambda p: 0)
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins)
    _stub_https(fetch, monkeypatch, zp)
    assert fetch.main() == 0
    graveyards = list(fetch.KB_DIR.glob("vector_db.bad-*"))
    assert len(graveyards) == 1                      # moved aside, not deleted
    assert (graveyards[0] / "chroma.sqlite3").exists()
    assert not vdb.exists()                          # zip carries no vector_db
    assert (fetch.KB_DIR / GPICKLE).exists()         # fresh extract landed
    assert "moving it aside" in capsys.readouterr().out


def test_main_leaves_healthy_vector_db_alone(fetch, monkeypatch, tmp_path):
    """Re-fetch triggered by a missing Phase-2 artifact must not disturb a
    healthy vector store."""
    vdb = _populate_kb(fetch)
    (fetch.KB_DIR / "lexical_index" / "bm25.pkl").unlink()  # forces re-fetch
    monkeypatch.setattr(fetch, "_vector_db_doc_count", lambda p: 4321)
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins)
    _stub_https(fetch, monkeypatch, zp)
    assert fetch.main() == 0
    assert vdb.exists() and (vdb / "chroma.sqlite3").exists()
    assert not list(fetch.KB_DIR.glob("vector_db.bad-*"))


def test_main_retire_move_failure_exits_actionable(fetch, monkeypatch, tmp_path):
    """Windows: a running MCP server holds chroma.sqlite3 open and the move
    fails — exit with the 'stop the MCP server' instruction, nothing extracted."""
    _populate_kb(fetch)
    monkeypatch.setattr(fetch, "_vector_db_doc_count", lambda p: 0)
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins)
    _stub_https(fetch, monkeypatch, zp)

    def _locked_rename(self, target):
        raise PermissionError(13, "The process cannot access the file", str(self))

    monkeypatch.setattr(type(fetch.KB_DIR), "rename", _locked_rename)
    with pytest.raises(SystemExit) as exc:
        fetch.main()
    assert "stop the MCP server" in str(exc.value)
    assert not (fetch.KB_DIR / GPICKLE).exists()     # exited before extract


def test_main_retires_broken_store_with_real_probe(fetch, monkeypatch, tmp_path):
    """End-to-end F1 proof, hermetic: a REAL sqlite in the broken-store shape,
    the REAL probe (no seam monkeypatch), then main() must retire-rename it
    and extract — all in one process. With the old chromadb probe the rename
    step raised WinError 5 against our own handle."""
    _populate_kb(fetch, sqlite=False)                # full KB layout, no store yet
    vdb = fetch.KB_DIR / "vector_db"
    (vdb / "stray.bin").unlink()
    _make_chroma_sqlite(vdb, collection=None)        # td_unified missing, like the real trap
    zp, pins = _make_zip(tmp_path)
    _manifest(fetch, zp, pins)
    _stub_https(fetch, monkeypatch, zp)
    assert fetch.main() == 0
    graveyards = list(fetch.KB_DIR.glob("vector_db.bad-*"))
    assert len(graveyards) == 1                      # rename SUCCEEDED in-process
    assert (graveyards[0] / "chroma.sqlite3").exists()
    assert (fetch.KB_DIR / GPICKLE).exists()         # fresh extract landed


def test_retire_graveyard_collision_uniquified(fetch, monkeypatch):
    """F2: same-second rerun — the .bad-<ts> target already exists. Uniquify
    with -1, -2, ... instead of colliding (rename onto an existing dir raises
    on Windows)."""
    vdb = _populate_kb(fetch)
    monkeypatch.setattr(fetch, "_vector_db_doc_count", lambda p: 0)
    monkeypatch.setattr(fetch.time, "strftime", lambda fmt: "20260716-120000")
    (fetch.KB_DIR / "vector_db.bad-20260716-120000").mkdir()
    (fetch.KB_DIR / "vector_db.bad-20260716-120000-1").mkdir()
    fetch._retire_unhealthy_vector_db()
    assert not vdb.exists()
    moved = fetch.KB_DIR / "vector_db.bad-20260716-120000-2"
    assert (moved / "chroma.sqlite3").exists()

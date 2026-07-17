"""KF1 — chromadb create-on-open guard.

chromadb has NO read-only open: ``PersistentClient`` is create-if-missing at
every construction site, so any consumer that boots against an absent or empty
vector store silently MANUFACTURES a ~188KB bare stub where the real store
belongs. That is the confirmed root cause of all three vector_db kills on the
dev machine (strikes 2 and 3 produced byte-identical stubs). A filesystem
read-only attribute was tried and empirically refuted: chromadb's rust
bindings open the sqlite file read-write even for pure reads.

The guard: ``search_docs.open_chroma_or_refuse`` probes the store with STDLIB
sqlite (read-only URI, deterministically closed — the
scripts/fetch_vector_db.py pattern) BEFORE anything chromadb-shaped runs, and
refuses loudly. The non-negotiable contract, pinned here:

    opening a missing/empty store RAISES and creates NO file.

Needs chromadb + sentence-transformers on sys.path (engine-kb lane), but no
real KB — every store below is a tmp fixture.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "MCP" / "server_core")):
    if p not in sys.path:
        sys.path.insert(0, p)

chromadb = pytest.importorskip("chromadb")

import search_docs as sd  # noqa: E402
from kb_build import user_components as uc  # noqa: E402


def _make_tiny_store(vdb: Path, collection: str = "td_unified", rows: int = 2):
    """A real, healthy Chroma store with `rows` tiny documents."""
    client = chromadb.PersistentClient(path=str(vdb))
    coll = client.create_collection(collection)
    coll.upsert(ids=[f"r{i}" for i in range(rows)],
                embeddings=[[0.0, 0.0, float(i + 1)] for i in range(rows)],
                documents=[f"doc {i}" for i in range(rows)])
    return coll


# ---------------------------------------------------------------------------
# the guard helper itself
# ---------------------------------------------------------------------------
def test_missing_store_raises_and_creates_no_file(tmp_path):
    vdb = tmp_path / "vector_db"                      # does not exist at all
    with pytest.raises(sd.ChromaStoreUnavailable):
        sd.open_chroma_or_refuse(vdb)
    assert not vdb.exists(), "the guard must not manufacture the directory"

    vdb.mkdir()                                       # exists but EMPTY
    with pytest.raises(sd.ChromaStoreUnavailable):
        sd.open_chroma_or_refuse(vdb)
    assert list(vdb.iterdir()) == [], "the guard must not manufacture a stub store"


def test_empty_collection_refused_via_min_docs(tmp_path):
    vdb = tmp_path / "vector_db"
    _make_tiny_store(vdb, rows=2)
    # wrong collection name: rows exist, but not under the requested collection
    with pytest.raises(sd.ChromaStoreUnavailable):
        sd.open_chroma_or_refuse(vdb, collection="nope")


def test_healthy_store_opens_and_counts(tmp_path):
    vdb = tmp_path / "vector_db"
    _make_tiny_store(vdb, rows=2)
    client, coll = sd.open_chroma_or_refuse(vdb)
    assert coll.count() == 2
    assert sd.chroma_store_doc_count(vdb) == 2
    assert sd.chroma_store_doc_count(tmp_path / "nowhere") is None


# ---------------------------------------------------------------------------
# TDDocSearch — the server/adapter constructor (mandated site search_docs:158)
# ---------------------------------------------------------------------------
def test_tddocsearch_refuses_missing_store_and_creates_nothing(tmp_path):
    vdb = tmp_path / "KB" / "vector_db"
    vdb.mkdir(parents=True)
    with pytest.raises(sd.ChromaStoreUnavailable):
        sd.TDDocSearch(vectordb_path=str(vdb))
    assert list(vdb.iterdir()) == [], \
        "TDDocSearch on an empty store manufactured files (create-on-open)"


# ---------------------------------------------------------------------------
# user store read path (kb_build/user_components._open_user_collection)
# ---------------------------------------------------------------------------
def test_user_collection_read_path_never_creates(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    vdb = tmp_path / "user_index" / "vector_db"

    # absent dir: (None, None), nothing created (pre-existing contract)
    assert uc._open_user_collection(create=False) == (None, None)
    assert not vdb.exists()

    # present-but-EMPTY dir: the old code mkdir'd + created a stub here
    vdb.mkdir(parents=True)
    assert uc._open_user_collection(create=False) == (None, None)
    assert list(vdb.iterdir()) == [], \
        "read path manufactured a stub store in an empty user vector_db"


def test_user_collection_create_path_still_creates(tmp_path, monkeypatch):
    monkeypatch.setenv("TD_BUILDER_USER_DIR", str(tmp_path))
    client, coll = uc._open_user_collection(create=True)
    assert coll is not None
    assert (tmp_path / "user_index" / "vector_db" / "chroma.sqlite3").exists()

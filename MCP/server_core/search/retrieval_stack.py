#!/usr/bin/env python3
r"""
TD Builder v0.2 — Phase 2 retrieval stack (behind unified_search._enhanced_search).

Pipeline (plan §6.3 / §7), all offline:

    query
     |- (A) dense  : Chroma td_unified top-40            (existing MiniLM TDDocSearch)
     |- (B) lexical: rank_bm25 BM25Okapi top-40          [NET-NEW, id-aligned pickle]
     |- (C) router : classify intent; if the query NAMES an operator, resolve it
     |               (canonical name / python_class) and INJECT + hard-boost that
     |               operator's parameter_group; apply chunk_type boosts per class
     -> RRF fuse(A,B) k=60  (ported from kb_pipeline/hybrid_retrieval_enhanced.py)
     -> graph_expand (optional; existing knowledge graph)
     -> cross-encoder rerank fused top-30  (ms-marco-MiniLM-L-6-v2, bundled, OFFLINE)
     -> router boosts applied in logit space; score = sigmoid(boosted_logit) in (0,1)
     -> score-floor (on the reranker score) + dedup
     -> top-k

The public contract is unchanged: ``search(query, n_results)`` returns the same
``[{content, metadata, score}, ...]`` shape the shipped ``TDDocSearch.search``
returns, so ``_enhanced_search`` and the MCP tool layer are untouched.

Artifacts (``lexical_index/`` + ``models/``) resolve RELATIVE to the KB root the
adapter is given, so ``--kb <new KB>`` picks them up. Every lever is individually
toggleable via ``RS_USE_*`` env vars so each one's eval delta is attributable.
If an artifact is missing the stack degrades gracefully toward the dense baseline.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional


def _kb_integrity():
    """File-relative import of server_core/kb_integrity.py (W2d trust boundary).

    This module is itself exec'd standalone via spec_from_file_location
    (unified_search does so), so package-relative imports are unavailable;
    resolve the sibling by path and memoize under a distinctive key.
    """
    import importlib.util
    mod = sys.modules.get("td_kb_integrity")
    if mod is None:
        p = Path(__file__).resolve().parent.parent / "kb_integrity.py"
        spec = importlib.util.spec_from_file_location("td_kb_integrity", str(p))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["td_kb_integrity"] = mod
        spec.loader.exec_module(mod)
    return mod


def _search_docs_mod():
    """File-relative import of server_core/search_docs.py (embedding-regime
    resolver) — same standalone-exec rationale as _kb_integrity."""
    import importlib.util
    mod = sys.modules.get("td_search_docs_regime")
    if mod is None:
        p = Path(__file__).resolve().parent.parent / "search_docs.py"
        spec = importlib.util.spec_from_file_location("td_search_docs_regime", str(p))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["td_search_docs_regime"] = mod
        spec.loader.exec_module(mod)
    return mod


def _semantic_hash_of_entry(entry: dict) -> str:
    """COPY of kb_build/user_components.semantic_hash_of_entry (the ingest side
    is the source of truth) — the two must stay in lockstep or the staleness
    guard misfires. Kept as a copy so the runtime stack never imports kb_build."""
    import hashlib
    basis = {
        "summary": entry.get("summary") or "",
        "use_cases": list(entry.get("use_cases") or []),
        "contained_operators": list(entry.get("contained_operators") or []),
        "custom_parameters": [[p.get("name") or "", p.get("description") or ""]
                              for p in (entry.get("custom_parameters") or [])],
    }
    return hashlib.sha256(json.dumps(basis, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


class _UserStore:
    """User-component store state, built complete and published via ONE
    attribute assignment (W5 — GIL-atomic; concurrent anyio-dispatched searches
    see the old or the new state, never a torn mix)."""

    __slots__ = ("collection", "count", "semantic_hash", "norm_names")

    def __init__(self, collection, count, semantic_hash, norm_names):
        self.collection = collection
        self.count = count
        self.semantic_hash = semantic_hash        # {name: sha} — the name registry
        self.norm_names = norm_names              # [(norm_key, name)] longest-first

# Query tokenizer — MUST match kb_build/build_bm25.TOKENIZER_PATTERN exactly
# (asserted against the value stored in the pickle at load time).
_TOKEN_RE = re.compile(r"[a-z0-9]+")

OP_FAMILY_WORDS = {"top", "chop", "sop", "dat", "comp", "mat", "pop"}
OP_FAMILY_WORDS_UPPER = {"TOP", "CHOP", "SOP", "DAT", "COMP", "MAT", "POP"}


def _env_flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


class RetrievalConfig:
    """Lever switches + tuning knobs, env-overridable for incremental measurement."""

    def __init__(self):
        self.use_bm25 = _env_flag("RS_USE_BM25", True)
        self.use_rerank = _env_flag("RS_USE_RERANK", True)
        self.use_router = _env_flag("RS_USE_ROUTER", True)
        self.use_floor = _env_flag("RS_USE_FLOOR", True)
        self.use_dedup = _env_flag("RS_USE_DEDUP", True)
        self.use_graph = _env_flag("RS_USE_GRAPH", False)   # measured; off by default
        self.debug = _env_flag("RS_DEBUG", False)

        self.dense_top = int(os.environ.get("RS_DENSE_TOP", "40"))
        self.bm25_top = int(os.environ.get("RS_BM25_TOP", "40"))
        self.rerank_top = int(os.environ.get("RS_RERANK_TOP", "45"))
        self.rrf_k = int(os.environ.get("RS_RRF_K", "60"))
        self.rrf_prior = float(os.environ.get("RS_RRF_PRIOR", str(RRF_PRIOR)))
        # W7 user-component injection: dense pre-select cap (bounds cross-encoder
        # cost on bulk-heavy stores; exact-name direct-injection bypasses it) and
        # the no-CE fallback scale (dense_score × scale into the rrf*100 fallback
        # space — 4.0 puts an exact-name match (1.0) above the dual-ladder KB
        # fallback ceiling ≈ 3.3, dense-preselected chunks proportionally below).
        self.user_top = int(os.environ.get("RS_USER_TOP", "20"))
        self.user_noce_scale = float(os.environ.get("RS_USER_NOCE_SCALE", "4.0"))


# ---------------------------------------------------------------------------
# Router signals — kept few, principled, and GENERAL (structure + TD vocabulary,
# never phrases lifted from a specific query set). The cross-encoder is the main
# ranker; these are nudges plus one decisive data-driven lever.
# ---------------------------------------------------------------------------

# General intent cues: question STRUCTURE + TouchDesigner DOMAIN VOCABULARY.
_RE_PY = re.compile(
    r"\b(python|numpy|callback|expression|script|scripting|programmatically|code|"
    r"method|attribute|member)\b|\.par\b")
_RE_BUILD = re.compile(
    r"\b(wire|connect|convert|route|feed|dock|attach|link|turn|hook\s*up)\b|"
    r"\bparameter\s+reference\b|"
    r"\b(into|to)\s+(\w+\s+){0,2}(chop|top|sop|dat|comp|mat|pop)s?\b")
_RE_HOWTO = re.compile(r"\bhow\s+(do|to|can|would|should)\b|\b(set\s*up|build\s+a|write\s+a)\b")
_RE_PARAM = re.compile(
    r"\b(parameter|param|setting|default)\b|"
    r"\b(set|adjust|control|change|tweak|configure)\s+(the|its|a|an|how)\b")
_RE_PALETTE = re.compile(
    r"\b(prebuilt|pre-built|palette|widget|ready-made|toolkit|tool)\b|"
    r"\bcomponent\b(?!\s+(that|which|for|to))")
_RE_OPLOOKUP = re.compile(
    r"\b(operator|op|node|component)s?\s+(that|which|for|to)\b|"
    r"\bwhat\s+(operator|op|node|component)\b|\bwhich\s+(operator|op|node)\b")

# Chunk-type affinity per intent: the natural answer type for that intent is boosted;
# a clearly-wrong type is demoted. Single magnitudes (not per-query tuning).
TYPE_AFFINITY = 1.5
TYPE_DEMOTE = 3.0
INTENT_TYPES = {
    "parameter":         (("parameter_group",), ()),
    "palette":           (("block_overview", "block_usecase", "block_io"), ()),
    "howto":             (("recipe", "pattern", "guide", "lesson_pattern", "real_example"), ()),
    "python":            (("class_method", "python_pattern", "python_class_overview", "callback"),
                          ("operator_overview", "parameter_group")),
    "build_instruction": (("build_instruction", "docked_dat"), ()),
    # "Which operator does X": a param table is never the operator — demote it so the
    # operator's overview / example surfaces (general; applies to any operator lookup).
    "operator_lookup": ((), ("parameter_group",)),
    # STRICT operator_lookup (the user literally said "operator/op that…") also rules
    # out palette blocks; a BARE capability description might still be a palette comp,
    # so blocks are only demoted under the explicit "operator" phrasing.
    "operator_lookup_strict": ((), ("block_overview", "block_usecase", "block_io")),
}

# The one decisive, justified DATA lever (Phase-1 finding): a NAMED operator being
# configured -> strongly prefer THAT operator's parameter_group; a python query that
# names an operator -> its class_method (e.g. AudiofileinCHOP_Class.metadata).
OP_PARAM_BOOST = 3.0
OP_METHOD_BOOST = 2.0

# Implied operator family from the query ("channel(s)"->CHOP, "texture/image/pixel"
# ->TOP): boost that family, demote the others. A general structural disambiguator
# for capability lookups ("add CHANNEL values" -> Math CHOP, not Add TOP).
FAMILY_CUES = {"CHOP": ("channel", "channels"), "TOP": ("texture", "image", "pixel", "pixels")}
FAMILY_BOOST = 2.0
FAMILY_DEMOTE = 2.0

# Retrieval prior: add the rank-fusion evidence back into the reranker logit so a
# strong dense+lexical agreement is REFINED, not overridden, by the cross-encoder.
RRF_PRIOR = 1.0

# Score-floor calibration. The REPORTED relevance score is sigmoid(raw_reranker_logit
# - SCORE_SHIFT): a shift that recalibrates the cross-encoder's "relevant" threshold up
# for TD-domain abstention, so out-of-domain queries (whose best match is only mildly
# positive, e.g. "send a text message" -> Text DAT) fall below the harness floor (0.2)
# and abstain, while genuine matches stay above. The shift only changes the score VALUE
# (for abstention); ranking is by the boosted logit and results are NEVER removed except
# by dedup — so a vague-but-valid query (operator-unnamed param) keeps its results, the
# way the dense baseline did. This is the score-floor "on the reranker score" — general,
# no per-query rule. Calibrated so all out-of-domain negatives report top-1 < 0.2.
SCORE_SHIFT = 1.5


class RetrievalStack:
    def __init__(self, kb_root, vector_search, knowledge_graph=None, config: Optional[RetrievalConfig] = None,
                 user_store: Optional[Path] = None):
        self.kb_root = Path(kb_root)
        self.vector_search = vector_search           # TDDocSearch: .collection, .model
        self.collection = getattr(vector_search, "collection", None)
        self.model = getattr(vector_search, "model", None)
        self.knowledge_graph = knowledge_graph
        self.cfg = config or RetrievalConfig()

        self._bm25 = None
        self._bm25_ids: List[str] = []
        self._bm25_texts: List[str] = []
        self._bm25_metas: List[dict] = []
        self._reranker = None
        self._reranker_failed = False
        # W7: user-component store (candidate injection). None = user search off;
        # with no user store configured the search path is byte-identical to today.
        self._user: Optional[_UserStore] = None
        self._user_store_path: Optional[Path] = Path(user_store) if user_store else None

        self._load_bm25()
        self._load_identity()
        # the reranker is heavy, so load it at init only when rerank is enabled
        # (_load_reranker itself no-ops on repeat calls / after a failed load)
        if self.cfg.use_rerank:
            self._load_reranker()
        if self._user_store_path is not None:
            self.reload_user_store()

    # -- artifact loading ----------------------------------------------------
    def _load_bm25(self):
        if not self.cfg.use_bm25:
            return
        pkl = self.kb_root / "lexical_index" / "bm25.pkl"
        if not pkl.exists():
            print(f"[retrieval_stack] no BM25 index at {pkl}; dense-only lexical channel disabled")
            return
        try:
            # W2d trust boundary: a bm25.pkl that arrived corrupted through the
            # distribution path (bad download / poisoned cache) would execute
            # arbitrary objects at unpickle time, so the bytes are hashed against
            # the KB receipt / pinned release manifest BEFORE unpickling (same
            # bytes — no verify-then-reopen race). Refusal degrades to the
            # dense-only ladder below instead of loading.
            data, verdict = _kb_integrity().load_verified_pickle(pkl, self.kb_root)
            if data is None:
                print(f"[retrieval_stack] SECURITY: {verdict.reason}")
                print("[retrieval_stack] BM25 index REFUSED (integrity); "
                      "lexical channel disabled - continuing DENSE-ONLY")
                return
            pat = data.get("tokenizer_pattern")
            if pat and pat != _TOKEN_RE.pattern:
                print(f"[retrieval_stack] WARNING: BM25 tokenizer pattern {pat!r} != "
                      f"runtime {_TOKEN_RE.pattern!r}; lexical matches may drift")
            self._bm25 = data["bm25"]
            self._bm25_ids = data["ids"]
            self._bm25_texts = data["texts"]
            self._bm25_metas = data["metas"]
            print(f"[retrieval_stack] BM25 index: {len(self._bm25_ids)} rows")
        except Exception as e:
            print(f"[retrieval_stack] BM25 load failed ({e}); dense-only lexical channel disabled")
            self._bm25 = None

    def _load_reranker(self):
        if self._reranker is not None or self._reranker_failed:
            return
        model_dir = self.kb_root / "models" / "ms-marco-MiniLM-L-6-v2"
        if not (model_dir / "config.json").exists():
            print(f"[retrieval_stack] no reranker bundle at {model_dir}; rerank disabled")
            self._reranker_failed = True
            return
        try:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            from sentence_transformers import CrossEncoder
            try:
                import torch
                torch.set_num_threads(1)
            except Exception:
                pass
            self._reranker = CrossEncoder(str(model_dir))
            print(f"[retrieval_stack] reranker loaded (offline): {model_dir.name}")
        except Exception as e:
            print(f"[retrieval_stack] reranker load failed ({e}); rerank disabled")
            self._reranker_failed = True

    def _load_identity(self):
        """operators.json -> normalized-name -> {name, python_class, family} for the router."""
        self._op_by_norm: Dict[str, dict] = {}
        self._op_norms_by_len: List[str] = []
        opj = self.kb_root / "operators.json"
        if not opj.exists():
            return
        try:
            ops = json.loads(opj.read_text(encoding="utf-8")).get("operators", [])
        except Exception:
            return
        for o in ops:
            nm = o.get("name")
            if not nm:
                continue
            nk = re.sub(r"[^a-z0-9]", "", nm.lower())
            if len(nk) >= 5:                       # avoid spurious short-name substring hits
                self._op_by_norm.setdefault(nk, {
                    "name": nm, "python_class": o.get("python_class"), "family": o.get("family")})
        self._op_norms_by_len = sorted(self._op_by_norm, key=len, reverse=True)

    # -- user-component store (W7) --------------------------------------------
    def reload_user_store(self, user_store: Optional[Path] = None):
        """(Re)resolve + (re)open the user store. Idempotent; covers
        store-absent-at-boot (the first commit creates the store and a reload
        late-binds it). Returns (ok, reason) — every failure degrades loudly to
        KB-only, never crashes a search.

        Publication rule (W5): the COMPLETE new state (collection handle,
        semantic-hash/name registry, count) is built locally and published via a
        single assignment to self._user; live attributes are never mutated in
        place (MCP dispatches requests as concurrent anyio tasks)."""
        if user_store is not None:
            self._user_store_path = Path(user_store)
        path = self._user_store_path
        if path is None:
            self._user = None
            return False, "no user store configured"
        vdb = path / "vector_db"
        manifest_p = path / "manifest.json"
        if not vdb.exists() or not manifest_p.exists():
            self._user = None
            return False, f"user store absent at {path} (no registrations yet)"
        try:
            manifest = json.loads(manifest_p.read_text(encoding="utf-8")) or {}
            if not isinstance(manifest, dict):
                raise ValueError("manifest is not an object")
        except Exception as e:
            self._user = None
            # All reload/inject diagnostics go to stderr: reload_user_store runs
            # MID-SESSION (register_component commit) when sys.stdout IS the MCP
            # JSON-RPC channel — one stray byte disconnects the client (F2).
            print(f"[retrieval_stack] user store REFUSED: unreadable manifest ({e}); "
                  f"KB-only — run reindex_all", file=sys.stderr)
            return False, f"unreadable user_index/manifest.json ({e}) — run reindex_all"
        # Regime guard: the user store must share the shipped KB's embedding
        # space or its vectors are garbage against this query encoder.
        try:
            regime = _search_docs_mod()._resolve_embedding(self.kb_root)
        except Exception as e:
            self._user = None
            print(f"[retrieval_stack] user store REFUSED: KB regime unresolvable ({e})",
                  file=sys.stderr)
            return False, f"KB embedding regime unresolvable ({e})"
        m_model = str(manifest.get("embedding_model") or "")
        if (m_model.casefold() != str(regime["model_id"]).casefold()
                or bool(manifest.get("normalize")) != bool(regime["normalize"])
                or (manifest.get("query_prefix") or "") != (regime["query_prefix"] or "")):
            self._user = None
            print(f"[retrieval_stack] user store REFUSED: embedding regime mismatch "
                  f"(store {m_model!r} vs KB {regime['model_id']!r}); KB-only — "
                  f"run reindex_all", file=sys.stderr)
            return False, "user store embedding regime mismatch — run reindex_all"
        try:
            import chromadb                        # lazy — hermetic import hygiene
            client = chromadb.PersistentClient(path=str(vdb))
            coll = client.get_collection(manifest.get("collection") or "td_unified")
            count = coll.count()
        except Exception as e:
            self._user = None
            print(f"[retrieval_stack] user store load failed ({e}); KB-only",
                  file=sys.stderr)
            return False, f"user store load failed ({e})"
        if count == 0:
            # W2 degrade-in-place contract: collection-count==0 ≡ store-absent
            # (last-comp removal empties rows; the directory is never deleted).
            self._user = None
            return False, "user store empty"
        hashes = {k: v for k, v in (manifest.get("semantic_hash") or {}).items()
                  if isinstance(k, str)}
        # Staleness check (loud, still serves — stale text beats absent): compare
        # the manifest's semantic_hash against a recompute over the registry.
        stale = []
        reg_p = path.parent / "user_components.json"
        try:
            comps = (json.loads(reg_p.read_text(encoding="utf-8")) or {}).get(
                "components") or {}
            for nm, h in hashes.items():
                e = comps.get(nm)
                if isinstance(e, dict) and _semantic_hash_of_entry(e) != h:
                    stale.append(nm)
        except Exception:
            pass
        if stale:
            print(f"[retrieval_stack] WARNING: user store STALE for {sorted(stale)} — "
                  f"summaries edited since ingest; run register_component "
                  f"(re-commit) or reindex_all", file=sys.stderr)
        # Name registry for exact-name direct-injection: normalize with the SAME
        # regex as _route (:316) / the KB resolver (:268), longest-match-first.
        # The KB resolver's len>=5 short-name guard is deliberately DROPPED here
        # (R2.2-3): the user registry is tiny and name-scoped; the guard would
        # silently exclude legitimately short names ('glow') from the exact-name
        # recall guarantee.
        norm_names = sorted(
            ((re.sub(r"[^a-z0-9]", "", n.lower()), n) for n in hashes),
            key=lambda t: len(t[0]), reverse=True)
        norm_names = [(k, n) for k, n in norm_names if k]
        if self._reranker is None:
            print("[retrieval_stack] user-component search degraded — reranker "
                  "unavailable; injected user chunks rank by scaled dense score",
                  file=sys.stderr)
        self._user = _UserStore(coll, count, hashes, norm_names)
        print(f"[retrieval_stack] user store: {count} chunks, "
              f"{len(hashes)} component(s)", file=sys.stderr)
        return True, ""

    def _inject_user(self, pool: Dict[str, dict], query: str):
        """Candidate INJECTION of user-component chunks (W7 design B). User
        chunks enter with rrf=0.0 (ZERO rank-fusion mass) + injected:True (the
        existing keep-rule carries them into the rerank set), ranked purely by
        cross-encoder + router boosts — the same arbitration KB chunks win by.
        Two halves:
          1. dense pre-select (RS_USER_TOP cap bounds cross-encoder cost);
          2. exact-name direct-injection (W1 — scale-invariant, bypasses the
             cap; ASSIGNED dense_score=1.0 per R2.2-1: Chroma get() returns no
             distances, and the no-CE fallback needs a real signal there)."""
        u = self._user
        if u is None:
            return

        def _add(cid, doc, meta, dscore):
            c = pool.get(cid)
            if c is None:
                pool[cid] = {"id": cid, "content": doc, "metadata": meta or {},
                             "rrf": 0.0, "injected": True, "user_injected": True,
                             "dense_score": dscore}
            else:
                c["injected"] = True
                c["user_injected"] = True
                c["dense_score"] = max(c.get("dense_score", 0.0), dscore)

        try:
            emb = self.model.encode(query, convert_to_numpy=True)
            res = u.collection.query(
                query_embeddings=[emb.tolist()],
                n_results=min(u.count, self.cfg.user_top),
                include=["documents", "metadatas", "distances"])
            for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                            res["metadatas"][0], res["distances"][0]):
                _add(cid, doc, meta, 1.0 - dist)
        except Exception as e:
            print(f"[retrieval_stack] WARNING: user dense pre-select failed ({e})",
                  file=sys.stderr)

        nq = re.sub(r"[^a-z0-9]", "", query.lower())
        for nk, name in u.norm_names:
            if nk in nq:
                try:
                    got = u.collection.get(where={"name": name},
                                           include=["documents", "metadatas"])
                    for cid, doc, meta in zip(got.get("ids", []),
                                              got.get("documents", []),
                                              got.get("metadatas", [])):
                        _add(cid, doc, meta, 1.0)
                except Exception as e:
                    print(f"[retrieval_stack] WARNING: user exact-name injection "
                          f"failed ({e})", file=sys.stderr)
                break

    # -- channels ------------------------------------------------------------
    def _dense(self, query: str, k: int) -> List[dict]:
        if self.collection is None or self.model is None:
            return []
        emb = self.model.encode(query, convert_to_numpy=True)
        res = self.collection.query(
            query_embeddings=[emb.tolist()], n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        out = []
        for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                        res["metadatas"][0], res["distances"][0]):
            out.append({"id": cid, "content": doc, "metadata": meta or {},
                        "dense_score": 1.0 - dist})
        return out

    def _bm25_search(self, query: str, k: int) -> List[dict]:
        if self._bm25 is None:
            return []
        toks = _TOKEN_RE.findall(query.lower())
        if not toks:
            return []
        scores = self._bm25.get_scores(toks)
        # top-k indices by score (descending), drop zero-score rows
        idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        out = []
        for i in idx:
            if scores[i] <= 0:
                break
            out.append({"id": self._bm25_ids[i], "content": self._bm25_texts[i],
                        "metadata": self._bm25_metas[i] or {}, "bm25_score": float(scores[i])})
        return out

    # -- router --------------------------------------------------------------
    def _route(self, query: str) -> dict:
        """Classify the query from GENERAL structure + the operator-name resolver.

        Intent comes from sentence structure and TD vocabulary (regexes above), never
        phrases lifted from a query set. The one strong, data-driven lever is the
        operator-name resolver: a NAMED operator being configured -> its parameter_group.
        """
        q = query.lower()
        nq = re.sub(r"[^a-z0-9]", "", q)

        named_op = None                                   # DATA: resolve a named operator
        for nk in self._op_norms_by_len:
            if nk in nq:
                named_op = self._op_by_norm[nk]
                break

        has_python = bool(_RE_PY.search(q))
        has_build = bool(_RE_BUILD.search(q))
        has_howto = bool(_RE_HOWTO.search(q))
        has_param = bool(_RE_PARAM.search(q))
        has_palette = bool(_RE_PALETTE.search(q))
        strict_ol = bool(_RE_OPLOOKUP.search(q))

        intents = set()
        if has_python:
            # Python-API queries are answered from class_method / python_pattern /
            # callback chunks — never reroute them to param/build/howto.
            intents.add("python")
        else:
            if has_build:
                intents.add("build_instruction")
            if has_palette:
                intents.add("palette")
            if has_howto:
                intents.add("howto")
            if strict_ol:
                intents.add("operator_lookup")
            if has_param:
                intents.add("parameter")
            # Fallback: a bare capability description (no other strong intent, no named
            # op) is an operator lookup — "bake a 3D scene into a texture" -> Render TOP.
            if not named_op and not (intents & {"build_instruction", "palette", "howto", "parameter"}):
                intents.add("operator_lookup")

        # A named operator that is NOT a wiring/python request is being configured:
        # INJECT its parameter_group broadly (recall safety — the cross-encoder then
        # ranks it), and BOOST it only when the phrasing is clearly param-shaped (not a
        # multi-step "how to" technique). Decoupling inject from boost is what lets the
        # held-out "how to spin an image with the Transform TOP" still find the param.
        inject_param = bool(named_op) and not has_python and not has_build
        do_param_filter = inject_param and not has_howto
        if do_param_filter:
            intents.add("parameter")

        op_lookup = "operator_lookup" in intents and "parameter" not in intents
        strict_oplookup = strict_ol and op_lookup
        family = None
        if op_lookup:
            fams = [f for f, cues in FAMILY_CUES.items() if any(c in q for c in cues)]
            if len(fams) == 1:
                family = fams[0]

        return {"named_op": named_op, "intents": intents, "do_param_filter": do_param_filter,
                "inject_param": inject_param, "has_python": has_python, "op_lookup": op_lookup,
                "strict_oplookup": strict_oplookup, "family": family}

    def _inject(self, pool: Dict[str, dict], where: dict):
        try:
            got = self.collection.get(where=where, include=["documents", "metadatas"])
        except Exception as e:
            # a failed injection silently loses the named-operator parameter_group
            # chunks -- surface the first failure instead of degrading invisibly
            if not getattr(self, "_inject_warned", False):
                self._inject_warned = True
                print(f"[retrieval_stack] WARNING: chunk injection failed ({e}); "
                      f"named-operator results degraded for this session")
            return
        for cid, doc, meta in zip(got.get("ids", []), got.get("documents", []), got.get("metadatas", [])):
            if cid not in pool:
                pool[cid] = {"id": cid, "content": doc, "metadata": meta or {}, "injected": True}
            else:
                pool[cid]["injected"] = True

    def _inject_op_chunks(self, route: dict, pool: Dict[str, dict]):
        """Guarantee the named operator's target chunks are in the candidate pool.

        param intent  -> its parameter_group (+overview) (the decisive recall lever)
        python intent -> its class_method chunks (e.g. AudiofileinCHOP_Class.metadata)
        """
        op = route.get("named_op")
        if not op or self.collection is None:
            return
        pyc = op.get("python_class")
        if not pyc:
            return
        if route.get("inject_param"):
            self._inject(pool, {"$and": [{"python_class": pyc},
                                         {"type": {"$in": ["parameter_group", "operator_overview"]}}]})
        if route.get("has_python"):
            # class_method `class` field is the Cap-first form of python_class
            klass = pyc[:1].upper() + pyc[1:]
            self._inject(pool, {"$and": [{"type": "class_method"}, {"class": klass}]})

    # -- fusion --------------------------------------------------------------
    def _rrf(self, dense: List[dict], bm25: List[dict]) -> Dict[str, dict]:
        """Reciprocal Rank Fusion (k=cfg.rrf_k). Returns id -> candidate w/ 'rrf' score."""
        k = self.cfg.rrf_k
        pool: Dict[str, dict] = {}

        def _add(results, key):
            for rank, r in enumerate(results):
                cid = r["id"]
                c = pool.get(cid)
                if c is None:
                    c = {"id": cid, "content": r["content"], "metadata": r["metadata"], "rrf": 0.0}
                    pool[cid] = c
                c["rrf"] += 1.0 / (k + rank + 1)
                if key in r:
                    c[key] = r[key]

        _add(dense, "dense_score")
        if self.cfg.use_bm25:
            _add(bm25, "bm25_score")
        return pool

    # -- graph expansion (optional) -----------------------------------------
    def _graph_expand(self, pool: Dict[str, dict], top_ids: List[str]):
        kg = self.knowledge_graph
        if not kg:
            return
        # Conservative: pull real_example chunks for operators already surfaced, by
        # orig_id, so the reranker (the arbiter) can promote a missed relevant example.
        op_names = []
        for cid in top_ids[:5]:
            m = pool[cid]["metadata"]
            nm = m.get("operator_name") or m.get("name")
            if nm and m.get("family"):
                op_names.append(nm)
        seen = set(op_names)
        for nm in list(seen)[:3]:
            try:
                exs = kg.find_examples_by_operator(nm, limit=2) or []
            except Exception:
                continue
            for ex in exs:
                eid = ex.get("example_id") or ex.get("id")
                if not eid:
                    continue
                try:
                    got = self.collection.get(where={"example_id": eid},
                                              include=["documents", "metadatas"], limit=1)
                except Exception:
                    continue
                for cid, doc, meta in zip(got.get("ids", []), got.get("documents", []), got.get("metadatas", [])):
                    pool.setdefault(cid, {"id": cid, "content": doc, "metadata": meta or {}, "rrf": 0.0})

    # -- rerank + boosts -----------------------------------------------------
    def _boost_logit(self, base_logit: float, meta: dict, route: dict) -> float:
        if not self.cfg.use_router:
            return base_logit
        bonus = 0.0
        ctype = meta.get("type")
        fam = meta.get("family")

        # chunk-type affinity / demote per detected intent
        intents = set(route["intents"])
        if route.get("strict_oplookup"):
            intents.add("operator_lookup_strict")
        for intent in intents:
            ud = INTENT_TYPES.get(intent)
            if not ud:
                continue
            up, down = ud
            if ctype in up:
                bonus += TYPE_AFFINITY
            elif ctype in down:
                bonus -= TYPE_DEMOTE

        # implied-family boost/demote (operator_lookup): right family up, others down
        if route.get("family") and fam in OP_FAMILY_WORDS_UPPER:
            bonus += FAMILY_BOOST if fam == route["family"] else -FAMILY_DEMOTE

        # decisive op-match levers (resolved named operator is the target)
        op = route.get("named_op")
        if op and op.get("python_class"):
            pyc = op["python_class"]
            if route.get("do_param_filter") and ctype == "parameter_group" \
                    and meta.get("python_class") == pyc:
                bonus += OP_PARAM_BOOST
            if route.get("has_python") and ctype == "class_method":
                klass = pyc[:1].upper() + pyc[1:]
                if meta.get("class") == klass:
                    bonus += OP_METHOD_BOOST
        return base_logit + bonus

    def _score_candidates(self, query: str, cands: List[dict], route: dict) -> List[dict]:
        """Assign each candidate a final ``score`` in (0,1) and order by it.

        score = sigmoid( reranker_logit + router_boosts + RRF_PRIOR*(rrf*100) ).
        The RRF prior keeps a strong dense+lexical signal from being overridden by
        the cross-encoder (which can over-prefer verbose chunks / near-synonym ops).
        """
        if not cands:
            return []
        use_rr = self.cfg.use_rerank and self._reranker is not None
        prior_w = self.cfg.rrf_prior
        floor = self.cfg.use_floor
        if use_rr:
            pairs = [(query, c["content"]) for c in cands]
            logits = self._reranker.predict(pairs, show_progress_bar=False)
            for c, lg in zip(cands, logits):
                ce = float(lg)
                c["ce_logit"] = ce                              # raw reranker relevance
                # RANK by the boosted logit (router/param/family nudges + RRF prior)
                c["_rank"] = _sigmoid(self._boost_logit(ce + prior_w * (c.get("rrf", 0.0) * 100.0),
                                                        c["metadata"], route))
                # REPORT a calibrated relevance score (shift -> out-of-domain abstains)
                c["score"] = _sigmoid(ce - SCORE_SHIFT) if floor else c["_rank"]
                # A genuine cross-encoder relevance score.
                c["score_kind"] = "reranked"
        else:
            # No reranker (lever-1 measurement): rank by RRF in a pseudo-logit space.
            # This score depends almost entirely on RANK POSITION (RRF) + fixed router
            # boosts, NOT the query's semantic content — flag it so callers do not read
            # it as a calibrated relevance score.
            for c in cands:
                if c.get("user_injected"):
                    # W3/R2.2-2: injected user chunks carry rrf=0.0 — a literal rrf
                    # substitution would leave user search silently inoperative in
                    # this branch. Rank them by the stashed dense score scaled into
                    # the rrf*100 fallback space, and label the signal honestly
                    # (Δ1: dense-similarity-derived, neither reranked nor fusion).
                    c["ce_logit"] = c.get("dense_score", 0.0) * self.cfg.user_noce_scale
                    c["_rank"] = _sigmoid(self._boost_logit(c["ce_logit"], c["metadata"], route))
                    c["score"] = c["_rank"]
                    c["score_kind"] = "dense_fallback"
                    continue
                c["ce_logit"] = c.get("rrf", 0.0) * 100.0
                c["_rank"] = _sigmoid(self._boost_logit(c["ce_logit"], c["metadata"], route))
                c["score"] = c["_rank"]
                c["score_kind"] = "rank_fusion_only"
        cands.sort(key=lambda c: c["_rank"], reverse=True)
        return cands

    def _collapse_by_op(self, cands: List[dict]) -> List[dict]:
        """For operator_lookup: keep only the best-scoring chunk per operator.

        "Which operator does X" wants a list of distinct OPERATORS, not five chunks
        of the same one. cands is already score-sorted, so keeping the first per
        python_class collapses redundant same-op chunks (which otherwise push a
        slightly-lower-scoring correct operator down out of the top ranks).
        """
        out, seen = [], set()
        for c in cands:
            pc = c["metadata"].get("python_class")
            if pc:
                if pc in seen:
                    continue
                seen.add(pc)
            out.append(c)
        return out

    # -- dedup ---------------------------------------------------------------
    def _dedup(self, cands: List[dict], n_results: int) -> List[dict]:
        """Collapse exact-duplicate ids / near-identical text. Results are NEVER dropped
        by a score floor here — abstention is handled by score calibration (SCORE_SHIFT)
        so a vague-but-valid query keeps its results (the dense baseline's behavior)."""
        out: List[dict] = []
        seen_ids = set()
        seen_text = set()
        for c in cands:
            cid = c["id"]
            if cid in seen_ids:
                continue
            if self.cfg.use_dedup:
                tkey = re.sub(r"\s+", " ", (c["content"] or "").strip().lower())
                if tkey and tkey in seen_text:
                    continue
                seen_text.add(tkey)
            seen_ids.add(cid)
            out.append(c)
            if len(out) >= n_results:
                break
        return out

    # -- public --------------------------------------------------------------
    def search(self, query: str, n_results: int = 5, **_) -> List[Dict]:
        cfg = self.cfg
        dense = self._dense(query, cfg.dense_top)
        bm25 = self._bm25_search(query, cfg.bm25_top) if cfg.use_bm25 else []

        pool = self._rrf(dense, bm25)
        route = self._route(query) if cfg.use_router else {"named_op": None, "intents": set(),
                                                           "do_param_filter": False, "op_lookup": False}
        if cfg.use_router:
            self._inject_op_chunks(route, pool)
        # W7: user-component candidate injection (rrf=0.0; kept by the injected
        # keep-rule below). No-op when no user store is loaded.
        self._inject_user(pool, query)

        # select the rerank candidate set: top by RRF + all injected/graph candidates
        ranked_ids = sorted(pool, key=lambda i: pool[i].get("rrf", 0.0), reverse=True)
        keep = set(ranked_ids[:cfg.rerank_top])
        keep |= {i for i in pool if pool[i].get("injected")}
        # operator_lookup: a capability-description query has no named op to inject, and
        # the right op's overview can sit just outside the RRF cut (it lacks the param
        # tables' lexical mass). Always rerank every operator_overview in the pool.
        if cfg.use_router and route.get("op_lookup"):
            keep |= {i for i in pool if pool[i]["metadata"].get("type") == "operator_overview"}
        if cfg.use_graph:
            self._graph_expand(pool, ranked_ids)
            keep |= {i for i in pool if pool[i].get("rrf", 0.0) == 0.0 and "injected" not in pool[i]}
        cands = [pool[i] for i in keep]

        cands = self._score_candidates(query, cands, route)

        if cfg.use_router and route.get("op_lookup"):
            cands = self._collapse_by_op(cands)
        results = self._dedup(cands, n_results)

        if cfg.debug:
            print(f"[rs] q={query!r} op={route.get('named_op')} intents={route.get('intents')} "
                  f"dense={len(dense)} bm25={len(bm25)} pool={len(pool)} -> {len(results)} "
                  f"top1={results[0]['score'] if results else None}")
        return [{"content": c["content"], "metadata": c["metadata"], "score": round(c["score"], 6),
                 "score_kind": c.get("score_kind", "unknown")}
                for c in results]

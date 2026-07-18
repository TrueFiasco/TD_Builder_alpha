"""
TD Builder v0.2 KB rebuild — shared scaffold (Phase 1, anatomy rebuild).

Reads ONLY from the LOCAL build corpus at ``New KB build/Resources`` and stages
all outputs under ``New KB build/Output/KB`` (never committed as a KB).

The chunk contract is driven by the Phase-0 eval harness (eval/predicates.py):
every chunk's ``meta`` must carry the identity/type fields the relevance and
name-integrity predicates read --
  type, __source_store, python_class, name, operator, operator_name, family,
  parameter, class, method, term, parent_chunk
-- and identity is JOINED from operator_ground_truth + operators.json via
python_class so a *retokenized* (underscored) wiki-title name never surfaces as
the ground-truth display name (the harness drives 294 -> 0).

The vector_db round-trip matches the shipped search path
(MCP/server_core/search_docs.py): a ChromaDB PersistentClient collection
``td_unified``, documents embedded with raw ``all-MiniLM-L6-v2`` (no
normalization, default L2 space), score = 1 - distance. Chroma metadata must be
flat scalars, so lists are pipe-joined and dicts JSON-encoded (matching the
shipped create_chroma_from_embeddings._coerce_chroma_metadata). ``parent_chunk``
is persisted INSIDE meta (the old pipeline computed it then dropped it at upsert).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Paths — the pipeline reads only from Resources, writes only to Output/KB.
# ---------------------------------------------------------------------------
# MAIN deliberately anchors to the MAIN tree: KB-build Resources/Output live
# there even when this code runs from a worktree. Do NOT adopt paths.REPO_ROOT
# here — it is worktree-relative and would silently repoint KB-build I/O.
MAIN = Path(r"C:\TD_Builder_Alpha_Build_V0.1.2")
RES = MAIN / "New KB build" / "Resources"
OUT = MAIN / "New KB build" / "Output" / "KB"
SHIPPED_KB = MAIN / "KB"

# Build-gate regrounded registry (eval/build_gate/reground_operators.py): the
# shipped operators.json corrected to live TD — build_token added, common-prefix
# param codes fixed (commonrenamefrom->renamefrom), Write_a_*/Anatomy_of_* wiki
# PAGES dropped from the operator set, dup display-names removed. Staged (never
# committed). When present it is the authoritative registry base; else fall back
# to the shipped operators.json so the build still runs standalone.
REGROUNDED = MAIN / "New KB build" / "Output" / "build_gate" / "operators.regrounded.json"

HAIKU = RES / "haiku_output"
EXPERT = RES / "expertise"
PAL_LOSSLESS = RES / "palette_lossless"
SNIPPETS = RES / "snippets"
GT = RES / "operator_ground_truth"
PARAMS_GT = GT / "params"               # live-TD param captures ({FAM}_{Name}_defaults.json)

# operator_types.json is TRACKED (eval/ground_truth/), regenerated from the live
# census by kb_build/gen_operator_types.py. It used to be read from GT above --
# the untracked corpus twin -- so this build resolved create tokens against a
# file CI never saw. The corpus path stays a legacy fallback; PARAMS_GT above is
# genuinely corpus-only and must NOT be repointed.
#
# MAIN-anchored on purpose, per the rule above: KB-build inputs come from the
# main tree even when this runs from a worktree. A worktree that regenerates the
# ground truth therefore does NOT change what a KB build consumes until it is
# merged -- which is the intended contract, not an oversight.
GT_OPERATOR_TYPES = MAIN / "eval" / "ground_truth" / "operator_types.json"
GT_OPERATOR_TYPES_LEGACY = GT / "operator_types.json"
CONFIG = RES / "Config"
WIKI = RES / "Learn" / "OfflineHelp"
WIKI_DOCS = WIKI / "https.docs.derivative.ca"      # Write_a_*.htm guide pages
WIKI_SUPPL = SHIPPED_KB / "wiki_supplemental"      # clean markdown GLSL guides

TD_BUILD = "0.99.2025.32460"
COLLECTION = "td_unified"
MODEL_ID = "all-MiniLM-L6-v2"

# Per-section provenance tag (plan §7) written to meta.__source_store.
STORE_OPERATOR = "td_operator"
STORE_PARAM = "td_param"
STORE_PYTHON = "td_python"
STORE_BLOCK = "td_block"
STORE_CONCEPT = "td_concept"
STORE_RECIPE = "td_recipe"
STORE_EXAMPLE = "td_example"
STORE_BUILD = "td_build"
STORE_GUIDE = "td_guide"


def write_kb_receipt(out_dir: Path, source: str):
    """Bless a staged KB's pickled artifacts (W2d load-time trust boundary).

    The runtime refuses to unpickle lexical_index/bm25.pkl and the gpickle
    unless their sha256 matches <KB>/kb_receipt.json or the pinned release
    manifest (scripts/vector_db_release.json artifact_sha256). A maintainer-
    built KB matches no release pin, so every kb_build staging path ends by
    writing this receipt; without it the server would boot dense-only with
    graph features off.
    """
    import importlib.util
    import sys
    ki = sys.modules.get("td_kb_integrity")
    if ki is None:
        p = Path(__file__).resolve().parents[1] / "MCP" / "server_core" / "kb_integrity.py"
        spec = importlib.util.spec_from_file_location("td_kb_integrity", str(p))
        ki = importlib.util.module_from_spec(spec)
        sys.modules["td_kb_integrity"] = ki
        spec.loader.exec_module(ki)
    rp = ki.write_receipt(Path(out_dir), source=source)
    print(f"[receipt] {('wrote ' + str(rp)) if rp else 'no pickled artifacts found - nothing to receipt'}")
    return rp


def _norm(s: Optional[str]) -> str:
    """Comparison key identical to predicates._norm: lowercase, alnum only."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower()) if s else ""


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


# ---------------------------------------------------------------------------
# Chroma metadata coercion — byte-compatible with the shipped pipeline.
# ---------------------------------------------------------------------------
def coerce_meta(meta: dict) -> dict:
    out: dict[str, Any] = {}
    for k, v in (meta or {}).items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, (list, tuple, set)):
            out[k] = "|".join(str(x) for x in v)
        elif isinstance(v, dict):
            out[k] = json.dumps(v, ensure_ascii=False, sort_keys=True)
        else:
            out[k] = str(v)
    return out


# ---------------------------------------------------------------------------
# Tuplet param grounding — inject value-bearing COMPONENTS for null-default
# headers from the live-TD capture (operator_ground_truth/params). The wiki
# documents a multi-value param as ONE value-less grouping header (Lag CHOP `lag`,
# default null); the real defaults live on the captured components `lag1`/`lag2`
# (=0.2). Adding those component entries lets the parameter_group chunk show real
# defaults AND lets get_parameter_detail('Lag CHOP','lag1') resolve at runtime
# (wiki_parameters is keyed by code). Mirrors the suffix convention in
# eval/tool_coverage.ParamDefaults.resolve / build_gate (header -> header+'1','2',…).
# Additive + orthogonal to the build-gate's code regrounding (it renames existing
# codes; this only ADDS components), so the two compose without conflict.
# ---------------------------------------------------------------------------
def _gt_params(family: str, name: str) -> dict:
    """Live-TD param specs for an operator, or {} if no capture file."""
    f = PARAMS_GT / f"{family}_{str(name).replace(' ', '_')}_defaults.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("parameters") or {}
    except Exception:
        return {}


def enrich_tuplets(operators: list[dict]) -> int:
    """Inject tuplet COMPONENTS for null-default header params. Mutates in place;
    returns the number of component entries added. A header qualifies only when its
    own default is None — the value-less wiki grouping (every default-None param is
    also type-None; an empty STRING default like Tablet CHOP `button2`=''/'string'
    is a real param, NOT a header, so it must be excluded) — AND the GT capture has
    `code1` (so op-reference params like Feedback TOP `top` — null but no `top1` —
    get nothing)."""
    injected = 0
    for o in operators:
        fam, name = o.get("family"), o.get("name")
        if not fam or not name:
            continue
        params = o.get("parameters")
        if not params:
            continue
        existing = {p.get("code") for p in params}
        gtp = None
        add: list[dict] = []
        for p in params:
            code = p.get("code")
            if not code or p.get("default") is not None or f"{code}1" in existing:
                continue
            if gtp is None:
                gtp = _gt_params(fam, name)
            i = 1
            while True:
                spec = gtp.get(f"{code}{i}")
                if not isinstance(spec, dict) or spec.get("default") is None:
                    break
                if f"{code}{i}" not in existing:
                    val = spec.get("value") if isinstance(spec.get("value"), dict) else {}
                    add.append({
                        "code": f"{code}{i}",
                        "display_name": spec.get("label") or f"{code}{i}",
                        "type": val.get("type") or p.get("type"),
                        "default": spec.get("default"),
                        "page": spec.get("page") or p.get("page"),
                        "section": p.get("section"),
                        "source": "ground_truth",
                    })
                    injected += 1
                i += 1
        if add:
            params.extend(add)
    return injected


# Grounded param write-rules the wiki param text omits but a builder MUST know.
# Applied to the registry param descriptions (-> staged operators.json ->
# get_operator_info / get_parameter_detail) and surfaced verbatim in the
# parameter_group chunks by ingest_operators (-> hybrid_search). Source:
# KB/wiki_supplemental/Write_GLSL_POPs.md ("selected for writing in Output
# Attributes"), confirmed live: P[id] = ... without outputattrs='P' fails to
# compile with "'P' : undeclared identifier".
PARAM_RULES: dict[tuple[str, str, str], str] = {
    ("POP", "GLSL POP", "outputattrs"):
        "WRITE RULE: to write an attribute in the shader (e.g. P[id] = ...), that "
        "attribute must be selected here — set outputattrs='P' to write P[id]; "
        "otherwise the shader fails to compile with \"'P' : undeclared identifier\".",
    ("POP", "GLSL Advanced POP", "ptoutputattrs"):
        "WRITE RULE: to write a point attribute in the shader (e.g. P[id] = ...), "
        "it must be selected here; otherwise the shader fails to compile with "
        "\"'P' : undeclared identifier\".",
    # --- migrated from Agents/expertise (2026-07-02 review; sources noted) ---
    ("CHOP", "Select CHOP", "channames"):
        "Space-separated name lists can fail in offline .tox builds (only the first "
        "channel selected) — prefer wildcard patterns ('t*') over 'tx ty'; never "
        "comma-separate.",  # PROB-002, validated
    ("DAT", "Table DAT", "cellexpr"):
        "Python expressions with parentheses may not serialize correctly into "
        ".toe/.tox — prefer simple literals in cell expressions, or verify the "
        "built file.",  # PROB-012, validated workaround
    ("COMP", "Geometry COMP", "instanceactive"):
        "Per-instance active SELECTOR (StrMenu naming an attribute), NOT an on/off "
        "switch — a boolean here makes TD hunt for an attribute literally named "
        "'True'. Enable instancing with the 'instancing' toggle; leave this unset "
        "unless gating per-instance visibility by attribute.",  # PROB-015
    ("CHOP", "POP to CHOP", "pop"):
        "Reads its source POP via this op-reference param (a param-plug, not a "
        "wired input).",  # td-builder-howto gotcha, live-verified in run1
    ("CHOP", "POP to CHOP", "attribscope"):
        "Set attribscope='*' together with scope='*' or channels can come through "
        "empty.",
    ("CHOP", "POP to CHOP", "scope"):
        "Set scope='*' together with attribscope='*' to receive all channels.",
    ("CHOP", "Speed CHOP", "timeslice"):
        "Continuous accumulation requires Time Slice ON (the live default, verified "
        "2026-07-02) — turning it off breaks accumulation across frames.",
}

# Op-level summary notes (appended to the operator summary): live-behavior facts
# a builder must know that no single param carries.
OP_SUMMARY_NOTES: dict[tuple[str, str], str] = {
    ("COMP", "Geometry COMP"):
        "NOTE: a live-created Geometry COMP ships with a default torus1 child "
        "(render flag ON) that renders/instances alongside your geometry — destroy "
        "it after live-create. Offline-built .tox geos have no torus1.",  # PROB-017
    ("POP", "Delete POP"):
        "NOTE: downstream reads can be stale by one cook after changing this op "
        "live — force-cook the reader (cook(force=True)) before trusting counts.",
}

# Registry python_class corrections. First two live-verified 2026-07-02
# (type(n).__name__ in TD 2025.32820): the shipped registry carried
# serialDAT_Class for all three serial-ish ops, which collided their derived
# build-token aliases. The remaining six are the same wiki-parse defect (the
# parser grabbed a related page's class or a prose fragment); corrected values
# verified against the offline wiki class pages (Learn/OfflineHelp, e.g.
# ExecuteDAT_Class.htm title "executeDAT Class").
PYTHON_CLASS_FIXES: dict[tuple[str, str], str] = {
    ("CHOP", "Hokuyo CHOP"): "hokuyoCHOP_Class",
    ("CHOP", "Serial CHOP"): "serialCHOP_Class",
    ("DAT", "CHOP Execute DAT"): "chopexecuteDAT_Class",   # was "default python method placeholders"
    ("DAT", "Execute DAT"): "executeDAT_Class",            # was "default python method placeholders"
    ("DAT", "OSC In DAT"): "oscinDAT_Class",               # was "Peer Class"
    ("DAT", "UDP In DAT"): "udpinDAT_Class",               # was "Peer Class"
    ("SOP", "Script SOP"): "scriptSOP_Class",              # was "Point Class"
    ("DAT", "SOP to DAT"): "soptoDAT_Class",               # was "Point Class"
}

# Wrong-token prose fixes: the Script CHOP/DAT/SOP wiki summaries say the docked
# callback is `cook`, but the correct (and stub-emitted) callback is `onCook`.
# TARGETED phrases only — a blind replace('cook','onCook') would corrupt every
# existing 'onCook' to 'ononCook' and mangle unrelated words ("re-cook").
SUMMARY_FIXES: list[tuple[str, str]] = [
    ("methods: cook ,", "methods: onCook ,"),
    ("methods: cook,", "methods: onCook,"),
    ("The cook method", "The onCook method"),
    # Script SOP phrases the same drift with parentheses
    ("methods: cook() ,", "methods: onCook() ,"),
    ("The cook() method", "The onCook() method"),
]


def enrich_param_rules(operators: list[dict]) -> int:
    """Apply PARAM_RULES (param descriptions), SUMMARY_FIXES + OP_SUMMARY_NOTES
    (summaries) and PYTHON_CLASS_FIXES (registry identity) in place; returns the
    number of edits. Idempotent (skips text already present/corrected)."""
    applied = 0
    for o in operators:
        fam, name = o.get("family"), o.get("name")
        for p in o.get("parameters", []) or []:
            rule = PARAM_RULES.get((fam, name, p.get("code")))
            if rule and rule not in (p.get("description") or ""):
                p["description"] = ((p.get("description") or "").rstrip() + " " + rule).strip()
                applied += 1
        summ = o.get("summary") or ""
        fixed = summ
        for old, new in SUMMARY_FIXES:
            if old in fixed:
                fixed = fixed.replace(old, new)
        note = OP_SUMMARY_NOTES.get((fam, name))
        if note and note not in fixed:
            fixed = (fixed.rstrip() + " " + note).strip()
        if fixed != summ:
            o["summary"] = fixed
            applied += 1
        pyc = PYTHON_CLASS_FIXES.get((fam, name))
        if pyc and o.get("python_class") != pyc:
            o["python_class"] = pyc
            applied += 1
    return applied


def enrich_docked_dats(operators: list[dict]) -> int:
    """Attach a LIGHTWEIGHT per-op docked-DAT summary from the live-TD harvest
    (operator_ground_truth/docked_dats/docked_dats_ground_truth.json) so the
    registry + retrieval answer "what ships docked to this op, and where is its
    default template". Full stubs stay in the deduped defaults store (staged as
    docked_contents.json); creation-time specs stay in KB/docked_dats.json."""
    gt_path = GT / "docked_dats" / "docked_dats_ground_truth.json"
    if not gt_path.exists():
        return 0
    gt = json.loads(gt_path.read_text(encoding="utf-8")).get("operators", {})
    applied = 0
    for o in operators:
        rec = gt.get(o.get("name") or "")
        if not rec or o.get("family") != rec.get("family"):
            continue
        o["docked_dats"] = [
            {k: v for k, v in d.items() if k in
             ("suffix", "optype", "kind", "host_params", "language", "default_md5", "chars")}
            for d in rec.get("docked", [])
        ]
        applied += 1
    return applied


# ---------------------------------------------------------------------------
# Identity registry — the ground-truth join (operator_ground_truth + operators.json).
# ---------------------------------------------------------------------------
class Identity:
    """Authoritative operator identity, loaded once and shared by every ingester.

    operators.json is already GT-merged (params carry typed defaults with
    source='ground_truth'); operator_types.json supplies the real ``.n`` create
    token (td_create) joined by python_class. The canonical display name is the
    SPACED operators.json name — never the underscored wiki-title form.
    """

    def __init__(self):
        # Prefer the build-gate's regrounded registry (live-TD corrected); fall back
        # to the shipped operators.json so the build still runs without the gate.
        self.source_path = REGROUNDED if REGROUNDED.exists() else (SHIPPED_KB / "operators.json")
        oj = json.loads(self.source_path.read_text(encoding="utf-8"))
        self.raw: dict = oj                       # full dict (classes/concepts/metadata) for emit
        self.operators: list[dict] = oj["operators"]
        self.classes: list = oj.get("classes", [])
        self.concepts: list = oj.get("concepts", [])

        # Ground null-default tuplet headers to their value-bearing components
        # (mutates self.operators AND self.raw, since raw["operators"] is the same
        # list) so BOTH the parameter_group chunks and the emitted operators.json
        # carry e.g. lag1/lag2=0.2.
        self.tuplets_injected: int = enrich_tuplets(self.operators)
        # Grounded write-rules + wrong-token prose fixes (same mutate-raw contract)
        self.param_rules_applied: int = enrich_param_rules(self.operators)
        # Live-harvested docked-DAT summaries (same mutate-raw contract)
        self.docked_attached: int = enrich_docked_dats(self.operators)

        self.by_pyclass: dict[str, dict] = {}
        self.by_name_norm: dict[str, dict] = {}
        for o in self.operators:
            pc = o.get("python_class")
            if pc:
                self.by_pyclass[pc] = o
            self.by_name_norm[_norm(o.get("name"))] = o

        # python_class -> td_create (.n token), authoritative from the live-TD capture
        self.pyclass_to_n: dict[str, str] = {}
        self.name_norm_to_n: dict[str, str] = {}
        gt_path = (GT_OPERATOR_TYPES if GT_OPERATOR_TYPES.exists()
                   else GT_OPERATOR_TYPES_LEGACY)
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        for fam, entries in (gt.get("operators") or {}).items():
            for e in entries:
                tdc = e.get("td_create")
                nm = e.get("name")
                if tdc:
                    self.pyclass_to_n[tdc + "_Class"] = tdc
                    if nm:
                        self.name_norm_to_n[_norm(nm)] = tdc

    def n_token(self, o: dict) -> Optional[str]:
        """The builder ``.n`` create token (OPType) for an operators.json record.

        Authoritative from operator_types.json via python_class; falls back to
        stripping the ``_Class`` suffix (still GT-derived, never a retokenization
        of the display name) only for the few KB ops absent from the capture.
        """
        pc = o.get("python_class") or ""
        if pc in self.pyclass_to_n:
            return self.pyclass_to_n[pc]
        nt = self.name_norm_to_n.get(_norm(o.get("name")))
        if nt:
            return nt
        return pc[:-6] if pc.endswith("_Class") else None

    def identity_meta(self, o: dict) -> dict:
        """Canonical identity fields for any operator-bearing chunk."""
        return {
            "name": o.get("name"),                 # SPACED canonical (never underscored)
            "operator_name": o.get("name"),
            "family": o.get("family"),
            "python_class": o.get("python_class"),
            "n_token": self.n_token(o),
        }


# ---------------------------------------------------------------------------
# Row helper — one place that guarantees the meta contract.
# ---------------------------------------------------------------------------
def make_row(rid: str, text: str, ctype: str, store: str,
             meta: Optional[dict] = None, parent: Optional[str] = None) -> dict:
    m = dict(meta or {})
    m["type"] = ctype                  # predicates read meta.type (NOT chunk_type)
    m["__source_store"] = store
    m["parent_chunk"] = parent         # persisted in meta (fixes the dropped-hierarchy bug)
    return {"id": rid, "text": text, "chunk_type": ctype, "parent_chunk": parent, "meta": m}


# ---------------------------------------------------------------------------
# Embedding — the ONE encode path shared by the build (build_vector_db) and the
# Phase-3 re-embed (reembed.py), so determinism + the normalize regime live in a
# single place. ``normalize=True`` writes unit-norm passage vectors (the cosine
# regime: ranking by Chroma's squared-L2 then equals ranking by cosine); the
# default ``False`` reproduces the shipped MiniLM build byte-for-byte (passing
# ``normalize_embeddings=False`` is identical to omitting it).
# ---------------------------------------------------------------------------
def _encode(model, texts, normalize: bool = False, batch_size: int = 256, threads: int = 1):
    """``threads`` = torch intra-op thread count for the forward pass. Default 1 keeps
    ``build_vector_db``'s canonical single-thread reproducibility; the Phase-3 re-embed
    passes a higher count because passage embedding is a one-shot build artifact and the
    QUERY-side determinism that matters for the eval is pinned by the harness, not here —
    so multi-thread passage embedding is safe and ~10x faster on the larger models."""
    try:
        import torch
        if threads and threads > 0:
            torch.set_num_threads(threads)
    except Exception:
        pass
    return model.encode(texts, convert_to_numpy=True, show_progress_bar=False,
                        batch_size=batch_size, normalize_embeddings=normalize)


# ---------------------------------------------------------------------------
# Vector DB build — replicates the shipped search_docs round-trip exactly.
# ---------------------------------------------------------------------------
def build_vector_db(rows: list[dict], out_dir: Path,
                    collection: str = COLLECTION, model_id: str = MODEL_ID,
                    batch: int = 512, normalize: bool = False) -> int:
    import shutil
    import chromadb
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_id)
    texts = [r["text"] for r in rows]
    embs = _encode(model, texts, normalize=normalize)

    vdb = out_dir / "vector_db"
    if vdb.exists():
        shutil.rmtree(vdb)
    vdb.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(vdb))
    coll = client.create_collection(collection)   # default L2 space, matching shipped

    # disambiguate duplicate ids; keep the original id in meta.orig_id (shipped behavior)
    seen: dict[str, int] = {}
    ids: list[str] = []
    for r in rows:
        rid = r["id"]
        c = seen.get(rid, 0)
        ids.append(rid if c == 0 else f"{rid}__dup{c}")
        seen[rid] = c + 1

    for i in range(0, len(rows), batch):
        j = min(i + batch, len(rows))
        coll.upsert(
            ids=ids[i:j],
            embeddings=[e.tolist() for e in embs[i:j]],
            documents=texts[i:j],
            metadatas=[{**coerce_meta(r["meta"]), "orig_id": r["id"]} for r in rows[i:j]],
        )
    return coll.count()

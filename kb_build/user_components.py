#!/usr/bin/env python3
"""USER custom-component engine (Wave 7): parse → author → commit.

One unified, name-keyed record per component in user_components.json:
  structural — component_manifest.offline_entry(...) + the engine's own
               harvest stamp (method="offline_manifest": the builder applies the
               strict NAME-authority wiring policy; see toe_builder_bridge);
  semantic   — LLM-authored summary/use_cases + the interface-scoped
               contained_operators inventory + custom parent parameters parsed
               from the interface COMP's .cparm (Δ7).

Retrieval side: 2–3 block chunks per component are upserted INCREMENTALLY into a
separate user Chroma store at paths.user_index_dir()/vector_db (collection
td_unified, same embedding regime as the shipped KB — resolved via
search_docs._resolve_embedding so the stores share one embedding space). There is
deliberately NO user BM25 / pickle: user chunks reach ranking by candidate
injection in the retrieval stack, never by rank fusion.

Integrity wording (W7 #46): user_index/manifest.json is SELF-SIGNED —
corruption/torn-write detection in the local trust domain ONLY, ZERO tamper
resistance (consistent with kb_integrity.py's documented scope). The
semantic_hash map inside it is the staleness guard: edits to summary/use_cases/
custom-parameter descriptions in user_components.json after ingest trip a loud
warning at store load until re-commit/reindex_all.

Import surface (W7 #44/#47): the three chunk-text templates are COPIED from
kb_build/ingest_palette.py §6.4 (the template source of truth) and the pure
helpers (make_row / slug / coerce_meta / STORE_BLOCK) are lifted from
kb_build/common.py, so this runtime module never imports kb_build.common (whose
module body hardcodes a dev-tree root). chromadb / sentence-transformers imports
stay LAZY (inside functions) for hermetic import hygiene.

Concurrency: every commit-side mutation (registry write + chroma upsert +
manifest write) runs under a lockfile at <user_dir>/.locks/user_index.lock —
deliberately OUTSIDE the guarded user_index/ tree (a lock inside it deadlocks
maintenance and pins the dir open on Windows).
"""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
import bootstrap  # noqa: E402

bootstrap.setup()

from paths import (  # noqa: E402
    KB_ROOT, kb_palette_components_path, user_components_path, user_index_dir,
    user_palette_dir)
from core.component_manifest import (  # noqa: E402
    ComponentManifestError, manifest_from_tox)
from core.component_manifest import offline_entry as _offline_entry  # noqa: E402

USER_COLLECTION = "td_unified"

REGISTRY_SKELETON = {
    "version": 1,
    "description": ("TD Builder USER component registry (kb_build/user_components.py). "
                    "Merged over KB/palette_components.json at load; user entries win "
                    "on name collision. Offline-grounded: NAME authority only. "
                    "summary/use_cases/custom-parameter descriptions are editable, but "
                    "edits require re-commit (register_component) or reindex_all() to "
                    "reach search — the user_index manifest's semantic_hash flags "
                    "stale entries loudly until then."),
    "components": {},
}


class UserComponentError(Exception):
    """Engine-level registration failure with a machine-readable kind."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------------------
# Helpers lifted from kb_build/common.py (pure; lifted so the runtime tool has
# zero dependency on common.py's hardcoded dev-tree root). Keep byte-compatible.
# ---------------------------------------------------------------------------
STORE_BLOCK = "td_block"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def make_row(rid: str, text: str, ctype: str, store: str,
             meta: Optional[dict] = None, parent: Optional[str] = None) -> dict:
    m = dict(meta or {})
    m["type"] = ctype
    m["__source_store"] = store
    m["parent_chunk"] = parent
    return {"id": rid, "text": text, "chunk_type": ctype, "parent_chunk": parent, "meta": m}


def coerce_meta(meta: dict) -> dict:
    """Chroma metadata coercion — byte-compatible with the shipped pipeline."""
    out: Dict[str, Any] = {}
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
# .cparm mini-parser (Δ7) — custom parent parameter definitions.
#
# Ground truth: offline toeexpand of real palette comps on TD 2025.32820
# (bloom.tox, moviePlayer.tox). Observed line grammar:
#   <typecode> <Name> <"Label"> <value fields...> <Page>
#       [<menuflags> <menucount> (<token> <label>)*] <order> [<enable-expr>]
# The value-field count varies by save format (bloom: one trailing string slot;
# moviePlayer: two) and by type (multi-component pars repeat
# (<int> <default> <""×n>) groups). The parser is type-aware and CONSERVATIVE:
# it extracts name/label/page/order, menu token+label pairs (tokens VERBATIM),
# a best-effort default, and min/max for the simple single-component layout;
# anything it cannot prove degrades to {name, label[, page]} with a warning —
# a registration NEVER fails over an exotic par line.
#
# The extra string slot(s) semantics are UNCONFIRMED (a help-string slot is
# suspected but was empty in every ground-truth sample) — they are deliberately
# NOT interpreted; no "help" field is ever guessed.
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_INT_RE = re.compile(r"^-?\d+$")

# Observed-typecode classes (TD 2025.32820 ground truth; used only to steer the
# default slot for structurally-ambiguous lines — everything else is structural).
_PULSE_TYPECODES = {772804869}
_STRING_TYPECODES = {772804868, 772804877, 772804880}


def _cparm_tokens(line: str) -> List[Tuple[str, bool]]:
    """Quote-aware tokenizer: [(token, was_quoted)]. Handles double AND single
    quoting (TD emits both: "Blur Size", 'none'); backslashes are literal (no
    escape processing — Windows-path defaults must survive verbatim)."""
    toks: List[Tuple[str, bool]] = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch in " \t":
            i += 1
            continue
        if ch in "\"'":
            q = ch
            i += 1
            j = line.find(q, i)
            if j < 0:               # unterminated quote — take the rest verbatim
                toks.append((line[i:], True))
                break
            toks.append((line[i:j], True))
            i = j + 1
        else:
            j = i
            while j < n and line[j] not in " \t":
                j += 1
            toks.append((line[i:j], False))
            i = j
    return toks


def _num(s: str):
    return int(s) if _INT_RE.match(s) else float(s)


def _tail_rest_ok(rest: List[str], rest_q: List[bool]) -> bool:
    """What may follow <order>: nothing | one expression (enable) | an int N
    followed by exactly N expression tokens (dynamic-menu source + enable —
    observed on scripted-menu pars like moviePlayer's Audiodriver)."""
    if not rest or len(rest) == 1:
        return True
    return (not rest_q[0] and _INT_RE.match(rest[0])
            and len(rest) == 1 + int(rest[0]))


def _parse_cparm_tail(tail: List[str], tail_q: List[bool]):
    """Validate + parse everything after the Page token. Returns
    (menu_pairs, order) or None when the tail doesn't match a known form:
      <order> [rest]  |  <flags> <count> (<tok> <lab>)*count <order> [rest]
    where [rest] is per _tail_rest_ok."""
    if not tail or tail_q[0] or not _INT_RE.match(tail[0]):
        return None
    # menu form first (an exact-length match is unambiguous)
    if len(tail) >= 2 and not tail_q[1] and _INT_RE.match(tail[1]):
        cnt = int(tail[1])
        base = 2 + 2 * cnt                          # flags count (tok lab)*cnt
        if cnt > 0 and len(tail) > base and not tail_q[base] \
                and _INT_RE.match(tail[base]) \
                and _tail_rest_ok(tail[base + 1:], tail_q[base + 1:]):
            pairs = [{"token": tail[2 + 2 * k], "label": tail[3 + 2 * k]}
                     for k in range(cnt)]
            return (pairs, int(tail[base]))
    if _tail_rest_ok(tail[1:], tail_q[1:]):
        return ([], int(tail[0]))
    return None


def _extract_default(rec: dict, V: List[str], VQ: List[bool], typecode: int,
                     menu: List[dict]) -> Optional[str]:
    """Best-effort default (+ min/max/type_class) from the value fields V.
    Mutates rec; returns a warning string or None."""
    if menu:
        rec["type_class"] = "menu"
        rec["menu"] = menu
        tokens = {m["token"] for m in menu}
        for v in reversed(V):
            if v == "":
                continue
            if v in tokens:
                rec["default"] = v
                return None
            if _NUM_RE.match(v):
                return None      # reached the numeric zone — legitimately no default
            return (f".cparm par '{rec['name']}': default {v!r} is not among "
                    f"the menu tokens — omitted")
        return None

    # trailing slot zone: empty / quoted / non-numeric tokens
    k = len(V) - 1
    slots: List[str] = []
    while k >= 0 and (V[k] == "" or VQ[k] or not _NUM_RE.match(V[k])):
        slots.append(V[k])
        k -= 1
    nonempty = [s for s in reversed(slots) if s != ""]

    if typecode in _PULSE_TYPECODES:
        rec["type_class"] = "pulse"
        return None
    if nonempty or typecode in _STRING_TYPECODES:
        rec["type_class"] = "string"
        rec["default"] = nonempty[0] if nonempty else ""
        return None
    if k < 0:
        return f".cparm par '{rec['name']}': no default field recognized"

    if len(V) > 11:
        # multi-component layout: repeated (<int> <default> <""×s>) groups from
        # the right (s = save-format slot count, 1 or 2). Anything that doesn't
        # match cleanly degrades to no default.
        j = len(V) - 1
        s = 0
        while j >= 0 and V[j] == "":
            s += 1
            j -= 1
        defaults: List[Any] = []
        if s in (1, 2):
            while j >= 1 and _NUM_RE.match(V[j]) and _NUM_RE.match(V[j - 1]):
                defaults.append(_num(V[j]))
                j -= 2
                s2 = 0
                while j >= 0 and V[j] == "":
                    s2 += 1
                    j -= 1
                if s2 != s:
                    break
        if len(defaults) >= 2:
            rec["type_class"] = "multi"
            rec["default"] = list(reversed(defaults))
            return None
        return (f".cparm par '{rec['name']}': multi-component layout not "
                f"recognized — default omitted")

    # simple single-component layout (10/11 fields): default is the last numeric
    # before the slot zone; min/max sit at fixed offsets 3 and 6 (both formats).
    rec["type_class"] = "number"
    rec["default"] = _num(V[k])
    if len(V) in (10, 11) and _NUM_RE.match(V[3]) and _NUM_RE.match(V[6]):
        lo, hi = _num(V[3]), _num(V[6])
        if lo <= hi:
            rec["min"], rec["max"] = lo, hi
    return None


def parse_cparm(text: str) -> Tuple[List[str], List[dict], List[str]]:
    """Parse a .cparm file's text → (pages, pars, warnings). Pars are sorted by
    (page order per the header, UI order field, name) for deterministic output."""
    pages: List[str] = []
    pars: List[dict] = []
    warnings: List[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line == "?":
            continue
        toks = _cparm_tokens(line)
        vals = [t for t, _ in toks]
        quoted = [q for _, q in toks]
        if vals[0] == "pages":
            pages = vals[2:] if len(vals) >= 3 else []
            continue
        if len(vals) < 5 or not _INT_RE.match(vals[0]):
            warnings.append(f"unparseable .cparm line skipped: {' '.join(vals[:3])} …")
            continue
        typecode = int(vals[0])
        rec: dict = {"name": vals[1], "label": vals[2]}
        # page scan is LEFT-to-right with tail validation (the page always
        # precedes the menu block; a value field that collides with a page name
        # fails tail validation and the scan continues).
        parsed = None
        for i in range(3, len(vals) - 1):
            if quoted[i] or vals[i] not in pages:
                continue
            got = _parse_cparm_tail(vals[i + 1:], quoted[i + 1:])
            if got is not None:
                parsed = (i, got)
                break
        if parsed is None:
            warnings.append(f".cparm par '{rec['name']}': page/tail not recognized — "
                            f"degraded to name/label only")
            pars.append(rec)
            continue
        i, (menu, order) = parsed
        rec["page"] = vals[i]
        rec["_order"] = order
        warn = _extract_default(rec, vals[3:i], quoted[3:i], typecode, menu)
        if warn:
            warnings.append(warn)
        pars.append(rec)

    page_rank = {p: n for n, p in enumerate(pages)}
    pars.sort(key=lambda r: (page_rank.get(r.get("page"), 1 << 20),
                             r.get("_order", 1 << 20), r["name"]))
    for r in pars:
        r.pop("_order", None)
    return pages, pars, warnings


def custom_parameters_from_skeleton(skeleton: dict) -> Tuple[List[dict], List[str]]:
    """Custom parent parameters with EFFECTIVE defaults: the .cparm definition
    default, overridden by the interface COMP's saved .parm value when the .tox
    carries a non-default (values live in .parm, definitions in .cparm)."""
    files = skeleton.get("interface_files") or {}
    text = files.get("cparm")
    if not text:
        return [], []
    _pages, pars, warnings = parse_cparm(text)
    overrides = files.get("parm_values") or {}
    for rec in pars:
        ov = overrides.get(rec["name"])
        if ov is not None:
            rec["default"] = _num(ov) if (rec.get("type_class") == "number"
                                          and _NUM_RE.match(ov)) else ov
    return pars, warnings


# ---------------------------------------------------------------------------
# Parse → entry
# ---------------------------------------------------------------------------
def parse_component(tox_path) -> dict:
    """toeexpand + parse a .tox (or expanded .dir) → registration skeleton:
    the full manifest_from_tox return plus parsed custom_parameters."""
    skeleton = manifest_from_tox(tox_path)
    pars, warnings = custom_parameters_from_skeleton(skeleton)
    skeleton["custom_parameters"] = pars
    skeleton["parse_warnings"] = warnings
    return skeleton


def _complexity_bucket(op_count) -> Optional[str]:
    """Op-count buckets (owner decision 5)."""
    if not isinstance(op_count, int):
        return None
    return "simple" if op_count <= 10 else ("moderate" if op_count <= 40 else "complex")


def relative_path_guard(source: str, tox_path: str) -> None:
    """G6 (single home = the engine): 'user'/'derivative' sources emit an
    app.userPaletteFolder/app.samplesFolder-relative EXPRESSION; an absolute
    tox_path there produces a broken `app.userPaletteFolder + '/C:/...'`."""
    if source not in ("user", "derivative"):
        return
    p = str(tox_path).replace("\\", "/")
    if Path(p).is_absolute() or (len(p) > 1 and p[1] == ":"):
        root = "app.userPaletteFolder" if source == "user" else "app.samplesFolder"
        raise UserComponentError(
            "absolute_tox_path",
            f"source '{source}' emits a {root}-relative expression, so tox_path "
            f"must be RELATIVE to that palette root (got '{p}'). Pass e.g. "
            f"'<name>.tox' (or use save_to_palette=true, which computes it), or "
            f"use source 'project' for a plain absolute path constant.")


def build_entry(skeleton: dict, *, source: str, tox_path: str,
                category: Optional[str] = None, summary: str,
                use_cases: Optional[List[str]] = None,
                parameter_descriptions: Optional[Dict[str, str]] = None
                ) -> Tuple[dict, List[str]]:
    """Unified registry record (structural + semantic) from a parse skeleton.
    Returns (entry, warnings). Stamps harvest.method itself (offline_entry does
    NOT — without the stamp the builder defaults to index-authority over
    NAME-SORTED indexes: silent BUG-3-class mis-wiring on multi-connector comps)."""
    emitted = str(tox_path).replace("\\", "/")
    relative_path_guard(source, emitted)

    entry = _offline_entry(skeleton["manifest"], skeleton["inner_type"],
                           source=source, tox_path=emitted, category=category,
                           subcompname=skeleton.get("subcompname"))
    entry["harvest"] = {"method": "offline_manifest",
                        "date": datetime.date.today().isoformat()}

    warnings: List[str] = list(skeleton.get("parse_warnings") or [])
    entry["summary"] = " ".join(str(summary or "").split())
    if not entry["summary"]:
        raise UserComponentError("missing_summary",
                                 "a non-empty 'summary' is required at commit "
                                 "(run prepare=true first and author one)")
    entry["use_cases"] = [str(u).strip() for u in (use_cases or []) if str(u).strip()]
    entry["contained_operators"] = list(skeleton.get("contained_operators") or [])
    entry["complexity"] = _complexity_bucket(entry.get("operator_count"))

    pars = [dict(p) for p in (skeleton.get("custom_parameters") or [])]
    descs = dict(parameter_descriptions or {})
    by_name = {p["name"]: p for p in pars}
    for pname, desc in descs.items():
        d = str(desc or "").strip()
        if not d:
            continue
        if pname in by_name:
            by_name[pname]["description"] = d
        else:
            warnings.append(f"description for unknown custom parameter '{pname}' "
                            f"dropped (not found on re-parse)")
    if pars:
        entry["custom_parameters"] = pars
    return entry, warnings


def semantic_hash_of_entry(entry: dict) -> str:
    """Content hash over the SEMANTIC fields — the staleness basis recorded in
    user_index/manifest.json. Covers custom-parameter names + descriptions (Δ7).
    Copied (with cross-reference) into retrieval_stack's user-store loader —
    both sides must stay in lockstep."""
    basis = {
        "summary": entry.get("summary") or "",
        "use_cases": list(entry.get("use_cases") or []),
        "contained_operators": list(entry.get("contained_operators") or []),
        "custom_parameters": [[p.get("name") or "", p.get("description") or ""]
                              for p in (entry.get("custom_parameters") or [])],
    }
    return hashlib.sha256(json.dumps(basis, sort_keys=True,
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Registry I/O (atomic tmp + os.replace)
# ---------------------------------------------------------------------------
def _registry_path(registry_path=None) -> Path:
    return Path(registry_path) if registry_path else user_components_path()


def load_registry(registry_path=None) -> dict:
    reg_path = _registry_path(registry_path)
    if reg_path.is_file():
        try:
            spec = json.loads(reg_path.read_text(encoding="utf-8"))
            if not isinstance(spec.get("components"), dict):
                raise ValueError('missing "components" object')
            return spec
        except Exception as e:
            raise UserComponentError(
                "registry_unreadable",
                f"existing registry {reg_path} is unreadable ({e}); fix or "
                f"remove it first") from e
    return json.loads(json.dumps(REGISTRY_SKELETON))


def _write_registry(spec: dict, registry_path=None) -> Path:
    reg_path = _registry_path(registry_path)
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = reg_path.with_name(reg_path.name + ".tmp")
    tmp.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, reg_path)
    return reg_path


def upsert_registry_entry(name: str, entry: dict, registry_path=None) -> bool:
    """Atomic upsert; returns True when an existing entry was replaced."""
    spec = load_registry(registry_path)
    replaced = name in spec["components"]
    spec["components"][name] = entry
    _write_registry(spec, registry_path)
    return replaced


def shipped_component_names() -> set:
    """Names in the SHIPPED KB/palette_components.json (shadow detection)."""
    try:
        spec = json.loads(kb_palette_components_path().read_text(encoding="utf-8"))
        comps = spec.get("components")
        return set(comps) if isinstance(comps, dict) else set()
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Commit lockfile — <user_dir>/.locks/user_index.lock, OUTSIDE user_index/.
# ---------------------------------------------------------------------------
_LOCK_STALE_S = 600.0


def _lock_path() -> Path:
    return user_components_path().parent / ".locks" / "user_index.lock"


@contextlib.contextmanager
def commit_lock(timeout_s: float = 30.0):
    """O_CREAT|O_EXCL lockfile with stale-lock age-out. Two concurrent commits
    would otherwise interleave a lost update (comp searchable but vanished from
    the build registry)."""
    lock = _lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    fd = None
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time():.0f}\n".encode("ascii"))
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > _LOCK_STALE_S:
                    lock.unlink(missing_ok=True)   # stale holder — age it out
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise UserComponentError(
                    "locked",
                    f"another registration holds {lock}; retry shortly (stale "
                    f"locks age out after {int(_LOCK_STALE_S)}s)")
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            os.close(fd)
        finally:
            lock.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Block chunks — templates COPIED from kb_build/ingest_palette.py §6.4 (source
# of truth), adjusted for the USER story: `user:`-namespaced ids,
# license_tier="user", builder-instantiation wording, the shadow-override
# sentence (4c), and the Δ7 custom-parameter sentence in block_io (menu tokens
# VERBATIM — they feed the string-menu-token build rule).
# ---------------------------------------------------------------------------
def _format_custom_par(p: dict) -> str:
    bits: List[str] = []
    if p.get("label") and p["label"] != p["name"]:
        bits.append(str(p["label"]))
    if p.get("menu"):
        bits.append("menu tokens: " + "|".join(m["token"] for m in p["menu"]))
    if p.get("default") not in (None, ""):
        d = p["default"]
        bits.append("default " + (", ".join(str(x) for x in d)
                                  if isinstance(d, list) else str(d)))
    if p.get("min") is not None and p.get("max") is not None:
        bits.append(f"range {p['min']}..{p['max']}")
    s = p["name"] + (f" ({'; '.join(bits)})" if bits else "")
    if p.get("description"):
        s += f" — {p['description']}"
    return s


def component_block_rows(name: str, entry: dict,
                         shadows_shipped: bool = False) -> List[dict]:
    """block_overview / block_usecase / block_io rows for ONE user component."""
    category = entry.get("category") or "User"
    summary = entry.get("summary") or f"{name} user-registered component."
    use_cases = [u for u in (entry.get("use_cases") or []) if u]
    contained = [c for c in (entry.get("contained_operators") or []) if c]
    custom_pars = entry.get("custom_parameters") or []
    op_count = entry.get("operator_count")
    ins = [d.get("in_op") for d in (entry.get("inputs") or [])]
    outs = [d.get("out_op") for d in (entry.get("outputs") or [])]

    base_meta = {
        "name": name,
        "palette_name": name,
        "category": category,
        "has_ui": False,
        "complexity": entry.get("complexity"),
        "operator_count": op_count,
        "tox_path": entry.get("tox_path"),
        "wiki_url": None,
        "license_tier": "user",
    }
    oid = f"user:block:{slug(name)}:overview"
    shadow_txt = (" Overrides the Derivative palette component of the same name "
                  "at build time." if shadows_shipped else "")

    uc = f" Use for: {'; '.join(use_cases)}." if use_cases else ""
    cx = entry.get("complexity")
    detail = (f" ({op_count} inner operators{', ' + cx if cx else ''})"
              if op_count else "")
    ov = (f"USER COMPONENT: {name} [{category}] — {summary}"
          f" User-registered prebuilt component{detail}."
          f"{uc}{shadow_txt}"
          f" Instantiate via the builder: {{\"palette\": \"{name}\"}} — it loads "
          f"from your registered .tox at open time (do not hand-build).")
    rows = [make_row(oid, ov, "block_overview", STORE_BLOCK, dict(base_meta))]

    tags = ", ".join(use_cases) if use_cases else category
    usecase_txt = (f"USER USE-CASE: {name} ({category}). {summary} "
                   f"When you need {tags.lower()}, use the registered {name} "
                   f"component rather than building it from scratch. Tags: {tags}.")
    rows.append(make_row(f"user:block:{slug(name)}:usecase", usecase_txt,
                         "block_usecase", STORE_BLOCK, dict(base_meta), parent=oid))

    # Template deviation vs shipped §6.4 (noted): the shipped block_io gates on
    # lossless `contained` only; the user block_io is emitted when EITHER the
    # inventory OR custom parameters are non-empty (Δ7 — for many user comps the
    # custom pars ARE the primary interface).
    if contained or custom_pars:
        parts = [f"USER COMPONENT I/O: {name} ({category}) —"
                 f" in ops: {ins or 'none'}; out ops: {outs or 'none'}."]
        if contained:
            parts.append(f" Internal network of {op_count} operators"
                         f" ({', '.join(contained[:18])}).")
        if custom_pars:
            parts.append(" Custom parameters: "
                         + "; ".join(_format_custom_par(p) for p in custom_pars)
                         + ". Set menu parameters by string token (verbatim), "
                           "never by index.")
        parts.append(f" Wire inner ops explicitly ('{name}/<op>'); a component "
                     f"is never itself a data source.")
        io_meta = dict(base_meta)
        if contained:
            io_meta["contained_operators"] = contained
        rows.append(make_row(f"user:block:{slug(name)}:io", "".join(parts),
                             "block_io", STORE_BLOCK, io_meta, parent=oid))
    return rows


# ---------------------------------------------------------------------------
# Incremental ingest into the user Chroma store
# ---------------------------------------------------------------------------
def _search_docs_mod():
    """File-relative import of MCP/server_core/search_docs.py (regime resolver)."""
    import importlib.util
    mod = sys.modules.get("td_user_search_docs")
    if mod is None:
        p = _REPO / "MCP" / "server_core" / "search_docs.py"
        spec = importlib.util.spec_from_file_location("td_user_search_docs", str(p))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["td_user_search_docs"] = mod
        spec.loader.exec_module(mod)
    return mod


def _kb_sha() -> Optional[str]:
    """kb_sha of the shipped KB (informational provenance in the user manifest)."""
    try:
        import importlib.util
        p = _REPO / "MCP" / "env_identity.py"
        spec = importlib.util.spec_from_file_location("td_user_env_identity", str(p))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.kb_identity(KB_ROOT)["kb_sha"]
    except Exception:
        return None


def _resolve_user_regime() -> dict:
    return _search_docs_mod()._resolve_embedding(KB_ROOT)


def _open_user_collection(create: bool = False):
    """(client, collection) for the user store, or (None, None) when absent."""
    import chromadb                                    # lazy (hermetic CI)
    vdb = user_index_dir() / "vector_db"
    if not create and not vdb.exists():
        return None, None
    vdb.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(vdb))
    coll = client.get_or_create_collection(USER_COLLECTION)  # default L2 space
    return client, coll


def _write_user_manifest(semantic_hash: Dict[str, str], regime: dict) -> Path:
    mpath = user_index_dir() / "manifest.json"
    manifest = {
        "_comment": ("Self-signed user-store manifest: corruption/torn-write "
                     "detection in the LOCAL trust domain only — zero tamper "
                     "resistance. Regime must match the shipped KB or the "
                     "retrieval stack refuses the store loudly."),
        "embedding_model": regime["model_id"],
        "normalize": bool(regime["normalize"]),
        "query_prefix": regime["query_prefix"] or "",
        "collection": USER_COLLECTION,
        "kb_sha": _kb_sha(),
        "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "semantic_hash": dict(sorted(semantic_hash.items())),
    }
    mpath.parent.mkdir(parents=True, exist_ok=True)
    tmp = mpath.with_name(mpath.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    os.replace(tmp, mpath)
    return mpath


def _read_user_manifest() -> dict:
    mpath = user_index_dir() / "manifest.json"
    if mpath.is_file():
        try:
            return json.loads(mpath.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def _raw_model(model):
    """Defensive unwrap: NEVER embed passages through the server's _QueryEncoder
    (it applies query_prefix + normalize; passages must not be prefixed). The
    wrapper exposes the wrapped sentence-transformer as `_model`."""
    return getattr(model, "_model", model)


def _load_embedder(regime: dict):
    from sentence_transformers import SentenceTransformer  # lazy
    return SentenceTransformer(regime["model_id"])


def _regime_differs(manifest: dict, regime: dict) -> bool:
    """True if the store manifest's recorded regime differs from `regime` on any
    of the three fields the boot guard compares (model_id casefolded, normalize,
    query_prefix). Mirrors retrieval_stack's user-store health check EXACTLY so
    ingest refuses on precisely the mismatches the boot guard would refuse."""
    return (str(manifest.get("embedding_model") or "").casefold()
                != str(regime["model_id"]).casefold()
            or bool(manifest.get("normalize")) != bool(regime["normalize"])
            or (manifest.get("query_prefix") or "") != (regime["query_prefix"] or ""))


def _manifest_regime_or_current(manifest: dict) -> dict:
    """Regime for a manifest REWRITE, resolved all-or-nothing (AN1): preserve the
    manifest's regime verbatim when it records ALL THREE fields, else fall back to
    the current KB regime as a UNIT. Never synthesise a mixed regime — a preserved
    model_id paired with a defaulted normalize/query_prefix could spuriously pass
    or fail the boot guard's three-field compare."""
    if (manifest.get("embedding_model")
            and "normalize" in manifest and "query_prefix" in manifest):
        return {"model_id": manifest["embedding_model"],
                "normalize": bool(manifest["normalize"]),
                "query_prefix": manifest.get("query_prefix") or ""}
    return _resolve_user_regime()


def _user_store_vector_count() -> int:
    """Number of vectors in the user collection (0 if the store is absent)."""
    _client, coll = _open_user_collection(create=False)
    if coll is None:
        return 0
    return len(coll.get().get("ids") or [])


def _guard_regime_change(regime: dict, allow_regime_change: bool) -> None:
    """Refuse-hard (A8) if adopting `regime` would CHANGE an existing store's
    recorded regime without authorisation — BEFORE any embed or write, so the
    manifest stays byte-unchanged and no vectors are upserted. Incremental ingest
    must never mix embedding spaces: one re-commit after a regime change would
    otherwise flip the boot guard from REFUSED to ACCEPTED while every
    un-recommitted component keeps stale-regime vectors.

    A regime change is authorised ONLY for an explicit reindex
    (allow_regime_change=True) AND only when the store holds zero vectors — the
    flag is independently VERIFIED against the store, never merely trusted, so a
    regressed caller cannot silently re-open the hole. First ingest (no manifest
    regime) and a same-regime re-commit are no-ops. The default (no-flag) path is
    a pure manifest read — no chromadb. Regime change is exclusively
    reindex_all's job."""
    prev = _read_user_manifest()
    if not prev.get("embedding_model") or not _regime_differs(prev, regime):
        return
    if not allow_regime_change:
        raise UserComponentError(
            "regime_mismatch",
            f"user store was built under embedding regime "
            f"{prev.get('embedding_model')!r} but the current KB regime is "
            f"{regime['model_id']!r}. Incremental ingest cannot mix embedding "
            f"spaces (the un-recommitted components would keep stale-regime "
            f"vectors and every retrieval would be geometrically wrong). Re-embed "
            f"the whole user store: `py -3.11 kb_build/register_user_component.py "
            f"--reindex-all` (or call kb_build.user_components.reindex_all()).")
    n = _user_store_vector_count()
    if n:
        raise UserComponentError(
            "regime_mismatch",
            f"allow_regime_change set on a NON-EMPTY user store ({n} vectors): a "
            f"regime change must drop every existing vector first. Use "
            f"reindex_all(), which wipes before it re-embeds.")


def ingest_incremental(rows: List[dict], semantic_hashes: Dict[str, str],
                       model=None, *, allow_regime_change: bool = False
                       ) -> Dict[str, int]:
    """Embed + upsert the given block rows into the user store; name-scoped
    delete first (never delete by the NEW rows' ids — that strands stale chunks
    when a re-registered comp's chunk count shrinks); manifest updated with the
    regime + merged semantic_hash map. Caller holds the commit lock.

    Refuses (A8) BEFORE any write if adopting the current regime would change an
    existing store's regime without authorisation — regime change is exclusively
    reindex_all's job (it passes allow_regime_change=True after wiping the store).

    Returns {name: chunk_count}."""
    regime = _resolve_user_regime()
    _guard_regime_change(regime, allow_regime_change)  # refuse-hard BEFORE any write
    by_name: Dict[str, List[dict]] = {}
    for r in rows:
        by_name.setdefault(r["meta"]["name"], []).append(r)

    _client, coll = _open_user_collection(create=True)
    emb_model = _raw_model(model) if model is not None else _load_embedder(regime)

    texts = [r["text"] for r in rows]
    embs = emb_model.encode(texts, convert_to_numpy=True, show_progress_bar=False,
                            batch_size=256,
                            normalize_embeddings=bool(regime["normalize"]))
    emb_by_id = {r["id"]: e for r, e in zip(rows, embs)}

    for name, nrows in by_name.items():
        coll.delete(where={"name": name})
        coll.upsert(
            ids=[r["id"] for r in nrows],
            embeddings=[emb_by_id[r["id"]].tolist() for r in nrows],
            documents=[r["text"] for r in nrows],
            metadatas=[{**coerce_meta(r["meta"]), "orig_id": r["id"]} for r in nrows],
        )

    merged = dict((_read_user_manifest().get("semantic_hash") or {}))
    merged.update(semantic_hashes)
    _write_user_manifest(merged, regime)
    return {name: len(nrows) for name, nrows in by_name.items()}


def remove_component(name: str, registry_path=None) -> dict:
    """Full lifecycle removal: registry entry + the comp's chunks + its
    semantic_hash manifest entry, all under the commit lock. Empty-store branch
    is DEGRADE-IN-PLACE (rows deleted, semantic_hash map empty) — the directory
    is NEVER deleted while handles may be open (Windows WinError 32)."""
    with commit_lock():
        spec = load_registry(registry_path)
        existed = name in spec["components"]
        if existed:
            del spec["components"][name]
            _write_registry(spec, registry_path)

        chunks_deleted = False
        _client, coll = _open_user_collection(create=False)
        if coll is not None:
            coll.delete(where={"name": name})
            chunks_deleted = True
            manifest = _read_user_manifest()
            hashes = dict(manifest.get("semantic_hash") or {})
            hashes.pop(name, None)
            # AN1: preserve the stored regime all-or-nothing — never pair the
            # current model_id with defaulted normalize/query_prefix (a mix).
            regime = _manifest_regime_or_current(manifest)
            _write_user_manifest(hashes, regime)
    return {"name": name, "removed_from_registry": existed,
            "chunks_deleted": chunks_deleted}


def reindex_all(model=None, registry_path=None) -> dict:
    """Recovery path (regime change, manifest corruption, bulk summary edits):
    drop every row in the user collection and re-embed the whole registry."""
    with commit_lock():
        spec = load_registry(registry_path)
        comps = spec.get("components") or {}
        _client, coll = _open_user_collection(create=True)
        existing = coll.get().get("ids") or []
        if existing:
            coll.delete(ids=existing)
        shipped = shipped_component_names()
        rows: List[dict] = []
        hashes: Dict[str, str] = {}
        for name, entry in comps.items():
            rows.extend(component_block_rows(name, entry,
                                             shadows_shipped=name in shipped))
            hashes[name] = semantic_hash_of_entry(entry)
        counts: Dict[str, int] = {}
        if rows:
            # the store was just wiped above — this is the ONE authorised path
            # allowed to adopt a changed regime (verified empty by the guard).
            counts = ingest_incremental(rows, hashes, model=model,
                                        allow_regime_change=True)
        else:
            _write_user_manifest({}, _resolve_user_regime())
    return {"components": len(comps), "chunks": sum(counts.values())}


# ---------------------------------------------------------------------------
# High-level prepare / commit (shared by the MCP tool and the CLI)
# ---------------------------------------------------------------------------
_CONTAINMENT_RE = re.compile(r"[\\/]|\.\.")


def _containment_check(kind: str, value: str) -> None:
    if _CONTAINMENT_RE.search(value or "") or not (value or "").strip():
        raise UserComponentError(
            "containment",
            f"{kind} '{value}' must be a bare name (no path separators or '..')")


def prepare_specs(specs: List[dict]) -> List[dict]:
    """prepare=true: parse only. Returns per-spec skeleton summaries for the
    session assistant to author summary / use_cases / per-parameter descriptions."""
    shipped = shipped_component_names()
    out = []
    for spec in specs:
        tox = spec.get("tox_path")
        name = spec.get("name") or (Path(tox).name.split(".")[0] if tox else None)
        item: dict = {"name": name, "tox_path": tox}
        try:
            if not tox:
                raise UserComponentError("bad_spec", "spec is missing 'tox_path'")
            sk = parse_component(Path(tox))
            man = sk["manifest"]
            item.update({
                "ok": True,
                "wrapper": bool(man.get("wrapper")),
                "subcompname": sk.get("subcompname"),
                "inner_type": sk.get("inner_type"),
                "operator_count": man.get("operator_count"),
                "inputs": [d["name"] for d in man.get("inputs", [])],
                "outputs": [d["name"] for d in man.get("outputs", [])],
                "contained_operators": sk.get("contained_operators") or [],
                "custom_parameters": sk.get("custom_parameters") or [],
                "parse_warnings": sk.get("parse_warnings") or [],
                "shadows_shipped": name in shipped,
            })
        except (ComponentManifestError, UserComponentError) as e:
            item.update({"ok": False,
                         "error": {"kind": getattr(e, "kind", "error"),
                                   "message": str(e)}})
        out.append(item)
    return out


def commit_specs(specs: List[dict], *, save_to_palette: bool = False,
                 folder: str = "TD_Builder", overwrite: bool = False,
                 confirm_shadow: bool = False, model=None) -> List[dict]:
    """Commit: per spec — optional palette copy, build_entry, registry upsert;
    then ONE batched ingest under ONE commit lock. Stateless: each commit
    re-parses its .tox (the authored summary describes whatever is committed;
    operator_count is echoed so a gross prepare/commit mismatch is visible).

    The caller is responsible for the post-commit reload_user_store() and for
    stamping `retrievable` onto the results."""
    shipped = shipped_component_names()
    results: List[dict] = []
    staged: List[Tuple[str, dict, List[dict]]] = []      # (name, entry, rows)

    for spec in specs:
        tox = spec.get("tox_path")
        name = spec.get("name") or (Path(tox).name.split(".")[0] if tox else None)
        res: dict = {"name": name, "ok": False}
        results.append(res)
        try:
            if not tox:
                raise UserComponentError("bad_spec", "spec is missing 'tox_path'")
            src_file = Path(tox)
            shadows = name in shipped
            res["shadows_shipped"] = shadows
            if shadows:
                res["shadow_note"] = (f"builds of {{palette: '{name}'}} now resolve "
                                      f"to your component, not Derivative's")

            source = spec.get("source") or "project"
            emitted = spec.get("registry_tox_path")
            if save_to_palette:
                if shadows and not confirm_shadow:
                    raise UserComponentError(
                        "shadow_unconfirmed",
                        f"'{name}' shadows a shipped Derivative palette component; "
                        f"palette-saved adds require confirm_shadow=true to proceed")
                _containment_check("name", name)
                _containment_check("folder", folder)
                pal_root = user_palette_dir().resolve()
                target = (pal_root / folder / f"{name}.tox").resolve()
                if pal_root not in target.parents:
                    raise UserComponentError(
                        "containment", f"palette target {target} escapes {pal_root}")
                if target.exists() and not overwrite:
                    raise UserComponentError(
                        "palette_collision",
                        f"{target} already exists; pass overwrite=true to replace "
                        f"it (every overwrite is reported as 'replaced')")
                replaced_file = target.exists()
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, target)
                if replaced_file:
                    res["replaced"] = str(target)
                source = "user"
                emitted = f"{folder}/{name}.tox"
            elif emitted is None:
                emitted = str(src_file.resolve())
            # G6 fail-fast (mirrors the old CLI): reject a bad source/tox_path
            # combination BEFORE the expensive toeexpand parse.
            relative_path_guard(source, emitted)

            skeleton = parse_component(src_file)
            entry, warnings = build_entry(
                skeleton, source=source, tox_path=emitted,
                category=spec.get("category") or (folder if save_to_palette else "User"),
                summary=spec.get("summary") or "",
                use_cases=spec.get("use_cases"),
                parameter_descriptions=spec.get("parameter_descriptions"))
            rows = component_block_rows(name, entry, shadows_shipped=shadows)
            staged.append((name, entry, rows))
            res.update({
                "ok": True,
                "operator_count": entry.get("operator_count"),
                "entry_summary": entry["summary"],
                "chunk_count": len(rows),
                "warnings": warnings,
            })
        except (ComponentManifestError, UserComponentError) as e:
            res["error"] = {"kind": getattr(e, "kind", "error"), "message": str(e)}

    if staged:
        with commit_lock():
            # A8: refuse a regime-changing commit up front — before any registry
            # write — so a mismatch never leaves the registry ahead of the store
            # (ingest_incremental re-checks as the last line of defence).
            _guard_regime_change(_resolve_user_regime(), allow_regime_change=False)
            for name, entry, _rows in staged:
                replaced = upsert_registry_entry(name, entry)
                for res in results:
                    if res.get("name") == name and res.get("ok"):
                        res["replaced_registry_entry"] = replaced
            all_rows = [r for _n, _e, rows in staged for r in rows]
            hashes = {name: semantic_hash_of_entry(entry)
                      for name, entry, _r in staged}
            ingest_incremental(all_rows, hashes, model=model)
    return results

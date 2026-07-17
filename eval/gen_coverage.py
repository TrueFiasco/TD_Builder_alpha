#!/usr/bin/env python3
r"""
Phase-0.6 COVERAGE-tier query generator for the TD Builder KB eval harness.

WHY this exists
---------------
The frozen 78-query set (``labeled_queries.jsonl``) is a cross-phase TREND gate,
but it touches only 23 distinct operators (3.4% of 673); POP (100) and MAT (13)
are never tested. This mints a stratified BREADTH set across all 7 families, the
main §6 chunk types, and the parameter kinds.

TWO HARD GUARANTEES on every emitted item (Phase-0.6b hardening):
  (1) GOLD DERIVED FROM GROUND TRUTH, never LLM-guessed — and it RESOLVES against
      operators.json + operator_ground_truth (so the run reports 0 unresolved).
  (2) GOLD IS THE UNIQUE / CLEARLY-BEST ANSWER. A uniqueness gate classifies every
      candidate into one of three outcomes (the "enlarge a rectangle" problem):
        - unique         : exactly one ground-truth entity satisfies the query.
        - disambiguated  : unique once the discriminator the ground truth already
                           implies (operator name / family) is carried IN the query
                           — the preferred repair (real queries carry this context).
        - multi          : genuinely many valid answers even with context -> emit an
                           ACCEPT-SET OR-predicate (tagged ambiguity:"multi"), scored
                           by SET-recall, never folded into single-gold MRR.
      Candidates that are ambiguous and cannot be repaired/enumerated are SKIPPED
      (a missing valid answer would silently corrupt the metric).
  Plus: NO answer leak (operator/comp/term/method name absent from the query).

Every item carries ``gen.ambiguity``. Per-category unambiguous-rate counts
unique+disambiguated; the multi slice is reported separately by set-recall.

OFFLINE (reads JSON/YAML only — never the search stack, never embeds; the optional
--paraphrase pass reads a committed cache, no live LLM) and DETERMINISTIC per --seed.

Recipes (gold <- named ground-truth source):
  operator_lookup  op summary, name/family/class STRIPPED      -> operator (python_class/op_name)
  parameter        op + op-SPECIFIC param, op name KEPT         -> that op's parameter_group  (disambiguated)
  palette_discovery comp distinctive purpose, name STRIPPED     -> block name (td_block)
  python           class_method desc (method noun KEPT)         -> class_method  (unique 1-class / multi accept-set)
  build_instruction family converter edge                       -> build_instruction
  concept          glossary definition, term STRIPPED           -> concept term
  negative         templated out-of-domain + TD-adjacent HARD   -> expect_no_match
(howto / recipe / pattern stay HAND-AUTHORED — not auto-derivable from ground truth.)
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent
sys.path.insert(0, str(EVAL_DIR))
from predicates import GroundTruth, _norm  # reuse the harness's resolver + norm  # noqa: E402

FAMILIES = ["CHOP", "TOP", "SOP", "DAT", "COMP", "MAT", "POP"]
GENERATOR_VERSION = "0.6.1"


# ---------------------------------------------------------------------------
# Path resolution -- ground-truth sources live ONLY in the main tree
# ---------------------------------------------------------------------------
def _main_tree() -> Path | None:
    parts = REPO_ROOT.parts
    if ".claude" in parts:
        return Path(*parts[: parts.index(".claude")])
    return None


def resolve_kb_root(cli: str | None) -> Path:
    if cli:
        return Path(cli)
    if (REPO_ROOT / "KB" / "operators.json").exists():
        return REPO_ROOT / "KB"
    mt = _main_tree()
    if mt:
        for cand in (mt / "New KB build" / "Output" / "KB", mt / "KB"):
            if (cand / "operators.json").exists():
                return cand
    raise FileNotFoundError("Could not locate a KB with operators.json. Pass --kb.")


def resolve_resources(cli: str | None, kb_root: Path) -> Path:
    if cli:
        return Path(cli)
    mt = _main_tree() or kb_root.parent.parent.parent
    cand = mt / "New KB build" / "Resources"
    if cand.exists():
        return cand
    raise FileNotFoundError("Could not locate New KB build/Resources. Pass --resources.")


# ---------------------------------------------------------------------------
# Text helpers (UTF-8 normalize, boilerplate strip, sentence split, leak, etc.)
# ---------------------------------------------------------------------------
_WS = re.compile(r"\s+")
_URL = re.compile(r"https?://\S+")
_TRAILERS = re.compile(
    r"\b(for more information|for more info|more information|see the |see also|refer to|note:)",
    re.IGNORECASE,
)
# leading boilerplate sentences that are not the capability (OS:/Hardware:/Note:
# label headers, platform/hardware caveats) -- else they become the "query".
_BOILER_LEAD = re.compile(
    r"^\s*("
    r"[A-Za-z][A-Za-z /]{1,18}:\s"                        # a leading "OS:/Hardware:/Note:/Platform:" label
    r"|deprecated|this operator is only supported"
    r"|only supported|supported only|this (operator|component|chop|top|sop|dat|comp|mat|pop) is "
    r"(only )?(supported|available)|available only|works only|only works|requires )",
    re.IGNORECASE,
)
_SMART = {
    "“": '"', "”": '"', "‘": "'", "’": "'", "«": '"', "»": '"',
    "–": "-", "—": "-", "−": "-", "…": "...", " ": " ",
    "�": " ",  # mojibake replacement char -> space (drop, don't propagate)
    "⊞": " ",  # multi-value marker
}
_STOP = set("a an the of to for and or in on with by from as is are be this that it its into "
            "your you can will using use used uses based on each other than then they them so "
            "which what when where who whose how at also any all not no if but more most some "
            "one two between out up off over under via per".split())


def clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(str(s))
    s = unicodedata.normalize("NFKC", s)
    s = "".join(_SMART.get(ch, ch) for ch in s)
    s = _URL.sub(" ", s)
    return _WS.sub(" ", s).strip()


_CAVEAT_CONTAINS = re.compile(
    r"(only (available|supported)|is only (available|supported)|available in touchdesigner"
    r"|commercial and pro|requires a |this operator only)", re.IGNORECASE)


def strip_leading_boilerplate(s: str) -> str:
    """Drop leading boilerplate sentences (OS:/Hardware:/License: labels AND
    licensing/platform caveats like '... is only available in ... Commercial and
    Pro') so the capability sentence, not the caveat, becomes the query."""
    s = clean_text(s)
    for _ in range(5):
        parts = _split_sentences(s)
        if not parts:
            return ""
        head = parts[0]
        if not (_BOILER_LEAD.match(head) or _CAVEAT_CONTAINS.search(head)):
            break
        if len(parts) <= 1:
            return ""           # caveat was the whole thing -> caller drops it
        s = " ".join(parts[1:]).strip()
    return s


# split on sentence end, but NOT inside e.g./i.e./vs./etc. or single-letter initials
_ABBR = re.compile(r"\b(e\.g|i\.e|etc|vs|cf|approx|Inc|no|No|Dr|Mr|Mrs|St|Fig|al)\.$", re.IGNORECASE)


def _split_sentences(s: str):
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", s.strip())
    out, buf = [], ""
    for seg in raw:
        buf = (buf + " " + seg).strip() if buf else seg
        if _ABBR.search(buf):       # ended on an abbreviation -> keep accumulating
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def first_sentence(s: str) -> str:
    s = clean_text(s)
    m = _TRAILERS.search(s)
    if m:
        s = s[: m.start()]
    parts = _split_sentences(s.strip())
    out = parts[0] if parts else s
    # guard against an e.g.-truncated fragment: if it ends mid-parenthetical, drop the tail
    if out.count("(") > out.count(")"):
        out = out[: out.rfind("(")]
    return out.rstrip(" .,;:").strip()


def strip_phrases(text: str, phrases) -> str:
    """Remove each phrase (longest first) at WORD BOUNDARIES, then tidy."""
    out = text
    for p in sorted({p for p in phrases if p and len(str(p)) >= 2}, key=lambda x: -len(str(x))):
        out = re.sub(r"(?<![A-Za-z0-9])" + re.escape(str(p)) + r"(?![A-Za-z0-9])",
                     " ", out, flags=re.IGNORECASE)
    out = _WS.sub(" ", out).strip()
    while True:
        nxt = re.sub(r"^(the|a|an|is|are|that|which|of|for|to)\b\s*", "", out, flags=re.IGNORECASE)
        if nxt == out:
            break
        out = nxt
    out = re.sub(r"\s+([.,;:'])", r"\1", out)
    return _WS.sub(" ", out).strip(" .,;:")


def lead_case(s: str) -> str:
    """Lowercase the first char UNLESS the first token is an acronym (GPU, DMX,
    OSC, PBR, NDI, …) — fixes 'gPU'/'dMX' from a blanket lower()."""
    if not s:
        return s
    first = s.split()[0]
    if len(first) >= 2 and first.isupper():
        return s
    return s[0].lower() + s[1:]


def has_leak(query: str, hard_tokens) -> bool:
    qn = _norm(query)
    for t in hard_tokens:
        tn = _norm(t)
        if len(tn) >= 4 and tn in qn:
            return True
    return False


def content_tokens(s: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) >= 3 and t not in _STOP}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cap_len(s: str, limit: int = 200) -> str:
    if len(s) <= limit:
        return s
    return s[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")


_POSSESSIVE_END = re.compile(r"(?:'s|’s|\bthe|\bof|\ba|\ban|\bfor|\bto|\bwith|\bin|\bon|\(e\.g|\(i\.e|\()\s*$",
                             re.IGNORECASE)


def is_malformed(q: str) -> bool:
    """Reject truncated / dangling / too-short queries."""
    if not q or "�" in q:
        return True
    if q.count("(") != q.count(")"):
        return True
    if _POSSESSIVE_END.search(q.strip()):
        return True
    return len(content_tokens(q)) < 5


# ---------------------------------------------------------------------------
# Operator identity (drives stripping + the leak gate)
# ---------------------------------------------------------------------------
def op_identity(op: dict):
    """(strip_phrases, hard_leak_tokens). Single-word cores (Noise, Blur) STAY as
    capability words; the FULL name, MULTI-word cores AND each of their component
    words, python_class, and the no-space concatenations are stripped + hard."""
    name = op.get("name") or ""
    fam = op.get("family") or ""
    pyc = op.get("python_class") or ""
    words = name.split()
    core = " ".join(words[:-1]) if (len(words) > 1 and words[-1] == fam) else name
    pyc_stem = pyc[:-6] if pyc.endswith("_Class") else pyc

    # The FULL name + its no-space concat + python_class are always identifying.
    # A SINGLE-word core (Noise, Attribute, Blur) is a legitimate capability word
    # (the 78-q keeps "noise"/"blurs") — it is NEITHER stripped NOR hard-leak, so its
    # plural/derived forms ("attributes") don't trigger a false leak. Only a MULTI-word
    # core (Ableton Link, Audio File In) and its component words are identifying.
    strip = {name, fam, pyc, pyc_stem, name.replace(" ", "")}
    hard = {name, pyc, pyc_stem, name.replace(" ", "")}
    if len(core.split()) >= 2:
        for t in (core, core.replace(" ", "")):
            strip.add(t); hard.add(t)
        for w in core.split():
            if len(w) >= 3:
                strip.add(w); hard.add(w)
    return {p for p in strip if p and len(p) >= 2}, {p for p in hard if p}


def safe_python_classes(ops) -> set:
    """python_class safe for a gold: UNIQUE to one op AND well-formed (*_Class, no
    space). Shared base labels (Peer Class, PanelCOMP_Class on >1 op, serialDAT_Class
    on 3) would over-match / mislabel; op_name_any always carries identity."""
    cnt = Counter(o.get("python_class") for o in ops if o.get("python_class"))
    return {p for p, c in cnt.items() if c == 1 and "_Class" in p and " " not in p}


# ===========================================================================
# Indices for the uniqueness gate (built once)
# ===========================================================================
class Indices:
    def __init__(self, ops, catalog, class_desc, concept_desc):
        self.ops = ops
        # operator capability tokens (own name stripped, for fair comparison)
        self.op_tokens = {}
        self.op_by_name = {}
        for o in ops:
            self.op_by_name[o["name"]] = o
            strip, _ = op_identity(o)
            cap = strip_phrases(first_sentence(strip_leading_boilerplate(o.get("summary") or "")), strip)
            self.op_tokens[o["name"]] = content_tokens(cap)
        # parameter code/label -> #ops
        self.code_ops = defaultdict(set)
        self.label_ops = defaultdict(set)
        for o in ops:
            for p in o.get("parameters") or []:
                c = (p.get("code") or "").lower()
                lab = (p.get("display_name") or "").strip().lower()
                if c:
                    self.code_ops[c].add(o["name"])
                if lab:
                    self.label_ops[lab].add(o["name"])
        # palette purposes (name stripped)
        self.comp_names = {k for k in catalog if k != "_metadata" and isinstance(catalog[k], dict)}
        self.comp_tokens = {}
        for nm in self.comp_names:
            e = catalog[nm]
            self.comp_tokens[nm] = content_tokens(
                strip_phrases(first_sentence(e.get("purpose") or e.get("summary") or ""),
                              self.comp_names))
        # python method -> classes
        self.method_classes = defaultdict(set)
        for c, ms in class_desc.items():
            if isinstance(ms, dict):
                for m in ms:
                    self.method_classes[m].add(c)
        # concept term -> definition tokens
        self.term_tokens = {t: content_tokens(first_sentence(d))
                            for t, d in concept_desc.items() if isinstance(d, str)}


# generic "does the gold dominate the field" check over a {key: token_set} index
def _dominates(query_tokens: set, gold_key, index: dict, *, margin=0.12, floor=0.30, restrict=None):
    """Return (is_unique, runner_up_key, gold_score). Unique iff the gold is the
    clear argmax: no OTHER candidate scores within `margin` of it AND above `floor`."""
    gold = jaccard(query_tokens, index.get(gold_key, set()))
    rival, rival_key = 0.0, None
    for k, toks in index.items():
        if k == gold_key or (restrict is not None and k not in restrict):
            continue
        j = jaccard(query_tokens, toks)
        if j > rival:
            rival, rival_key = j, k
    unique = gold > 0 and gold >= floor and (gold - rival) >= margin
    contested = rival >= floor and (gold - rival) < margin
    return unique, rival_key, gold, rival, contested


# ---------------------------------------------------------------------------
# Recipe generators -- each yields candidate dicts:
#   {recipe, category, query, predicate, gen{...}, notes, resolve{...}, ambiguity}
# ---------------------------------------------------------------------------
_OL_TEMPLATES = ["operator that {c}", "which operator {c}", "find an operator that {c}",
                 "is there an operator that {c}"]


_CAP_CAVEAT = {"hardware", "os", "supported", "requires", "require", "only", "available",
               "deprecated", "platform", "note", "warning", "experimental"}


def _good_capability(cap: str) -> bool:
    """A real capability clause, not a residual caveat/label fragment."""
    if not cap or ":" in cap:                            # residual "Label:" never makes a clean query
        return False
    toks = cap.split()
    if toks and toks[0].lower() in _CAP_CAVEAT:
        return False
    # >=4 content words: keeps terse-but-valid capabilities (e.g. MAT "renders a
    # constant color on a material"); real truncation is caught by the paren /
    # dangling-end / U+FFFD guards in is_malformed regardless of length.
    return len(content_tokens(cap)) >= 4


def gen_operator_lookup(ops, idx: Indices, safe_pyc):
    """ENUMERATE every operator (no cap). Emit a capability query for each that
    passes the gates; otherwise SKIP and record (operator, family, reason) — the
    skip list is itself a KB-quality finding (boilerplate/ambiguous summaries)."""
    out, skips = [], []
    fam_members = defaultdict(set)
    for o in ops:
        if o.get("family") in FAMILIES:
            fam_members[o["family"]].add(o["name"])
    for i, op in enumerate(ops):
        name, fam, pyc = op.get("name"), op.get("family"), op.get("python_class") or ""
        if not name or fam not in FAMILIES:
            continue
        summary = op.get("summary") or ""
        if not summary.strip():
            skips.append({"operator": name, "family": fam, "reason": "no_summary"}); continue
        if re.search(r"\bdeprecated\b", summary[:80], re.IGNORECASE):
            skips.append({"operator": name, "family": fam, "reason": "deprecated"}); continue
        strip, hard = op_identity(op)
        cap = cap_len(lead_case(strip_phrases(first_sentence(strip_leading_boilerplate(summary)), strip)))
        if not _good_capability(cap):
            skips.append({"operator": name, "family": fam, "reason": "boilerplate_or_thin_summary"}); continue
        query = _OL_TEMPLATES[i % len(_OL_TEMPLATES)].format(c=cap)
        if has_leak(query, hard):
            skips.append({"operator": name, "family": fam, "reason": "name_leak_in_summary"}); continue
        if is_malformed(query):
            skips.append({"operator": name, "family": fam, "reason": "malformed_query"}); continue
        qt = content_tokens(cap)
        uniq, rival, g, r, contested = _dominates(qt, name, idx.op_tokens)
        ambiguity = "unique"
        if not uniq:
            uf, _, gf, rf, _ = _dominates(qt, name, idx.op_tokens, restrict=fam_members[fam])
            if uf:
                query = f"{query} (it is a {fam} operator)"
                ambiguity = "disambiguated"
            else:
                skips.append({"operator": name, "family": fam, "reason": "ambiguous_capability"}); continue
        clauses = []
        if pyc in safe_pyc:
            clauses.append({"python_class_any": [pyc]})
        clauses.append({"op_name_any": [name]})
        out.append({
            "recipe": "operator_lookup", "category": "operator_lookup", "query": query,
            "predicate": {"clauses": clauses},
            "gen": {"family": fam, "kind": "operator", "chunk_type": "operator_overview",
                    "source": "operators.json#summary", "ambiguity": ambiguity, "op": name},
            "notes": f"gold={clauses[0].get('python_class_any', [name])[0]}; "
                     f"cap from summary (name/family/class stripped); domJ={g:.2f}/{r:.2f}",
            "resolve": {"kind": "operator", "pyc": pyc, "name": name},
        })
    return out, skips


_PA_TEMPLATES = ["what is the default of {op}'s {d} parameter",
                 "default value of the {d} parameter on the {op}",
                 "on a {op}, what is the default {d}",
                 "the {op} {d} parameter default"]
_KIND = {"float": "scalar", "int": "scalar", "menu": "menu", "toggle": "toggle",
         "string": "string", "op": "op"}


def _params_file(res: Path, op: dict):
    name = (op.get("name") or "").replace(" ", "_")
    f = res / "operator_ground_truth" / "params" / f"{op.get('family')}_{name}_defaults.json"
    return f if f.exists() else None


def _tuplet_subfield(res: Path, op: dict, code: str):
    """Tuplet base code (lag) carries its real default on element '<code>1' (lag1)
    with a real page; operators.json drops it (type=None)."""
    f = _params_file(res, op)
    if not f:
        return None
    try:
        pd = json.loads(f.read_text(encoding="utf-8")).get("parameters", {})
    except Exception:
        return None
    for k in (code + "1", code):
        e = pd.get(k)
        if e and e.get("default") not in (None, "") and (e.get("page") or "") not in ("", "Common"):
            return k, e["default"], e.get("page")
    return None


def _fmt_default(v):
    return repr(round(v, 4)) if isinstance(v, float) else repr(v)


# universal/utility params: on the Common page OR shared across many operators
def _is_op_specific_param(idx: Indices, code: str, label: str, page: str) -> bool:
    if page in ("Common", ""):
        return False
    return len(idx.code_ops.get(code.lower(), ())) <= 40 and len(idx.label_ops.get(label.lower(), ())) <= 40


def gen_parameter(ops, res: Path, idx: Indices, safe_pyc):
    out = []
    n = 0
    for op in ops:
        name, fam, pyc = op.get("name"), op.get("family"), op.get("python_class") or ""
        if not name or fam not in FAMILIES:
            continue
        for p in op.get("parameters") or []:
            code = p.get("code")
            disp = (p.get("display_name") or "").strip()
            if not code or not disp:
                continue
            ptype, default, page = p.get("type"), p.get("default"), p.get("page") or ""
            if ptype in _KIND and default not in (None, ""):
                kind, note = _KIND[ptype], f"default={_fmt_default(default)} ({ptype})"
            elif ptype is None:                                  # tuplet/multi-value
                tf = _tuplet_subfield(res, op, code)
                if not tf:
                    continue
                sub, dv, page = tf
                kind, note = "tuplet", f"tuplet {code}->{sub} default={_fmt_default(dv)}"
            else:
                continue
            if not _is_op_specific_param(idx, code, disp, page):  # reject Common/shared params
                continue
            tmpl = _PA_TEMPLATES[n % len(_PA_TEMPLATES)]
            n += 1
            query = tmpl.format(op=name, d=disp)
            if is_malformed(query):
                continue
            # gold is op-LEVEL parameter_group; op name in the query makes it UNIQUE (disambiguated)
            clauses = [{"op_name_any": [name], "type_any": ["parameter_group"]}]
            if pyc in safe_pyc:
                clauses.append({"python_class_any": [pyc], "type_any": ["parameter_group"]})
            out.append({
                "recipe": "parameter", "category": "parameter", "query": query,
                "predicate": {"clauses": clauses},
                "gen": {"family": fam, "kind": kind, "chunk_type": "parameter_group",
                        "source": "operators.json#parameters", "ambiguity": "disambiguated", "op": name},
                "notes": f"op={name}; code={code} [{page}]; {note}; op-specific; op-name carried in query",
                "resolve": {"kind": "operator", "pyc": pyc, "name": name},
            })
    return out


_PD_TEMPLATES = ["prebuilt component for {c}", "is there a palette component for {c}",
                 "ready-made component for {c}", "palette component for {c}"]


def _placeholder_purpose(p: str, name: str, cat: str) -> bool:
    pl = p.lower()
    return (len(p) < 30 or
            bool(re.match(rf"^{re.escape(cat)}\s+component for\s+{re.escape(name)}\s*$", p, re.I)) or
            any(b in pl for b in ("these extensions", "this extension", "reference a specific",
                                  "component for ", "see the wiki", "no description")))


def gen_palette(catalog: dict, idx: Indices):
    comps = [(k, v) for k, v in catalog.items() if k != "_metadata" and isinstance(v, dict)]
    # de-dupe identical/near-identical purposes (keep none of a colliding pair — neither is unique)
    norm_purpose = {}
    for nm, e in comps:
        pur = clean_text(e.get("purpose") or e.get("summary") or "")
        norm_purpose[nm] = re.sub(r"\(\s*palette\b[^)]*\)", " ", pur, flags=re.IGNORECASE)
    out = []
    i = 0
    for nm, e in comps:
        cat = e.get("category") or ""
        pur = norm_purpose[nm]
        if _placeholder_purpose(pur, nm, cat):
            continue
        cap = strip_phrases(first_sentence(pur), idx.comp_names)   # strip ALL comp names
        cap = lead_case(cap)
        query = _PD_TEMPLATES[i % len(_PD_TEMPLATES)].format(c=cap)
        if is_malformed(query) or has_leak(query, {nm}):
            continue
        # uniqueness: this comp's purpose must clearly dominate the field
        qt = content_tokens(cap)
        uniq, rival, g, r, _ = _dominates(qt, nm, idx.comp_tokens, margin=0.10, floor=0.25)
        if not uniq:
            continue
        i += 1
        out.append({
            "recipe": "palette_discovery", "category": "palette_discovery", "query": query,
            "predicate": {"clauses": [{"store_any": ["td_block"], "meta_name_any": [nm]}]},
            "gen": {"family": "PALETTE", "kind": cat or "uncategorized", "chunk_type": "block_overview",
                    "source": "palette_semantic_catalog.yaml#purpose", "ambiguity": "unique"},
            "notes": f"comp={nm} [{cat}]; from distinctive purpose; domJ={g:.2f}/{r:.2f}",
            "resolve": {"kind": "palette", "name": nm},
        })
    return out


_PY_TEMPLATES = ["in python, {d}", "how do I {d} in python", "python method to {d}",
                 "what is the python call to {d}"]


def _humanize_class(cls: str) -> str:
    stem = cls[:-6] if cls.endswith("_Class") else cls
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", stem)


def gen_python(class_desc: dict, idx: Indices):
    out = []
    i = 0
    for cls, methods in class_desc.items():
        if not isinstance(methods, dict):
            continue
        for method, desc in methods.items():
            if not isinstance(desc, str):
                continue
            carriers = sorted(idx.method_classes.get(method, {cls}))
            # strip only the full class token + multiword humanized class; KEEP the
            # method noun + domain nouns (the 78-q keeps "frame"/"samples"/"rows").
            strip = {cls}
            hcls = _humanize_class(cls)
            if len(hcls.split()) >= 2:
                strip.add(hcls)
            d = lead_case(strip_phrases(first_sentence(desc), strip))
            query = _PY_TEMPLATES[i % len(_PY_TEMPLATES)].format(d=d)
            if is_malformed(query) or has_leak(query, {cls}):
                continue
            i += 1
            if len(carriers) == 1:                       # member defined on exactly one class -> UNIQUE
                clauses = [{"type_any": ["class_method"], "class_any": [cls], "method_any": [method]}]
                amb = "unique"
                note = f"{cls}.{method} (sole carrier)"
            else:                                        # shared/inherited -> ACCEPT-SET multi
                clauses = [{"type_any": ["class_method"], "method_any": [method], "class_any": carriers}]
                amb = "multi"
                note = f"method '{method}' on {len(carriers)} classes -> accept-set"
            out.append({
                "recipe": "python", "category": "python", "query": query,
                "predicate": {"clauses": clauses},
                "gen": {"family": "PYTHON", "kind": "class_method", "chunk_type": "class_method",
                        "source": "class_semantic_descriptions.yaml", "ambiguity": amb,
                        "n_carriers": len(carriers)},
                "notes": note + "; query from method description (method noun kept)",
                "resolve": {"kind": "python", "cls": cls, "method": method, "carriers": carriers},
            })
    return out


_BI_TEMPLATES = ["wire a {s} into a {d}", "how do I connect a {s} to a {d}",
                 "convert a {s} into a {d}", "I have a {s} and want a {d}",
                 "feed a {s} into a {d}"]
_CONV_RE = re.compile(r"^(CHOP|TOP|SOP|DAT|POP|MAT|COMP) to (CHOP|TOP|SOP|DAT|POP|MAT|COMP)$")


def gen_build_instruction(ops, safe_pyc):
    out, i = [], 0
    for op in ops:
        name, pyc = op.get("name") or "", op.get("python_class") or ""
        m = _CONV_RE.match(name)
        if not m:
            continue
        src, dst = m.group(1), m.group(2)
        query = _BI_TEMPLATES[i % len(_BI_TEMPLATES)].format(s=src, d=dst)
        i += 1
        if has_leak(query, {name, pyc}):
            continue
        clauses = [{"type_any": ["build_instruction"], "op_name_any": [name]}]
        if pyc in safe_pyc:
            clauses.append({"type_any": ["build_instruction"], "python_class_any": [pyc]})
        out.append({
            "recipe": "build_instruction", "category": "build_instruction", "query": query,
            "predicate": {"clauses": clauses},
            "gen": {"family": dst, "kind": f"{src}->{dst}", "chunk_type": "build_instruction",
                    "source": "operators.json (converter ops)", "ambiguity": "unique", "op": name},
            "notes": f"converter {name}; src={src} dst={dst}",
            "resolve": {"kind": "operator", "pyc": pyc, "name": name},
        })
    return out


_CN_TEMPLATES = ["what touchdesigner concept is this: {d}", "touchdesigner term that means {d}",
                 "explain the touchdesigner concept where {d}", "in touchdesigner, the idea that {d}"]
_CONCEPT_BLACKLIST = {"videos", "tutorials", "examples", "release notes", "experimental",
                      "palette", "snippets", "category", "deprecated"}
_FAM_SUFFIX = re.compile(r"\b(CHOP|TOP|SOP|DAT|COMP|MAT|POP)$")


def gen_concept(concept_desc: dict, idx: Indices, op_names_norm: set):
    terms = [t for t in concept_desc if isinstance(concept_desc.get(t), str)]
    # prefix/near-name collisions: drop ALL terms that collide on a normalized prefix
    nt = {t: _norm(t) for t in terms}
    collide = set()
    items = list(nt.items())
    for a in range(len(items)):
        t1, n1 = items[a]
        for b in range(a + 1, len(items)):
            t2, n2 = items[b]
            if n1 and n2 and (n1.startswith(n2) or n2.startswith(n1)) and min(len(n1), len(n2)) >= 5:
                collide.add(t1); collide.add(t2)
    out, i = [], 0
    for term in terms:
        tl = term.lower()
        defn = concept_desc[term]
        dl = defn.lower()
        if (tl in _CONCEPT_BLACKLIST or _norm(term) in op_names_norm or
                _FAM_SUFFIX.search(term) or term in collide or
                ":" in term or                                    # MediaWiki namespace (Widget:Vimeo, Category:X)
                re.search(r"\b(vid|video|tutorial|course|webinar|workshop)$", tl) or
                tl.startswith(("introduction to", "intro to", "getting started")) or
                dl.startswith(("mediawiki", "video tutorial", "this video", "tutorial")) or
                "mediawiki widget" in dl[:40]):
            continue                                     # op names / site-sections / videos / wiki artifacts / near-dups
        d = lead_case(strip_phrases(first_sentence(defn), {term}))
        query = _CN_TEMPLATES[i % len(_CN_TEMPLATES)].format(d=d)
        if is_malformed(query) or has_leak(query, {term}):
            continue
        # disambiguation: gold definition must clearly dominate the glossary field
        qt = content_tokens(d)
        uniq, rival, g, r, _ = _dominates(qt, term, idx.term_tokens, margin=0.12, floor=0.28)
        if not uniq:
            continue
        i += 1
        out.append({
            "recipe": "concept", "category": "concept", "query": query,
            "predicate": {"clauses": [{"type_any": ["concept"], "term_any": [term]}]},
            "gen": {"family": "CONCEPT", "kind": "glossary", "chunk_type": "concept",
                    "source": "concept_semantic_descriptions.yaml", "ambiguity": "unique"},
            "notes": f"term={term}; from definition (term stripped); domJ={g:.2f}/{r:.2f}",
            "resolve": {"kind": "concept", "term": term},
        })
    return out


_NEG_EASY = [
    "book a restaurant reservation for tonight", "what is the capital of France",
    "convert 50 US dollars to euros", "write a haiku about autumn leaves",
    "schedule a dentist appointment next week", "best hiking trails near Denver",
    "translate good morning into Japanese", "calculate the tip on a 45 dollar bill",
    "how to bake sourdough bread at home", "current stock price of a tech company",
    "rules of the game of chess", "recipe for a vegetarian lasagna",
]
# TD-ADJACENT hard negatives: reuse creative-coding/DSP/GPU vocab so abstention must
# rely on score CALIBRATION, not lexical distance from the domain.
_NEG_HARD = [
    "write a Shadertoy GLSL fragment shader for a Mandelbrot set",
    "build a Niagara particle emitter in Unreal Engine",
    "set up an FM synthesis gen~ patch in Max MSP",
    "convert a polygon mesh to NURBS in Houdini",
    "configure a vvvv gamma boygroup for multi-machine rendering",
    "create a Blender geometry nodes scatter on a surface",
    "write a WebGL vertex shader with instanced rendering",
    "make a Processing sketch that draws a flow field",
    "set up an Ableton Live audio effect rack with sidechain",
    "TouchOSC layout to send MIDI control change messages",
    "openFrameworks ofShader bloom post-processing pass",
    "Resolume Arena composition with audio-reactive clips",
]


def gen_negative():
    out = []
    for q in _NEG_EASY:
        out.append({"recipe": "negative", "category": "negative", "query": q, "predicate": None,
                    "gen": {"family": "NONE", "kind": "easy", "chunk_type": "none",
                            "source": "templated", "ambiguity": "n/a"},
                    "notes": "out-of-domain (everyday) — abstain", "resolve": {"kind": "negative"}})
    for q in _NEG_HARD:
        out.append({"recipe": "negative", "category": "negative", "query": q, "predicate": None,
                    "gen": {"family": "NONE", "kind": "hard", "chunk_type": "none",
                            "source": "templated", "ambiguity": "n/a"},
                    "notes": "TD-adjacent out-of-KB — abstention needs score calibration",
                    "resolve": {"kind": "negative"}})
    return out


# ---------------------------------------------------------------------------
# Self-verify: gold resolves against ground truth (the 1st guarantee)
# ---------------------------------------------------------------------------
def make_verifier(gt: GroundTruth, palette_names, python_pairs, concept_terms):
    def resolves(item) -> bool:
        r = item["resolve"]; k = r["kind"]
        if k == "operator":
            return gt.pyclass_ok(r.get("pyc")) or gt.name_ok(r.get("name"))
        if k == "palette":
            return r["name"] in palette_names
        if k == "python":
            return all((c, r["method"]) in python_pairs for c in r.get("carriers", [r.get("cls")]))
        if k == "concept":
            return r["term"] in concept_terms
        if k == "negative":
            return True
        return False
    return resolves


# ---------------------------------------------------------------------------
# Stratified round-robin selection (seeded; covers every non-empty stratum)
# ---------------------------------------------------------------------------
def stratified(cands, key_fn, total, rng):
    groups = defaultdict(list)
    for c in cands:
        groups[key_fn(c)].append(c)
    for g in groups.values():
        rng.shuffle(g)
    keys = sorted(groups, key=str)
    rng.shuffle(keys)
    picked, exhausted = [], set()
    while len(picked) < total and len(exhausted) < len(keys):
        for kk in keys:
            if len(picked) >= total:
                break
            if groups[kk]:
                picked.append(groups[kk].pop())
            else:
                exhausted.add(kk)
    return picked


# ---------------------------------------------------------------------------
# Optional paraphrase pass (naturalness only; the gold NEVER changes)
# ---------------------------------------------------------------------------
def apply_paraphrases(rows, cache, gt, idx, seed):
    """Replace the template query with a cached natural paraphrase IFF it re-passes
    every gate (gold resolves [unchanged], no leak, not malformed, still unique to
    the same gold). Else keep the deterministic template (safe fallback)."""
    stats = defaultdict(lambda: {"have": 0, "kept": 0})
    for r in rows:
        if r["category"] == "negative":
            continue
        key = f"{seed}:{r['id']}"
        para = cache.get(key)
        cat = r["category"]
        if not para:
            continue
        stats[cat]["have"] += 1
        if not _paraphrase_ok(r, para, idx):
            continue                                  # fails a gate -> keep template
        r["query"] = para
        r["gen"]["paraphrased"] = True
        stats[cat]["kept"] += 1
    return stats


def _paraphrase_ok(row, para, idx: Indices) -> bool:
    if is_malformed(para):
        return False
    res = row.get("_resolve") or {}
    cat = row["category"]
    # leak + uniqueness re-check against the SAME gold
    if cat == "operator_lookup":
        op = idx.op_by_name.get(res.get("name"))
        if not op:
            return False
        _, hard = op_identity(op)
        if has_leak(para, hard):
            return False
        uniq, *_ = _dominates(content_tokens(para), res["name"], idx.op_tokens)
        same = {o["name"] for o in idx.ops if o.get("family") == op.get("family")}
        uf, *_ = _dominates(content_tokens(para), res["name"], idx.op_tokens, restrict=same)
        return uniq or uf
    if cat == "palette_discovery":
        if has_leak(para, {res.get("name")}):
            return False
        uniq, *_ = _dominates(content_tokens(para), res["name"], idx.comp_tokens, margin=0.10, floor=0.25)
        return uniq
    if cat == "concept":
        if has_leak(para, {res.get("term")}):
            return False
        uniq, *_ = _dominates(content_tokens(para), res["term"], idx.term_tokens, margin=0.12, floor=0.28)
        return uniq
    if cat == "python":
        return not has_leak(para, {res.get("cls")})
    if cat == "parameter":
        return res.get("name", "").lower() in para.lower()   # op-name context must survive
    if cat == "build_instruction":
        return True
    return False


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Phase-0.6 coverage-tier query generator (hardened)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(EVAL_DIR / "coverage_queries.jsonl"))
    ap.add_argument("--kb", default=None)
    ap.add_argument("--resources", default=None)
    ap.add_argument("--gt-operators", default=None)
    ap.add_argument("--gt-types", default=None)
    # COVERAGE mode (Phase 0.6c): operator_lookup ENUMERATES all ops (no cap); parameter
    # is greedy set-cover (recover ops uncovered by operator_lookup, then fill family×kind).
    ap.add_argument("--n-parameter", type=int, default=620, help="parameter total cap (set-cover budget)")
    ap.add_argument("--per-op-params", type=int, default=2, help="max parameter items per operator")
    ap.add_argument("--fk-min", type=int, default=8, help="target parameter items per family×kind cell")
    ap.add_argument("--n-palette", type=int, default=60)
    ap.add_argument("--n-python", type=int, default=110)
    ap.add_argument("--n-build", type=int, default=24)
    ap.add_argument("--n-concept", type=int, default=80)
    ap.add_argument("--n-python-multi", type=int, default=20, help="cap on multi accept-set python items")
    ap.add_argument("--max-total", type=int, default=1800, help="hard cap on total emitted items")
    ap.add_argument("--paraphrase", action="store_true", help="apply eval/paraphrase_cache.json (re-gated)")
    ap.add_argument("--paraphrase-cache", default=str(EVAL_DIR / "paraphrase_cache.json"))
    ap.add_argument("--check-kb", dest="check_kb", action="store_true", default=True)
    ap.add_argument("--no-check-kb", dest="check_kb", action="store_false")
    args = ap.parse_args()

    import random
    rng = random.Random(args.seed)

    kb_root = resolve_kb_root(args.kb).resolve()
    res = resolve_resources(args.resources, kb_root).resolve()
    gt_ops = Path(args.gt_operators) if args.gt_operators else kb_root / "operators.json"
    gt_types = Path(args.gt_types) if args.gt_types else \
        res / "operator_ground_truth" / "operator_types.json"
    print(f"KB:        {kb_root}\nResources: {res}", file=sys.stderr)

    gt = GroundTruth(operators_json=gt_ops, operator_types_json=gt_types)
    import yaml
    ops = json.loads(gt_ops.read_text(encoding="utf-8"))["operators"]
    catalog = yaml.safe_load((res / "expertise" / "palette_semantic_catalog.yaml").read_text(encoding="utf-8"))
    class_desc = yaml.safe_load((res / "haiku_output" / "class_semantic_descriptions.yaml").read_text(encoding="utf-8"))
    concept_desc = yaml.safe_load((res / "haiku_output" / "concept_semantic_descriptions.yaml").read_text(encoding="utf-8"))

    idx = Indices(ops, catalog, class_desc, concept_desc)
    safe_pyc = safe_python_classes(ops)
    palette_names = {k for k in catalog if k != "_metadata"}
    python_pairs = {(c, m) for c, ms in class_desc.items() if isinstance(ms, dict) for m in ms}
    concept_terms = set(concept_desc)
    op_names_norm = {_norm(o["name"]) for o in ops}
    resolves = make_verifier(gt, palette_names, python_pairs, concept_terms)

    ol_out, ol_skips = gen_operator_lookup(ops, idx, safe_pyc)
    raw = {
        "operator_lookup": ol_out,
        "parameter": gen_parameter(ops, res, idx, safe_pyc),
        "palette_discovery": gen_palette(catalog, idx),
        "python": gen_python(class_desc, idx),
        "build_instruction": gen_build_instruction(ops, safe_pyc),
        "concept": gen_concept(concept_desc, idx, op_names_norm),
        "negative": gen_negative(),
    }

    # ---- self-verify: gold resolves (drop unresolved) ----
    drops = Counter()
    verified = {}
    for recipe, cands in raw.items():
        keep = []
        for c in cands:
            if resolves(c):
                keep.append(c)
            else:
                drops[f"{recipe}:unresolved"] += 1
        verified[recipe] = keep

    selected = {}
    # operator_lookup: ENUMERATE-ALL — emit every operator that passed the gates (no cap)
    selected["operator_lookup"] = verified["operator_lookup"]
    covered_ops = {c["gen"]["op"] for c in selected["operator_lookup"]}

    # parameter: GREEDY SET-COVER. Phase A recovers operators NOT covered by
    # operator_lookup (1 op-specific param each → extends operator coverage);
    # Phase B fills every family×kind cell to --fk-min. Caps: per-op + total.
    pa = verified["parameter"]
    by_op = defaultdict(list)
    for c in pa:
        by_op[c["gen"]["op"]].append(c)
    for v in by_op.values():
        v.sort(key=lambda c: (c["gen"]["kind"], c["query"]))
        rng.shuffle(v)
    pa_sel, sel_ids, per_op, fk = [], set(), Counter(), Counter()
    cap = args.n_parameter

    def _take(c):
        pa_sel.append(c); sel_ids.add(id(c))
        per_op[c["gen"]["op"]] += 1
        fk[(c["gen"]["family"], c["gen"]["kind"])] += 1
        covered_ops.add(c["gen"]["op"])

    recover = sorted(op for op in by_op if op not in covered_ops)
    rng.shuffle(recover)
    for op in recover:                                   # Phase A: maximise operator coverage
        if len(pa_sel) >= cap:
            break
        _take(by_op[op][0])
    cells = sorted({(c["gen"]["family"], c["gen"]["kind"]) for c in pa})
    by_cell = defaultdict(list)
    for c in pa:
        if id(c) not in sel_ids:
            by_cell[(c["gen"]["family"], c["gen"]["kind"])].append(c)
    progress = True
    while progress and len(pa_sel) < cap:                # Phase B: fill family×kind cells
        progress = False
        for cell in cells:
            if fk[cell] >= args.fk_min or len(pa_sel) >= cap:
                continue
            pool = by_cell[cell]
            while pool:
                c = pool.pop()
                if per_op[c["gen"]["op"]] >= args.per_op_params:
                    continue
                _take(c); progress = True
                break
    selected["parameter"] = pa_sel
    for c in pa_sel:                                     # build edges + converters also cover ops
        covered_ops.add(c["gen"]["op"])

    # palette / concept / build: emit all gate-passing (capped); python: unique + capped multi
    selected["palette_discovery"] = stratified(verified["palette_discovery"],
                                               lambda c: c["gen"]["kind"], args.n_palette, rng)
    selected["concept"] = stratified(verified["concept"], lambda c: 0, args.n_concept, rng)
    selected["build_instruction"] = stratified(verified["build_instruction"],
                                               lambda c: c["gen"]["kind"], args.n_build, rng)
    py_u = [c for c in verified["python"] if c["gen"]["ambiguity"] == "unique"]
    py_m = [c for c in verified["python"] if c["gen"]["ambiguity"] == "multi"]
    selected["python"] = (stratified(py_u, lambda c: c["resolve"]["cls"], args.n_python, rng)
                          + stratified(py_m, lambda c: c["resolve"]["method"], args.n_python_multi, rng))
    selected["negative"] = verified["negative"]
    for c in selected["build_instruction"]:
        covered_ops.add(c["gen"]["op"])

    # ---- assign ids + finalize rows ----
    prefix = {"operator_lookup": "ol", "parameter": "pa", "palette_discovery": "pd",
              "python": "py", "build_instruction": "bi", "concept": "cn", "negative": "ne"}
    order = ["operator_lookup", "parameter", "palette_discovery", "python",
             "build_instruction", "concept", "negative"]
    rows = []
    for recipe in order:
        for k, c in enumerate(selected[recipe], 1):
            row = {"id": f"cov-{prefix[recipe]}-{k:03d}", "query": c["query"], "category": c["category"]}
            if recipe == "negative":
                row["expect_no_match"] = True
            else:
                row["relevant_predicate"] = c["predicate"]
            row["notes"] = c["notes"]
            row["gen"] = c["gen"]
            row["_resolve"] = c["resolve"]                 # internal, stripped before write
            rows.append(row)

    # ---- optional paraphrase pass (re-gated; gold unchanged) ----
    para_stats = {}
    if args.paraphrase:
        cache_path = Path(args.paraphrase_cache)
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        para_stats = apply_paraphrases(rows, cache, gt, idx, args.seed)

    for r in rows:
        r.pop("_resolve", None)
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                        encoding="utf-8")

    # ---- coverage accounting (set-cover result) ----
    fam_ops = defaultdict(set)
    for o in ops:
        if o.get("family") in FAMILIES:
            fam_ops[o["family"]].add(o["name"])
    ol_emit = defaultdict(set)
    for r in rows:
        if r["category"] == "operator_lookup":
            ol_emit[r["gen"]["family"]].add(r["gen"]["op"])
    covered_by_fam = defaultdict(set)
    for r in rows:
        op = r["gen"].get("op")
        if op and r["gen"].get("family") in FAMILIES and r["category"] in ("operator_lookup", "parameter", "build_instruction"):
            covered_by_fam[r["gen"]["family"]].add(op)
    for s in ol_skips:                                   # annotate: was a skipped op recovered via parameter?
        s["covered_via"] = "parameter" if s["operator"] in covered_by_fam.get(s["family"], set()) else None
    # goal-checklist facts (computed here so coverage_report can surface them all)
    unamb = _unambiguous_rates(rows)
    leaks = _count_answer_leaks(rows)
    matchable = _check_against_kb(rows, kb_root) if args.check_kb else None
    coverage_meta = {
        "seed": args.seed, "total_items": len(rows), "max_total": args.max_total,
        "operators_total_by_family": {f: len(fam_ops[f]) for f in FAMILIES},
        "operators_covered_by_family": {f: len(covered_by_fam[f]) for f in FAMILIES},
        "operator_lookup_emit_by_family": {f: len(ol_emit[f]) for f in FAMILIES},
        "coverage_pct_by_family": {f: round(100 * len(covered_by_fam[f]) / max(len(fam_ops[f]), 1), 1) for f in FAMILIES},
        "worst_family_coverage_pct": min(round(100 * len(covered_by_fam[f]) / max(len(fam_ops[f]), 1), 1) for f in FAMILIES),
        "param_kind_by_family": {f: dict(Counter(r["gen"]["kind"] for r in rows
                                                  if r["category"] == "parameter" and r["gen"]["family"] == f))
                                 for f in FAMILIES},
        "param_kinds_present": sorted({r["gen"]["kind"] for r in rows if r["category"] == "parameter"}),
        "chunk_type_counts": dict(Counter(r["gen"]["chunk_type"] for r in rows if r["category"] != "negative")),
        "category_counts": dict(Counter(r["category"] for r in rows)),
        "palette_categories": sorted({r["gen"]["kind"] for r in rows if r["category"] == "palette_discovery"}),
        "unambiguous_rate_by_category": unamb,
        "answer_leaks": leaks,
        "kb_matchable": matchable,
        "skipped_operators": sorted(ol_skips, key=lambda s: (s["family"], s["reason"], s["operator"])),
        "skipped_uncovered": sorted(s["operator"] for s in ol_skips if not s["covered_via"]),
    }
    meta_path = out_path.with_name("coverage_meta.json")
    meta_path.write_text(json.dumps(coverage_meta, indent=2), encoding="utf-8")

    _summary(rows, verified, selected, drops, order, args, para_stats, out_path, coverage_meta)
    assert all(v >= 0.9 for v in unamb.values()), "unambiguous-rate < 0.9 in some category"
    assert leaks == 0, f"{leaks} answer-leaks detected"


# ---------------------------------------------------------------------------
def _summary(rows, verified, selected, drops, order, args, para_stats, out_path, cm):
    print("=" * 72)
    print(f"coverage generator v{GENERATOR_VERSION}  seed={args.seed}  -> {len(rows)} items "
          f"(max-total {args.max_total})")
    print("=" * 72)
    for recipe in order:
        print(f"  {recipe:18s} selected {len(selected[recipe]):4d} / {len(verified[recipe]):4d} verified")
    if drops:
        print("  unresolved drops:", dict(drops))
    # ---- OPERATOR COVERAGE (the set-cover headline) ----
    print("\n  OPERATOR COVERAGE per family (covered by operator_lookup + parameter + build):")
    worst = 100.0
    for f in FAMILIES:
        tot = cm["operators_total_by_family"][f]
        cov = cm["operators_covered_by_family"][f]
        ol = cm["operator_lookup_emit_by_family"][f]
        pct = cm["coverage_pct_by_family"][f]
        worst = min(worst, pct)
        flag = "" if pct >= 90 else "  <90%"
        print(f"    {f:5s} {cov:3d}/{tot:3d} = {pct:5.1f}%  (op_lookup {ol}){flag}")
    print(f"    WORST family = {worst:.1f}%  | total skipped-from-op_lookup={len(cm['skipped_operators'])} "
          f"(uncovered-entirely={len(cm['skipped_uncovered'])})")
    print("  skip reasons:", dict(Counter(s["reason"] for s in cm["skipped_operators"])))
    # ---- param-kind × family grid ----
    print("  parameter kind×family grid:")
    kinds = ["scalar", "menu", "string", "toggle", "op", "tuplet"]
    print("    fam   " + " ".join(f"{k:>7s}" for k in kinds))
    for f in FAMILIES:
        g = cm["param_kind_by_family"][f]
        print(f"    {f:5s} " + " ".join(f"{g.get(k,0):7d}" for k in kinds))
    print("  chunk-type counts:", cm["chunk_type_counts"])
    print("  palette categories:", len(cm["palette_categories"]))
    print("  per-category unambiguous-rate:", cm["unambiguous_rate_by_category"])
    if para_stats:
        print("  paraphrase pass-rate:",
              {c: f"{s['kept']}/{s['have']}" for c, s in sorted(para_stats.items())})
    # ---- GOAL CHECKLIST (the verifiable stop condition) ----
    kinds6 = {"scalar", "menu", "string", "toggle", "op", "tuplet"}
    chunk6 = {"operator_overview", "parameter_group", "block_overview", "class_method",
              "concept", "build_instruction"}
    unamb_ok = all(v >= 0.9 for v in cm["unambiguous_rate_by_category"].values())
    match = cm.get("kb_matchable") or {}
    valid_ok = all(m == t for m, t in match.values()) if match else None
    print("\n  GOAL CHECKLIST:")
    print(f"    [{'x' if cm['worst_family_coverage_pct'] >= 90 else ' '}] operators >=90% EVERY family "
          f"(worst {cm['worst_family_coverage_pct']}%)")
    print(f"    [{'x' if kinds6 <= set(cm['param_kinds_present']) else ' '}] all 6 param kinds present "
          f"({sorted(cm['param_kinds_present'])})")
    print(f"    [{'x' if chunk6 <= set(cm['chunk_type_counts']) else ' '}] all targeted chunk types present "
          f"({sorted(cm['chunk_type_counts'])})")
    print(f"    [{'x' if unamb_ok else ' '}] per-category unambiguous-rate >=0.9")
    print(f"    [{'x' if cm['answer_leaks'] == 0 else ' '}] 0 answer-leakage ({cm['answer_leaks']})")
    print(f"    [{'x' if valid_ok else '?' if valid_ok is None else ' '}] ~100% valid gold (KB-matchable: "
          f"{match if match else 'not checked'})")
    print(f"    [{'x' if cm['total_items'] <= cm['max_total'] else ' '}] total <= {cm['max_total']} "
          f"({cm['total_items']})")
    print(f"\nwrote {out_path}\n      {out_path.with_name('coverage_meta.json')}")


def _unambiguous_rates(rows):
    """Per-category unambiguous-rate = (unique+disambiguated)/(non-multi emitted).
    multi items are reported separately (set-recall at measure). Returns {cat: rate}."""
    by_cat = defaultdict(Counter)
    for r in rows:
        if r["category"] == "negative":
            continue
        by_cat[r["category"]][r["gen"]["ambiguity"]] += 1
    rates = {}
    for cat, c in by_cat.items():
        non_multi = c["unique"] + c["disambiguated"]
        denom = non_multi + c.get("ambiguous", 0)
        rates[cat] = round(non_multi / denom, 3) if denom else 1.0
    return rates


# the entity-IS-answer recipes (operator_lookup/palette/concept/python): the gold
# entity's name must NOT appear in the query. parameter/build deliberately name the
# operator/families as CONTEXT (not the answer) -> excluded from this audit.
def _count_answer_leaks(rows) -> int:
    n = 0
    for r in rows:
        cat, q, pred = r["category"], r["query"], r.get("relevant_predicate")
        if cat not in ("operator_lookup", "palette_discovery", "concept", "python") or not pred:
            continue
        toks = set()
        for cl in pred["clauses"]:
            if cat == "operator_lookup":
                for v in cl.get("op_name_any", []) + cl.get("python_class_any", []):
                    toks.add(v); ws = str(v).split()
                    if len(ws) > 2 and ws[-1] in FAMILIES:
                        toks.add(" ".join(ws[:-1]))
            elif cat == "palette_discovery":
                toks |= set(cl.get("meta_name_any", []))
            elif cat == "concept":
                toks |= set(cl.get("term_any", []))
            elif cat == "python":                        # method noun is allowed (78-q keeps it);
                toks |= {t for t in cl.get("class_any", []) if "_" in t}   # only real class tokens, not base "COMP"
        if has_leak(q, toks):
            n += 1
    return n


def _check_against_kb(rows, kb_root: Path):
    """Search-free well-formedness / indexing-gap check (does each gold match >=1
    chunk). 100% = predicates well-formed; <100% = a real indexing gap (breadth
    signal), NOT a drop criterion."""
    try:
        import chromadb
        from predicates import is_relevant
    except Exception as e:
        print(f"\n(skipping --check-kb: {e})", file=sys.stderr)
        return None
    if not (kb_root / "vector_db" / "chroma.sqlite3").exists():
        # KF1: PersistentClient is create-if-missing — refuse, never create
        print(f"\n(skipping --check-kb: no vector_db at {kb_root / 'vector_db'})",
              file=sys.stderr)
        return None
    col = chromadb.PersistentClient(path=str(kb_root / "vector_db")).get_collection("td_unified")
    g = col.get(include=["metadatas", "documents"], limit=col.count())
    chunks = [{"metadata": m, "content": d} for m, d in zip(g["metadatas"], g["documents"])]
    matched, total = Counter(), Counter()
    for r in rows:
        pred = r.get("relevant_predicate")
        if not pred:
            continue
        total[r["category"]] += 1
        if any(is_relevant(ch, pred) for ch in chunks):
            matched[r["category"]] += 1
    print("\n  static KB indexing check (gold matches >=1 chunk; search-free):")
    for cat in sorted(total):
        print(f"    {cat:18s} {matched[cat]:3d}/{total[cat]:3d} matchable "
              f"({100 * matched[cat] // max(total[cat], 1)}%)")
    return {cat: [matched[cat], total[cat]] for cat in total}


if __name__ == "__main__":
    main()

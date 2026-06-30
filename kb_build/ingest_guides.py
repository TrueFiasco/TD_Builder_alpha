"""
§6.x Authoring guides -> GUIDE chunks (guide_overview / guide_section).

The `Write_a_*` wiki pages are how-to authoring docs (write a GLSL TOP, a C++ CHOP,
a CUDA DLL, a Shared-Memory CHOP, ...). They answer goal-shaped "how do I write a
…" queries that no operator/parameter chunk covers. The Phase-0 `howto` predicates
already accept `type:"guide"` (e.g. ho-07), so indexing these lifts howto directly.

Each guide -> one `guide_overview` (title + intro + section index, the richest
discriminator) + one `guide_section` per heading. Chunk_type stays granular for the
histogram, but **meta.type is forced to "guide"** so the howto `type_any` predicate
matches (it lists "guide", not "guide_overview"). Guides assert NO operator identity
(no python_class) so they stay clean through the name-integrity gate.

Sources (10 unique guides): the 3 GLSL guides from the clean markdown in
KB/wiki_supplemental; the other 7 from the MediaWiki HTML in
Resources/Learn/OfflineHelp/https.docs.derivative.ca (parsed with stdlib only —
bs4 is not available). wiki_url is carried for hydration.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

import common as C

# (page stem, display title, family|None, topic, source 'md'|'htm').
# C++ pages: title uses "C++" but we also fold "CPlusPlus" into the text so both
# phrasings retrieve. The 3 GLSL guides have clean markdown; the rest are HTML-only.
GUIDES = [
    ("Write_a_GLSL_TOP",          "Write a GLSL TOP",            "TOP",  "GLSL",          "md"),
    ("Write_a_GLSL_Material",     "Write a GLSL Material",       "MAT",  "GLSL",          "md"),
    ("Write_GLSL_POPs",           "Write GLSL POPs",             "POP",  "GLSL",          "md"),
    ("Write_a_CPlusPlus_CHOP",    "Write a C++ CHOP",            "CHOP", "C++ CPlusPlus", "htm"),
    ("Write_a_CPlusPlus_POP",     "Write a C++ POP",             "POP",  "C++ CPlusPlus", "htm"),
    ("Write_a_CPlusPlus_TOP",     "Write a C++ TOP",             "TOP",  "C++ CPlusPlus", "htm"),
    ("Write_a_CPlusPlus_Plugin",  "Write a C++ Plugin",          None,   "C++ CPlusPlus", "htm"),
    ("Write_a_CUDA_DLL",          "Write a CUDA DLL",            None,   "CUDA",          "htm"),
    ("Write_a_Shared_Memory_CHOP", "Write a Shared Memory CHOP", "CHOP", "Shared Memory", "htm"),
    ("Write_a_Shared_Memory_TOP",  "Write a Shared Memory TOP",  "TOP",  "Shared Memory", "htm"),
]

_OV_INTRO_CAP = 700
_SEC_CAP = 1200


def _squash(s: str) -> str:
    return " ".join((s or "").split())


# --------------------------------------------------------------------------- md
def _parse_md(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(intro, [(heading, body)]) from markdown. Intro = text before the first
    `##`/`###` after the title; sections split on `##`/`###` headings."""
    intro_lines: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    cur_h, cur_body = None, []
    for ln in text.splitlines():
        m = re.match(r"^(#{2,3})\s+(.*)$", ln)
        if re.match(r"^#\s+\S", ln):           # top title line — skip (we set our own)
            continue
        if m:
            if cur_h is not None:
                sections.append((cur_h, cur_body))
            cur_h, cur_body = m.group(2).strip(), []
        elif cur_h is None:
            intro_lines.append(ln)
        else:
            cur_body.append(ln)
    if cur_h is not None:
        sections.append((cur_h, cur_body))
    intro = _squash(" ".join(intro_lines))
    return intro, [(h, _squash(" ".join(b))) for h, b in sections if _squash(" ".join(b))]


# ------------------------------------------------------------------------- html
class _MWParser(HTMLParser):
    """Pull (heading, text) sections from a MediaWiki article body. Section breaks
    on h2/h3; ignores script/style/sup(citations) and the [edit] section links."""

    def __init__(self):
        super().__init__()
        self.sections: list[tuple[str, list[str]]] = []
        self.intro: list[str] = []
        self._cur_h = None
        self._buf: list[str] = []
        self._skip = 0          # inside script/style/sup
        self._in_head = 0       # inside h2/h3
        self._head_buf: list[str] = []
        self._in_editsection = 0

    def _flush(self):
        if self._cur_h is None:
            self.intro = self._buf
        else:
            self.sections.append((self._cur_h, self._buf))
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "sup"):
            self._skip += 1
        elif tag in ("h2", "h3"):
            self._flush()
            self._in_head += 1
            self._head_buf = []
        a = dict(attrs)
        if a.get("class") and "mw-editsection" in a.get("class", ""):
            self._in_editsection += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "sup") and self._skip:
            self._skip -= 1
        elif tag in ("h2", "h3") and self._in_head:
            self._in_head -= 1
            self._cur_h = _squash("".join(self._head_buf)) or "Section"
        # editsection close is approximated by the heading close; reset defensively
        if tag in ("h2", "h3"):
            self._in_editsection = 0

    def handle_data(self, data):
        if self._skip or self._in_editsection:
            return
        if self._in_head:
            self._head_buf.append(data)
        else:
            self._buf.append(data)


def _html_body(raw: str) -> str:
    """Bound the article to the MediaWiki content region (drop nav/footer chrome)."""
    i = raw.find("mw-parser-output")
    if i == -1:
        i = raw.find('id="mw-content-text"')
    if i != -1:                          # start AFTER the opening tag's '>' (not mid-tag)
        gt = raw.find(">", i)
        i = gt + 1 if gt != -1 else i
    body = raw[i:] if i != -1 else raw
    for marker in ('<div class="printfooter"', 'id="catlinks"', "<!-- \nNewPP",
                   "<!-- NewPP", 'class="mw-data-after-content"', 'id="footer"'):
        j = body.find(marker)
        if j != -1:
            body = body[:j]
    return body


def _parse_html(raw: str) -> tuple[str, list[tuple[str, str]]]:
    p = _MWParser()
    p.feed(_html_body(raw))
    p._flush()
    intro = _squash("".join(p.intro))
    secs = [(_squash(h), _squash("".join(b))) for h, b in p.sections]
    return intro, [(h, b) for h, b in secs if b]


# ------------------------------------------------------------------------ build
def build(idn: C.Identity) -> list[dict]:
    rows: list[dict] = []
    for stem, title, family, topic, src in GUIDES:
        if src == "md":
            path = C.WIKI_SUPPL / f"{stem}.md"
            if not path.exists():
                path = C.WIKI_DOCS / f"{stem}.htm"   # fall back to HTML if md missing
                src = "htm"
        else:
            path = C.WIKI_DOCS / f"{stem}.htm"
        if not path.exists():
            print(f"[guides] MISSING source for {title} ({path.name}) — skipped")
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        intro, sections = (_parse_md(raw) if src == "md" else _parse_html(raw))

        wiki_url = f"https://docs.derivative.ca/{stem}"
        base_meta = {
            "name": title,
            "guide_name": title,
            "topic": topic,
            "family": family,
            "wiki_url": wiki_url,
            "license_tier": "public",
        }
        gid = f"guide:{C.slug(stem)}:overview"
        sec_titles = [h for h, _ in sections]
        fam_word = f" {family}" if family else ""
        ov = (f"GUIDE: {title} — TouchDesigner authoring guide ({topic}{fam_word}). "
              f"{intro[:_OV_INTRO_CAP]}"
              + (f" Covers: {'; '.join(sec_titles[:14])}." if sec_titles else "")
              + f" wiki: {wiki_url}")
        ov_row = C.make_row(gid, ov, "guide_overview", C.STORE_GUIDE, dict(base_meta))
        ov_row["meta"]["type"] = "guide"          # howto type_any matches "guide"
        rows.append(ov_row)

        for i, (heading, body) in enumerate(sections):
            if not body:
                continue
            stext = f"GUIDE: {title} — {heading}. {body[:_SEC_CAP]} (wiki: {wiki_url})"
            smeta = dict(base_meta)
            smeta["section"] = heading
            srow = C.make_row(f"guide:{C.slug(stem)}:s{i}", stext,
                              "guide_section", C.STORE_GUIDE, smeta, parent=gid)
            srow["meta"]["type"] = "guide"
            rows.append(srow)
    return rows


# inputs pinned in sources.lock.json
INPUTS = (
    [C.WIKI_SUPPL / f"{s}.md" for s, _, _, _, src in GUIDES if src == "md"]
    + [C.WIKI_DOCS / f"{s}.htm" for s, _, _, _, _ in GUIDES]
)

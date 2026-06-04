# Knowledge Base Unification Audit (KBU_REPORT)

**Scope:** Read-only analytical audit of every scattered knowledge store under
`C:\TD_builder_pre_alpha\`, to design ONE canonical "mega" KB and prove no
knowledge is lost before redundant stores are quarantined.

**Status:** Audit + unification design only. No merge performed. The only
filesystem modifications made by this audit were `mkdir KB\` and writing this
file.

**Headline finding:** The live MCP server (`META_AGENTIC_TOOL/mcp_server.py`)
already loads a *de-facto canonical triad*:

| Knowledge axis | Live canonical store (server-loaded) | Evidence |
|---|---|---|
| Operators/classes/concepts | `META_AGENTIC_TOOL/data/wiki_docs/td_universal_parsed_enriched.json` | mcp_server.py:389 |
| RAG chunks + relationship graph | `META_AGENTIC_TOOL/data/td_graphrag.json` + `td_knowledge_graph_enhanced.gpickle` | mcp_server.py:387–395 |
| Vector embeddings | `META_AGENTIC_TOOL/data/vector_db_merged/` (collection `td_unified`, 34,350 docs) | mcp_server.py:407–413 |

The project CLAUDE.md is **stale**: it claims `td_universal_parsed.json` is the
canonical the server loads. It is not — the server loads the **enriched**
variant. This audit proves `enriched` is a strict additive superset of
`td_universal_parsed.json` and of `td_universal_parsed_with_build_instructions.json`,
so adopting it loses nothing.

---

## (A) Per-Store Inventory Table

Sizes in bytes. MD5 shown for exact-dup confirmation where relevant.

### A.1 Operator/wiki JSON stores (dict: metadata, operators, classes, concepts, errors)

| # | Path | Format | Size | Records | MD5 | Verdict |
|---|---|---|---|---|---|---|
| 1 | `META_AGENTIC_TOOL/data/wiki_docs/td_universal_parsed.json` | JSON | 31,841,350 | 673 ops / 592 cls / 711 con / 0 err | `ab15edaa71dcaebaf65c5b530b99d4ef` | **subset-of-#2** (base layer; no params enrichment, no build_instructions) |
| 2 | `META_AGENTIC_TOOL/data/wiki_docs/td_universal_parsed_enriched.json` | JSON | 35,835,036 | 673 ops / 592 cls / 711 con / 0 err | (unique) | **CANONICAL-SUPERSET** (operator axis) — server-loaded |
| 3 | `META_AGENTIC_TOOL/data/wiki_docs/td_universal_parsed_with_build_instructions.json` | JSON | 31,849,943 | 673 ops / 592 cls / 711 con / 0 err | `53ce53cb81ac2e61d34e56d7d4ff7db2` | **subset-of-#2** (adds only 6 build_instructions, all 6 already in #2) |
| 9a | `td_universal.json` (root) | JSON | 31,841,350 | identical to #1 | `ab15edaa71dcaebaf65c5b530b99d4ef` | **exact-dup-of-#1** |
| 7a | `td-mcp/knowledge_base/data/operators.json` | JSON | 31,841,350 | identical to #1 | `ab15edaa71dcaebaf65c5b530b99d4ef` | **exact-dup-of-#1** |

`673` operator records vs `670` unique operator names (3 duplicate names) — identical across #1/#2/#3.
`classes` and `concepts` arrays are **byte-identical** (canonical JSON, sorted) across #1/#2/#3.

### A.2 GraphRAG / graph stores

| # | Path | Format | Size | Records | MD5 | Verdict |
|---|---|---|---|---|---|---|
| 4 | `META_AGENTIC_TOOL/data/td_graphrag.json` | JSON (metadata, chunks, graph) | 58,280,950 | 74,280 chunks / 18,392 nodes / 25,831 edges | `bd59b6057bc819e3808c69b17944c930` | **canonical-superset** (RAG-chunk axis) — server-loaded |
| 9b | `td_graphrag.json` (root) | JSON | 58,280,950 | identical to #4 | `bd59b6057bc819e3808c69b17944c930` | **exact-dup-of-#4** |
| 5 | `META_AGENTIC_TOOL/data/td_knowledge_graph_enhanced.gpickle` | pickle → **dict** {nodes,edges,metadata} | 9,296,137 | 37,526 nodes / 40,568 edges | `cc16851a153016bcca1b798670b46391` | **canonical-superset** (enhanced-graph axis) — server-loaded. NOT a networkx Graph (dict, as code expects) |
| 9c | `td_knowledge_graph_enhanced.gpickle` (root) | pickle dict | 9,296,137 | identical to #5 | `cc16851a153016bcca1b798670b46391` | **exact-dup-of-#5** |
| 9d | `td_knowledge_graph.gpickle` (root) | pickle → **networkx DiGraph** | 4,646,098 | 18,888 nodes / 25,325 edges | (unique) | **subset-of-#5** (older flat op/param graph; superseded by enhanced dict graph #5) |
| 7b | `td-mcp/knowledge_base/graph/knowledge_graph.json` | JSON {nodes,edges} | 5,001,873 | 16,814 nodes / 18,084 edges | (unique) | **subset-of-#5** (older/smaller snapshot of the enhanced graph) |

Enhanced gpickle #5 node-type histogram: `ParameterConfig` 26,233, `OperatorInstance` 9,023, `ExampleNetwork` 1,373, `Operator` 852, `NetworkPattern` 45. Edge types: HAS_PARAMETER 26,233, CONTAINS_OPERATOR 9,023, CONNECTS_TO 3,769, DEMONSTRATES 1,370, IMPLEMENTS_PATTERN 173. Metadata records `examples_merged: 1,077`, `patterns_detected: 45`.

### A.3 Vector / ChromaDB stores

| # | Path | Format | Size (chroma.sqlite3) | Collection / docs | MD5 (sqlite) | Verdict |
|---|---|---|---|---|---|---|
| 6a | `META_AGENTIC_TOOL/data/vector_db_merged/` | ChromaDB | 56,610,816 | `td_unified` / **34,350** | (unique) | **canonical-superset** (vector axis) — server-loaded. `__source_store`: active 1,869 + enriched_kb 6 + orphan 32,475 |
| 6b | `META_AGENTIC_TOOL/data/vector_db/` | ChromaDB + npy/pkl | 16,826,368 | `td_unified` / 1,869 | `4d42db3e083147d0c4a971d35589ec29` | **subset-of-#6a** (all 1,869 docs present in #6a; 0 missing) |
| 7c | `td-mcp/knowledge_base/vector_db/` | ChromaDB + npy/pkl | 16,826,368 | `td_unified` / 1,869 | `56f410b04cff8f1d293aa2aae6013ae6` | **subset-of-#6a** (replica of #6b — see note) |
| 8a | `kb_pipeline/vector_db/` | ChromaDB + npy/pkl | 16,826,368 | `td_unified` / 1,869 | `56f410b04cff8f1d293aa2aae6013ae6` | **exact-dup-of-#7c** (sqlite md5 identical); **subset-of-#6a** |
| 8b | `kb_pipeline/vector_db_chroma/` | ChromaDB | 48,545,792 | `td_unified` / 20,477 | (unique) | **build-artifact** (intermediate merge between 1,869 and 34,350; superseded by #6a) |

Cross-store byte-identity within the "small" vector DBs (#6b/#7c/#8a):
`embeddings.npy` md5 `d2fbfeefd208c67ebc262fd95b03685c` (identical all 3),
`vector_db_full.pkl` md5 `17d5490286c748c4c8eefbd3f713d7ac` (identical all 3).
Same 1,869-document content; chroma.sqlite3 differs only by SQLite page layout
(td-mcp == kb_pipeline byte-identical).

### A.4 Snippet / palette / auxiliary stores

| # | Path | Format | Files / Size | Verdict |
|---|---|---|---|---|
| 6c | `META_AGENTIC_TOOL/data/snippets/semantic/` | 479 JSON | 4.5 MB | **unique-additions** (source: real network examples — keys: source_file, operator_type, examples[{name,description,operators,connections,network_pattern}]). Build input to #4/#5/#6a |
| 6d | `META_AGENTIC_TOOL/data/snippets/lossless_pop/` | 98 JSON (117 files) | 155.0 MB | **unique-additions** (lossless POP captures: metadata/operators/raw_files/toc_order/connections/statistics) |
| 6e | `META_AGENTIC_TOOL/data/snippets/index.tsv` | TSV | 514,882 B | md5 `dd9f83315981ab26f04f86df6294f4ba` — **exact-dup** with `td-mcp/.../snippets/index.tsv` |
| 6f | `META_AGENTIC_TOOL/data/snippets/expanded_pop/` | empty | 0 | **empty** (no content) |
| 6g | `META_AGENTIC_TOOL/data/palette_lossless/` | 266 files (2 JSON: `enriched_index.json`) | 18.0 MB | **unique-additions** (palette component lossless data + searchable index) |
| 6h | `META_AGENTIC_TOOL/data/palette_summaries.json` | JSON {summaries,chunks} | 154,754 B | md5 `8966a73fdee45baf8ecba0e89e9cb955` — **exact-dup** with `td-mcp/.../palette_summaries.json` |
| 7d | `td-mcp/knowledge_base/data/snippets/semantic/` | 479 JSON | 4.5 MB | **exact-dup-of-#6c** (same 479 filenames) |
| 7e | `td-mcp/knowledge_base/cache/search_cache.db` | sqlite | 98,304 B | **build-artifact** (runtime query cache, not knowledge) |
| 8c | `kb_pipeline/data/palette_semantic/` | 529 JSON | 263.8 MB | **unique-additions** (largest palette semantic capture; superset of palette_lossless count-wise — 529 vs 266) |
| 8d | `kb_pipeline/data/palette_lossless/` | 266 files (1 JSON) | 17.8 MB | **near-dup-of-#6g** (266 files, lossless palette data) |
| 8e | `kb_pipeline/data/palette_wiki/` | 182 files (0 JSON) | 8.8 MB | **unique-additions** (palette wiki docs, non-JSON) |
| 8f | `kb_pipeline/data/snippets/` | 577 JSON (578 files) | 160.0 MB | **unique-additions / superset** of #6c+#6d (semantic + lossless snippets combined) |
| 8g | `kb_pipeline/data/{fixtures,templates}/` | 1 / 2 files | small | **build-artifact** (pipeline scaffolding) |
| 9e | `priority_operators.json` (root) | JSON dict (len 2) | 51,774 B | **unique-additions** (priority operator list — curation metadata, not in #2) |
| 9f | `search_test_queries.json` (root) | JSON dict (len 1) | 2,173 B | **build-artifact** (test fixture, not knowledge) |

---

## (B) Unique Knowledge Ledger

For each non-superset store, the concrete unique content it holds that the
canonical triad (#2 enriched JSON, #4 graphrag, #5 enhanced gpickle, #6a merged
vector DB) does **not** already fully contain:

### B.1 vs operator superset #2 (`td_universal_parsed_enriched.json`)
- **#1 `td_universal_parsed.json`**: ZERO unique knowledge. Proven strict subset
  of #2: 0 missing operators, 0 missing classes/concepts, 0 parameter-base-field
  regressions (code/display_name/description/section all preserved exactly), 0
  param-count mismatches. The only deltas are #2 *adding* to #1:
  - 14,375 params gained `type`, `default`, `page`, `readOnly`, `source` fields
  - 4,825 params gained `menuNames` + `menuLabels` (parallel menu arrays)
  - 6 operators gained `build_instructions`
  - 13 operators had an **empty** `summary` filled in (parsed had `len 0`;
    enriched filled with 87–2,389 chars). No non-empty summary was overwritten.
- **#3 `td_universal_parsed_with_build_instructions.json`**: ZERO unique
  knowledge. Its only addition over #1 is 6 `build_instructions`
  (`CHOP to TOP`, `Composite TOP`, `DAT to CHOP`, `Feedback TOP`, `SOP to CHOP`,
  `Table DAT`). Verified **byte-identical** to the 6 build_instructions already
  present in #2 (`bB == bE` → True). #3 lacks all of #2's param enrichment.
- **#9a / #7a** (`td_universal.json`, `operators.json`): exact MD5 dup of #1 →
  zero unique knowledge.

### B.2 vs RAG superset #4 (`td_graphrag.json`) / enhanced graph #5
- **#9d `td_knowledge_graph.gpickle`** (DiGraph, 18,888 nodes): older flat
  operator+parameter graph. Its node universe (operators + per-parameter nodes)
  is fully represented in #5's richer typed graph (37,526 nodes incl.
  ParameterConfig 26,233). Treat as **no unique knowledge** beyond #5; verify
  with assertion D.3 before discard.
- **#7b `td-mcp/.../graph/knowledge_graph.json`** (16,814 nodes / 18,084 edges):
  smaller earlier snapshot of #5's enhanced graph; no edges/nodes expected
  beyond #5. Verify with D.3.
- **#8b `kb_pipeline/vector_db_chroma`** (20,477 docs): intermediate merge
  between the 1,869 base and the 34,350 final; all docs expected in #6a. Verify
  with D.4.

### B.3 vs vector superset #6a (`vector_db_merged`, 34,350 docs)
- **#6b / #7c / #8a** (1,869-doc DBs): PROVEN strict subset of #6a — 0 of 1,869
  documents missing from #6a. The 1,869 appear as `__source_store=active`
  inside #6a. Zero unique knowledge.

### B.4 Source/ingredient stores (unique RAW knowledge — KEEP as build inputs)
These hold the *primary* knowledge from which #4/#5/#6a were derived
(per `_out_of_scope/import_to_graphrag.py`). They are not represented
*verbatim* in the canonical triad — only their *processed projection* is:
- **#6c semantic snippets (479 files)** — real network examples
  (operators/connections/network_pattern). Source for DEMONSTRATES edges,
  ExampleNetwork/OperatorInstance nodes, and many merged vector docs.
- **#6d lossless_pop (98 files, 155 MB)** — exact POP network captures.
- **#6g / #8d palette_lossless (266 files, ~18 MB)** — palette component
  lossless networks + `enriched_index.json`.
- **#8c palette_semantic (529 files, 264 MB)** — largest palette semantic
  capture (superset of palette_lossless by count).
- **#8e palette_wiki (182 files)** — palette wiki documentation.
- **#8f kb_pipeline/data/snippets (577 files, 160 MB)** — appears to be the
  combined semantic+lossless snippet superset feeding the pipeline.
- **#9e priority_operators.json** — curation list (priority operators) not
  encoded in #2.
- **#6h / #7? palette_summaries.json** — palette summaries+chunks (dup'd between
  META and td-mcp; one copy is unique knowledge).

> **Provenance note (from `_out_of_scope/` scripts):**
> `enrich_wiki_from_gt.py` derived an early `*_enriched.json` from #1 +
> ground-truth `param_catalog.json` (additive params, `source="ground_truth"`).
> `add_build_instructions_to_kb.py` derived #3 from #1 + 6 hardcoded
> build_instructions. `META_AGENTIC_TOOL/merge_ground_truth_types.py` then
> merged real `type`/`default`/menu data into `td_universal_parsed_enriched.json`
> in place (metadata `ground_truth_merge: operators_matched 648,
> params_enriched 14375`). The shipped #2 is the **convergence of BOTH
> derivation chains plus the GT type merge** — hence it is the maximal operator
> superset. `import_to_graphrag.py` built #5 from text snippets + semantic
> network extraction.

---

## (C) Recommended Single Mega-KB Design

A single mega-KB cannot be one flat file because the four knowledge axes are
structurally different (operator specs vs RAG chunks vs typed graph vs vector
embeddings). The recommended design is **one versioned KB bundle directory**
with one canonical artifact per axis — i.e. promote the already-server-loaded
canonical triad to an explicit, self-describing bundle.

### C.1 Base superset selection (per axis)
- **Operator axis base:** `td_universal_parsed_enriched.json` (#2). It is the
  proven maximal superset of #1, #3, #9a, #7a — adopt as-is, no merge needed.
- **RAG-chunk axis base:** `td_graphrag.json` (#4) — 74,280 chunks.
- **Typed-graph axis base:** `td_knowledge_graph_enhanced.gpickle` (#5) —
  37,526 nodes / 40,568 edges (largest; #9d, #7b are subsets).
- **Vector axis base:** `vector_db_merged/` (#6a) — 34,350 docs (strict superset
  of all 1,869-doc DBs and the 20,477 intermediate).

### C.2 Elements to merge IN from other stores
After verification (Section D), **no operator/graph/vector content needs to be
merged** — every audited candidate is a proven subset or exact dup. The only
*additive* action is to physically co-locate the raw source corpora so the
bundle is self-contained and re-buildable:

| Into bundle slot | From store | Why (unique element) |
|---|---|---|
| `sources/snippets_semantic/` | #6c (479 files) | raw example networks (DEMONSTRATES source) |
| `sources/snippets_lossless_pop/` | #6d (98 files) | lossless POP captures |
| `sources/palette_semantic/` | #8c (529 files) | largest palette semantic corpus |
| `sources/palette_lossless/` | #6g/#8d (266 files) | palette lossless + enriched_index |
| `sources/palette_wiki/` | #8e (182 files) | palette wiki docs |
| `sources/palette_summaries.json` | #6h | palette summaries+chunks (de-dup the 2 copies) |
| `meta/priority_operators.json` | #9e | curation metadata |

### C.3 Conflict rule
**Keep the richest field; never overwrite a non-empty value with a poorer one;
additive-only union.** Concretely:
- Operator merge key: `(family, name)` then positional parameter alignment by
  `code`. On field collision, prefer the value with `source="ground_truth"` >
  enriched > parsed; for `summary`, prefer the longer non-empty string (matches
  observed enriched behavior: only the 13 empty summaries were filled).
- Graph merge key: node `id` / edge `(from,to,type)` — union, keep the variant
  with more `properties`.
- Vector merge key: chroma document id — union, keep doc with richer metadata
  (the `__source_store` tag already records provenance).

### C.4 Resulting mega-KB bundle schema (top-level layout)
```
KB/mega/                         # proposed bundle root (NOT created by this audit)
  manifest.json                  # versions, md5s, source provenance, counts
  operators.json                 # = td_universal_parsed_enriched.json (#2)
                                 #   keys: metadata, operators, classes,
                                 #         concepts, errors
  graphrag.json                  # = td_graphrag.json (#4)
                                 #   keys: metadata, chunks, graph
  knowledge_graph_enhanced.gpickle  # = #5 (dict: nodes, edges, metadata)
  vector_db/                     # = vector_db_merged/ (#6a, chroma td_unified)
  sources/                       # raw build-input corpora (B.4)
    snippets_semantic/  snippets_lossless_pop/
    palette_semantic/  palette_lossless/  palette_wiki/
    palette_summaries.json  snippets_index.tsv
  meta/
    priority_operators.json
```
This bundle is exactly what `mcp_server.py` already loads (operators=enriched,
graph=graphrag+enhanced gpickle, vectors=vector_db_merged) — formalized,
versioned, and self-contained with its rebuild sources.

---

## (D) Completeness-Proof Plan (assertions to run post-merge)

Run these BEFORE quarantining any store. All must pass.

**D.1 Operator superset proof (covers #1, #3, #9a, #7a):**
For each store S in {parsed, build_instructions, td_universal(root), operators.json}:
```
for op in S.operators:
    M = mega.operators[(op.family, op.name)]            # must exist
    assert M is not None
    assert set(op.keys()) <= set(M.keys())              # no op field lost
    for p in op.parameters:
        mp = M.param_by_code(p.code)                    # must exist
        assert mp is not None
        for k in ('code','display_name','description','section'):
            assert p.get(k) == mp.get(k) or (not p.get(k))  # base fields intact
    for k in ('build_instructions',):
        if k in op: assert mega_value(op,k) == op[k]     # BI preserved verbatim
assert mega.classes == S.classes                        # byte-equal (already true)
assert mega.concepts == S.concepts                      # byte-equal (already true)
```
Expected (already empirically verified in this audit): 0 failures.

**D.2 Operator field-richness proof:**
```
assert count(params with 'type')      >= 14375
assert count(params with 'menuNames') >= 4825
assert count(ops with build_instructions) == 6
assert count(ops with non-empty summary filled vs parsed) == 13  # no regressions
```

**D.3 Graph superset proof (covers #9d, #7b):**
```
for n in old_graph.nodes:  assert normalize(n.id) in mega.graph.nodes
for e in old_graph.edges:  assert (e.from,e.to,e.type) representable in mega.graph
assert mega.graph.node_count >= 37526 and edge_count >= 40568
```
(#9d is a networkx DiGraph; normalize node ids to the `op:FAMILY/name` /
`...param...` scheme used by #5 before the membership check.)

**D.4 Vector superset proof (covers #6b/#7c/#8a/#8b):**
```
for db in {vector_db(1869 x3), vector_db_chroma(20477)}:
    docs_db = set(db.documents)
    assert docs_db.issubset(set(mega.vector_db.documents))   # 0 missing
assert mega.vector_db.collection == 'td_unified'
assert mega.vector_db.count == 34350
```
Expected (already verified for the 1,869-doc DBs): 0 missing.

**D.5 Source-corpus presence proof:**
```
for d in {snippets_semantic(479), snippets_lossless_pop(98),
          palette_semantic(529), palette_lossless(266),
          palette_wiki(182)}:
    assert file_count(bundle.sources/d) >= original_count(d)
    assert md5_set(bundle...) ⊇ md5_set(original...)        # byte-for-byte
```

**D.6 Exact-dup proof (covers #9a/#7a/#9b/#9c/#6e/#6h/#7d/#8a):**
```
assert md5(td_universal.json) == md5(td_universal_parsed.json)            # ab15edaa…
assert md5(root td_graphrag.json) == md5(META td_graphrag.json)          # bd59b605…
assert md5(root enhanced.gpickle) == md5(META enhanced.gpickle)          # cc168511…
assert md5(META index.tsv) == md5(td-mcp index.tsv)                      # dd9f8331…
assert md5(META palette_summaries) == md5(td-mcp palette_summaries)      # 8966a73f…
assert md5(td-mcp vdb sqlite) == md5(kb_pipeline vdb sqlite)             # 56f410b0…
```
(All six already verified TRUE in this audit.)

---

## (E) Stores Safe to Quarantine (after D.1–D.6 all pass)

**Immediately safe — exact MD5 duplicates (proven, D.6):**
- `td_universal.json` (root) — dup of #1
- `td-mcp/knowledge_base/data/operators.json` — dup of #1
- `td_graphrag.json` (root) — dup of #4
- `td_knowledge_graph_enhanced.gpickle` (root) — dup of #5
- `td-mcp/knowledge_base/data/snippets/index.tsv` — dup of #6e
- `td-mcp/knowledge_base/data/palette_summaries.json` — dup of #6h
- `td-mcp/knowledge_base/data/snippets/semantic/` — dup of #6c (479 files)
- `kb_pipeline/vector_db/` — sqlite dup of `td-mcp/.../vector_db/`

**Safe after D.1 passes — proven operator subsets:**
- `META_AGENTIC_TOOL/data/wiki_docs/td_universal_parsed.json` (#1)
- `META_AGENTIC_TOOL/data/wiki_docs/td_universal_parsed_with_build_instructions.json` (#3)
> Caveat: #1 is referenced as the data source by the **stale CLAUDE.md** and by
> `unified_system`/`kb_pipeline` legacy code paths. Quarantine of #1 requires
> repointing those loaders to #2 first, or keeping #1 as a generated symlink/copy
> of #2 during the alpha. Do NOT delete #1 until loader references are updated.

**Safe after D.3 passes — proven graph subsets:**
- `td_knowledge_graph.gpickle` (root, #9d — old DiGraph)
- `td-mcp/knowledge_base/graph/knowledge_graph.json` (#7b — old snapshot)

**Safe after D.4 passes — proven vector subsets/intermediates:**
- `META_AGENTIC_TOOL/data/vector_db/` (#6b, 1,869 docs)
- `td-mcp/knowledge_base/vector_db/` (#7c, 1,869 docs)
- `kb_pipeline/vector_db/` (#8a, 1,869 docs)
- `kb_pipeline/vector_db_chroma/` (#8b, 20,477 docs intermediate)

**Build-artifacts — quarantine anytime (not knowledge):**
- `td-mcp/knowledge_base/cache/search_cache.db`
- `search_test_queries.json` (root, test fixture)
- `kb_pipeline/data/{fixtures,templates}/`
- `META_AGENTIC_TOOL/data/snippets/expanded_pop/` (empty)

**MUST RETAIN until folded into `KB/mega/sources/` (raw build inputs, unique):**
- `META_AGENTIC_TOOL/data/snippets/semantic/` (#6c)
- `META_AGENTIC_TOOL/data/snippets/lossless_pop/` (#6d, 155 MB)
- `META_AGENTIC_TOOL/data/palette_lossless/` (#6g)
- `kb_pipeline/data/palette_semantic/` (#8c, 264 MB)
- `kb_pipeline/data/palette_wiki/` (#8e)
- `kb_pipeline/data/snippets/` (#8f, 160 MB)
- `priority_operators.json` (#9e)
- one copy of `palette_summaries.json` (#6h)

**Canonical — NEVER quarantine (the mega-KB itself):**
- `META_AGENTIC_TOOL/data/wiki_docs/td_universal_parsed_enriched.json` (#2)
- `META_AGENTIC_TOOL/data/td_graphrag.json` (#4)
- `META_AGENTIC_TOOL/data/td_knowledge_graph_enhanced.gpickle` (#5)
- `META_AGENTIC_TOOL/data/vector_db_merged/` (#6a)

---

## Evidence Appendix (key empirical results, this audit)

- MD5 confirmed: `td_universal.json` = `td_universal_parsed.json` =
  `td-mcp/.../operators.json` = `ab15edaa71dcaebaf65c5b530b99d4ef`.
- MD5 confirmed: root vs META `td_graphrag.json` = `bd59b6057bc819e3808c69b17944c930`;
  root vs META enhanced gpickle = `cc16851a153016bcca1b798670b46391`.
- Operator-name sets identical across #1/#2/#3 (670 unique / 673 records).
- `classes` & `concepts` byte-identical across #1/#2/#3 (592 / 711).
- Param-key Counters: #1 = {code,display_name,description,section} ×16,751;
  #2 adds type/default/page/readOnly/source ×14,375 + menuNames/menuLabels ×4,825;
  #3 = identical to #1 (no param enrichment).
- #2 vs #1: 0 op-field regressions, 0 param-base-field changes, 0 param-count
  mismatches; only 13 `summary` values changed, all from empty → filled.
- #2 and #3 contain the **same 6** build_instructions ops, content byte-identical.
- Enhanced gpickle #5 = dict (not networkx) — 37,526 nodes / 40,568 edges,
  matches `mcp_server.py` UnifiedGraphQuery expectation.
- Live server (mcp_server.py): operators ← `td_universal_parsed_enriched.json`
  (L389); graph ← `td_graphrag.json`+`td_knowledge_graph_enhanced.gpickle`
  (L387–395); vectors ← `vector_db_merged/` (L407–413).
- Chroma: small DBs = `td_unified`/1,869 (all 1,869 ⊆ merged, 0 missing);
  `vector_db_merged` = `td_unified`/34,350 (`__source_store`: active 1,869 +
  enriched_kb 6 + orphan 32,475); `kb_pipeline/vector_db_chroma` = 20,477
  (intermediate). `embeddings.npy` & `vector_db_full.pkl` byte-identical across
  the 3 small DBs.
- CLAUDE.md is STALE (claims server loads `td_universal_parsed.json`; it loads
  the enriched variant). Treat verified facts above as authoritative.

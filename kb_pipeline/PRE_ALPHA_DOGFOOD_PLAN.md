# Pre-Alpha Dogfood Plan (2 weeks)

## Decisions locked
- Runtime is standardized on **Python 3.11** via `C:\TD_Projects\kb_pipeline\.venv_py311`.
- Endgame build output is **JSON → expanded dir/toc → toe/tox** (via `toecollapse.exe`) once the builder/parsers are 100%.
- Until the JSON builder is 100%, default “build a network” output can still be `build_python` for fast iteration.

## Pre-alpha scope
### Must work daily
1) **Retrieval + grounding**
   - One tool entrypoint: `td_assistant action=query`
   - Results must come from `docs|snippets|palette`, with provenance in metadata.
2) **Explain using evidence**
   - For any claim about parameters/behavior: at least one supporting docs/snippet chunk.
3) **Build path (feature-flagged)**
   - Phase A (now): `build_python` produces runnable Text DAT scripts.
   - Phase B (target for end of dogfood): JSON builder produces `.toe/.tox` via expand/collapse round-trip.

## What “100% JSON builder” means (acceptance)
- Given a valid Builder JSON input:
  - Expanded output is deterministic (byte-stable unless timestamps are required).
  - `toecollapse.exe` succeeds.
  - The resulting `.toe/.tox` loads in TouchDesigner.
  - `toeexpand.exe` on the result succeeds.
  - Structural checks pass (expected ops exist, wires exist, key pars exist).

## Workstreams
### A) Runtime standardization (done)
- MCP server config uses: `C:\TD_Projects\kb_pipeline\.venv_py311\Scripts\python.exe`
- Script runner: `C:\TD_Projects\kb_pipeline\scripts\kb311.ps1`

### B) Canonical fixtures (done)
- Empty canonical templates are snapshotted in:
  - `C:\TD_Projects\kb_pipeline\data\templates\empty_templates`
  - `C:\TD_Projects\kb_pipeline\data\templates\empty_templates.zip`
- Expanded test zips are snapshotted in:
  - `C:\TD_Projects\kb_pipeline\data\fixtures\zips`

### C) Dogfood prompt suite
Create a single file you actually use every day:
- `pre_alpha_prompts.md` with ~30 prompts in 5 buckets:
  - parameter lookups
  - “how-to”
  - “show me a real snippet example” + explain the network
  - palette component discovery + usage
  - build requests (initially python; later json→toe/tox)

### D) Logging + triage loop
Log each dogfood run as one row:
- prompt
- result (0/1 useful)
- failure type: `data|retrieval|reasoning|builder|tooling`
- quick note + link to relevant artifact (chunk id, file path)

Weekly rule: only ship fixes that reduce failures in your suite.

## Week-by-week cadence
### Week 1: Retrieval quality + noise control
- Fix ranking issues by adjusting chunk text (especially snippet noise).
- Ensure `docs` tier chunks cover parameter lookups cleanly.
- Lock in evidence-pack format.

### Week 2: JSON builder push
- Focus on deterministic expanded outputs.
- Grow fixture coverage (more palette/snippet toxs).
- Add regression tests: expand → parse lossless → rebuild → collapse → expand.
- Gate “always output toe/tox” on passing regression + real TD load checks.

## Daily routine (10–20 min)
1) Run 5 prompts from the suite
2) File failures immediately into the triage log
3) Fix 1–3 highest-impact issues
4) Re-run the failed prompts

## Practical commands (Py311)
- Build vector text index: `powershell -File C:\TD_Projects\kb_pipeline\scripts\kb311.ps1 build-vectors`
- Build embeddings: `powershell -File C:\TD_Projects\kb_pipeline\scripts\kb311.ps1 embed`
- Build merged graph/index: `powershell -File C:\TD_Projects\kb_pipeline\scripts\kb311.ps1 build-graph`
- Build Chroma (optional): `powershell -File C:\TD_Projects\kb_pipeline\scripts\kb311.ps1 build-chroma`
- Run MCP server: `powershell -File C:\TD_Projects\kb_pipeline\scripts\kb311.ps1 serve`


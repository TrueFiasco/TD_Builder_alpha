# Meta-Agentic Interop + Output Policy + Eval Gates

## 1) Claude/OpenAI Interoperability (YAML <-> JSONL)
- Sources of truth stay the same: `kb_pipeline/data/wiki_docs/td_universal_parsed.json`, `kb_pipeline/data/snippets/`, curator index TSV. Expertise is working memory only.
- Event log (append-only, JSONL): `meta_agentic/history/expertise_events.jsonl`
  - Required fields: `id`, `ts`, `agent_id`, `domain`, `inputs`, `outputs`, `evidence` (pointers with hash + td_version), `metrics`, `status`, `notes`, `schema_version`.
  - Atomic writes with `concurrency/file_lock.py` on the log file.
- Materialized state (YAML, shared): `meta_agentic/meta/expertise_state.yaml`
  - Built by periodic compaction of the event log (idempotent script).
  - Keep `schema_version`, `last_compacted`, `checksum`, and per-domain sections (recipes, patterns, params, problems).
- Legacy YAML expertise (Claude): `meta_agentic/expertise/*.yaml`
  - Treat as working-set views. When updating, also append an event to JSONL. Compaction can refresh these YAMLs from `expertise_state.yaml` to keep all agents aligned.
- Validation before writes: every event/state update must include evidence pointers (`source_path`, `chunk_id`, `excerpt_hash`, `td_version`) and pass schema validation. Reject if evidence count <3 for pattern claims.

## 2) Planner/Builder Output Policy (toe -> tox -> Text DAT -> instructions)
- Default order of deliverables: .toe (project) -> .tox (component) -> Text DAT Python script -> human instructions.
- Planner must emit `target_mode` hint (`toe` | `tox` | `text_dat` | `instructions`) and TD version tag; builder honors this and falls back in order if validation/build fails.
- Validation gate: run `unified_system/validation/pipeline.py` before any build; only proceed to .toe/.tox when PASS.
- TD version tagging: include `td_version` and `python_version` in planner output meta; builder logs these into event log entries for reproducibility.

## 3) Evaluation Gate Rules (recipes/patterns/specs)
- Accept new recipe/pattern/spec only if:
  - Evidence >=3 distinct pointers with hashes + matching TD version (or marked forward-compatible).
  - Validation PASS on generated builder JSON via `ValidationPipeline`.
  - Build attempt for .toe/.tox succeeds OR recorded fallback reason; if fallback to Text DAT, note reason in event.
  - Confidence score recorded (0.0-1.0) and linked problem IDs if covering a regression fix.
- On failure: log to `meta_agentic/expertise/td_problems.yaml` with root cause, not just symptom.
- All accepted updates append an event and update `expertise_state.yaml`; YAML working files refreshed via compaction, not direct ad-hoc edits.

# Pre-Alpha Triage Loop (how we keep it clean)

## Files
- Prompt suite: `C:\TD_Projects\kb_pipeline\pre_alpha_prompts.md`
- Log: `C:\TD_Projects\kb_pipeline\pre_alpha_triage_log.csv`

## Workflow (daily)
1) Pick 5 prompts from the suite (rotate so you cover all buckets weekly).
2) Run them through the assistant.
3) Immediately log each run:
   - `result_useful_0_1`: 1 if you’d actually use the answer/build output as-is.
   - `failure_type`:
     - `data`: missing/incorrect KB content, bad summaries, wrong provenance
     - `retrieval`: wrong ranking, needs better filtering, wrong source picked
     - `reasoning`: tool used correctly but explanation/design is wrong
     - `builder`: python/json build fails or output doesn’t match intent
     - `tooling`: MCP server/runtime issues (crash, encoding, config)
   - `data_ids_or_files`: chunk ids, semantic file paths, toe/toc paths, stderr logs
4) Fix only the top 1–3 issues that would make the biggest dent in repeated failures.
5) Re-run the failing prompt(s) and mark the fix in the same row (append to `notes`).

## Weekly review (30 minutes)
- Sort the log by `failure_type`, then by frequency.
- Only promote “default build output = toe/tox” if:
  - `builder` failures are effectively 0 in the last 7 days, and
  - builder regression tests pass on the fixture set.


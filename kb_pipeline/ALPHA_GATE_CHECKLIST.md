# Alpha Gate Checklist

## Packaging / Runtime
- MCP server runs from Py311 venv: `C:\TD_Projects\kb_pipeline\.venv_py311`.
- Claude Desktop config points to venv python: `C:\TD_Projects\kb_pipeline\mcp\claude_desktop_config_kb_pipeline.json`.
- No external hard-coded paths are required at runtime beyond TD install path.

## Retrieval quality (dogfood-proven)
- Top 30 prompts in `C:\TD_Projects\kb_pipeline\pre_alpha_prompts.md` score ≥80% useful (your 0/1).
- Parameter lookups are grounded in docs chunks (not hallucinated).
- Snippet answers reference curator summaries when available (index.tsv).
- Palette answers include wiki summary grounding.

## Builder readiness (when switching default to toe/tox)
- JSON→expanded dir/toc→toecollapse passes on the fixture set.
- toeexpand of the collapsed output succeeds.
- Output loads in TouchDesigner with no errors.
- Clear failure mode: if builder fails, you still get the expanded output + `.toc` + logs.

## Observability
- Every run can be triaged from `C:\TD_Projects\kb_pipeline\pre_alpha_triage_log.csv` with chunk ids / file paths.


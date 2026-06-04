# Compaction Runner

Use the compaction utilities to materialize expertise state and refresh legacy YAML views.

## Manual Run
```bash
cd C:\TD_Projects\META_AGENTIC_TOOL\meta_agentic\compaction
python run_compaction.py          # compact + refresh
python run_compaction.py --no-refresh  # compact only
```

Optional overrides:
```bash
python run_compaction.py --events ..\history\expertise_events.jsonl --state ..\meta\expertise_state.yaml
```

## Windows Task Scheduler (example)
Create a basic task to run daily:
- Action: `python C:\TD_Projects\META_AGENTIC_TOOL\meta_agentic\compaction\run_compaction.py`
- Start in: `C:\TD_Projects\META_AGENTIC_TOOL\meta_agentic\compaction`
- Trigger: daily (or hourly if high churn)

## Notes
- Uses append-only JSONL -> YAML per `INTEROP_AND_POLICY.md`
- Refreshes `meta_agentic/expertise/*.yaml` to keep Claude/OpenAI views in sync
- Safe to run repeatedly (idempotent)

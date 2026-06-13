# tests/ — acceptance + smoke gate

A small, fast gate to confirm a working install. This is **not** a benchmark suite (the
quality-measurement harness lives in the dev repo, not the release).

## Run it
```powershell
py -3.11 -m pytest tests\acceptance tests\measure -q     # ~21 checks
```

- **Offline checks** (server identity, tool inventory, KB search, `td_validate`/`td_convert`/
  `td_build_project`, `get_expert_prompt`) run against the **`td-builder`** server (15 tools).
- **Live checks** (identity / topology / capture / diagnostics / CRUD) run against the
  **`td-builder-live`** server (19 tools) and need TouchDesigner open (WebServer DAT on `:9981`).
  With TD down they still pass via the graceful "not running" path.
- The first KB-dependent test warms the knowledge base (~1–2 min, one-time).

## Layout
| File | Role |
|---|---|
| `acceptance/test_acceptance.py` | The main probes P01–P19 (offline + live). |
| `measure/test_smoke.py` | Server-loads + tool-inventory + 5-stage validate smoke. |
| `measure/_server.py`, `measure/probe.py` | In-process loaders for the two servers + the probe used by `conftest.py`. |
| `conftest.py` | `probe` (offline) + `live_probe` (live) fixtures; warms the KB before KB tests. |

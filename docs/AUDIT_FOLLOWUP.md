# Audit follow-up — report-only items

> Findings + recommendations only — **no code was changed for anything in this file.** These are the
> deferred / report-only items from the v0.1.1 post-release audit, recorded during the Round-1
> safe-hardening pass (see git log `Fix #…` / `Cleanup #…`). Each needs an owner decision before action.

---

## #11 — Offline server "could merge the 19 live tools" → **non-issue (verified)**

**Concern (audit):** `mcp_server.py` ends `list_tools` with
`if TD_LIVE_ENABLED and TD_LIVE_TOOLS: tools.extend(TD_LIVE_TOOLS)`, supposedly undercutting the clean
"16 offline / 19 live" split.

**What's actually true.** The offline entry point `MCP/server.py` calls `bootstrap.setup()`, which puts
only the repo root, `MCP/engine`, and `MCP/server_core` on `sys.path` — **not** `MCP/live_client`. So the
guarded import `from td_live_client import TD_LIVE_TOOLS, …` (mcp_server.py, ~line 62) raises `ImportError`,
`TD_LIVE_ENABLED` is set `False`, and the `tools.extend(...)` line is never reached. A normal offline
launch advertises **16 tools**, not 35. The live tools are served only by `MCP/live_server.py`
(`td-builder-live`), which explicitly adds `live_client` to `sys.path`.

**Recommendation (optional, defense-in-depth):** either have the offline entry point force live-off
explicitly, or just document the merged-mode condition. No leak exists in the shipped configuration.

---

## #12 — `td_convert`/`td_validate` mislabel the "extended" format → **real**

**Format layers** (`MCP/engine/core/models.py`): **Builder** (AI-friendly, simple paths) → **Extended**
("ground truth, complete data" — the in-memory `TDNetwork` after `from_builder()` fills in defaults /
resolved paths) → **Canonical** (string-table compressed) → **Lossless** (perfect round-trip incl. raw
files).

**The bug.** "Extended" exists only in memory; there is **no real `to_extended()` serializer**:
- `MCP/engine/cli/td_convert.py` (~line 137) calls a non-existent `converter.to_extended()` → would
  `AttributeError` at runtime.
- `mcp_server.py` (~line 1755) stamps `result_json["format_layer"] = "extended"` onto `to_builder()`
  output — a label, not a real serialization.
- `td_validate.py` (~line 111) + `mcp_server.py` (~line 1689) route `extended` *input* through
  `from_builder()` with a `# TODO: Implement proper Extended JSON deserialization`.

**What `to_extended()` should do:** serialize the full `TDNetwork` graph (all fields, no string-table
compression, no raw file blobs). A near-equivalent already ships — **Lossless** (`to_lossless_json_dict`)
for full fidelity, or **Builder** (`to_builder`, re-enrichable via `from_builder`).

**Recommendation (owner decision):** either (a) implement a genuine `to_extended()` / `from_extended()`
pair, or (b) **reject `extended` with a clear "not supported — use builder or lossless" error** instead of
silently mislabeling. Option (b) is the smaller, honest fix.

---

## #6 — Expertise YAMLs: inventory + prune decision → **defer all pruning to the wiring round**

`Agents/expertise/` holds **19 YAMLs (~677 KB)**. The Round-1 audit prune was **reversed** after
investigation (only the `Agents/README.md` overstatement was fixed — no files deleted). Why:

1. **No Python reads `expertise_inputs:`.** The expert `config.yaml` files declare `expertise_inputs:`
   lists, but a repo-wide grep finds **zero** code that reads that key. The only YAML actually loaded at
   runtime is **`td_network_building.yaml`** (by `meta_agentic/execution/toe_builder_bridge.py`'s
   `load_conversion_op_expertise()`). So "referenced in a config" is **no more live** than
   "zero-reference" — both are unwired. The earlier "td_operators.yaml is referenced, trimmed isn't"
   distinction is therefore not a safety signal.

2. **The "unreferenced" YAMLs are curated knowledge, not cruft:**
   - `td_operators_v2.yaml` (35 KB) — unique **data-conversion guide** (`datto_chop`, `chopto_top`, …),
     cross-referenced 5× in `td_problems.yaml`'s prevention blocks.
   - `td_file_formats.yaml` (25 KB) — `.text` format / select-CHOP / noise-centering specs, cited in
     problem-prevention blocks.
   - `collaborative_workflow.yaml`, `orchestrator_patterns.yaml`, `prebuilt_solution_expert.yaml` — the
     design blueprint for the deferred **#6 expert wiring**.
   - `td_operators_trimmed.yaml` (4.9 KB, zero refs) — a hand-curated ~20-operator quick-reference subset
     that a future "quick mode" could use.

**Recommendation:** make the prune decision **as part of the #6 wiring design**, not before — the value of
each YAML depends on how wiring consumes them. The single defensible "if forced" deletion is
`td_operators_trimmed.yaml`; everything else should wait. Also: nothing reads `expertise_inputs:` — decide
whether to wire it or drop it during the wiring work.

---

## #14 — Propose-only housekeeping (decisions, not auto-fixes)

- **Dead `MCP/engine/writers/lossless_writer.py` (688 LOC).** Verified zero external importers
  (`LosslessWriter` is referenced only inside its own file + `__main__` demo). Duplicates
  `toe_builder.py::TOEBuilder._build_lossless`. → **Decide: delete vs wire.**
- **Redundant import-time `sys.path.insert(...)`** in ~8–10 engine modules (e.g.
  `MCP/engine/builders/toe_builder.py:14`, `api/network_builder.py:9`). `bootstrap.setup()` already covers
  the repo root / `MCP/engine` / `MCP/server_core`. **Deferred from Round 1** because several of these
  modules also run **standalone** (the self-insert is load-bearing then), and removing them safely needs
  the full import gate (which requires the KB). → **Decide per-module: keep / convert to `bootstrap.setup()`.**
- **Folder name with spaces** `Tools/offline Builder tools/` → propose rename to
  `Tools/offline_builder_tools/` (launcher shims don't depend on the name, but `README.md` / `Tools/TOOLS.md`
  reference the path — update those refs).
- **Duplicate `search_config.json`.** Code loads `MCP/server_core/config/search_config.json`
  (`MCP/server_core/config/__init__.py:18`). The `Config/search_config.json` copy is the **unused
  duplicate** → keep the server_core copy, remove/redirect the `Config/` one (confirm identical first).
- **Duplicate `.env.template`** (`./.env.template` vs `Config/.env.template`) → determine which the setup
  docs point at, keep one, redirect the other.
- **Process-wide `sys.stdout = sys.stderr` swaps** (`mcp_server.py:~39-40, ~320-321, ~406`) — a workaround
  for leftover `print()`s in the search modules. → Convert those prints to `logging`/stderr and remove the
  swaps.
- **`self_improve` still offered as a `get_expert_prompt` phase** though unwired, and its prompts import a
  removed `compaction` module. → Remove the phase or fix the prompts.
- **`docs/TOE_FORMAT_LEARNINGS.md`** documents a builder + generated files that no longer exist (and an
  operator count — 685 — for a build-pipeline artifact, left untouched in the #8 reconciliation). →
  Rewrite or archive.

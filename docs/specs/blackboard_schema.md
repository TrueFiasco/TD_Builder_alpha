# Blackboard schema — §1-§7 project-document state (design harvest)

**Status: design input, not implemented.** Harvested 2026-07-04 (harness remediation W2a)
from the never-wired workflow-orchestration reference implementation, now preserved at
`quarantine/meta_agentic_orchestration/` (see `quarantine/README.md`). No shipped tool path
reads or writes a blackboard. This document records the *schema and intent* so the parked
D6 proposal (cowork phase-loops + blackboard-as-file) can design against it without
resurrecting the code.

Companion: [metrics_shapes.md](metrics_shapes.md) (D4 feedback-spine input).

## Core idea

One central **project document** ("blackboard") is the single source of truth for a
multi-phase build workflow. Every participant — human or expert prompt — reads from and
writes to *named sections* of that document, never to each other directly. State lives in
the document; the orchestration layer stays stateless and merely decides the next action
from what the document says.

## The seven sections

| ID token | Section | Content intent |
|---|---|---|
| `§1_requirements` | Requirements | User intent + constraints (the original prompt, hard requirements) |
| `§2_creative_vision` | Creative Vision | Artistic direction, mood, style |
| `§3_technical_approach` | Technical Approach | Techniques and tradeoffs chosen to realize §2 |
| `§4_available_resources` | Available Resources | Operators, palette components, patterns retrieved from the KB |
| `§5_network_design` | Network Design | The JSON network + human descriptions |
| `§6_validation_history` | Validation History | Every critic review, appended |
| `§7_build_artifacts` | Build Artifacts | Output paths, build status, validation results |

Section content is an arbitrary dict; the schema constrains the *envelope*, not the payload.

## Versioning envelope

Sections are append-only version lists. Each write produces a `SectionVersion`:

| Field | Type | Notes |
|---|---|---|
| `version` | int | 0-based, monotonically increasing per section |
| `content` | dict | the payload |
| `author` | str | expert id or `"user"` |
| `timestamp` | str | ISO-8601 UTC with `Z` suffix |
| `score` | float or null | quality score attached by a critic review |
| `locked` | bool | snapshot of the lock state when the section was locked |
| `hash` | str | first 16 hex chars of sha256 over `json.dumps(content, sort_keys=True)` — cheap identity/change detection |

"Current" = last element. Old versions stay readable (`read_version`), enabling diffs and
revert-style reasoning.

## Locking

- `lock(section, reason)` freezes a section (e.g. "Approved by critic"); a write to a
  locked section is a hard error (`PermissionError`), not a silent skip.
- `unlock(section, reason)` reopens it — used only by phase reopening (below).
- Locks carry their reason; the lock state is part of the persisted document.

## Phase state machine

```
INIT → CREATIVE → TECHNICAL → RESOURCES → DESIGN → BUILD → COMPLETE
```

- Each phase gates on its section reaching a quality threshold (critic score), then locks
  that section and advances.
- **Reopening:** a blocking issue classified `creative` / `technical` / `design` unlocks
  the matching section (§2/§3/§5) and sets the phase back — the only sanctioned way to
  revisit a locked decision.
- Advancement thresholds come from presets: `quick_draft` (0.70/0.70/0.80),
  `standard` (0.85/0.85/0.90), `excellence` (0.90/0.90/0.95) for creative/technical/design.
- **Stop rules** (per phase): max 3 iterations, or convergence — improvement across the
  last 2 scores below 0.01. On stop, the workflow *proceeds with the best available*
  rather than stalling ("below threshold but converged, proceeding" is an explicit,
  logged decision).

## Blocking issues

A first-class queue, not ad-hoc notes:

| Field | Type | Notes |
|---|---|---|
| `id` | str | `ISSUE-NNNN`, sequential |
| `section` | SectionID | where the problem lives |
| `severity` | str | `high` / `medium` / `low` — high severity is routed first |
| `classification` | str | `creative` / `technical` / `design` / `validation` — drives which phase reopens |
| `description` | str | |
| `resolved` / `resolution` / `resolved_at` | bool / str / timestamp | resolution is recorded, never deleted |

Unresolved issues preempt normal phase handling: the orchestration loop routes them
before any other action.

## Access control (who reads/writes what)

Read scopes per expert (the write map is one section per expert):

| Expert | Reads | Writes |
|---|---|---|
| `creative_expert` | §1 | §2 |
| `cg_expert` | §1, §2 | §3 |
| `kb_query_agent` | §1, §2, §3 | §4 |
| `td_designer` | §1, §2, §3, §4 | §5 |
| `critic` | §1-§5 | §6 |
| `network_builder` | §5 | §7 |
| `td_glsl_expert`, `td_python_expert` | §3, §5 | (contribute via §5 revisions) |
| `summary_generator` | §5, §7 | — |
| orchestration layer | all | — (writes only phase/lock/issue state) |

The intent: experts see *only* the sections upstream of their job, which keeps context
small and forces decisions to flow through the document.

## Orchestration action vocabulary

The stateless decision function returns one action per tick, each with a recorded
`reasoning` string:

`ACTIVATE_EXPERT` (expert id + task + context sections) · `REQUEST_CRITIC_REVIEW`
(section + focus) · `ADVANCE_PHASE` (target + sections to lock) · `REOPEN_PHASE`
(target + sections to unlock) · `HANDLE_BLOCKING_ISSUE` (issue id + strategy) ·
`WAIT_FOR_USER` · `COMPLETE_WORKFLOW`.

A section with content but no score always routes to critic review before any
threshold check — nothing advances unreviewed.

## Persistence + audit

- The whole document serializes to a single YAML file (sections with full version
  history, blocking issues, workflow state) — the "blackboard-as-file" D6 premise is
  literally this snapshot.
- Every operation appends to an in-document event log:
  `read` / `write` / `lock` / `unlock` / `add_issue` / `resolve_issue` /
  `phase_transition` / `iteration`, each with a UTC timestamp and the operation's key
  fields (author, version, hash, reason…). The audit trail travels with the document.

## Notes for the D6 design

- The schema's real asset is the *discipline*: append-only versions, explicit locks with
  reasons, issues as first-class objects, per-expert read scopes, and every decision
  carrying its reasoning. A cowork phase-loop can adopt these on plain files without any
  of the quarantined class machinery.
- Known gaps in the reference design (fix in D6, don't inherit): expert ids in the access
  map drifted from the shipped expert roster; `kb_query_agent` never existed as a
  runnable thing; §4 population was hand-waved; no schema for the §5 payload itself
  (the network JSON contract lives with the builders, keep it there).

#!/usr/bin/env python3
r"""Deterministic scorer for the agent eval (design §4 + §12 revisions).

Verdict taxonomy (load-bearing for regression diagnosis, §5):
  PASS  — gate satisfied
  FAIL  — gate violated by model/product behavior
  ERROR — harness fault (CLI crash, timeout, spend cap, NO MCP CONNECTION
          EVIDENCE, unexpected built-in tool leak) — never books as FAIL
  SKIP  — declared precondition absent (scenario `requires`)

The scorer is INDEPENDENT of agent self-report: verdicts come from artifacts
on disk + an out-of-band re-run of the 5-stage ValidationPipeline + transcript
facts — never from the agent's own success claims (acceptance criterion 4).

R-2: `kb_lookup_any` is the EXPLICIT enumeration below (10 knowledge-retrieval
tools; `get_expert_prompt` and `get_server_info` are deliberately excluded —
they are prompt/contract tools, not KB retrieval). Never say "the N".

R-3 (connection barrier): a headless run can exit normally with the MCP server
never connected (proven on CLI 2.1.19x). Assertions are only evaluated after
POSITIVE connection evidence: a stream-json init event listing the td-builder
server as connected, or >=1 successful td-builder tool_result. Absent =>
verdict ERROR, never FAIL.

R-1: there is no --max-turns in the pinned CLI (2.1.81, re-verified at pilot);
turn counts are SCORED here post-hoc from the transcript, budgets are enforced
by the runner as wall-clock timeout + sweep-level spend cap (ERROR, not FAIL).
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

AGENT_EVAL_DIR = Path(__file__).resolve().parent
EVAL_DIR = AGENT_EVAL_DIR.parent
REPO_ROOT = EVAL_DIR.parent
ENGINE_ROOT = REPO_ROOT / "MCP" / "engine"

# --- gate_common: raw .parm reader + token normalizer (bypass the tolerant
# lossless parser — same evidence surface the Penrose checklist reads by hand).
if str(EVAL_DIR / "build_gate") not in sys.path:
    sys.path.insert(0, str(EVAL_DIR / "build_gate"))
import gate_common  # noqa: E402  (light: run_eval env pins + predicates only)

read_parm_codes = gate_common.read_parm_codes
norm_token = gate_common.norm_token

MCP_PREFIX = "mcp__td-builder__"
# Live-surface scenarios (surface:"live") additionally register the separate
# td-builder-live server; its calls carry this prefix. Offline and live tool
# NAMES are disjoint sets, so both strip to bare names in one call list.
LIVE_MCP_PREFIX = "mcp__td-builder-live__"

# R-2: the explicit enumeration behind the `kb_lookup_any` trace alias.
KB_LOOKUP_TOOLS = (
    "hybrid_search",
    "get_operator_info",
    "query_graph",
    "list_pop_operators",
    "find_operator_examples",
    "find_operator_combination",
    "find_parameter_usage",
    "find_similar_networks",
    "get_parameter_detail",
    "get_network_patterns",
)

# The 18-tool offline surface under test (P01b inventory). register_component
# is offline-buildable/searchable registration, NOT a KB lookup — it must be in
# Lane-M's --allowedTools but never in the kb_lookup_any alias.
OFFLINE_TOOLS = KB_LOOKUP_TOOLS + (
    "td_build_project", "td_build_status", "td_validate", "td_convert",
    "get_expert_prompt", "get_server_info", "expand_toe_file",
    "register_component",
)

TRACE_ALIASES = {"kb_lookup_any": KB_LOOKUP_TOOLS}


# ---------------------------------------------------------------------------
# Normalized run — the lane-independent shape both lanes score against
# ---------------------------------------------------------------------------
@dataclass
class ToolCall:
    name: str                 # bare tool name (mcp__td-builder[-live]__ prefix stripped)
    args: dict
    ok: bool                  # envelope-level success (see _envelope_ok)
    result_text: str = ""
    live: bool = False        # True when the call went to td-builder-live

    @property
    def result_json(self):
        try:
            return json.loads(self.result_text) if self.result_text.strip() else None
        except (ValueError, TypeError):
            return None


@dataclass
class NormalizedRun:
    lane: str                                 # "model" | "replay"
    tool_calls: list = field(default_factory=list)   # [ToolCall] in order
    assistant_text: str = ""
    connection_evidence: str | None = None    # "init_event"|"tool_result"|"in_process"|None
    live_connection_evidence: str | None = None  # same vocabulary, td-builder-live server
    unexpected_tools: list = field(default_factory=list)  # non-td-builder tool_use names
    runner_error: str | None = None           # timeout / spawn / spend_cap / truncated...
    num_turns: int | None = None
    cost_usd: float | None = None
    duration_s: float | None = None
    warm_wait_count: int = 0
    model_id: str | None = None
    raw_result_event: dict | None = None
    assistant_messages: int = 0


def _envelope_ok(text: str) -> bool:
    """Success heuristic over a tool result envelope (mirrors tests/measure/probe.py)."""
    stripped = (text or "").lstrip()
    if stripped.startswith(("Error:", "ERROR:")):
        return False
    try:
        data = json.loads(text) if text.strip() else None
    except (ValueError, TypeError):
        return True  # non-JSON text is not an error envelope
    if isinstance(data, dict):
        if data.get("ok") is False or data.get("success") is False:
            return False
        if data.get("error"):
            return False
        if str(data.get("status", "")).upper() == "ERROR":
            return False
    return True


def parse_stream_json(lines) -> NormalizedRun:
    """Tolerant parser for `claude -p --output-format stream-json` transcripts.

    Only the event shapes we score are interpreted; unknown events are ignored
    (the stream-json contract evolves — cli_version is in the identity block).
    """
    run = NormalizedRun(lane="model")
    calls_by_id: dict[str, ToolCall] = {}
    texts: list[str] = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        etype = ev.get("type")
        if etype == "system" and ev.get("subtype") == "init":
            for srv in ev.get("mcp_servers") or []:
                if srv.get("status") != "connected":
                    continue
                if srv.get("name") == "td-builder":
                    run.connection_evidence = "init_event"
                elif srv.get("name") == "td-builder-live":
                    run.live_connection_evidence = "init_event"
        elif etype == "assistant":
            msg = ev.get("message") or {}
            if msg.get("model"):
                run.model_id = msg["model"]
            run.assistant_messages += 1     # message count, not text-part count (R-1 fallback)
            for part in msg.get("content") or []:
                if part.get("type") == "text":
                    texts.append(part.get("text") or "")
                elif part.get("type") == "tool_use":
                    full = part.get("name") or ""
                    if full.startswith(LIVE_MCP_PREFIX):
                        tc = ToolCall(name=full[len(LIVE_MCP_PREFIX):],
                                      args=part.get("input") or {}, ok=True, live=True)
                        run.tool_calls.append(tc)
                        calls_by_id[part.get("id") or ""] = tc
                    elif full.startswith(MCP_PREFIX):
                        tc = ToolCall(name=full[len(MCP_PREFIX):],
                                      args=part.get("input") or {}, ok=True)
                        run.tool_calls.append(tc)
                        calls_by_id[part.get("id") or ""] = tc
                    else:
                        run.unexpected_tools.append(full)
        elif etype == "user":
            msg = ev.get("message") or {}
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict) or part.get("type") != "tool_result":
                    continue
                tc = calls_by_id.get(part.get("tool_use_id") or "")
                if tc is None:
                    continue
                inner = part.get("content")
                if isinstance(inner, list):
                    tc.result_text = "\n".join(
                        p.get("text") or "" for p in inner
                        if isinstance(p, dict) and p.get("type") == "text")
                elif isinstance(inner, str):
                    tc.result_text = inner
                if part.get("is_error"):
                    tc.ok = False
                else:
                    tc.ok = _envelope_ok(tc.result_text)
                if "kb_warming" in (tc.result_text or ""):
                    run.warm_wait_count += 1
                # Connection evidence (R-3): ANY paired td-builder tool_result
                # proves the server answered — even an error envelope
                # ({"status":"ERROR"}) or an is_error result. A true no-server
                # run produces NO tool_results at all (the proven quiet failure),
                # so it stays None → ERROR. Gating this on tc.ok would misbook a
                # connected server that returns only errors as a harness ERROR
                # instead of the real model FAIL it is. Evidence is per-server:
                # a live-prefixed result vouches for td-builder-live only.
                if tc.live:
                    if run.live_connection_evidence is None:
                        run.live_connection_evidence = "tool_result"
                elif run.connection_evidence is None:
                    run.connection_evidence = "tool_result"
        elif etype == "result":
            run.raw_result_event = ev
            run.num_turns = ev.get("num_turns")
            run.cost_usd = ev.get("total_cost_usd")
            if ev.get("duration_ms") is not None:
                run.duration_s = round(ev["duration_ms"] / 1000.0, 2)
    run.assistant_text = "\n".join(texts)
    if run.num_turns is None:
        # R-1: turns are always countable post-hoc even if the result event is
        # missing (truncated stream) — count assistant MESSAGES, not text parts
        # (a message can hold several text + tool_use blocks).
        run.num_turns = run.assistant_messages or None
    return run


# ---------------------------------------------------------------------------
# Artifact readers (raw .n / .parm — gate_common evidence surface)
# ---------------------------------------------------------------------------
@dataclass
class NFile:
    path: Path
    token: str                    # first line, e.g. "CHOP:lfo"
    inputs: list = field(default_factory=list)   # [(index, source_str)]


def read_n_file(path: Path) -> NFile | None:
    """Parse a .n file: first-line token + the optional inputs block.

    Ground-truth shape (offline builder output, verified 2026-07-04):
        CHOP:math
        tile 150 0 130 90
        flags =  parlanguage 0
        inputs
        {
        0\tlfo1
        }
        end
    Sources may be sibling names (`lfo1`) or path-form (`analysis/out2`).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    if not lines:
        return None
    token = lines[0].strip()
    inputs = []
    in_block = False
    for ln in lines[1:]:
        s = ln.strip()
        if s == "inputs":
            in_block = True
        elif in_block and s == "{":
            continue
        elif in_block and s == "}":
            in_block = False
        elif in_block and s:
            parts = s.split(None, 1)
            if len(parts) == 2:
                inputs.append((parts[0], parts[1].strip()))
            elif parts:
                inputs.append(("", parts[0]))
    return NFile(path=path, token=token, inputs=inputs)


@dataclass
class ExpandedArtifact:
    """One built artifact: the collapsed file + its expanded .dir contents."""
    file: Path
    dir: Path
    ops: dict = field(default_factory=dict)       # rel_posix_path (no .n) -> NFile

    @classmethod
    def locate(cls, work_dir: Path, filename: str) -> "ExpandedArtifact | None":
        hits = sorted(work_dir.rglob(filename))
        for f in hits:
            d = f.with_name(f.name + ".dir")
            if d.is_dir():
                art = cls(file=f, dir=d)
                for n in sorted(d.rglob("*.n")):
                    nf = read_n_file(n)
                    if nf:
                        rel = n.relative_to(d).as_posix()[:-2]  # strip ".n"
                        art.ops[rel] = nf
                return art
        return None

    def is_project(self) -> bool:
        """True iff the expanded dir is a real .toe PROJECT, not a .tox wearing a
        .toe name (the exact BUG-1 regression s12 guards). Ground truth
        (probed 2026-07-04): a project expands with a top-level `.application`
        file and a `perform.n` whose token is `COMP:window`; a component
        expands to a single `COMP:base` wrapper with neither."""
        if (self.dir / ".application").exists():
            return True
        perf = self.dir / "perform.n"
        return perf.exists() and (read_n_file(perf) or NFile(perf, "")).token == "COMP:window"

    def is_component(self) -> bool:
        """True iff the expanded dir is a .tox COMPONENT (root <stem>.n =
        COMP:base, and NOT a project)."""
        if self.is_project():
            return False
        root = self.dir / f"{self.file.stem}.n"
        return root.exists() and (read_n_file(root) or NFile(root, "")).token == "COMP:base"

    def sibling_token(self, nf: NFile, source: str) -> str | None:
        """Token of a wire SOURCE relative to nf's dir. Handles flat sibling
        names ('lfo1') and path-form ('analysis/out2', where the wire source is
        the container 'analysis'). Resolution order: the full path as a key
        (from the .dir root), then relative to nf's own directory, then the
        first path segment (the source container) relative to nf's dir."""
        rel_dir = nf.path.parent.relative_to(self.dir).as_posix()
        head = source.split("/", 1)[0]
        candidates = [source]                              # full path from root
        if rel_dir != ".":
            candidates.append(f"{rel_dir}/{source}")       # full path under nf's dir
            candidates.append(f"{rel_dir}/{head}")         # container under nf's dir
        candidates.append(head)                            # container from root
        for key in candidates:
            hit = self.ops.get(key)
            if hit:
                return hit.token
        return None

    def parm_for(self, nf: NFile) -> dict:
        return read_parm_codes(nf.path.with_suffix(".parm"))


# ---------------------------------------------------------------------------
# Out-of-band validation (mirror of mcp_server.py td_validate, engine-direct)
# ---------------------------------------------------------------------------
_VALIDATOR = None


def _validator():
    """FormatConverter.from_builder + ValidationPipeline — the EXACT stack of
    the shipped td_validate handler, constructed through the engine's single
    seam (MCP/engine/api/validate.py::build_validation_stack) and imported from
    the engine directly so scoring works in the light-deps lanes (no ML stack,
    no mcp_server import — the scorer must not trust the server surface it
    scores). Canonicalization changes now land in the shared seam; this mirror
    only owns the from_builder call in validate_design below."""
    global _VALIDATOR
    if _VALIDATOR is None:
        for p in (str(REPO_ROOT), str(ENGINE_ROOT)):
            if p not in sys.path:
                sys.path.insert(0, p)
        # Lazy: `api` resolves only after the ENGINE_ROOT insert above.
        from api.validate import build_validation_stack
        _registry, converter, validator = build_validation_stack()
        _VALIDATOR = (converter, validator)
    return _VALIDATOR


def validate_design(design: dict) -> dict:
    """Run the 5-stage pipeline on a builder-format design. Never raises."""
    try:
        converter, validator = _validator()
        network = converter.from_builder(design)
        report = validator.validate(network, design.get("project", "network"))
        return {
            "valid": bool(report.valid),
            "total_errors": int(report.total_errors),
            "errors": [f"{e.stage}: {e.message}" for e in report.get_errors()][:20],
        }
    except Exception as e:  # noqa: BLE001 — a validator crash is a scoring fact
        return {"valid": False, "total_errors": -1, "errors": [f"validator raised: {e}"]}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
@dataclass
class ScoreResult:
    scenario_id: str
    lane: str
    verdict: str                      # PASS | FAIL | ERROR | SKIP
    failures: list = field(default_factory=list)     # [{assertion, detail}]
    error: str | None = None
    advisory: dict = field(default_factory=dict)

    @property
    def fingerprints(self) -> list:
        return sorted(f["assertion"] for f in self.failures)

    def to_json(self) -> dict:
        return {
            "scenario": self.scenario_id, "lane": self.lane, "verdict": self.verdict,
            "error": self.error, "failures": self.failures,
            "fingerprints": self.fingerprints, "advisory": self.advisory,
        }


def _names_for(alias_or_name) -> tuple:
    """Expand a trace-assertion tool reference: alias, bare name, or any-of list."""
    if isinstance(alias_or_name, (list, tuple)):
        out = []
        for x in alias_or_name:
            out.extend(_names_for(x))
        return tuple(out)
    if alias_or_name in TRACE_ALIASES:
        return TRACE_ALIASES[alias_or_name]
    return (alias_or_name,)


def _first_call_index(run: NormalizedRun, ref) -> int | None:
    names = set(_names_for(ref))
    for i, tc in enumerate(run.tool_calls):
        if tc.name in names:
            return i
    return None


def score_scenario(scenario: dict, run: NormalizedRun, work_dir: Path,
                   skip_reason: str | None = None) -> ScoreResult:
    """The deterministic gate. Order matters (§4 + R-3):
    SKIP -> runner ERROR -> connection barrier ERROR -> tool-leak ERROR ->
    assertions (artifact/validation/trace/response/discipline) -> PASS/FAIL."""
    sid = scenario["id"]
    res = ScoreResult(scenario_id=sid, lane=run.lane, verdict="PASS")
    res.advisory = _advisory(run)

    if skip_reason:
        res.verdict = "SKIP"
        res.error = skip_reason
        return res

    if run.runner_error:
        res.verdict = "ERROR"
        res.error = f"runner: {run.runner_error}"
        return res

    # R-3 — the connection barrier: no positive MCP connection evidence means
    # every downstream assertion is meaningless. ERROR, never FAIL.
    if run.connection_evidence is None:
        res.verdict = "ERROR"
        res.error = ("no MCP connection evidence in transcript (init event absent / "
                     "no successful td-builder tool result) — quiet-no-server run")
        return res

    # Live scenarios need the SAME positive evidence for td-builder-live: a dead
    # live server (or one that never connected) must never read as "the model
    # failed to use the live tools".
    if scenario.get("surface") == "live" and run.live_connection_evidence is None:
        res.verdict = "ERROR"
        res.error = ("live scenario but no td-builder-live connection evidence in "
                     "transcript (init event absent / no live tool result) — "
                     "quiet-no-live-server run")
        return res

    # Harness-config leak: a built-in tool executing despite --disallowedTools
    # is a runner fault, not a model capability fact.
    tolerated = set(scenario.get("_tolerated_builtin_tools") or ())
    leaked = [t for t in run.unexpected_tools if t not in tolerated]
    if leaked:
        res.verdict = "ERROR"
        res.error = f"non-td-builder tool_use leaked through config: {sorted(set(leaked))}"
        return res

    expect = scenario.get("expect") or {}

    _score_trace(expect.get("trace") or [], run, res)
    _score_response(expect.get("response") or {}, run, res)
    artifacts = _score_artifact(expect.get("artifact") or {}, run, work_dir, res)
    _score_validation(expect.get("validate"), run, res)
    _score_discipline(scenario, run, work_dir, res, artifacts)

    if res.failures:
        res.verdict = "FAIL"
    return res


def _fail(res: ScoreResult, assertion: str, detail: str):
    res.failures.append({"assertion": assertion, "detail": detail})


def _score_trace(items, run: NormalizedRun, res: ScoreResult):
    for item in items:
        if "tool_called" in item:
            ref = item["tool_called"]
            if _first_call_index(run, ref) is None:
                _fail(res, f"trace.tool_called[{ref}]", "never called")
        elif "tool_not_called" in item:
            ref = item["tool_not_called"]
            if _first_call_index(run, ref) is not None:
                _fail(res, f"trace.tool_not_called[{ref}]", "was called")
        elif "call_order" in item:
            seq = item["call_order"]
            last = -1
            for ref in seq:
                idx = _first_call_index(run, ref)
                if idx is None or idx < last:
                    _fail(res, f"trace.call_order[{'->'.join(map(str, seq))}]",
                          f"'{ref}' missing or out of order")
                    break
                last = idx
        elif "tool_result_re" in item:
            # Lane-independent result-surface assertion (added for the live-tool
            # scenarios, PR #24/#26 behaviors): ≥1 call to `tool` whose result
            # text matches `re`. Replay re-executes and captures result_text, so
            # unlike `response` assertions this one DOES score in the replay
            # lane — it binds to the tool contract, not the model's prose.
            spec = item["tool_result_re"]
            names = set(_names_for(spec["tool"]))
            pat = spec["re"]
            hits = [tc for tc in run.tool_calls if tc.name in names]
            if not hits:
                _fail(res, f"trace.tool_result_re[{spec['tool']}:{pat}]",
                      "tool never called")
            elif not any(re.search(pat, tc.result_text or "", re.MULTILINE)
                         for tc in hits):
                _fail(res, f"trace.tool_result_re[{spec['tool']}:{pat}]",
                      f"no match in {len(hits)} result(s)")
        else:
            _fail(res, f"trace.unknown[{sorted(item)}]", "unknown trace assertion key")


def _score_response(spec, run: NormalizedRun, res: ScoreResult):
    if run.lane == "replay":
        # Response assertions measure the MODEL's answer; replay has no model.
        # Skipping them here is part of the replay-gate =/= agent-gate honesty
        # rule — the replay lane only certifies tools/KB/builder/artifacts.
        return
    text = run.assistant_text or ""
    for pat in spec.get("must_match") or []:
        if not re.search(pat, text, re.MULTILINE):
            _fail(res, f"response.must_match[{pat}]", "no match in assistant text")
    for pat in spec.get("must_not_match") or []:
        m = re.search(pat, text, re.MULTILINE)
        if m:
            _fail(res, f"response.must_not_match[{pat}]", f"matched: {m.group(0)[:80]!r}")


def _score_artifact(spec, run: NormalizedRun, work_dir: Path, res: ScoreResult) -> list:
    artifacts = []
    if spec.get("absent"):
        assets = (work_dir / "assets").resolve()
        stray = []
        for pat in ("*.tox", "*.toe"):
            for p in work_dir.rglob(pat):
                # fixtures staged by the runner live UNDER assets/ — exclude by
                # PATH, not basename (a real illicit build sharing a fixture's
                # filename must still be caught).
                try:
                    p.resolve().relative_to(assets)
                    continue
                except ValueError:
                    stray.append(p.relative_to(work_dir).as_posix())
        if stray:
            _fail(res, "artifact.absent", f"unexpected artifacts written: {sorted(stray)}")
        return artifacts

    for key in ("tox", "toe"):
        name = spec.get(key)
        if not name:
            continue
        art = ExpandedArtifact.locate(work_dir, name)
        if art is None:
            f = sorted(work_dir.rglob(name))
            detail = ("file exists but expanded .dir missing" if f
                      else "file not found under run dir")
            _fail(res, f"artifact.{key}[{name}]", detail)
            continue
        # Type verification (BUG-1 regression guard): a file NAMED *.toe that is
        # structurally a component (or vice-versa) must FAIL — the "handed a .tox
        # wearing a .toe name" case s12 exists to catch. Extension trust is not
        # enough; verify the expanded structure.
        if key == "toe" and not art.is_project():
            _fail(res, f"artifact.{key}[{name}]",
                  "named .toe but expanded structure is NOT a project "
                  "(no .application / perform.n=COMP:window) — a .tox in disguise")
            continue
        if key == "tox" and not art.is_component():
            _fail(res, f"artifact.{key}[{name}]",
                  "named .tox but expanded structure is NOT a component "
                  "(root .n != COMP:base)")
            continue
        artifacts.append(art)

    if not artifacts:
        if spec.get("tox") or spec.get("toe"):
            return artifacts       # existence failures already recorded
        return artifacts

    primary = artifacts[0]

    for req in spec.get("ops_present") or []:
        want = norm_token(f"{req['family']}:{req['type']}")
        n = sum(1 for nf in primary.ops.values() if norm_token(nf.token) == want)
        if n < req.get("min", 1):
            _fail(res, f"artifact.ops_present[{req['family']}:{req['type']}]",
                  f"found {n}, need >= {req.get('min', 1)}")

    for req in spec.get("ops_absent") or []:
        want = norm_token(f"{req['family']}:{req['type']}")
        if any(norm_token(nf.token) == want for nf in primary.ops.values()):
            _fail(res, f"artifact.ops_absent[{req['family']}:{req['type']}]", "present")

    if spec.get("min_total_ops"):
        # every .n except the top-level wrapper is one op
        n_ops = max(0, len(primary.ops) - 1)
        if n_ops < spec["min_total_ops"]:
            _fail(res, f"artifact.min_total_ops[{spec['min_total_ops']}]", f"found {n_ops}")

    if spec.get("min_families"):
        fams = {nf.token.split(":", 1)[0] for nf in primary.ops.values() if ":" in nf.token}
        if spec.get("min_families_exclude_comp"):
            fams.discard("COMP")
        if len(fams) < spec["min_families"]:
            _fail(res, f"artifact.min_families[{spec['min_families']}]", f"found {sorted(fams)}")

    for req in spec.get("wires") or []:
        f_t, t_t = norm_token(req["from_type"]), norm_token(req["to_type"])
        found = False
        for nf in primary.ops.values():
            if norm_token(nf.token) != t_t:
                continue
            for _, src in nf.inputs:
                if primary.sibling_token(nf, src) and \
                        norm_token(primary.sibling_token(nf, src)) == f_t:
                    found = True
                    break
            if found:
                break
        if not found:
            _fail(res, f"artifact.wires[{req['from_type']}->{req['to_type']}]",
                  "no type-adjacent wire found")

    for req in spec.get("params") or []:
        want_t = norm_token(req["op_type"])
        ok = False
        for nf in primary.ops.values():
            if norm_token(nf.token) != want_t:
                continue
            codes = primary.parm_for(nf)
            got = codes.get(req["param"])
            if got is None:
                continue
            mode, raw = got
            if "mode" in req and str(req["mode"]) != mode:
                continue
            if "value" in req and str(req["value"]) != raw:
                continue
            if "value_contains" in req and req["value_contains"] not in raw:
                continue
            if "value_re" in req and not re.search(req["value_re"], raw):
                continue
            ok = True
            break
        if not ok:
            _fail(res, f"artifact.params[{req['param']}@{req['op_type']}]",
                  "no op of that type carries the param with the required mode/value")

    for req in spec.get("parm_line_re") or spec.get("file_re") or []:
        _score_file_re(req, artifacts, res, "artifact.parm_line_re")

    for req in spec.get("network_has") or []:
        hits = _glob_all(artifacts, req["file_glob"])
        if not hits:
            _fail(res, f"artifact.network_has[{req['file_glob']}]", "no file matched glob")
            continue
        block = req.get("block")
        want_re = req.get("re")
        ok = any((block and block in h.read_text(encoding="utf-8", errors="replace")) or
                 (want_re and re.search(want_re, h.read_text(encoding="utf-8", errors="replace"),
                                        re.MULTILINE))
                 for h in hits)
        if not ok:
            _fail(res, f"artifact.network_has[{req['file_glob']}:{block or want_re}]",
                  "block/pattern absent")

    for req in spec.get("work_file_re") or []:
        # docked content DATs are FILE-BACKED (shaders/<host>_pixel.glsl beside
        # the artifact, not inside the .dir) — glob the whole run work dir
        hits = sorted(work_dir.rglob(req["file_glob"]))
        if not hits:
            _fail(res, f"artifact.work_file_re[{req['file_glob']}]", "no file matched glob")
            continue
        if "re" in req and not any(
                re.search(req["re"], h.read_text(encoding="utf-8", errors="replace"),
                          re.MULTILINE) for h in hits):
            _fail(res, f"artifact.work_file_re[{req['file_glob']}:{req['re']}]", "no match")
        if "not_re" in req:
            for h in hits:
                if re.search(req["not_re"], h.read_text(encoding="utf-8", errors="replace"),
                             re.MULTILINE):
                    _fail(res, f"artifact.work_file_re[{req['file_glob']}:!{req['not_re']}]",
                          f"matched in {h.name}")

    for req in spec.get("n_file") or []:
        hits = _glob_all(artifacts, req["file_glob"])
        if not hits:
            _fail(res, f"artifact.n_file[{req['file_glob']}]", "no file matched glob")
            continue
        for h in hits:
            text = h.read_text(encoding="utf-8", errors="replace")
            first = text.splitlines()[0].strip() if text.splitlines() else ""
            if "first_line" in req and norm_token(first) != norm_token(req["first_line"]):
                _fail(res, f"artifact.n_file[{req['file_glob']}:first_line]",
                      f"got {first!r}, want {req['first_line']!r}")
            if "re" in req and not re.search(req["re"], text, re.MULTILINE):
                _fail(res, f"artifact.n_file[{req['file_glob']}:{req['re']}]", "no match")
            if "not_re" in req and re.search(req["not_re"], text, re.MULTILINE):
                _fail(res, f"artifact.n_file[{req['file_glob']}:!{req['not_re']}]", "matched")
    return artifacts


def _glob_all(artifacts, pattern):
    out = []
    for art in artifacts:
        out.extend(sorted(art.dir.rglob(pattern)))
    return out


def _score_file_re(req, artifacts, res, tag):
    hits = _glob_all(artifacts, req["file_glob"])
    if not hits:
        _fail(res, f"{tag}[{req['file_glob']}]", "no file matched glob")
        return
    if "re" in req:
        if not any(re.search(req["re"], h.read_text(encoding="utf-8", errors="replace"),
                             re.MULTILINE) for h in hits):
            _fail(res, f"{tag}[{req['file_glob']}:{req['re']}]", "no match in any file")
    if "not_re" in req:
        for h in hits:
            m = re.search(req["not_re"], h.read_text(encoding="utf-8", errors="replace"),
                          re.MULTILINE)
            if m:
                _fail(res, f"{tag}[{req['file_glob']}:!{req['not_re']}]",
                      f"matched in {h.name}: {m.group(0)[:60]!r}")


def _successful_build_designs(run: NormalizedRun) -> list:
    out = []
    for tc in run.tool_calls:
        if tc.name != "td_build_project":
            continue
        data = tc.result_json
        status = (data or {}).get("status", "")
        if str(status).upper() == "SUCCESS":
            design = tc.args.get("design") or tc.args.get("network_design")
            if isinstance(design, dict):
                out.append(design)
    return out


def _score_validation(mode, run: NormalizedRun, res: ScoreResult):
    """Out-of-band re-validation (§4.2): we do NOT trust the agent's own
    td_validate result — whether it CALLED td_validate is a trace assertion."""
    if mode != "PASS":
        return
    designs = _successful_build_designs(run)
    if not designs:
        _fail(res, "validate.PASS", "no successful td_build_project call to validate")
        return
    for i, design in enumerate(designs):
        v = validate_design(design)
        if not v["valid"] or v["total_errors"] != 0:
            _fail(res, f"validate.PASS[build#{i}]",
                  f"{v['total_errors']} errors: {v['errors'][:3]}")


def _score_discipline(scenario, run: NormalizedRun, work_dir: Path, res: ScoreResult,
                      artifacts):
    """Always-on (§4.4): writes confined to the run dir; no scenario opt-out."""
    run_dir = work_dir.resolve()

    def _confined(p: Path) -> bool:
        # is_relative_to (not a raw string prefix): a sibling 'work_evil' must
        # NOT count as inside 'work'. Windows-case-insensitive via casefold.
        try:
            rp, rd = p.resolve(), run_dir
            return Path(rp.as_posix().casefold()).is_relative_to(
                Path(rd.as_posix().casefold())) or rp == rd
        except (ValueError, OSError):
            return False

    for tc in run.tool_calls:
        if tc.name != "td_build_project":
            continue
        out_dir = tc.args.get("output_dir")
        if not out_dir:
            _fail(res, "discipline.writes_confined[output_dir]",
                  "td_build_project called WITHOUT output_dir (defaults inside the repo)")
        elif not _confined(Path(str(out_dir))):
            _fail(res, "discipline.writes_confined[output_dir]",
                  f"output_dir escapes the run dir: {out_dir}")
    for art in artifacts:
        if not _confined(art.file):
            _fail(res, "discipline.writes_confined[artifact]",
                  f"artifact outside run dir: {art.file}")


def _advisory(run: NormalizedRun) -> dict:
    per_tool: dict[str, int] = {}
    for tc in run.tool_calls:
        per_tool[tc.name] = per_tool.get(tc.name, 0) + 1
    first_build = _first_call_index(run, "td_build_project")
    kb_before = sum(1 for tc in run.tool_calls[:first_build] if tc.name in KB_LOOKUP_TOOLS) \
        if first_build is not None else \
        sum(1 for tc in run.tool_calls if tc.name in KB_LOOKUP_TOOLS)
    denom = first_build if first_build is not None else len(run.tool_calls)
    return {
        "turns": run.num_turns,
        "tool_calls": len(run.tool_calls),
        "per_tool": dict(sorted(per_tool.items())),
        "cost_usd": run.cost_usd,
        "wall_s": run.duration_s,
        "warm_wait_events": run.warm_wait_count,
        "kb_calls_before_build": kb_before,
        # approximation of the manual suites' KB-first%: KB lookups among all
        # calls preceding the first build (or all calls when nothing builds)
        "kb_first_ratio": round(kb_before / denom, 3) if denom else None,
        "model_id": run.model_id,
    }


# ---------------------------------------------------------------------------
def load_scenario(path: Path) -> dict:
    sc = json.loads(Path(path).read_text(encoding="utf-8"))
    for req in ("id", "version", "prompt", "expect"):
        if req not in sc:
            raise ValueError(f"scenario {path.name} missing required key '{req}'")
    # Structural safety coupling (review F1): a live-surface scenario mutates
    # the open TouchDesigner project, so the td_live_running precondition
    # (TD_EVAL_LIVE=1 opt-in + socket probe) must gate it BY CONSTRUCTION —
    # never by per-scenario convention. A future live scenario that forgets
    # the requires token still cannot run without the opt-in.
    if sc.get("surface") == "live":
        reqs = list(sc.get("requires") or [])
        if "td_live_running" not in reqs:
            sc["requires"] = ["td_live_running"] + reqs
    return sc


def load_transcript(path: Path) -> NormalizedRun:
    return parse_stream_json(Path(path).read_text(encoding="utf-8").splitlines())

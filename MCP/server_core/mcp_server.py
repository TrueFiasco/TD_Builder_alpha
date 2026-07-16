#!/usr/bin/env python3
"""
TouchDesigner MCP Server with Multi-Agent System
Spawns specialized engineer agents for knowledge extraction
"""

import sys
import json
import asyncio
import os
import re
import uuid
from pathlib import Path
from typing import Any, Sequence, Dict, Callable, List, Optional, Union
import base64
import threading
import time

sys.path.insert(0, str(Path(__file__).parent))

# Add unified_system to path for validation and format conversion
UNIFIED_SYSTEM_ROOT = Path(__file__).resolve().parent.parent / "engine"
sys.path.insert(0, str(UNIFIED_SYSTEM_ROOT))

# --------------------------------------------------------------------------
# Stdout-pollution guard
# --------------------------------------------------------------------------
# MCP uses stdout for the JSON-RPC protocol channel. Diagnostic prints from
# imported modules (unified_graph_query, enhanced_graph_query, search
# adapters, sentence-transformers etc.) use bare print() which would write
# to stdout and pollute the protocol — Claude Desktop then surfaces those
# as "Unexpected token ... is not valid JSON" warnings to the user.
#
# Solution: redirect sys.stdout -> sys.stderr for the entire import and
# module-level initialization phase. Restored to the real stdout in main()
# right before stdio_server() takes over the protocol channel.
#
# mcp_server.py's own prints already use file=sys.stderr explicitly, so
# this change doesn't affect them. It only catches the bare print() calls
# in the imported third-party modules.
_real_stdout = sys.stdout
sys.stdout = sys.stderr

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, ImageContent, ToolAnnotations
except ImportError:
    print("ERROR: MCP package not installed", file=sys.stderr)
    print("Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

# Output budgets for the two flood-prone tools (W4b). server_core is on sys.path
# (inserted above); output_budget is a pure json/os module — safe to import here.
from output_budget import budget_full_expand, budget_hybrid_results  # noqa: E402

# hybrid_search proactively caps how many wiki_parameters it hydrates per hit, so a
# multi-hit envelope stays small even when it is under HYBRID_SEARCH_MAX_BYTES (the
# reactive shed only fires once the WHOLE envelope is oversized). The TRUE counts are
# always preserved; `parameters_capped` flags any hit whose dict was truncated.
PARAM_HYDRATE_CAP = 12

# TD Live Client tools live SOLELY on the separate `td-builder-live` server
# (MCP/live_server.py). This offline `td-builder` server never co-loads them, so
# its tool surface is a fixed 18 regardless of ambient import state — co-loading
# would make the count depend on whether MCP/live_client happened to be importable
# (it isn't on this server's sys.path). The three symbols stay defined (pinned
# off) because scope_for_server() and get_server_info still read them.
TD_LIVE_ENABLED = False
TD_LIVE_TOOLS = []
TD_LIVE_HANDLERS = {}
print("Offline server: live TD tools are served separately by td-builder-live.", file=sys.stderr)

try:
    import importlib.util

    # Load unified graph query engine (wiki docs + enhanced examples)
    spec = importlib.util.spec_from_file_location("unified_graph_query", str(Path(__file__).parent / "unified_graph_query.py"))
    unified_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(unified_module)
    UnifiedGraphQuery = unified_module.UnifiedGraphQuery
    print("Loaded unified graph query (wiki + examples)", file=sys.stderr)

    # Load unified search adapter (enhanced with multiple embedding providers).
    # Deliberately no fallback: hybrid_search.py's HybridGraphRAG is the eval
    # harness's frozen A/B baseline (eval/run_eval.py --backend legacy), not a
    # server backend — a broken unified_search import is an install defect that
    # must fail loudly. Missing optional deps (sentence-transformers, vector DB)
    # surface later, in _load_kb(), as a partial-KB degrade.
    try:
        spec = importlib.util.spec_from_file_location("unified_search", str(Path(__file__).parent / "search" / "unified_search.py"))
        search_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(search_module)
        UnifiedSearchAdapter = search_module.UnifiedSearchAdapter
        print("Loaded unified search adapter with enhanced embedding support", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: Could not load unified search adapter (search/unified_search.py): {e}", file=sys.stderr)
        sys.exit(1)

except Exception as e:
    print(f"ERROR: Could not load unified graph query: {e}", file=sys.stderr)
    sys.exit(1)

# META_AGENTIC_TOOL builders — the live .tox/.toe build path. td_build_project
# and _run_build (both modes) depend on exactly these two imports, so the flag
# gating them must not be coupled to any other module's importability.
try:
    from meta_agentic.execution.tox_builder import ToxBuilder
    from meta_agentic.execution.toe_builder_bridge import ToeBuilderBridge
    EXPERT_WORKFLOW_ENABLED = True
    print("META_AGENTIC_TOOL expert workflow enabled", file=sys.stderr)
except ImportError as e:
    EXPERT_WORKFLOW_ENABLED = False
    print(f"WARNING: META_AGENTIC_TOOL not available: {e}", file=sys.stderr)

# Import unified_system components for validation and format conversion
try:
    from api.network_builder import NetworkBuilder
    from core.format_converter import FormatConverter
    from core.operator_registry import OperatorRegistry
    from validation.pipeline import ValidationPipeline
    from builders.toe_builder import TOEBuilder

    # Initialize validation/conversion components
    _registry = OperatorRegistry()
    _converter = FormatConverter(_registry)
    _validator = ValidationPipeline(_registry)
    UNIFIED_SYSTEM_ENABLED = True
    print("Unified system validation/conversion enabled", file=sys.stderr)
except (ImportError, FileNotFoundError) as e:
    # FileNotFoundError: the KB (operators.json) isn't fetched yet. Degrade
    # gracefully (the build/validate/convert tools emit their own unavailable
    # message) instead of crashing the whole MCP import.
    UNIFIED_SYSTEM_ENABLED = False
    _registry = None
    _converter = None
    _validator = None
    print(f"WARNING: Unified system not available: {e}", file=sys.stderr)

# Release root: honor the documented TD_BUILDER_ROOT relocation knob (see
# MCP/README.md / Config/SETTINGS.md), else infer from this file's location
# (<root>/MCP/server_core/mcp_server.py). Everything the offline server
# resolves on disk (Agents/, KB/) hangs off this.
_RELEASE_ROOT = (
    Path(os.environ["TD_BUILDER_ROOT"]).resolve()
    if os.environ.get("TD_BUILDER_ROOT")
    else Path(__file__).resolve().parents[2]
)

# Expert prompts for td_designer, network_builder, etc.
EXPERTS_DIR = _RELEASE_ROOT / "Agents" / "experts"

AVAILABLE_EXPERTS = {
    "td_designer": {
        "description": "Create TouchDesigner network specifications from creative briefs. Knows operator types, parameters, and TD conventions.",
        "files": ["build.md", "plan.md"]
    },
    "network_builder": {
        "description": "Build .toe/.tox files from network specifications. Handles parameter values, connections, and file generation.",
        "files": ["build.md", "plan.md"]
    },
    "td_glsl_expert": {
        "description": "Write and optimize GLSL shaders for TouchDesigner. Knows GLSL TOP patterns and uniforms.",
        "files": ["build.md", "plan.md"]
    },
    "td_python_expert": {
        "description": "Write Python scripts for TouchDesigner automation. Knows TD Python API.",
        "files": ["build.md", "plan.md"]
    },
    "ui_expert": {
        "description": "Design TouchDesigner UI and control panels. Knows widget patterns.",
        "files": ["build.md", "plan.md"]
    },
    "critic": {
        "description": "Review and score outputs. Flags issues and suggests improvements.",
        "files": ["build.md"]
    },
}
# Roster cleanup (H1/M20/M21): three legacy multi-agent-era expert ids were
# registered here historically but never invoked by V2-V6 strategies and not
# reachable via the standard expert loader; they were removed from this roster.

def _load_expert_expertise(expert_name: str, per_file_cap: int = 16000,
                           total_cap: int = 48000) -> str:
    """Load the curated expertise YAMLs an expert declares in its config.yaml
    `expertise_inputs:` and return them as an appendable prompt block (Round-4 #3 slice).

    These ~18 YAMLs were dormant — declared in every expert config but never read by any
    code. Size-capped so the big catalogs (e.g. td_operators.yaml, 234 KB) don't blow the
    prompt; the live MCP tools (get_operator_info / find_operator_examples / hybrid_search)
    remain the source for exhaustive operator/param facts."""
    config_path = EXPERTS_DIR / expert_name / "config.yaml"
    if not config_path.exists():
        return ""
    try:
        import yaml as _yaml
        cfg = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    inputs = cfg.get("expertise_inputs") or []
    repo_root = EXPERTS_DIR.parent.parent  # <root>/Agents/experts -> <root>
    chunks, total = [], 0
    for i, item in enumerate(inputs):
        if not isinstance(item, dict):
            continue
        rel = item.get("path")
        if not rel:
            continue
        f = repo_root / rel
        if not f.exists():
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        if len(content) > per_file_cap:
            content = content[:per_file_cap] + (
                f"\n# ...[truncated to {per_file_cap} chars - full file at {rel}; "
                "use the KB tools for exhaustive operator/param facts]")
        chunk = f"### {Path(rel).name} - {item.get('purpose', '')}\n{content}"
        if total + len(chunk) > total_cap:
            remaining = ", ".join(
                Path(x.get("path", "")).name for x in inputs[i:] if isinstance(x, dict))
            chunks.append(f"### (further expertise omitted to fit context: {remaining})")
            break
        chunks.append(chunk)
        total += len(chunk)
    if not chunks:
        return ""
    return ("\n\n## Curated expertise (configured for this expert)\n"
            "Use these alongside the live MCP tools for operator/param facts.\n\n"
            + "\n\n".join(chunks))


def load_expert_prompt(expert_name: str, phase: str = "build") -> str:
    """Load expert prompt from meta_agentic/experts/{expert}/{phase}.md, with the expert's
    declared expertise YAMLs appended (Round-4 #3 slice — previously dormant)."""
    expert_dir = EXPERTS_DIR / expert_name
    if not expert_dir.exists():
        return f"ERROR: Expert '{expert_name}' not found"

    prompt_file = expert_dir / f"{phase}.md"
    if not prompt_file.exists():
        return f"ERROR: Phase '{phase}' not found for expert '{expert_name}'"

    try:
        base = prompt_file.read_text(encoding='utf-8')
    except Exception as e:
        return f"ERROR reading {prompt_file}: {e}"

    return base + _load_expert_expertise(expert_name)




# --------------------------------------------------------------------------
# Lazy knowledge-base init  (FAST STARTUP — fixes Desktop init timeouts)
# --------------------------------------------------------------------------
# The enhanced graph (~37k nodes) + ChromaDB + sentence-transformers take
# 1-2 min to load. Doing that at import blocks the MCP `initialize` handshake,
# so trivial tools (get_server_info) and the client connection itself time out
# in Claude/ChatGPT Desktop — especially with multiple servers contending.
# Fix: resolve bundle paths now (cheap) and DEFER the heavy construction to
# the first KB-dependent tool call via _ensure_kb().
try:
    # Prefer the consolidated alpha KB/ bundle (release-root/KB); fall back to
    # the legacy META_AGENTIC_TOOL/data layout (pre_alpha baseline).
    _kb = _RELEASE_ROOT / "KB"
    _data = Path(__file__).parent / "data"
    if (_kb / "operators.json").exists():
        enhanced_graph_path = _kb / "knowledge_graph_enhanced.gpickle"
        graphrag_json_path = _kb / "graphrag.json"
        enriched_wiki_path = _kb / "operators.json"
        vectordb_path = _kb / "vector_db"
    else:
        enhanced_graph_path = _data / "td_knowledge_graph_enhanced.gpickle"
        graphrag_json_path = _data / "td_graphrag.json"
        enriched_wiki_path = _data / "wiki_docs" / "td_universal_parsed_enriched.json"
        vectordb_path = _data / "vector_db_merged"
except Exception as e:
    print(f"WARNING: Could not resolve KB paths: {e}", file=sys.stderr)
    enhanced_graph_path = graphrag_json_path = enriched_wiki_path = vectordb_path = Path("___missing___")

# KB identity for get_server_info: SERVER_VERSION is a code constant decoupled
# from the installed KB, and that decoupling has already caused version
# confusion (server reported one version while the KB was another). Surface the
# KB manifest's own version next to it.
_KB_ROOT = _RELEASE_ROOT / "KB"
_KB_MANIFEST_VERSION = None
_KB_TD_BUILD = None  # informational (the KB's TouchDesigner build pin); never compared
try:
    _kb_manifest = json.loads((_KB_ROOT / "manifest.json").read_text(encoding="utf-8"))
    _KB_MANIFEST_VERSION = _kb_manifest.get("version")
    _KB_TD_BUILD = _kb_manifest.get("td_build")
except Exception as _e:
    print(f"WARNING: KB manifest unreadable at {_KB_ROOT / 'manifest.json'} ({_e}); "
          f"get_server_info will report kb_version=null", file=sys.stderr)

knowledge_graph = None
hybrid_search = None
# _KB_STATUS values: "pending" | "warming" | "ready" | "partial" | "failed"
#   pending  — warmup hasn't started yet
#   warming  — _load_kb() is running right now
#   ready    — both knowledge_graph AND hybrid_search loaded
#   partial  — knowledge_graph loaded but hybrid_search is None (semantic search
#              unavailable: vector_db missing OR sentence-transformers not installed
#              OR semantic init exception). Graph-only tools still work.
#   failed   — knowledge_graph could not be loaded. No KB tools work.
# _KB_REASON: human-readable detail for partial/failed states. Empty otherwise.
_KB_STATUS = "pending"
_KB_REASON: str = ""
_kb_lock = threading.Lock()  # serializes warm-up thread vs first KB tool call


def _ensure_kb():
    """Build the knowledge graph + unified search on first use (idempotent).

    BLOCKING — used by the warmup thread at startup. Tool handlers should
    use _kb_check() instead, which is non-blocking and returns a structured
    "warming" response to the caller rather than waiting on the lock.
    """
    if _KB_STATUS in ("ready", "partial", "failed"):
        return
    with _kb_lock:
        if _KB_STATUS in ("ready", "partial", "failed"):  # double-check after wait
            return
        _load_kb()


def _kb_check(needs_semantic: bool = False) -> Optional[Dict[str, Any]]:
    """Non-blocking KB readiness check for tool handlers.

    Returns None if the tool can proceed, or a structured error dict
    (status + actionable message) to return to the caller as-is.

    needs_semantic=True means the tool requires hybrid_search (semantic
    vector search) — the _SEMANTIC_TOOLS set (hybrid_search itself, plus
    register_component, whose ingest/reload needs the search adapter); every
    other KB tool only needs the knowledge_graph (graph-only).
    """
    if _KB_STATUS == "ready":
        return None
    if _KB_STATUS in ("pending", "warming"):
        return {
            "status": "kb_warming",
            "message": (
                "KB is still loading (~1–2 min after server start). "
                "Wait and retry; do NOT fall back to live introspection — "
                "the answer is in the KB."
            ),
            "retry_after_seconds": 30,
        }
    if _KB_STATUS == "partial":
        if not needs_semantic:
            return None  # graph-only tools still work
        return {
            "status": "kb_partial",
            "message": _KB_REASON,
            "actionable": True,
        }
    # failed
    return {
        "status": "kb_failed",
        "message": _KB_REASON or "KB unavailable; see server stderr.",
        "actionable": True,
    }


def _load_kb():
    """One-time KB + search construction. Always runs under _kb_lock.

    Sets _KB_STATUS to one of: ready | partial | failed. Sets _KB_REASON
    with an actionable message for partial/failed states so callers can
    surface a useful next step instead of a confusing AttributeError.
    """
    global knowledge_graph, hybrid_search, _KB_STATUS, _KB_REASON
    _KB_STATUS = "warming"
    # CRITICAL stdout-pollution guard: KB/search submodules
    # (UnifiedGraphQuery / UnifiedSearchAdapter / sentence-transformers /
    # chromadb) emit bare print() progress like "🔍 Loading ..." to stdout.
    # _ensure_kb() runs at RUNTIME on the first KB-dependent tool call —
    # AFTER main() restored the real stdout, which IS the MCP JSON-RPC
    # channel. Any such print corrupts the protocol and the client
    # ("... is not valid JSON" -> server disconnected). Force every byte of
    # this lazy load to stderr, then restore stdout for MCP responses.
    _saved_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        # --- pre-flight: check files exist before construction so we can give
        # actionable error messages instead of opaque construction failures ---
        if not enhanced_graph_path.exists():
            _KB_STATUS = "failed"
            _KB_REASON = (
                f"Knowledge graph file not found at {enhanced_graph_path}. "
                f"Fix: run `python scripts/fetch_vector_db.py` from the repo "
                f"root, then restart the MCP server."
            )
            print(f"WARNING: {_KB_REASON}", file=sys.stderr)
            return
        if not graphrag_json_path.exists():
            # graphrag.json is OPTIONAL, not a boot blocker. UnifiedGraphQuery wraps
            # its load in try/except and runs ENRICHED-ONLY (operators.json supersedes
            # the wiki dump for params/identity). The v0.2 KB ships WITHOUT the ~58MB
            # graphrag.json, so a fresh install must still boot — warn and continue.
            # (The gpickle check above stays fatal: the enhanced graph IS required.)
            print(
                f"INFO: graphrag.json not found at {graphrag_json_path}; running "
                f"enriched-only (operators.json). Expected for a v0.2 KB bundle.",
                file=sys.stderr,
            )

        # --- load knowledge_graph (required) ---
        try:
            print("Loading unified knowledge graph (wiki + examples)", file=sys.stderr)
            knowledge_graph = UnifiedGraphQuery(
                graphrag_json_path=str(graphrag_json_path),
                enhanced_graph_path=str(enhanced_graph_path),
                enriched_wiki_path=str(enriched_wiki_path),
            )
            print(f"Loaded unified TD knowledge graph with {len(knowledge_graph.nodes)} nodes", file=sys.stderr)
        except Exception as e:
            _KB_STATUS = "failed"
            _KB_REASON = (
                f"Knowledge graph init error: {e}. "
                f"Check server stderr for the full traceback. "
                f"Common causes: corrupt gpickle file, mismatched Python version, "
                f"missing networkx/numpy. Try reinstalling: `pip install -e \".[api,dev]\"`."
            )
            print(f"WARNING: {_KB_REASON}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return

        # --- load hybrid_search (optional — degrade to partial, not failed) ---
        if not vectordb_path.exists():
            _KB_STATUS = "partial"
            _KB_REASON = (
                f"Semantic search unavailable: vector DB missing at "
                f"{vectordb_path}. Graph tools still work. "
                f"Fix: `python scripts/fetch_vector_db.py` then restart the MCP server."
            )
            print(f"WARNING: {_KB_REASON}", file=sys.stderr)
            return
        try:
            hybrid_search = UnifiedSearchAdapter(
                graph_path=str(enhanced_graph_path),
                vectordb_path=str(vectordb_path),
                use_legacy=False,
                # W7: auto-on user-component search on the live server (a no-op
                # until the first register_component commit creates the store).
                # Every eval/gate adapter passes user_search=False explicitly.
                user_search=True,
            )
            print("Loaded unified search", file=sys.stderr)
            _KB_STATUS = "ready"
            _KB_REASON = ""
        except Exception as e:
            _KB_STATUS = "partial"
            _KB_REASON = (
                f"Semantic search init error: {e}. Graph tools still work. "
                f"Check server stderr for the full traceback."
            )
            print(f"WARNING: {_KB_REASON}", file=sys.stderr)
            import traceback
            traceback.print_exc()
    finally:
        sys.stdout = _saved_stdout

# D2 (harness item 3b): the single-sourced non-negotiables are passed as the
# server's always-on `instructions=` channel (delivered verbatim on Claude Code /
# cowork; see docs/NON_NEGOTIABLES.md). SCOPE FOLLOWS TOOLS SERVED: this offline
# `td-builder` server serves no live tools (TD_LIVE_ENABLED is pinned off — the 22
# live tools live only on td-builder-live), so scope_for_server() resolves to the
# offline scope ([always] rules only). The helper stays the single scope-follows-
# tools source: a server that DID serve the live tools would ship the live scope,
# incl. the catastrophic-silent rules (GLSL-invisible, next-frame-reads). The
# loader fails soft to a baked-in minimal string, so a partial install still starts.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # MCP/ (for server_instructions)
from server_instructions import load_instructions, scope_for_server  # noqa: E402
# D4 feedback spine (opt-in, local-only). Pure module; a cheap no-op when the flag
# is off. MCP/ is on sys.path (inserted just above), same as server_instructions.
from feedback import feedback_recorded  # noqa: E402

# TD_LIVE_ENABLED is pinned False on this offline server (co-load removed), so this
# always resolves to scope_for_server(False) -> "offline". The True branch is
# production-unreachable here by design but retained as canary-tested defensive code
# (test_scope_follows_tools_served) for any future live-serving server.
_NON_NEGOTIABLES = load_instructions(
    _RELEASE_ROOT, scope=scope_for_server(bool(TD_LIVE_ENABLED and TD_LIVE_TOOLS)))
app = Server("touchdesigner-mcp-server", instructions=_NON_NEGOTIABLES)

SERVER_NAME = "touchdesigner-mcp-server"
SERVER_VERSION = "0.2.0"

# Server <-> KB version-compat check (Wave 5). Computed here because it needs both
# SERVER_VERSION (just defined) and the KB manifest version/td_build (loaded above).
# WARN-not-fail: a version-mismatched KB still boots (degraded). Policy + semver-minor
# comparison live in compat.py; the result is surfaced in get_server_info.compat.
from compat import compat_status as _compat_status  # noqa: E402
_COMPAT = _compat_status(SERVER_VERSION, _KB_MANIFEST_VERSION, _KB_TD_BUILD)
if _COMPAT["compatible"] is False:
    print(f"WARNING: KB/server version mismatch - server {SERVER_VERSION} vs "
          f"KB {_KB_MANIFEST_VERSION}. Running degraded; rebuild or refetch a matching KB "
          f"(get_server_info.compat has details).", file=sys.stderr)

# Tools that need the heavy knowledge graph / vector search. Only these
# trigger the one-time _ensure_kb() lazy load; everything else (get_server_info,
# live-TD, validate/convert/build, spawn_*, expert prompts) stays instant.
_KB_DEPENDENT_TOOLS = {
    "hybrid_search", "get_operator_info", "query_graph", "list_pop_operators",
    "find_operator_examples", "find_operator_combination", "find_parameter_usage",
    "find_similar_networks", "get_parameter_detail", "get_network_patterns",
    "register_component",
}

# Tools that require the SEMANTIC half (hybrid vector search), not just the
# knowledge graph: a partial-KB install must return the structured `kb_partial`
# envelope for these instead of an unstructured crash (W7 #31/#43).
_SEMANTIC_TOOLS = {"hybrid_search", "register_component"}


def _build_menu_options(param: Dict[str, Any]) -> List[Dict[str, str]]:
    """Zip menuNames + menuLabels into [{code, label}, ...] for menu parameters.

    The enriched wiki stores menu choices as two parallel arrays — menuNames
    (the code used in .par files and Python) and menuLabels (the human-facing
    display label). Returns [] if neither field is populated. Falls back to a
    legacy `options` field if some record uses that shape.
    """
    names = param.get("menuNames") or []
    labels = param.get("menuLabels") or []
    if not names and not labels:
        legacy = param.get("options") or []
        return legacy if isinstance(legacy, list) else []
    n = max(len(names), len(labels))
    return [
        {
            "code":  names[i]  if i < len(names)  else (labels[i] if i < len(labels) else ""),
            "label": labels[i] if i < len(labels) else (names[i]  if i < len(names)  else ""),
        }
        for i in range(n)
    ]


_COMPOUND_LEAF_LETTER_SUFFIXES = ("x", "y", "z", "w", "r", "g", "b", "a")


def _strip_compound_leaf_suffix(name: str):
    """Return the candidate compound-parent code for a leaf-looking miss, or None.

    Only strips ONE trailing letter-suffix (x/y/z/w/r/g/b/a) or a trailing digit run
    (1-4), and only if >=2 chars remain, so short/ambiguous codes are left alone. Used
    ONLY as a fallback after an exact-match miss (get_parameter_detail), so it can never
    regress a currently-working lookup.
    """
    if not name or len(name) < 3:
        return None
    if name[-1] in _COMPOUND_LEAF_LETTER_SUFFIXES:
        return name[:-1]
    stripped = name.rstrip("1234")
    if stripped != name and len(stripped) >= 2:
        return stripped
    return None


# W-C — param family collapse (applied BEFORE the hydration cap). TD serializes a
# transform as the tuplet codes t/r/s/p (+ a uniform ``scale``); some ops/pages use
# the split tx/ty/tz form. Either way, folding them — and other standard component
# triplets/quads (xyz / rgba) and the boilerplate Common page — into ONE
# self-describing entry each means the ``cap`` slots carry DISTINGUISHING params
# instead of 13 near-identical transform components. True counts are never touched.
_TRANSFORM_MEMBERS = {
    "t", "r", "s", "p", "scale",                       # tuplet form (TD ground truth)
    "tx", "ty", "tz", "rx", "ry", "rz",                # split form (some wiki/pages)
    "sx", "sy", "sz", "px", "py", "pz",
}
_TRANSFORM_LABEL = "3D transform (t/r/s/p, scale)"
_XYZ_SUFFIXES = ("x", "y", "z", "w")
_RGBA_SUFFIXES = ("r", "g", "b", "a")
_COMMON_LABEL = "Common page params"

# W-C addendum — TD sequence-block params: <prefix><N><suffix>, e.g. GLSL uniform
# blocks (vec0name/vec0type/vec0valuex..w, vec1...), Attribute POP (att0name/
# att0val), Constant CHOP (name0/value0/name1...), Dimension POP (dim0num),
# multi-input refs (input0pop/input1pop). One generic rule folds a whole sequence
# into a single reconstructible entry instead of N*fields hydration slots.
_SEQ_RE = re.compile(r"^([a-z]{2,}?)(\d+)([a-z0-9]*)$")


def _sequence_label(prefix: str, idxs: list, sufs: list) -> str:
    """Compact, reconstructible label for a sequence block, e.g.
    ``vec[0-15]{name,type,valuex,valuey,valuez,valuew}`` or ``name[0-3]``."""
    lo, hi = min(idxs), max(idxs)
    rng = f"[{lo}]" if lo == hi else f"[{lo}-{hi}]"
    fields = [s for s in sufs if s]
    shown = ",".join(fields[:8]) + (f",+{len(fields) - 8} more" if len(fields) > 8 else "")
    return f"{prefix}{rng}" + (f"{{{shown}}}" if fields else "")


def _collapsed_descriptor(label: str, members: list) -> dict:
    """A self-describing stand-in for a collapsed param family — lists the member
    codes so nothing is hidden (the caller can still get_parameter_detail any one).
    Big sequence blocks list a bounded sample: the label already encodes the full
    prefix/index-range/field pattern, so every member code is reconstructible."""
    d = {
        "collapsed_family": label,
        "member_count": len(members),
        "note": (
            f"{len(members)} related params folded into one entry to conserve "
            f"hydration slots; call get_parameter_detail for any member."
        ),
    }
    if len(members) <= 12:
        d["members"] = list(members)
    else:
        d["members_sample"] = list(members[:6])
    return d


def _collapse_param_families(items: list) -> list:
    """Collapse known parameter families in an ordered ``[(code, value), ...]`` list.

    Groups (priority order, each code joins at most one): the 3D transform tuplet/
    split set + uniform scale; sequence blocks ``<prefix><N><suffix>`` (GLSL uniform
    vec-blocks, att0name/att0val, name0/value0, input0pop, ...); generic component
    triplets/quads (``<base>{x,y,z,w}`` and colorish ``<base>{r,g,b,a}`` with r+g+b
    present); and — last, over whatever is left — params on the Common page. A group
    must have >=2 members to collapse (folding one adds no value). Order is
    preserved; each collapsed group is emitted at its first member's position.
    Returns the input unchanged when nothing groups.
    """
    items = list(items)
    codes = [c for c, _ in items]
    lower = {c: str(c).lower() for c in codes}

    assigned: dict = {}            # code -> group label
    members_by_group: dict = {}    # group label -> [codes in order]
    seq_labels: set = set()        # labels that are TD sequence blocks

    # 1. Transform tuplet/split + uniform scale (fold only with >=2 members AND at
    #    least one real t/r/s/p component, so a lone "scale" is never swallowed).
    transform = [c for c in codes if lower[c] in _TRANSFORM_MEMBERS]
    real = [c for c in transform if lower[c] != "scale"]
    if len(transform) >= 2 and len(real) >= 1:
        for c in transform:
            assigned[c] = _TRANSFORM_LABEL
        members_by_group[_TRANSFORM_LABEL] = transform

    # 2. Sequence blocks (<prefix><N><suffix>) — runs BEFORE the xyz/rgba buckets so
    #    vec0valuex folds into the vec-block, not a spurious "vec0value (xyz)" group.
    #    A prefix qualifies with >=2 distinct indices (a real sequence) OR one index
    #    but >=2 field suffixes (wiki pages often document only block 0, e.g.
    #    att0name/att0val). A lone indexed code never folds.
    seq_buckets: dict = {}
    for c in codes:
        if c in assigned:
            continue
        m = _SEQ_RE.match(lower[c])
        if m:
            prefix, idx, suf = m.group(1), int(m.group(2)), m.group(3)
            seq_buckets.setdefault(prefix, []).append((c, idx, suf))
    for prefix, entries in seq_buckets.items():
        idxs = sorted({idx for _, idx, _ in entries})
        sufs = []
        for _, _, s in entries:
            if s not in sufs:
                sufs.append(s)
        if len(entries) < 2 or (len(idxs) < 2 and len(sufs) < 2):
            continue
        label = _sequence_label(prefix, idxs, sufs)
        group = [c for c, _, _ in entries]
        for c in group:
            assigned[c] = label
        members_by_group[label] = group
        seq_labels.add(label)

    # 3. Generic component groups by <base><suffix>.
    xyz_buckets: dict = {}
    rgba_buckets: dict = {}
    for c in codes:
        if c in assigned:
            continue
        cl = lower[c]
        if len(cl) < 2:
            continue
        base, suf = cl[:-1], cl[-1]
        if suf in _XYZ_SUFFIXES:
            xyz_buckets.setdefault(base, []).append(c)
        elif suf in _RGBA_SUFFIXES:
            rgba_buckets.setdefault(base, []).append(c)
    for base, group in xyz_buckets.items():
        if len(group) >= 2:
            present = {lower[c][-1] for c in group}
            label = f"{base} ({''.join(s for s in _XYZ_SUFFIXES if s in present)})"
            for c in group:
                assigned[c] = label
            members_by_group[label] = group
    for base, group in rgba_buckets.items():
        sufs = {lower[c][-1] for c in group}
        if len(group) >= 2 and {"r", "g", "b"} <= sufs:   # require a real color (r+g+b)
            label = f"{base} ({''.join(s for s in _RGBA_SUFFIXES if s in sufs)})"
            for c in group:
                assigned[c] = label
            members_by_group[label] = group

    # 4. Common-page params (optional): fold the boilerplate common page into one.
    common = []
    for c, v in items:
        if c in assigned:
            continue
        page = str(v.get("page") or "").strip().lower() if isinstance(v, dict) else ""
        if page == "common":
            common.append(c)
    if len(common) >= 2:
        for c in common:
            assigned[c] = _COMMON_LABEL
        members_by_group[_COMMON_LABEL] = common

    if not assigned:
        return items

    out = []
    emitted: set = set()
    for c, v in items:
        label = assigned.get(c)
        if label is None:
            out.append((c, v))
        elif label not in emitted:
            emitted.add(label)
            desc = _collapsed_descriptor(label, members_by_group[label])
            if label in seq_labels:
                desc["sequenced"] = True
                desc["note"] += (
                    " TD sequence block: the live op replicates these fields per"
                    " index (the wiki typically documents block 0 only)."
                )
            out.append((label, desc))
    return out


def _hydrate_hit_params(result: dict, full_info: dict, compact: bool,
                        cap: int = PARAM_HYDRATE_CAP) -> None:
    """Attach bounded parameter data from ``full_info`` onto a hybrid_search hit.

    Always stamps the TRUE counts (``parameter_count``/``ground_truth_param_count``)
    and ``parameter_names`` — the full post-collapse name list (plain codes literally,
    families/sequences as reconstructible labels) so every param is visible in BOTH
    modes. ``compact=True`` omits the (large) per-hit ``parameters`` dict entirely;
    otherwise known param families are collapsed (W-C) and the result is capped to
    ``cap`` items, with ``parameters_capped`` flagging any POST-collapse truncation.
    Mutates ``result`` in place. No-op when ``full_info`` carries no ``wiki_parameters``.
    """
    if not full_info or 'wiki_parameters' not in full_info:
        return
    wiki_params = full_info['wiki_parameters']
    if isinstance(wiki_params, dict):
        items = list(wiki_params.items())
        full_count = len(items)
    elif isinstance(wiki_params, list):
        items = wiki_params
        full_count = len(items)
    else:
        return
    result['parameter_count'] = full_count
    if full_info.get('ground_truth_param_count'):
        result['ground_truth_param_count'] = full_info['ground_truth_param_count']
    # Collapse families BEFORE the cap so the slots carry distinguishing params. The
    # TRUE full_count above is left untouched; parameters_capped reflects whether the
    # post-collapse list was still longer than the cap (i.e. genuinely truncated).
    if isinstance(wiki_params, dict):
        pairs = items
    else:
        pairs = [
            ((p.get('name') or p.get('code') or str(i)) if isinstance(p, dict) else str(i), p)
            for i, p in enumerate(items)
        ]
    collapsed = _collapse_param_families(pairs)
    # W-C addendum: EVERY param name is visible pre-hydration, in BOTH modes — plain
    # codes literally, families/sequences as reconstructible labels (the cap below
    # only bounds the hydrated detail, never name visibility).
    result['parameter_names'] = [c for c, _ in collapsed]
    if compact:
        result.pop('parameters', None)
        return
    if isinstance(wiki_params, dict):
        result['parameters'] = dict(collapsed[:cap])
    else:
        result['parameters'] = [v for _, v in collapsed[:cap]]
    if len(collapsed) > cap:
        result['parameters_capped'] = True


def _find_param_code(wiki_params, code: str):
    """Exact, case-insensitive lookup of ``code`` in a wiki_parameters dict OR list.

    Returns the same ``param_detail`` dict shape get_parameter_detail serializes today,
    or None on a miss. Factors the previously-duplicated dict/list branches into one.
    """
    if not code:
        return None
    target = code.lower()

    def _detail(found_code, p):
        if isinstance(p, dict):
            return {
                "code": found_code,
                "name": p.get("display_name", found_code),
                "type": p.get("type", "unknown"),
                "description": p.get("description", "No description available"),
                "section": p.get("section", ""),
                "default": p.get("default"),
                "options": _build_menu_options(p),
                "range": p.get("range"),
            }
        return {"code": found_code, "value": str(p)}

    if isinstance(wiki_params, dict):
        for c, p in wiki_params.items():
            if c.lower() == target:
                return _detail(c, p)
    elif isinstance(wiki_params, list):
        for p in wiki_params:
            if isinstance(p, dict):
                c = p.get("code", p.get("name", ""))
                if c.lower() == target:
                    return _detail(c, p)
    return None


async def td_build_project(design: Dict, project_name: str = None, output_dir: str = None) -> Dict:
    """
    Build a TouchDesigner .tox file from a network design specification.

    Uses META_AGENTIC_TOOL's ToxBuilder with validated operator mappings.

    Args:
        design: Network design dict with:
            - operators: list of {name, type, position, parameters}
            - connections: list of {from, to}
            An operator may instead carry a 'palette' field naming a registered
            pre-built component (KB/palette_components.json) — it becomes an
            external-tox placeholder that loads from the user's own TD install.
            Unregistered .tox files: `external_tox: <path>`. The file is
            manifest-parsed at build time; a bare `{"from"/"to": "comp"}` wire
            auto-resolves only when the component has exactly ONE inner out/in
            op — otherwise name the inner op explicitly (`"comp/<outOp>"`);
            a component is never itself a data source. A wired comp whose .tox
            is missing/unreadable at build time fails the build with the reason.
        project_name: Optional project name (auto-generated if not provided)
        output_dir: Optional output directory (defaults to mcp_server/output)

    Returns:
        Dict with status, file path, and build details

    Example design:
        {
            "operators": [
                {"name": "noise1", "type": "noiseTOP", "position": [0, 0], "parameters": {"type": "random"}},
                {"name": "level1", "type": "levelTOP", "position": [200, 0], "parameters": {"opacity": 0.8}}
            ],
            "connections": [{"from": "noise1", "to": "level1"}]
        }
    """
    if not EXPERT_WORKFLOW_ENABLED:
        return {
            "status": "ERROR",
            "message": "META_AGENTIC_TOOL not available - ToxBuilder cannot be used"
        }

    try:
        import time
        import gzip

        # Generate project name if not provided
        if not project_name:
            project_name = f"td_project_{int(time.time()) % 10000}"

        # Set output directory
        if not output_dir:
            output_dir = str(Path(__file__).parent / "output")

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        print(f"Building project: {project_name}", file=sys.stderr)

        # Ensure design has required structure
        if not isinstance(design, dict):
            return {
                "status": "ERROR",
                "message": "design must be a dictionary with 'operators' and 'connections'"
            }

        # Palette components are per-OPERATOR fields ({"name": ..., "palette": "bloom"}),
        # not a design-level key. Single-sourced via _reject_design_level_palette so
        # this simple route and the advanced _run_build route stay identical.
        perr = _reject_design_level_palette(design)
        if perr:
            return perr

        if 'operators' not in design:
            design['operators'] = []
        if 'connections' not in design:
            design['connections'] = []
        if 'project' not in design:
            design['project'] = project_name

        # Build using ToxBuilder (for non-palette builds)
        builder = ToxBuilder(output_dir, verbose=True)
        tox_path = builder.build_tox(design, project_name)

        if tox_path and tox_path.exists():
            return {
                "status": "SUCCESS",
                "project_name": project_name,
                "output_file": str(tox_path),
                "file_size": tox_path.stat().st_size,
                "operators": len(design.get('operators', [])),
                "connections": len(design.get('connections', []))
            }
        else:
            return {
                "status": "ERROR",
                "message": "ToxBuilder did not produce output file"
            }

    except Exception as e:
        import traceback
        return {
            "status": "ERROR",
            "message": str(e),
            "traceback": traceback.format_exc()
        }


# ---------------------------------------------------------------------------
# Build core + async job registry (Round-3 Stream 3, R2-A)
# ---------------------------------------------------------------------------
# Shared by the synchronous td_build_project path and the opt-in async path. The background
# pattern mirrors the KB warm-up thread: a daemon thread, a lock, and a module-level state
# dict keyed by job id, polled via the td_build_status tool.
_build_jobs = {}            # job_id -> {status, result?/error?, started, finished?}
_build_lock = threading.Lock()


def _prune_build_jobs(limit=50):
    """Keep the registry bounded (oldest-first eviction). Call under _build_lock."""
    if len(_build_jobs) > limit:
        oldest = sorted(_build_jobs.items(), key=lambda kv: kv[1].get("started", 0))
        for jid, _ in oldest[:len(_build_jobs) - limit]:
            _build_jobs.pop(jid, None)


def _reject_design_level_palette(design_like) -> Optional[Dict]:
    """Design-level `palette` key is the old, invalid form — `palette` is a
    per-OPERATOR field. Return the identical ERROR envelope for either build route
    (single source, so the simple and advanced paths can't drift), else None.
    Top-level only, matching the simple path; per-operator `palette` inside
    operators/containers stays valid."""
    if isinstance(design_like, dict) and 'palette' in design_like:
        return {
            "status": "ERROR",
            "message": ("'palette' is a per-operator field, not a design-level key. "
                        "Use {\"operators\": [{\"name\": \"glow\", \"palette\": \"bloom\"}], ...} — "
                        "names come from KB/palette_components.json (277 registered components)."),
        }
    return None


async def _run_build(network_design, design, table_data, project_name, output_dir, mode) -> dict:
    """Build a .tox/.toe and return the result envelope dict (callers run B08 pre-validation
    first). network_design -> ToeBuilderBridge advanced path; otherwise the simple
    td_build_project() path. Same envelopes the tool returned before the refactor."""
    # BUG-1: a flat simple `design` requesting mode="toe" must reach ToeBuilderBridge, which
    # honors mode. The simple td_build_project() fallback below is tox-only and silently drops
    # `mode` -> a .toe request produced a .tox. Promote it to the advanced path (build_from_design
    # accepts a flat design); fold table_data in first so network.get("table_data") still sees it.
    if not network_design and mode == "toe" and design:
        network_design = dict(design)
        if table_data:
            network_design["table_data"] = table_data
    # Single guard path (W4a): reject a design-level `palette` key on EITHER route
    # (advanced network_design, simple design, or a promoted design) with the one
    # shared envelope, before any builder runs. The simple td_build_project() path
    # calls the same helper, so the two routes can't drift.
    perr = _reject_design_level_palette(network_design or design)
    if perr:
        return perr
    if network_design and EXPERT_WORKFLOW_ENABLED:
        try:
            if not output_dir:
                output_dir = str(Path(__file__).parent / "output")
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            if not project_name:
                project_name = f"td_project_{int(time.time()) % 10000}"
            if mode == "tox":
                bridge = ToxBuilder(output_dir, verbose=True)
                result_path = bridge.build_tox(network_design, project_name)
            else:
                bridge = ToeBuilderBridge(Path(output_dir))
                result_path = bridge.build_from_design(network_design, project_name)
            op_count = len(network_design.get("operators", []))
            conn_count = len(network_design.get("connections", []))
            for container in network_design.get("containers", []):
                op_count += len(container.get("operators", []))
                conn_count += len(container.get("connections", []))
                conn_count += len(container.get("network", {}).get("connections", []))
            if result_path and Path(result_path).exists():
                # BUG-1 (fail loud): never report SUCCESS with a different extension than the
                # requested mode. The branch above already picks the builder by mode, so this is
                # a belt-and-suspenders guard against a silent .tox-for-.toe (or vice versa).
                expected_ext = ".toe" if mode == "toe" else ".tox"
                if Path(result_path).suffix != expected_ext:
                    return {
                        "status": "ERROR",
                        "builder": "ToeBuilderBridge",
                        "message": (f"Builder produced {Path(result_path).suffix} but "
                                    f"mode={mode!r} requires {expected_ext}"),
                        "output_file": str(result_path),
                    }
                return {
                    "status": "SUCCESS",
                    "builder": "ToeBuilderBridge",
                    "output_file": str(result_path),
                    "file_size": Path(result_path).stat().st_size,
                    "operators": op_count,
                    "connections": conn_count,
                    "features_used": {
                        "containers": len(network_design.get("containers", [])) > 0,
                        "palette": any(
                            item.get("palette")
                            for item in (network_design.get("operators", [])
                                         + network_design.get("containers", []))
                        ) or any(
                            op.get("palette")
                            for container in network_design.get("containers", [])
                            for op in container.get("operators", [])
                        ),
                        "external_tox": any(
                            op.get("external_tox") or op.get("externaltox")
                            for op in (network_design.get("operators", [])
                                       + [op for container in network_design.get("containers", [])
                                          for op in container.get("operators", [])])
                        ),
                    },
                }
            return {
                "status": "ERROR",
                "builder": "ToeBuilderBridge",
                "message": "Build completed but file was not created",
                "attempted_path": str(result_path) if result_path else None,
            }
        except Exception as e:
            import traceback
            return {
                "status": "ERROR",
                "builder": "ToeBuilderBridge",
                "message": str(e),
                "traceback": traceback.format_exc(),
            }

    # Simple design path
    if table_data:
        design = dict(design)
        design["table_data"] = table_data
    result = await td_build_project(design, project_name, output_dir)
    # BUG-1 (fail loud): mode="toe" only reaches here in the degenerate case where promotion
    # above was skipped (falsy `design`). td_build_project is tox-only, so a SUCCESS here for a
    # .toe request would be a silent .tox — convert it to an explicit error instead.
    if mode == "toe" and result.get("status") == "SUCCESS" \
            and not str(result.get("output_file", "")).endswith(".toe"):
        return {
            "status": "ERROR",
            "message": ("mode='toe' requested but the simple builder produced a .tox — "
                        "provide a design with operators."),
            "output_file": result.get("output_file", ""),
        }
    return result


def _start_build_job(network_design, design, table_data, project_name, output_dir, mode) -> str:
    """Spawn a daemon thread that runs _run_build and records the result in _build_jobs.
    Returns the new job id immediately (poll with td_build_status)."""
    job_id = uuid.uuid4().hex[:12]
    with _build_lock:
        _build_jobs[job_id] = {"status": "running", "started": time.time()}
        _prune_build_jobs()

    def _worker():
        try:
            res = asyncio.run(_run_build(network_design, design, table_data,
                                         project_name, output_dir, mode))
            with _build_lock:
                if job_id in _build_jobs:
                    _build_jobs[job_id].update({"status": "done", "result": res,
                                                "finished": time.time()})
        except Exception as e:  # noqa: BLE001
            import traceback
            with _build_lock:
                if job_id in _build_jobs:
                    _build_jobs[job_id].update({"status": "error", "error": str(e),
                                                "traceback": traceback.format_exc(),
                                                "finished": time.time()})

    threading.Thread(target=_worker, name=f"build-{job_id}", daemon=True).start()
    return job_id


# MCP risk annotations (W4b, audit cluster C3). These are the machine-readable tiers
# the client's approval layer gates on — the prerequisite for D3 live-authorization
# tiering. Owner-decided: ship only the three named hints (openWorldHint omitted).
# destructiveHint/idempotentHint are meaningful only when readOnlyHint is false.
#   READ_ONLY      — no environment change (all KB lookup / validate / convert / expand
#                    / status tools; expand only writes a temp dir it cleans up).
#   WRITE_ADDITIVE — creates a file/artifact, never the live graph (td_build_project).
#                    idempotentHint=False: re-running a build can mint new outputs.
#   WRITE_ADDITIVE_IDEMPOTENT — same additive class, but the write is a delete-then-
#                    upsert against stable name-keyed targets, so re-running it has
#                    the same effect (register_component: user registry + user Chroma
#                    + manifest + optional palette copy). Honest idempotentHint=True,
#                    per the owner-approved D3 precedent (the live save tool shipped
#                    the analogous honest-True hints as its own WRITE_CHECKPOINT
#                    class — a checkpoint OVERWRITE of a stable target, live-side;
#                    this constant is the offline additive-upsert counterpart, a
#                    separate name because the offline vocabulary is test-pinned).
#   (No DESTRUCTIVE tools on this offline server — all live-graph mutation and
#    arbitrary-exec tools are on the separate td-builder-live surface.)
# Shared singletons — never mutated. See docs/TOOL_RISK_ANNOTATIONS.md.
READ_ONLY = ToolAnnotations(readOnlyHint=True)
WRITE_ADDITIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False
)
WRITE_ADDITIVE_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True
)


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools"""

    tools = [
        Tool(
            annotations=READ_ONLY,
            name="hybrid_search",
            description="Search TouchDesigner documentation using semantic search + knowledge graph. Returns relevant operators, parameters, concepts with relationships.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language question about TouchDesigner"
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5)",
                        "default": 5
                    },
                    "compact": {
                        "type": "boolean",
                        "description": "If true, omit per-hit parameter dicts (keep the true counts) to save context. Default: false, which caps each hit's parameters to a small number.",
                        "default": False
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="get_operator_info",
            description="Get info about a TouchDesigner operator. Use compact=true to save context (returns name, family, type, summary).",
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_name": {
                        "type": "string",
                        "description": "Name of the operator (e.g., 'Grid SOP', 'Audio File In CHOP')"
                    },
                    "compact": {
                        "type": "boolean",
                        "description": "If true, returns minimal info to save context. Default: false",
                        "default": False
                    }
                },
                "required": ["operator_name"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="query_graph",
            description="Query TouchDesigner knowledge graph. Use compact=true for 'family' queries to get just names (saves ~700K context).",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["params", "related", "family"],
                        "description": "Type of query: 'params' (operator parameters), 'related' (related operators), 'family' (operators in family)"
                    },
                    "operator": {
                        "type": "string",
                        "description": "Operator name (required for 'params' and 'related')"
                    },
                    "family": {
                        "type": "string",
                        "description": "Operator family (required for 'family' command): SOP, CHOP, TOP, DAT, COMP, MAT, POP"
                    },
                    "compact": {
                        "type": "boolean",
                        "description": "If true, returns only names for 'family' queries. Default: false",
                        "default": False
                    }
                },
                "required": ["command"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="list_pop_operators",
            description="List all POP (Point) operators available in TouchDesigner",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="find_operator_examples",
            description=(
                "Find real example networks demonstrating how to use a specific operator. "
                "Returns parameter values, connections, and text explanations from working "
                "TouchDesigner examples.\n"
                "\n"
                "Disambiguation: pass `family='TOP'` (etc.), or use the colon-form "
                "('TOP:noise') / family-suffixed ('noiseTOP') / space-separated ('noise TOP') "
                "in `operator`.\n"
                "\n"
                "Response shape (Wave 5 W5.2):\n"
                "  - Single-family resolution (family supplied OR bare name matches one family) "
                "    → flat list of example dicts.\n"
                "  - Bare name matching MULTIPLE families → bucketed dict:\n"
                "      {_resolution: 'multi-family', _query: ..., _families: [...],\n"
                "       results_by_family: {CHOP: [...], TOP: [...], ...}}\n"
                "    Each bucket is capped at `limit`. Caller should pick a family or iterate "
                "    `results_by_family` explicitly."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operator": {
                        "type": "string",
                        "description": "Operator name. Bare ('noise'), colon-form ('TOP:noise'), suffixed ('noiseTOP'), or space-separated ('noise TOP'). Bare names matching multiple families return a per-family bucketed dict (W5.2)."
                    },
                    "family": {
                        "type": "string",
                        "enum": ["CHOP", "TOP", "SOP", "MAT", "DAT", "COMP", "POP"],
                        "description": "Optional family scope. Overrides any family inferred from `operator`. Supplying this forces single-family flat-list response."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of examples to return (default: 10). For bucketed multi-family responses, this is per-bucket.",
                        "default": 10
                    }
                },
                "required": ["operator"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="find_operator_combination",
            description=(
                "Find examples that use specific operator combinations. Useful for learning "
                "how operators work together (e.g., 'CHOP:noise + CHOP:analyze', "
                "'TOP:feedback + TOP:level').\n"
                "\n"
                "Wave 5 W5.1 — every entry in `operator_types` MUST encode a family scope. "
                "Bare names like 'constant' or 'noise' are rejected with a structured error "
                "(they previously matched across every family with the same name and could "
                "surface cross-family false-positives silently). Accepted forms:\n"
                "  TOP:constant   colon-form (family explicit)\n"
                "  constantTOP    suffix-form (family explicit)\n"
                "  constant TOP   space-separated wiki form\n"
                "  ALL:constant   explicit opt-in for cross-family matching\n"
                "\n"
                "On bare-name input you get back {error, rejected, accepted_forms, hint} — "
                "re-issue the call with one of the accepted forms."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of family-scoped operator types to find together. Each entry must be in one of: 'TOP:noise' (colon), 'noiseTOP' (suffix), 'noise TOP' (space), or 'ALL:noise' (opt-in any-family). Bare names like 'noise' are rejected."
                    },
                    "require_connection": {
                        "type": "boolean",
                        "description": "Whether operators must be connected (default: true)",
                        "default": True
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of examples to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["operator_types"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="find_parameter_usage",
            description="Find examples of parameter usage. Use compact=true to get just values (saves ~50K context).",
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_type": {
                        "type": "string",
                        "description": "Operator type (e.g., 'analyze', 'filter', 'noise')"
                    },
                    "parameter_name": {
                        "type": "string",
                        "description": "Parameter name (e.g., 'function', 'method', 'type')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of examples to return (default: 10)",
                        "default": 10
                    },
                    "compact": {
                        "type": "boolean",
                        "description": "If true, returns only unique values found. Default: false",
                        "default": False
                    }
                },
                "required": ["operator_type"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="find_similar_networks",
            description="Find examples with similar network patterns to a given example. Useful for finding alternative implementations or related techniques.",
            inputSchema={
                "type": "object",
                "properties": {
                    "example_id": {
                        "type": "string",
                        "description": "Example ID (e.g., 'analyzeCHOP/example1')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of similar examples to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["example_id"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="get_parameter_detail",
            description="Get full description and options for a specific parameter. Use after get_operator_info(compact=true) to drill down into specific params.",
            inputSchema={
                "type": "object",
                "properties": {
                    "operator_name": {
                        "type": "string",
                        "description": "Operator name (e.g., 'Noise CHOP', 'Level TOP')"
                    },
                    "parameter_name": {
                        "type": "string",
                        "description": "Parameter code name (e.g., 'amp', 'period', 'invert')"
                    }
                },
                "required": ["operator_name", "parameter_name"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="get_network_patterns",
            description="Get common network patterns found across TouchDesigner examples. Shows frequently-used operator combinations and connection patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "min_frequency": {
                        "type": "integer",
                        "description": "Minimum number of times pattern must appear (default: 5)",
                        "default": 5
                    }
                },
                "required": []
            }
        ),
        Tool(
            annotations=WRITE_ADDITIVE,
            name="td_build_project",
            description=(
                "Build a TouchDesigner project (.toe, mode='toe') or component (.tox, mode='tox') from a network design.\n"
                "Required args: `design` (or `network_design` for containers). "
                "Operators take `{name, type, family?, parameters?, uniforms?}`. "
                "Connections take `{from, to}`. Use `table_data` to populate Table DATs.\n"
                "Caveats:\n"
                "1. Disambiguate types that exist in multiple families: pass `family` "
                "(or use the colon-form `'CHOP:noise'` / suffix `'noiseCHOP'`). "
                "Common ambiguous types: noise, constant, null, analyze, level, math, "
                "transform, merge, blend, text.\n"
                "2. Look up operator-specific parameter values via `get_operator_info` "
                "or `find_parameter_usage` rather than guessing — invented types are "
                "now rejected (Wave 3 B08) so build will fail noisily if you fabricate one.\n"
                "3. Pre-built components: give an operator a `palette` field naming a "
                "registered component (e.g. {\"name\": \"glow\", \"palette\": \"bloom\"}) — "
                "it loads from the user's own TD install at open time, arrives fully wired "
                "(wire to/from it like any op; `\"from\": \"glow/out2\"` selects a second "
                "output), and exposes its real custom parameter pages. 277 Derivative "
                "palette items are registered in KB/palette_components.json; unknown names "
                "fail with the registered-name hint. For an unregistered .tox file use "
                "`external_tox` with a path instead (`embed_tox` is removed): the file is "
                "manifest-parsed at build time when it exists — a bare `{\"from\": \"comp\"}` "
                "wire auto-resolves only when the component has exactly one inner out/in op; "
                "otherwise name the inner op explicitly (`\"comp/<outOp>\"` / "
                "`\"comp/<inOp>\"`) — a component is never itself a data source. Wired comps "
                "with a missing/unreadable .tox fail the build with the reason; wrapper-style "
                ".toxes need `parameters.subcompname`.\n"
                "Non-negotiables (KB-first params, string menu tokens, place/save, relative "
                "paths): see docs/NON_NEGOTIABLES.md or the td-builder-howto skill."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "design": {
                        "type": "object",
                        "description": "Network design with 'operators', 'connections', and optional 'containers'. Operators have: name, type, family (optional), position (optional), parameters (optional), uniforms (for GLSL). Example: {\"operators\": [{\"name\": \"noise1\", \"type\": \"noise\", \"family\": \"CHOP\"}], \"connections\": [{\"from\": \"noise1\", \"to\": \"null1\"}]}"
                    },
                    "network_design": {
                        "type": "object",
                        "description": "Advanced network design with containers and hierarchical paths. Takes precedence over 'design' if both provided. Operators and containers may carry a 'palette' field naming a registered pre-built component, or 'external_tox' with a .tox path (see caveat 3: bare wires auto-resolve only single-connector comps — name inner ops explicitly otherwise); 'embed_tox' is removed."
                    },
                    "table_data": {
                        "type": "object",
                        "description": "Dict mapping Table DAT names to 2D arrays of cell values"
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Optional project name. Auto-generated if not provided."
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "Optional output directory. Defaults to mcp_server/output."
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["toe", "tox"],
                        "default": "tox",
                        "description": "Build mode: toe (project) or tox (component)"
                    },
                    "async_build": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, build in the background and return immediately with a job_id; poll td_build_status. Use for large builds that may exceed the client's tool-call timeout."
                    }
                },
                "required": []
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="td_build_status",
            description=(
                "Poll an async build started with td_build_project(async_build=true). "
                "Returns {status: running|done|error, result?/error?, elapsed}. Job ids are "
                "in-memory and not persisted across server restarts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "The job_id returned by td_build_project(async_build=true)."
                    }
                },
                "required": ["job_id"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="td_validate",
            description=(
                "Validate a TouchDesigner network JSON against the unified 5-stage validation pipeline. "
                "Returns validation report with errors, warnings, and suggestions. "
                "Stages: Schema -> Semantic -> Reference -> Logical -> TD Rules."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "network": {
                        "type": "object",
                        "description": "TD network JSON (builder or canonical format)"
                    },
                    "format_layer": {
                        "type": "string",
                        "enum": ["builder", "canonical"],
                        "default": "builder",
                        "description": "Input format layer"
                    },
                    "verbose": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include detailed validation stages"
                    }
                },
                "required": ["network"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="td_convert",
            description=(
                "Convert TouchDesigner network JSON between format layers. "
                "Supports: builder (AI-friendly) <-> canonical (compact). "
                "Conversion passes through the internal in-memory Extended representation "
                "(TDNetwork) as hub; 'extended' is not an importable/exportable JSON layer."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "network": {
                        "type": "object",
                        "description": "TD network JSON to convert"
                    },
                    "source_layer": {
                        "type": "string",
                        "enum": ["builder", "canonical"],
                        "description": "Source format layer"
                    },
                    "target_layer": {
                        "type": "string",
                        "enum": ["builder", "canonical"],
                        "description": "Target format layer"
                    }
                },
                "required": ["network", "source_layer", "target_layer"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="get_expert_prompt",
            description="Get the full prompt/instructions for a specialized TD expert. Use this before complex builds to get the expert's complete knowledge. Available experts: td_designer (network specs), network_builder (file generation), td_glsl_expert (shaders), td_python_expert (scripts), ui_expert (control panels), critic (review).",
            inputSchema={
                "type": "object",
                "properties": {
                    "expert_name": {
                        "type": "string",
                        "enum": ["td_designer", "network_builder", "td_glsl_expert", "td_python_expert", "ui_expert", "critic"],
                        "description": "Name of the expert to load"
                    },
                    "phase": {
                        "type": "string",
                        "enum": ["build", "plan", "self_improve"],
                        "default": "build",
                        "description": "Which phase prompt to load (build is most common)"
                    }
                },
                "required": ["expert_name"]
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="get_server_info",
            description="Return runtime identity of this MCP server: working directory, absolute script path, version, server name, Python version, and whether the live-TD client is enabled. Use this to confirm which copy/install of the server is actually running.",
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        ),
        Tool(
            annotations=READ_ONLY,
            name="expand_toe_file",
            description=(
                "Expand a TouchDesigner .toe/.tox file (via toeexpand.exe) and parse it OFFLINE. "
                "mode='summary' (default) returns each node's op_type plus its NON-DEFAULT parameters "
                "with value + mode (constant/expression/reference/bind), and the connection list — "
                "ideal for understanding/explaining an existing network. mode='full' returns the complete "
                "lossless JSON (operator positions + raw files + .toc) that round-trips back into a "
                ".toe.dir/.tox. Also accepts an already-expanded .toe.dir/.tox.dir (skips toeexpand)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "toe_path": {
                        "type": "string",
                        "description": "Absolute path to a .toe/.tox file, or to an already-expanded .toe.dir/.tox.dir."
                    },
                    "path": {
                        "type": "string",
                        "description": "Alias for toe_path."
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["summary", "full"],
                        "default": "summary",
                        "description": "summary = node/connection map with non-default params; full = complete round-trippable lossless JSON."
                    }
                },
                "required": []
            }
        ),
        Tool(
            annotations=WRITE_ADDITIVE_IDEMPOTENT,
            name="register_component",
            description=(
                "Register the user's own .tox component(s) so they become SEARCHABLE "
                "(hybrid_search) and BUILDABLE ({\"palette\": \"<name>\"}) exactly like "
                "Derivative palette components — single, several, or a whole directory.\n"
                "Two-step flow: 1) call with prepare=true — each .tox is parsed offline "
                "and you get back its interface skeleton (in/out ops, contained "
                "operators, custom parameters with defaults + menu tokens). 2) author a "
                "discriminating one-line `summary` (+ optional `use_cases` and one-line "
                "per-parameter `parameter_descriptions`) and call again with "
                "prepare=false to commit: the registry entry is written, the comp's "
                "2–3 search chunks are embedded incrementally into a separate user "
                "store (the shipped KB is never touched), and the result carries "
                "retrievable:true once the live search index has reloaded — same "
                "session, no restart. Commits re-parse the .tox (stateless; "
                "operator_count is echoed so a prepare/commit mismatch is visible).\n"
                "save_to_palette=true copies each .tox into "
                "<user palette>/<folder>/ and registers it palette-relative "
                "(source 'user'); existing files are refused unless overwrite=true, "
                "and a name that shadows a shipped Derivative palette component "
                "additionally requires confirm_shadow=true (shadowed builds resolve "
                "to YOUR component). Editing summary/use_cases/parameter descriptions "
                "in user_components.json afterwards requires a re-commit (or engine "
                "reindex_all) to reach search — the store flags stale entries loudly "
                "until then. On installs without the reranker bundle, user hits rank "
                "by scaled dense score (score_kind 'dense_fallback'). For large "
                "directories, batch ~10–20 comps per call — a 100-comp prepare "
                "payload plus 100 authored summaries risks context exhaustion."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "specs": {
                        "type": "array",
                        "description": (
                            "1..N component specs: {tox_path (required), name?, "
                            "source? ('project' default), category?, summary? "
                            "(required at commit), use_cases?: [str], "
                            "parameter_descriptions?: {parName: one-liner}}."
                        ),
                        "items": {"type": "object"}
                    },
                    "directory": {
                        "type": "string",
                        "description": "Alternative to specs: expand to one spec per *.tox in this directory."
                    },
                    "prepare": {
                        "type": "boolean",
                        "default": False,
                        "description": "true = parse only and return skeletons for authoring; false = commit (requires summary per spec)."
                    },
                    "save_to_palette": {
                        "type": "boolean",
                        "default": False,
                        "description": "Copy each .tox into <user palette>/<folder>/ and register it palette-relative (source 'user')."
                    },
                    "folder": {
                        "type": "string",
                        "default": "TD_Builder",
                        "description": "Palette subfolder for save_to_palette (bare name, no separators)."
                    },
                    "overwrite": {
                        "type": "boolean",
                        "default": False,
                        "description": "Allow save_to_palette to replace an existing .tox (reported as 'replaced')."
                    },
                    "confirm_shadow": {
                        "type": "boolean",
                        "default": False,
                        "description": "Required for save_to_palette adds whose name shadows a shipped Derivative palette component."
                    }
                },
                "required": []
            }
        )
    ]

    # The 22 live-TD tools are served by the separate td-builder-live server, never
    # co-loaded here — this offline server's surface is a fixed 18 (see the pinned-off
    # TD_LIVE_* constants at module top).
    return tools


# TD parameter modes (the integer stored in a .parm line; see lossless_parser
# _parse_parameters). 0=constant, 1=expression, 2=export/reference, 3=bind.
_TD_PARM_MODE = {0: "constant", 1: "expression", 2: "reference", 3: "bind"}

_SEQ_PARAM_RE = re.compile(r"^(\D*?)(\d+)(.*)$")

# toeexpand hang-guard (Round-3 Stream 2). Generous: the MCP client's own ~45s tool-call
# timeout may fire first — this only stops a genuinely stuck toeexpand from blocking forever.
EXPAND_TIMEOUT_S = 180

# Cross-project reference lint (Round-3 Stream 2). _OP_REF_RE matches an op('/abs/path')
# expression; _WHOLE_ABS_RE matches a param whose entire value is an absolute TD path. A ref
# whose first path segment != the component root is "foreign" (e.g. a dormant /project1/...
# reference that shipped inside a saved .tox).
_OP_REF_RE = re.compile(r"""op\(\s*['"](/[^'"]+)['"]""")
_WHOLE_ABS_RE = re.compile(r"^/[A-Za-z_]\w*(?:/[A-Za-z_.\w]+)*$")


def _scan_foreign_refs(network):
    """Flag cross-project references that leave the component root (Round-3 Stream 2).

    Scans each operator's param values + expressions for `op('/abs/path')` refs and for param
    values that are themselves an absolute TD path; a ref whose first segment !=
    `network.metadata.project_name` is foreign. Conservative (only clear op() refs /
    whole-value absolute paths) to avoid false positives. Returns [{path, param, ref}], empty
    when clean."""
    from core.models import ParameterValue
    root = (getattr(network.metadata, "project_name", "") or "").strip("/")
    found = []
    for op in network.operators:
        for pname, pval in (getattr(op, "parameters", None) or {}).items():
            value_str = None
            expr_str = None
            if isinstance(pval, ParameterValue):
                if isinstance(pval.value, str):
                    value_str = pval.value
                expr_str = pval.expression
            elif isinstance(pval, str):
                value_str = pval
            refs = []
            if expr_str:
                refs += _OP_REF_RE.findall(expr_str)
            if value_str:
                refs += _OP_REF_RE.findall(value_str)
                if _WHOLE_ABS_RE.match(value_str.strip()):
                    refs.append(value_str.strip())
            for ref in dict.fromkeys(refs):  # dedupe, preserve order
                first = ref.lstrip("/").split("/")[0]
                if root and first and first != root:
                    found.append({"path": op.path, "param": pname, "ref": ref})
    return found


def _collapse_seq_params(params, family_threshold: int = 2, keep_per_family: int = 1):
    """Collapse long repeated TD sequence-param families in a summary.

    TD sequence params look like ``attr0name, attr1name, …`` / ``vec0name, vec1name, …`` /
    ``sampler0extendu, …`` — a glslPOP's Create-Attributes + Vectors pages alone can emit
    dozens of rows, which blew the expand_toe_file(mode='summary') token budget. This keeps
    the first ``keep_per_family`` index of each family and replaces the rest with an
    explicit marker ``{name, collapsed: <count>, note}``. Families with
    ``<= family_threshold`` members (e.g. fromrange1/2) and non-sequence params pass through
    untouched. The omitted count is always reported — never a silent truncation.
    """
    buckets = {}      # family -> [(idx, param)], first-appearance order preserved via `rendered`
    rendered = []     # ("plain", param) | ("seq", family)
    for p in params:
        m = _SEQ_PARAM_RE.match(p.get("name", ""))
        if not m:
            rendered.append(("plain", p))
            continue
        family = f"{m.group(1)}#{m.group(3)}"
        if family not in buckets:
            buckets[family] = []
            rendered.append(("seq", family))
        buckets[family].append((int(m.group(2)), p))

    out = []
    for kind, val in rendered:
        if kind == "plain":
            out.append(val)
            continue
        members = sorted(buckets[val], key=lambda t: t[0])
        if len(members) <= family_threshold:
            out.extend(p for _, p in members)
        else:
            out.extend(p for _, p in members[:keep_per_family])
            omitted = len(members) - keep_per_family
            out.append({
                "name": val,
                "collapsed": omitted,
                "note": f"{omitted} repeated sequence params omitted in summary; use mode='full'",
            })
    return out


# Component interface manifest (Round-4 #1b): moved to engine/core/component_manifest.py
# so the offline builder can manifest-parse external_tox components at build time (BUG-3)
# without a circular import (this module imports ToeBuilderBridge). Re-exported under the
# original name — tests and the harvest script read `_component_manifest` off this module.
from core.component_manifest import component_manifest as _component_manifest  # noqa: E402


def _summarize_td_network(network) -> dict:
    """Compact node/connection summary of a parsed TDNetwork.

    Lists each operator's op_type ("FAMILY:type") and only its NON-DEFAULT
    parameters (TouchDesigner writes only changed params to .parm), each with
    its value and mode (constant/expression/reference/bind).
    """
    from core.models import ParameterValue

    operators = []
    for op in network.operators:
        params = []
        for pname, pval in (op.parameters or {}).items():
            if isinstance(pval, ParameterValue):
                label = _TD_PARM_MODE.get(
                    pval.td_mode, "expression" if pval.expression else "constant"
                )
                value = pval.value if label == "constant" else (
                    pval.expression if pval.expression is not None else pval.value
                )
            else:
                label, value = "constant", pval
            params.append({"name": pname, "value": value, "mode": label})
        operators.append({
            "path": op.path,
            "op_type": op.op_type or (f"{op.family.value}:{op.type}" if op.family else op.type),
            "params": _collapse_seq_params(params),
        })

    connections = [
        {"from": c.source, "to": c.target,
         "source_output": c.source_output, "target_input": c.target_input}
        for c in network.connections
    ]
    by_family = network.statistics.by_family if (network.statistics and network.statistics.by_family) else {}
    return {
        "project_name": network.metadata.project_name,
        "mode": network.metadata.mode,
        "node_count": len(network.operators),
        "connection_count": len(network.connections),
        "by_family": by_family,
        "operators": operators,
        "connections": connections,
        "foreign_refs": _scan_foreign_refs(network),
        "manifest": _component_manifest(network),
    }


def _feedback_tool_names():
    """The registered tool-name inventory, for the feedback identity hash. Resolved
    ONCE at import: asyncio.run is safe here because decoration runs during import,
    before the server's event loop exists. Fail-soft to () (hash simply omitted)."""
    try:
        import asyncio as _asyncio
        return tuple(sorted(t.name for t in _asyncio.run(list_tools())))
    except Exception:
        return ()


@app.call_tool()
@feedback_recorded(
    server="td-builder",
    server_version=SERVER_VERSION,
    kb_root=_KB_ROOT,
    instructions_text=_NON_NEGOTIABLES,
    tool_names=_feedback_tool_names(),
)
async def call_tool(name: str, arguments: dict) -> Sequence[Union[TextContent, ImageContent]]:
    """Handle tool calls"""
    
    try:
        # Non-blocking KB readiness check for KB-dependent tools.
        # If the background warmup hasn't finished yet, return a structured
        # "kb_warming" response so the caller can wait and retry instead of
        # blocking the MCP request and hitting the client timeout.
        # If the KB partially or fully failed to load (missing files, missing
        # deps, init exception), return a structured error naming the fix.
        if name in _KB_DEPENDENT_TOOLS:
            kb_err = _kb_check(needs_semantic=(name in _SEMANTIC_TOOLS))
            if kb_err is not None:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "ok": False,
                        "data": None,
                        "error": kb_err,
                        "meta": {"tool": name, "server": SERVER_NAME},
                    }, indent=2),
                )]

        if name == "hybrid_search":
            query = arguments["query"]
            n_results = arguments.get("n_results", 5)
            compact = arguments.get("compact", False)

            if not hybrid_search:
                return [TextContent(type="text", text="ERROR: Hybrid search not initialized")]

            results = hybrid_search.search(query, n_results=n_results)

            # Enrich results with full parameter data from knowledge_graph.
            # hybrid_search.search() returns a dict {query, semantic_results, relationships, ...};
            # the list of per-document hits lives under 'semantic_results', and the operator name
            # lives in each hit's 'metadata' dict.
            #
            # Hydration is bounded so a multi-hit envelope cannot blow up UNDER the reactive
            # HYBRID_SEARCH_MAX_BYTES cap: compact=true omits the parameter dicts entirely;
            # otherwise each hit's dict is capped to PARAM_HYDRATE_CAP items. In BOTH modes
            # the true full counts (parameter_count/ground_truth_param_count) are preserved.
            if knowledge_graph and isinstance(results, dict):
                for result in results.get('semantic_results', []):
                    if not isinstance(result, dict):
                        continue
                    meta = result.get('metadata') if isinstance(result.get('metadata'), dict) else {}
                    op_name = meta.get('operator_name') or result.get('operator_name') or result.get('name')
                    if op_name:
                        try:
                            full_info = knowledge_graph.get_operator_info(op_name)
                            _hydrate_hit_params(result, full_info, compact)
                        except Exception:
                            pass

            # Output budget (W4b): if the enriched envelope is oversized, shed the
            # per-result parameter lists and add a non-error `_truncation` signal.
            # semantic_results is preserved (test_p03); scorer envelope stays ok.
            if isinstance(results, dict):
                results, _ = budget_hybrid_results(results)

            return [TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )]

        elif name == "register_component":
            # F2 stdout protocol invariant: this is the only tool that runs the
            # heavy ingest machinery (chromadb + sentence-transformers via the
            # user-components engine, then reload_user_store) MID-SESSION —
            # after main() restored the real stdout, which IS the JSON-RPC
            # channel. One bare print() from those libraries corrupts the
            # protocol and disconnects the client, so the ENTIRE handler body
            # runs under the same stdout->stderr swap _load_kb uses (~:390).
            _saved_stdout = sys.stdout
            sys.stdout = sys.stderr
            try:
                # Engine: kb_build/user_components.py, loaded by FILE path relative to
                # this module (the engine ships with the code; it self-bootstraps its
                # own sys.path). Lazy + memoized — never imported at server boot.
                import importlib.util
                eng = sys.modules.get("td_user_components_engine")
                if eng is None:
                    eng_path = Path(__file__).resolve().parents[2] / "kb_build" / "user_components.py"
                    spec = importlib.util.spec_from_file_location(
                        "td_user_components_engine", str(eng_path))
                    eng = importlib.util.module_from_spec(spec)
                    sys.modules["td_user_components_engine"] = eng
                    spec.loader.exec_module(eng)

                def _reg_err(kind, message):
                    return [TextContent(type="text", text=json.dumps({
                        "ok": False, "data": None,
                        "error": {"kind": kind, "message": message},
                        "meta": {"tool": name, "server": SERVER_NAME},
                    }, indent=2))]

                specs = arguments.get("specs")
                directory = arguments.get("directory")
                if directory and not specs:
                    d = Path(directory)
                    if not d.is_dir():
                        return _reg_err("bad_directory", f"not a directory: {d}")
                    specs = [{"tox_path": str(p)} for p in sorted(d.glob("*.tox"))]
                    if not specs:
                        return _reg_err("empty_directory", f"no .tox files in {d}")
                if not specs or not isinstance(specs, list):
                    return _reg_err("bad_spec",
                                    "'specs' (a list of {tox_path, ...}) or 'directory' "
                                    "is required")

                if arguments.get("prepare", False):
                    try:
                        prepared = eng.prepare_specs(specs)
                    except Exception as e:
                        return _reg_err(getattr(e, "kind", "prepare_failed"), str(e))
                    return [TextContent(type="text", text=json.dumps({
                        "ok": True,
                        "prepared": prepared,
                        "next": ("author a discriminating one-line 'summary' (+ optional "
                                 "'use_cases' and per-parameter one-line "
                                 "'parameter_descriptions') for each spec, then call "
                                 "register_component again with prepare=false to commit"),
                        "meta": {"tool": name, "server": SERVER_NAME},
                    }, indent=2, ensure_ascii=False))]

                # Commit. Pass the server's query encoder into the engine — it unwraps
                # the raw sentence-transformer itself (passages must NEVER be embedded
                # through the _QueryEncoder's prefix/normalize, W7 #24/#43).
                model = getattr(getattr(hybrid_search, "vector_search", None), "model", None)
                try:
                    results = eng.commit_specs(
                        specs,
                        save_to_palette=bool(arguments.get("save_to_palette", False)),
                        folder=arguments.get("folder", "TD_Builder"),
                        overwrite=bool(arguments.get("overwrite", False)),
                        confirm_shadow=bool(arguments.get("confirm_shadow", False)),
                        model=model,
                    )
                except Exception as e:
                    return _reg_err(getattr(e, "kind", "commit_failed"), str(e))

                # In-session searchability (BLOCKER A): reload the live store; only a
                # successful reload may stamp retrievable:true. A failed reload (e.g.
                # RS_DISABLE dense-only mode) still leaves the commit valid —
                # buildable ≠ searchable — and carries the reason.
                committed = [r for r in results if r.get("ok")]
                if committed:
                    reload_ok, reload_reason = hybrid_search.reload_user_store()
                else:
                    reload_ok, reload_reason = False, "no components committed"
                for r in committed:
                    r["retrievable"] = bool(reload_ok)
                    if not reload_ok:
                        r["retrievable_reason"] = reload_reason
                return [TextContent(type="text", text=json.dumps({
                    "ok": bool(committed),
                    "results": results,
                    "meta": {"tool": name, "server": SERVER_NAME},
                }, indent=2, ensure_ascii=False))]
            finally:
                sys.stdout = _saved_stdout

        elif name == "get_operator_info":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Tools not initialized")]

            operator_name = arguments["operator_name"]
            compact = arguments.get("compact", False)

            # Use knowledge_graph (UnifiedGraphQuery) for comprehensive operator info
            info = knowledge_graph.get_operator_info(operator_name)

            # On a KB miss, return an explicit, self-describing not-found object instead of
            # the literal JSON `null` (which every downstream json.dumps(info) would emit).
            # Placed before the compact branch so both modes get the same shape.
            if info is None:
                import difflib
                # Union both name sources: this KB build ships with the 58MB graphrag
                # dump dropped, so wiki_data is empty and enriched_wiki carries the names
                # (both are lower-cased keys; KB lookup is case-insensitive).
                candidates = list({
                    *getattr(knowledge_graph, "wiki_data", {}).keys(),
                    *getattr(knowledge_graph, "enriched_wiki", {}).keys(),
                })
                suggestions = (
                    difflib.get_close_matches(operator_name.lower(), candidates, n=3, cutoff=0.6)
                    if candidates else []
                )
                not_found = {
                    "found": False,
                    "operator_name": operator_name,
                    "message": f"No KB entry found for operator '{operator_name}'.",
                    "suggestions": suggestions,
                    "hint": (
                        "Check spelling/family suffix (e.g. 'GLSL POP'); call "
                        "list_pop_operators for the POP family, or "
                        "query_graph(command='family', family=<FAMILY>) to list valid names "
                        "in another family."
                    ),
                }
                return [TextContent(type="text", text=json.dumps(not_found, indent=2))]

            # Compact mode: return essential fields + all params with types
            if compact and info:
                # Extract all parameters with their types
                params_compact = {}
                wiki_params = info.get("wiki_parameters", {})

                # Handle both dict and list formats
                if isinstance(wiki_params, dict):
                    # Dict format: {"param_code": {"description": ..., ...}}
                    for code, p in wiki_params.items():
                        if isinstance(p, dict):
                            ptype = p.get("type", "unknown")
                            desc = p.get("description", "")
                            # Infer type from description if not explicit
                            if ptype == "unknown":
                                desc_lower = desc.lower()
                                if "menu" in desc_lower or "dropdown" in desc_lower:
                                    ptype = "menu"
                                elif "toggle" in desc_lower or "on/off" in desc_lower:
                                    ptype = "toggle"
                                elif any(x in desc_lower for x in ["float", "decimal", "0.0"]):
                                    ptype = "float"
                                elif any(x in desc_lower for x in ["integer", "whole number"]):
                                    ptype = "int"
                            params_compact[code] = ptype
                        else:
                            params_compact[code] = str(type(p).__name__)
                elif isinstance(wiki_params, list):
                    for p in wiki_params:
                        if isinstance(p, dict):
                            code = p.get("code", p.get("name", ""))
                            ptype = p.get("type", "unknown")
                            # Normalize type names
                            if "menu" in ptype.lower():
                                ptype = "menu"
                            elif "float" in ptype.lower() or ptype in ["XY", "XYZ", "UV", "RGB", "RGBA"]:
                                ptype = "float"
                            elif "int" in ptype.lower():
                                ptype = "int"
                            elif "str" in ptype.lower():
                                ptype = "str"
                            elif "toggle" in ptype.lower() or "bool" in ptype.lower():
                                ptype = "toggle"
                            params_compact[code] = ptype

                compact_info = {
                    "name": info.get("name"),
                    "family": info.get("family"),
                    "type": info.get("op_type") or info.get("type"),
                    "summary": info.get("summary") or info.get("description", "")[:200],
                    "parameters": params_compact,
                    "_note": "Use get_parameter_detail for full descriptions"
                }
                return [TextContent(
                    type="text",
                    text=json.dumps(compact_info, indent=2)
                )]

            return [TextContent(
                type="text",
                text=json.dumps(info, indent=2)
            )]
        
        elif name == "query_graph":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]

            command = arguments["command"]
            compact = arguments.get("compact", False)

            if command == "params":
                operator = arguments.get("operator")
                if not operator:
                    return [TextContent(type="text", text="Error: 'operator' required for 'params' command")]
                result = knowledge_graph.get_operator_parameters(operator)

            elif command == "related":
                operator = arguments.get("operator")
                if not operator:
                    return [TextContent(type="text", text="Error: 'operator' required for 'related' command")]
                result = knowledge_graph.get_related_operators(operator)

            elif command == "family":
                family = arguments.get("family")
                if not family:
                    return [TextContent(type="text", text="Error: 'family' required for 'family' command")]
                result = knowledge_graph.get_operators_by_family(family)

                # Compact mode: return operators categorized by function
                if compact and isinstance(result, list):
                    # Group by function/category based on operator name patterns
                    categories = {}
                    for op in result:
                        if isinstance(op, dict):
                            name = op.get("name", "")
                            # Extract category from name suffix (e.g., "Noise TOP" -> generator)
                            cat = "other"
                            name_lower = name.lower()
                            if any(x in name_lower for x in ["noise", "ramp", "constant", "pattern", "circle", "rectangle"]):
                                cat = "generators"
                            elif any(x in name_lower for x in ["blur", "level", "edge", "sharpen", "hsv", "composite"]):
                                cat = "filters"
                            elif any(x in name_lower for x in ["math", "logic", "trigger", "count", "compare"]):
                                cat = "math"
                            elif any(x in name_lower for x in ["in", "out", "null", "select", "switch"]):
                                cat = "utilities"
                            elif any(x in name_lower for x in ["file", "movie", "audio", "video"]):
                                cat = "io"
                            elif any(x in name_lower for x in ["transform", "crop", "tile", "flip"]):
                                cat = "transform"
                            elif any(x in name_lower for x in ["render", "geo", "light", "camera"]):
                                cat = "3d"
                            elif any(x in name_lower for x in ["chop", "top", "sop", "dat"]):
                                cat = "conversion"
                            if cat not in categories:
                                categories[cat] = []
                            categories[cat].append(name)

                    compact_result = {
                        "family": family,
                        "count": len(result),
                        "categories": {k: sorted(v) for k, v in sorted(categories.items())},
                        "_note": "Use compact=false for full operator details"
                    }
                    return [TextContent(
                        type="text",
                        text=json.dumps(compact_result, indent=2)
                    )]

            else:
                return [TextContent(type="text", text=f"Error: Unknown command '{command}'")]

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
        
        elif name == "list_pop_operators":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            # B22 — delegate to the canonical enumeration used by query_graph(family='POP').
            # Previously this inline-iterated knowledge_graph.nodes (enhanced graph only) and
            # missed wiki-side operators, returning 95 while query_graph(family='POP') returned 100.
            # B28 — drop meta entries (`masterPOP`, `_conceptsPOP` etc.) that aren't real operators.
            ops = knowledge_graph.get_operators_by_family("POP") or []
            result = [
                {
                    "name": op.get("name", ""),
                    "family": (op.get("data") or {}).get("family", "POP"),
                }
                for op in ops
                if op.get("name", "")
                and not op.get("name", "").startswith("_")
                and not op.get("name", "").lower().startswith("master")
            ]
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_operator_examples":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            # Accept both `operator` (schema) and `operator_name` (consistent with
            # get_operator_info/get_parameter_detail) so callers using either work.
            operator = arguments.get("operator") or arguments.get("operator_name")
            if not operator:
                return [TextContent(type="text", text="Error: 'operator' (or 'operator_name') is required")]
            limit = arguments.get("limit", 10)
            # B24 — optional `family` disambiguates bare names. Also accepts
            # colon-form ('TOP:noise') / suffixed-form ('noiseTOP') in the
            # `operator` arg itself; the backend normalises both.
            family = arguments.get("family")
            result = knowledge_graph.find_examples_by_operator(
                operator, limit, family=family,
            )
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_operator_combination":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            operator_types = arguments.get("operator_types", [])
            require_connection = arguments.get("require_connection", True)
            limit = arguments.get("limit", 5)
            result = knowledge_graph.find_examples_by_operator_combination(
                operator_types, require_connection, limit
            )
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_parameter_usage":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            operator_type = arguments.get("operator_type")
            parameter_name = arguments.get("parameter_name")
            limit = arguments.get("limit", 10)
            compact = arguments.get("compact", False)
            result = knowledge_graph.find_parameter_usage(
                operator_type, parameter_name, limit
            )

            # Compact mode: return only unique values to save context
            if compact and isinstance(result, list):
                unique_values = set()
                for item in result:
                    if isinstance(item, dict):
                        # B19 — backend records use `parameter_value`, not `value`.
                        # Keep `value` and `parameter_name` as graceful fallbacks for
                        # any future backend-shape drift.
                        val = item.get("parameter_value") or item.get("value") or item.get(parameter_name)
                        if val is not None:
                            unique_values.add(str(val))
                compact_result = {
                    "operator_type": operator_type,
                    "parameter_name": parameter_name,
                    "example_count": len(result),
                    "unique_values": sorted(list(unique_values)),
                    "_note": "Use compact=false for full example contexts"
                }
                return [TextContent(
                    type="text",
                    text=json.dumps(compact_result, indent=2)
                )]

            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "find_similar_networks":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            example_id = arguments.get("example_id")
            limit = arguments.get("limit", 5)
            result = knowledge_graph.find_similar_networks(example_id, limit)
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "get_parameter_detail":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            operator_name = arguments.get("operator_name")
            parameter_name = arguments.get("parameter_name")

            # Get operator info
            info = knowledge_graph.get_operator_info(operator_name)
            if not info:
                return [TextContent(type="text", text=f"Operator '{operator_name}' not found")]

            # Find the specific parameter - handle both dict and list formats.
            wiki_params = info.get("wiki_parameters", {})

            # 1) Exact match first (unchanged behavior).
            param_detail = _find_param_code(wiki_params, parameter_name)

            # 2) On a miss, try the compound-parent fallback: TD exposes compound params
            #    (color, pt0pos, vec0value, ...) as per-component leaves (pt0posx/y/z,
            #    colorr/g/b/a) that have no separate KB entry. Retry against the stripped
            #    parent and, on a hit, annotate the response as a heuristic leaf match.
            candidate = None
            if param_detail is None:
                candidate = _strip_compound_leaf_suffix(parameter_name)
                if candidate:
                    parent_detail = _find_param_code(wiki_params, candidate)
                    if parent_detail is not None:
                        parent_detail["requested_parameter"] = parameter_name
                        parent_detail["leaf_of_compound"] = True
                        parent_detail["_note"] = (
                            f"'{parameter_name}' has no separate KB entry; TouchDesigner "
                            f"exposes it as a component (.x/.y/.z/.w or .r/.g/.b/.a or "
                            f"numeric) of the compound parameter '{candidate}'. Showing the "
                            f"parent's details -- the per-component default/range is not "
                            f"tracked separately yet."
                        )
                        param_detail = parent_detail

            if not param_detail:
                msg = f"Parameter '{parameter_name}' not found on operator '{operator_name}'"
                if candidate:
                    msg += f" (also checked '{candidate}' as a possible compound parent; not found)"
                return [TextContent(type="text", text=msg)]

            return [TextContent(
                type="text",
                text=json.dumps(param_detail, indent=2)
            )]

        elif name == "get_network_patterns":
            if not knowledge_graph:
                return [TextContent(type="text", text="ERROR: Knowledge graph not available")]
            min_frequency = arguments.get("min_frequency", 5)
            result = knowledge_graph.get_network_patterns(min_frequency)
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

        elif name == "td_build_project":
            # Support both 'design' (simple) and 'network_design' (advanced with containers)
            network_design = arguments.get("network_design")
            design = arguments.get("design", {})
            table_data = arguments.get("table_data", {})
            project_name = arguments.get("project_name")
            output_dir = arguments.get("output_dir")
            mode = arguments.get("mode", "tox")

            # B08 — pre-validate operator types against OperatorRegistry. Catches
            # invented type strings (e.g. "POP:sourcePOP") before producing a broken .tox.
            # Walks both the flat `operators` list and any nested `containers[*].operators` /
            # `containers[*].network.operators`. Accepts colon-form ("CHOP:noise") and
            # separate-family form ({"family":"CHOP","type":"noise"}).
            if UNIFIED_SYSTEM_ENABLED:
                def _collect_ops(design_dict):
                    d = design_dict or {}
                    ops = list(d.get("operators", []) or [])
                    for c in d.get("containers", []) or []:
                        ops.extend(c.get("operators", []) or [])
                        net = c.get("network", {}) or {}
                        ops.extend(net.get("operators", []) or [])
                    return ops

                unknown = []
                for op in _collect_ops(network_design or design):
                    if not isinstance(op, dict):
                        continue
                    raw = (op.get("type") or "").strip()
                    if not raw:
                        continue
                    if ":" in raw:
                        full = raw
                    else:
                        fam = (op.get("family") or "").strip()
                        if not fam:
                            unknown.append(raw)
                            continue
                        full = f"{fam}:{raw}"
                    if not _registry.get_operator_by_type(full):
                        unknown.append(full)
                if unknown:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "ERROR",
                        "message": "Unknown operator types — not in registry",
                        "unknown_types": sorted(set(unknown)),
                        "hint": "Use query_graph(command='family') or hybrid_search to look up valid types.",
                    }, indent=2))]

            # Opt-in async (R2-A): run the build in a background thread and return a job id
            # immediately, so a long build never hits the MCP client's ~45s tool-call timeout.
            # Pre-validation above already ran synchronously, so bad input still fails fast.
            if bool(arguments.get("async_build")):
                job_id = _start_build_job(network_design, design, table_data,
                                          project_name, output_dir, mode)
                return [TextContent(type="text", text=json.dumps({
                    "status": "STARTED",
                    "job_id": job_id,
                    "hint": "Poll td_build_status with this job_id; the .tox completes on disk.",
                }, indent=2))]

            # Synchronous (default, unchanged behavior).
            result = await _run_build(network_design, design, table_data,
                                      project_name, output_dir, mode)
            # Result-envelope pull pointer (D2 / item 3b): cheap reminder that
            # rides the build result to surfaces where instructions= is dropped.
            if isinstance(result, dict):
                result.setdefault("non_negotiables", "docs/NON_NEGOTIABLES.md")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "td_build_status":
            job_id = arguments.get("job_id")
            if not job_id:
                return [TextContent(type="text", text=json.dumps({
                    "status": "ERROR", "message": "Missing required argument 'job_id'."}, indent=2))]
            with _build_lock:
                job = _build_jobs.get(job_id)
                snapshot = dict(job) if job else None
            if snapshot is None:
                return [TextContent(type="text", text=json.dumps({
                    "status": "ERROR",
                    "message": f"Unknown job_id: {job_id}",
                    "hint": "Job ids are not persisted across server restarts.",
                }, indent=2))]
            started = snapshot.get("started")
            if started is not None:
                end = snapshot.get("finished") or time.time()
                snapshot["elapsed"] = round(end - started, 2)
            return [TextContent(type="text", text=json.dumps(snapshot, indent=2, default=str))]

        elif name == "td_validate":
            if not UNIFIED_SYSTEM_ENABLED:
                return [TextContent(type="text", text=json.dumps({
                    "error": "Unified system validation not available",
                    "hint": "Check unified_system imports"
                }, indent=2))]

            try:
                network_json = arguments.get("network")
                if not network_json:
                    return [TextContent(type="text", text="Error: 'network' is required")]

                format_layer = arguments.get("format_layer", "builder")
                verbose = arguments.get("verbose", False)

                # Convert to TDNetwork if needed. 'extended' exists only as the
                # in-memory TDNetwork hub — there is no Extended JSON (de)serializer,
                # so refuse it honestly instead of silently parsing as builder.
                if format_layer == "builder":
                    network = _converter.from_builder(network_json)
                elif format_layer == "canonical":
                    network = _converter.from_canonical(network_json)
                else:
                    return [TextContent(type="text", text=json.dumps({
                        "status": "NOT_IMPLEMENTED",
                        "error": f"format_layer '{format_layer}' is not implemented in this release.",
                        "hint": "Use 'builder' or 'canonical'. 'extended' is the internal in-memory "
                                "representation and has no JSON form to validate.",
                    }, indent=2))]

                # Validate
                project_name = network_json.get("meta", {}).get("project_name", "network")
                report = _validator.validate(network, project_name)

                # Build response
                result = {
                    "valid": report.valid,
                    "total_errors": report.total_errors,
                    "total_warnings": report.total_warnings,
                    "errors": [{"stage": e.stage, "message": e.message, "severity": e.severity}
                              for e in report.get_errors()],
                    "warnings": [{"stage": w.stage, "message": w.message, "severity": w.severity}
                                for w in report.get_warnings()]
                }

                if verbose:
                    result["stages"] = {}
                    for stage_report in report.stages:
                        result["stages"][stage_report.stage] = {
                            "passed": stage_report.status == "PASS",
                            "errors": len(stage_report.errors),
                            "warnings": len(stage_report.warnings)
                        }

                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            except Exception as e:
                import traceback
                return [TextContent(type="text", text=json.dumps({
                    "error": f"Validation error: {str(e)}",
                    "traceback": traceback.format_exc()
                }, indent=2))]

        elif name == "td_convert":
            if not UNIFIED_SYSTEM_ENABLED:
                return [TextContent(type="text", text=json.dumps({
                    "error": "Unified system format converter not available",
                    "hint": "Check unified_system imports"
                }, indent=2))]

            try:
                network_json = arguments.get("network")
                if not network_json:
                    return [TextContent(type="text", text="Error: 'network' is required")]

                source_layer = arguments.get("source_layer")
                target_layer = arguments.get("target_layer")

                if not source_layer or not target_layer:
                    return [TextContent(type="text", text="Error: 'source_layer' and 'target_layer' are required")]

                # 'extended' is the internal in-memory hub (TDNetwork) — there is no
                # Extended JSON (de)serializer, so refuse it with a clear error
                # instead of mislabeling builder JSON as extended.
                if source_layer not in ("builder", "canonical") or target_layer not in ("builder", "canonical"):
                    bad = source_layer if source_layer not in ("builder", "canonical") else target_layer
                    return [TextContent(type="text", text=json.dumps({
                        "status": "NOT_IMPLEMENTED",
                        "error": f"format layer '{bad}' is not implemented in this release.",
                        "hint": "Use 'builder' or 'canonical'. Conversion already passes through the "
                                "internal Extended (TDNetwork) hub; it has no JSON form to emit or ingest.",
                    }, indent=2))]

                # Convert source -> Extended hub (in-memory)
                if source_layer == "builder":
                    network = _converter.from_builder(network_json)
                else:  # canonical
                    network = _converter.from_canonical(network_json)

                # Convert Extended hub -> target
                if target_layer == "builder":
                    result_json = _converter.to_builder(network)
                else:  # canonical
                    result_json = _converter.to_canonical(network)

                return [TextContent(type="text", text=json.dumps(result_json, indent=2))]
            except Exception as e:
                import traceback
                return [TextContent(type="text", text=json.dumps({
                    "error": f"Conversion error: {str(e)}",
                    "traceback": traceback.format_exc()
                }, indent=2))]

        elif name == "get_expert_prompt":
            expert_name = arguments["expert_name"]
            phase = arguments.get("phase", "build")
            prompt_content = load_expert_prompt(expert_name, phase)
            return [TextContent(
                type="text",
                text=prompt_content
            )]

        elif name == "get_server_info":
            # Diagnose a degraded retrieval install (reranker/BM25 missing => hybrid_search
            # scores are rank-fusion only) without reading server stdout. Guarded so a
            # not-yet-initialized adapter never raises here.
            _rs = getattr(hybrid_search, "retrieval_stack", None) if hybrid_search else None
            info = {
                "ok": True,
                "data": {
                    "server_name": SERVER_NAME,
                    "version": SERVER_VERSION,
                    "kb_version": _KB_MANIFEST_VERSION,
                    "compat": _COMPAT,
                    "retrieval_backend": {
                        "reranker_active": getattr(_rs, "_reranker", None) is not None,
                        "bm25_active": getattr(_rs, "_bm25", None) is not None,
                    },
                    "kb_root": str(_KB_ROOT),
                    "script_path": str(Path(__file__).resolve()),
                    "cwd": os.getcwd(),
                    "python": sys.version.split()[0],
                    "td_live_enabled": TD_LIVE_ENABLED,
                    # Pull-side delivery of the non-negotiables (D2 / item 3b): the
                    # only channel that reaches surfaces where `instructions=` is
                    # dropped (Claude Desktop chat, Cursor). This is the offline
                    # server, so it returns the offline-scoped payload (== this
                    # server's own instructions=) so the model can recover the
                    # rules after compaction.
                    "non_negotiables": _NON_NEGOTIABLES,
                    "non_negotiables_file": "docs/NON_NEGOTIABLES.md",
                },
                "meta": {"tool": "get_server_info", "server": SERVER_NAME},
            }
            return [TextContent(type="text", text=json.dumps(info, indent=2))]

        elif name == "expand_toe_file":
            import shutil as _shutil
            import subprocess as _subprocess
            import tempfile as _tempfile
            import glob as _glob

            def _expand_err(msg, hint=None):
                err = {"message": msg}
                if hint:
                    err["hint"] = hint
                return [TextContent(type="text", text=json.dumps({
                    "ok": False, "data": None, "error": err,
                    "meta": {"tool": "expand_toe_file", "server": SERVER_NAME},
                }, indent=2))]

            toe_path_arg = arguments.get("toe_path") or arguments.get("path")
            out_mode = (arguments.get("mode") or "summary").lower()
            if not toe_path_arg:
                return _expand_err("Missing required argument 'toe_path' (or 'path').")
            if out_mode not in ("summary", "full"):
                return _expand_err(f"Invalid mode '{out_mode}'. Use 'summary' or 'full'.")
            src = Path(toe_path_arg)
            if not src.exists():
                return _expand_err(f"Path not found: {src}",
                                   "Pass an absolute path to a .toe/.tox file or an expanded .toe.dir/.tox.dir.")

            cleanup_dir = None
            if src.is_dir() and src.name.endswith(".dir"):
                toe_dir = src
            elif src.is_file() and src.suffix.lower() in (".toe", ".tox"):
                from paths import resolve_td_tool
                exe = resolve_td_tool("toeexpand")
                if not exe:
                    return _expand_err(
                        "toeexpand not found.",
                        "Install TouchDesigner (it provides toeexpand), set TD_TOEEXPAND/TD_BIN_DIR, "
                        "or pass an already-expanded .toe.dir.")
                work = Path(_tempfile.mkdtemp(prefix="td_expand_"))
                cleanup_dir = work
                work_proj = work / src.name
                _shutil.copy2(src, work_proj)
                # toeexpand returns rc 1 even on success on some builds.
                try:
                    proc = _subprocess.run([str(exe), str(work_proj)], cwd=str(work),
                                           capture_output=True, text=True, timeout=EXPAND_TIMEOUT_S)
                except _subprocess.TimeoutExpired:
                    _shutil.rmtree(work, ignore_errors=True)
                    return _expand_err(
                        f"toeexpand exceeded {EXPAND_TIMEOUT_S}s and was aborted.",
                        "The .toe/.tox may be very large; note the MCP client's own ~45s "
                        "tool-call timeout may also fire first.")
                toe_dir = work / f"{src.name}.dir"
                if not toe_dir.exists():
                    alts = list(work.glob("*.dir"))
                    if alts:
                        toe_dir = alts[0]
                    else:
                        _shutil.rmtree(work, ignore_errors=True)
                        return _expand_err(
                            f"toeexpand produced no .dir output (rc={proc.returncode}).",
                            (proc.stderr or proc.stdout or "").strip()[:500] or None)
            else:
                return _expand_err(f"Unsupported input: {src}",
                                   "Expected a .toe/.tox file or an expanded .toe.dir/.tox.dir.")

            expand_truncated = False
            try:
                from parsers.lossless_parser import parse_toe_lossless
                network = parse_toe_lossless(toe_dir, registry=None, verbose=False)
                if out_mode == "full":
                    from core.lossless_json import to_lossless_json_dict
                    data = to_lossless_json_dict(network)
                    # Output budget (W4b): full lossless JSON round-trips, so an
                    # oversized payload is withheld (not partially truncated) with an
                    # explicit pointer. Stays ok=True so the scorer envelope is fine.
                    data, expand_truncated, _ = budget_full_expand(data)
                else:
                    data = _summarize_td_network(network)
            except Exception as pe:
                return _expand_err(f"Failed to parse expanded network: {pe}")
            finally:
                if cleanup_dir is not None:
                    _shutil.rmtree(cleanup_dir, ignore_errors=True)

            _meta = {"tool": "expand_toe_file", "server": SERVER_NAME, "mode": out_mode}
            if expand_truncated:
                _meta["truncated"] = True
            return [TextContent(type="text", text=json.dumps({
                "ok": True, "data": data, "meta": _meta,
            }, indent=2, default=str))]

        # (Live-TD tools are dispatched by the separate td-builder-live server;
        # this offline server has no live handlers.)
        else:
            return [TextContent(
                type="text",
                text=f"Error: Unknown tool '{name}'"
            )]
            
    except Exception as e:
        import traceback
        return [TextContent(
            type="text",
            text=f"Error: {str(e)}\n{traceback.format_exc()}"
        )]


async def main():
    """Run the MCP server"""
    # Restore real stdout for MCP JSON-RPC protocol. See top-of-file
    # stdout-pollution guard.
    sys.stdout = _real_stdout
    print(
        f"[td-builder] {SERVER_NAME} v{SERVER_VERSION} starting | "
        f"script={Path(__file__).resolve()} | cwd={os.getcwd()} | "
        f"td_live={TD_LIVE_ENABLED}",
        file=sys.stderr,
    )
    # Warm the KB in the background so the first KB-dependent tool call
    # doesn't pay the ~1-2 min load on a silent socket (clients time out at
    # ~4 min). Non-blocking: get_server_info / live-TD stay instant; a first
    # KB call either finds it already warm or briefly waits on _kb_lock.
    #
    # Delay 2s before kicking off the load: _load_kb() mutates sys.stdout
    # process-wide for the duration of the load (see stdout-pollution guard
    # at line 446), so if it fires before the MCP `initialize` response is
    # flushed, that response gets written to stderr and Claude Desktop's
    # 60s handshake timeout fires. The sleep ensures stdio_server has
    # already completed the handshake by the time the swap happens.
    def _delayed_kb_warmup():
        time.sleep(2.0)
        _ensure_kb()
    threading.Thread(target=_delayed_kb_warmup, name="kb-warmup", daemon=True).start()
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())

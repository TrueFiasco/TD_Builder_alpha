r"""D4 feedback spine — opt-in, local-only, per-tool-call record (offline server).

A cross-server module (``MCP/`` sibling of ``server_instructions.py``, importable by
both servers). Wraps the offline dispatch as a ONE-LINE decorator between
``@app.call_tool()`` and ``call_tool``:

    @app.call_tool()
    @feedback_recorded(server="td-builder", server_version=SERVER_VERSION,
                       kb_root=_KB_ROOT, instructions_text=_NON_NEGOTIABLES,
                       tool_names=_feedback_tool_names())
    async def call_tool(name, arguments): ...   # body unchanged

Guarantees (the trust-critical contract):
  * OFF by default. When off, the wrapper returns ``await fn(...)`` immediately —
    the SAME object out — so the returned envelope is byte-identical and there is no
    I/O. The flag is read at CALL time (matches ``paths.py`` convention; the
    "byte-identical" property comes from returning the same object, not from skipping
    a nanosecond ``getenv``).
  * When on, the record is READ-ONLY on the envelope and written to a side-channel
    JSONL FILE only — never stdout (the MCP JSON-RPC channel). The returned object is
    handed back unchanged.
  * FAIL-SOFT: the entire record path (identity hashing, redaction, open/write,
    rotation, retention) is inside one swallow-all ``try`` with NO ``print`` — a
    recorder failure never perturbs the tool result and never raises.
  * The writer is fully SYNCHRONOUS (no ``await`` between building the line and
    writing it) and holds a lock, so concurrent async tool calls cannot interleave a
    half-written line. Per-(server, pid, date) filenames additionally rule out
    cross-process interleave.

Never captures raw tokens (keys matching token/secret/key/password/auth are masked)
or raw file contents (large args are summarized; strings truncated); all free text is
run through a home/root/worktree substring scrubber. No network calls, ever.
"""

import functools
import json
import os
import platform
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import env_identity
import feedback_classify

SCHEMA = "td-feedback/1"

_LOCK = threading.Lock()
_identity_cache: dict = {}
_config_default_cache = None
_scrub_cache = None
_last_sweep_date = None

# Bounds (env-tunable, same _cap idiom as output_budget.py).
_ARG_STR_MAX = 200            # per-string truncation
_ARG_VALUE_SUMMARIZE = 512    # summarize a nested dict/list bigger than this (bytes)
_ARG_TOTAL_MAX = 2 * 1024     # whole args blob cap (bytes)
_DEFAULT_MAX_BYTES = 8 * 1024 * 1024
_DEFAULT_RETENTION_DAYS = 14


# --------------------------------------------------------------------------- #
# Opt-in flag (call-time; real-env -> .env -> search_config.json -> "false")
# --------------------------------------------------------------------------- #
def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _config_default() -> str:
    """The JSON/`.env`-layer default for the master switch, resolved once.

    Robust to ``config`` not being importable (e.g. a bare unit test): the JSON layer
    is simply skipped and the code default ``"false"`` applies. Real-env and ``.env``
    (folded into ``os.environ`` at config import) are still honoured via ``getenv``.
    """
    global _config_default_cache
    if _config_default_cache is None:
        try:
            from config import FEEDBACK_ENABLED_DEFAULT
            _config_default_cache = str(FEEDBACK_ENABLED_DEFAULT)
        except Exception:
            _config_default_cache = "false"
    return _config_default_cache


def _enabled() -> bool:
    return _truthy(os.getenv("TD_FEEDBACK_ENABLED", _config_default()))


def _cap(env_name: str, default: int) -> int:
    raw = os.environ.get(env_name, "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return default


# --------------------------------------------------------------------------- #
# Record location (call-time; mirrors paths.py::user_components_path)
# --------------------------------------------------------------------------- #
def feedback_dir() -> Path:
    """Where records live. Outside ``KB/`` (a fetched, identity-hashed artifact that
    stays pristine); same home as the live-server ``api_token`` and
    ``user_components.json``. ``TD_FEEDBACK_DIR`` overrides the whole path; else
    ``TD_BUILDER_USER_DIR``/feedback; else ``~/.td_builder/feedback``. Resolved at
    CALL time so tests and a long-lived server see env changes without a reload."""
    override = os.environ.get("TD_FEEDBACK_DIR")
    if override and override.strip():
        return Path(override).expanduser()
    base = os.environ.get("TD_BUILDER_USER_DIR")
    root = Path(base).expanduser() if base and base.strip() else Path.home() / ".td_builder"
    return root / "feedback"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


# --------------------------------------------------------------------------- #
# Privacy: home/root/worktree substring scrubber (redact_path alone misses home())
# --------------------------------------------------------------------------- #
import re as _re

_SECRET_KEY = _re.compile(r"token|secret|key|password|auth|cred", _re.IGNORECASE)
# Match a worktree prefix up to (but NOT consuming) the separator after the worktree
# name, so both a child path and the BARE worktree root scrub. `$` covers the no-
# trailing-separator case (e.g. an exception message ending exactly at the dir).
_WORKTREE_RE = _re.compile(r".*?[\\/]\.claude[\\/]worktrees[\\/][^\\/]+(?=[\\/]|$)", _re.IGNORECASE)


def _scrub_pairs():
    """(needle, token) replacements, computed once. Longest needles first so a
    worktree/release root is replaced before the broader home dir."""
    global _scrub_cache
    if _scrub_cache is None:
        pairs = []
        # <ROOT> = the release/install root. TD_BUILDER_ROOT is documented-optional;
        # when unset, infer it the same way the rest of the server does (feedback.py
        # lives at <root>/MCP/) so an install-root path still scrubs on a real deploy.
        root = os.environ.get("TD_BUILDER_ROOT")
        if not (root and root.strip()):
            try:
                root = str(Path(__file__).resolve().parents[1])
            except Exception:
                root = ""
        if root:
            pairs.append((str(Path(root)), "<ROOT>"))
        try:
            pairs.append((str(Path.home()), "<HOME>"))
        except Exception:
            pass
        # Match both native and forward-slash spellings; sort by length desc.
        expanded = []
        for needle, tok in pairs:
            if needle:
                expanded.append((needle, tok))
                alt = needle.replace("\\", "/")
                if alt != needle:
                    expanded.append((alt, tok))
        expanded.sort(key=lambda p: len(p[0]), reverse=True)
        _scrub_cache = expanded
    return _scrub_cache


def scrub_text(s: str) -> str:
    """Replace home/release-root/worktree prefixes with tokens. Public: the exporter
    re-runs this defensively over every record."""
    if not isinstance(s, str) or not s:
        return s
    s = _WORKTREE_RE.sub("<ROOT>", s)   # lookahead leaves the following separator in place
    for needle, tok in _scrub_pairs():
        if needle in s:
            s = s.replace(needle, tok)
    return s


def _trunc(s: str) -> str:
    if len(s) > _ARG_STR_MAX:
        return s[:_ARG_STR_MAX] + f"...(+{len(s) - _ARG_STR_MAX} chars)"
    return s


def _rough_size(v) -> int:
    try:
        return len(json.dumps(v, default=str, ensure_ascii=False))
    except Exception:
        return _ARG_VALUE_SUMMARIZE + 1


def _summarize_value(v, depth: int = 0):
    if isinstance(v, str):
        return _trunc(scrub_text(v))
    if isinstance(v, bool) or v is None or isinstance(v, (int, float)):
        return v
    if isinstance(v, dict):
        if depth >= 2 or _rough_size(v) > _ARG_VALUE_SUMMARIZE:
            # Summarized branch already drops values (keeps only key names).
            return {"_type": "dict", "len": len(v),
                    "keys": sorted(map(str, v.keys()))[:20]}
        # Mask secrets at EVERY depth, not just top-level (a token nested under a
        # non-secret key must not leak verbatim).
        return {str(k): ("<redacted>" if _SECRET_KEY.search(str(k))
                         else _summarize_value(val, depth + 1))
                for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        if depth >= 2 or _rough_size(v) > _ARG_VALUE_SUMMARIZE:
            return {"_type": "list", "len": len(v)}
        return [_summarize_value(x, depth + 1) for x in v]
    return _trunc(scrub_text(str(v)))


def _redact_args(args):
    if not isinstance(args, dict):
        return _summarize_value(args)
    out = {}
    for k, v in args.items():
        if _SECRET_KEY.search(str(k)):
            out[k] = "<redacted>"
        else:
            out[k] = _summarize_value(v)
    if _rough_size(out) > _ARG_TOTAL_MAX:
        return {"_type": "dict", "len": len(out),
                "keys": sorted(map(str, out.keys()))[:20], "_truncated": True}
    return out


def _deep_scrub(obj):
    """Belt-and-suspenders: walk the assembled record and scrub every string, so no
    absolute path can leak through description/exception/artifact fields."""
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, dict):
        return {k: _deep_scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_scrub(x) for x in obj]
    return obj


def redact_record(rec):
    """Public: defensive re-redaction of a whole record (used by the exporter)."""
    try:
        return _deep_scrub(rec)
    except Exception:
        return rec


# --------------------------------------------------------------------------- #
# Identity header (computed once per server, cached)
# --------------------------------------------------------------------------- #
def _identity(server, server_version, kb_root, instructions_text, tool_names):
    if server not in _identity_cache:
        ident = {
            "server_version": server_version,
            "platform": sys.platform,
            "python": platform.python_version(),
        }
        try:
            ident.update(env_identity.kb_identity(Path(kb_root)))
        except Exception:
            pass
        if tool_names:
            try:
                ident["tool_inventory_hash"] = env_identity.tool_inventory_hash(tool_names)
            except Exception:
                pass
        if instructions_text:
            try:
                ident["instructions_hash"] = env_identity.sha256_text(instructions_text)
            except Exception:
                pass
        _identity_cache[server] = ident
    return _identity_cache[server]


# --------------------------------------------------------------------------- #
# Record assembly + synchronous locked writer
# --------------------------------------------------------------------------- #
def _build_record(name, arguments, result, raised, latency_ms):
    c = feedback_classify.classify(name, result, raised)
    rec = {
        "kind": "call",
        "ts": _utc_iso(),
        "tool": name,
        "outcome": c.get("outcome", "unknown"),
        "latency_ms": round(float(latency_ms), 2),
        "args": _redact_args(arguments),
    }
    exc = c.get("exception")
    if isinstance(exc, dict):
        rec["exception"] = {"type": exc.get("type"),
                            "message": str(exc.get("message", ""))[:feedback_classify._MAX_DESC]}
    for k in ("event_type", "status"):
        if c.get(k) is not None:
            rec[k] = c[k]
    if c.get("artifact") is not None:
        rec["artifact"] = c["artifact"]
    if c.get("description"):
        rec["description"] = str(c["description"])[:feedback_classify._MAX_DESC]
    return _deep_scrub(rec)


def _rotate_if_big(path: Path) -> Path:
    max_bytes = _cap("TD_FEEDBACK_MAX_BYTES", _DEFAULT_MAX_BYTES)
    try:
        if path.exists() and path.stat().st_size > max_bytes:
            n = 1
            while True:
                cand = path.with_name(f"{path.stem}-{n}{path.suffix}")
                if not cand.exists() or cand.stat().st_size <= max_bytes:
                    return cand
                n += 1
    except Exception:
        pass
    return path


def _sweep_retention(d: Path):
    global _last_sweep_date
    today = _date_str()
    if _last_sweep_date == today:
        return
    _last_sweep_date = today
    days = _cap("TD_FEEDBACK_RETENTION_DAYS", _DEFAULT_RETENTION_DAYS)
    try:
        cutoff = datetime.now(timezone.utc)
        for f in d.glob("*.jsonl"):
            # filename: <server>-<pid>-YYYYMMDD[-N].jsonl -> pull the date field.
            # The date is the LAST 8-digit segment (the optional "-N" rotation suffix
            # is 1-2 digits); scanning in reverse is robust to the hyphen in the server
            # name and to any short numeric segments before it.
            parts = f.stem.split("-")
            stamp = next((p for p in reversed(parts) if len(p) == 8 and p.isdigit()), None)
            if not stamp:
                continue
            try:
                fdate = datetime.strptime(stamp, "%Y%m%d").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if (cutoff - fdate).days > days:
                f.unlink(missing_ok=True)
    except Exception:
        pass


def _emit(server, server_version, kb_root, instructions_text, tool_names,
          name, arguments, result, raised, latency_ms):
    """Fully synchronous, swallow-all. Covers identity hashing + redaction + open/
    write + rotation + retention so no OSError can reach the tool path."""
    try:
        if not _enabled():
            return
        ident = _identity(server, server_version, kb_root, instructions_text, tool_names)
        rec = _build_record(name, arguments, result, raised, latency_ms)
        rec_line = json.dumps(rec, ensure_ascii=False, default=str)
        with _LOCK:
            d = feedback_dir()
            d.mkdir(parents=True, exist_ok=True)
            path = _rotate_if_big(d / f"{server}-{os.getpid()}-{_date_str()}.jsonl")
            new_file = not path.exists()
            with open(path, "a", encoding="utf-8") as f:
                if new_file:
                    header = {"kind": "session_header", "schema": SCHEMA,
                              "created_at": _utc_iso(), "server": server,
                              "identity": ident}
                    f.write(json.dumps(header, ensure_ascii=False, default=str) + "\n")
                f.write(rec_line + "\n")
            _sweep_retention(d)
    except Exception:
        # Never perturb the tool path; never print (would hit the JSON-RPC stdout).
        pass


# --------------------------------------------------------------------------- #
# The decorator
# --------------------------------------------------------------------------- #
def feedback_recorded(*, server, server_version, kb_root, instructions_text="",
                      tool_names=()):
    """Wrap an async dispatch ``fn(name, arguments)``. Off -> transparent no-op; on ->
    record read-only to the side-channel file, returning ``fn``'s result unchanged."""
    tool_names = tuple(tool_names or ())

    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(name, arguments):
            if not _enabled():
                return await fn(name, arguments)
            t0 = time.perf_counter()
            result = None
            raised = None
            try:
                result = await fn(name, arguments)
                return result
            except Exception as e:
                raised = e
                raise
            finally:
                _emit(server, server_version, kb_root, instructions_text, tool_names,
                      name, arguments, result, raised,
                      (time.perf_counter() - t0) * 1000.0)
        return wrapper
    return deco

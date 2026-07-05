r"""Read-only per-tool-call outcome classifier for the D4 feedback spine.

PURE module: no MCP / server / KB imports, so it unit-tests in isolation. Given a
tool name and the offline dispatch's return value (a ``Sequence[TextContent |
ImageContent]``) plus any exception that escaped the wrapper, it returns a small
classification dict WITHOUT ever mutating the envelope (it only ever ``json.loads``
a copy of the text).

Honesty rule (owner ruling): the ONLY things allowed to set ``outcome="error"`` are
(a) a raised/uncaught exception, or (b) an ALLOW-LISTED adapter that knows that
tool's failure shape. Everything else is ``"unknown"`` — a wrong classification
poisons the user's bug report, so conservative-or-unknown, always. The taxonomy is
limited to the two events observable from a single call: ``build_failure`` and
``validation_error`` (``phase_reopen`` / ``manual_intervention`` need session-level
machinery — a future D6 concern).

The three adapters map onto the REAL envelopes in ``mcp_server.py`` (grounded, not
guessed):
  * ``td_validate``       -> ``{valid, errors[...]}`` on success; ``{error,...}`` /
                             ``{status:"NOT_IMPLEMENTED"}`` / plaintext on failure
                             (NO ``valid`` key -> unknown; there is no ``connection``
                             field).
  * ``td_build_project``  -> ``{status: SUCCESS | ERROR | STARTED}``.
  * ``td_build_status``   -> async snapshot ``{status: running | done | error | ERROR}``
                             where ``done`` carries a nested ``result`` whose OWN
                             ``status`` can be ``ERROR`` (a completed-but-FAILED build
                             — must be caught, not stamped success), a worker crash is
                             lowercase ``error`` with a ``traceback``, and a bad job-id
                             lookup is uppercase ``ERROR`` with a ``message``.
"""

import json

# Tools whose failure shape the classifier is allowed to read. Nothing else may be
# classified as success/error — see the honesty rule above.
ADAPTERS = ("td_validate", "td_build_project", "td_build_status")

# The offline dispatch's catch-all (mcp_server.py) returns this exact plaintext on an
# UNCAUGHT exception: "Error: <msg>\n<traceback>". Requiring the traceback marker (not
# just the "Error: " prefix) avoids flagging handled plaintext errors like
# "Error: 'network' is required" or "Error: Unknown tool 'x'" as exceptions.
_CATCHALL_PREFIX = "Error: "
_CATCHALL_MARKER = "Traceback (most recent call last)"

_MAX_DESC = 500


def classify(tool, result, raised=None):
    """Classify one tool call. NEVER raises; always returns a dict with ``outcome``.

    Return keys (all optional except ``outcome``): ``outcome`` in
    {success, error, unknown}; ``event_type`` (build_failure | validation_error);
    ``artifact`` (dict of independently-verifiable booleans + validation_errors);
    ``description`` (short, redacted by the recorder); ``status`` (raw build status
    passthrough); ``exception`` ({type, message}) for the exception-equivalent path.
    """
    try:
        return _classify(tool, result, raised)
    except Exception:
        # The classifier must never be able to break recording, let alone the tool.
        return {"outcome": "unknown"}


def _classify(tool, result, raised):
    # 1. A genuine exception escaped the wrapper (rare: the dispatch swallows most
    #    into the catch-all envelope below). Tool-agnostic, unambiguous.
    if raised is not None:
        return {"outcome": "error",
                "exception": {"type": type(raised).__name__, "message": str(raised)}}

    text = _text_of(result)

    # 2. Universal catch-all exception envelope (needs the traceback marker).
    if text is not None and text.startswith(_CATCHALL_PREFIX) and _CATCHALL_MARKER in text:
        first_line = text.split("\n", 1)[0][len(_CATCHALL_PREFIX):]
        return {"outcome": "error",
                "exception": {"type": _last_exc_type(text), "message": first_line}}

    # 3. Allow-listed adapters (only these may assert success/error from the body).
    if tool in ADAPTERS and text is not None:
        data = _json_or_none(text)
        if isinstance(data, dict):
            if tool == "td_validate":
                return _validate(data)
            if tool == "td_build_project":
                return _build_result(data)
            if tool == "td_build_status":
                return _build_status(data)

    # 4. Everything else — including td_convert, hybrid_search, all read tools, and
    #    ImageContent returns — is honestly unknown.
    return {"outcome": "unknown"}


# --------------------------------------------------------------------------- #
# Envelope readers (type-checked, read-only)
# --------------------------------------------------------------------------- #
def _text_of(result):
    """The text of a single-TextContent envelope, or None.

    ImageContent has ``.data``/``.mimeType`` and NO ``.text`` — never blindly index
    ``result[0].text``. An empty list or a non-text first element -> None -> unknown.
    """
    if not isinstance(result, (list, tuple)) or not result:
        return None
    first = result[0]
    if getattr(first, "type", None) != "text":
        return None
    t = getattr(first, "text", None)
    return t if isinstance(t, str) else None


def _json_or_none(text):
    try:
        return json.loads(text)   # a fresh object; the envelope is never mutated
    except (ValueError, TypeError):
        return None


def _last_exc_type(traceback_text):
    """Best-effort exception class name from the last "Xxx: msg" line of a traceback."""
    for line in reversed(traceback_text.splitlines()):
        line = line.strip()
        if not line:
            continue
        head = line.split(":", 1)[0].strip()
        if head and head.replace(".", "").replace("_", "").isalnum() and head[0].isalpha():
            return head.split(".")[-1]
        break
    return "Exception"


# --------------------------------------------------------------------------- #
# Adapters
# --------------------------------------------------------------------------- #
def _validate(d):
    # No `valid` key => the {error,...} / {status:NOT_IMPLEMENTED} / plaintext paths.
    # Conservative: unknown, never crash on the missing key.
    if "valid" not in d:
        return {"outcome": "unknown"}
    valid = bool(d.get("valid"))
    if valid:
        return {"outcome": "success", "artifact": {"toe_valid": True}}
    msgs = [e.get("message") for e in (d.get("errors") or [])
            if isinstance(e, dict) and e.get("message")]
    return {
        "outcome": "error",
        "event_type": "validation_error",
        "artifact": {"toe_valid": False, "validation_errors": msgs},
        "description": ("; ".join(msgs)[:_MAX_DESC] or None),
    }


def _build_result(d):
    """Classify a build RESULT envelope (td_build_project return, or the nested
    ``result`` of a done td_build_status snapshot)."""
    raw = str(d.get("status", "")).strip()
    low = raw.lower()
    if low == "success":
        return {"outcome": "success", "artifact": {"toe_valid": True}, "status": raw}
    if low == "started":
        # Async build dispatched; the real outcome comes from td_build_status.
        return {"outcome": "unknown", "status": raw}
    if low == "error":
        msg = d.get("message") or ""
        return {"outcome": "error", "event_type": "build_failure",
                "description": (str(msg)[:_MAX_DESC] or None), "status": raw}
    return {"outcome": "unknown", "status": (raw or None)}


def _build_status(d):
    """Classify a td_build_status snapshot. Distinguishes (by structure, not case
    alone) a completed-but-failed build, a worker crash, and a bad-lookup error."""
    raw = str(d.get("status", "")).strip()
    low = raw.lower()

    if low == "done":
        res = d.get("result")
        if isinstance(res, dict):
            return _build_result(res)          # <-- descend: done+result.ERROR is a FAILURE
        return {"outcome": "unknown", "status": raw}

    if low == "running":
        return {"outcome": "unknown", "status": raw}

    if low == "error":
        # Two source shapes share the lowercased token:
        #   worker crash        -> {status:"error", error, traceback, finished}
        #   bad job-id / no arg -> {status:"ERROR", message}  (a lookup error, NOT a build failure)
        has_crash = ("traceback" in d) or ("error" in d)
        is_lookup = ("message" in d) and not has_crash and ("result" not in d)
        if is_lookup:
            return {"outcome": "unknown", "status": raw}
        msg = d.get("error") or d.get("message") or ""
        return {"outcome": "error", "event_type": "build_failure",
                "description": (str(msg)[:_MAX_DESC] or None), "status": raw}

    return {"outcome": "unknown", "status": (raw or None)}

"""Output budgets for the two flood-prone offline tools (W4b, audit cluster C3).

Two `td-builder` tools can blow past the model's context window:

  * ``expand_toe_file(mode='full')`` returns the complete *lossless* JSON (operators
    + raw files + ``.toc``) so it round-trips back into a ``.toe.dir``. On a large
    project this is megabytes.
  * ``hybrid_search`` returns ranked hits, and the handler enriches each hit with the
    operator's full ``wiki_parameters`` — for a heavy op across several results that
    balloons the envelope.

These are *pure* helpers (no MCP / KB / TD imports) so they unit-test in isolation in
the PR CI lane. When output is over budget they replace the flood with an explicit,
non-silent signal — the same "never a silent truncation, always report the omitted
count" rule as ``_collapse_seq_params`` in mcp_server.py.

Caps are env-tunable and default *far* above any normal artifact, so typical calls
are returned byte-identical and the eval / acceptance suites see zero behavioral
change. The truncation signal always lives in a **non-error** field so the agent-eval
scorer's ``_envelope_ok`` keeps treating a truncated-but-valid result as success.
"""
import json
import os


def _cap(env_name: str, default: int) -> int:
    """Read an int byte-cap from the environment, ignoring blank/garbage values."""
    raw = os.environ.get(env_name, "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return default


# Generous defaults: a normal component/query serialises well under these; only a
# genuinely huge network or heavy multi-result enrichment trips the budget.
EXPAND_FULL_MAX_BYTES = _cap("TD_EXPAND_FULL_MAX_BYTES", 256 * 1024)     # 256 KB
HYBRID_SEARCH_MAX_BYTES = _cap("TD_HYBRID_SEARCH_MAX_BYTES", 96 * 1024)  # 96 KB

# Stage-3 shed: chars of a hit's `content` snippet kept (enough for the
# operator-identifying lead sentence; the omitted length is always reported).
SHED_CONTENT_KEEP = 280


def sized(obj) -> int:
    """Serialized UTF-8 byte length under the same encoder the handlers use."""
    return len(json.dumps(obj, default=str, ensure_ascii=False).encode("utf-8"))


def budget_full_expand(data, max_bytes: int = EXPAND_FULL_MAX_BYTES):
    """Cap ``expand_toe_file(mode='full')`` output.

    Returns ``(payload, truncated, info)``.

    * Under budget → ``(data, False, {})`` — returned unchanged (byte-identical).
    * Over budget → a compact stub (NOT a partial lossless blob, which would be a
      *broken* round-trip) plus ``truncated=True``. The caller keeps ``ok=True`` and
      flags ``meta['truncated']``.
    """
    if not isinstance(data, dict):
        return data, False, {}
    size = sized(data)
    if size <= max_bytes:
        return data, False, {}

    ops = data.get("operators")
    node_count = len(ops) if isinstance(ops, (list, dict)) else None
    info = {"full_bytes": size, "max_bytes": max_bytes, "node_count": node_count}
    stub = {
        "_truncated": True,
        "full_bytes": size,
        "max_bytes": max_bytes,
        "node_count": node_count,
        "reason": (
            f"full lossless JSON is {size} bytes, over the {max_bytes}-byte "
            f"output budget"
        ),
        "hint": (
            "Truncating lossless JSON would break its round-trip, so it is withheld. "
            "Use mode='summary' for an inline node/connection map, or pass an "
            "already-expanded .toe.dir/.tox.dir and read the lossless files from disk."
        ),
    }
    return stub, True, info


def budget_hybrid_results(results, max_bytes: int = HYBRID_SEARCH_MAX_BYTES):
    """Cap ``hybrid_search`` output by shedding per-result enrichment in stages.

    Returns ``(results, truncated)``.

    * Under budget → returned unchanged.
    * Over budget → degrade toward the COMPACT hit shape, never the legacy
      (pre-W-C) one: the W-C fidelity fields — ``parameter_names`` (the full
      post-collapse name list), ``score_kind`` and ``parameters_capped`` — survive
      EVERY stage, as does the TRUE ``parameter_count``. Stages, with the envelope
      re-measured between each so later stages fire only when still needed:

        1. strip the heavy hydrated ``parameters`` dicts (exactly the compact
           shape), leaving a ``{parameters_omitted, parameter_count}`` marker;
        2. slim ``relationships`` values to name level — ``sample_examples``
           payloads become an ``examples_omitted`` count, hydrated
           ``common_parameters`` become ``common_parameter_names``;
        3. trim each hit's ``content`` to a ``SHED_CONTENT_KEEP``-char stub with
           an explicit ``content_chars_omitted`` count.

      ``semantic_results`` is never dropped or emptied — the ranked hits (names,
      metadata, scores, W-C fidelity fields) survive — and every stage applied is
      reported in the top-level non-error ``_truncation`` signal. (Preserves the
      ``test_p03`` contract.)
    """
    if not isinstance(results, dict):
        return results, False
    if sized(results) <= max_bytes:
        return results, False

    raw_hits = results.get("semantic_results")
    hits = [h for h in raw_hits if isinstance(h, dict)] if isinstance(raw_hits, list) else []
    stages = []

    # Stage 1 — drop the hydrated parameter dicts (the compact shape). The W-C
    # fidelity fields are deliberately NOT touched: a shed envelope must still
    # answer "which params exist" / "how were these scored" without a follow-up.
    stripped = 0
    for h in hits:
        if "parameters" not in h:
            continue
        pc = h.get("parameter_count")
        if pc is None and isinstance(h.get("parameters"), (list, dict)):
            pc = len(h["parameters"])
        h.pop("parameters", None)
        h.pop("ground_truth_param_count", None)
        h["parameters_omitted"] = True
        if pc is not None:
            h["parameter_count"] = pc
        stripped += 1
    if stripped:
        stages.append(f"parameters omitted from {stripped} hit(s)")

    # Stage 2 — relationships enrichment down to name level. Fires when stage 1
    # was not enough, or could not fire at all (an oversized compact-mode
    # envelope has no per-hit `parameters` to shed).
    if sized(results) > max_bytes:
        rels = results.get("relationships")
        slimmed = 0
        if isinstance(rels, dict):
            for rel in rels.values():
                if not isinstance(rel, dict):
                    continue
                touched = False
                examples = rel.get("sample_examples")
                if isinstance(examples, list):
                    rel.pop("sample_examples")
                    rel["examples_omitted"] = len(examples)
                    touched = True
                common = rel.get("common_parameters")
                if isinstance(common, dict):
                    rel.pop("common_parameters")
                    rel["common_parameter_names"] = list(common)
                    touched = True
                slimmed += touched
        if slimmed:
            stages.append(f"relationship enrichment slimmed on {slimmed} operator(s)")

    # Stage 3 — trim hit content to a stub. Last resort: content is the grounding
    # snippet the caller reads, so it goes only when the envelope is still over.
    if sized(results) > max_bytes:
        trimmed = 0
        for h in hits:
            c = h.get("content")
            if isinstance(c, str) and len(c) > SHED_CONTENT_KEEP:
                h["content_chars_omitted"] = len(c) - SHED_CONTENT_KEEP
                h["content"] = c[:SHED_CONTENT_KEEP] + " …"
                trimmed += 1
        if trimmed:
            stages.append(f"content trimmed to {SHED_CONTENT_KEEP} chars on {trimmed} hit(s)")

    results["_truncation"] = {
        "truncated": True,
        "reason": (
            f"result envelope exceeded the {max_bytes}-byte output budget; "
            + ("; ".join(stages) if stages else "no sheddable enrichment found")
        ),
        "hint": (
            "Call get_operator_info(operator_name, compact=false) or "
            "get_parameter_detail(operator_name, parameter_name) for full parameters. "
            "Per-hit parameter_names / score_kind / parameters_capped are never shed."
        ),
    }
    return results, True

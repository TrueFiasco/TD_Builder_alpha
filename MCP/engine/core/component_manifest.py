"""Component interface manifest — shared by the MCP server and the offline builder.

`component_manifest` moved here verbatim from mcp_server.py (BUG-3): the offline builder
(toe_builder_bridge) must manifest-parse an `external_tox` component at build time to
resolve its inner in/out op names, and importing the server module from the builder would
be circular (mcp_server imports ToeBuilderBridge). mcp_server re-exports it under its
original `_component_manifest` name.

`manifest_from_tox` is the build-time acquisition path: toeexpand a .tox (or accept an
already-expanded .dir), parse it losslessly, and return the manifest plus the inner root
type and wrapper subcompname. Failures carry a machine-readable `kind` so callers can map
them to distinct user-facing messages.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

# toeexpand hang-guard for the BUILD path. 120s matched the harvest offline phase across
# all 277 shipped palette items with zero timeouts; the interactive expand_toe_file tool
# keeps its own, longer budget.
EXTERNAL_MANIFEST_TIMEOUT_S = 120


class ComponentManifestError(Exception):
    """Manifest acquisition failed. `kind` is one of:
    tool_missing | timeout | expand_failed | parse_failed."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def parm_quoted_fields(line: str):
    """Quote-aware field scanner for TD's .parm/.cparm serialization:
    ``[(field, was_quoted)]``. Fields are whitespace-separated; a field
    containing spaces is quote-wrapped (double AND single quoting both occur:
    "Blur Size", 'none'), and an embedded quote of the ACTIVE kind is escaped
    as \\q (ground truth: masterRadioMenu.tox 'Menulabels'/'Tableformat',
    TD 2025.32820) — which unescapes to the bare quote. Every other backslash
    is literal (Windows-path values survive verbatim; the other quote kind is
    embedded UNescaped, e.g. "x == 'y'"). Unknown residual: a quoted value
    ENDING in a literal backslash would need \\\\" from TD — no such sample
    exists in the 2025.32820 palette, so that shape stays unspecified.

    SINGLE SOURCE for the quoting convention (A1/A2): the Δ7 .cparm tokenizer
    in kb_build/user_components binds to this same function — do not fork."""
    toks = []
    i, n = 0, len(line)
    while i < n:
        ch = line[i]
        if ch in " \t":
            i += 1
            continue
        if ch in "\"'":
            q = ch
            i += 1
            buf = []
            while i < n:
                c = line[i]
                if c == "\\" and i + 1 < n and line[i + 1] == q:
                    buf.append(q)          # \q -> embedded quote
                    i += 2
                    continue
                if c == q:                 # closing quote
                    i += 1
                    break
                buf.append(c)
                i += 1
            # unterminated quote: the accumulated rest is taken verbatim
            toks.append(("".join(buf), True))
        else:
            j = i
            while j < n and line[j] not in " \t":
                j += 1
            toks.append((line[i:j], False))
            i = j
    return toks


def _parm_effective_constant(raw: str, first_field_only: bool = False) -> str:
    """Effective saved CONSTANT from a .parm value tail (A2). The lossless
    parser splits .parm lines on whitespace only, so a quoted constant with
    spaces reaches us either truncated at its first space (expression modes:
    the remainder glued onto the expression payload) or with its quote
    wrapping intact (constant modes hold the raw tail). Re-scan with the
    quote-aware field scanner and return the first field (expression modes) /
    the sole field (constant modes); fall back to the input verbatim when the
    shape is not confidently recoverable. Caveat: rejoining value+expression
    collapses a whitespace RUN at the first field boundary to one space (the
    parser discarded the raw line); palette ground-truth values carry single
    spaces only."""
    fields = parm_quoted_fields(raw)
    if not fields:
        return raw
    if first_field_only or len(fields) == 1:
        return fields[0][0]
    return raw


def _engine_imports():
    """Lazy-import the engine-rooted dependencies (parsers/, paths).

    This module may be loaded by absolute file path from contexts where MCP/engine is not
    on sys.path (the builder's unit tests add only repo root + server_core). Repo root IS
    reliably importable there (the bridge does `from paths import ...`), so fall back to
    the canonical bootstrap."""
    try:
        from parsers.lossless_parser import parse_toe_lossless
        from paths import resolve_td_tool, td_tool_missing_error
    except ImportError:
        import bootstrap
        bootstrap.setup()
        from parsers.lossless_parser import parse_toe_lossless
        from paths import resolve_td_tool, td_tool_missing_error
    return parse_toe_lossless, resolve_td_tool, td_tool_missing_error


def component_manifest(network) -> dict:
    """Extract a reusable component's interface (Round-4 #1b).

    A component .tox exposes its inputs/outputs via in/out operators. Connectors are
    matched by op-type family suffix (`:in`/`:out`) ONLY — names are reporting-only, so
    an op merely NAMED `in5` or `integrate1` is never a phantom connector. inputs/outputs
    are scoped to the DIRECT children of the interface COMP: normally the root COMP, but
    a Derivative palette wrapper (connector-less root + icon/help + same-name inner COMP)
    redirects to the inner comp — previously every nested in*/out* at any depth leaked in
    (a wrapper tox reported 14 bogus inputs). families and op/connection counts stay
    whole-network. The manifest lets an LLM wire a component referenced via `external_tox`
    without re-expanding it. Surfaced as the `manifest` field of
    expand_toe_file(mode='summary')."""
    ops, families = [], {}
    for op in network.operators:
        ot = op.op_type or (f"{op.family.value}:{op.type}" if getattr(op, "family", None)
                            else getattr(op, "type", "")) or ""
        path = op.path.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        fam = ot.split(":")[0] if ":" in ot else ""
        if fam:
            families[fam] = families.get(fam, 0) + 1
        ops.append({
            "path": path,
            "parent": path.rsplit("/", 1)[0],   # "" for depth-1 ops
            "name": path.split("/")[-1],
            "base": ot.split(":")[-1].lower() if ":" in ot else ot.lower(),
            "fam": fam.upper(),
            "op_type": ot,
            "depth": path.count("/"),
        })

    # Interface COMP: the root COMP. For a parsed .toe prefer the declared root
    # (metadata.root_comp, usually project1) so utility trees like /local can't win
    # the tie-break; otherwise the shallowest COMP, ties broken by most descendants.
    root = None
    comps = [o for o in ops if o["fam"] == "COMP"]
    if comps:
        if getattr(getattr(network, "metadata", None), "mode", None) == "toe":
            root_name = getattr(network.metadata, "root_comp", None) or "project1"
            root = next((o for o in comps if o["depth"] == 1 and o["name"] == root_name), None)
        if root is None:
            min_depth = min(o["depth"] for o in comps)
            top = [o for o in comps if o["depth"] == min_depth]
            root = max(top, key=lambda c: sum(
                1 for o in ops if o["path"].startswith(c["path"] + "/")))

    wrapper = False
    if root is not None:
        scope = root["path"]
        direct = [o for o in ops if o["parent"] == scope]
        # Wrapper redirect ONLY when the root has no connectors of its own — a root
        # with real in/out children is the interface even if a same-name child exists.
        if not any(o["base"] in ("in", "out") for o in direct):
            inner = next((o for o in direct
                          if o["fam"] == "COMP" and o["name"] == root["name"]), None)
            if inner is not None:
                scope, wrapper = inner["path"], True
    elif ops:
        # No COMP in the list (already-scoped fragment): direct children of the
        # shallowest level are the interface candidates.
        scope = min(ops, key=lambda o: o["depth"])["parent"]
    else:
        scope = ""

    inputs = [{"name": o["name"], "op_type": o["op_type"]}
              for o in ops if o["parent"] == scope and o["base"] == "in"]
    outputs = [{"name": o["name"], "op_type": o["op_type"]}
               for o in ops if o["parent"] == scope and o["base"] == "out"]
    inputs.sort(key=lambda x: x["name"])
    outputs.sort(key=lambda x: x["name"])
    return {
        "inputs": inputs,
        "outputs": outputs,
        "families": families,
        "operator_count": len(network.operators),
        "connection_count": len(network.connections),
        "interface_path": scope,
        "wrapper": wrapper,
        "summary": (f"{len(network.operators)} operators, {len(network.connections)} connections; "
                    f"inputs={[i['name'] for i in inputs]}, outputs={[o['name'] for o in outputs]}"
                    + (f" (wrapper: interface at {scope})" if wrapper else "")),
    }


def offline_entry(manifest: dict, inner_type: str, *, source: str, tox_path: str,
                  category: str = None, subcompname: str = None) -> dict:
    """Registry entry (KB/palette_components.json item schema) built from an OFFLINE
    manifest — shared by the palette harvest's offline phase and the user registration
    script. Indexes are enumerate()-assigned over the manifest's NAME-SORTED lists, so
    they are NOT connector order: consumers must stamp entry["harvest"]["method"]
    accordingly ("offline_manifest" -> the builder applies the strict name-authority
    wiring policy; the shipped registry's live phase overwrites with connector truth
    and stamps "offline_manifest+live")."""
    entry = {
        "source": source,
        "tox_path": tox_path,
    }
    if category is not None:
        entry["category"] = category
    entry.update({
        "wrapper": bool(manifest.get("wrapper")),
        "inner_type": inner_type or "COMP:base",
        "inputs": [{"index": n, "in_op": d["name"],
                    "family": (d.get("op_type") or "").split(":")[0]}
                   for n, d in enumerate(manifest.get("inputs", []))],
        "outputs": [{"index": n, "out_op": d["name"],
                     "family": (d.get("op_type") or "").split(":")[0]}
                    for n, d in enumerate(manifest.get("outputs", []))],
        "operator_count": manifest.get("operator_count"),
    })
    if entry["wrapper"] and subcompname:
        entry["subcompname"] = subcompname
    return entry


def manifest_from_tox(tox_path, timeout_s: int = EXTERNAL_MANIFEST_TIMEOUT_S) -> dict:
    """toeexpand + lossless-parse a .tox (or already-expanded .dir) and return
    `{"manifest": <component_manifest dict>, "inner_type": str, "subcompname": str|None,
    "contained_operators": [str], "interface_files": {"cparm": str|None,
    "parm_values": {name: str}}}`.

    `inner_type` is the op_type of the COMP at the manifest's interface_path (the token a
    placeholder .n would carry); `subcompname` is the wrapper's inner-comp leaf name when
    the manifest reports a wrapper, else None. Raises ComponentManifestError(kind=...) on
    every failure — callers decide whether that is fatal (wired component) or a warning.

    `contained_operators` (W7) is the sorted distinct op_type inventory scoped to the
    INTERFACE — ops strictly under interface_path, excluding the interface COMP itself —
    so wrapper icon/help plumbing never pollutes it. Computed here (the one place that
    holds both the parsed network and interface_path); `component_manifest()`'s own
    return is untouched, so expand_toe_file(mode='summary') is unaffected by
    construction.

    `interface_files` (W7 Δ7) carries the interface COMP's raw `.cparm` text (custom
    parameter DEFINITIONS live there) and its `.parm` VALUES (plain strings; non-default
    saved values live there) so the user-component engine can parse custom parameters
    without a second toeexpand. Multi-component/indexed .parm values are omitted
    (conservative).

    NOTE: the offline manifest name-sorts inputs/outputs — it is a NAME authority only,
    never a connector-index authority (index order ≠ name order on real comps)."""
    parse_toe_lossless, resolve_td_tool, td_tool_missing_error = _engine_imports()

    src = Path(tox_path)
    cleanup_dir = None
    try:
        if src.is_dir() and src.name.endswith(".dir"):
            toe_dir = src
        else:
            exe = resolve_td_tool("toeexpand")
            if not exe:
                raise ComponentManifestError("tool_missing", td_tool_missing_error("toeexpand"))
            work = Path(tempfile.mkdtemp(prefix="td_extmanifest_"))
            cleanup_dir = work
            local = work / src.name
            shutil.copy2(src, local)
            # toeexpand returns rc 1 even on success on some builds.
            try:
                proc = subprocess.run([str(exe), str(local)], cwd=str(work),
                                      capture_output=True, text=True, timeout=timeout_s)
            except subprocess.TimeoutExpired:
                raise ComponentManifestError(
                    "timeout", f"toeexpand exceeded {timeout_s}s on '{src}'")
            toe_dir = work / f"{src.name}.dir"
            if not toe_dir.exists():
                alts = list(work.glob("*.dir"))
                if not alts:
                    detail = (proc.stderr or proc.stdout or "").strip()[:300]
                    raise ComponentManifestError(
                        "expand_failed",
                        f"toeexpand produced no .dir output (rc={proc.returncode})"
                        + (f": {detail}" if detail else ""))
                toe_dir = alts[0]

        try:
            network = parse_toe_lossless(toe_dir, registry=None, verbose=False)
            man = component_manifest(network)
        except ComponentManifestError:
            raise
        except Exception as pe:
            raise ComponentManifestError("parse_failed", str(pe))

        # Inner root type: the op_type of the COMP at interface_path (harvest logic).
        inner_type = None
        iface_op = None
        scope = (man.get("interface_path") or "").rstrip("/")
        contained = set()
        for op in network.operators:
            p = op.path.rstrip("/")
            if not p.startswith("/"):
                p = "/" + p
            if p == scope:
                inner_type = op.op_type or None
                iface_op = op
            elif scope and p.startswith(scope + "/") and op.op_type:
                contained.add(op.op_type)

        # Interface COMP extra files (W7 Δ7): raw .cparm text + flat .parm values.
        cparm_text = None
        parm_values = {}
        if iface_op is not None:
            cf = (getattr(iface_op, "extra_files", None) or {}).get("cparm")
            if cf is not None and not getattr(cf, "is_binary", False):
                cparm_text = cf.content
            for pname, pval in (getattr(iface_op, "parameters", None) or {}).items():
                # A2: undo the lossless parser's whitespace-only split before a
                # value becomes a durable user-facing default — a quoted
                # constant with spaces must not commit truncated/quote-mangled
                # (moviePlayer.tox 'File'). Expression preference for
                # expression-mode pars is deliberately NOT taken here (AM4).
                if isinstance(pval, str):
                    parm_values[pname] = _parm_effective_constant(pval)
                elif hasattr(pval, "value") and isinstance(getattr(pval, "value"), str):
                    expr = getattr(pval, "expression", None)
                    raw = pval.value + (" " + expr
                                        if isinstance(expr, str) and expr else "")
                    parm_values[pname] = _parm_effective_constant(
                        raw, first_field_only=True)
                # indexed/dict component values: omitted (conservative)

        return {
            "manifest": man,
            "inner_type": inner_type or "COMP:base",
            "subcompname": scope.split("/")[-1] if man.get("wrapper") else None,
            "contained_operators": sorted(contained),
            "interface_files": {"cparm": cparm_text, "parm_values": parm_values},
        }
    finally:
        if cleanup_dir is not None:
            shutil.rmtree(cleanup_dir, ignore_errors=True)

"""Harvest the palette component registry (KB/palette_components.json).

Three phases (run all, or one at a time — intermediates persist in --workdir):

  offline   Enumerate <TD>/Samples/Palette/**/*.tox, toeexpand + parse each one
            (no TouchDesigner session needed) and extract interface metadata via
            the server's wrapper-aware _component_manifest: wrapper flag,
            subcompname (inner comp name), inner root type, in/out op names +
            families. Joined with palette_semantic_catalog.yaml seed fields.
  live      Verify every item through the ACTUAL product mechanism against the
            running TD (placeholder COMP + enableexternaltox + externaltox +
            subcompname): load success, retyped OPType, custom par pages, and
            the TRUE connector-index order via inputConnectors[i].inOP /
            outputConnectors[i].outOP (authoritative over the offline
            name-sorted order). Failures become the skip-list.
            GOTCHA: reinitnet MUST be pulsed via td.run(..., delayFrames=N) —
            a synchronous pulse inside the webserver exec handler dies with
            'error return without exception set' (the load still happens, but
            the response is lost).
  assemble  Merge (live wins over offline where both speak), write
            KB/palette_components.json. Live-failing items land in a "skipped"
            section with reasons, not in "components".

Usage (py -3.11, repo root):
    python kb_build/harvest_palette_components.py --phase all
    python kb_build/harvest_palette_components.py --phase live --batch-size 12
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import bootstrap  # noqa: E402

bootstrap.setup()

from paths import resolve_td_tool, KB_PALETTE_COMPONENTS  # noqa: E402

TD_API_URL = "http://127.0.0.1:9981"
TOKEN_FILE = Path.home() / ".td_builder" / "api_token"
CATALOG = REPO / "Agents" / "expertise" / "palette_semantic_catalog.yaml"
SEED_FIELDS = ("purpose", "use_cases", "has_ui", "wiki_url")
EXPAND_TIMEOUT_S = 120


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def _load_manifest_fn():
    """Import the offline server module for its _component_manifest (DRY: the
    wrapper-redirect scoping logic lives there and is gate-covered)."""
    import importlib.util
    server_path = REPO / "MCP" / "server_core" / "mcp_server.py"
    spec = importlib.util.spec_from_file_location("td_builder_mcp_server_harvest", str(server_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    if sys.__stdout__ is not None:
        sys.stdout = sys.__stdout__  # the server redirects stdout at import
    return mod._component_manifest


def _samples_palette_dir() -> Path:
    """The RUNNING TD's palette dir (what the emitted app.samplesFolder expression
    will actually resolve to). Asks the live server first — machines routinely have
    several installs and resolve_td_tool's glob can pick a different one (an
    unversioned 'TouchDesigner\\' dir sorts AFTER versioned ones). Falls back to
    toeexpand's install folder when TD isn't running."""
    try:
        r = _td_exec("print(app.samplesFolder)", timeout=15.0)
        if r.get("success"):
            pal = Path(r["data"]["stdout"].strip()) / "Palette"
            if pal.exists():
                return pal
    except Exception as e:  # noqa: BLE001
        print(f"[warn] live samplesFolder unavailable ({e}); falling back to toeexpand")
    exe = resolve_td_tool("toeexpand")
    if exe is None:
        raise SystemExit("toeexpand not found — install TouchDesigner or set TD_BIN_DIR")
    pal = exe.parent.parent / "Samples" / "Palette"
    if not pal.exists():
        raise SystemExit(f"palette dir not found next to toeexpand: {pal}")
    return pal


def _catalog_seeds() -> dict:
    try:
        import yaml
        with open(CATALOG, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data.pop("_metadata", None)
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}
    except Exception as e:  # seeds are enrichment, never a blocker
        print(f"[warn] catalog seeds unavailable: {e}")
        return {}


def _td_exec(script: str, timeout: float = 120.0) -> dict:
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    body = json.dumps({"script": script}).encode("utf-8")
    req = urllib.request.Request(
        TD_API_URL + "/api/td/server/exec", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + token}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# phase: offline
# ---------------------------------------------------------------------------

def phase_offline(workdir: Path) -> None:
    manifest_fn = _load_manifest_fn()
    from parsers.lossless_parser import parse_toe_lossless

    pal = _samples_palette_dir()
    exe = resolve_td_tool("toeexpand")
    seeds = _catalog_seeds()

    items, errors, dupes = {}, {}, []
    tox_files = sorted(pal.rglob("*.tox"))
    print(f"[offline] {len(tox_files)} .tox under {pal}")

    for i, tox in enumerate(tox_files):
        rel = tox.relative_to(pal).as_posix()
        stem = tox.stem
        key = stem
        if key in items:
            key = f"{rel.split('/')[0]}/{stem}"   # category-qualified on collision
            dupes.append(key)
        work = Path(tempfile.mkdtemp(prefix="pal_h_"))
        try:
            local = work / tox.name
            shutil.copy2(tox, local)
            proc = subprocess.run([str(exe), str(local)], cwd=str(work),
                                  capture_output=True, text=True, timeout=EXPAND_TIMEOUT_S)
            toe_dir = work / f"{tox.name}.dir"
            if not toe_dir.exists():
                alts = list(work.glob("*.dir"))
                if not alts:
                    raise RuntimeError(f"toeexpand produced no .dir (rc={proc.returncode})")
                toe_dir = alts[0]
            network = parse_toe_lossless(toe_dir, registry=None, verbose=False)
            man = manifest_fn(network)

            # inner root type: the op_type of the COMP at interface_path
            inner_type = None
            scope = (man.get("interface_path") or "").rstrip("/")
            for op in network.operators:
                p = op.path.rstrip("/")
                if not p.startswith("/"):
                    p = "/" + p
                if p == scope:
                    inner_type = op.op_type or None
                    break

            entry = {
                "source": "derivative",
                "tox_path": rel,
                "category": rel.split("/")[0],
                "wrapper": bool(man.get("wrapper")),
                "inner_type": inner_type or "COMP:base",
                "inputs": [{"index": n, "in_op": d["name"],
                            "family": (d.get("op_type") or "").split(":")[0]}
                           for n, d in enumerate(man.get("inputs", []))],
                "outputs": [{"index": n, "out_op": d["name"],
                             "family": (d.get("op_type") or "").split(":")[0]}
                            for n, d in enumerate(man.get("outputs", []))],
                "operator_count": man.get("operator_count"),
            }
            if entry["wrapper"]:
                entry["subcompname"] = scope.split("/")[-1]
            seed = seeds.get(stem) or {}
            for f in SEED_FIELDS:
                if seed.get(f) is not None:
                    entry[f] = seed[f]
            items[key] = entry
        except Exception as e:  # noqa: BLE001 — per-item isolation
            errors[key] = f"{type(e).__name__}: {e}"
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if (i + 1) % 25 == 0:
            print(f"[offline] {i + 1}/{len(tox_files)} done ({len(errors)} errors)")

    out = {"palette_dir": str(pal), "items": items, "errors": errors, "dupes": dupes}
    (workdir / "offline.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[offline] DONE: {len(items)} parsed, {len(errors)} errors, "
          f"{len(dupes)} name collisions -> {workdir / 'offline.json'}")


# ---------------------------------------------------------------------------
# phase: live
# ---------------------------------------------------------------------------

_LIVE_CREATE = """
import json as _json
h = op('/pal_harvest')
if h:
    h.destroy()
h = root.create(td.baseCOMP, 'pal_harvest')
spec = _json.loads('''{payload}''')
made = []
k = 0
for nm, cfg in spec.items():
    ph = h.create(td.baseCOMP, nm)
    ph.par.externaltox = cfg['tox']
    ph.par.enableexternaltox = 1
    if cfg.get('subcompname'):
        ph.par.subcompname = cfg['subcompname']
    td.run("op('/pal_harvest/" + nm + "').par.reinitnet.pulse()", delayFrames=5 + k * 2)
    made.append(nm)
    k += 1
print(_json.dumps({{'made': made}}))
"""

_LIVE_INSPECT = """
import json as _json
h = op('/pal_harvest')
res = {}
for ph in h.children:
    ins = []
    for con in ph.inputConnectors:
        inner = con.inOP
        ins.append({'index': con.index,
                    'in_op': inner.name if inner else None,
                    'family': inner.family if inner else None})
    outs = []
    for con in ph.outputConnectors:
        inner = con.outOP
        outs.append({'index': con.index,
                     'out_op': inner.name if inner else None,
                     'family': inner.family if inner else None})
    pages = []
    for p in ph.customPages:
        pages.append(p.name)
    res[ph.name] = {'children': len(ph.children), 'optype': ph.OPType,
                    'inputs': ins, 'outputs': outs, 'custom_pages': pages}
h.destroy()
print('@@PAL@@' + _json.dumps(res) + '@@END@@')
"""


def _live_batch(batch: dict, settle_s: float, timeout: float = 60.0) -> dict:
    payload = json.dumps(batch).replace("\\", "\\\\").replace("'", "\\'")
    r = _td_exec(_LIVE_CREATE.format(payload=payload), timeout=timeout)
    if not r.get("success"):
        raise RuntimeError(f"create failed: {r.get('error')}")
    time.sleep(settle_s)
    r = _td_exec(_LIVE_INSPECT, timeout=timeout)
    if not r.get("success"):
        raise RuntimeError(f"inspect failed: {r.get('error')}")
    # Sentinel-delimited: chatty components print to stdout while loading/destroying,
    # so the response is NOT guaranteed to be bare JSON (seen: synchroFrameOut,
    # tdAbletonPackage).
    stdout = r["data"]["stdout"]
    start = stdout.rfind("@@PAL@@")
    end = stdout.rfind("@@END@@")
    if start < 0 or end < start:
        raise RuntimeError(f"inspect output missing sentinels: {stdout[:200]!r}")
    return json.loads(stdout[start + len("@@PAL@@"):end])


def phase_live(workdir: Path, batch_size: int) -> None:
    off = json.loads((workdir / "offline.json").read_text(encoding="utf-8"))
    pal = Path(off["palette_dir"])
    items = off["items"]

    # Resumable: partial results persist after every batch; done keys are skipped.
    # 'did not populate' skips are RETRIED on resume: a degrading/crashed TD fails
    # external-tox loads silently (observed live: a 60-item zero-children run before
    # a crash), so zero-children is only trustworthy from a healthy session.
    partial_path = workdir / "live_partial.json"
    results, skips = {}, {}
    if partial_path.exists():
        prev = json.loads(partial_path.read_text(encoding="utf-8"))
        results, skips = prev.get("results", {}), prev.get("skips", {})
        retry = [k for k, v in skips.items()
                 if "did not populate" in v or "JSONDecodeError" in v]
        for k in retry:
            skips.pop(k)
        print(f"[live] resuming: {len(results)} done, {len(skips)} skipped, "
              f"{len(retry)} zero-children retried")
    keys = [k for k in sorted(items.keys()) if k not in results and k not in skips]
    print(f"[live] verifying {len(keys)} items, batch={batch_size}")

    def _save_partial():
        partial_path.write_text(json.dumps({"results": results, "skips": skips}),
                                encoding="utf-8")

    def _run_one_key(key: str):
        entry = items[key]
        nm = "itm0"
        cfg = {nm: {"tox": (pal / entry["tox_path"]).as_posix(),
                    "subcompname": entry.get("subcompname")}}
        got = _live_batch(cfg, settle_s=1.5, timeout=45.0)
        return got.get(nm)

    i = 0
    all_zero_streak = 0
    while i < len(keys):
        chunk = keys[i:i + batch_size]
        cfg, name_map = {}, {}
        for n, key in enumerate(chunk):
            nm = f"itm{n}"
            name_map[nm] = key
            cfg[nm] = {"tox": (pal / items[key]["tox_path"]).as_posix(),
                       "subcompname": items[key].get("subcompname")}
        t0 = time.time()
        try:
            got = _live_batch(cfg, settle_s=1.0 + 0.15 * len(chunk))
            for nm, key in name_map.items():
                results[key] = got.get(nm)
            # TD-health circuit breaker: a whole batch of zero-children loads means
            # TD has stopped loading external toxes (degradation precedes crashes) —
            # results from here on would be garbage. Stop; resume retries them.
            batch_zero = all(
                not (got.get(nm) or {}).get("children") for nm in name_map)
            all_zero_streak = all_zero_streak + 1 if batch_zero else 0
            if all_zero_streak >= 2:
                _save_partial()
                raise SystemExit(
                    f"[live] ABORT: {all_zero_streak} consecutive all-zero batches — "
                    "TouchDesigner has likely stopped loading external toxes. "
                    "Restart TD and re-run --phase live (zero-children items retry).")
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001 — isolate the poison item(s)
            print(f"[live] batch at {i} failed ({e}); retrying singly")
            for key in chunk:
                try:
                    results[key] = _run_one_key(key)
                except Exception as e1:  # noqa: BLE001
                    skips[key] = f"live exec failed: {type(e1).__name__}: {e1}"
        i += batch_size
        _save_partial()
        print(f"[live] {min(i, len(keys))}/{len(keys)} ({len(skips)} skipped, "
              f"batch {time.time() - t0:.1f}s)", flush=True)

    for key, got in list(results.items()):
        if got is None:
            skips[key] = "placeholder missing after batch (create failed?)"
            results.pop(key)
        elif not got.get("children"):
            skips[key] = "external tox did not populate (0 children after reinit)"
            results.pop(key)
    _save_partial()

    out = {"results": results, "skips": skips}
    (workdir / "live.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[live] DONE: {len(results)} loaded, {len(skips)} skipped -> {workdir / 'live.json'}")


# ---------------------------------------------------------------------------
# phase: assemble
# ---------------------------------------------------------------------------

def phase_assemble(workdir: Path) -> None:
    off = json.loads((workdir / "offline.json").read_text(encoding="utf-8"))
    live = json.loads((workdir / "live.json").read_text(encoding="utf-8"))
    today = date.today().isoformat()

    components, skipped = {}, {}
    for key, reason in off.get("errors", {}).items():
        skipped[key] = f"offline: {reason}"
    for key, reason in live.get("skips", {}).items():
        skipped[key] = f"live: {reason}"

    for key, entry in off["items"].items():
        got = live["results"].get(key)
        if got is None:
            skipped.setdefault(key, "no live verification result")
            continue
        # live connector truth (index order + families) wins over offline name-sort
        ins = [d for d in got.get("inputs", []) if d.get("in_op")]
        outs = [d for d in got.get("outputs", []) if d.get("out_op")]
        entry["inputs"] = ins or entry["inputs"]
        entry["outputs"] = outs or entry["outputs"]
        # inner_type stays the OFFLINE parser-read token: that is the on-disk .n
        # token (COMP:cam, COMP:geo, ...), which live OPType does NOT map to by
        # name (cameraCOMP != COMP:camera — the token-vs-OPType trap). Live OPType
        # is recorded as a consistency signal only.
        optype = got.get("optype") or ""
        if optype:
            entry["live_optype"] = optype
        if got.get("custom_pages"):
            entry["custom_pages"] = got["custom_pages"]
        entry["harvest"] = {"method": "offline_manifest+live", "td_build": "2025.32820",
                            "date": today}
        components[key] = entry

    spec = json.loads(KB_PALETTE_COMPONENTS.read_text(encoding="utf-8"))
    spec["components"] = components
    spec["skipped"] = skipped
    KB_PALETTE_COMPONENTS.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"[assemble] DONE: {len(components)} components, {len(skipped)} skipped "
          f"-> {KB_PALETTE_COMPONENTS}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=("offline", "live", "assemble", "all"), default="all")
    ap.add_argument("--batch-size", type=int, default=12)
    ap.add_argument("--workdir", type=Path,
                    default=Path(tempfile.gettempdir()) / "td_palette_harvest")
    args = ap.parse_args()
    args.workdir.mkdir(parents=True, exist_ok=True)
    if args.phase in ("offline", "all"):
        phase_offline(args.workdir)
    if args.phase in ("live", "all"):
        phase_live(args.workdir, args.batch_size)
    if args.phase in ("assemble", "all"):
        phase_assemble(args.workdir)


if __name__ == "__main__":
    main()

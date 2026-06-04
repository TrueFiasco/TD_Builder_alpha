"""#1 Builder parameter-acceptance.

Build each operator with the engine builder (NetworkBuilder -> TOEBuilder
BASIC mode, the layer td_build_project wraps), re-parse the produced
`.toe.dir` with the LosslessParser, and diff the emitted parameter set
against the real-TouchDesigner answer key in
operator_ground_truth/params/*_defaults.json.

Why the engine builder and not the td_build_project tool: the tool *collapses*
to a binary `.tox` (needs TD's toecollapse) and deletes the expanded dir, so
parameter emission cannot be inspected offline. TOEBuilder BASIC writes the
inspectable `.toe.dir` and IS exactly the documented "unrecognized parameter"
weakness this target exists to measure and improve.

Metric (per operator, 0..1): |emitted ∩ ground-truth| / |ground-truth|.
Pure deterministic structure diff — no human, no LLM. Grouped by family so
the worst-case backlog points at which families' .parm emission to fix.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from measure import datasets
from measure.harness import CaseScore, emit


def _short_type(operator: str, family: str) -> str:
    """Mirror OperatorRegistry._extract_type_from_name: 'Ableton_Link_CHOP' +
    'CHOP' -> 'abletonlink' (the registry/build key the server expects)."""
    name = operator.replace("_", " ").strip()
    if name.endswith(f" {family}"):
        name = name[: -len(family) - 1]
    return name.lower().replace(" ", "")


def _find_artifact_dir(root: Path) -> Path | None:
    dirs = [p for p in root.rglob("*.dir") if p.is_dir()]
    if not dirs:
        return None
    # Prefer a .toe.dir / .tox.dir; otherwise the largest by file count.
    dirs.sort(key=lambda p: (p.suffixes[-2:] != [".toe", ".dir"]
                             and p.suffixes[-2:] != [".tox", ".dir"],
                             -sum(1 for _ in p.rglob("*"))))
    return dirs[0]


def _raw_parm_names(artifact_dir: Path, op_name: str) -> set[str]:
    """Parameter names straight from the operator's emitted `<op>.parm` file.

    More faithful than the LOSSLESS-tuned parser for measuring BASIC output:
    it reflects exactly what the builder wrote, so an empty/garbage .parm
    scores 0 (the documented weakness) rather than being masked.
    """
    names: set[str] = set()
    for p in artifact_dir.rglob(f"{op_name}.parm"):
        try:
            txt = p.read_text(encoding="latin-1")
        except OSError:
            continue
        for line in txt.splitlines():
            line = line.strip()
            if not line or line == "end" or line.startswith("?"):
                continue
            tok = line.split()[0]
            if tok and tok[0].isalpha():
                names.add(tok.lower())
    return names


def _emitted_params(artifact_dir: Path, family: str, td_type: str) -> set[str] | None:
    from parsers.lossless_parser import LosslessParser  # bootstrap'd by probe

    net = LosslessParser(str(artifact_dir)).parse(verbose=False)
    ops = list(net.operators)
    if not ops:
        return None
    fam = family.upper()
    cand = [o for o in ops
            if getattr(getattr(o, "family", None), "value", "") == fam
            or (o.type or "").lower() == td_type.lower()]
    pool = cand or ops
    pool.sort(key=lambda o: -len(getattr(o, "parameters", {}) or {}))
    chosen = pool[0]
    parsed = {str(k).lower() for k in (getattr(chosen, "parameters", {}) or {})}
    raw = _raw_parm_names(artifact_dir, getattr(chosen, "name", "op1") or "op1")
    return parsed | raw


def _build_toe_dir(out_dir: Path, fam: str, short: str) -> tuple[Path | None, str]:
    """Build a 1-op network with the engine. Returns (toe_dir | None, detail)."""
    from api.network_builder import NetworkBuilder  # bootstrap'd by probe

    try:
        b = NetworkBuilder("m", mode="toe")
        b.add_operator("op1", fam, short)
    except ValueError as exc:  # type not in OperatorRegistry
        return None, f"registry reject: {exc}"[:90]
    except Exception as exc:  # noqa: BLE001
        return None, f"builder init: {type(exc).__name__}: {exc}"[:90]
    try:
        b.build_toe(out_dir / "m.toe", verbose=False)
    except Exception as exc:  # noqa: BLE001
        return None, f"build_toe: {type(exc).__name__}: {exc}"[:90]
    adir = out_dir / "m.toe.dir"
    if not adir.is_dir():
        adir = _find_artifact_dir(out_dir)
    return (adir if adir and adir.is_dir() else None,
            "no .toe.dir produced" if not adir else "")


def run_builder(probe, promote: bool = False) -> dict:
    dataset = datasets.ground_truth_params(datasets.BUILDER_PER_FAMILY)
    scores: list[CaseScore] = []
    tmp_root = Path(tempfile.mkdtemp(prefix="td_builder_measure_"))
    try:
        for d in dataset:
            op = d["operator"]
            fam = d.get("family", "?")
            short = _short_type(op, fam)
            gt = {str(k).lower() for k in d.get("parameters", {})}
            if not gt or not short:
                continue
            case = f"{fam}:{op}"
            out_dir = tmp_root / op
            out_dir.mkdir(parents=True, exist_ok=True)

            adir, why = _build_toe_dir(out_dir, fam, short)
            if adir is None:
                scores.append(CaseScore(case, 0.0, fam,
                              {"param_recall": 0.0, "built": 0.0}, why))
                continue
            try:
                emitted = _emitted_params(adir, fam, short)
            except Exception as exc:  # noqa: BLE001
                scores.append(CaseScore(case, 0.0, fam,
                              {"param_recall": 0.0, "built": 1.0},
                              f"parse failed: {type(exc).__name__}: {exc}"[:80]))
                continue
            if not emitted:
                scores.append(CaseScore(case, 0.0, fam,
                              {"param_recall": 0.0, "built": 1.0},
                              "artifact had no operators/params"))
                continue
            hit = gt & emitted
            recall = round(len(hit) / len(gt), 4)
            missing = sorted(gt - emitted)[:6]
            scores.append(CaseScore(
                case, recall, fam,
                {"param_recall": recall, "built": 1.0},
                f"{len(hit)}/{len(gt)} params; missing e.g. {missing}",
            ))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    return emit("builder_param_acceptance", scores, promote=promote)


def test_builder_param_acceptance(probe, promote):
    report = run_builder(probe, promote)
    assert report["n"] > 0, "no builder cases ran (dataset empty?)"
    exc = [c for c in report["cases"] if "Traceback" in (c.get("detail") or "")]
    assert not exc, f"unexpected tracebacks in {len(exc)} cases"

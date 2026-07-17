#!/usr/bin/env python3
r"""Identity two-tier tests (hygiene bundle H4b) — pure, KB-free, no model.

Pins the warn-tier contract: AGENT_IDENTITY_WARN_FIELDS mismatches WARN and
proceed (exit-code-neutral); only AGENT_IDENTITY_FIELDS mismatches refuse.
engine_code_hash is deterministic, newline-invariant, and edit/rename
sensitive. git_sha is informational — in neither tuple, never compared.

Run: py -3.11 -m pytest eval/agent_eval/tests/test_identity_tiers.py -q
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AGENT_EVAL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENT_EVAL_DIR))

import identity  # noqa: E402
import run_agent_eval as R  # noqa: E402


# ---------------------------------------------------------------------------
# Tier declarations
# ---------------------------------------------------------------------------
def test_warn_and_hard_tiers_disjoint():
    overlap = set(identity.AGENT_IDENTITY_WARN_FIELDS) & set(identity.AGENT_IDENTITY_FIELDS)
    assert not overlap, (
        f"{overlap} in BOTH tiers — a field is either refuse-worthy or "
        f"warn-worthy, never both"
    )


def test_git_sha_in_neither_tier():
    for tier in (identity.AGENT_IDENTITY_FIELDS, identity.AGENT_IDENTITY_WARN_FIELDS):
        assert "git_sha" not in tier, "git_sha is informational only — never compared"


# ---------------------------------------------------------------------------
# engine_code_hash
# ---------------------------------------------------------------------------
def _seed(root: Path, files: dict[str, bytes]):
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)


def test_engine_code_hash_stable_and_edit_sensitive(tmp_path):
    _seed(tmp_path, {"core/a.py": b"x = 1\n", "validation/b.py": b"y = 2\n"})
    h1 = identity.engine_code_hash(tmp_path)
    assert h1 == identity.engine_code_hash(tmp_path), "not deterministic"

    (tmp_path / "core" / "a.py").write_bytes(b"x = 1  # comment\n")
    assert identity.engine_code_hash(tmp_path) != h1, "blind to a file edit"


def test_engine_code_hash_rename_sensitive(tmp_path):
    _seed(tmp_path, {"core/a.py": b"x = 1\n"})
    h1 = identity.engine_code_hash(tmp_path)
    (tmp_path / "core" / "a.py").rename(tmp_path / "core" / "a2.py")
    assert identity.engine_code_hash(tmp_path) != h1, "blind to a rename (relpath is hashed)"


def test_engine_code_hash_newline_invariant(tmp_path):
    _seed(tmp_path, {"core/a.py": b"x = 1\ny = 2\n"})
    h_lf = identity.engine_code_hash(tmp_path)
    (tmp_path / "core" / "a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    assert identity.engine_code_hash(tmp_path) == h_lf, (
        "CRLF checkout flips the hash — autocrlf would make the warn tier cry wolf"
    )


def test_engine_code_hash_empty_reads_unknown(tmp_path):
    assert identity.engine_code_hash(tmp_path) is None
    # None on the CURRENT side vs a stamped prior is a mismatch (warn); None
    # on the PRIOR side is 'unknown' (warn). Neither can refuse — warn tier.


# ---------------------------------------------------------------------------
# git_sha never compared
# ---------------------------------------------------------------------------
def test_identities_differing_only_in_git_sha_match():
    a = {f: "v" for f in identity.AGENT_IDENTITY_FIELDS + identity.AGENT_IDENTITY_WARN_FIELDS}
    b = dict(a)
    a["git_sha"], b["git_sha"] = "aaa1111", "bbb2222"
    for tier in (identity.AGENT_IDENTITY_FIELDS, identity.AGENT_IDENTITY_WARN_FIELDS):
        mism, unknown = identity.identity_mismatches(a, b, tier)
        assert mism == [] and unknown == [], (tier, mism, unknown)


# ---------------------------------------------------------------------------
# compare_against: warn tier is exit-neutral, hard tier still refuses
# ---------------------------------------------------------------------------
def _replay_sweep_and_baseline(tmp_path, *, diverge_field, diverge_value):
    ident = {f: "v" for f in identity.AGENT_IDENTITY_FIELDS}
    ident["model_id"] = None      # structurally None on the replay lane
    ident["cli_version"] = None
    ident["engine_code_hash"] = "engine-old"
    baseline = {"identity": dict(ident), "scenarios": {}}
    sweep_ident = dict(ident)
    sweep_ident[diverge_field] = diverge_value
    sweep = {"lane": "replay", "identity": sweep_ident, "results": {}}
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    args = argparse.Namespace(compare=str(baseline_path), allow_identity_drift=False)
    return args, sweep


def test_compare_warn_tier_is_exit_neutral(tmp_path, capsys):
    args, sweep = _replay_sweep_and_baseline(
        tmp_path, diverge_field="engine_code_hash", diverge_value="engine-new")
    rc = R.compare_against(args, sweep)
    out = capsys.readouterr().out  # stdout: warn lines must reach the CI step summary
    assert rc == 0, f"warn tier changed the exit code: rc={rc}"
    assert "WARNING (soft identity) engine_code_hash" in out, out


def test_compare_hard_tier_still_refuses(tmp_path, capsys):
    args, sweep = _replay_sweep_and_baseline(
        tmp_path, diverge_field="kb_sha", diverge_value="kb-drifted")
    rc = R.compare_against(args, sweep)
    assert rc == 3, f"hard-tier mismatch must refuse with exit 3: rc={rc}"


def test_compare_missing_soft_identity_warns_and_proceeds(tmp_path, capsys):
    args, sweep = _replay_sweep_and_baseline(
        tmp_path, diverge_field="engine_code_hash", diverge_value="engine-new")
    prior = json.loads(Path(args.compare).read_text(encoding="utf-8"))
    del prior["identity"]["engine_code_hash"]  # pre-H4b baseline shape
    Path(args.compare).write_text(json.dumps(prior), encoding="utf-8")
    rc = R.compare_against(args, sweep)
    out = capsys.readouterr().out
    assert rc == 0, f"unknown soft identity must not refuse: rc={rc}"
    assert "no soft identity for ['engine_code_hash']" in out, out


# ---------------------------------------------------------------------------
# guidance_hash: replay-lane exclusion (PR #37 post-merge audit) — replay
# injects no guidance, but build_identity re-reads guidance.md on every lane,
# so without the exclusion every guidance.md edit false-refused Lane R's
# --compare permanently.
# ---------------------------------------------------------------------------
def test_compare_replay_guidance_hash_excluded(tmp_path, capsys):
    args, sweep = _replay_sweep_and_baseline(
        tmp_path, diverge_field="guidance_hash", diverge_value="guidance-edited")
    rc = R.compare_against(args, sweep)
    assert rc == 0, \
        f"guidance_hash drift false-refused the replay compare: rc={rc}"


def test_compare_model_lane_guidance_hash_still_refuses(tmp_path):
    ident = {f: "v" for f in identity.AGENT_IDENTITY_FIELDS}
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps({"identity": dict(ident), "scenarios": {}}),
        encoding="utf-8")
    args = argparse.Namespace(compare=str(baseline_path),
                              allow_identity_drift=False)
    sweep = {"lane": "model", "results": {},
             "identity": dict(ident, guidance_hash="guidance-edited")}
    rc = R.compare_against(args, sweep)
    assert rc == 3, \
        "guidance_hash is a model-lane fact and must still refuse there"

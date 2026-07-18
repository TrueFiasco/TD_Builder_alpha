"""The ground truth must have exactly one source (W3 Census Lock).

HERMETIC and TOLERANT OF ABSENCE: CI has no corpus, so a missing twin is the
expected, passing state. Unmarked so it runs in both ci.yml lanes.

BACKGROUND. `eval/ground_truth/operator_types.json` is tracked, but an untracked
byte-identical twin lived in the main-tree corpus at
`New KB build/Resources/operator_ground_truth/`. CI read the tracked file via an
explicit `--gt-types`; every local default read the twin. They agreed only by
being identical -- so regenerating either one would have made local eval runs and
CI grade against different ground truth with nothing red. W3 repointed every
resolver at the tracked file. This test is what stops the twin coming back.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TRACKED = REPO / "eval" / "ground_truth" / "operator_types.json"

# Both plausible roots: this repo, and the main tree when running from a worktree.
_CORPUS_REL = Path("New KB build") / "Resources" / "operator_ground_truth" / "operator_types.json"
TWIN_CANDIDATES = [
    REPO / _CORPUS_REL,
    Path(r"C:\TD_Builder_Alpha_Build_V0.1.2") / _CORPUS_REL,
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_tracked_ground_truth_exists():
    assert TRACKED.exists(), (
        "the tracked ground truth is the source of truth since W3; regenerate "
        "with kb_build/gen_operator_types.py")


# Sites that may name the corpus copy: each passes it as an EXPLICIT legacy
# fallback, used only when the tracked file is missing. Anything else that
# hardcodes the path is reintroducing the divergence.
_LEGACY_FALLBACK_SITES = {
    "paths.py",
    "kb_build/common.py",
    "eval/build_gate/gate_common.py",
    "eval/run_eval.py",
    "eval/gen_coverage.py",
    "tests/unit/test_ground_truth_no_twin.py",
}


def test_no_source_file_hardcodes_the_corpus_ground_truth():
    """THE INVARIANT THAT MATTERS: nothing reads the twin.

    Deliberately NOT a byte-identity assertion on the twin. Now that every
    resolver prefers the tracked file, a stale corpus copy is inert -- gating on
    its contents would go red for a benign reason on any maintainer machine and
    train people to ignore this test. What must stay true is that no code path
    resolves it, which is what this checks (plus the resolver tests below).

    `kb_build/common.py` is the cautionary case: it read the twin for create-token
    resolution and nobody had noticed, because the two files happened to be
    byte-identical.
    """
    # Match the QUOTED path component, which is how every real construction site
    # writes it (`res / "operator_ground_truth" / "operator_types.json"`). Prose
    # mentions in docstrings are documentation, not a code path.
    needles = ('"operator_ground_truth"', "'operator_ground_truth'")
    offenders = []
    for py in REPO.rglob("*.py"):
        rel = py.relative_to(REPO).as_posix()
        if rel.startswith((".claude/", "New KB build/", "quarantine/")):
            continue
        if rel in _LEGACY_FALLBACK_SITES:
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if any(n in line for n in needles) and "operator_types" in line:
                offenders.append(f"{rel}:{i}: {line.strip()}")
    assert offenders == [], (
        "these files build the corpus operator_types.json path directly; resolve "
        "it via paths.operator_types_path() instead:\n  " + "\n  ".join(offenders))


def test_a_corpus_twin_is_inert_if_present():
    """If a twin exists it is allowed to be stale -- nothing reads it. Recorded
    here so the state is visible rather than surprising."""
    for twin in TWIN_CANDIDATES:
        if twin.exists():
            assert _sha(twin) != "" and TRACKED.exists()


def test_resolvers_prefer_the_tracked_file():
    """Every default path must land on the tracked file, not a corpus copy."""
    from paths import operator_types_path

    assert operator_types_path().resolve() == TRACKED.resolve()

    sys.path.insert(0, str(REPO / "eval"))
    import run_eval

    _, gt_types = run_eval.resolve_gt_paths(None, None, run_eval.resolve_kb_root(None))
    assert gt_types.resolve() == TRACKED.resolve()


def test_params_dir_still_resolves_to_the_corpus():
    """The FILE moved to the tracked tree; the live-TD capture DIRECTORIES did not.
    Deriving params/ from the ground truth's parent (as tool_coverage.py once did)
    now points at eval/ground_truth/params, which does not exist."""
    sys.path.insert(0, str(REPO / "eval"))
    sys.path.insert(0, str(REPO / "eval" / "build_gate"))
    import gate_common

    assert gate_common.params_dir().name == "params"
    assert gate_common.params_dir().parent.name == "operator_ground_truth"
    assert gate_common.params_dir() != TRACKED.parent / "params"

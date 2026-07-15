"""Smoke for the td_validate_expanded CLI (revived by the 2026-07 dead-weight sweep).

.toc <-> disk consistency is checked nowhere else: the lossless parser silently
skips .toc entries whose files are missing on disk (lossless_parser.py returns
early on `not full_path.exists()`), so this audit is the invariant's only owner.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402

bootstrap.setup()

from cli.td_validate_expanded import validate_expanded_pair  # noqa: E402


def _make_pair(tmp_path, toc_lines, disk_files):
    d = tmp_path / "proj.toe.dir"
    d.mkdir()
    for rel in disk_files:
        (d / rel).write_text("x", encoding="utf-8")
    (tmp_path / "proj.toe.toc").write_text("\n".join(toc_lines) + "\n", encoding="utf-8")
    return d


def test_missing_and_extra_findings_fire(tmp_path):
    d = _make_pair(tmp_path, ["present.n", "missing.n"], ["present.n", "orphan.parm"])
    result = validate_expanded_pair(d, strict_extra=True)
    assert result.missing_toc_entries == ["missing.n"]
    assert result.extra_disk_files == ["orphan.parm"]


def test_clean_pair_has_no_findings(tmp_path):
    d = _make_pair(tmp_path, ["a.n", "a.parm"], ["a.n", "a.parm"])
    result = validate_expanded_pair(d, strict_extra=True)
    assert result.missing_toc_entries == []
    assert result.extra_disk_files == []

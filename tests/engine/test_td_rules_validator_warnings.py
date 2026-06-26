"""Regression test for the Stage-5 validator NameError (audit #3).

Before the fix, validating any operator with a relative/default path or a
digit-leading name raised NameError ('warnings' was undefined inside
_validate_operator_rules). After the fix it returns a StageReport with those
findings as *warnings* (not errors), so they don't crash and don't fail the stage.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bootstrap  # noqa: E402
bootstrap.setup()

from validation.td_rules_validator import TDRulesValidator  # noqa: E402


def test_relative_path_and_bad_name_are_warnings_not_crash():
    net = {
        "metadata": {"project_name": "p", "mode": "toe"},
        "operators": [
            {"name": "1noise", "family": "CHOP", "type": "noise", "path": "noise1"},
        ],
    }
    # These TD rules never consult the operator registry, so inject a no-op
    # to keep this a fast, KB-independent unit test.
    report = TDRulesValidator(registry=object()).validate(net)  # pre-fix: NameError
    codes = {(w.code, w.severity) for w in report.warnings}
    assert ("INVALID_OPERATOR_NAME", "warning") in codes      # digit-leading name
    assert ("RELATIVE_OPERATOR_PATH", "warning") in codes     # path missing leading /
    assert report.errors == []      # warnings must not be miscounted as errors
    assert report.status == "PASS"  # warnings must not fail the stage

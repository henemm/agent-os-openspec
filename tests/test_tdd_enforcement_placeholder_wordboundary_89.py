"""Regressionstest für Issue #89 (Epic #199).

`tdd_enforcement._PLACEHOLDER_RE` prüfte TODO|PLACEHOLDER|FIXME ohne Wortgrenzen.
Ein Testname wie `test_gate_ignores_known_placeholder_values` enthält "placeholder"
als Teilstring und blockierte damit jede echte RED-Artefakt-Registrierung, in der
dieser Testname vorkommt (Testkopf, Traceback, short test summary — typischerweise
alle drei in derselben pytest-Ausgabe).

Stilvorlage: tests/test_gate_parser_fixes_73_76_79.py::TestTapSummaryNotPlaceholder
(direkter Aufruf von tdd_enforcement._validate_artifact, echte Dateien in tmp_path).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import tdd_enforcement  # noqa: E402


def _artifact(tmp_path, content: str) -> dict:
    p = tmp_path / "red-output.log"
    p.write_text(content)
    return {
        "type": "test_output",
        "path": str(p),
        "description": "3 Tests fehlgeschlagen: AssertionError in secrets_guard",
    }


# Realer Fall aus Issue #89: der Testname selbst enthält "placeholder" als
# Teilstring, dreimal in echter pytest-RED-Ausgabe.
REAL_PYTEST_RED_WITH_PLACEHOLDER_TESTNAME = (
    "============================= test session starts ==============================\n"
    "collected 12 items\n\n"
    "tests/test_secrets_guard.py::test_gate_ignores_known_placeholder_values FAILED [ 50%]\n\n"
    "=================================== FAILURES ===================================\n"
    "____________________ test_gate_ignores_known_placeholder_values ________________\n\n"
    "    def test_gate_ignores_known_placeholder_values():\n"
    ">       assert mask(\"changeme\") == \"changeme\"\n"
    "E       AssertionError: assert '***' == 'changeme'\n\n"
    "tests/test_secrets_guard.py:42: in test_gate_ignores_known_placeholder_values\n"
    "    assert mask(\"changeme\") == \"changeme\"\n"
    "E   AssertionError\n\n"
    "=========================== short test summary info =============================\n"
    "FAILED tests/test_secrets_guard.py::test_gate_ignores_known_placeholder_values"
    " - AssertionError\n"
    "========================= 1 failed, 11 passed in 0.42s ============================\n"
)


class TestPlaceholderSubstringInTestNameNotBlocked:
    def test_real_red_artifact_with_placeholder_in_testname_is_valid(self, tmp_path):
        art = _artifact(tmp_path, REAL_PYTEST_RED_WITH_PLACEHOLDER_TESTNAME)
        assert tdd_enforcement._validate_artifact(art, tmp_path) is None

    def test_fixme_and_todo_as_testname_substring_also_not_blocked(self, tmp_path):
        content = (
            "tests/test_x.py::test_handles_fixme_comments_in_source FAILED\n"
            "tests/test_x.py:10: in test_handles_fixme_comments_in_source\n"
            "E   AssertionError: expected TODOItem count 1, got 0\n"
            "FAILED tests/test_x.py::test_handles_fixme_comments_in_source - AssertionError\n"
        )
        art = _artifact(tmp_path, content)
        assert tdd_enforcement._validate_artifact(art, tmp_path) is None


class TestRealPlaceholderMarkerStillBlocked:
    def test_standalone_placeholder_word_still_blocked(self, tmp_path):
        art = _artifact(
            tmp_path,
            "PLACEHOLDER - replace with actual test output\n"
            "AssertionError: dummy\n" * 5,
        )
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None
        assert "Platzhalter" in err

    def test_standalone_todo_word_still_blocked(self, tmp_path):
        art = _artifact(
            tmp_path,
            "TODO: insert output here\nAssertionError: dummy\n" * 5,
        )
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None
        assert "Platzhalter" in err

    def test_standalone_fixme_word_still_blocked(self, tmp_path):
        art = _artifact(
            tmp_path,
            "FIXME before merging\nAssertionError: dummy\n" * 5,
        )
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None
        assert "Platzhalter" in err

    def test_bracket_phrase_patterns_still_blocked(self, tmp_path):
        art = _artifact(
            tmp_path,
            "<test_output>\nAssertionError: dummy\n" * 5,
        )
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None
        assert "Platzhalter" in err

"""Regressionstests für die Gate-Parser-Fixes (Issues #73, #76, #79).

Drei False-Positive-Klassen, gemeinsame Wurzel: Parser waren an eine einzige
beobachtete Formatausprägung gebunden statt an das reale Format des Runners.

1. #79: pytest hängt ab 60s Laufzeit '(H:MM:SS)' HINTER 'in X.Ys' an —
   die Summary-Regex modellierte beide Suffixe als Entweder-oder.
2. #76: Playwright schreibt die Klammer-Dauer ab 60s in Minuten ('(1.5m)'),
   real genutzte Einheiten sind ms/s/m/h. Zusätzlich (Issue-Kommentar):
   go-test-Ausgaben wurden überhaupt nicht erkannt.
3. #73: `node --test` (TAP) endet IMMER mit der Summary-Zeile '# todo 0' —
   das TODO-Platzhalter-Pattern in tdd_enforcement bewertete damit jedes
   echte node-RED-Artefakt als "gefälscht".

Direkte Funktionsaufrufe mit echten Dateien in tmp_path (kein Mocking),
Stilvorlage: tests/test_qa_gate.py und tests/test_adversary_dialog_verdict.py.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import qa_gate  # noqa: E402
import tdd_enforcement  # noqa: E402


# --- Teil 1 (Issue #79): pytest-Summenzeile mit 'in X.Ys (H:MM:SS)' ---

class TestPytestSummaryLongRuns:
    def test_summary_over_60s_with_wallclock_suffix_recognized(self):
        line = "================= 171 passed, 5 deselected in 68.29s (0:01:08) ================="
        assert qa_gate._find_pytest_summary_line(line) is not None

    def test_summary_under_60s_still_recognized(self):
        line = "============================== 29 passed in 1.38s =============================="
        assert qa_gate._find_pytest_summary_line(line) is not None

    def test_summary_over_one_hour_recognized(self):
        line = "== 500 passed in 3661.00s (1:01:01) =="
        assert qa_gate._find_pytest_summary_line(line) is not None

    def test_validate_passes_green_long_run(self, tmp_path):
        out = tmp_path / "pytest.log"
        out.write_text(
            "===== test session starts =====\n"
            + "tests/test_x.py ................ [100%]\n" * 5
            + "================= 171 passed, 5 deselected in 68.29s (0:01:08) =================\n"
        )
        valid, msg = qa_gate.validate_test_output(str(out))
        assert valid is True
        assert "171 passed" in msg

    def test_validate_fails_red_long_run(self, tmp_path):
        out = tmp_path / "pytest.log"
        out.write_text(
            "===== test session starts =====\n"
            + "FAILED tests/test_x.py::test_a - AssertionError\n" * 3
            + "========== 2 failed, 169 passed in 75.00s (0:01:15) ==========\n"
        )
        valid, msg = qa_gate.validate_test_output(str(out))
        assert valid is False
        assert "2 failed" in msg


# --- Teil 2 (Issue #76): Playwright-Dauer in ms/m/h ---

class TestPlaywrightDurationUnits:
    def test_minutes_duration_recognized(self):
        assert qa_gate._find_pytest_summary_line("  39 passed (1.5m)") is not None

    def test_milliseconds_duration_recognized(self):
        assert qa_gate._find_pytest_summary_line("  3 passed (982ms)") is not None

    def test_hours_duration_recognized(self):
        assert qa_gate._find_pytest_summary_line("  120 passed (1.2h)") is not None

    def test_seconds_duration_still_recognized(self):
        assert qa_gate._find_pytest_summary_line("  39 passed (48.7s)") is not None

    def test_prose_with_non_duration_paren_still_rejected(self):
        # AC-4-Grenze aus Fix #71: Prosa mit Klammer ist KEINE Summary-Zeile
        assert qa_gate._find_pytest_summary_line("5 passed (siehe oben)") is None

    def test_validate_passes_green_playwright_long_run(self, tmp_path):
        out = tmp_path / "playwright.log"
        out.write_text(
            "Running 39 tests using 4 workers\n"
            + "  ok e2e/issue-498.spec.ts ....\n" * 10
            + "  39 passed (1.5m)\n"
        )
        valid, msg = qa_gate.validate_test_output(str(out))
        assert valid is True
        assert "39 passed" in msg


# --- Teil 2b (Issue #76, Kommentar): go test wird erkannt ---

class TestGoTestOutput:
    GO_GREEN = (
        "=== RUN   TestBriefingFingerprint_FollowsFileBytes\n"
        "--- PASS: TestBriefingFingerprint_FollowsFileBytes (0.00s)\n"
        "=== RUN   TestStoreRoundtrip\n"
        "--- PASS: TestStoreRoundtrip (0.01s)\n"
        "ok  \tgithub.com/henemm/gregor-api/internal/store\t5.607s\n"
    )
    GO_RED = (
        "=== RUN   TestStoreRoundtrip\n"
        "--- FAIL: TestStoreRoundtrip (0.01s)\n"
        "    store_test.go:42: got 0, want 1\n"
        "FAIL\n"
        "FAIL\tgithub.com/henemm/gregor-api/internal/store\t0.512s\n"
    )

    def test_green_go_run_passes(self, tmp_path):
        out = tmp_path / "go.log"
        out.write_text(self.GO_GREEN * 3)
        valid, msg = qa_gate.validate_test_output(str(out))
        assert valid is True
        assert "go test" in msg

    def test_red_go_run_fails(self, tmp_path):
        out = tmp_path / "go.log"
        out.write_text(self.GO_RED * 3)
        valid, msg = qa_gate.validate_test_output(str(out))
        assert valid is False
        assert "go test" in msg

    def test_cached_package_line_counts_as_green(self, tmp_path):
        out = tmp_path / "go.log"
        out.write_text(
            "--- PASS: TestX (0.00s)\n--- PASS: TestY (0.00s)\n"
            "ok  \tgithub.com/henemm/gregor-api/internal/api\t(cached)\n" * 2
        )
        valid, _ = qa_gate.validate_test_output(str(out))
        assert valid is True

    def test_tap_not_ok_output_is_not_false_passed_via_go_branch(self, tmp_path):
        # TAP-Zeilen ('ok 1 - x') dürfen NICHT als Go-Paketzeile durchgehen:
        # sonst würde eine TAP-Ausgabe mit not-ok-Fails als PASSED gewertet.
        out = tmp_path / "tap.log"
        out.write_text(
            "TAP version 13\n"
            "ok 1 - erste pruefung passed\n"
            "not ok 2 - zweite pruefung failed\n"
            "# tests 2\n# pass 1\n# fail 1\n# todo 0\n"
            "AssertionError: expected 1 to equal 2\n" * 3
        )
        valid, _ = qa_gate.validate_test_output(str(out))
        assert valid is False


# --- Teil 3 (Issue #73): TAP-Summary '# todo 0' ist kein Platzhalter ---

class TestTapSummaryNotPlaceholder:
    def _artifact(self, tmp_path, content: str) -> dict:
        p = tmp_path / "red-output.log"
        p.write_text(content)
        return {
            "type": "test_output",
            "path": str(p),
            "description": "6 Tests fehlgeschlagen: ERR_MODULE_NOT_FOUND",
        }

    TAP_RED = (
        "TAP version 13\n"
        "not ok 1 - compare new trip pattern\n"
        "  ---\n"
        "  error: |-\n"
        "    AssertionError: ERR_MODULE_NOT_FOUND cannot find module\n"
        "  ...\n"
        "# tests 6\n# suites 1\n# pass 0\n# fail 6\n"
        "# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 312.4\n"
    )

    def test_real_tap_red_artifact_is_valid(self, tmp_path):
        art = self._artifact(tmp_path, self.TAP_RED)
        assert tdd_enforcement._validate_artifact(art, tmp_path) is None

    def test_real_placeholder_todo_still_blocked(self, tmp_path):
        art = self._artifact(
            tmp_path,
            "TODO: insert output here\nAssertionError: platzhalter\n" * 5,
        )
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None
        assert "Platzhalter" in err

    def test_placeholder_outside_tap_summary_still_blocked(self, tmp_path):
        # Ein TODO in einer Nicht-Summary-Zeile bleibt verdächtig,
        # auch wenn die Datei zusätzlich TAP-Summary-Zeilen enthält.
        art = self._artifact(
            tmp_path,
            self.TAP_RED + "\nhier noch ein TODO vom Entwickler\n",
        )
        err = tdd_enforcement._validate_artifact(art, tmp_path)
        assert err is not None
        assert "Platzhalter" in err

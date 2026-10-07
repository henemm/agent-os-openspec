"""Issue #388: qa_gate wertet Swift-Testing-Laeufe (`@Test`) aus.

xcodebuild zaehlt Swift-Testing-Tests nicht in der XCTest-Zeile
`Executed N tests, with M failures`. Die Ausgaben unten folgen dem Format von
swift-testing 6 (roh) bzw. dem, was nach xcbeautify davon uebrig bleibt.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

from qa_gate import validate_test_output  # noqa: E402

XCODE_HEAD = (
    "Testing started\n"
    "Test Suite 'Selected tests' started at 2026-10-06 19:40:01.123.\n"
)
XCTEST_ZERO = (
    "Test Suite 'Selected tests' passed at 2026-10-06 19:40:01.500.\n"
    "\t Executed 0 tests, with 0 failures (0 unexpected) in 0.000 (0.001) seconds\n"
)


def _swift_green(n=15):
    lines = ["◇ Test run started.",
             "↳ Testing Library Version: 6.0 (arm64e-apple-macos13.0)",
             '◇ Suite "Siri-Angaben (#225)" started.']
    for i in range(n):
        lines.append(f'◇ Test "Feld {i}" started.')
        lines.append(f'✔ Test "Feld {i}" passed after 0.001 seconds.')
    lines.append('✔ Suite "Siri-Angaben (#225)" passed after 0.349 seconds.')
    lines.append(f"✔ Test run with {n} tests in 1 suite passed after 0.349 seconds.")
    return "\n".join(lines) + "\n"


def _write(tmp_path, text):
    p = tmp_path / "out.txt"
    p.write_text(text)
    return validate_test_output(str(p))


def test_ac1_executed_zero_does_not_override_green_swift_testing(tmp_path):
    """Fundfall: nur Swift-Testing-Suite ausgewaehlt, XCTest meldet 0."""
    text = XCODE_HEAD + _swift_green(15) + XCTEST_ZERO + "** TEST SUCCEEDED **\n"
    valid, msg = _write(tmp_path, text)
    assert valid, msg
    assert "15" in msg, msg


def test_ac2_full_run_counts_xctest_plus_swift_testing(tmp_path):
    text = (XCODE_HEAD + _swift_green(343)
            + "\t Executed 7 tests, with 0 failures (0 unexpected) in 0.2 (0.3) seconds\n"
            + "** TEST SUCCEEDED **\n")
    valid, msg = _write(tmp_path, text)
    assert valid, msg
    assert "350" in msg, msg


def test_ac3_failed_test_line_is_red(tmp_path):
    text = (XCODE_HEAD + _swift_green(3).replace(
        '✔ Test "Feld 1" passed after 0.001 seconds.',
        '✘ Test "Feld 1" recorded an issue at SiriFieldsTests.swift:12:5: '
        'Expectation failed: (a → 1) == 2\n'
        '✘ Test "Feld 1" failed after 0.002 seconds with 1 issue.')
        + XCTEST_ZERO + "** TEST SUCCEEDED **\n")
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_ac3_failed_suite_is_red(tmp_path):
    text = (XCODE_HEAD + _swift_green(3).replace(
        '✔ Suite "Siri-Angaben (#225)" passed', '✘ Suite "Siri-Angaben (#225)" failed')
        + XCTEST_ZERO)
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_ac3_failed_run_summary_is_red(tmp_path):
    text = XCODE_HEAD + (
        '✘ Test run with 4 tests in 1 suite failed after 0.3 seconds with 1 issue.\n'
    ) + XCTEST_ZERO
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_ac3_xcbeautify_output_without_summary(tmp_path):
    """Nach xcbeautify: nur ✔/✘-Zeilen je Test und `Suite "…" passed|failed`."""
    green = (
        "Test Suite Selected tests started\n"
        + "".join(f"    ✔ Feld {i}() (0.001 seconds)\n" for i in range(15))
        + 'Suite "Siri-Angaben (#225)" passed after 0.349 seconds.\n'
        + "\t Executed 0 tests, with 0 failures (0 unexpected) in 0.000 (0.001) seconds\n"
        + "Test Succeeded\n"
    )
    valid, msg = _write(tmp_path, green)
    assert valid and "15" in msg, msg

    red = green.replace("    ✔ Feld 3() (0.001 seconds)", "    ✘ Feld 3() (0.001 seconds)")
    valid, msg = _write(tmp_path, red)
    assert not valid, msg

    red_suite = green.replace('passed after 0.349', 'failed after 0.349')
    valid, msg = _write(tmp_path, red_suite)
    assert not valid, msg


def test_ac4_swift_testing_without_xctest_line(tmp_path):
    """Reiner `swift test`-Lauf ohne Executed-Zeile wird auch gewertet."""
    valid, msg = _write(tmp_path, "Building for debugging...\n" + _swift_green(5))
    assert valid and "5" in msg, msg


def test_ac5_xctest_failure_still_red(tmp_path):
    text = (XCODE_HEAD + _swift_green(15)
            + "\t Executed 7 tests, with 1 failure (0 unexpected) in 0.2 (0.3) seconds\n")
    valid, msg = _write(tmp_path, text)
    assert not valid and "1/7" in msg, msg


def test_ac5_zero_everywhere_stays_not_passed(tmp_path):
    text = (XCODE_HEAD + "✔ Test run with 0 tests in 0 suites passed after 0.001 seconds.\n"
            + XCTEST_ZERO)
    valid, msg = _write(tmp_path, text)
    assert not valid and "0 tests" in msg, msg


def test_ac5_all_skipped_is_not_passed(tmp_path):
    text = (XCODE_HEAD
            + '➜ Test "Feld 0" skipped: "kein Simulator"\n'
            + '➜ Test "Feld 1" skipped: "kein Simulator"\n'
            + '✔ Suite "Siri-Angaben (#225)" passed after 0.001 seconds.\n'
            + "✔ Test run with 2 tests in 1 suite passed after 0.001 seconds.\n"
            + XCTEST_ZERO)
    valid, msg = _write(tmp_path, text)
    assert not valid and "skipped" in msg, msg


def test_ac6_mocha_checkmarks_are_not_swift_testing(tmp_path):
    """✔ allein (mocha/node spec) loest den Swift-Testing-Zweig nicht aus."""
    text = (
        "  login\n"
        "    ✔ accepts valid user\n"
        "    ✔ rejects empty password\n"
        "    1) rejects wrong password\n\n"
        "  2 passing (12ms)\n"
        "  1 failing\n\n"
        "  1) login\n       rejects wrong password:\n     AssertionError: FAILED\n"
    )
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


# --- Adversary-Runde 1 (#390) ---

GREEN_SUMMARY = "✔ Test run with 3 tests in 1 suite passed after 0.001 seconds.\n"


def test_crash_after_green_summary_is_red(tmp_path):
    text = (XCODE_HEAD + GREEN_SUMMARY + XCTEST_ZERO
            + "Testing failed:\n\tMyApp (12345) encountered an error (Crash)\n"
            + "** TEST FAILED **\n")
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_xcbeautify_crash_without_summary_is_red(tmp_path):
    text = ('✔ Test a() passed after 0.001 seconds.\n'
            '✔ Suite "S" passed after 0.01 seconds.\n'
            "MyApp crashed\n** TEST FAILED **\n")
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_restart_after_crash_is_red(tmp_path):
    text = (XCODE_HEAD + GREEN_SUMMARY
            + "Restarting after unexpected exit, crash, or test timeout\n" + XCTEST_ZERO)
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_build_failed_after_green_summary_is_red(tmp_path):
    valid, msg = _write(tmp_path, XCODE_HEAD + GREEN_SUMMARY + "** BUILD FAILED **\n")
    assert not valid, msg


import pytest  # noqa: E402


@pytest.mark.parametrize("fail_line", [
    "✘  Test b() failed after 0.001 seconds with 1 issue.",
    "✘︎ Test b() failed after 0.001 seconds with 1 issue.",
    "✘\tTest b() failed after 0.001 seconds with 1 issue.",
    "\U00100884  Test b() failed after 0.001 seconds with 1 issue.",
])
def test_fail_line_variants_are_red(tmp_path, fail_line):
    text = ('✔ Suite "S" passed after 0.01 seconds.\n' + fail_line + "\n"
            "✔ Test a() passed after 0.001 seconds.\n")
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_sf_symbols_green_summary_overrides_executed_zero(tmp_path):
    text = (XCODE_HEAD + "\U001007c8  Test run started.\n"
            "\U0010105b  Test run with 4 tests in 1 suite passed after 0.01 seconds.\n"
            + XCTEST_ZERO + "** TEST SUCCEEDED **\n")
    valid, msg = _write(tmp_path, text)
    assert valid and "4" in msg, msg


def test_sf_symbols_red_summary_is_red(tmp_path):
    text = (XCODE_HEAD
            + "\U00100884  Test run with 1 test in 1 suite failed after 0.01 seconds with 1 issue.\n"
            + "\t Executed 5 tests, with 0 failures (0 unexpected) in 0.1 (0.1) seconds\n")
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_unquoted_suite_name_activates_swift_branch(tmp_path):
    text = ("✔ Test foo() passed after 0.001 seconds.\n"
            "✔ Suite MyTests passed after 0.01 seconds.\n" + XCTEST_ZERO
            + "** TEST SUCCEEDED **\n")
    valid, msg = _write(tmp_path, text)
    assert valid, msg


def test_known_issue_pass_is_not_red(tmp_path):
    text = (XCODE_HEAD + "✖ Test a() passed after 0.001 seconds with 1 known issue.\n"
            + GREEN_SUMMARY + XCTEST_ZERO + "** TEST SUCCEEDED **\n")
    valid, msg = _write(tmp_path, text)
    assert valid, msg


# --- Adversary-Runde 2 (#390) ---

def test_recorded_known_issue_is_not_red(tmp_path):
    text = (XCODE_HEAD
            + "✖ Test a() recorded a known issue at A.swift:3:5: Expectation failed: (x → 1) == 2\n"
            + "✖ Test a() passed after 0.001 seconds with 1 known issue.\n"
            + "✔ Test run with 1 test in 0 suites passed after 0.002 seconds with 1 known issue.\n"
            + XCTEST_ZERO + "** TEST SUCCEEDED **\n")
    valid, msg = _write(tmp_path, text)
    assert valid, msg


def test_known_issue_text_in_real_failure_stays_red(tmp_path):
    text = (XCTEST_ZERO
            + "✘ Test x() failed after 0.1 seconds: expected passed with known issue\n"
            + "✔ Test run with 1 test in 0 suites passed after 0.1 seconds.\n")
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_cross_glyph_real_failure_is_red(tmp_path):
    text = (XCTEST_ZERO + "✖ Test x() failed after 0.1 seconds with 1 issue.\n"
            + "✔ Test run with 1 test in 0 suites passed after 0.1 seconds.\n")
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


PYTEST_RED = (
    "============================= test session starts ==============================\n"
    "collected 5 items\n\n"
    "tests/test_a.py ....F                                                    [100%]\n\n"
    "=================================== FAILURES ===================================\n"
    "___________________________________ test_e ____________________________________\n"
    "E       assert 1 == 2\n"
)


@pytest.mark.parametrize("stray", [
    "- Test run with 5 tests passed\n",
    "Suite Auth passed\n✔ ok\n",
])
def test_stray_swift_like_line_in_red_pytest_stays_red(tmp_path, stray):
    text = PYTEST_RED + stray + "========================= 1 failed, 4 passed in 0.12s =========================\n"
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_stray_suite_line_in_red_mocha_stays_red(tmp_path):
    text = ("  Login\n    ✔ a\n    1) b\n\nSuite Login passed\n\n"
            "  1 passing (12ms)\n  1 failing\n\n  1) Login\n       b:\n     AssertionError: x\n")
    valid, msg = _write(tmp_path, text)
    assert not valid, msg


def test_mocha_title_with_suite_word_does_not_trigger_swift(tmp_path):
    text = ("  Teardown\n    ✔ Suite teardown failed gracefully\n    ✔ other\n\n"
            "  2 passing (12ms)\n" + "x" * 60 + "\n")
    valid, msg = _write(tmp_path, text)
    assert "Swift" not in msg, msg


def test_green_swift_with_red_pytest_summary_is_red(tmp_path):
    text = (PYTEST_RED + "✔ Test run with 3 tests in 1 suite passed after 0.01 seconds.\n"
            + "========================= 1 failed, 4 passed in 0.12s =========================\n")
    valid, msg = _write(tmp_path, text)
    assert not valid, msg

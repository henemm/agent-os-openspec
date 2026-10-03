"""Tests fuer #313/#327: QA-Gate erkennt Python-unittest- und node --test-Ausgaben.

Alle Fixtures unter tests/fixtures/qa_gate_313_327/ stammen aus echten Laeufen.
Jeder Test kopiert sein Fixture nach tmp_path, damit die mtime frisch ist und
der 30-Minuten-Alterscheck von validate_test_output() nicht greift.
Keine Mocks: geprueft wird die echte validate_test_output().
"""
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "qa_gate_313_327"
FIXTURES_275 = REPO_ROOT / "tests" / "fixtures" / "testausgabe_275"

sys.path.insert(0, str(HOOKS_DIR))
import qa_gate  # noqa: E402


def _copy_fixture(tmp_path: Path, name: str, source_dir: Path = FIXTURES) -> Path:
    src = source_dir / name
    assert src.exists(), f"Fixture fehlt: {src}"
    dst = tmp_path / name
    shutil.copy(src, dst)
    dst.touch()
    return dst


def _read_fixture(name: str, source_dir: Path = FIXTURES) -> str:
    src = source_dir / name
    assert src.exists(), f"Fixture fehlt: {src}"
    return src.read_text(encoding="utf-8")


def _write(tmp_path: Path, name: str, content: str) -> Path:
    out = tmp_path / name
    out.write_text(content, encoding="utf-8")
    return out


def _validate(path: Path):
    return qa_gate.validate_test_output(str(path), infra=True)


def _assert_recognized(msg: str) -> None:
    """False allein beweist nichts: auch ein unerkanntes Format liefert False.
    Rot muss aus einem erkannten Runner-Ergebnis kommen."""
    assert "Could not determine" not in msg, msg
    assert "Doesn't look like test output" not in msg, msg


# --- unittest -----------------------------------------------------------------

def test_unittest_green_verbose_passed(tmp_path):
    """AC-1: gruener `unittest -v`-Lauf -> True, 'PASSED', Zahl der Tests (3)."""
    valid, msg = _validate(_copy_fixture(tmp_path, "unittest_green_verbose.txt"))
    assert valid is True, msg
    assert "PASSED" in msg
    assert "3" in msg


def test_unittest_red_failed_with_counts(tmp_path):
    """AC-2: `FAILED (failures=1, errors=1, skipped=1)` -> False, 'FAILED',
    Zahlen fuer failures und errors, nicht 'Could not determine'."""
    valid, msg = _validate(
        _copy_fixture(tmp_path, "unittest_red_failures_errors_skipped.txt"))
    assert valid is False, msg
    assert "FAILED" in msg
    assert "Could not determine" not in msg
    assert "1 failure" in msg or "failures=1" in msg or "1 failed" in msg, msg
    assert "1 error" in msg or "errors=1" in msg, msg


def test_unittest_all_skipped_not_passed_expected_failures_green(tmp_path):
    """AC-3: `OK (skipped=2)` bei 2 Tests -> False 'NOT PASSED' mit Zahl 2;
    `OK (expected failures=1)` -> True."""
    valid, msg = _validate(_copy_fixture(tmp_path, "unittest_only_skipped.txt"))
    assert valid is False, msg
    assert "NOT PASSED" in msg
    assert "2" in msg

    valid, msg = _validate(_copy_fixture(tmp_path, "unittest_expected_failure.txt"))
    assert valid is True, msg


def test_unittest_no_tests_ran_not_passed(tmp_path):
    """AC-4: `Ran 0 tests` + `NO TESTS RAN` -> False 'NOT PASSED'."""
    valid, msg = _validate(_copy_fixture(tmp_path, "unittest_no_tests_ran.txt"))
    assert valid is False, msg
    assert "NOT PASSED" in msg


def test_unittest_unexpected_success_is_red(tmp_path):
    """AC-5: unerwarteter Erfolg ist rot.

    Abweichung von der Spec: Echtes Python (3.14) meldet unerwarteten Erfolg als
    `FAILED (unexpected successes=1)`, nicht `OK (unexpected successes=1)`. Der
    erste Fall nutzt die echte Fixture. Der zweite Fall nutzt die Spec-
    Schreibweise inline (Kopf/Fuss nach Muster der echten Fixture) und erwartet
    ebenfalls False.
    """
    valid, msg = _validate(_copy_fixture(tmp_path, "unittest_unexpected_success.txt"))
    assert valid is False, msg
    assert "FAILED" in msg

    spec_variant = (
        "$ python3 -m unittest -v t_unexpected\n"
        "test_ok (t_unexpected.A.test_ok) ... ok\n"
        "test_surprise (t_unexpected.A.test_surprise) ... unexpected success\n"
        "\n"
        "----------------------------------------------------------------------\n"
        "Ran 2 tests in 0.000s\n"
        "\n"
        "OK (unexpected successes=1)\n"
    )
    assert len(spec_variant.encode()) >= 100
    valid, msg = _validate(_write(tmp_path, "unexpected_ok_variant.txt", spec_variant))
    assert valid is False, msg


# --- node --test ---------------------------------------------------------------

def test_node_spec_green_passed(tmp_path):
    """AC-6: gruener node --test-Lauf (Spec-Reporter) -> True 'PASSED'."""
    valid, msg = _validate(_copy_fixture(tmp_path, "node_spec_green.txt"))
    assert valid is True, msg
    assert "PASSED" in msg


def test_node_spec_red_with_trailing_stacktraces_failed(tmp_path):
    """AC-7: roter Spec-Reporter-Lauf mit nachfolgendem `✖ failing tests:`-Block
    -> False 'FAILED' mit Zahl 2 (keine Dateiende-Bindung)."""
    valid, msg = _validate(_copy_fixture(tmp_path, "node_spec_red_with_stacktraces.txt"))
    assert valid is False, msg
    assert "FAILED" in msg
    assert "2" in msg


def test_node_tap_green_passed(tmp_path):
    """AC-8: gruener TAP-Lauf -> True."""
    valid, msg = _validate(_copy_fixture(tmp_path, "node_tap_green.txt"))
    assert valid is True, msg


def test_node_tap_red_failed(tmp_path):
    """AC-9: roter TAP-Lauf (`# fail 2`) -> False 'FAILED' mit Zahl 2."""
    valid, msg = _validate(_copy_fixture(tmp_path, "node_tap_red.txt"))
    assert valid is False, msg
    assert "FAILED" in msg
    assert "2" in msg


def test_node_cancelled_is_red(tmp_path):
    """AC-10: `cancelled 1`, `fail 0` (Spec und TAP) -> jeweils False.

    Zusaetzlich muss das Rot aus dem erkannten node-Ergebnis stammen, nicht aus
    'Could not determine' (heutiger Stand liefert False nur zufaellig).
    """
    for name in ("node_cancelled_spec.txt", "node_cancelled_tap.txt"):
        valid, msg = _validate(_copy_fixture(tmp_path, name))
        assert valid is False, f"{name}: {msg}"
        _assert_recognized(msg)


def test_node_zero_tests_and_all_skipped_not_passed(tmp_path):
    """AC-11: `tests 0` und `pass 0` + `skipped 2` -> jeweils False 'NOT PASSED'.

    Abweichung: node 26.5.1 kann keinen echten Lauf mit `tests 0` erzeugen
    (eine leere Testdatei ergibt `tests 1`). Der `tests 0`-Fall ist daher
    SYNTHETISCH ABGELEITET, WEIL NICHT ECHT ERZEUGBAR: Inhalt von
    node_spec_green.txt mit ersetzten Zaehlwerten (`ℹ tests 0`, `ℹ pass 0`).
    Der `pass 0 + skipped`-Fall nutzt die echte node_skipped_only.txt.
    """
    green = _read_fixture("node_spec_green.txt")
    assert "ℹ tests 3" in green and "ℹ pass 3" in green
    zero = green.replace("ℹ tests 3", "ℹ tests 0").replace("ℹ pass 3", "ℹ pass 0")
    valid, msg = _validate(_write(tmp_path, "node_tests_zero_synthetic.txt", zero))
    assert valid is False, msg
    assert "NOT PASSED" in msg

    valid, msg = _validate(_copy_fixture(tmp_path, "node_skipped_only.txt"))
    assert valid is False, msg
    assert "NOT PASSED" in msg


# --- gemischte Ausgaben ---------------------------------------------------------

def test_mixed_unittest_red_xcodebuild_green_is_failed(tmp_path):
    """AC-12: roter unittest-Lauf + gruene xcodebuild-Zeilen -> False 'FAILED'.

    Gruener xcodebuild-Teil: echte Fixture testausgabe_275/xcodebuild_mixed_raw.txt
    (`Executed 5 tests, with 1 test skipped and 0 failures`, `** TEST SUCCEEDED **`).
    """
    red = _read_fixture("unittest_red_failures_errors_skipped.txt")
    xcode = _read_fixture("xcodebuild_mixed_raw.txt", FIXTURES_275)
    assert "TEST SUCCEEDED" in xcode
    out = _write(tmp_path, "mixed_unittest_xcode.txt", red + "\n" + xcode)
    valid, msg = _validate(out)
    assert valid is False, msg
    assert "FAILED" in msg


def test_mixed_unittest_green_pytest_red_and_two_runs_is_failed(tmp_path):
    """AC-13: (a) gruener unittest + roter pytest -> False;
    (b) zwei unittest-Laeufe, erst gruen, dann rot -> False.

    Jeweils muss das Rot aus einer erkannten Summary stammen, nicht aus
    'Could not determine' (Fall b liefert heute False nur zufaellig).
    """
    green = _read_fixture("unittest_green_verbose.txt")
    pytest_red = (
        "============================= test session starts ==============================\n"
        "collected 5 items\n"
        "\n"
        "tests/test_x.py ....F\n"
        "\n"
        "========================= 1 failed, 4 passed in 0.12s ==========================\n"
    )
    valid, msg = _validate(
        _write(tmp_path, "mixed_unittest_pytest.txt", green + "\n" + pytest_red))
    assert valid is False, msg
    _assert_recognized(msg)

    red = _read_fixture("unittest_red_failures_errors_skipped.txt")
    valid, msg = _validate(
        _write(tmp_path, "two_unittest_runs.txt", green + "\n" + red))
    assert valid is False, msg
    _assert_recognized(msg)


# --- Gegenproben / Regression ----------------------------------------------------

def test_quoted_summary_in_prose_not_recognized(tmp_path):
    """AC-14: `Ran 5 tests in 0.1s` bzw. `ℹ pass 3` nur mitten in Prosa -> nie True."""
    prose_unittest = (
        "Im Protokoll von gestern stand die Zeile Ran 5 tests in 0.1s als Beispiel,\n"
        "die wir hier nur zitieren, damit die Dokumentation die Form der Ausgabe zeigt.\n"
        "Es wurde dabei nichts ausgefuehrt und kein Ergebnis erzeugt.\n"
    )
    prose_node = (
        "Im Protokoll von gestern stand die Zeile ℹ pass 3 als Beispiel,\n"
        "die wir hier nur zitieren, damit die Dokumentation die Form der Ausgabe zeigt.\n"
        "Es wurde dabei nichts ausgefuehrt und kein Ergebnis erzeugt.\n"
    )
    for name, text in (("prose_unittest.txt", prose_unittest),
                       ("prose_node.txt", prose_node)):
        assert len(text.encode()) >= 100
        valid, msg = _validate(_write(tmp_path, name, text))
        assert valid is False, f"{name}: {msg}"


def test_size_gate_and_prefilter_unchanged(tmp_path):
    """AC-15: echte Einzeltest-Ausgabe ohne -v (98 Byte) -> 'too small';
    Text mit genau einem Muster-Treffer ohne Runner-Block -> Vorfilter."""
    valid, msg = _validate(_copy_fixture(tmp_path, "unittest_single_quiet.txt"))
    assert valid is False, msg
    assert "too small" in msg

    one_hit = (
        "Notiz zur Besprechung: In der Test Suite sollen kuenftig mehr Beispiele\n"
        "stehen. Das ist nur eine Gedankenstuetze, keine Ausgabe eines Laufs.\n"
    )
    assert len(one_hit.encode()) >= 100
    hits = sum(1 for p in qa_gate.TEST_PATTERNS
               if re.search(p, one_hit, re.IGNORECASE))
    assert hits == 1, hits
    valid, msg = _validate(_write(tmp_path, "one_hit.txt", one_hit))
    assert valid is False, msg
    assert "Doesn't look like test output" in msg


def test_existing_branches_unchanged_pytest_executed_go(tmp_path):
    """AC-16: bestehende Zweige pytest, xcodebuild-`Executed` und go bleiben gruen."""
    cases = {
        "pytest.txt": "test session starts\n5 passed in 1.2s\n" * 3,
        "executed.txt": "Test Suite started\nExecuted 12 tests, with 0 failures\n" * 3,
        "go.txt": (
            "=== RUN   TestA\n--- PASS: TestA (0.00s)\n"
            "=== RUN   TestB\n--- PASS: TestB (0.00s)\n"
            "PASS\nok  \texample.com/pkg\t0.012s\n"
        ),
    }
    for name, text in cases.items():
        assert len(text.encode()) >= 100, name
        valid, msg = _validate(_write(tmp_path, name, text))
        assert valid is True, f"{name}: {msg}"


# --- Adversary-Befunde F001-F005 (Leitregel: jede rote Evidenz gewinnt) ---------

def _concat(tmp_path: Path, name: str, *fixtures: str) -> Path:
    return _write(tmp_path, name, "\n".join(_read_fixture(f) for f in fixtures))


def test_adv_f001_node_spec_red_then_green_is_failed(tmp_path):
    """F001: zwei node-Laeufe (Spec), erst rot dann gruen -> False, und umgekehrt."""
    for order in (("node_spec_red_with_stacktraces.txt", "node_spec_green.txt"),
                  ("node_spec_green.txt", "node_spec_red_with_stacktraces.txt")):
        valid, msg = _validate(_concat(tmp_path, "spec_two_runs.txt", *order))
        assert valid is False, f"{order}: {msg}"
        assert "FAILED" in msg
        _assert_recognized(msg)


def test_adv_f001_node_tap_red_then_green_is_failed(tmp_path):
    """F001: zwei node-Laeufe (TAP), erst rot dann gruen -> False, und umgekehrt."""
    for order in (("node_tap_red.txt", "node_tap_green.txt"),
                  ("node_tap_green.txt", "node_tap_red.txt")):
        valid, msg = _validate(_concat(tmp_path, "tap_two_runs.txt", *order))
        assert valid is False, f"{order}: {msg}"
        assert "FAILED" in msg
        _assert_recognized(msg)


def test_adv_f002_unittest_green_with_cargo_failed_is_red(tmp_path):
    """F002: gruener unittest + `test result: FAILED` (cargo) -> False."""
    text = _read_fixture("unittest_green_verbose.txt") + "test result: FAILED. 1 passed; 1 failed\n"
    valid, msg = _validate(_write(tmp_path, "ut_cargo.txt", text))
    assert valid is False, msg
    assert "FAILED" in msg


def test_adv_f002_unittest_green_with_test_failed_marker_is_red(tmp_path):
    """F002: gruener unittest + `** TEST FAILED **` -> False."""
    text = _read_fixture("unittest_green_verbose.txt") + "** TEST FAILED **\n"
    valid, msg = _validate(_write(tmp_path, "ut_marker.txt", text))
    assert valid is False, msg
    assert "FAILED" in msg


def test_adv_f003_ran_line_without_status_is_not_passed(tmp_path):
    """F003: abgeschnittener unittest-Lauf (Ran-Zeile ohne Statuszeile) nach
    einem gruenen Lauf -> False (fail-safe)."""
    text = _read_fixture("unittest_green_verbose.txt") + "Ran 5 tests in 0.1s\n"
    valid, msg = _validate(_write(tmp_path, "ut_truncated.txt", text))
    assert valid is False, msg
    assert "NOT PASSED" in msg


def test_adv_f004_huge_numbers_do_not_raise(tmp_path):
    """F004: riesige Zahlen werfen nicht und ergeben nie True."""
    green = _read_fixture("node_spec_green.txt")
    node_text = green.replace("ℹ fail 0", "ℹ fail " + "9" * 400)
    ut = _read_fixture("unittest_green_verbose.txt")
    ut_text = ut.replace("Ran 3 tests", "Ran " + "9" * 5000 + " tests")
    for name, text in (("node_huge.txt", node_text), ("ut_huge.txt", ut_text)):
        valid, msg = _validate(_write(tmp_path, name, text))
        assert valid is not True, f"{name}: {msg}"


def test_adv_f005_node_pass_zero_without_skips_not_passed(tmp_path):
    """F005: `tests 3 / pass 0 / fail 0` ohne skipped/todo -> False NOT PASSED.
    Synthetisch abgeleitet aus node_spec_green.txt (Zaehlwert ersetzt)."""
    green = _read_fixture("node_spec_green.txt")
    assert "ℹ pass 3" in green
    text = green.replace("ℹ pass 3", "ℹ pass 0")
    valid, msg = _validate(_write(tmp_path, "node_pass_zero_synthetic.txt", text))
    assert valid is False, msg
    assert "NOT PASSED" in msg

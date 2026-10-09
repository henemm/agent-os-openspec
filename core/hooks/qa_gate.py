#!/usr/bin/env python3
"""
QA Gate v3.1 — Validates test output and sets adversary_verdict.

Project-agnostic version. Validates test output files for freshness,
content patterns, and test results. Sets verdict via workflow.py CLI.

Supports adversary dialog checklist validation via --checklist flag.
Tri-state verdicts: VERIFIED / BROKEN (exit 1) / AMBIGUOUS (exit 0, flagged).

Usage:
    python3 qa_gate.py <test-output-file>
    python3 qa_gate.py <test-output-file> --screenshot <path>
    python3 qa_gate.py <test-output-file> --checklist <artifact-path>
    python3 qa_gate.py <test-output-file> --no-visual "reason"
    python3 qa_gate.py <test-output-file> --infra --no-visual "reason"
    python3 qa_gate.py --run [--timeout <s>] [--checklist <md>] [--screenshot <png>]
                             [--infra] [--no-visual "reason"]
    python3 qa_gate.py --check

--run (#345): das Gate startet `qa_gate.test_command` aus config.yaml selbst
(bash -o pipefail; nie ein Befehl von der Kommandozeile), Ausgabe fest nach
docs/artifacts/<workflow>/test-run-output.txt. Exit != 0 ist BROKEN, bei Exit 0
entscheidet die Textauswertung (unbekannt -> AMBIGUOUS).

Exit Codes: 0 = VERIFIED or AMBIGUOUS, 1 = BROKEN/FAILED
"""

from hook_utils import setup_path, strip_ansi
setup_path()

import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from hook_utils import find_project_root, find_worktree_root

# Generic test patterns (project-agnostic)
TEST_PATTERNS = [
    r"Test Suite", r"Test Case", r"test session starts",
    r"Executed \d+ test", r"passed|failed", r"PASSED|FAILED",
    r"tests?, \d+ failures?", r"test result:",
    r"\d+ tests? ran", r"OK \(", r"FAIL",
    r"--- (PASS|FAIL|SKIP):",      # go test -v (je Test) — Issue #76
    r"(?m)^(ok|FAIL)\s+\S+",       # go test (je Paket) — Issue #76
    r"Test run with \d+ tests?",   # Swift Testing (Summary) — Issue #388
]

# go test: Paket-Summenzeile MIT Dauer-/Cache-Suffix. Das Suffix ist Pflicht,
# damit TAP-Zeilen (`ok 1 - beschreibung`) nicht als Go-Paketzeile durchgehen —
# sonst würde eine TAP-Ausgabe mit `not ok`-Fails über den Go-Zweig als
# PASSED gewertet (False-Pass-Richtung, ausgeschlossen).
_GO_TEST_RE = re.compile(r"(?m)^--- (PASS|FAIL|SKIP): ")
_GO_PKG_OK_RE = re.compile(r"(?m)^ok\s+\S+\s+(?:[\d.]+s|\(cached\))")
_GO_PKG_FAIL_RE = re.compile(r"(?m)^FAIL\s+\S+")

# xcodebuild/XCTest-Summary, auch in der Apple-Variante mit Uebersprungenen (#275).
_EXECUTED_RE = re.compile(
    r"Executed (\d+) tests?, with (?:(\d+) tests? skipped and )?(\d+) failures?"
)

# Swift Testing (#388): xcodebuild zaehlt `@Test`-Tests nicht in der
# Executed-Zeile. Roh: `✔ Test run with N tests in K suites passed after …`
# bzw. `✘ Test run with N tests … failed …`; nach xcbeautify bleiben nur die
# ✔/✘-Zeilen je Test und `Suite "…" passed|failed`. Ein ✔ allein (mocha, node
# spec) ist KEIN Swift-Testing-Beleg — erst Summary oder Suite-Zeile aktivieren
# den Zweig.
# Fuehrendes Symbol: nur die Swift-Testing-Glyphen ✔ ✘ ✖ ◇ ➜ bzw. auf macOS
# SF-Symbols aus der Private-Use-Area (􁁛 pass, 􀢄 fail), optional mit
# Variationsselektor. Pflicht fuer Summary und Suite-Zeile, ebenso das
# `after …` dahinter: so aktiviert eine zufaellige Zeile wie `Suite Auth passed`
# oder `- Test run with 5 tests passed` im Log eines anderen Runners den Zweig
# nicht (#390).
_SWIFT_GLYPH = "[\u2714\u2718\u2716\u25c7\u279c\U00100000-\U0010fffd]\ufe0e?\ufe0f?"
_SWIFT_RUN_RE = re.compile(
    r"(?m)^\s*" + _SWIFT_GLYPH
    + r"\s+Test run with (\d{1,9}) tests?\b[^\n]*?\b(passed|failed) after\b")
# Suite-Namen sind nur mit Anzeigenamen gequotet: `Suite "Name" passed` / `Suite MyTests passed`
# Ohne Glyphe (xcbeautify) nur die gequotete Form; die ungequotete braucht die Glyphe.
_SWIFT_SUITE_RE = re.compile(
    r'(?m)^\s*(?:' + _SWIFT_GLYPH + r'\s+Suite (?:"[^"\n]*"|[^\s"]+)|Suite "[^"\n]*")'
    r' (passed|failed) after\b')
_SWIFT_PASS_LINE_RE = re.compile(
    "(?m)^\\s*[\u2714\U0010105b]\ufe0e?\ufe0f?\\s+(?!Suite |Test run with )\\S")
# ✘ und 􀢄 sind immer Fehlschlag; ✖ ist bei Swift Testing auch das Symbol fuer
# bekannte Probleme (withKnownIssue) und zaehlt nur ohne diese Form.
_SWIFT_FAIL_LINE_RE = re.compile("(?m)^\\s*[\u2718\U00100884]\ufe0e?\ufe0f?\\s+\\S")
_SWIFT_CROSS_LINE_RE = re.compile("(?m)^\\s*\u2716\ufe0e?\ufe0f?\\s+(\\S.*)$")
_SWIFT_KNOWN_ISSUE_RE = re.compile(
    r"^Test .*?(?:\bpassed after\b.*\bwith \d+ known issues?\b|\brecorded a known issue\b)")
_SWIFT_SKIP_LINE_RE = re.compile("(?m)^\\s*\u279c\ufe0e?\ufe0f?\\s+Test .*\\bskipped\\b")
# Abbruch neben gruenem Swift Testing: Crash, Build- oder Testlauf-Fehler
_SWIFT_ABORT_RE = re.compile(
    r"(?m)\*\* (?:TEST (?:EXECUTE )?|BUILD )FAILED \*\*|^\s*Testing failed:"
    r"|Restarting after unexpected exit")

def _set_verdict(verdict: str) -> None:
    """Set adversary_verdict on active workflow via workflow.py CLI."""
    workflow_py = Path(__file__).parent / "workflow.py"
    result = subprocess.run(
        [sys.executable, str(workflow_py), "set-field", "adversary_verdict", verdict],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(
            f"ERROR: Failed to persist adversary_verdict via workflow.py: "
            f"{result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)


def _find_pytest_summary_line(content: str) -> str | None:
    """Findet die letzte echte pytest-Summary-Zeile in der Testausgabe.

    Bindet den Scan an das strukturelle pytest-Summary-Format (Liste aus
    '<N> <status>'-Tokens, optional von '='-Rahmen umschlossen, optional mit
    'in X.Ys' Laufzeit-Suffix) statt an eine beliebige Fundstelle im
    Gesamttext. Verhindert False-BLOCK durch anderswo zitierten Text
    (z.B. eine Zeile, die ueber den Fix berichtet und dabei eine Zahl+"failed"
    nennt) UND False-PASS durch zitierten Text (eine Zahl+"passed" ohne
    echte Summary-Zeile).

    Liegen mehrere echte Summary-Zeilen vor (mehrere aneinandergehaengte
    Testlaeufe in derselben Datei), wird die LETZTE zurueckgegeben.
    """
    # Summary-Zeile: Liste aus '<N> <status>'-Tokens, danach optional ein
    # Laufzeit-Suffix in den real vorkommenden Formen:
    #   - pytest:     'in X.Ys', ab 60s Laufzeit zusaetzlich '(H:MM:SS)'
    #                 dahinter — als Folge, nicht Alternative (Issue #79)
    #   - Playwright: '(X.Ys)' in Klammern; ab 60s in Minuten '(1.5m)',
    #                 real genutzte Einheiten: ms / s / m / h (Issue #76)
    # Der Klammer-Inhalt MUSS eine Dauer oder H:MM:SS-Zeit sein und die Zeile
    # bleibt full-line-verankert: Prosa mit Klammer ohne Dauer (z.B.
    # '5 passed (siehe oben)') matcht dadurch weiterhin NICHT (AC-4-Grenze).
    line_re = re.compile(
        r"^\s*=*\s*(?:\d+\s+\w+\s*,?\s*)+"
        r"(?:in\s+[\d.]+s\s*(?:\(\d+:\d{2}:\d{2}\)\s*)?"
        r"|\(\d+(?:\.\d+)?(?:ms|s|m|h)\)\s*)?=*\s*$"
    )
    status_re = re.compile(r"\d+\s+(passed|failed|error|skipped)")
    # Terminal-Runner (Playwright/farbiges pytest) schreiben ANSI-Steuercodes
    # vor die Summary-Zeile; die werden pro Zeile entfernt (hook_utils.strip_ansi,
    # #275), bevor die full-line-Verankerung greift.
    last = None
    for raw in content.splitlines():
        line = strip_ansi(raw)
        if line_re.match(line) and status_re.search(line):
            last = line
    return last


def _not_passed_skipped(skipped: int) -> tuple[bool, str]:
    """#273-Regel: null bestanden + Uebersprungenes ist kein Erfolg."""
    return False, f"Tests NOT PASSED: 0 passed, {skipped} skipped (nichts bestanden)"


def _evaluate_executed(total: int, skipped: int, failures: int) -> tuple[bool, str]:
    """Wertet die letzte 'Executed …'-Zeile aus (#275)."""
    if failures > 0:
        return False, f"Tests FAILED: {failures}/{total} failures"
    if total == 0:
        return False, "Tests NOT PASSED: 0 tests executed (nichts gelaufen)"
    if skipped > 0 and total - skipped - failures <= 0:
        return _not_passed_skipped(skipped)
    suffix = f" ({skipped} skipped)" if skipped else ""
    return True, f"Tests PASSED: {total} tests, 0 failures{suffix}"


def _other_runner_red(content: str) -> bool:
    """Rote Evidenz eines anderen Runners im selben Log (#390).

    Ein gruenes Swift-Testing-Ergebnis kehrt vor den pytest-/go-/cargo-/
    mocha-/jest-Auswertungen zurueck und darf deren Rot nicht ueberstimmen.
    """
    line = _find_pytest_summary_line(content)
    if line is not None:
        verdict = _evaluate_pytest_summary(line)
        if verdict is not None and not verdict[0]:
            return True
    return bool(_GO_PKG_FAIL_RE.search(content) or "\n--- FAIL: " in "\n" + content
                or _CARGO_FAILED_RE.search(content)
                or re.search(r"(?m)^\s*\d+ failing\b", content)
                or re.search(r"(?m)^Tests:.*\b[1-9]\d* failed\b", content))


def _swift_testing_result(content: str) -> "tuple[bool | None, int, int] | None":
    """Swift-Testing-Befund (#388): (gruen?, Anzahl Tests, uebersprungen).

    None = keine Swift-Testing-Ausgabe. gruen=False bei jeder ✘/✖/􀢄-Zeile,
    fehlgeschlagener Suite, roter Summary oder Abbruch-Marker (Crash,
    `** TEST/BUILD FAILED **`) — eine gruene Summary vor dem Crash zaehlt nicht. Anzahl: Summe der Summaries,
    sonst ✔- plus ➜-Zeilen je Test (nach xcbeautify inkl. XCTest-Tests).
    """
    runs = _SWIFT_RUN_RE.findall(content)
    suites = _SWIFT_SUITE_RE.findall(content)
    if not runs and not suites:
        return None
    skipped = len(_SWIFT_SKIP_LINE_RE.findall(content))
    cross_fails = [m.group(1) for m in _SWIFT_CROSS_LINE_RE.finditer(content)
                   if not _SWIFT_KNOWN_ISSUE_RE.search(m.group(1))]
    if (any(status == "failed" for _, status in runs) or "failed" in suites
            or _SWIFT_FAIL_LINE_RE.search(content) or cross_fails
            or _SWIFT_ABORT_RE.search(content) or _other_runner_red(content)):
        return False, 0, skipped
    if runs:
        return True, sum(int(n) for n, _ in runs), skipped
    return True, len(_SWIFT_PASS_LINE_RE.findall(content)) + skipped, skipped


def _evaluate_pytest_summary(line: str) -> "tuple[bool, str] | None":
    """Wertet eine pytest-Summary-Zeile aus; None = nicht bestimmbar."""
    pytest_fail = re.search(r"(\d+)\s+failed", line)
    pytest_pass = re.search(r"(\d+)\s+passed", line)
    pytest_skip = re.search(r"(\d+)\s+skipped", line)
    pytest_err = re.search(r"(\d+)\s+errors?\b", line)
    if pytest_fail and int(pytest_fail.group(1)) > 0:
        return False, f"Tests FAILED: {pytest_fail.group(1)} failed"
    if pytest_err and int(pytest_err.group(1)) > 0:
        return False, f"Tests FAILED: {pytest_err.group(1)} error(s)"
    n_pass = int(pytest_pass.group(1)) if pytest_pass else 0
    n_skip = int(pytest_skip.group(1)) if pytest_skip else 0
    if n_pass == 0 and n_skip > 0:
        return _not_passed_skipped(n_skip)
    if (pytest_pass or pytest_fail) and n_pass == 0:
        return False, "Tests NOT PASSED: 0 passed (nichts bestanden)"
    if pytest_pass or pytest_fail:
        suffix = f" ({n_skip} skipped)" if n_skip else ""
        return True, f"Tests PASSED: {n_pass} passed{suffix}"
    return None


# Python unittest: 'Ran N tests in X.XXXs', danach Statuszeile (#313).
# Ziffern auf 9 begrenzt: riesige Zahlen gelten als "nicht erkannt" statt zu werfen.
_UNITTEST_RAN_RE = re.compile(r"(?m)^Ran (\d{1,9}) tests? in [\d.]+s$")
_UNITTEST_STATUS_RE = re.compile(r"(?m)^(OK|FAILED)(?: \(([^()]*)\))?$")
_UNITTEST_NO_TESTS_RE = re.compile(r"(?m)^NO TESTS RAN$")
_UNITTEST_COUNTER_RE = re.compile(r"([a-z][a-z ]*)=(\d{1,9})")

# node --test: Summary-Block im Spec- (ℹ) oder TAP-Reporter (#) (#327).
_NODE_LINE_RE = re.compile(
    r"(?m)^(ℹ|#) (tests|suites|pass|fail|cancelled|skipped|todo|duration_ms) (\d{1,9}(?:\.\d+)?)$"
)
# Rot-Evidenz, die ein gruenes unittest/node-Ergebnis nicht ueberstimmen darf.
_CARGO_FAILED_RE = re.compile(r"(?m)^test result: FAILED")
# xcodebuild-Marker in seiner echten Form `** TEST FAILED **` (#347 F101): ein
# Testname oder Docstring, der die Worte nur erwaehnt, ist keine Rot-Evidenz —
# auch nicht am Zeilenanfang (unittest -v druckt den Docstring dort). Ueberall
# in der Zeile, damit Zeitstempel/fastlane-Praefixe ihn nicht verstecken.
_TEST_FAILED_MARKER_RE = re.compile(r"\*\* TEST (?:EXECUTE )?FAILED \*\*")
_NODE_COUNTS = ("pass", "fail", "cancelled", "skipped", "todo")


def _evaluate_unittest_run(total: int, status: str) -> "tuple[bool, str] | None":
    """Wertet einen einzelnen unittest-Lauf (Ran-Zeile + Statuszeile) aus."""
    if status == "NO TESTS RAN" or total == 0:
        return False, "Tests NOT PASSED: 0 tests executed (nichts gelaufen)"
    m = _UNITTEST_STATUS_RE.match(status)
    if not m:  # abgeschnittener Lauf: fail-safe rot
        return False, "Tests NOT PASSED: unittest-Lauf ohne Abschlusszeile"
    c = {k.strip(): int(v) for k, v in _UNITTEST_COUNTER_RE.findall(m.group(2) or "")}
    fails, errs = c.get("failures", 0), c.get("errors", 0)
    unexp, skipped = c.get("unexpected successes", 0), c.get("skipped", 0)
    if m.group(1) == "FAILED" or fails or errs or unexp:
        extra = f", {unexp} unexpected successes" if unexp else ""
        return False, f"Tests FAILED: {fails} failures, {errs} errors{extra} (unittest)"
    if skipped > 0 and total - skipped <= 0:
        return _not_passed_skipped(skipped)
    suffix = f" ({skipped} skipped)" if skipped else ""
    return True, f"Tests PASSED: {total} tests (unittest){suffix}"


def _evaluate_unittest(content: str) -> "tuple[bool, str] | None":
    """Wertet alle unittest-Laeufe aus; jede rote Evidenz gewinnt. None = kein unittest."""
    lines = content.splitlines()
    results = []
    for idx, line in enumerate(lines):
        m = _UNITTEST_RAN_RE.match(line)
        if not m:
            continue
        status = next((l.strip() for l in lines[idx + 1:] if l.strip()), "")
        verdict = _evaluate_unittest_run(int(m.group(1)), status)
        if verdict is not None:
            results.append(verdict)
    if not results and _UNITTEST_NO_TESTS_RE.search(content):
        return False, "Tests NOT PASSED: 0 tests executed (nichts gelaufen)"
    if not results:
        return None
    return next((r for r in results if not r[0]), results[-1])


def _node_blocks(content: str) -> "list[dict]":
    """Liefert die Felder ALLER zusammenhaengenden node-Summary-Bloecke."""
    blocks, current, prefix = [], {}, None
    for line in content.splitlines():
        m = _NODE_LINE_RE.match(line)
        if not m or (prefix is not None and m.group(1) != prefix):
            if current:
                blocks.append(current)
            current, prefix = {}, None
        if m and m.group(2) in current:
            # Feld erneut: neuer Block, auch ohne Trennzeile (#347 F102)
            blocks.append(current)
            current = {}
        if m:
            prefix = m.group(1)
            current[m.group(2)] = float(m.group(3))
    if current:
        blocks.append(current)
    return blocks


def _evaluate_node_block(block: dict) -> "tuple[bool, str] | None":
    """Wertet einen node --test-Summary-Block aus. None = unvollstaendig."""
    if block.get("fail", 0) > 0 or block.get("cancelled", 0) > 0:
        # Rot-Evidenz zaehlt auch im unvollstaendigen Block (Pruefrunde zu #347)
        return False, (f"Tests FAILED: {int(block.get('fail', 0))} failed, "
                       f"{int(block.get('cancelled', 0))} cancelled (node --test)")
    if not all(k in block for k in ("tests", "pass", "fail")):
        return None
    # Plausibilitaet (#347 F104): Zaehlfelder ganzzahlig, Summe stimmt — sonst
    # ist der Block nicht echt node-erzeugt, fail-safe rot.
    counters = {k: v for k, v in block.items() if k != "duration_ms"}
    if any(v != int(v) for v in counters.values()):
        return False, "Tests NOT PASSED: node-Summary mit nicht ganzzahligem Zaehler (unplausibel)"
    if all(k in block for k in _NODE_COUNTS) and \
            int(block["tests"]) != sum(int(block[k]) for k in _NODE_COUNTS):
        return False, "Tests NOT PASSED: node-Summary, tests != pass+fail+cancelled+skipped+todo"
    tests, passed, failed = int(block["tests"]), int(block["pass"]), int(block["fail"])
    cancelled = int(block.get("cancelled", 0))
    skipped = int(block.get("skipped", 0)) + int(block.get("todo", 0))
    if failed > 0 or cancelled > 0:
        return False, f"Tests FAILED: {failed} failed, {cancelled} cancelled (node --test)"
    if tests == 0:
        return False, "Tests NOT PASSED: 0 tests executed (nichts gelaufen)"
    if passed == 0:
        if skipped > 0:
            return _not_passed_skipped(skipped)
        return False, "Tests NOT PASSED: 0 passed (nichts bestanden)"
    suffix = f" ({skipped} skipped)" if skipped else ""
    return True, f"Tests PASSED: {passed} passed (node --test){suffix}"


def _evaluate_node_test(content: str) -> "tuple[bool, str] | None":
    """Wertet alle node --test-Bloecke aus; jede rote Evidenz gewinnt. None = nicht erkannt."""
    results = [r for r in map(_evaluate_node_block, _node_blocks(content)) if r is not None]
    if not results:
        return None
    return next((r for r in results if not r[0]), results[-1])


def validate_test_output(filepath: str, infra: bool = False,
                         trusted: bool = False) -> tuple[bool, str]:
    """Validate test output file. Returns (valid, message).

    trusted=True (#345, `--run`): die Datei hat das Gate selbst erzeugt —
    Altersgrenze und Groessen-/"fabricated"-Vorfilter entfallen.
    """
    path = Path(filepath)

    if not path.exists():
        return False, f"File not found: {filepath}"

    age_min = (time.time() - path.stat().st_mtime) / 60
    if not trusted and age_min > 30:
        return False, f"Test output is {age_min:.0f} min old (max 30). Re-run tests."

    size = path.stat().st_size
    if not trusted and size < 100:
        return False, f"Test output too small ({size} bytes). Looks fabricated."

    content = strip_ansi(path.read_text(errors="replace"))

    # unittest / node --test (#313, #327): Rot zuerst, vor allen anderen
    # Zweigen — sonst gewinnt bei gemischter Ausgabe ein spaeteres Gruen.
    runner_results = [r for r in (_evaluate_unittest(content), _evaluate_node_test(content))
                      if r is not None]
    red = next((r for r in runner_results if not r[0]), None)
    if red is not None:
        return red

    # Must contain test patterns (erkannter unittest/node-Block gilt selbst als Beleg)
    matches = sum(1 for p in TEST_PATTERNS if re.search(p, content, re.IGNORECASE))
    if matches < 2 and not runner_results:
        return False, f"Doesn't look like test output (matched {matches}/{len(TEST_PATTERNS)} patterns)."

    # Check for failures via common patterns
    # Pattern: "Executed N tests, with [S tests skipped and ]M failures" (#275).
    # Die Zahlen der Meldung stammen aus der LETZTEN Zeile (Gesamtsumme;
    # Summieren ueber Suite-Zeilen wuerde sie vervielfachen). Hat aber
    # IRGENDEINE Zeile failures > 0, ist der Lauf rot: ist die letzte Zeile
    # gruen, wird die erste rote Zeile gewertet.
    # Kehrt bei vorhandener Executed-Zeile IMMER zurueck — der spaetere
    # 'TEST SUCCEEDED'-Fallback kann die skipped-Regel daher nicht aushebeln.
    exec_rows = [tuple(int(x or 0) for x in m) for m in _EXECUTED_RE.findall(content)]
    # Swift Testing (#388): jede rote Evidenz gewinnt; eine gruene Summary
    # wird zur XCTest-Zahl addiert, sodass `Executed 0` sie nicht ueberstimmt.
    swift = _swift_testing_result(content)
    if swift is not None and not swift[0]:
        return False, "Tests FAILED: Swift Testing meldet fehlgeschlagene Tests/Suites oder Abbruch"
    if exec_rows:
        red_rows = [r for r in exec_rows if r[2] > 0]
        row = red_rows[0] if red_rows and exec_rows[-1][2] == 0 else exec_rows[-1]
        if swift is not None and row[2] == 0:
            _, n_swift, swift_skipped = swift
            if _SWIFT_RUN_RE.search(content):
                total = row[0] + n_swift
            else:  # xcbeautify: ✔-Zeilen zaehlen XCTest bereits mit
                total = max(row[0], n_swift)
            row = (total, row[1] + swift_skipped, 0)
        return _evaluate_executed(*row)
    if swift is not None:
        return _evaluate_executed(swift[1], swift[2], 0)

    # Pattern: pytest summary line ("N passed, M failed, ...").
    # Bound to the real summary line (not a whole-text scan) and check the
    # failure count > 0, so a green suite ("0 failed") is not blocked and a
    # quoted "N failed"/"N passed" outside the summary can't flip the verdict.
    summary_line = _find_pytest_summary_line(content)
    if summary_line is not None:
        verdict = _evaluate_pytest_summary(summary_line)
        if verdict is not None:
            return verdict

    # Pattern: go test — '--- PASS:'/'--- FAIL:' je Test, 'ok <pkg> <dauer>'/
    # 'FAIL <pkg>' je Paket (Issue #76). Greift nur, wenn keine pytest-Summary
    # gefunden wurde. Fehlerrichtung: jede FAIL-Evidenz gewinnt gegen PASS.
    go_results = _GO_TEST_RE.findall(content)
    go_pkg_ok = _GO_PKG_OK_RE.search(content)
    go_pkg_fail = _GO_PKG_FAIL_RE.search(content)
    if go_results or go_pkg_ok or go_pkg_fail:
        go_fails = sum(1 for r in go_results if r == "FAIL")
        if go_fails or go_pkg_fail:
            return False, f"Tests FAILED: {go_fails or 1} failed (go test)"
        go_passes = sum(1 for r in go_results if r == "PASS")
        return True, f"Tests PASSED: {go_passes or 'ok'} passed (go test)"

    # Gruenes unittest/node-Ergebnis erst nach Executed/pytest/go (#313, #327).
    # Vorher cargo-/Marker-Rot pruefen: jede rote Evidenz gewinnt.
    if runner_results:
        if _CARGO_FAILED_RE.search(content) or _TEST_FAILED_MARKER_RE.search(content):
            return False, "Tests FAILED: cargo/TEST FAILED-Marker neben gruenem unittest/node-Lauf"
        return runner_results[0]

    # Pattern: "test result: ok" (cargo/rust)
    if "test result: ok" in content:
        return True, "Tests PASSED (test result: ok)"

    # Pattern: generic markers
    if "TEST FAILED" in content or "FAILED" in content.upper().split("\n")[-5:]:
        return False, "TEST FAILED marker found."

    if "TEST SUCCEEDED" in content:
        return True, "TEST SUCCEEDED"

    return False, "Could not determine test result."


DEFAULT_RUN_TIMEOUT = 540  # unter dem 600-s-Limit des Bash-Tools (#345)
UNREADABLE_MSG = "Exit 0, Ausgabe nicht auswertbar"


def _opt(args: list, flag: str) -> "str | None":
    """Wert hinter `flag` oder None."""
    if flag in args:
        idx = args.index(flag)
        if idx + 1 < len(args):
            return args[idx + 1]
    return None


def _usage_error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def _sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_stamp(stamp: dict) -> None:
    """Stempel `qa_run_stamp` ueber den Schreibpfad in workflow.py, nie set-field (#345)."""
    stamp["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        from workflow import write_qa_run_stamp
        write_qa_run_stamp(stamp)  # False = kein aktiver Workflow, still
    except Exception as exc:  # Stempel darf das Urteil nicht verhindern
        print(f"Warnung: qa_run_stamp nicht geschrieben: {exc}", file=sys.stderr)


def _pump(stream, out_file) -> None:
    """Kopiert die Ausgabe zeilenweise in die Artefaktdatei und auf stdout.

    Bricht stdout weg (`| head`), wird nur das Spiegeln abgeschaltet und fd 1 auf
    /dev/null gelegt; Datei und Pipe laufen bis zum Ende weiter (#345 F002).
    """
    mirror = sys.stdout is not None
    for line in iter(stream.readline, b""):
        out_file.write(line)
        out_file.flush()
        if mirror:
            try:
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
            except OSError:
                mirror = False
                os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def _kill_group(proc) -> None:
    """Beendet die ganze Prozessgruppe des Laufs: erst SIGTERM, dann SIGKILL."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def run_and_capture(cmd: str, out_path, timeout: int) -> "tuple[int, bool]":
    """Fuehrt `cmd` mit pipefail aus, schreibt stdout+stderr nach out_path (#345).

    Returns (exit_code, timed_out). Gelesen wird in einem Thread, damit ein
    Kindprozess, der die Pipe offen haelt, den Timeout nicht blockiert.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if sys.stdout is not None:  # F005: `--run >&-` laesst sys.stdout None
        sys.stdout.flush()
    fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644)
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:  # F004: erst pruefen, dann kuerzen
        os.close(fd)
        _usage_error(f"Artefaktpfad {out_path} ist keine eigenstaendige Datei — Abbruch.")
    os.ftruncate(fd, 0)
    with os.fdopen(fd, "wb") as out_file:
        proc = subprocess.Popen(["bash", "-o", "pipefail", "-c", cmd],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True)
        reader = threading.Thread(target=_pump, args=(proc.stdout, out_file), daemon=True)
        reader.start()
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(proc)
        reader.join(timeout=5)
        if reader.is_alive():  # Hintergrundprozess haelt die Pipe offen
            _kill_group(proc)
            reader.join(timeout=5)
    return proc.wait(), timed_out


def _judge_run(code: int, timed_out: bool, timeout: int, out_path) -> "tuple[str, str]":
    """Urteil "rot gewinnt" (#345): (BROKEN|VERIFIED|AMBIGUOUS, Meldung)."""
    if timed_out:
        return "BROKEN", f"Timeout nach {timeout} s (Prozessgruppe beendet)"
    if code != 0:
        return "BROKEN", f"Testbefehl endete mit Exit-Code {code}"
    valid, message = validate_test_output(str(out_path), trusted=True)
    if valid:
        return "VERIFIED", message
    if message.startswith(("Could not determine", "Doesn't look like test output")):
        return "AMBIGUOUS", UNREADABLE_MSG
    return "BROKEN", message


RUN_VALUE_OPTIONS = ("--timeout", "--checklist", "--screenshot", "--no-visual")
RUN_FLAG_OPTIONS = ("--infra",)


def _positive_int(value, what: str) -> int:
    """Positive Ganzzahl oder Fehlbedienung (Exit 1)."""
    try:
        number = int(str(value).strip())
    except ValueError:
        number = 0
    if number <= 0:
        _usage_error(f"{what} braucht eine positive ganze Sekundenzahl, nicht {value!r}")
    return number


def _check_run_args(args: list) -> "int | None":
    """Nur bekannte Optionen nach `--run` (#345 v2), sonst Exit 1 vor jeder Ausfuehrung.

    Returns den `--timeout`-Wert der Kommandozeile oder None.
    """
    timeout, i = None, 1
    while i < len(args):
        arg = args[i]
        if arg in RUN_FLAG_OPTIONS:
            i += 1
            continue
        if arg not in RUN_VALUE_OPTIONS:
            _usage_error(f"--run nimmt kein Argument {arg!r} an. Der Testbefehl kommt aus "
                         "config.yaml (qa_gate.test_command); erlaubt: "
                         + ", ".join(RUN_VALUE_OPTIONS + RUN_FLAG_OPTIONS))
        if i + 1 >= len(args):
            _usage_error(f"{arg} braucht einen Wert")
        if arg == "--timeout":
            timeout = _positive_int(args[i + 1], "--timeout")
        i += 2
    return timeout


def _run_config(cli_timeout: "int | None") -> "tuple[str, int]":
    """Testbefehl und Timeout aus config.yaml (`qa_gate`), `--timeout` gewinnt."""
    from config_loader import load_config
    section = load_config().get("qa_gate") or {}
    if not isinstance(section, dict):
        section = {}
    cmd = section.get("test_command")
    if not isinstance(cmd, str) or not cmd.strip():
        _usage_error("Kein Testbefehl konfiguriert: qa_gate.test_command in config.yaml "
                     "setzen (z.B. \"python3 -m pytest tests/ -q\").")
    if cli_timeout is not None:
        return cmd, cli_timeout
    configured = section.get("run_timeout")
    if configured is None:
        return cmd, DEFAULT_RUN_TIMEOUT
    return cmd, _positive_int(configured, "qa_gate.run_timeout")


def _run_mode(cmd: str, timeout: int, wf_name: str) -> "tuple[str, str]":
    """`--run`: konfigurierten Befehl ausfuehren, Stempel schreiben, Urteil liefern."""
    root = find_worktree_root() or find_project_root()
    wf_dir = (wf_name.split() or ["unknown"])[0]  # `status` haengt "[quelle]" an
    if wf_dir in ("unknown", "unknown-error"):  # F003: ohne Workflow nichts ausfuehren
        _usage_error("Kein aktiver Workflow — --run fuehrt nichts aus.")
    rel = Path("docs", "artifacts", wf_dir, "test-run-output.txt")
    out_path = root / rel
    for i in range(1, len(rel.parts) + 1):  # F001: kein Symlink unterhalb der Wurzel
        if root.joinpath(*rel.parts[:i]).is_symlink():
            _usage_error(f"Symlink im Artefaktpfad {root.joinpath(*rel.parts[:i])} — Abbruch.")
    print(f"Running qa_gate.test_command (timeout {timeout} s), output: {out_path}")
    code, timed_out = run_and_capture(cmd, out_path, timeout)
    _write_stamp({"source": "run", "exit_code": code, "output_sha256": _sha256_file(out_path),
                  "output_path": str(out_path),
                  "command_sha256": hashlib.sha256(cmd.encode()).hexdigest()})
    return _judge_run(code, timed_out, timeout, out_path)


def _file_mode(args: list, wf_name: str) -> "tuple[str, str]":
    """Bisheriger Datei-Modus; vermerkt zusaetzlich `source: "file"` (#345)."""
    filepath = args[0]
    print(f"Validating test output: {filepath}")
    valid, message = validate_test_output(filepath, infra="--infra" in args)
    if Path(filepath).is_file():
        _write_stamp({"source": "file", "output_sha256": _sha256_file(filepath),
                      "output_path": str(Path(filepath))})
    if not valid:
        print(f"\nFAILED — {message}")
        print(f"Workflow: {wf_name}")
        print("Fix the issues and re-run tests.")
        sys.exit(1)
    return "VERIFIED", message


def main():
    args = sys.argv[1:]

    if not args or args[0] == "--check":
        workflow_py = Path(__file__).parent / "workflow.py"
        subprocess.run([sys.executable, str(workflow_py), "status"])
        sys.exit(0)

    run_mode = args[0] == "--run"
    if not run_mode and "--run" in args:
        _usage_error("--run und eine Testausgabedatei schliessen sich aus.")
    if run_mode:  # Fehlbedienung endet vor jedem anderen Schritt (#345 v2)
        run_cmd, run_timeout = _run_config(_check_run_args(args))

    if "--no-visual" in args:
        print(f"Screenshot skipped: {_opt(args, '--no-visual') or 'no reason given'}")

    wf_name = _workflow_name()
    if run_mode:
        kind, message = _run_mode(run_cmd, run_timeout, wf_name)
    else:
        kind, message = _file_mode(args, wf_name)
    if kind == "BROKEN":
        _set_verdict(f"BROKEN:{message}")
        print(f"\nBROKEN:{message}")
        print(f"Workflow: {wf_name}")
        sys.exit(1)
    _finish(args, wf_name, message, kind == "AMBIGUOUS")


def _workflow_name() -> str:
    """Name des aktiven Workflows laut `workflow.py status`."""
    workflow_py = Path(__file__).parent / "workflow.py"
    result = subprocess.run(
        [sys.executable, str(workflow_py), "status"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(
            f"ERROR: Could not read workflow status via workflow.py: "
            f"{result.stderr.strip()}",
            file=sys.stderr,
        )
        wf_name = "unknown-error"
    else:
        wf_name = "unknown"
        for line in result.stdout.splitlines():
            if line.startswith("Workflow:"):
                wf_name = line.split(":", 1)[1].strip()
    return wf_name


def _check_screenshot(args: list) -> None:
    """Validate screenshot if required."""
    screenshot = _opt(args, "--screenshot")
    if screenshot and "--no-visual" not in args:
        ss_path = Path(screenshot)
        if not ss_path.exists():
            print(f"\nFAILED — Screenshot not found: {screenshot}")
            sys.exit(1)
        if ss_path.stat().st_size < 1000:
            print(f"\nFAILED — Screenshot too small ({ss_path.stat().st_size} bytes)")
            sys.exit(1)


def _finish(args: list, wf_name: str, message: str, is_ambiguous: bool) -> None:
    """Screenshot, Checkliste, Verdict setzen — gemeinsam fuer Datei- und --run-Modus."""
    _check_screenshot(args)
    checklist = _opt(args, "--checklist")

    # Validate adversary dialog checklist if provided
    if checklist:
        try:
            from adversary_dialog import dialog_verdict, validate_dialog_artifact_ex
            cl_valid, cl_message, cl_kind = validate_dialog_artifact_ex(checklist)
            if not cl_valid:
                print(f"\nCHECKLIST FAILED — {cl_message}")
                if cl_kind == "content":
                    # Das Artefakt belegt ein inhaltlich negatives Ergebnis
                    # (BROKEN-Verdict, offene Punkte) → als BROKEN persistieren.
                    _set_verdict(f"BROKEN:{cl_message}")
                else:
                    # Reiner FORMfehler (unbekanntes Vokabular, fehlende
                    # Marker, Alter) ist KEIN inhaltliches Urteil: das
                    # adversary_verdict bleibt unangetastet, statt ein
                    # womoeglich positives Validator-Ergebnis als BROKEN
                    # zu ueberschreiben (Issue #77).
                    print("Formfehler im Artefakt — adversary_verdict bleibt unveraendert.")
                sys.exit(1)
            print(f"Checklist: {cl_message}")
            if dialog_verdict(checklist) == "AMBIGUOUS":  # geparst statt Substring (#259 F003)
                is_ambiguous = True
        except ImportError:
            print("Warning: adversary_dialog module not found, skipping checklist validation")

    if is_ambiguous:
        verdict = f"AMBIGUOUS:{message} — User review recommended"
    else:
        verdict = f"VERIFIED:{message}"

    _set_verdict(verdict)

    print(f"\n{verdict}")
    print(f"Workflow: {wf_name}")
    if is_ambiguous:
        print("Pipeline NOT blocked — but user should review ambiguous findings.")
    elif checklist:
        print("Commit is now allowed.")
    else:
        # #253: ohne geprueftes Dialog-Artefakt ist das kein Freibrief.
        print("Hinweis: Commit-Gate und Phase 8 verlangen zusätzlich ein gestempeltes, "
              "registriertes Dialog-Artefakt (/50-implement Step 8: Dialog, "
              "adversary_dialog.py stamp, workflow.py add-artifact adversary_dialog). "
              "Ein grüner Testlauf allein öffnet den Commit nicht.")
    sys.exit(0)


if __name__ == "__main__":
    main()

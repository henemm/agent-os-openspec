"""RED-Tests für #275 — Testausgaben richtig erkennen (ANSI, xcbeautify, „übersprungen").

Spec: docs/specs/fix-275-testausgabe-erkennung.md (AC-1 … AC-15).

Alle Tests rufen die ECHTEN Hook-Funktionen auf:
- `hook_utils.strip_ansi` (neu, AC-1/AC-2)
- `tdd_enforcement._validate_artifact` (RED-Artefakt-Prüfung, AC-3/4/5/11)
- `qa_gate.validate_test_output` (Verdict-Grundlage, AC-2/6/7/8/9/10/15)
- `post_bash.py` als echter Hook-Prozess mit PostToolUse-Payload (AC-12/13),
  Muster aus tests/test_verdict_pipeline_77.py

Fixtures unter tests/fixtures/testausgabe_275/ stammen aus echten Läufen
(siehe dortige README.md). Weil beide Gates das Dateialter prüfen (qa_gate
max. 30 min, tdd_enforcement max. 24 h), wird der Fixture-Inhalt für jeden
Test unverändert in eine frische Datei unter tmp_path kopiert.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "testausgabe_275"
sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402
import qa_gate  # noqa: E402
import tdd_enforcement  # noqa: E402


# --- Hilfsfunktionen --------------------------------------------------------

def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _write(tmp_path: Path, content, name: str = "output.txt") -> Path:
    p = tmp_path / name
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")
    return p


def _red_check(tmp_path: Path, content, name: str = "red-output.txt"):
    """Fehler-Evidenz-Prüfung in tdd_enforcement auf einem echten Artefakt."""
    p = _write(tmp_path, content, name)
    art = {
        "type": "test_output",
        "path": str(p),
        "description": "RED-Lauf fuer #275: Testausgabe mit Fehlschlag",
    }
    return tdd_enforcement._validate_artifact(art, tmp_path)


def _qa(tmp_path: Path, content, name: str = "test-output.txt"):
    p = _write(tmp_path, content, name)
    return qa_gate.validate_test_output(str(p))


# Neutrale Füllzeilen ohne jedes Fehler-/Platzhalterwort, damit Inline-Artefakte
# die Mindestgröße (80 Bytes) erreichen, ohne selbst Evidenz zu liefern.
_NEUTRAL = (
    "Test Suite 'All tests' started at 2026-10-01 12:48:14.152.\n"
    "Test Suite 'DemoTests' started at 2026-10-01 12:48:14.152.\n"
)

_PYTEST_HEAD = (
    "============================= test session starts ==============================\n"
    "platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.6.0\n"
    "collected 5 items\n\n"
    "test_demo.py .....                                                       [100%]\n\n"
)


# --- AC-1: hook_utils.strip_ansi --------------------------------------------

def test_strip_ansi_removes_codes_keeps_plain():
    strip_ansi = getattr(hook_utils, "strip_ansi", None)
    assert callable(strip_ansi), "hook_utils.strip_ansi() fehlt (AC-1)"
    assert strip_ansi("\x1b[31mFAIL\x1b[0m") == "FAIL"
    assert strip_ansi("\x1b[36;1mnote: \x1b[0mBuilding") == "note: Building"
    plain = "5 passed, 0 failed in 0.31s — ✖ ❌ unverändert"
    assert strip_ansi(plain) == plain
    assert "\x1b" not in strip_ansi(_fixture_bytes("xcbeautify_fail.txt").decode("utf-8"))


# --- AC-2: qa_gate nutzt die gemeinsame ANSI-Entfernung ---------------------

def test_qa_gate_uses_shared_strip_ansi_pytest_color_summary(tmp_path):
    ok, msg = _qa(tmp_path, _fixture_bytes("pytest_color_fail.txt"), "fail.txt")
    assert ok is False, msg
    assert "FAILED" in msg and "1" in msg, msg

    ok, msg = _qa(tmp_path, _fixture_bytes("pytest_color_pass.txt"), "pass.txt")
    assert ok is True, msg
    assert "2 passed" in msg, msg

    assert callable(getattr(hook_utils, "strip_ansi", None)), \
        "hook_utils.strip_ansi() fehlt (AC-2)"
    source = (HOOKS_DIR / "qa_gate.py").read_text(encoding="utf-8")
    assert "\\x1b" not in source, \
        "qa_gate.py enthält noch ein eigenes ANSI-Muster — soll hook_utils.strip_ansi nutzen"
    assert "strip_ansi" in source, "qa_gate.py ruft hook_utils.strip_ansi nicht auf"


# --- AC-3 (#201): ANSI-ummanteltes FAIL + EXIT=1 ----------------------------

def test_ansi_wrapped_fail_with_exit1_accepted_as_red(tmp_path):
    content = (
        _NEUTRAL
        + "tests/demo.test.js \x1b[31mFAIL\x1b[0m\n"
        + "EXIT=1\n"
    )
    assert _red_check(tmp_path, content) is None


# --- AC-4 (#256①): xcbeautify „❌" und weitere Fehlermarker -----------------

def test_xcbeautify_cross_mark_fixture_accepted_as_red(tmp_path):
    raw = _fixture_bytes("xcbeautify_compileerror.txt")
    text = raw.decode("utf-8")
    # Vorbedingung der echten Fixture: „❌" + ANSI, ohne error:/FAILED.
    assert "❌" in text and "\x1b[" in text
    assert "error:" not in text and "FAILED" not in text
    assert _red_check(tmp_path, raw) is None


def test_other_failure_markers_each_accepted_as_red(tmp_path):
    cases = {
        "nur ✖": "    \x1b[31m✖\x1b[0m testAddFailsOnPurpose\n",
        "nur ✘": "    ✘ testAddFailsOnPurpose (0.001 seconds)\n",
        "nur TEST FAILED": "** TEST FAILED **\n",
        "nur Swift-Testing-Zeile": "Test run with 3 tests failed after 0.1 seconds.\n",
        "nur 3 failures": "Executed 5 tests, with 3 failures (3 unexpected) in 0.2 seconds\n",
    }
    rejected = {}
    for i, (label, marker) in enumerate(cases.items()):
        err = _red_check(tmp_path, _NEUTRAL + marker, name=f"red-{i}.txt")
        if err is not None:
            rejected[label] = err.splitlines()[0]
    assert not rejected, f"Als RED abgewiesen, obwohl Fehler-Evidenz vorliegt: {rejected}"


# --- AC-5 (Gegenprobe): grüner Lauf bleibt abgewiesen ------------------------

def test_green_run_artifact_still_rejected_zero_failures_exit0(tmp_path):
    green = _fixture_bytes("pytest_color_pass.txt").decode("utf-8") + (
        "Executed 5 tests, with 0 failures (0 unexpected) in 0.2 seconds\n"
        "test_demo.py::test_one \x1b[32mPASSED\x1b[0m\n"
        "EXIT=0\n"
    )
    err = _red_check(tmp_path, green)
    assert err is not None, "Grüner Lauf wurde als RED-Artefakt akzeptiert"
    assert "keine Fehler-Evidenz" in err, err


# --- AC-6 (#202): Executed-Zeile mit skipped und Fehlschlägen -----------------

def test_executed_skipped_variant_with_failures_reports_failed_count(tmp_path):
    inline = (
        "Test Suite 'All tests' started at 2026-10-01 12:00:00.000.\n"
        "Test Case '-[DemoTests.DemoTests testOne]' passed (0.001 seconds).\n"
        "Executed 5 tests, with 1 test skipped and 3 failures (3 unexpected) "
        "in 0.336 (0.337) seconds\n"
    )
    ok, msg = _qa(tmp_path, inline, "inline.txt")
    assert ok is False, msg
    assert "Could not determine" not in msg, msg
    assert "Tests FAILED" in msg and "3" in msg, msg

    ok, msg = _qa(tmp_path, _fixture_bytes("xcodebuild_skipfail_raw.txt"), "real.txt")
    assert ok is False, msg
    assert "Tests FAILED" in msg and "3" in msg, msg


# --- AC-7: nur die letzte Executed-Zeile zählt -------------------------------

def test_executed_uses_last_line_only(tmp_path):
    # Echter Lauf: dreimal „Executed 2 tests, with 1 failure" (Suite, Bundle, Gesamt).
    ok, msg = _qa(tmp_path, _fixture_bytes("xcodebuild_fail_raw.txt"), "real.txt")
    assert ok is False, msg
    assert "1/2" in msg, f"Meldung soll die Gesamtsumme nennen (1/2): {msg}"
    assert "3/6" not in msg, msg

    # Suite-Zeilen mit unterschiedlichen Zahlen, Gesamtsumme am Ende.
    inline = (
        "Test Suite 'SuiteA' started at 2026-10-01 12:00:00.000.\n"
        "Executed 2 tests, with 1 failure (0 unexpected) in 0.1 (0.1) seconds\n"
        "Test Suite 'SuiteB' started at 2026-10-01 12:00:00.100.\n"
        "Executed 3 tests, with 0 failures (0 unexpected) in 0.1 (0.1) seconds\n"
        "Test Suite 'All tests' started at 2026-10-01 12:00:00.000.\n"
        "Executed 5 tests, with 1 failure (0 unexpected) in 0.2 (0.2) seconds\n"
    )
    ok, msg = _qa(tmp_path, inline, "inline.txt")
    assert ok is False, msg
    assert "1/5" in msg, f"Meldung soll die Gesamtsumme nennen (1/5): {msg}"


# --- AC-8: gemischter Lauf ist grün und nennt Übersprungene ------------------

def test_executed_mixed_run_is_green_and_names_skipped(tmp_path):
    inline = (
        "Test Suite 'All tests' started at 2026-10-01 12:00:00.000.\n"
        "Test Case '-[DemoTests.DemoTests testOne]' passed (0.001 seconds).\n"
        "Executed 5 tests, with 1 test skipped and 0 failures (0 unexpected) "
        "in 0.003 (0.004) seconds\n"
    )
    ok, msg = _qa(tmp_path, inline, "inline.txt")
    assert ok is True, msg
    assert "1 skipped" in msg, msg

    ok, msg = _qa(tmp_path, _fixture_bytes("xcodebuild_mixed_raw.txt"), "real.txt")
    assert ok is True, msg
    assert "1 skipped" in msg, msg


# --- AC-9 (#273-Regel): alles übersprungen / nichts gelaufen + TEST SUCCEEDED -

def test_executed_all_skipped_with_test_succeeded_is_not_green(tmp_path):
    inline = (
        "Test Suite 'All tests' started at 2026-10-01 12:00:00.000.\n"
        "Executed 5 tests, with 5 tests skipped and 0 failures (0 unexpected) "
        "in 0.003 (0.004) seconds\n"
        "** TEST SUCCEEDED **\n"
    )
    ok, msg = _qa(tmp_path, inline, "inline.txt")
    assert ok is False, msg
    assert "5 skipped" in msg, msg

    ok, msg = _qa(tmp_path, _fixture_bytes("xcodebuild_allskipped_raw.txt"), "real.txt")
    assert ok is False, msg
    assert "3 skipped" in msg, msg


def test_executed_zero_tests_with_test_succeeded_is_not_green(tmp_path):
    inline = (
        "Test Suite 'All tests' started at 2026-10-01 12:00:00.000.\n"
        "Test Suite 'All tests' passed at 2026-10-01 12:00:00.001.\n"
        "Executed 0 tests, with 0 failures (0 unexpected) in 0.000 (0.001) seconds\n"
        "** TEST SUCCEEDED **\n"
    )
    ok, msg = _qa(tmp_path, inline)
    assert ok is False, msg
    assert "NOT PASSED" in msg, msg


# --- AC-10 (#273-Regel, pytest) -----------------------------------------------

def test_pytest_all_skipped_not_green_mixed_green_names_skipped(tmp_path):
    ok, msg = _qa(tmp_path, _PYTEST_HEAD
                  + "============================== 0 passed, 5 skipped in 0.31s ===============================\n",
                  "zero_passed.txt")
    assert ok is False, f"0 passed, 5 skipped: {msg}"

    ok, msg = _qa(tmp_path, _PYTEST_HEAD
                  + "============================== 5 skipped in 0.31s ===============================\n",
                  "only_skipped.txt")
    assert ok is False, f"5 skipped: {msg}"

    ok, msg = _qa(tmp_path, _PYTEST_HEAD
                  + "========================= 4 passed, 1 skipped in 0.31s =========================\n",
                  "mixed.txt")
    assert ok is True, f"4 passed, 1 skipped: {msg}"
    assert "1 skipped" in msg, msg


# --- AC-11: RED-Artefakt nur mit Übersprungenem wird abgewiesen ---------------

def test_red_artifact_with_only_skipped_rejected(tmp_path):
    cases = {
        "5 skipped": _PYTEST_HEAD.replace(".....", "sssss")
        + "============================== 5 skipped in 0.31s ===============================\n",
        "⊘": _NEUTRAL + "    ⊘ testSkipOne (bewusst uebersprungen)\n"
                         "    ⊘ testSkipTwo (bewusst uebersprungen)\n",
        "Executed … skipped": _NEUTRAL
        + "Executed 5 tests, with 5 tests skipped and 0 failures (0 unexpected) "
          "in 0.003 (0.004) seconds\n",
    }
    accepted = []
    for i, (label, content) in enumerate(cases.items()):
        err = _red_check(tmp_path, content, name=f"skip-{i}.txt")
        if err is None or "keine Fehler-Evidenz" not in err:
            accepted.append((label, err))
    assert not accepted, f"Nur-übersprungen-Artefakt nicht abgewiesen: {accepted}"


# --- AC-12/AC-13: post_bash als echter Hook-Prozess --------------------------

_POST_BASH_COPY = ["post_bash.py", "hook_utils.py", "config_loader.py"]


def _run_post_bash(tmp_path: Path, command: str, stdout: str):
    """Echten post_bash.py-Lauf ausführen und last_test_run zurückgeben."""
    fake_hooks = tmp_path / "pb_hooks"
    if not fake_hooks.exists():
        fake_hooks.mkdir()
        for fname in _POST_BASH_COPY:
            shutil.copy(HOOKS_DIR / fname, fake_hooks / fname)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    wf_file = wf_dir / "wf1.json"
    wf_file.write_text(json.dumps({
        "name": "wf1", "current_phase": "phase6_implement",
        "adversary_verdict": None,
    }))
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = "wf1"
    env.pop("CLAUDE_TOOL_INPUT", None)
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": stdout, "stderr": ""},
    }
    r = subprocess.run(
        [sys.executable, str(fake_hooks / "post_bash.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env=env, cwd=str(tmp_path),
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(wf_file.read_text())
    assert data.get("adversary_verdict") is None  # #253: nie ein Verdict
    return (data.get("last_test_run") or {}).get("result")


_XCB_CMD = "xcodebuild test -scheme Demo-Package -destination 'platform=macOS' | xcbeautify"


def test_post_bash_ansi_cross_marks_with_pass_pattern_recorded_failed(tmp_path):
    cases = {
        "xcbeautify ✖ (echt) + 3 passed": (
            _XCB_CMD,
            _fixture_bytes("xcbeautify_fail.txt").decode("utf-8") + "3 passed\n",
        ),
        "xcbeautify ❌ (echt) + 3 passed": (
            _XCB_CMD,
            _fixture_bytes("xcbeautify_compileerror.txt").decode("utf-8") + "3 passed\n",
        ),
        "pytest ANSI ✖ + 3 passed": (
            "pytest --color=yes",
            "\x1b[31m✖\x1b[0m test_demo.py::test_kaputt\n"
            "============================== 3 passed in 0.10s ===============================\n",
        ),
    }
    wrong = {}
    for label, (cmd, out) in cases.items():
        result = _run_post_bash(tmp_path, cmd, out)
        if result != "failed":
            wrong[label] = result
    assert not wrong, f"last_test_run.result sollte 'failed' sein: {wrong}"


def test_post_bash_only_skipped_recorded_skipped_mixed_passed(tmp_path):
    cases = {
        "pytest 0 passed, 5 skipped": (
            "pytest -q",
            "============================== 0 passed, 5 skipped in 0.31s ===============================\n",
            "skipped",
        ),
        "xcodebuild 5 tests skipped + TEST SUCCEEDED": (
            "xcodebuild test -scheme Demo-Package",
            "Executed 5 tests, with 5 tests skipped and 0 failures (0 unexpected) "
            "in 0.003 (0.004) seconds\n** TEST SUCCEEDED **\n",
            "skipped",
        ),
        "xcodebuild echt: 3 tests skipped + TEST SUCCEEDED": (
            "xcodebuild test -scheme Demo-Package",
            _fixture_bytes("xcodebuild_allskipped_raw.txt").decode("utf-8"),
            "skipped",
        ),
        "pytest 4 passed, 1 skipped": (
            "pytest -q",
            "========================= 4 passed, 1 skipped in 0.31s =========================\n",
            "passed",
        ),
    }
    wrong = {}
    for label, (cmd, out, expected) in cases.items():
        result = _run_post_bash(tmp_path, cmd, out)
        if result != expected:
            wrong[label] = (expected, result)
    assert not wrong, f"(erwartet, tatsächlich): {wrong}"


# --- AC-14: Report-Vorlagen + Skills synchron --------------------------------

_TEMPLATES = [
    "core/commands/60-validate.md",
    "core/commands/82-test.md",
    "core/agents/implementation-validator.md",
    "core/agents/test-runner.md",
]

# Ergebniszeilen der Vorlagen: „Tests: X passed …", „- Unit Tests: [N] passed …" usw.
_RESULT_LINE_RE = re.compile(
    r"^\s*-?\s*(?:Unit Tests|Integration Tests|Full Suite|Tests):.*\bpassed\b.*$",
    re.MULTILINE,
)
_RULE_RE = re.compile(r"0 bestanden.{0,80}übersprungen.{0,80}nicht grün", re.IGNORECASE | re.DOTALL)


def test_report_templates_have_skipped_field_and_skills_in_sync():
    problems = []
    for rel in _TEMPLATES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        lines = _RESULT_LINE_RE.findall(text)
        if not lines:
            problems.append(f"{rel}: keine Ergebniszeile gefunden")
        missing = [ln.strip() for ln in lines if "übersprungen" not in ln]
        if missing:
            problems.append(f"{rel}: Ergebniszeile(n) ohne Feld 'übersprungen': {missing}")
        if not _RULE_RE.search(text):
            problems.append(f"{rel}: Satz '0 bestanden + übersprungen ist nicht grün' fehlt")

    for skill in ("skills/60-validate/SKILL.md", "skills/82-test/SKILL.md"):
        if "übersprungen" not in (REPO_ROOT / skill).read_text(encoding="utf-8"):
            problems.append(f"{skill}: nicht regeneriert (kein 'übersprungen')")

    sync = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"), "--check"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if sync.returncode != 0:
        problems.append(f"sync_skills.py --check: {sync.stdout}{sync.stderr}")

    assert not problems, "\n".join(problems)


# --- AC-15: Executed ohne skipped unverändert -------------------------------

def test_executed_without_skipped_unchanged_green_and_red(tmp_path):
    green = (
        "Test Suite 'All tests' started at 2026-10-01 12:00:00.000.\n"
        "Executed 5 tests, with 0 failures (0 unexpected) in 0.2 (0.2) seconds\n"
    )
    ok, msg = _qa(tmp_path, green, "green.txt")
    assert ok is True, msg
    assert "5 tests" in msg, msg

    red = (
        "Test Suite 'All tests' started at 2026-10-01 12:00:00.000.\n"
        "Executed 5 tests, with 2 failures (2 unexpected) in 0.2 (0.2) seconds\n"
    )
    ok, msg = _qa(tmp_path, red, "red.txt")
    assert ok is False, msg
    assert "Tests FAILED" in msg and "2/5" in msg, msg


# --- Adversary F001: frühere rote Executed-Zeile wird nicht maskiert --------

def test_executed_earlier_red_line_not_masked_by_later_green(tmp_path):
    red_then_green = (
        "Test Suite 'SuiteA' started at 2026-10-01 12:00:00.000.\n"
        "Executed 5 tests, with 2 failures (2 unexpected) in 0.1 (0.1) seconds\n"
        "Test Suite 'SuiteB' started at 2026-10-01 12:00:00.100.\n"
        "Executed 3 tests, with 0 failures (0 unexpected) in 0.1 (0.1) seconds\n"
    )
    ok, msg = _qa(tmp_path, red_then_green, "red_green.txt")
    assert ok is False, msg
    assert "Tests FAILED" in msg and "2/5" in msg, msg

    ok, msg = _qa(tmp_path, red_then_green + "** TEST SUCCEEDED **\n", "red_green_ok.txt")
    assert ok is False, msg
    assert "Tests FAILED" in msg, msg

    green_then_red = (
        "Test Suite 'SuiteA' started at 2026-10-01 12:00:00.000.\n"
        "Executed 3 tests, with 0 failures (0 unexpected) in 0.1 (0.1) seconds\n"
        "Test Suite 'SuiteB' started at 2026-10-01 12:00:00.100.\n"
        "Executed 5 tests, with 2 failures (2 unexpected) in 0.1 (0.1) seconds\n"
        "** TEST SUCCEEDED **\n"
    )
    ok, msg = _qa(tmp_path, green_then_red, "green_red.txt")
    assert ok is False, msg
    assert "Tests FAILED" in msg and "2/5" in msg, msg


# --- Adversary F002: pytest-errors / 0 passed nie grün ----------------------

def _pytest_run(summary: str, errors_block: bool = True) -> str:
    head = (
        "============================= test session starts ==============================\n"
        "platform darwin -- Python 3.12.4, pytest-8.3.3, pluggy-1.5.0\n"
        "rootdir: /Users/dev/project\n"
        "collected 2 items / 1 error\n\n"
    )
    block = (
        "==================================== ERRORS ====================================\n"
        "_____________________ ERROR collecting tests/test_broken.py _____________________\n"
        "ImportError while importing test module 'tests/test_broken.py'.\n"
        "E   ModuleNotFoundError: No module named 'missing_dep'\n"
        "=========================== short test summary info ============================\n"
        "ERROR tests/test_broken.py\n"
    ) if errors_block else ""
    return head + block + summary + "\n"


def test_pytest_errors_or_zero_passed_never_green(tmp_path):
    cases = {
        "zero_passed_one_error": "========================= 0 passed, 1 error in 0.10s ==========================",
        "passed_skipped_error": "=================== 1 passed, 1 skipped, 1 error in 0.12s ====================",
        "passed_two_errors": "======================== 3 passed, 2 errors in 0.30s =========================",
    }
    for label, summary in cases.items():
        ok, msg = _qa(tmp_path, _pytest_run(summary), f"{label}.txt")
        assert ok is False, f"{label}: {msg}"
        assert "Tests FAILED" in msg, f"{label}: {msg}"

    # Reiner Sammelfehler ohne passed/failed-Wort: darf ebenfalls nie grün sein.
    lone = "=============================== 1 error in 0.10s ==============================="
    ok, msg = _qa(tmp_path, _pytest_run(lone), "one_error.txt")
    assert ok is False, f"1 error: {msg}"

    zero = "============================== 0 passed in 0.01s ==============================="
    ok, msg = _qa(tmp_path, _pytest_run(zero, errors_block=False), "zero.txt")
    assert ok is False, f"0 passed: {msg}"

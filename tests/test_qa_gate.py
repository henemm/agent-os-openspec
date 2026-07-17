import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
COPY_FILES = ["qa_gate.py", "workflow.py", "hook_utils.py",
              "config_loader.py", "override_token.py"]

# Direct, mock-free import of the module under test for the fine-grained
# pytest-summary parsing cases (Fix #71). validate_test_output() is pure
# read/evaluate logic, so it can be called directly with a tmp_path fixture.
sys.path.insert(0, str(HOOKS_DIR))
import qa_gate  # noqa: E402


def _setup_fake_project(tmp_path: Path, wf_name: str, skip_workflow_py: bool = False) -> Path:
    fake_hooks = tmp_path / "fake_hooks"
    fake_hooks.mkdir()
    for fname in COPY_FILES:
        if skip_workflow_py and fname == "workflow.py":
            continue
        shutil.copy(HOOKS_DIR / fname, fake_hooks / fname)
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{wf_name}.json").write_text(json.dumps({
        "name": wf_name, "current_phase": "phase6_implement",
        "adversary_verdict": None,
    }))
    return fake_hooks


def _run_qa_gate(fake_hooks: Path, tmp_path: Path, wf_name: str, output_file: Path):
    env = {"CLAUDE_PROJECT_DIR": str(tmp_path), "OPENSPEC_ACTIVE_WORKFLOW": wf_name,
           "PATH": "/usr/bin:/bin"}
    return subprocess.run(
        [sys.executable, str(fake_hooks / "qa_gate.py"), str(output_file)],
        capture_output=True, text=True, cwd=str(fake_hooks), env=env,
    )


def test_verdict_persisted_in_flat_consumer_layout(tmp_path):
    fake_hooks = _setup_fake_project(tmp_path, "wf1")
    output = tmp_path / "test-output.txt"
    output.write_text("test session starts\n5 passed in 1.2s\n" * 3)
    result = _run_qa_gate(fake_hooks, tmp_path, "wf1", output)
    assert result.returncode == 0
    state = json.loads((tmp_path / ".claude" / "workflows" / "wf1.json").read_text())
    assert state["adversary_verdict"] is not None
    assert state["adversary_verdict"].startswith("VERIFIED:")


def test_missing_workflow_py_fails_loudly(tmp_path):
    fake_hooks = _setup_fake_project(tmp_path, "wf2", skip_workflow_py=True)
    output = tmp_path / "test-output.txt"
    output.write_text("test session starts\n5 passed in 1.2s\n" * 3)
    result = _run_qa_gate(fake_hooks, tmp_path, "wf2", output)
    assert result.returncode != 0
    assert "Commit is now allowed." not in result.stdout

# ---------------------------------------------------------------------------
# Fix #71: qa_gate wertet die pytest-Erfolgsmeldung `0 failed` als Fehlschlag.
# Die folgenden Faelle binden die Erkennung an die echte pytest-Summary-Zeile
# und pruefen die Fehleranzahl korrekt auf `> 0`.
# ---------------------------------------------------------------------------


def _write_output(tmp_path: Path, content: str) -> Path:
    """Schreibt eine Test-Ausgabe-Datei; padded auf die 100-Byte-Mindestgroesse
    von validate_test_output() ohne weitere passed/failed-Zaehlungen."""
    out = tmp_path / "test-output.txt"
    if len(content) < 120:
        content = content + "\n" + ("-" * 120) + "\n"
    out.write_text(content)
    return out


def test_ac1_zero_failed_summary_is_success(tmp_path):
    """AC-1: '754 passed, 0 failed, 3 skipped' ist eine gruene Suite -> PASSED,
    keine widerspruechliche 'Tests FAILED: 0 failed'-Meldung mehr."""
    out = _write_output(
        tmp_path,
        "test session starts\n754 passed, 0 failed, 3 skipped in 12.34s\n",
    )
    valid, message = qa_gate.validate_test_output(str(out))
    assert valid is True, message
    assert "FAILED" not in message


def test_ac1_zero_failed_summary_framed_is_success(tmp_path):
    """AC-1 (=-Rahmen-Variante): umrahmte Summary mit 0 failed -> PASSED."""
    out = _write_output(
        tmp_path,
        "test session starts\n"
        "============ 754 passed, 0 failed in 12.34s =============\n",
    )
    valid, message = qa_gate.validate_test_output(str(out))
    assert valid is True, message
    assert "FAILED" not in message


def test_ac2_nonzero_failed_summary_blocks(tmp_path):
    """AC-2 (Regressionsschutz): '2 failed, 750 passed' blockt weiterhin."""
    out = _write_output(
        tmp_path,
        "test session starts\n2 failed, 750 passed in 12.34s\n",
    )
    valid, message = qa_gate.validate_test_output(str(out))
    assert valid is False
    assert message == "Tests FAILED: 2 failed"


def test_ac3_quoted_failed_outside_summary_does_not_block(tmp_path):
    """AC-3: eine zitierte 'N failed'-Zeile ausserhalb der echten Summary darf
    ein gruenes Verdict ('5 passed, 0 failed') nicht in Richtung Fehlschlag
    kippen."""
    out = _write_output(
        tmp_path,
        "test session starts\n"
        "Der Fix behebt 3 failed aus dem letzten Lauf\n"
        "5 passed, 0 failed in 1.1s\n",
    )
    valid, message = qa_gate.validate_test_output(str(out))
    assert valid is True, message


def test_ac4_quoted_passed_without_real_summary_is_not_pass(tmp_path):
    """AC-4: 'N passed' nur als Prosa-Zitat, KEINE echte pytest-Summary-Zeile
    -> darf nicht als PASSED gewertet werden (Fallback statt False-Pass)."""
    out = _write_output(
        tmp_path,
        "test session starts\nFremdes Tool meldete 10 passed irgendwo\n",
    )
    valid, message = qa_gate.validate_test_output(str(out))
    assert valid is False, message


def test_ac5_executed_zero_failures_still_passes(tmp_path):
    """AC-5 (Regressionsschutz): node/Go-TAP 'Executed N tests, with 0 failures'
    bleibt bestanden - der Zweig ist nicht Teil dieses Fixes."""
    out = _write_output(
        tmp_path,
        "Test Suite started\nExecuted 12 tests, with 0 failures\n",
    )
    valid, message = qa_gate.validate_test_output(str(out))
    assert valid is True, message


def test_ac5_executed_nonzero_failures_still_blocks(tmp_path):
    """AC-5 (Regressionsschutz): 'Executed N tests, with 2 failures' blockt
    weiterhin - unveraendertes Bestandsverhalten."""
    out = _write_output(
        tmp_path,
        "Test Suite started\nExecuted 12 tests, with 2 failures\n",
    )
    valid, message = qa_gate.validate_test_output(str(out))
    assert valid is False, message


# ---------------------------------------------------------------------------
# Fix-Loop 1 (F001): Playwright-Summary-Format `N passed (X.Ys)` (Klammer-Dauer)
# muss wieder als echte Summary-Zeile erkannt werden. Die AC-4-Grenze (Prosa
# ohne echte Summary zaehlt nicht) bleibt unveraendert bestehen.
# ---------------------------------------------------------------------------


def test_f001_playwright_paren_duration_green_is_pass(tmp_path):
    """F001: Playwright meldet gruen als '  2 passed (12.0s)' (Klammer-Dauer
    statt 'in X.Ys'). Diese echte, real genutzte Summary-Zeile muss als
    PASSED erkannt werden."""
    out = _write_output(
        tmp_path,
        "Running 2 tests using 1 worker\n"
        "  2 passed (12.0s)\n",
    )
    valid, message = qa_gate.validate_test_output(str(out))
    assert valid is True, message
    assert "FAILED" not in message


def test_f001_playwright_paren_duration_red_blocks(tmp_path):
    """F001-Regressionsschutz: eine rote Playwright-Summary '  1 failed (8.2s)'
    als LETZTE matchende Zeile muss blocken, auch wenn davor eine gruene
    Klammer-Dauer-Zeile steht."""
    out = _write_output(
        tmp_path,
        "Running tests using 1 worker\n"
        "  2 passed (12.0s)\n"
        "  1 failed (8.2s)\n",
    )
    valid, message = qa_gate.validate_test_output(str(out))
    assert valid is False, message
    assert message == "Tests FAILED: 1 failed"


def test_f001_ac4_guard_paren_without_duration_is_not_pass(tmp_path):
    """AC-4-Waechter (haelt nach dem Fix): Prosa mit Klammer OHNE echte Dauer
    ('Der Bericht sagt 5 passed (siehe oben)') ist KEINE echte Summary-Zeile
    und darf nicht als PASSED gewertet werden."""
    out = _write_output(
        tmp_path,
        "test session starts\n"
        "Der Bericht sagt 5 passed (siehe oben)\n",
    )
    valid, message = qa_gate.validate_test_output(str(out))
    assert valid is False, message


def test_f001_real_playwright_artifact_is_pass(tmp_path):
    """F001-Realdaten: das historisch akzeptierte GREEN-Artefakt
    issue_273_green_output.txt (Playwright, ANSI-Codes + '  2 passed (12.0s)')
    muss als PASSED erkannt werden."""
    src = Path("/home/hem/gregor_zwanzig/docs/artifacts/issue_273_green_output.txt")
    dst = tmp_path / "issue_273_green_output.txt"
    shutil.copy(src, dst)  # copy() setzt mtime=jetzt -> Frische-Check ok
    valid, message = qa_gate.validate_test_output(str(dst))
    assert valid is True, message
    assert "FAILED" not in message

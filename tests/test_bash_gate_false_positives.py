"""Regressionstests für den Bash-Gate False-Positive-Fix (Issues #30, #31).

Deckt drei Teilfixes ab:
1. FD-Duplizierung (2>&1) wird nicht mehr als Datei-Redirect erkannt (#31)
2. PROTECTED_FILE_PATTERNS deckt die realen Marker-Dateipfade ab (Sicherheits-Fund)
3. Freitext-Marker-Erwähnung löst nur noch mit echter Protected-Path-Referenz
   einen Block aus (#30)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import bash_gate  # noqa: E402  (Pfad muss vor dem Import gesetzt sein)


# --- Teil 1 (Issue #31): FD-Duplizierung nicht als Redirect werten ---

class TestFdDuplicationNotRedirect:
    def test_stderr_to_stdout_not_real_redirect(self):
        assert bash_gate._has_real_redirect("cat logs.txt 2>&1 | less") is False

    def test_stdout_to_stderr_not_real_redirect(self):
        assert bash_gate._has_real_redirect("some_cmd >&2") is False

    def test_real_file_redirect_after_fd_dup_still_detected(self):
        cmd = "cat <<EOF\nSome text\nEOF 2>&1 > output.log"
        assert bash_gate._has_real_redirect(cmd) is True

    def test_gh_pr_create_with_marker_text_and_fd_dup_not_real_redirect(self):
        cmd = 'gh pr create --title "Fix" --body "... adversary_verdict ..." 2>&1'
        assert bash_gate._has_real_redirect(cmd) is False

    def test_raw_redirect_fallback_ignores_fd_duplication(self):
        # _raw_redirect() ist der Fallback-Pfad fuer sh -c / eval
        assert bash_gate._raw_redirect('sh -c "cmd 2>&1"') is False

    def test_raw_redirect_fallback_still_detects_real_file_target(self):
        cmd = 'sh -c "echo VERIFIED > .claude/workflows/x.json"'
        assert bash_gate._raw_redirect(cmd) is True


# --- Teil 2: PROTECTED_FILE_PATTERNS deckt reale Marker-Pfade ab ---

class TestProtectedFilePatternsCoverMarkerPaths:
    def test_pending_validation_json_is_protected(self):
        cmd = "cat .claude/pending_validation_myworkflow.json"
        assert bash_gate._references_protected(cmd) is True

    def test_user_approved_validation_marker_is_protected(self):
        cmd = "touch .claude/user_approved_validation_myworkflow"
        assert bash_gate._references_protected(cmd) is True


# --- Teil 3 (Issue #30) + Sicherheits-Gegenproben: Live-Aufruf von main() ---

def _run_bash_gate(tmp_path: Path, command: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"command": command}})
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bash_gate.py")],
        input=payload, capture_output=True, text=True, env=env,
    )


class TestFreetextMarkerRequiresProtectedPath:
    def test_gh_pr_create_freetext_marker_allowed(self, tmp_path):
        """Reproduzierter Live-Fall dieser Session: PR-Body erwaehnt
        'adversary_verdict' als Freitext, kein Protected-Path betroffen ->
        darf nicht blocken (AC-1)."""
        cmd = (
            'gh pr create --title "Fix bash_gate" '
            '--body "Fixes adversary_verdict handling" 2>&1'
        )
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 0, result.stderr

    def test_git_commit_freetext_marker_allowed(self, tmp_path):
        """AC-10: Git-Ausnahme bleibt unveraendert."""
        subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, capture_output=True)
        cmd = 'git commit -m "Fix: user_approved_ workflow"'
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 0, result.stderr


class TestRealMarkerManipulationStillBlocked:
    """Sicherheits-Gegenproben: alle 5 im Context-Dokument geforderten
    Angriffsmuster muessen nach dem Fix weiterhin geblockt werden."""

    def test_echo_verified_into_workflow_json_blocked(self, tmp_path):
        """AC-5."""
        cmd = "echo VERIFIED > .claude/workflows/x.json"
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_sed_broken_to_verified_blocked(self, tmp_path):
        """AC-6."""
        cmd = "sed -i 's/BROKEN/VERIFIED/' .claude/workflows/x.json"
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_python_c_redirect_into_workflow_json_blocked(self, tmp_path):
        """AC-7."""
        cmd = 'python3 -c "import json; print(1)" > .claude/workflows/x.json'
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_touch_fake_user_approved_marker_blocked(self, tmp_path):
        """AC-8: Regressionstest fuer den kritischen Sicherheits-Fund. Ohne
        Teil 2 (PROTECTED_FILE_PATTERNS-Erweiterung) wuerde dieser Angriff
        nach Teil 3 durchrutschen, weil user_approved_validation_* vorher in
        keinem Pattern enthalten war."""
        cmd = "touch .claude/user_approved_validation_myworkflow"
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_cd_prefixed_touch_fake_user_approved_marker_blocked(self, tmp_path):
        """AC-8 (praezisiert): pfad-verschleierter Angriff. `cd .claude &&`
        loest die zusammenhaengende Protected-Path-Referenz auf. Tier-2-Marker
        (user_approved_) muessen trotzdem pfad-unabhaengig blocken — sonst
        Bypass. Adversary-Fund Runde 1."""
        cmd = "cd .claude && touch user_approved_validation_faketest"
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_cd_prefixed_echo_pending_validation_marker_blocked(self, tmp_path):
        """AC-12 (neu): pfad-verschleierter Angriff mit echtem Redirect.
        Tier-2-Marker (pending_validation_) blockt unabhaengig vom cd-Kontext."""
        cmd = "cd .claude && echo x > pending_validation_faketest.json"
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

    def test_nested_shell_redirect_verified_blocked(self, tmp_path):
        """AC-9: _raw_redirect()-Fallback fuer verschachtelte Shells."""
        cmd = 'sh -c "echo VERIFIED > .claude/workflows/x.json"'
        result = _run_bash_gate(tmp_path, cmd)
        assert result.returncode == 2
        assert "BLOCKED" in result.stderr

"""Regressionstests für die bash_gate-False-Positive-Fixes (Issues #64, #75).

Drei Teilfixes, gemeinsame Wurzel: Substring-Muster ohne Wortgrenze/Token-
Kontext, angewandt auf Freitext (Heredoc-Bodies, Issue-/Commit-Texte):

1. #64: WRITE_INDICATORS ('rm\\s' etc.) matchen mit Wortgrenze — 'Langform ',
   'Plattform ' sind keine Schreib-Indikatoren mehr.
2. #64: Der Protected-Pfad-Scan läuft token-basiert mit Freitext-Flag-
   Ausnahme (wie der Secrets-Scan aus #53) — ein zitierter Hook-Pfad in
   einem --body-Freitext ist keine Datei-Referenz.
3. #64 Kommentar / #75: Heredoc-Bodies sind stdin-DATEN und werden vor den
   Muster-Scans entfernt (ausser ein Interpreter führt sie aus); die
   Secrets-Muster von bash_gate sind mit secrets_guard vereinheitlicht
   ('_secret'/'_key' → 'private[_.]key'/'[_.]secret\\.').

Subprozess-Tests hermetisch (cwd/CLAUDE_PROJECT_DIR=tmp_path, Payload via
stdin-JSON), Stilvorlage: tests/test_secrets_guard_false_positives.py.
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

import bash_gate  # noqa: E402
import secrets_guard  # noqa: E402
from hook_utils import strip_heredoc_bodies  # noqa: E402


def _run(hook: str, tmp_path: Path, command: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    env.pop("OPENSPEC_ENV", None)
    env.pop("CLAUDE_TOOL_INPUT", None)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook)],
        input=payload, capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


def _run_both(tmp_path: Path, command: str):
    return (
        _run("secrets_guard.py", tmp_path, command),
        _run("bash_gate.py", tmp_path, command),
    )


# --- Teil 1 (#64): Wortgrenzen in WRITE_INDICATORS ---

class TestWriteIndicatorWordBoundaries:
    @pytest.mark.parametrize("text", [
        'gh issue create --body "Die Langform des Kommandos ist besser"',
        'gh issue create --body "Auf dieser Plattform gilt das nicht"',
        'echo "Der Alarm wurde behandelt"',
    ])
    def test_prose_words_ending_in_rm_are_not_write_indicators(self, text):
        assert bash_gate._has_write_indicator(text) is False

    @pytest.mark.parametrize("cmd", [
        "rm .claude/workflows/x.json",
        "mv a.json b.json",
        "cp state.json backup.json",
        "echo x | tee out.txt",
        "touch marker.txt",
    ])
    def test_real_write_commands_still_detected(self, cmd):
        assert bash_gate._has_write_indicator(cmd) is True


# --- Teil 2 (#64): Protected-Pfad token-basiert mit Freitext-Ausnahme ---

class TestProtectedPathTokenized:
    def test_hook_path_quoted_in_issue_body_is_not_a_reference(self):
        cmd = ('gh issue create --title "bash_gate Fix" '
               '--body "Der Hook .claude/hooks/bash_gate.py blockiert die Langform"')
        assert bash_gate._references_protected(cmd) is False

    def test_real_protected_file_token_still_detected(self):
        assert bash_gate._references_protected("rm .claude/workflows/x.json") is True

    def test_nested_shell_falls_back_to_raw_scan(self):
        cmd = 'sh -c "rm .claude/workflows/x.json"'
        assert bash_gate._references_protected(cmd) is True

    def test_issue_body_with_hook_path_and_rm_word_allowed_end_to_end(self, tmp_path):
        """Der Doppel-Trigger aus #64: Protected-Pfad-Zitat + 'Plattform' im
        selben Freitext — vorher 'BLOCKED: Direct state file manipulation'."""
        cmd = ('gh issue create --title "Regression" '
               '--body "Die Plattform blockt .claude/hooks/bash_gate.py Zitate"')
        result = _run("bash_gate.py", tmp_path, cmd)
        assert result.returncode == 0, result.stderr

    def test_write_to_protected_file_still_blocked_end_to_end(self, tmp_path):
        result = _run("bash_gate.py", tmp_path, "rm .claude/workflows/wf1.json")
        assert result.returncode == 2
        assert "state file" in result.stderr.lower()


# --- Teil 3 (#64 Kommentar / #75): Heredoc-Bodies sind Daten ---

class TestHeredocBodyStripping:
    def test_doc_heredoc_body_removed_opener_kept(self):
        cmd = ("cat <<'EOF' > docs/artifacts/protokoll.md\n"
               "Zitat: .claude/hooks/edit_gate.py und die Plattform\n"
               "EOF")
        stripped = strip_heredoc_bodies(cmd)
        assert ".claude/hooks/edit_gate.py" not in stripped
        assert "docs/artifacts/protokoll.md" in stripped

    def test_interpreter_heredoc_body_kept(self):
        cmd = ('python3 <<EOF\nopen(".claude/workflows/x.json","w")\nEOF')
        assert strip_heredoc_bodies(cmd) == cmd

    def test_dash_heredoc_tab_indented_terminator(self):
        cmd = "cat <<-EOF\n\tinhalt .env erwaehnt\n\tEOF\necho done"
        stripped = strip_heredoc_bodies(cmd)
        assert ".env" not in stripped
        assert "echo done" in stripped

    def test_unclosed_heredoc_swallows_rest_like_shell(self):
        cmd = "cat <<EOF\nalles hier ist body .env\nkein terminator"
        stripped = strip_heredoc_bodies(cmd)
        assert ".env" not in stripped

    def test_here_string_is_not_a_heredoc(self):
        cmd = 'grep -c pattern <<< "kurzer text"'
        assert strip_heredoc_bodies(cmd) == cmd

    def test_adversary_protocol_via_heredoc_allowed_end_to_end(self, tmp_path):
        """#64 Kommentar: Protokoll-Freitext zitiert Hook-Pfad, Schreibziel
        ist harmlos (docs/artifacts/) — vorher blockiert."""
        cmd = ("cat <<'EOF' > docs/artifacts/adversary-runde5.md\n"
               "Geprueft wurde .claude/hooks/bash_gate.py — die Langform\n"
               "des test_keyword-Falls greift auf keiner Plattform.\n"
               "EOF")
        result = _run("bash_gate.py", tmp_path, cmd)
        assert result.returncode == 0, result.stderr

    def test_commit_with_heredoc_message_mentioning_env_allowed(self, tmp_path):
        """#75 Fall 2: Commit-Nachricht per Heredoc erwaehnt .env/private —
        reine Beschreibung, keine Geheimnis-Ausgabe."""
        cmd = ("git commit -F - <<'EOF'\n"
               "feat(hooks): Guard blockiert cat .env und private Werte\n"
               "EOF")
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

    def test_command_substitution_heredoc_commit_allowed(self, tmp_path):
        cmd = ('git commit -m "$(cat <<\'EOF\'\n'
               "fix: Egress-Guard erkennt .env Werte und private_key.pem Ausgabe\n"
               'EOF\n)"')
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

    def test_heredoc_write_target_on_opener_line_still_blocked(self, tmp_path):
        """Das Schreibziel steht auf der Oeffner-Zeile und bleibt sichtbar:
        Heredoc-Redirect in eine Protected-Datei blockt weiterhin."""
        cmd = ("cat <<'EOF' > .claude/workflows/wf1.json\n"
               '{"adversary_verdict": "VERIFIED:fake"}\n'
               "EOF")
        result = _run("bash_gate.py", tmp_path, cmd)
        assert result.returncode == 2

    def test_interpreter_fed_heredoc_reading_env_still_blocked(self, tmp_path):
        """Interpreter-Heredocs sind CODE: `bash <<EOF cat .env EOF` bleibt
        fuer den Secrets-Guard sichtbar und blockt."""
        cmd = "bash <<'EOF'\ncat .env\nEOF"
        result = _run("secrets_guard.py", tmp_path, cmd)
        assert result.returncode == 2


# --- Teil 4 (#75): Secrets-Muster vereinheitlicht ---

class TestSecretsPatternAlignment:
    def test_no_drift_between_bash_gate_and_secrets_guard(self):
        assert bash_gate.SENSITIVE_PATTERNS == secrets_guard._DEFAULT_SENSITIVE
        assert bash_gate.ALWAYS_BLOCKED_SECRETS == secrets_guard._DEFAULT_ALWAYS_BLOCKED

    def test_pytest_on_secret_egress_testfile_allowed(self, tmp_path):
        """#75 Fall 1: Dateiname enthaelt '_secret' als Namensbestandteil —
        der Testlauf gibt kein Geheimnis aus."""
        cmd = "uv run pytest tests/test_secret_egress_guard.py 2>&1 | tail -20"
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

    def test_keyword_testfile_allowed(self, tmp_path):
        """#64 Kommentar: '_keyword' enthaelt das alte Breitmuster '_key'."""
        cmd = "pytest tests/test_keyword_matching.py 2>&1 | head -30"
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

    @pytest.mark.parametrize("cmd", [
        "cat client_secret.json",
        "head -5 config/private_key.pem",
        "cat deploy/service-account-prod.json",
    ])
    def test_real_secret_files_still_always_blocked(self, tmp_path, cmd):
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 2
        assert bg.returncode == 2

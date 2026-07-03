"""Regressionstests fuer den Secrets-Guard False-Positive-Fix (Issue #53).

Ursache: `secrets_guard.py` UND der Secrets-Check in `bash_gate.py` scannten den
ROHEN Befehlsstring mit unverankerten Regexen. Lange Befehle mit Freitext
(Commit-Messages, PR-/Issue-Bodies, grep-Muster) triggerten False-Positives,
obwohl keine sensible Datei beruehrt wird.

Fix: Sensitive-Datei-Patterns matchen nur noch gegen echte DATEI-Token
(shlex-Tokenisierung; Freitext-Argumente von -m/--body/--title/-F ausgenommen).
Konservativer Fallback auf Roh-Scan bei verschachtelter Shell / Parse-Fehler.

Tests laufen hermetisch: Subprozess mit cwd/CLAUDE_PROJECT_DIR=tmp_path,
Payload via stdin-JSON (Stilvorlage: tests/test_bash_gate_false_positives.py).
Beide Guards werden jeweils geprueft, damit kein Guard-Drift entsteht.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"


def _run(hook: str, tmp_path: Path, command: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    env.pop("OPENSPEC_ENV", None)  # kein Staging-Bypass
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / hook)],
        input=payload, capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )


def _run_both(tmp_path: Path, command: str):
    return (
        _run("secrets_guard.py", tmp_path, command),
        _run("bash_gate.py", tmp_path, command),
    )


# --- Die 3 Realfall-Befehle aus der Spec: duerfen NICHT mehr blocken ---

class TestRealWorldFalsePositivesAllowed:
    def test_commit_and_pr_create_with_sensitive_words_in_freetext(self, tmp_path):
        """#53 Fall 1: Commit-Message + PR-Body erwaehnen .env/credentials.json
        als Fliesstext. Keine sensible Datei wird beruehrt -> kein Block."""
        cmd = (
            'git add core/hooks/bash_gate.py && '
            'git commit -m "fix: guard blocks cat .env in commit body" && '
            'gh pr create --body "Previously running cat .env or head '
            'credentials.json in a demo blocked the whole command"'
        )
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

    def test_grep_for_secret_terms_in_source_allowed(self, tmp_path):
        """#53 Fall 2: grep nach Secret-bezogenen Begriffen in einer Quelldatei.
        Das einzige Datei-Token (core/hooks/bash_gate.py) ist nicht sensibel."""
        cmd = (
            r'grep -n "SECRET\|def _check_secrets\|secrets_guard\|SENSITIVE" '
            r'core/hooks/bash_gate.py'
        )
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

    def test_grep_freetext_pattern_with_env_word_behind_flag_allowed(self, tmp_path):
        """#53 Fall 2 (Variante): sensible Woerter stehen NUR im Freitext,
        das Datei-Token bleibt harmlos -> kein Block in beiden Guards."""
        cmd = 'gh issue create --title ".env false positive" --body "cat .env and head credentials.json get blocked"'
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

    def test_gh_issue_create_freetext_body_allowed(self, tmp_path):
        """#53 Fall 3: Issue-Body beschreibt den Bug (nennt .env/credentials.json/
        .pem/.key) -> reiner Freitext, kein Datei-Zugriff -> kein Block."""
        cmd = (
            'gh issue create --body "secrets_guard blocks cat .env in free text; '
            'head credentials.json and the .pem/.key patterns also false-positive"'
        )
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr


# --- Sicherheits-Invarianten: Block MUSS bleiben (je Gegenprobe) ---

class TestSecurityInvariantsStillBlocked:
    def test_cat_env_blocked(self, tmp_path):
        sg, bg = _run_both(tmp_path, "cat .env")
        assert sg.returncode == 2, sg.stdout + sg.stderr
        assert bg.returncode == 2, bg.stdout + bg.stderr

    def test_head_credentials_json_blocked(self, tmp_path):
        sg, bg = _run_both(tmp_path, "head credentials.json")
        assert sg.returncode == 2
        assert bg.returncode == 2

    def test_grep_private_key_file_blocked(self, tmp_path):
        """grep liest eine private.key-DATEI (echtes Datei-Token) -> Block.
        In bash_gate ist grep kein Content-Output-Command; secrets_guard blockt.
        Mindestens ein Guard MUSS diesen Lesezugriff verhindern."""
        sg, bg = _run_both(tmp_path, "grep x private.key")
        assert sg.returncode == 2, sg.stdout + sg.stderr

    def test_quoted_path_with_spaces_env_blocked(self, tmp_path):
        """Quoted Pfad mit Leerzeichen -> shlex haelt ihn als EIN Datei-Token
        zusammen; .env matcht -> Block bleibt."""
        cmd = 'cat "datei mit leerzeichen/.env"'
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 2, sg.stdout + sg.stderr
        assert bg.returncode == 2, bg.stdout + bg.stderr

    def test_nested_shell_cat_env_conservative_fallback_blocks(self, tmp_path):
        """`bash -c "cat .env"`: verschachtelte Shell -> konservativer Roh-Scan
        blockt (kein Bypass durch quoted Code)."""
        cmd = 'bash -c "cat .env"'
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 2, sg.stdout + sg.stderr
        assert bg.returncode == 2, bg.stdout + bg.stderr

    def test_broken_quotes_shlex_fallback_blocks(self, tmp_path):
        """Nicht-parsebarer Befehl (kaputte Quotes) + .env -> shlex.ValueError
        -> konservativer Roh-Scan-Fallback blockt weiterhin."""
        cmd = 'cat .env" && echo done'
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 2, sg.stdout + sg.stderr
        assert bg.returncode == 2, bg.stdout + bg.stderr

    def test_grep_dash_l_exception_preserved(self, tmp_path):
        """`grep -l` zeigt nur Dateipfade ohne Inhalt -> secrets_guard-Ausnahme
        bleibt erhalten (kein Block), auch bei sensiblem Datei-Token."""
        sg = _run("secrets_guard.py", tmp_path, "grep -l secret .env")
        assert sg.returncode == 0, sg.stderr


# --- Fixtures/Feinheiten: Freitext hinter allen relevanten Flags ---

class TestFreetextFlagsExcluded:
    @pytest.mark.parametrize("flag", ["-m", "--message", "--body", "--title", "-F"])
    def test_sensitive_word_behind_freetext_flag_allowed(self, tmp_path, flag):
        cmd = f'somecmd {flag} "please cat .env now"'
        sg, bg = _run_both(tmp_path, cmd)
        assert sg.returncode == 0, sg.stderr
        assert bg.returncode == 0, bg.stderr

"""Issue #276: Guards schlagen an, wo nichts geschrieben wird (fasst #269, #256③).

1. secret_egress_guard: ein '>' im Heredoc-KOERPER ist zitierter Text, kein Ziel.
2. Wiedereinstieg: die Befehle nutzen `workflow.py find` statt eines Python-Schnipsels,
   den bash_gate als Marker-Manipulation blockte.
Die Gegenproben (echte Schreibvorgaenge bleiben blockiert) sind der eigentliche
Nachweis.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))



def _clean_env(project: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME", "OPENSPEC_FRAMEWORK")}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    return env


def _egress(project: Path, command: str) -> subprocess.CompletedProcess:
    env = _clean_env(project)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "secret_egress_guard.py")],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True, text=True, env=env, cwd=str(project),
    )


@pytest.fixture
def project(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    wf = tmp_path / ".claude" / "workflows"
    wf.mkdir(parents=True)
    (wf / "fix-42-x.json").write_text(json.dumps(
        {"name": "fix-42-x", "current_phase": "phase6_implement"}))
    return tmp_path


def _gate(project: Path, command: str) -> subprocess.CompletedProcess:
    env = _clean_env(project)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = "fix-42-x"
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bash_gate.py")],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True, text=True, env=env, cwd=str(project),
    )


# --- 1. Heredoc-Koerper im Egress-Guard (#269) ---

class TestEgressHeredocBody:
    def test_case_d_quoted_redirect_in_body_allowed(self, project):
        cmd = "cat > notizen.md <<'MD'\nBeispiel: echo hallo > /etc/boese.txt\nMD"
        r = _egress(project, cmd)
        assert r.returncode == 0, r.stderr

    def test_real_redirect_on_opener_line_still_blocked(self, project):
        cmd = "cat > /etc/boese.txt <<'MD'\nnur text\nMD"
        r = _egress(project, cmd)
        assert r.returncode == 2 and "/etc/boese.txt" in r.stderr, r.stderr

    def test_redirect_in_shell_interpreter_body_still_blocked(self, project):
        """Koerper hinter bash/sh ist Code, nicht Daten — bleibt im Scan."""
        cmd = "bash <<'SH'\necho x > /etc/boese.txt\nSH"
        r = _egress(project, cmd)
        assert r.returncode == 2, r.stderr

    def test_plain_redirect_unchanged(self, project):
        assert _egress(project, "echo hallo > notizen.md").returncode == 0
        assert _egress(project, "echo hallo > /etc/boese.txt").returncode == 2


# --- 2. Wiedereinstieg ohne Python-Schnipsel (#256③) ---
#
# Statt eine Python-Lese-Erkennung ins Sicherheits-Gate zu bauen, nutzen die
# Befehle den lesenden CLI-Aufruf `workflow.py find` — die Gate-Logik bleibt
# unveraendert streng (`python3 -c` zaehlt weiter pauschal als schreibend).

COMMANDS_DIR = REPO_ROOT / "core" / "commands"
FIND_RE = re.compile(r"python3 \.claude/hooks/workflow\.py find 42")


def _commands_with_reentry():
    return sorted(p for p in COMMANDS_DIR.glob("*.md") if FIND_RE.search(p.read_text()))


def test_no_command_uses_python_snippet_for_reentry():
    """/90-retro sucht bewusst im ARCHIV (eigener Fall, nicht Teil von #276)."""
    paths = list(COMMANDS_DIR.glob("*.md")) + list((REPO_ROOT / "skills").glob("*/SKILL.md"))
    for p in paths:
        if "90-retro" in str(p):
            continue
        assert "glob.glob('.claude/workflows" not in p.read_text(), p


def test_step0_of_50_implement_uses_find():
    assert FIND_RE.search((COMMANDS_DIR / "50-implement.md").read_text())
    assert len(_commands_with_reentry()) >= 12


def test_find_command_passes_gate(project):
    r = _gate(project, "python3 .claude/hooks/workflow.py find 42")
    assert r.returncode == 0, r.stderr


def test_find_resolves_workflow(project):
    env = _clean_env(project)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = ""
    r = subprocess.run([sys.executable, str(HOOKS_DIR / "workflow.py"), "find", "#42"],
                       capture_output=True, text=True, env=env, cwd=str(project))
    assert r.returncode == 0, r.stderr
    assert "GEFUNDEN: fix-42-x | Phase=phase6_implement" in r.stdout
    assert r.stdout.rstrip().endswith("NAME=fix-42-x")
    r2 = subprocess.run([sys.executable, str(HOOKS_DIR / "workflow.py"), "find", "4"],
                        capture_output=True, text=True, env=env, cwd=str(project))
    assert "KEIN laufender Workflow" in r2.stdout


@pytest.mark.parametrize("cmd", [
    "python3 -c \"open('.claude/user_approved_x','w').write('1')\"",
    "python3 -c \"import pathlib; pathlib.Path('.claude/user_approved_x').touch()\"",
    "cd .claude && touch user_approved_x",
    "touch .claude/user_approved_x",
    "python3 - <<'PY'\nopen('.claude/user_approved_x', 'w').write('1')\nPY",
])
def test_marker_writes_stay_blocked(project, cmd):
    r = _gate(project, cmd)
    assert r.returncode == 2 and "Marker" in r.stderr, (cmd, r.stderr)

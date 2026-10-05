"""Issue #276: Guards schlagen an, wo nichts geschrieben wird (fasst #269, #256③).

1. secret_egress_guard: ein '>' im Heredoc-KOERPER ist zitierter Text, kein Ziel.
2. bash_gate: ein nachweislich lesender Python-Schnipsel ist kein Schreibvorgang —
   der Wiedereinstiegs-Schritt aus /50-implement Step 0 laeuft durch.
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

import bash_gate  # noqa: E402


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


# --- 2. Lesende Kommandos im bash_gate (#256③) ---

def _step0_command() -> str:
    md = (REPO_ROOT / "core" / "commands" / "50-implement.md").read_text()
    m = re.search(r"```bash\n(ISSUE=42.*?)```", md, re.S)
    assert m, "Step-0-Block in 50-implement.md nicht gefunden"
    return m.group(1)


class TestBashGateReadOnlyPython:
    def test_documented_step0_command_passes(self, project):
        r = _gate(project, _step0_command())
        assert r.returncode == 0, r.stderr

    def test_readonly_python_c_listing_workflows_passes(self, project):
        cmd = ("python3 -c \"import glob,json; "
               "[print(json.load(open(f)).get('adversary_verdict')) "
               "for f in glob.glob('.claude/workflows/*.json')]\"")
        r = _gate(project, cmd)
        assert r.returncode == 0, r.stderr

    @pytest.mark.parametrize("cmd", [
        "python3 -c \"open('.claude/user_approved_x','w').write('1')\"",
        "python3 -c \"import pathlib; pathlib.Path('.claude/user_approved_x').touch()\"",
        "python3 -c \"import os; os.remove('.claude/user_approved_x')\"",
        "cd .claude && touch user_approved_x",
        "cd .claude && python3 -c \"open('user_approved_x','w')\"",
        "touch .claude/user_approved_x",
        "python3 - <<'PY'\nopen('.claude/user_approved_x', 'w').write('1')\nPY",
        # ungequotetes Endwort: die Shell expandiert den Koerper -> nicht entlastet
        "python3 - <<PY\nprint('$(touch .claude/user_approved_x)')\nPY",
        "python3 -c \"getattr(__builtins__, 'op'+'en')('.claude/user_approved_x', 'w')\"",
    ])
    def test_marker_writes_stay_blocked(self, project, cmd):
        r = _gate(project, cmd)
        assert r.returncode == 2 and "Marker" in r.stderr, (cmd, r.stderr)

    @pytest.mark.parametrize("cmd", [
        "python3 -c \"import json; json.dump({}, open('.claude/workflows/fix-42-x.json', 'w'))\"",
        "python3 -c \"import shutil; shutil.copy('a', '.claude/workflows/fix-42-x.json')\"",
        "python3 -c \"import glob; print(glob.glob('.claude/workflows/*.json'))\" "
        "> .claude/workflows/fix-42-x.json",
    ])
    def test_state_writes_stay_blocked(self, project, cmd):
        r = _gate(project, cmd)
        assert r.returncode == 2, (cmd, r.stderr)


class TestReadonlyClassifier:
    @pytest.mark.parametrize("code", [
        "open('m', 'w')", "open('m', mode='a')", "open('m', 'r+')",
        "o = open; o('m', 'w')", "x = [open][0]",
        "import shutil", "import subprocess", "import io", "from os import *",
        "from os import remove", "import os; f = os.remove; f('x')",
        "import os; os.replace('a', 'b')", "import os; m = os; m.replace('a', 'b')",
        "from pathlib import Path; Path('a').replace('b')",
        "from pathlib import Path; Path('a').open('w')",
        "from pathlib import Path; Path('a').write_text('x')",
        "import os; os.__dict__", "import sys; sys.modules['os']",
        "exec('1')", "eval('1')", "__import__('os')",
        "import os; os.system('x')", "import os; os.execv('x', [])",
        "open('x', **k)", "open('x', *m)",
        "print('$(rm x)')", "kaputt(",
    ])
    def test_writing_or_unclear_code_is_not_readonly(self, code):
        assert not bash_gate._python_is_readonly(code), code

    @pytest.mark.parametrize("code", [
        "import json, glob; [print(json.load(open(f))) for f in glob.glob('*.json')]",
        "print('abc'.replace('a', 'b'))",
        "d = {}; e = d.copy()",
        "from pathlib import Path; print(Path('x').read_text())",
        "open('x', 'rb').read()",
        "from os.path import join",
    ])
    def test_reading_code_is_readonly(self, code):
        assert bash_gate._python_is_readonly(code), code

    def test_dollar_in_quoted_heredoc_body_is_fine(self):
        code = "import re\nprint(re.compile(r'x$'))"
        assert bash_gate._python_is_readonly(code, shell_expanded=False)
        assert not bash_gate._python_is_readonly(code)

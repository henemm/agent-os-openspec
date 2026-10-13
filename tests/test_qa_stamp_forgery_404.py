"""TDD RED — Issue #404, Befund F003: `qa_run_stamp` darf nicht per Python-Import
gefaelscht werden koennen.

Spec: docs/specs/fix-404-qa-stempel-faelschung.md (AC-1 bis AC-7).

Ebene 1: `workflow.write_qa_run_stamp` schreibt nur, wenn der Einstiegspunkt des
Prozesses `qa_gate.py` ist. Ebene 2: `bash_gate.py` blockt Bash-Kommandos, die den
Stempel per Python ansprechen (Freitext bleibt frei). Alle Tests laufen ueber echte
Subprozesse gegen eine Wegwerf-Sandbox (Muster: test_qa_gate_run_345.py).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

WF = "wf-404"
STAMP = "qa_run_stamp"
FORGED = {"source": "forged", "exit_code": 0, "output_sha256": "0" * 64}


def _env(root: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK",
                        "CLAUDE_TOOL_INPUT", "PYTHONPATH")
           and not k.startswith("GIT_")}
    env["CLAUDE_PROJECT_DIR"] = str(root)
    return env


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    claude = root / ".claude"
    (claude / "workflows").mkdir(parents=True)
    (claude / "active_workflow").write_text(WF + "\n")
    (claude / "workflows" / f"{WF}.json").write_text(json.dumps({
        "name": WF, "workflow_type": "feature", "current_phase": "phase6_implement",
        "adversary_verdict": None, "test_artifacts": [], "phase_log": [],
    }, indent=2))
    return root


def _state(root: Path) -> dict:
    return json.loads((root / ".claude" / "workflows" / f"{WF}.json").read_text())


def _out(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


def _py(root: Path, args: list):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True,
                          cwd=str(root), env=_env(root), stdin=subprocess.DEVNULL,
                          timeout=60)


def _bash_gate(root: Path, command: str):
    env = _env(root)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"command": command})
    return subprocess.run([sys.executable, str(HOOKS_DIR / "bash_gate.py")],
                          capture_output=True, text=True, cwd=str(root), env=env,
                          stdin=subprocess.DEVNULL, timeout=60)


FORGE_CODE = (
    f"import sys; sys.path.insert(0, {str(HOOKS_DIR)!r}); "
    "from workflow import write_qa_run_stamp; "
    f"write_qa_run_stamp({FORGED!r})"
)


def test_python_c_import_is_refused(project):
    """AC-1: `python3 -c`-Import -> PermissionError, Stempel unveraendert."""
    r = _py(project, ["-c", FORGE_CODE])
    assert r.returncode != 0, _out(r)
    assert "PermissionError" in _out(r), _out(r)
    assert STAMP not in _state(project)


def test_script_file_import_is_refused(project, tmp_path):
    """AC-2: Skriptdatei mit anderem Namen -> PermissionError, kein Stempel."""
    script = tmp_path / "forge_stamp.py"
    script.write_text(FORGE_CODE + "\n")
    r = _py(project, [str(script)])
    assert r.returncode != 0, _out(r)
    assert "PermissionError" in _out(r), _out(r)
    assert STAMP not in _state(project)


def test_qa_gate_run_still_writes_stamp(project):
    """AC-3: `qa_gate.py --run` schreibt den Stempel weiterhin."""
    (project / ".claude" / "config.yaml").write_text(
        'qa_gate:\n  test_command: "echo \'3 passed in 0.1s\'"\n')
    r = _py(project, [str(HOOKS_DIR / "qa_gate.py"), "--run"])
    assert r.returncode == 0, _out(r)
    stamp = _state(project).get(STAMP)
    assert stamp and stamp.get("exit_code") == 0, _out(r)


def test_bash_gate_blocks_python_c_stamp_write(project):
    """AC-4: `python3 -c "... write_qa_run_stamp ..."` -> Exit 2."""
    cmd = ('python3 -c "from workflow import write_qa_run_stamp; '
           'write_qa_run_stamp({\'exit_code\': 0})"')
    r = _bash_gate(project, cmd)
    assert r.returncode == 2, _out(r)
    assert "qa_gate.py --run" in _out(r), _out(r)


def test_bash_gate_blocks_heredoc_stamp_write(project):
    """AC-5: Heredoc an Python, der qa_run_stamp anspricht -> Exit 2."""
    cmd = ("python3 - <<'EOF'\n"
           "from workflow import write_qa_run_stamp\n"
           "write_qa_run_stamp({'exit_code': 0})\n"
           "EOF")
    r = _bash_gate(project, cmd)
    assert r.returncode == 2, _out(r)
    assert "qa_gate.py --run" in _out(r), _out(r)


@pytest.mark.parametrize("command", [
    'gh issue comment 404 --body "write_qa_run_stamp laesst sich fuellen"',
    'git log --grep qa_run_stamp',
    "grep -rn qa_run_stamp core/hooks",
])
def test_bash_gate_allows_freetext_mentions(project, command):
    """AC-6: Freitext/Suche, die den Namen nennt, wird nicht wegen des Stempels geblockt."""
    r = _bash_gate(project, command)
    assert "qa_gate.py --run" not in _out(r), _out(r)

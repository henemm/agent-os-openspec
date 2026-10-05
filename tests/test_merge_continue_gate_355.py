"""Issue #355: `git merge --continue` erzeugt einen Merge-Commit und muss wie
`git commit` durch die Commit-Gates (Adversary-Verdict, Rebase-Pflicht)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"


@pytest.fixture
def project(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    wf = tmp_path / ".claude" / "workflows"
    wf.mkdir(parents=True)
    (wf / "fix-42-x.json").write_text(json.dumps(
        {"name": "fix-42-x", "current_phase": "phase6_implement"}))
    return tmp_path


def _gate(project: Path, command: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME", "OPENSPEC_FRAMEWORK")}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env["OPENSPEC_ACTIVE_WORKFLOW"] = "fix-42-x"
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bash_gate.py")],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True, text=True, env=env, cwd=str(project),
    )


@pytest.mark.parametrize("cmd", [
    "git commit -m x",
    "git merge --continue",
    "git -C . merge --continue",
    "git add -A && git merge --continue",
])
def test_commit_creating_commands_need_verdict(project, cmd):
    r = _gate(project, cmd)
    assert r.returncode == 2 and "Adversary verdict" in r.stderr, (cmd, r.stderr)


@pytest.mark.parametrize("cmd", [
    "git merge --abort",
    "git status",
    "echo 'git merge --continue'",
    "git log --grep='merge --continue'",
])
def test_other_commands_unaffected(project, cmd):
    r = _gate(project, cmd)
    assert r.returncode == 0, (cmd, r.stderr)

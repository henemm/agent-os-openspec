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


# --- Pruefrunde 1 (F3): git akzeptiert Praefixe langer Optionen ---

@pytest.mark.parametrize("cmd", ["git merge --cont", "git merge --conti",
                                 'git merge "--continue"', "git merge --no-edit --continue"])
def test_option_prefixes_need_verdict(project, cmd):
    r = _gate(project, cmd)
    assert r.returncode == 2 and "Adversary verdict" in r.stderr, (cmd, r.stderr)


# --- Pruefrunde 1 (F4): im Merge zaehlen nur eigene Aenderungen ---

def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def test_merge_change_set_excludes_files_brought_in_from_main(tmp_path, monkeypatch):
    repo = tmp_path / "r"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@example.invalid"], repo)
    _git(["config", "user.name", "T"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    (repo / "conf.txt").write_text("base\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-qm", "base"], repo)
    _git(["checkout", "-qb", "feat"], repo)
    (repo / "own.py").write_text("x = 1\n")
    (repo / "conf.txt").write_text("feat\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-qm", "feat"], repo)
    _git(["checkout", "-q", "main"], repo)
    (repo / "upstream.py").write_text("y = 2\n")
    (repo / "conf.txt").write_text("main\n")
    _git(["add", "-A"], repo)
    _git(["commit", "-qm", "main"], repo)
    _git(["checkout", "-q", "feat"], repo)
    subprocess.run(["git", "merge", "main"], cwd=str(repo), capture_output=True)
    (repo / "conf.txt").write_text("resolved\n")
    _git(["add", "conf.txt"], repo)

    sys.path.insert(0, str(HOOKS_DIR))
    import bash_gate
    monkeypatch.setattr(bash_gate, "_measurement_root", lambda: repo)
    files, partial, err = bash_gate._commit_change_set("git merge --continue")
    names = {Path(f).name for f in files or []}
    assert err is None
    assert "upstream.py" not in names, names

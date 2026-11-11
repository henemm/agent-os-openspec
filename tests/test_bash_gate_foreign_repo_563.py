"""Issue #563: Commit-Gates (bash_gate Schritt 5) nur fuer Commits im Repo
des aktiven Workflows.

Echte Repos in tmp_path, echter Worktree, Hook als Subprozess (Muster
test_bash_gate_worktree_commit_155.py). Kein Mock von Shell oder git.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BASH_GATE = REPO_ROOT / "core" / "hooks" / "bash_gate.py"

WF_NAME = "fix-563"


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(["init", "-b", "main"], path)
    _git(["config", "user.email", "test@example.invalid"], path)
    _git(["config", "user.name", "Test"], path)
    _git(["config", "commit.gpgsign", "false"], path)
    (path / "a.txt").write_text("a\n")
    _git(["add", "-A"], path)
    _git(["commit", "-m", "init"], path)
    return path


@pytest.fixture
def env563(tmp_path):
    """Sitzungsrepo (Workflow phase6, kein Verdict), Worktree, fremdes Repo."""
    main = _init_repo(tmp_path / "session_repo")
    worktree = tmp_path / "worktrees" / WF_NAME
    _git(["worktree", "add", str(worktree), "-b", WF_NAME], main)
    foreign = _init_repo(tmp_path / "foreign_repo")
    nonrepo = tmp_path / "plain_dir"
    nonrepo.mkdir()

    wf_dir = main / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{WF_NAME}.json").write_text(json.dumps({
        "name": WF_NAME,
        "current_phase": "phase6_implement",
        "workflow_type": "feature",
    }))
    (main / ".claude" / "active_workflow").write_text(WF_NAME)
    (worktree / ".claude").mkdir(parents=True, exist_ok=True)
    (worktree / ".claude" / "active_workflow").write_text(WF_NAME)
    return {"main": main, "worktree": worktree, "foreign": foreign,
            "nonrepo": nonrepo, "tmp": tmp_path}


def _run_gate(cwd: Path, command: str, project_dir: Path = None):
    env = dict(os.environ)
    for var in ("CLAUDE_PROJECT_DIR", "CLAUDE_TOOL_INPUT",
                "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK"):
        env.pop(var, None)
    if project_dir is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project_dir)
    payload = json.dumps({"tool_input": {"command": command}})
    proc = subprocess.run(
        [sys.executable, str(BASH_GATE)], cwd=str(cwd), input=payload,
        capture_output=True, text=True, timeout=60, env=env,
    )
    return proc.returncode, proc.stderr


def _assert_adversary_block(rc, stderr):
    assert rc == 2, f"erwartet Exit 2, war {rc}; stderr={stderr!r}"
    assert "Adversary verdict" in stderr, f"stderr={stderr!r}"


def test_cd_into_foreign_repo_then_commit_is_allowed(env563):
    rc, stderr = _run_gate(env563["main"],
                           f"cd {env563['foreign']} && git commit -m x")
    assert rc == 0, f"rc={rc}, stderr={stderr!r}"


def test_git_dash_c_foreign_repo_commit_is_allowed(env563):
    rc, stderr = _run_gate(env563["main"],
                           f"git -C {env563['foreign']} commit -m x")
    assert rc == 0, f"rc={rc}, stderr={stderr!r}"


def test_bare_commit_in_own_repo_stays_blocked(env563):
    rc, stderr = _run_gate(env563["main"], "git commit -m x")
    _assert_adversary_block(rc, stderr)


def test_commit_in_own_worktree_or_main_repo_stays_blocked(env563):
    rc, stderr = _run_gate(env563["main"],
                           f"git -C {env563['worktree']} commit -m x")
    _assert_adversary_block(rc, stderr)
    rc, stderr = _run_gate(env563["worktree"],
                           f"cd {env563['main']} && git commit -m x")
    _assert_adversary_block(rc, stderr)


def test_mixed_own_and_foreign_commit_stays_blocked(env563):
    f = env563["foreign"]
    rc, stderr = _run_gate(env563["main"],
                           f"git commit -m x && git -C {f} commit -m y")
    _assert_adversary_block(rc, stderr)
    rc, stderr = _run_gate(env563["main"],
                           f"git -C {f} commit -m y && git commit -m x")
    _assert_adversary_block(rc, stderr)


def _unsafe_commands(e):
    f, n, p = e["foreign"], e["tmp"] / "does_not_exist", e["nonrepo"]
    return [
        f"GIT_DIR={f}/.git git commit -m x",
        f"git --git-dir={f}/.git commit -m x",
        f"git --work-tree={f} commit -m x",
        f'bash -c "cd {f} && git commit -m x"',
        "cd $X && git commit -m x",
        f"cd {f} && xargs git commit -m x",
        f"git -C {n} commit -m x",
        f"git -C {p} commit -m x",
        f'cd {f} && git commit -m "x',
    ]


@pytest.mark.parametrize("idx", range(9))
def test_unsafe_forms_stay_blocked_fail_closed(env563, idx):
    cmd = _unsafe_commands(env563)[idx]
    rc, stderr = _run_gate(env563["main"], cmd)
    assert rc == 2, f"{cmd!r}: rc={rc}, stderr={stderr!r}"


def test_stop_lock_and_secrets_still_block_in_foreign_repo(env563):
    f = env563["foreign"]
    secret_file = "." + "env"
    # Secrets
    rc, stderr = _run_gate(env563["main"],
                           f"cat {secret_file} && git -C {f} commit -m x")
    assert rc == 2, f"rc={rc}, stderr={stderr!r}"
    assert "Adversary verdict" not in stderr
    # Stop-Lock
    (env563["main"] / ".claude" / "stop_lock.json").write_text(
        json.dumps({"enabled": True}))
    rc, stderr = _run_gate(env563["main"], f"git -C {f} commit -m x")
    assert rc == 2, f"rc={rc}, stderr={stderr!r}"
    assert "Adversary verdict" not in stderr
    assert "stop" in stderr.lower(), f"stderr={stderr!r}"


def test_bare_commit_with_cwd_in_foreign_repo_is_allowed(env563):
    # Persistentes `cd` der Sitzung: Projekt bleibt das Sitzungsrepo, die
    # Hook-cwd liegt im fremden Repo.
    rc, stderr = _run_gate(env563["foreign"], "git commit -m x",
                           project_dir=env563["main"])
    assert rc == 0, f"rc={rc}, stderr={stderr!r}"

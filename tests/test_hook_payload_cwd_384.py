"""Regressionstest fuer Issue #384 (Hooks loesen in Worktree-Sitzungen der
Desktop-App den Workflow nicht auf).

Beobachtet in loose-ends (2026-10-06): Der phase_listener feuerte bei
"approved" und "go", meldete aber "kein aufloesbarer Workflow" — obwohl
`<worktree>/.claude/active_workflow` gesetzt war. Der Prozess-cwd des Hooks
lag nicht im Worktree; `_find_worktree_root()` entscheidet aber ueber
`Path.cwd()`. Laut Claude-Code-Doku folgt nur das Eingabefeld `cwd` dem
Worktree ("cwd follows Claude"), `CLAUDE_PROJECT_DIR` bleibt am Startort.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
WF = "bug-384-probe"


def _git(args: list, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def main_and_worktree(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    _git(["init", "-q"], main)
    _git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
          "--allow-empty", "-m", "init"], main)
    wt = main / ".claude" / "worktrees" / "wt"
    _git(["worktree", "add", "-q", str(wt)], main)
    wf_dir = main / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{WF}.json").write_text(json.dumps({
        "name": WF,
        "workflow_type": "bug",
        "current_phase": "phase3_spec",
        "spec_approved": False,
    }))
    (wt / ".claude").mkdir()
    (wt / ".claude" / "active_workflow").write_text(WF + "\n")
    return main, wt


def _run(main: Path, payload: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "OPENSPEC_ACTIVE_WORKFLOW"}
    env["CLAUDE_PROJECT_DIR"] = str(main)
    # Prozess-cwd = Haupt-Repo, wie in der Desktop-App beobachtet.
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "phase_listener.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env=env, cwd=str(main),
    )


def _approved(main: Path) -> bool:
    data = json.loads((main / ".claude" / "workflows" / f"{WF}.json").read_text())
    return data.get("spec_approved") is True


def test_approval_resolves_worktree_from_payload_cwd(main_and_worktree):
    main, wt = main_and_worktree
    result = _run(main, {"prompt": "approved", "cwd": str(wt)})
    assert result.returncode == 0, result.stderr
    assert "kein auflösbarer Workflow" not in result.stdout + result.stderr
    assert _approved(main)


def test_without_payload_cwd_main_repo_resolution_is_unchanged(main_and_worktree):
    main, _ = main_and_worktree
    result = _run(main, {"prompt": "approved"})
    assert result.returncode == 0, result.stderr
    assert not _approved(main)


def test_nonexistent_payload_cwd_is_ignored(main_and_worktree, tmp_path):
    main, _ = main_and_worktree
    result = _run(main, {"prompt": "approved", "cwd": str(tmp_path / "gone")})
    assert result.returncode == 0, result.stderr
    assert not _approved(main)


def test_adopt_payload_cwd_switches_directory(main_and_worktree, monkeypatch):
    sys.path.insert(0, str(HOOKS_DIR))
    import hook_utils
    main, wt = main_and_worktree
    monkeypatch.chdir(main)
    hook_utils.adopt_payload_cwd({"cwd": str(wt)})
    assert hook_utils.find_worktree_root().resolve() == wt.resolve()

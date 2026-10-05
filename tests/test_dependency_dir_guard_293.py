"""Issue #293: bash_gate blockt das Loeschen von Abhaengigkeits-Ordnern.

In Worktrees ist node_modules oft ein Symlink auf den geteilten Ordner im
Haupt-Repo — ein `rm -rf` trifft dann alle Sitzungen. Die Sperre setzt KEINE
Symlink-Aufloesung voraus.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import bash_gate  # noqa: E402


@pytest.mark.parametrize("cmd", [
    "rm -rf node_modules",
    "rm -rf frontend/node_modules/",
    "rm -rf node_modules/*",
    "cd frontend && rm -rf node_modules && npm install",
    "npx rimraf node_modules",
    "sudo rm -r .venv",
    "rmdir vendor",
    "mv node_modules /tmp/old",
    "find . -name node_modules -prune -exec rm -rf {} +",
    "bash -c \"rm -rf node_modules\"",
    "FOO=1 rm -rf ./node_modules",
])
def test_deleting_dependency_dir_detected(cmd):
    assert bash_gate._deletes_dependency_dir(cmd, {}), cmd


@pytest.mark.parametrize("cmd", [
    "rm -rf node_modules/.cache",
    "ls -la node_modules",
    "npm ci",
    "rm -rf dist",
    "git rm -r --cached node_modules",
    "echo rm node_modules",
    "grep -r foo node_modules",
    "mv /tmp/old node_modules",
    "rm -rf my_node_modules",
])
def test_other_commands_untouched(cmd):
    assert not bash_gate._deletes_dependency_dir(cmd, {}), cmd


def test_kill_switch_and_custom_list():
    off = {"dependency_dir_guard": {"enabled": False}}
    assert not bash_gate._deletes_dependency_dir("rm -rf node_modules", off)
    custom = {"dependency_dir_guard": {"dirs": ["target"]}}
    assert bash_gate._deletes_dependency_dir("rm -rf target", custom) == "target"
    assert not bash_gate._deletes_dependency_dir("rm -rf node_modules", custom)


def test_config_yaml_matches_code_default():
    cfg = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())
    assert cfg["dependency_dir_guard"]["dirs"] == bash_gate.DEFAULT_DEPENDENCY_DIRS


def _run(project: Path, command: str):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_TOOL_INPUT", "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK")}
    env["CLAUDE_PROJECT_DIR"] = str(project)
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bash_gate.py")],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True, text=True, env=env, cwd=str(project),
    )


def test_hook_blocks_through_symlink(tmp_path):
    """Ende-zu-Ende: node_modules als Symlink auf einen geteilten Ordner."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    shared = tmp_path / "shared_deps"
    shared.mkdir()
    (tmp_path / "node_modules").symlink_to(shared)
    r = _run(tmp_path, "rm -rf node_modules && npm install")
    assert r.returncode == 2, r.stderr
    assert "npm ci" in r.stderr and "override" in r.stderr
    assert shared.exists()


def test_hook_allows_in_place_reinstall(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert _run(tmp_path, "npm ci").returncode == 0
    assert _run(tmp_path, "rm -rf node_modules/.cache").returncode == 0

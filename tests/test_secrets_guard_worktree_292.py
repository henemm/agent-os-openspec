"""Issue #292 (PO-Entscheidung A): secrets_guard-Muster aus dem eigenen Zweig,
mit fester Untergrenze.

Ein Worktree darf die projekteigenen Muster seines Zweigs setzen (sonst blockt
die breite Fassung des Haupt-Ordners harmlose Dateinamen). Die eingebauten
Grundmuster (.env, credentials.json, private Keys, .pem, .key, *.secret.*)
bleiben immer aktiv; `enabled` kommt nie aus dem Worktree. Echte Repos, echter
`git worktree add`, Hooks als Subprozess.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"

MAIN_CFG = """framework:
  enabled: true
secrets_guard:
  sensitive_patterns:
    - "\\\\.env(rc)?\\\\b"
    - "_key"
  always_blocked:
    - "_key"
"""


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    _git(["init", "-q", "-b", "main"], main)
    _git(["config", "user.email", "t@example.invalid"], main)
    _git(["config", "user.name", "T"], main)
    _git(["config", "commit.gpgsign", "false"], main)
    (main / "openspec.yaml").write_text(MAIN_CFG)
    _git(["add", "-A"], main)
    _git(["commit", "-qm", "init"], main)
    wt = tmp_path / "wt"
    _git(["worktree", "add", "-q", "-b", "feat", str(wt)], main)
    for d in (main, wt):
        (d / "notes_key.txt").write_text("harmlos\n")
        (d / ".env").write_text("X=1\n")
    return main, wt


def _hook(hook, cwd, command):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_TOOL_INPUT", "CLAUDE_TOOL_NAME",
                        "OPENSPEC_FRAMEWORK", "OPENSPEC_ENV", "OPENSPEC_ACTIVE_WORKFLOW")}
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run([sys.executable, str(HOOKS_DIR / hook)], input=payload,
                          capture_output=True, text=True, env=env, cwd=str(cwd))


def test_main_patterns_apply_in_worktree_without_own_config(repo):
    main, wt = repo
    (wt / "openspec.yaml").unlink()
    assert _hook("secrets_guard.py", wt, "cat notes_key.txt").returncode == 2


def test_branch_can_narrow_project_patterns(repo):
    main, wt = repo
    (wt / "openspec.yaml").write_text(MAIN_CFG.replace('    - "_key"\n', '    - "private_key"\n'))
    assert _hook("secrets_guard.py", wt, "cat notes_key.txt").returncode == 0
    assert _hook("bash_gate.py", wt, "cat notes_key.txt").returncode == 0


@pytest.mark.parametrize("hook", ["secrets_guard.py", "bash_gate.py"])
@pytest.mark.parametrize("branch_cfg", [
    "secrets_guard:\n  sensitive_patterns: []\n  always_blocked: []\n",
    "secrets_guard:\n  enabled: false\n  sensitive_patterns: []\n",
    "secrets_guard:\n  sensitive_patterns: ['(', 'foo']\n",
])
def test_branch_cannot_drop_builtin_floor(repo, hook, branch_cfg):
    main, wt = repo
    (wt / "openspec.yaml").write_text(branch_cfg)
    for cmd in ("cat .env", "cat deploy/id.pem", "cat credentials.json"):
        r = _hook(hook, wt, cmd)
        assert r.returncode == 2, (hook, branch_cfg, cmd, r.stderr)


def test_main_folder_session_unchanged(repo):
    main, wt = repo
    (wt / "openspec.yaml").write_text("secrets_guard:\n  sensitive_patterns: []\n")
    assert _hook("secrets_guard.py", main, "cat notes_key.txt").returncode == 2


def test_helper_floor_and_validity(repo):
    """Im eigenen Prozess (load_config/find_project_root cachen modulweit)."""
    main, wt = repo
    (wt / "openspec.yaml").write_text("secrets_guard:\n  sensitive_patterns: ['(', 'custom_x']\n")
    code = (
        "import json, sys; sys.path.insert(0, %r)\n"
        "import config_loader, hook_utils\n"
        "s, a = config_loader.secrets_guard_patterns()\n"
        "print(json.dumps({'s': s, 'a': a, 'base': list(hook_utils.SECRETS_SENSITIVE_PATTERNS)}))\n"
    ) % str(HOOKS_DIR)
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    out = subprocess.run([sys.executable, "-c", code], cwd=str(wt), env=env,
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    assert set(data["base"]) <= set(data["s"])
    assert "custom_x" in data["s"] and "(" not in data["s"] and "_key" not in data["s"]
    assert data["a"] == ["_key"], "ohne always_blocked im Zweig gilt die Haupt-Ordner-Liste"

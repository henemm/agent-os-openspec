"""Issue #185: Banner warnt, wenn der Haupt-Ordner hinter origin liegt.

Echte Repos: ein Bare-Remote, ein Haupt-Ordner (Klon) und ein zweiter Klon,
der einen Commit pusht. Gemessen wird der Zweig des Haupt-Ordners — auch aus
einer Worktree-Sitzung heraus. Scheitert der Fetch, erscheint keine Zeile.
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import session_banner  # noqa: E402


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _identity(repo):
    _git(["config", "user.email", "t@example.invalid"], repo)
    _git(["config", "user.name", "T"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)


@pytest.fixture
def repos(tmp_path):
    origin = tmp_path / "origin.git"
    _git(["init", "-q", "--bare", "-b", "main", str(origin)], tmp_path)
    main = tmp_path / "main"
    _git(["clone", "-q", str(origin), str(main)], tmp_path)
    _identity(main)
    (main / "a.txt").write_text("1\n")
    _git(["add", "-A"], main)
    _git(["commit", "-qm", "init"], main)
    _git(["push", "-q", "-u", "origin", "main"], main)
    return origin, main


def _push_foreign_commit(origin, tmp_path, n=1):
    other = tmp_path / "other"
    _git(["clone", "-q", str(origin), str(other)], tmp_path)
    _identity(other)
    for i in range(n):
        (other / f"b{i}.txt").write_text("x\n")
        _git(["add", "-A"], other)
        _git(["commit", "-qm", f"c{i}"], other)
    _git(["push", "-q"], other)


def test_up_to_date_no_line(repos):
    _, main = repos
    assert session_banner.behind_lines(main) == []


def test_behind_shows_count_and_sync_main(repos, tmp_path):
    origin, main = repos
    _push_foreign_commit(origin, tmp_path, n=2)
    lines = session_banner.behind_lines(main)
    assert len(lines) == 1 and "2 Commit(s) hinter origin/main" in lines[0], lines
    assert "sync-main" in lines[0]


def test_worktree_session_measures_main_folder(repos, tmp_path):
    origin, main = repos
    wt = tmp_path / "wt"
    _git(["worktree", "add", "-q", "-b", "feat", str(wt)], main)
    _push_foreign_commit(origin, tmp_path)
    lines = session_banner.behind_lines(wt)
    assert lines and "1 Commit(s) hinter origin/main" in lines[0], lines
    assert (main / "a.txt").exists() and not (main / "b0.txt").exists(), "Haupt-Ordner unberuehrt"


def test_failed_fetch_shows_nothing_and_is_fast(repos, tmp_path):
    origin, main = repos
    _push_foreign_commit(origin, tmp_path)
    _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], main)
    start = time.monotonic()
    assert session_banner.behind_lines(main) == []
    assert time.monotonic() - start < 5


def test_not_a_repo_no_line(tmp_path):
    assert session_banner.behind_lines(tmp_path) == []


# --- Pruefrunde 1 ---

def test_no_askpass_dialog_on_fetch(repos, tmp_path, monkeypatch):
    """VS Code setzt GIT_ASKPASS — beim Session-Start darf kein Dialog aufgehen."""
    origin, main = repos
    marker = tmp_path / "askpass_called"
    askpass = tmp_path / "askpass.sh"
    askpass.write_text(f"#!/bin/sh\ntouch {marker}\necho x\n")
    askpass.chmod(0o755)
    monkeypatch.setenv("GIT_ASKPASS", str(askpass))
    monkeypatch.setenv("SSH_ASKPASS", str(askpass))
    calls = []
    real_run = session_banner.__dict__.get("_git")

    def spy(args, cwd, timeout):
        calls.append(args)
        return real_run(args, cwd, timeout)
    monkeypatch.setattr(session_banner, "_git", spy)
    session_banner.behind_lines(main)
    import subprocess as sp
    env = {}
    orig = sp.Popen

    def capture(*a, **kw):
        env.update(kw.get("env") or {})
        return orig(*a, **kw)
    monkeypatch.setattr(session_banner, "_git", real_run)
    monkeypatch.setattr(sp, "Popen", capture)
    session_banner.behind_lines(main)
    assert env.get("GIT_ASKPASS") == "" and env.get("SSH_ASKPASS") == ""
    assert env.get("GIT_TERMINAL_PROMPT") == "0" and env.get("GCM_INTERACTIVE") == "never"
    assert not marker.exists()
    assert any("fetch" in a for a in calls)


def test_remote_name_with_slash(repos, tmp_path):
    origin, main = repos
    _git(["remote", "rename", "origin", "team/origin"], main)
    _git(["branch", "--set-upstream-to", "team/origin/main", "main"], main)
    _push_foreign_commit(origin, tmp_path)
    lines = session_banner.behind_lines(main)
    assert lines and "1 Commit(s) hinter team/origin/main" in lines[0], lines


# --- #371: keine Waisen nach dem Timeout, BatchMode auch bei eigener GIT_SSH_COMMAND ---

def test_hanging_credential_helper_leaves_no_orphans(repos, tmp_path, monkeypatch):
    origin, main = repos
    marker = tmp_path / "helper_started"
    helper = tmp_path / "helper.sh"
    helper.write_text(f"#!/bin/sh\ntouch {marker}\nexec sleep 30\n")
    helper.chmod(0o755)
    # Remote, der nach Zugangsdaten fragt: ext::-Transport mit haengendem Helfer
    _git(["config", "protocol.ext.allow", "always"], main)
    _git(["remote", "set-url", "origin", f"ext::{helper}"], main)
    import time
    start = time.monotonic()
    assert session_banner.behind_lines(main) == []
    assert time.monotonic() - start < 5
    time.sleep(0.3)
    left = subprocess.run(["pgrep", "-f", str(helper)], capture_output=True, text=True).stdout
    assert marker.exists(), "Testaufbau: Helfer muss gestartet sein"
    assert left.strip() == "", f"Waisenprozesse: {left}"


def test_user_ssh_command_gets_batchmode(monkeypatch, tmp_path):
    seen = {}
    import subprocess as sp
    real = sp.Popen

    def spy(*a, **kw):
        seen.update(kw.get("env") or {})
        return real(*a, **kw)
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -i ~/.ssh/deploy")
    monkeypatch.setattr(sp, "Popen", spy)
    # Nur der Fetch nutzt ssh und bekommt BatchMode (#382); kein Remote, scheitert lokal
    session_banner._git(["fetch", "--quiet", "nonexistent-remote"], tmp_path, 2)
    assert seen["GIT_SSH_COMMAND"] == "ssh -i ~/.ssh/deploy -oBatchMode=yes"

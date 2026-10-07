"""Issue #382: `core.sshCommand` nur fuer den Fetch lesen, im Zeitbudget.

`_git` las `git config --get core.sshCommand` vor JEDEM Aufruf (ca. 5 pro
Banner) mit festem 1-s-Timeout, obwohl nur der Fetch ssh nutzt. Haengt
`git config`, frass das bis zu 5 s vom 4-s-Budget.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import session_banner  # noqa: E402


class _Recorder:
    """Ersetzt subprocess.run/Popen; zeichnet Aufrufe auf, startet nichts."""

    def __init__(self):
        self.config_timeouts = []
        self.popen_timeouts = []
        self.popen_env = None

    def run(self, cmd, **kw):
        if cmd[:3] == ["git", "config", "--get"] and cmd[3:] == ["core.sshCommand"]:
            self.config_timeouts.append(kw.get("timeout"))
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    def popen(self, cmd, **kw):
        rec = self
        rec.popen_env = kw.get("env")

        class _P:
            returncode = 0
            pid = 0

            def communicate(self, timeout=None):
                rec.popen_timeouts.append(timeout)
                return "", None
        return _P()


def _patch(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(subprocess, "run", rec.run)
    monkeypatch.setattr(subprocess, "Popen", rec.popen)
    return rec


def test_non_fetch_does_not_read_core_ssh_command(monkeypatch, tmp_path):
    rec = _patch(monkeypatch)
    for args in (["worktree", "list", "--porcelain"],
                 ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "main@{u}"],
                 ["config", "branch.main.remote"],
                 ["rev-list", "--count", "main..origin/main"]):
        session_banner._git(args, tmp_path, 1)
    assert rec.config_timeouts == []


def test_fetch_reads_core_ssh_command_once(monkeypatch, tmp_path):
    rec = _patch(monkeypatch)
    session_banner._git(["-c", "maintenance.auto=false", "-c", "gc.auto=0", "fetch", "--quiet",
                         "--no-recurse-submodules", "origin"], tmp_path, 3)
    assert len(rec.config_timeouts) == 1
    assert rec.config_timeouts[0] <= 1
    assert rec.popen_env["GIT_SSH_COMMAND"].endswith("-oBatchMode=yes")


def test_config_timeout_capped_by_remaining_budget(monkeypatch, tmp_path):
    rec = _patch(monkeypatch)
    session_banner._git(["fetch", "origin"], tmp_path, 0.3)
    assert rec.config_timeouts and rec.config_timeouts[0] <= 0.3


def test_fetch_timeout_includes_config_time(monkeypatch, tmp_path):
    """Config-Lesen und Fetch zusammen bleiben im uebergebenen Timeout."""
    rec = _patch(monkeypatch)
    clock = iter([100.0, 100.8, 100.8, 100.8])
    monkeypatch.setattr(session_banner, "_monotonic", lambda: next(clock, 100.8))
    session_banner._git(["fetch", "origin"], tmp_path, 3)
    assert rec.popen_timeouts and rec.popen_timeouts[0] <= 2.2 + 1e-9

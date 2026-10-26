"""Schutz gegen Dauerlast durch Werkzeuge — #462.

Teil 1: Der Adversary-Agent ruft Plugin-Skripte ueber `${_H}` auf, nie ueber `.claude/hooks/`.
Teil 2: `bash_gate.py` lehnt Suchen ab `/`, `~` ab; Unterordner bleiben frei.
Teil 3: `process_watchdog.py` beendet Suchen ab `/`, laesst `xcodebuild` in Ruhe.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / "core" / "hooks"
BASH_GATE = HOOKS / "bash_gate.py"
sys.path.insert(0, str(HOOKS))


# --- Teil 1 -------------------------------------------------------------------

def test_agent_ruft_skripte_ueber_hook_pfad_auf():
    text = (REPO_ROOT / "core" / "agents" / "implementation-validator.md").read_text()
    assert "python3 .claude/hooks/" not in text
    assert '_H="${_H:-.claude/hooks}"' in text
    assert "python3 ${_H}/adversary_dialog.py scaffold" in text


# --- Teil 2 -------------------------------------------------------------------

def _gate(command: str, tmp_path: Path) -> subprocess.CompletedProcess:
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / ".claude").mkdir(exist_ok=True)
    env = dict(os.environ)
    for var in ("OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK"):
        env.pop(var, None)
    env["CLAUDE_PROJECT_DIR"] = str(tmp_path)
    env["CLAUDE_TOOL_INPUT"] = json.dumps({"command": command})
    return subprocess.run([sys.executable, str(BASH_GATE)], cwd=str(tmp_path), env=env,
                          capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("command", [
    "find / -name adversary_dialog.py",
    "bfs -S dfs / -name adversary_dialog.py",
    "find ~ -name x",
    "find $HOME -name x",
    "find /home -type f",
    "find -L / -name x 2>/dev/null",
    "fd adversary_dialog /",
    "grep -r adversary_dialog /",
    "grep -rn foo ~/",
    "rg foo /",
    "cd /tmp && find / -name x",
    "timeout 5 find / -name x",
])
def test_suche_ab_wurzel_wird_abgelehnt(command, tmp_path):
    r = _gate(command, tmp_path)
    assert r.returncode == 2, (command, r.stdout, r.stderr)
    assert "#462" in r.stderr


@pytest.mark.parametrize("command", [
    "find ./docs -name x",
    "find . -name x",
    "find -name x",
    "find /tmp/foo -name x",
    "find ~/projekt -name x",
    "bfs ./core -name x",
    "fd adversary_dialog core",
    "grep -r foo .",
    "grep -r foo core/hooks",
    "grep foo /etc/hostname",
    "rg foo core",
    "echo find / -name x",
    "git log --grep='find /'",
])
def test_suche_im_projekt_bleibt_frei(command, tmp_path):
    r = _gate(command, tmp_path)
    assert "#462" not in r.stderr, (command, r.stderr)


# --- Teil 3 -------------------------------------------------------------------

def _fake(tmp_path: Path, name: str) -> subprocess.Popen:
    script = tmp_path / name
    # kein `exec`: sonst ersetzt `sleep` die Argumentzeile und die Suchwurzel ist weg
    script.write_text("#!/bin/sh\nsleep 20\n")
    script.chmod(0o755)
    return subprocess.Popen([str(script), "/", "-name", "x"])


def test_waechter_beendet_suche_und_schont_xcodebuild(tmp_path, monkeypatch):
    import process_watchdog as wd
    monkeypatch.setattr(wd, "SEARCH_KILL_AGE", 0)
    suche = _fake(tmp_path, "bfs")
    bau = _fake(tmp_path, "xcodebuild")
    try:
        time.sleep(0.5)
        # ein Shell-Skript zeigt `ps` als `/bin/sh <skript> …`; die Argumentzeile eines
        # echten bfs/xcodebuild-Binaers wird nachgestellt, Prozess und Kill bleiben echt
        shown = {suche.pid: "bfs -S dfs / -name x", bau.pid: "xcodebuild -scheme X /"}
        procs = [(pid, ppid, age, cpu, shown.get(pid, args))
                 for pid, ppid, age, cpu, args in wd.list_processes()]
        scope = wd.descendants(procs, {os.getpid()})
        findings = wd.scan(procs, scope)
        assert [f["pid"] for f in findings] == [suche.pid]
        assert findings[0]["kind"] == "search"
        wd.act(findings)
        assert suche.wait(timeout=10) == -signal.SIGTERM
        assert bau.poll() is None
    finally:
        for p in (suche, bau):
            if p.poll() is None:
                p.kill()
                p.wait()


def test_waechter_meldet_langlaeufer_ohne_ihn_zu_beenden():
    import process_watchdog as wd
    procs = [(10, 1, 3600, 900, "python3 build.py"), (11, 1, 30, 1, "python3 kurz.py"),
             (12, 1, 3600, 900, "xcodebuild -scheme X")]
    findings = wd.scan(procs, {10, 11, 12})
    assert [(f["pid"], f["kind"]) for f in findings] == [(10, "long")]
    assert "nicht beendet" in wd.act(findings, dry_run=True)[0]


def test_waechter_ausserhalb_des_scopes_bleibt_unberuehrt():
    import process_watchdog as wd
    procs = [(20, 1, 7200, 5000, "bfs -S dfs / -name x")]
    assert wd.scan(procs, set()) == []
    assert wd.scan(procs, {20})[0]["kind"] == "search"


def test_waechter_cli_meldet_und_beendet_nie_mit_fehler():
    for mode in ("hook", "end", "service"):
        r = subprocess.run([sys.executable, str(HOOKS / "process_watchdog.py"), mode, "--dry-run"],
                           input="{}", capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, (mode, r.stderr)

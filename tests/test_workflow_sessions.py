"""Tests fuer `workflow.py sessions` — Issue #106 (TDD RED).

Neues Lesekommando: gibt die Eintraege unter
`{project_root}/.claude/session-locks/*.json` aus — als Tabelle (Default) oder
als JSON-Array (`--json`). Spec: docs/specs/feat-106-session-register.md,
Test Plan Tests 19-21, AC-12/AC-13.

Hermetik: `find_project_root` wird auf `tmp_path` gepinnt. Kein Test darf das
echte `.claude/session-locks/` dieses Repos lesen oder beschreiben — dort
liegen die Eintraege laufender Server-Sessions.
"""

import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402
import workflow as wf  # noqa: E402


FULL_ENTRY = {
    "session_id": "sess-full",
    "cwd": "/home/user/myproject/.claude/worktrees/intake-106",
    "pid": 999999999,
    "started_at": 0.0,           # wird im Fixture auf now-basiert gesetzt
    "last_seen": 0.0,
    "agent_name": "agent-os-openspec-9a",
    "branch": "feat-106-session-register",
    "worktree": "intake-106",
    "issue": "106",
    "phase": "phase5_tdd_red",
    "workflow": "feat-106-session-register",
}

MINIMAL_ENTRY = {
    "session_id": "sess-min",
    "cwd": "/home/user/myproject",
    "pid": 999999998,
    "started_at": 0.0,
    "last_seen": 0.0,
}


def _pin_project_root(monkeypatch, root: Path) -> None:
    """find_project_root auf tmp_path pinnen — modulweite Bindung in
    workflow.py (`from hook_utils import find_project_root`) und die Quelle
    in hook_utils selbst."""
    monkeypatch.setattr(wf, "find_project_root", lambda: root)
    monkeypatch.setattr(hook_utils, "find_project_root", lambda: root)


def _make_locks(monkeypatch, tmp_path: Path, entries: list) -> Path:
    locks = tmp_path / ".claude" / "session-locks"
    locks.mkdir(parents=True, exist_ok=True)
    now = time.time()
    for entry in entries:
        data = dict(entry)
        data["started_at"] = now - 300
        data["last_seen"] = now - 30
        (locks / f"{data['session_id']}.json").write_text(json.dumps(data))
    _pin_project_root(monkeypatch, tmp_path)
    return locks


# ---------------------------------------------------------------------------
# Test 19 — Tabellenausgabe (AC-12)
# ---------------------------------------------------------------------------

def test_sessions_table_lists_all_entries(tmp_path, monkeypatch, capsys):
    """Beide Eintraege erscheinen; fehlende optionale Felder werden mit dem
    Platzhalter '–' dargestellt statt einen Fehler auszuloesen."""
    _make_locks(monkeypatch, tmp_path, [FULL_ENTRY, MINIMAL_ENTRY])

    wf.cmd_sessions([])

    out = capsys.readouterr().out
    assert "sess-full" in out
    assert "sess-min" in out
    assert "agent-os-openspec-9a" in out
    assert "intake-106" in out
    assert "–" in out, "Kein Platzhalter fuer fehlende optionale Felder"


# ---------------------------------------------------------------------------
# Test 20 — JSON-Ausgabe (AC-13)
# ---------------------------------------------------------------------------

def test_sessions_json_output_is_parsable(tmp_path, monkeypatch, capsys):
    """Die komplette stdout-Ausgabe ist mit json.loads() parsebar und enthaelt
    pro Eintrag mindestens session_id."""
    _make_locks(monkeypatch, tmp_path, [FULL_ENTRY, MINIMAL_ENTRY])

    wf.cmd_sessions(["--json"])

    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, list)
    assert {e["session_id"] for e in data} == {"sess-full", "sess-min"}


# ---------------------------------------------------------------------------
# Test 21 — Leeres Verzeichnis
# ---------------------------------------------------------------------------

def test_sessions_empty_dir_prints_hint(tmp_path, monkeypatch, capsys):
    """Leeres Lock-Verzeichnis → Hinweistext, keine leere Tabelle, kein Fehler."""
    _make_locks(monkeypatch, tmp_path, [])

    wf.cmd_sessions([])

    out = capsys.readouterr().out
    assert out.strip(), "Keine Ausgabe bei leerem Lock-Verzeichnis"
    assert "─" not in out, "Leere Tabelle statt Hinweistext"


def test_sessions_missing_dir_prints_hint(tmp_path, monkeypatch, capsys):
    """Gar kein Lock-Verzeichnis → derselbe Hinweistext, kein Crash."""
    _pin_project_root(monkeypatch, tmp_path)
    assert not (tmp_path / ".claude" / "session-locks").exists()

    wf.cmd_sessions([])

    out = capsys.readouterr().out
    assert out.strip(), "Keine Ausgabe ohne Lock-Verzeichnis"
    assert "─" not in out, "Leere Tabelle statt Hinweistext"

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


# ===========================================================================
# fix-120-121-session-register — Issue-Spalte  (AC-36, AC-37)
#
# Durch den Claim (#121) kann ein Eintrag mehrere Issues halten ("120,121",
# 7 Zeichen). Die Spalte war auf 5 Zeichen ausgelegt — laengere Werte
# schoben jede nachfolgende Spalte dieser Zeile nach rechts.
# ===========================================================================

def _table_rows(out: str) -> list:
    """Datenzeilen der Tabelle (ohne Trenner, Kopf und Fusszeile)."""
    return [
        line for line in out.splitlines()
        if line.startswith("  ") and "Session" not in line
        and "registriert" not in line and "─" not in line
    ]


def _header_line(out: str) -> str:
    return next(line for line in out.splitlines() if "Session" in line)


def test_sessions_multi_issue_keeps_column_alignment(tmp_path, monkeypatch, capsys):
    """AC-36: '120,121' (7 Zeichen) erscheint vollstaendig UND buendig.

    Die Zeile darf nicht laenger werden als die Kopfzeile — sonst rutscht die
    Alter-Spalte aus der Flucht.
    """
    entry = dict(FULL_ENTRY, session_id="sess-multi", issue="120,121")
    _make_locks(monkeypatch, tmp_path, [entry])

    wf.cmd_sessions([])

    out = capsys.readouterr().out
    assert "120,121" in out, "Mehrfach-Issue abgeschnitten"

    rows = _table_rows(out)
    assert len(rows) == 1
    assert len(rows[0]) == len(_header_line(out)), (
        "Datenzeile und Kopfzeile unterschiedlich lang — die Issue-Spalte "
        "sprengt die Ausrichtung"
    )


def test_sessions_issue_column_is_nine_wide(tmp_path, monkeypatch, capsys):
    """AC-36: die Kopfzeile reserviert 9 Zeichen fuer die Issue-Spalte."""
    _make_locks(monkeypatch, tmp_path, [dict(FULL_ENTRY, issue="120,121")])

    wf.cmd_sessions([])

    out = capsys.readouterr().out
    header = _header_line(out)
    start = header.index("Issue")
    # Zwischen 'Issue' und der naechsten Spalte muessen 9 Zeichen Platz sein.
    assert header[start:start + 9] == "Issue" + " " * 4, (
        f"Issue-Spalte nicht 9 Zeichen breit: {header[start:start + 12]!r}"
    )


def test_sessions_overlong_issue_is_truncated(tmp_path, monkeypatch, capsys):
    """AC-37: Werte laenger als 9 Zeichen werden gekuerzt statt die Spalte
    zu sprengen (Schutz vor kaputten oder manipulierten Eintraegen)."""
    entry = dict(FULL_ENTRY, session_id="sess-long", issue="120,121,122,123,124")
    _make_locks(monkeypatch, tmp_path, [entry])

    wf.cmd_sessions([])

    out = capsys.readouterr().out
    assert "120,121,122,123,124" not in out, "ueberlanger Wert nicht gekuerzt"

    rows = _table_rows(out)
    assert len(rows) == 1
    assert len(rows[0]) == len(_header_line(out)), (
        "Ausrichtung durch ueberlangen Issue-Wert zerstoert"
    )


def test_sessions_separator_matches_row_width(tmp_path, monkeypatch, capsys):
    """AC-36: der Trennstrich waechst mit der breiteren Issue-Spalte mit."""
    _make_locks(monkeypatch, tmp_path, [dict(FULL_ENTRY, issue="120,121")])

    wf.cmd_sessions([])

    out = capsys.readouterr().out
    sep = next(line for line in out.splitlines() if set(line.strip()) == {"─"})
    assert len(sep) == 178, f"Trennstrich {len(sep)} statt 178 Zeichen"


# ---------------------------------------------------------------------------
# Realistische Projektwerte muessen VOLLSTAENDIG erscheinen
#
# Dieser Test fehlte und haette den Rueckschritt verhindert: eine generische
# Kuerzung aller Spalten erfuellt zwar die Ausrichtungspruefung oben, kostete
# aber bei 4 von 5 realen Feldern Information, die der Vorgaengercode
# vollstaendig anzeigte. Gekuerzt wird ausschliesslich die Issue-Spalte.
# ---------------------------------------------------------------------------

REAL_WORLD_ENTRY = {
    "session_id": "c96ccadb-c87d-4934-aecb-9383baae9ced",   # UUID, 36
    "cwd": "/home/hem/agent-os-openspec/.claude/worktrees/intake-120-121",
    "pid": 999999999,
    "started_at": 0.0,
    "last_seen": 0.0,
    "agent_name": "agent-os-openspec-c6",                   # 20
    "worktree": "intake-120-121",                           # 14
    "branch": "worktree-intake-120-121",                    # 23
    "workflow": "fix-120-121-session-register",             # 28
    "phase": "phase6b_adversary",                           # 17
    "issue": "120,121",                                     # 7
}


def test_sessions_shows_real_project_values_in_full(tmp_path, monkeypatch, capsys):
    """Werte nach Projektkonvention `typ-NNN[-MMM]-beschreibung` erscheinen
    ungekuerzt — kein Feld verliert Information, kein '…' in der Zeile."""
    _make_locks(monkeypatch, tmp_path, [REAL_WORLD_ENTRY])

    wf.cmd_sessions([])

    out = capsys.readouterr().out
    for key in ("session_id", "agent_name", "worktree", "branch", "workflow",
                "phase", "issue"):
        assert REAL_WORLD_ENTRY[key] in out, (
            f"{key}={REAL_WORLD_ENTRY[key]!r} wird abgeschnitten — "
            "Informationsverlust gegenueber dem Vorgaengercode"
        )

    rows = _table_rows(out)
    assert len(rows) == 1
    assert "…" not in rows[0], f"Kuerzungszeichen in der Datenzeile: {rows[0]!r}"
    assert len(rows[0]) == len(_header_line(out)), "Ausrichtung gebrochen"

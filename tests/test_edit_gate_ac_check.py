"""TDD RED — Fix #60: edit_gate AC-Längencheck matcht Prosa + Repo-Scoping + Worktree-Spec.

Bildet AC-1, AC-2, AC-3, AC-5, AC-6 der Spec `docs/specs/fix-60-69-gate-parsing.md`
ab. Subprozess-Muster analog `tests/test_edit_gate_orchestrator_files.py`:
hermetisches Fake-Projekt (`.git` + `.claude/workflows/`), JSON-Payload über
stdin, `OPENSPEC_ACTIVE_WORKFLOW`-Env + `CLAUDE_PROJECT_DIR`. Kein Mocking —
echte Dateien in tmp_path.

RED-Erwartung (gegen den aktuellen Code):
  * AC-1  (test_prose_and_table_mentions_do_not_block)      → FÄLLT (Block trotz gültiger Spec)
  * AC-2  (test_path_outside_repo_skips_ac_check)           → FÄLLT (Block obwohl außerhalb Repo)
  * AC-3  (test_worktree_only_spec_is_checked)              → FÄLLT (Check steigt aus, kein Block)
  * AC-5  (test_ac_detection_is_shared_from_hook_utils)     → FÄLLT (geteilte Funktion fehlt)
Regressionsschutz (schon grün, MUSS grün bleiben):
  * AC-1-Gegenprobe (test_genuinely_short_bullet_still_blocks)
  * AC-6            (test_legacy_cutoff_still_passes)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
EDIT_GATE = HOOKS_DIR / "edit_gate.py"


# --- Subprozess-Harness (Absolutpfad zum Hook, cwd frei wählbar) ---

def _run_edit_gate(env: dict, file_path: str, cwd: str) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    full_env = dict(os.environ)
    full_env.update(env)
    return subprocess.run(
        [sys.executable, str(EDIT_GATE)],
        input=payload, capture_output=True, text=True, env=full_env, cwd=cwd,
    )


def _make_main_project(tmp_path: Path) -> Path:
    """Fake-Hauptrepo: .git als Verzeichnis (kein Worktree)."""
    proj = tmp_path / "project"
    (proj / ".git").mkdir(parents=True)
    (proj / ".claude" / "workflows").mkdir(parents=True)
    return proj


def _write_workflow(proj: Path, name: str, spec_rel: str, affected: list[str]) -> None:
    wf = {
        "name": name,
        "current_phase": "phase6_implement",
        "spec_file": spec_rel,
        "affected_files": affected,
        "red_test_done": True,
    }
    (proj / ".claude" / "workflows" / f"{name}.json").write_text(json.dumps(wf))


def _env(proj: Path, name: str, home: Path) -> dict:
    return {
        "CLAUDE_PROJECT_DIR": str(proj),
        "OPENSPEC_ACTIVE_WORKFLOW": name,
        "HOME": str(home),
    }


# Gültige Spec: sechs echte, lange AC-Deklarationen INNERHALB der Section,
# plus mehrfache kurze AC-Erwähnungen außerhalb (Prosa mit Zeilenumbruch nach
# der AC-Nummer, Tabellenzelle) und ein kurzer Querverweis am Section-Ende.
# Belegdaten aus docs/context/fix-60-69-gate-parsing.md ("durch SMS-, Telegram-
# und", "nie gegen den echten"). Der aktuelle globale Regex findet hier fünf
# <30-Zeichen-Reste und blockt — obwohl keine echte Bullet-Deklaration zu kurz ist.
_VALID_SPEC = """---
entity_id: fix-1275-sms-thunder
type: bugfix
created: 2026-07-15
---

# Fix: SMS Gewitter heute

## Purpose

Der Report zieht Gewitter aus EINER Quelle. Wie in AC-1
durch SMS-, Telegram- und
E-Mail konsistent gemeldet. Frueher wurde in AC-2 und
widerspruechlich gerendert. Der Renderpfad war in AC-2
nie gegen den echten
Renderpfad geprueft.

## Scope

| Metrik | ACs |
|--------|-----|
| Gewitter | AC-1 AC-8 kurz |

## Acceptance Criteria

- **AC-1:** Given eine einzige Gewitterquelle / When der Report rendert / Then stimmen SMS, Telegram und E-Mail ueberein.
- **AC-2:** Given widerspruechliche Quellen frueher / When der Fix aktiv ist / Then zieht alles aus derselben Quelle.
- **AC-3:** Given ein Nutzer mit SMS-Kanal / When Gewitter heute erwartet wird / Then erscheint die Warnung lesbar.
- **AC-4:** Given ein Nutzer mit Telegram / When dasselbe Ereignis gilt / Then ist die Telegram-Meldung identisch.
- **AC-5:** Given der E-Mail-Kanal / When das Briefing erzeugt wird / Then enthaelt die Tabelle den Hinweis.
- **AC-6:** Given der Parser laeuft section-gebunden / When ein Querverweis auftaucht / Then blockt er nicht mehr.

Hinweis: siehe AC-2 und
Folgeschritte im Text.
"""


# --- AC-1: Prosa-/Tabellen-/Querverweis-Erwähnungen blocken nicht (RED heute) ---

def test_prose_and_table_mentions_do_not_block(tmp_path):
    """AC-1 (RED): Gültige Spec mit kurzen AC-Erwähnungen in Prosa/Tabelle/Querverweis.

    Nur echte, zu kurze Bullet-Deklarationen INNERHALB der Section dürften blocken.
    Heute blockt der globale Scan wegen der Prosa-Reste → returncode 2 statt 0.
    """
    proj = _make_main_project(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec = proj / "docs" / "specs" / "fix-1275.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(_VALID_SPEC)
    _write_workflow(proj, "sms-wf", "docs/specs/fix-1275.md", ["src/report.py"])

    result = _run_edit_gate(
        _env(proj, "sms-wf", home), str(proj / "src" / "report.py"), cwd=str(proj)
    )
    assert result.returncode == 0, (
        f"Gültige Spec darf nicht blocken, aber returncode={result.returncode}. "
        f"stderr={result.stderr!r}"
    )


def test_genuinely_short_bullet_still_blocks(tmp_path):
    """AC-1-Gegenprobe (Regressionsschutz, heute schon grün).

    Eine echte Bullet-Deklaration mit < 30 Zeichen Beschreibungstext INNERHALB
    der Section muss weiterhin blocken — vor und nach dem Fix. returncode 2.
    """
    proj = _make_main_project(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec = proj / "docs" / "specs" / "short.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("## Acceptance Criteria\n\n- **AC-1:** short\n")
    _write_workflow(proj, "short-wf", "docs/specs/short.md", ["src/y.py"])

    result = _run_edit_gate(
        _env(proj, "short-wf", home), str(proj / "src" / "y.py"), cwd=str(proj)
    )
    assert result.returncode == 2, (
        f"Zu kurze Bullet-Deklaration muss blocken. stderr={result.stderr!r}"
    )
    assert "too short" in result.stderr.lower()


# --- AC-2: Pfad außerhalb Repo-/Worktree-Wurzel → Check greift nicht (RED heute) ---

def test_path_outside_repo_skips_ac_check(tmp_path):
    """AC-2 (RED): Zielpfad außerhalb des Repos + aktiver Workflow mit unvollständiger Spec.

    Der AC-Check darf für einen Pfad außerhalb von Haupt- und Worktree-Wurzel
    nicht greifen. Heute feuert der Längencheck trotzdem → returncode 2 statt 0.
    """
    proj = _make_main_project(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    spec = proj / "docs" / "specs" / "short.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("## Acceptance Criteria\n\n- **AC-1:** short\n")
    _write_workflow(proj, "oor-wf", "docs/specs/short.md", ["src/y.py"])

    outside = tmp_path / "outside"
    outside.mkdir()
    scratch = outside / "scratch.py"

    result = _run_edit_gate(
        _env(proj, "oor-wf", home), str(scratch), cwd=str(proj)
    )
    assert result.returncode == 0, (
        f"Pfad außerhalb des Repos darf nicht wegen Spec-Inhalt blocken, "
        f"aber returncode={result.returncode}. stderr={result.stderr!r}"
    )


# --- AC-3: Spec nur im Worktree → wird gefunden und geprüft (RED heute) ---

def test_worktree_only_spec_is_checked(tmp_path):
    """AC-3 (RED): Spec existiert NUR im Worktree, nicht im Hauptrepo, kurze AC-Deklaration.

    Der Check muss die Worktree-Spec finden und wegen der zu kurzen Deklaration
    blocken. Heute steigt er aus, weil die Spec unter der Hauptrepo-Wurzel fehlt
    → returncode 0 statt 2.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    main = tmp_path / "main"
    (main / ".git").mkdir(parents=True)
    (main / ".claude" / "workflows").mkdir(parents=True)

    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {main}/.git/worktrees/wt\n")

    # Spec ausschließlich im Worktree, NICHT im Hauptrepo
    specw = wt / "docs" / "specs" / "short.md"
    specw.parent.mkdir(parents=True)
    specw.write_text("## Acceptance Criteria\n\n- **AC-1:** short\n")

    # Workflow-State liegt im Hauptrepo (dort sucht _read_active_workflow)
    _write_workflow(main, "wt-wf", "docs/specs/short.md", ["src/z.py"])

    editfile = wt / "src" / "z.py"
    env = {
        "CLAUDE_PROJECT_DIR": str(wt),
        "OPENSPEC_ACTIVE_WORKFLOW": "wt-wf",
        "HOME": str(home),
    }
    result = _run_edit_gate(env, str(editfile), cwd=str(wt))
    assert result.returncode == 2, (
        f"Worktree-Spec muss gefunden und geprüft werden, aber "
        f"returncode={result.returncode}. stderr={result.stderr!r}"
    )


# --- AC-6: Legacy-Stichtag lässt weiter durch (Regressionsschutz, heute grün) ---

def test_legacy_cutoff_still_passes(tmp_path):
    """AC-6 (Regressionsschutz): Spec-mtime vor ac_format_required_since → durchgelassen.

    Der Legacy-Stichtag-Mechanismus lässt eine Spec ohne valide AC-Section
    unverändert durch, wenn ihre mtime vor dem konfigurierten Stichtag liegt.
    returncode 0 — vor und nach dem Fix identisch.
    """
    proj = _make_main_project(tmp_path)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    # config.yaml mit Stichtag; Spec-mtime davor
    (proj / "config.yaml").write_text(
        "spec_validation:\n  ac_format_required_since: '2030-01-01'\n"
    )
    spec = proj / "docs" / "specs" / "legacy.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# Legacy spec\n\nKeine AC-Section, kein AC-N.\n")
    os.utime(spec, (1600000000, 1600000000))  # 2020-09, vor dem Stichtag
    _write_workflow(proj, "legacy-wf", "docs/specs/legacy.md", ["src/x.py"])

    result = _run_edit_gate(
        _env(proj, "legacy-wf", home), str(proj / "src" / "x.py"), cwd=str(proj)
    )
    assert result.returncode == 0, (
        f"Legacy-Spec vor Stichtag muss durchgelassen werden, aber "
        f"returncode={result.returncode}. stderr={result.stderr!r}"
    )


# --- AC-5: geteilte AC-Erkennung in hook_utils (RED heute — Funktion fehlt) ---

def test_ac_detection_is_shared_from_hook_utils():
    """AC-5 (RED): Beide Konsumenten nutzen dieselbe geteilte Erkennungsfunktion.

    Nach dem Fix existiert die section-gebundene AC-Bullet-Erkennung nur an einer
    Stelle (`hook_utils.extract_ac_entries`), und sowohl `edit_gate` als auch
    `adversary_dialog` referenzieren exakt dieses Objekt. Heute existiert die
    Funktion nicht → AttributeError → Test fällt.
    """
    sys.path.insert(0, str(HOOKS_DIR))
    import hook_utils
    import edit_gate
    import adversary_dialog

    # 1. Geteilte Funktion existiert und ist aufrufbar
    assert hasattr(hook_utils, "extract_ac_entries"), (
        "hook_utils.extract_ac_entries fehlt — geteilte Funktion nicht angelegt."
    )
    assert callable(hook_utils.extract_ac_entries)

    shared = hook_utils.extract_ac_entries

    # 2. Beide Konsumenten referenzieren DASSELBE Objekt (keine eigenen Kopien)
    assert getattr(edit_gate, "extract_ac_entries", None) is shared, (
        "edit_gate referenziert nicht die geteilte hook_utils.extract_ac_entries."
    )
    assert getattr(adversary_dialog, "extract_ac_entries", None) is shared, (
        "adversary_dialog referenziert nicht die geteilte hook_utils.extract_ac_entries."
    )

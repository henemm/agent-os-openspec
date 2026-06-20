---
entity_id: session_singleton_guard
type: feature
created: 2026-06-20
updated: 2026-06-20
status: draft
version: "1.0"
tags: [enforcement, orchestrator, sessions, worktree]
test_targets:
  - core/hooks/session_singleton_guard.py
  - core/hooks/hooks.json
---

# Session Singleton Guard

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** (noch nicht erstellt)

## Purpose

Erkennt wenn mehrere Claude-Instanzen denselben Working Tree teilen und warnt
aktiv. Stärkt das Orchestrator-Prinzip: der Hauptkontext arbeitet im Main-Repo,
Developer Agents arbeiten in isolierten Worktrees.

Ohne diesen Guard läuft eine zweite Claude-Session (z.B. ein Agent, der nicht
in einen Worktree umgeleitet wurde) still im Main-Repo und kann dort Dateien
ändern — Konflikt mit dem Hauptkontext, unkontrollierte `git add`-Effekte,
Workflow-State-Korruption.

Portiert und generalisiert aus `gregor_zwanzig`. Der Original-Code dort ist
bewährt (seit 2025 produktiv).

## Abhängigkeiten

| Komponente | Typ | Abhängigkeit |
|-----------|-----|-------------|
| `session_singleton_guard.py` | neuer Hook | UserPromptSubmit + Stop |
| `hooks.json` | Konfiguration | Registrierung als UserPromptSubmit + Stop Hook |
| `hook_utils.find_project_root()` | Utility | Worktree-transparenter Root |

## Implementierungsdetails

### 1. Mechanismus (aus gregor_zwanzig übernommen, unverändert bewährt)

Jede Session schreibt beim ersten UserPromptSubmit eine Lock-Datei:

```
.claude/session-locks/<PID>.lock
{
  "pid": 12345,
  "started": "2026-06-20T10:00:00"
}
```

Beim nächsten UserPromptSubmit wird die Lock-Directory gescannt:
- Veraltete Locks (Prozess nicht mehr aktiv via `os.kill(pid, 0)`) → gelöscht
- Andere aktive Locks gefunden → **Warning** auf stderr

Bei Session-Ende (Stop Hook): eigene Lock-Datei löschen.

**Fail-open:** Jede Exception → still ignorieren, Exit 0. Der Hook blockiert nie.

### 2. Warning-Text (erweitert gegenüber gregor_zwanzig)

```
WARNING: Andere Claude-Session (PID 12345) ist bereits in diesem Working Tree aktiv.
  Risiko: uncommitted-file Konflikte, Workflow-State-Korruption,
  'git add -A' erfasst fremde Änderungen.
  → Orchestrator-Prinzip: Agents gehören in Worktrees, nicht ins Main-Repo.
  Lösung: EnterWorktree nutzen um diese Session zu isolieren.
```

Der Zusatz "Orchestrator-Prinzip" macht den Kontext explizit — nicht nur
"technisches Problem", sondern Verletzung des Workflow-Musters.

### 3. `session_singleton_guard.py` — vollständige Implementierung

```python
#!/usr/bin/env python3
"""
Session Singleton Guard — Warnt wenn mehrere Claude-Sessions denselben Working Tree teilen.

Stärkt das Orchestrator-Prinzip: Hauptkontext im Main-Repo,
Developer Agents in isolierten Worktrees (EnterWorktree).

Hook type: UserPromptSubmit + Stop (cleanup)
Exit Codes: 0 immer (warnt, blockiert nie)
"""

from hook_utils import setup_path, find_project_root
setup_path()

import json
import os
import sys
from datetime import datetime
from pathlib import Path

_root = find_project_root()

def _lock_dir() -> Path:
    return _root / ".claude" / "session-locks"

def _session_pid() -> int:
    return os.getppid()

def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False

def _cleanup_stale_locks() -> None:
    lock_dir = _lock_dir()
    if not lock_dir.exists():
        return
    for lock_file in lock_dir.glob("*.lock"):
        try:
            pid = int(lock_file.stem)
            if not _is_running(pid):
                lock_file.unlink(missing_ok=True)
        except (ValueError, OSError):
            try:
                lock_file.unlink(missing_ok=True)
            except OSError:
                pass

def check_singleton() -> None:
    lock_dir = _lock_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)
    my_pid = _session_pid()
    my_lock = lock_dir / f"{my_pid}.lock"
    _cleanup_stale_locks()
    for lock_file in lock_dir.glob("*.lock"):
        if lock_file == my_lock:
            continue
        try:
            other_pid = int(lock_file.stem)
            if _is_running(other_pid):
                print(
                    f"WARNING: Andere Claude-Session (PID {other_pid}) ist bereits in "
                    f"diesem Working Tree aktiv.\n"
                    f"  Risiko: uncommitted-file Konflikte, Workflow-State-Korruption.\n"
                    f"  Orchestrator-Prinzip: Agents gehören in Worktrees, nicht ins Main-Repo.\n"
                    f"  Lösung: EnterWorktree nutzen um diese Session zu isolieren.",
                    file=sys.stderr,
                )
        except (ValueError, OSError):
            pass
    try:
        my_lock.write_text(json.dumps({
            "pid": my_pid,
            "started": datetime.now().isoformat(),
        }))
    except OSError:
        pass

def cleanup() -> None:
    my_pid = _session_pid()
    my_lock = _lock_dir() / f"{my_pid}.lock"
    try:
        my_lock.unlink(missing_ok=True)
    except OSError:
        pass

def main():
    if "--cleanup" in sys.argv:
        cleanup()
    else:
        check_singleton()
    sys.exit(0)

if __name__ == "__main__":
    main()
```

### 4. `hooks.json` — Registrierung

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/session_singleton_guard.py\""
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/session_singleton_guard.py\" --cleanup"
        }]
      }
    ]
  }
}
```

Stop Hook ist neu — bisher hatte das Framework keine Stop-Hooks. Er muss in
`setup.py` in die `generate_settings_json`-Funktion eingefügt werden.

### 5. `.gitignore` — Lock-Verzeichnis ausschließen

```
.claude/session-locks/
```

Lock-Dateien sind rein lokal, dürfen nie committed werden.

### 6. Was dieser Guard NICHT tut (bewusste Entscheidung)

- **Blockiert nicht** — nur Warning. Der Hauptkontext bleibt in der Lage,
  in Notfällen direkt zu agieren (Agent-Ausfall, Recovery)
- **Unterscheidet nicht** zwischen Hauptkontext und Agent — erkennt nur
  "zwei Sessions, gleicher Tree"
- **Erzwingt EnterWorktree nicht** — zeigt nur den Weg

Die eigentliche Code-Writing-Prävention des Hauptkontexts liegt in CLAUDE.md
("Orchestrator schreibt keinen Code") + `worktree_write_guard.py` (blockiert
Agenten die aus Worktrees ins Main-Repo schreiben wollen).

## Expected Behavior

- **Session A startet** → Lock `<PID_A>.lock` erstellt, keine Warning (allein)
- **Session B startet im selben Tree** → Lock von A gefunden, aktiver Prozess → Warning
- **Session A endet** → Lock von A gelöscht (Stop Hook)
- **Session A crasht** → Lock von A bleibt, aber `_is_running(PID_A)` → False → wird bei nächstem Check als stale gelöscht
- **Worktree-Session** → `find_project_root()` gibt Main-Repo zurück; Lock landet dort → Guard greift auch bei Worktree-Sessions korrekt

## Error Handling

- Lock-Dir nicht erstellbar → silent fail, Exit 0
- Lock-Datei nicht schreibbar → silent fail, Exit 0
- `os.kill` wirft unerwartete Exception → catch-all, nicht als "running" werten
- Stop Hook schlägt fehl → silent fail (Session ist sowieso beendet)

## Known Limitations

- PID-basiert: Bei PID-Reuse (sehr selten) könnte eine abgelaufene Session
  fälschlicherweise als aktiv erkannt werden. Praktisch vernachlässigbar.
- Warning erscheint nur bei `UserPromptSubmit` — nicht sofort beim Start,
  sondern erst bei erster User-Eingabe in der neuen Session.
- Warnt auch wenn zwei Tabs desselben Users gleichzeitig offen sind
  (harmlos, aber verwirrend). Lösung: `sessions`-Allowlist in config — not in scope.

## Acceptance Criteria

- **AC-1:** Given eine Session aktiv (Lock existiert) / When zweite Session startet und User Prompt schickt / Then Warning auf stderr mit PID der ersten Session
- **AC-2:** Given Session endet (Stop Hook) / When Stop Hook läuft / Then Lock-Datei der Session gelöscht
- **AC-3:** Given Lock-Datei mit PID eines nicht mehr laufenden Prozesses / When Session startet / Then stale Lock wird gelöscht, keine false-positive Warning
- **AC-4:** Given Session in Worktree / When UserPromptSubmit / Then Lock landet im Main-Repo (nicht im Worktree)
- **AC-5:** Given Lock-Dir nicht beschreibbar / When UserPromptSubmit / Then Exit 0 (fail-open, kein Crash)

## Test Plan

```bash
# AC-1: Zwei Sessions simulieren
mkdir -p .claude/session-locks
echo '{"pid": 99999999, "started": "2026-06-20T10:00:00"}' \
  > .claude/session-locks/99999999.lock
# PID 99999999 existiert nicht → wird als stale erkannt

# Echten aktiven PID nutzen:
echo '{"pid": '$$', "started": "2026-06-20T10:00:00"}' \
  > .claude/session-locks/$$.lock
echo '{}' | python3 core/hooks/session_singleton_guard.py
# → Warning auf stderr (eigene PID als "andere" Session)

# AC-2: Stop Hook
python3 core/hooks/session_singleton_guard.py --cleanup
ls .claude/session-locks/  # → eigene Lock-Datei weg

# AC-3: Stale Lock
echo '{"pid": 99999999}' > .claude/session-locks/99999999.lock
echo '{}' | python3 core/hooks/session_singleton_guard.py
ls .claude/session-locks/99999999.lock  # → nicht mehr vorhanden
```

## Changelog

- 2026-06-20: Initial spec erstellt (portiert und generalisiert aus gregor_zwanzig)

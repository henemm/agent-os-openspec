---
entity_id: session_singleton_guard
type: feature
created: 2026-06-20
updated: 2026-08-21
status: draft
version: "2.0"
tags: [enforcement, orchestrator, sessions, worktree, diagnostics]
test_targets:
  - core/hooks/session_singleton_guard.py
  - core/hooks/hooks.json
  - tests/test_session_singleton_guard.py
---

# Session Singleton Guard

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #106 (letzte Erweiterung: Session-Register)

## Purpose

Erzwingt die Worktree-Pflicht (seit v3.4.10): **jede** Session muss in einem eigenen
`.claude/worktrees/<name>/` arbeiten. Schreibende Tools im Haupt-Repo werden blockiert,
lesende Tools bleiben immer erlaubt (sonst waere der Notausgang `EnterWorktree` nicht mehr
ladbar).

Zusaetzlich fuehrt der Hook das einzige projekteigene **Register aktiver Sessions** unter
`.claude/session-locks/`. Es dient der Diagnostik und der Abfrage durch andere
Claude-Sessions (`workflow.py sessions`).

## Abhaengigkeiten

| Komponente | Typ | Abhaengigkeit |
|-----------|-----|-------------|
| `session_singleton_guard.py` | Hook | SessionStart + PreToolUse (alle Tools) + SessionEnd |
| `hooks.json` | Konfiguration | Registrierung der drei Modi |
| `hook_utils.find_project_root()` | Utility | Worktree-transparenter Root (Lock-Dir, Workflow-State) |
| `hook_utils.resolve_active_workflow()` | Utility | Aktiver Workflow-Name (worktree-aware) |
| `override_token.has_valid_token()` | Utility | Notausgang im Guard |
| `~/.claude/sessions/*.json` | externes, undokumentiertes Harness-Internal | liefert ausschliesslich `agent_name` |

## Implementierungsdetails

### 1. Drei Modi (argv[1])

| Modus | Event | Aufgabe |
|-------|-------|---------|
| `register` | SessionStart | Registereintrag anlegen/erneuern (`started_at` bleibt erhalten), tote Eintraege reapen |
| `guard` | PreToolUse (alle Tools) | Heartbeat schreiben; schreibende Tools im Haupt-Repo blockieren |
| `cleanup` | SessionEnd | Eigenen Eintrag loeschen |

### 2. Registerformat

Eine Datei pro Session: `.claude/session-locks/<session_id>.json` (Dateiname per
`_safe_sid()` slugified). Das frueher dokumentierte Format `<PID>.lock` existiert nicht mehr.

```json
{
  "session_id": "05cd60a0-7c59-4eff-8764-c4f606a64f05",
  "cwd": "/repo/.claude/worktrees/intake-106",
  "pid": 12345,
  "started_at": 1787287937.880,
  "last_seen": 1787288512.114,

  "agent_name": "agent-os-openspec-9a",
  "worktree": "intake-106",
  "branch": "feat-106-session-register",
  "workflow": "feat-106-session-register",
  "issue": "106",
  "phase": "phase6_implement"
}
```

- **Pflichtfelder:** `session_id`, `cwd`, `pid`, `started_at`, `last_seen`.
- **Optionale Felder:** `agent_name`, `worktree`, `branch`, `workflow`, `issue`, `phase`.
  Ein fehlendes optionales Feld ist kein Fehlerzustand — die Quelle hat im Moment des
  Schreibens nichts geliefert (kein aktiver Workflow, kein Harness-Treffer, kein lesbarer
  Branch).

### 3. Reihenfolge in `_do_guard`

1. Session/`cwd`-Check (fehlt eines → fail-safe allow)
2. **Throttled Heartbeat** (`_heartbeat`) — laeuft fuer JEDES Tool, auch lesende, und
   **vor** jedem Ausstiegspfad
3. Tool-Filter-Ausstieg (`tool_name not in _BLOCKING_TOOLS` → allow)
4. Worktree-Ausstieg (`_is_worktree_cwd(cwd)` → allow)
5. Rescue-Ausstieg (`EnterWorktree` → allow)
6. Override-Token-Ausstieg → allow
7. Block-Text auf stderr + `exit(2)`

Der Heartbeat stand frueher an Position 7 und wurde damit von Worktree-Sessions (also
seit v3.4.10 von praktisch allen) und von rein lesenden Sessions nie erreicht: `cwd` blieb
auf dem Stand des SessionStart eingefroren, und Dauerlaeufer wurden nach `_STALE_SECONDS`
faelschlich weggeraeumt, weil die gespeicherte `pid` die laengst beendete Hook-Shell ist.

### 4. Throttled Heartbeat (`_heartbeat`)

- Existiert keine eigene Lock-Datei → No-op. **Der Guard legt niemals Eintraege an** —
  das tut ausschliesslich `register`.
- Gelesen wird der Eintrag immer, danach zwei unabhaengige Entscheidungen:
  - **`agent_name` fehlt** → `_harness_agent_name(session_id)`, unabhaengig vom Throttle,
    aber nur solange `now - started_at < _AGENT_NAME_LOOKUP_WINDOW_SECONDS` (60s). Ist
    `agent_name` gesetzt, wird der Lookup gar nicht erst aufgerufen.
  - **Restliche Felder** (`last_seen`, `cwd`, `worktree`, `branch`, `workflow`, `phase`,
    `issue`) nur wenn `now - last_seen >= _HEARTBEAT_THROTTLE_SECONDS` (Default 60,
    ueberschreibbar per `OPENSPEC_HEARTBEAT_THROTTLE`).
  - Beide Zweige teilen sich **einen** Schreibvorgang — hoechstens ein Datei-Write pro
    Guard-Aufruf.
- Der gesamte Ablauf ist in `try/except Exception: pass` gekapselt.

### 5. Helferfunktionen

| Funktion | Ergebnis |
|----------|----------|
| `_extract_worktree(cwd)` | Capture-Group aus `/\.claude/worktrees/([^/]+)` oder `None` |
| `_read_branch(cwd)` | Branch aus `.git/HEAD` bzw. `gitdir:`-Datei im Worktree; **kein Subprozess**; Detached HEAD → `None` |
| `_extract_issue_number(name)` | erste Ziffernfolge im Workflow-Namen (`feat-106-…` → `"106"`) oder `None` |
| `_read_workflow_phase(name)` | `current_phase` aus `.claude/workflows/<name>.json` oder `None` |
| `_harness_agent_name(sid)` | `name` aus der `~/.claude/sessions/*.json`-Datei mit passender `sessionId`, sonst `None` |
| `_context_fields(cwd)` | Sammelt `worktree`/`branch`/`workflow`/`issue`/`phase`; nur erfolgreich ermittelte Felder |

Jeder Helfer faengt seine Fehler selbst ab und degradiert auf `None` — der Guard bleibt
subprozessfrei und fail-safe.

### 6. Liveness / Reaping

`_is_alive` prueft zuerst die PID (`/proc/<pid>`), faellt aber auf `last_seen` zurueck:
Hooks laufen in einer transienten Shell, deren PID unmittelbar nach dem Hook tot ist.
Ohne diesen Fallback wuerde jede lebende Session beim ersten PreToolUse weggeraeumt.
`_STALE_SECONDS` (Default 900, `OPENSPEC_SESSION_STALE`) definiert die Verfallsgrenze.

### 7. Lesepfad: `workflow.py sessions`

`python3 core/hooks/workflow.py sessions [--json]` liest ausschliesslich
`.claude/session-locks/*.json` des eigenen Projekts. Default ist eine Tabelle (fehlende
optionale Felder als `–`), `--json` liefert dieselben Eintraege als JSON-Array.
`workflow.py` bleibt damit frei von Harness-Wissen — es gibt genau einen Schreiber
(`session_singleton_guard.py`) und ein Register.

### 8. `.gitignore`

`.claude/session-locks/` ist rein lokal und darf nie committed werden.

## Expected Behavior

- **Session startet** (`register`) → Eintrag mit Pflichtfeldern, dazu alle im Moment
  ermittelbaren optionalen Felder; `started_at` einer vorhandenen Datei bleibt erhalten.
- **Beliebiges Tool** (`guard`) → Heartbeat laeuft; `last_seen` und Kontextfelder werden
  hoechstens alle 60s aktualisiert, `agent_name` wird sofort nachgezogen, sobald der
  Harness ihn liefert (erste Session-Minute).
- **Schreibendes Tool im Haupt-Repo** → Block mit Exit 2 und Aufforderung, `EnterWorktree`
  aufzurufen.
- **Lesendes Tool / Worktree-Session / EnterWorktree / gueltiger Override-Token** → allow.
- **Session endet** (`cleanup`) → eigener Eintrag geloescht.
- **Dauerlaeufer** (tote Shell-PID, `started_at` weit ueber `_STALE_SECONDS`) → bleibt
  erhalten, solange der Heartbeat laeuft.

## Error Handling

- Jede unerwartete Exception in `main()` → `exit(0)` (fail-safe allow, nie faelschlich blocken).
- Jede neue Datenquelle zusaetzlich einzeln gekapselt: Harness-Lookup, Branch-Lesen,
  Workflow-/Phasen-Aufloesung, Heartbeat insgesamt.
- Kaputte Einzeldatei im Harness-Verzeichnis bricht den Scan nicht ab.
- Aendert sich das Harness-Format oder verschwindet das Verzeichnis, fehlt lediglich
  `agent_name` — alle anderen Felder und die Guard-Logik arbeiten unveraendert weiter.

## Architektur-Notiz: Warum kein `fcntl.flock()`

`flock()` setzt einen dauerhaften Prozess voraus, der den File-Descriptor offen haelt.
Hooks sind kurzlebige Subprozesse — der Lock waere beim Hook-Exit sofort wieder frei.
Deshalb Datei-Register plus `last_seen`-Heartbeat statt Kernel-Lock.

## Architektur-Notiz: Eigenes Register bleibt Wahrheit

Das Harness-Register (`~/.claude/sessions/*.json`) wird **ausschliesslich** fuer
`agent_name` gelesen. Alle uebrigen Felder stammen aus dem Guard-Payload bzw. dem
Projekt-State. Begruendung: nur `agent_name` existiert nirgends sonst; jede weitere
Abhaengigkeit wuerde ein undokumentiertes Internal in den sicherheitskritischen
Reaping-Pfad und in den PreToolUse-Hot-Path ziehen. Ausfuehrliche Abwaegung:
`docs/specs/feat-106-session-register.md`, Abschnitt „Design-Entscheidung".

## Known Limitations

- Die gespeicherte `pid` ist `os.getppid()` (transiente Hook-Shell), kompensiert durch den
  `last_seen`-Fallback in `_is_alive`.
- `~/.claude/sessions/` ist ein undokumentiertes Harness-Internal (beobachtet: `2.1.238`).
- `agent_name` kann im Fenster zwischen `register` und dem ersten `guard`-Aufruf fehlen
  (der Harness schreibt seinen Eintrag ca. 29 ms spaeter). Liefert der Harness den Namen in
  der ersten Session-Minute nicht, bleibt das Feld dauerhaft leer — bewusster Zeitdeckel
  gegen Dauer-Scans im Hot-Path.
- Innerhalb des 60s-Throttle-Fensters koennen `cwd`, `worktree`, `branch`, `workflow`,
  `phase`, `issue` bis zu 60s hinter dem tatsaechlichen Zustand zurueckliegen.
- Detached-HEAD-Worktrees liefern kein `branch`-Feld.
- `workflow.py sessions` zeigt nur Sessions des eigenen Projekts, keine serverweite Uebersicht.

## Acceptance Criteria

- **AC-1:** Schreibendes Tool (`Edit`/`Write`/`MultiEdit`/`Bash`/`Task`/`Agent`) im
  Haupt-Repo → Exit 2 mit Hinweis auf `EnterWorktree`.
- **AC-2:** Lesendes Tool im Haupt-Repo, Tool im Worktree, `EnterWorktree`, gueltiger
  Override-Token → Exit 0.
- **AC-3:** `register` legt einen Eintrag mit allen Pflichtfeldern an und erhaelt ein
  bestehendes `started_at`.
- **AC-4:** Jeder `guard`-Aufruf (auch lesendes Tool, auch im Worktree) aktualisiert
  `last_seen` — sofern das Throttle-Fenster abgelaufen ist.
- **AC-5:** Zwei `guard`-Aufrufe innerhalb des Throttle-Fensters → die Lock-Datei wird
  kein zweites Mal geschrieben.
- **AC-6:** `guard` ohne vorhandene Lock-Datei legt keine an und wirft keinen Fehler.
- **AC-7:** Eintrag mit toter PID und frischem `last_seen` ueberlebt `_reap_dead`; mit
  toter PID und stale `last_seen` wird er entfernt.
- **AC-8:** Fehlendes/kaputtes/leeres Harness-Verzeichnis → kein Crash, lediglich
  `agent_name` fehlt.
- **AC-9:** `workflow.py sessions` gibt eine Tabelle mit Platzhaltern fuer fehlende Felder
  aus, `--json` eine vollstaendig `json.loads()`-parsebare Ausgabe.

## Test Plan

Automatisiert: `python3 -m pytest tests/test_session_singleton_guard.py tests/test_workflow_sessions.py -q`

Manuell:

```bash
# Register-Eintrag ansehen
python3 core/hooks/workflow.py sessions
python3 core/hooks/workflow.py sessions --json
```

## Changelog

- 2026-06-20: Initial spec erstellt (portiert und generalisiert aus gregor_zwanzig)
- 2026-08-21: Neufassung auf den Ist-Stand — Worktree-Pflicht statt Warn-Modus,
  Registerformat `<session_id>.json` statt `<PID>.lock`, throttled Heartbeat vor allen
  Ausstiegspfaden, neue Felder `agent_name`/`worktree`/`branch`/`workflow`/`issue`/`phase`,
  Lesepfad `workflow.py sessions` (Issue #106)

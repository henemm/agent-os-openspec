---
entity_id: feat-106-session-register
type: feature
created: 2026-08-21
updated: 2026-08-21
status: draft
workflow: feat-106-session-register
version: "1.0"
tags: [feature, bugfix, hooks, session-singleton-guard, workflow-py, diagnostics]
test_targets:
  - core/hooks/session_singleton_guard.py
  - core/hooks/workflow.py
  - tests/test_session_singleton_guard.py
  - tests/test_workflow_sessions.py
---

# Feature #106: Session-Register erweitern (agent_name, cwd/branch/worktree, issue/phase, Dauerläufer-Fix)

## Approval

- [ ] Approved

## GitHub Issue

- **Issue:** #106 — Session-Register liefert keinen lesbaren Namen, ein eingefrorenes `cwd` und
  verliert Dauerläufer-Sessions nach 15 Minuten.

## Purpose

`session_singleton_guard.py` pflegt in `.claude/session-locks/<session_id>.json` das einzige
projekteigene Register aktiver Claude-Sessions. Heute ist der Eintrag nach dem initialen
`register` faktisch eingefroren (`cwd` bleibt auf dem Hauptverzeichnis stehen, `last_seen` wird in
Worktree-Sessions nie mehr geschrieben) und enthält keinen für Menschen lesbaren Namen. Diese Spec
behebt den zugrunde liegenden Heartbeat-Bug (AC-2, AC-4 des Issues) und reichert den Eintrag
additiv um `agent_name`, `branch`, `worktree`, `issue`, `phase` und `workflow` an (AC-1, AC-3), samt
einem neuen Lesepfad `workflow.py sessions`.

## Source

- **File:** `core/hooks/session_singleton_guard.py`
- **Identifier:** `_do_register()`, `_do_guard()` (Root Cause: Heartbeat-Block hinter dem
  Worktree-Ausstieg, Zeilen 227–246 im Ist-Zustand)
- **Zweite Datei:** `core/hooks/workflow.py` — neues Kommando `cmd_sessions()` / `sessions`

## Root Cause (Bug-Anteil: AC-2, AC-4)

In `_do_guard()` steht der `last_seen`-Heartbeat **hinter** dem Worktree-Ausstieg
(`if _is_worktree_cwd(cwd): sys.exit(0)`) und zusätzlich hinter dem
Nicht-Blockierendes-Tool-Ausstieg (`if tool_name not in _BLOCKING_TOOLS: sys.exit(0)`). Da seit
v3.4.10 alle Sessions im Worktree laufen müssen, erreicht praktisch keine Session mehr den
Heartbeat-Block:

- **Eingefrorenes `cwd` (AC-2):** Der Eintrag wird nach dem initialen `register` (der noch vor
  `EnterWorktree` läuft und daher das Hauptverzeichnis speichert) nie wieder angefasst.
- **Verlorene Dauerläufer (AC-4):** Die gespeicherte `pid` ist `os.getppid()` — die transiente
  Hook-Shell, die Sekunden nach dem Hook-Aufruf beendet ist. Ohne laufenden Heartbeat verfällt
  jede Session nach `_STALE_SECONDS` (900s), unabhängig davon, ob sie noch aktiv ist. Eine
  Session, die nur liest (Read/Grep/Glob — nicht in `_BLOCKING_TOOLS`), erreicht den
  Heartbeat-Block heute **niemals**, selbst wenn er vor den Worktree-Ausstieg gezogen würde, aber
  hinter dem Tool-Filter bliebe.

## Design-Entscheidung: Eigenes Register bleibt Wahrheit (Option A)

Abgewogen wurden zwei Architekturen:

- **(A, gewählt):** Das eigene Register (`.claude/session-locks/`) bleibt alleinige Wahrheit und
  wird additiv angereichert. Das Harness-Register (`~/.claude/sessions/*.json`) wird ausschliesslich
  für das Feld `agent_name` gelesen — in `_do_register` (SessionStart) sowie ergänzend im
  `guard`-Pfad, dort jedoch nur solange `agent_name` im eigenen Eintrag noch fehlt. Sobald das
  Feld einmal gesetzt ist, scannt kein weiterer `guard`-Aufruf mehr (siehe EB-3 und den Abschnitt
  „Race Condition beim `agent_name`-Lookup" unten).
- **(B, verworfen):** Das Harness-Register wird Wahrheit für Liveness/Name/`cwd`; das eigene
  Register führt nur noch die Projektebene (Issue, Branch, Workflow, Phase).

**Begründung:** Eine Feld-für-Feld-Prüfung zeigt, dass nur ein einziges Feld überhaupt
Harness-Daten braucht (`agent_name` — der Name wird ausschliesslich vom Harness vergeben,
`nameSource: "derived"`, und existiert nirgends sonst). `cwd`/`worktree` liegen live in jedem
Guard-Payload vor, `issue`/`phase`/`workflow` löst `hook_utils.resolve_active_workflow()` plus der
Workflow-State bereits vollständig auf, und die Dauerläufer-Regression ist ein reiner
Root-Cause-Fix am eigenen Heartbeat. Option B würde die Abhängigkeit vom undokumentierten
Harness-Internal (Version `2.1.238`, kein öffentliches Format) unnötig in den
sicherheitskritischen Reaping-Pfad ziehen und zusätzlich bei **jedem** Guard-Aufruf dauerhaft
einen Verzeichnis-Scan erzwingen — nicht nur bis zum ersten Treffer wie bei diesem Fix, sondern
für die gesamte Session-Laufzeit. Ein PreToolUse-Hot-Path, der bei jedem Tool-Aufruf in sechs
Server-Instanzen feuert. Verifiziert: `_owner_sid()` ist im Ist-Zustand toter Code (`grep -rn
'_owner_sid' core/ tests/` liefert nur die Definition) — es gibt heute keinen Konsumenten, der
Liveness/Ownership aus dem Register ableitet; alles, was #106 fordert, ist reine Diagnostik.

### Race Condition beim `agent_name`-Lookup (Nachtrag)

Empirisch belegt an einer laufenden Session:

```
Lock  started_at : 1787287937.880
Harness startedAt: 1787287937.909   (Delta +0.029s)
Harness nameSince: 1787287937.909   (name entsteht GENAU in diesem Moment)
```

Die eigene Lock-Datei wird ca. 29ms **vor** dem Harness-`startedAt` geschrieben — zum Zeitpunkt
von `_do_register` existiert `~/.claude/sessions/<pid>.json` also womöglich noch gar nicht, und
`nameSince == startedAt` zeigt, dass der Name exakt dann erst vergeben wird. Ein Lookup, der
ausschliesslich in `_do_register` stattfindet, würde `agent_name` daher in der Praxis regelmässig
leer lassen — und zwar dauerhaft für die ganze Session, weil nie wieder nachgeschlagen wird.

**Korrektur — Lazy-Nachführung:** Der Lookup läuft in `_do_register` und zusätzlich im
`guard`-Heartbeat-Pfad, dort aber ausschliesslich solange `agent_name` im eigenen Eintrag noch
fehlt — unabhängig vom sonstigen 60s-Throttle des Heartbeats, damit der Name nicht erst nach einer
vollen Throttle-Periode erscheint. Sobald das Feld gesetzt ist, unterbleibt jeder weitere Scan.

**Zeitdeckel gegen Dauer-Scan:** Die Bedingung „solange `agent_name` fehlt" allein genügt nicht.
Liefert der Harness den Namen **nie** — etwa weil sich sein Format geändert hat, exakt der von
EB-4 eingeplante Fall — dann wäre die Bedingung dauerhaft erfüllt und der Guard würde bei jedem
Tool-Aufruf über die gesamte Session-Laufzeit ins Leere scannen. Genau das, was EB-3 verhindern
soll. Der Lookup läuft deshalb nur, wenn **beide** Bedingungen gelten: `agent_name` fehlt **und**
`now - started_at < 60`. Begründung für die Schwelle: Der Harness schreibt seinen Eintrag
innerhalb von Millisekunden nach dem SessionStart (gemessen: +29 ms); ist der Name nach einer
Minute nicht da, kommt er nicht mehr. Kein zusätzliches Feld, keine Zustandsverwaltung.

Kosten: höchstens eine kleine, begrenzte Anzahl zusätzlicher Scans pro Session (praktisch meist
genau einer, beim ersten `guard`-Aufruf nach `register`), hart begrenzt auf die erste
Session-Minute. Die Absicht von EB-3 (kein Scan bei jedem Tool-Aufruf über die gesamte
Session-Laufzeit) bleibt damit unter allen Umständen gewahrt — auch im Fehlerfall.

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| `hook_utils.resolve_active_workflow()` | function | Löst den aktiven Workflow-Namen auf (worktree-aware, Priorität Datei > Settings > Env) |
| `hook_utils.find_project_root()` | function | Lock-Verzeichnis + Workflow-State-Pfad, worktree-transparent |
| `~/.claude/sessions/<pid>.json` (Harness) | externes, undokumentiertes Internal | Liefert `agent_name` via `sessionId`-Match; gelesen in `_do_register` sowie lazy im `guard`-Pfad, solange `agent_name` im eigenen Eintrag fehlt |
| `.claude/workflows/<name>.json` | Projekt-State-Datei | Liefert `current_phase` für den aktiven Workflow |
| `.git`-Datei/-Verzeichnis + `HEAD` (reines Dateilesen) | Filesystem | Branch-Ermittlung, kein Subprozess |
| `override_token.has_valid_token()` | function | Unverändert, weiterhin Notausgang im Guard |

## Scope

### Affected Files

| File | Change Type | Description | Risiko |
|------|-------------|--------------|--------|
| `core/hooks/session_singleton_guard.py` | MODIFY | Heartbeat-Block vor den Worktree-/Tool-Filter-Ausstieg ziehen und throtteln (60s); `cwd`/`worktree`/`branch`/`workflow`/`phase`/`issue` bei jedem übers Throttle laufenden Heartbeat nachführen; neue Helfer `_extract_worktree`, `_read_branch`, `_extract_issue_number`, `_read_workflow_phase`, `_harness_agent_name`; `_do_register` reichert zusätzlich um `agent_name` an; `guard` ergänzt `agent_name` zusätzlich lazy nach, solange das Feld im eigenen Eintrag fehlt (Race-Condition-Fix, siehe Design-Entscheidung) | **HOCH** — PreToolUse-Hot-Path, serverweit in 6 Instanzen aktiv |
| `core/hooks/workflow.py` | MODIFY | Neues Kommando `sessions` (+ `COMMANDS`-Eintrag `cmd_sessions`): liest `.claude/session-locks/*.json` des eigenen Projekts, Tabellenausgabe nach Repo-Konvention, zusätzlich `--json` | NIEDRIG (rein additiv, kein bestehender Codepfad geändert) |
| `tests/test_session_singleton_guard.py` | MODIFY | Neue Tests für Heartbeat-vor-Worktree-Ausstieg, Throttle, Dauerläufer-Regression, Harness-Erfolgsfall, Harness-Fail-Safe-Varianten, Issue/Phase-Ableitung, lazy `agent_name`-Nachführung im Guard; bestehende 19 Tests bleiben unverändert | NIEDRIG |
| `tests/test_workflow_sessions.py` | CREATE | Neue Testdatei für `workflow.py sessions` gegen ein Fixture-Lock-Verzeichnis (Tabellen- und `--json`-Ausgabe) | NIEDRIG |
| `docs/specs/session-singleton-guard.md` | MODIFY | Neufassung der bestehenden Modul-Spec — beschreibt heute noch ein veraltetes Dateiformat (`<PID>.lock` statt `<session_id>.json`) und keinen der neuen Felder | KEINS funktional, aber irreführend falls nicht nachgezogen |

`core/hooks/hook_utils.py` bleibt unverändert — die Issue-Regex und der Harness-Zugriff liegen
lokal in `session_singleton_guard.py`, damit der Utils-Layer frei von Harness-Wissen bleibt.

### Estimated Changes

- Files: 5 (4 MODIFY, 1 CREATE)
- LoC: +300/-20 (Schätzung; Analyse nennt eine Bandbreite von 250–400 LoC, konzentriert auf
  `session_singleton_guard.py` und die zugehörigen Tests)

## Implementation Details

### 1. Neue Felder im Registereintrag (alle additiv, alle optional ausser den fünf Bestandsfeldern)

Bestehend (unverändert Pflicht): `session_id`, `cwd`, `pid`, `started_at`, `last_seen`
Neu (optional, additiv): `agent_name`, `branch`, `worktree`, `issue`, `phase`, `workflow`

Ein fehlendes optionales Feld ist kein Fehlerzustand — es bedeutet lediglich, dass die jeweilige
Quelle im Moment des Schreibens nichts geliefert hat (kein aktiver Workflow, kein Harness-Treffer,
kein lesbarer Branch).

### 2. Guard-Reihenfolge (`_do_guard`)

Die heutige Reihenfolge lautet: Session/cwd-Check → Tool-Filter-Ausstieg → Worktree-Ausstieg →
Rescue-Ausstieg → Override-Ausstieg → Heartbeat → Block. Neu:

1. Session/cwd-Check (Fail-Safe, unverändert)
2. **Throttled Heartbeat-Update inkl. lazy `agent_name`-Nachführung** (neu, vorgezogen — feuert
   für JEDES Tool, auch lesende; Details siehe Schritt 3)
3. Tool-Filter-Ausstieg (unverändert)
4. Worktree-Ausstieg (unverändert)
5. Rescue-Ausstieg (unverändert)
6. Override-Ausstieg (unverändert)
7. Block-Ausgabe + `exit(2)` (unverändert)

Der Heartbeat-Schritt läuft also für jede Session bei jedem Tool-Aufruf, **bevor** irgendein
Ausstiegspfad greift — das schliesst die Lücke, dass rein lesende Sessions (Read/Grep/Glob) den
Heartbeat nie erreichten.

### 3. Throttled Heartbeat-Update (mit unabhängiger lazy `agent_name`-Nachführung)

Neue interne Konstante `_HEARTBEAT_THROTTLE_SECONDS` (Default 60, überschreibbar per
`OPENSPEC_HEARTBEAT_THROTTLE`, analog zu `_STALE_SECONDS`). Ablauf, vollständig in
`try/except Exception: pass` gekapselt:

- Eigene Lock-Datei existiert nicht → No-op, kein Schreiben, kein Fehler (Guard schreibt niemals
  Einträge neu an — nur `register` legt an).
- Eigene Lock-Datei existiert: gelesen wird sie in jedem Fall (billige Operation), danach zwei
  **unabhängige** Entscheidungen:
  - **`agent_name` fehlt im Eintrag** → `_harness_agent_name(session_id)` wird aufgerufen,
    unabhängig vom 60s-Throttle. Liefert der Lookup einen Wert, wird `agent_name` gesetzt und die
    Datei geschrieben — auch wenn der allgemeine Throttle sonst blocken würde. Ist `agent_name`
    bereits gesetzt, wird `_harness_agent_name` gar nicht erst aufgerufen (Hot-Path-Schutz).
  - **Restliche Felder** (`last_seen`, `cwd`, `worktree`, `branch`, `workflow`, `phase`, `issue`)
    unterliegen weiterhin dem 60s-Throttle: nur wenn `now - last_seen >= 60` (oder `last_seen`
    fehlt/ungültig), werden sie neu ermittelt und geschrieben.
  - Beide Zweige teilen sich denselben Schreibvorgang, falls mindestens einer greift — es gibt
    also höchstens einen Datei-Write pro Guard-Aufruf, nicht zwei.

Innerhalb des Throttle-Fensters bleiben `cwd`/`worktree`/`branch`/`workflow`/`phase`/`issue` auf
dem Stand des letzten erfolgreichen Heartbeats — bewusster Trade-off gegen unnötige I/O-Last bei
sehr tool-intensiven Sessions. `agent_name` ist von diesem Trade-off bewusst ausgenommen, da die
Race Condition sonst dazu führen würde, dass der Name bis zu 60s (oder bei sehr kurzen Sessions
nie) sichtbar wird.

### 4. `_do_register` — zusätzliche Anreicherung

`_do_register` baut den Eintrag wie bisher (`session_id`, `cwd`, `pid`, `started_at`,
`last_seen`) und ergänzt zusätzlich, jeweils nur bei erfolgreicher Ermittlung:

- `worktree` per `_extract_worktree(cwd)`
- `branch` per `_read_branch(cwd)`
- `agent_name` per `_harness_agent_name(session_id)` — **erster** Aufrufort des
  Harness-Lookups; wegen der Race Condition (siehe oben) schlägt dieser erste Versuch häufig fehl
  und wird dann vom `guard`-Pfad lazy nachgeholt (Schritt 3)
- `workflow`/`phase`/`issue` per `resolve_active_workflow()` + Workflow-State, dieselbe Logik wie
  im Heartbeat (Schritt 5), aber ungethrottelt (Register läuft ohnehin nur einmal pro
  SessionStart)

### 5. Neue Helferfunktionen (alle lokal in `session_singleton_guard.py`)

- `_extract_worktree(cwd) -> str | None` — Regex `r"/\.claude/worktrees/([^/]+)"` auf `cwd`,
  liefert die Capture-Group oder `None`.
- `_read_branch(cwd) -> str | None` — reines Dateilesen, kein Subprozess: Ist `<cwd>/.git` eine
  Datei (Worktree), wird die Zeile `gitdir: <pfad>` geparst und `<pfad>/HEAD` gelesen. Ist
  `<cwd>/.git` ein Verzeichnis (Haupt-Repo), wird `<cwd>/.git/HEAD` direkt gelesen. In beiden
  Fällen wird aus `ref: refs/heads/<branch>` der Branchname extrahiert; jede Abweichung (Detached
  HEAD, fehlende Datei, kaputtes Format) liefert `None`. Vollständig `try/except Exception: return
  None`.
- `_extract_issue_number(workflow_name) -> str | None` — Regex-Suche nach der ersten
  Ziffernfolge im Workflow-Namen (z.B. `feat-106-session-register` → `"106"`); kein Treffer →
  `None`.
- `_read_workflow_phase(workflow_name) -> str | None` — liest
  `{find_project_root()}/.claude/workflows/{name}.json` und gibt `current_phase` zurück;
  jeder Fehler (Datei fehlt, kaputtes JSON, fehlendes Feld) → `None`.
- `_harness_agent_name(session_id) -> str | None` — iteriert `~/.claude/sessions/*.json`, matched
  über `.get("sessionId") == session_id`, liefert `.get("name")`. Kompletter Funktionskörper in
  `try/except Exception: return None`; fehlendes Verzeichnis, kaputte Einzeldatei oder fehlendes
  Feld degradieren auf `None`, ohne den Scan der übrigen Dateien abzubrechen. Nur `.get()`-Zugriffe,
  keine Versionsprüfung des Harness-Formats — degradiert bei jedem Formatwandel automatisch.
  Aufgerufen von `_do_register` (immer, ein Versuch) und vom `guard`-Pfad (nur solange
  `agent_name` im eigenen Eintrag noch fehlt — danach nie wieder für diese Session).

Alle fünf Helfer werden sowohl von `_do_register` als auch (inkl. `_harness_agent_name`, siehe
oben) vom throttled Heartbeat in `_do_guard` verwendet — eine geteilte Ermittlungslogik, zwei
Aufrufstellen.

### 6. `workflow.py sessions` — Lesepfad

Neues Kommando, registriert im `COMMANDS`-Dict analog zu `retro-list`/`list`. Implementierung
folgt dem bestehenden Repo-Muster (`SEP = "─" * N`, f-string-Spalten, siehe `cmd_retro_list`):

- Liest ausschliesslich `.claude/session-locks/*.json` unter `find_project_root()` — **nicht**
  `~/.claude/sessions/`, da `agent_name` zu diesem Zeitpunkt bereits im eigenen Register steht
  (ein Schreiber, ein Register; `workflow.py` bleibt frei von Harness-Wissen).
- Default-Ausgabe: Tabelle mit Session-Kennung, `agent_name`, `worktree`, `branch`, `workflow`,
  `phase`, `issue`, Alter von `last_seen`; fehlende optionale Felder werden als `–` dargestellt.
- Zusatz-Flag `--json`: gibt dieselben Einträge als JSON-Array maschinenlesbar aus. Neu für dieses
  Repo (bisher kennt kein Kommando `--json`), begründet dadurch, dass der Zweck des Tickets die
  Abfrage durch andere Claude-Sessions ist — ein stabiles, parsebares Format verhindert
  Tabellen-Scraping.
- Reichweite: nur Sessions des eigenen Projekts, ergibt sich automatisch aus
  `find_project_root()`; kein zusätzlicher Filter nötig.
- Ohne vorhandenes Lock-Verzeichnis oder ohne Einträge: druckt einen Hinweistext, keine leere
  Tabelle, kein Fehler (Stil wie `cmd_retro_list` bei leerem Archiv).

## Expected Behavior

- **EB-1 (Fail-Safe):** Kein neuer Pfad darf eine Exception nach aussen werfen — jede neue Quelle
  (Harness-Lookup, Branch-Lesen, Workflow-/Phasen-Auflösung) ist einzeln try/except-gekapselt,
  zusätzlich zum äusseren `except Exception: sys.exit(0)`-Fangnetz in `main()`.
- **EB-2 (Subprozessfrei):** Der Guard bleibt vollständig subprozessfrei; Branch-Ermittlung
  geschieht ausschliesslich durch Dateilesen.
- **EB-3 (Harness-Scan begrenzt, kein Dauer-Scan):** Der Verzeichnis-Scan von
  `~/.claude/sessions/*.json` läuft in `_do_register` (SessionStart) sowie zusätzlich im
  `guard`-Heartbeat-Pfad — dort aber ausschliesslich solange `agent_name` im eigenen
  Registereintrag noch fehlt UND `now - started_at < 60` gilt. Sobald das Feld einmal gesetzt ist
  — oder die erste Session-Minute verstrichen ist — findet bei folgenden `guard`-Aufrufen für
  diese Session kein weiterer Scan mehr statt. Der Zeitdeckel ist notwendig, weil ein dauerhaft
  erfolgloser Lookup (EB-4: Harness-Format geändert) sonst zum Dauer-Scan im Hot-Path würde.
- **EB-4 (Stilles Degradieren):** Bricht das Harness-Format oder verschwindet das Verzeichnis,
  fehlt lediglich `agent_name` — alle anderen Felder und die Guard-Logik funktionieren unverändert.

## Known Limitations

- Die gespeicherte `pid` bleibt `os.getppid()` (transiente Hook-Shell), weiterhin kompensiert
  durch den bestehenden `last_seen`-Fallback in `_is_alive`. Kein Ersatz durch die echte
  Claude-PID aus dem Harness — das würde eine Harness-Abhängigkeit in den sicherheitskritischen
  Reaping-Pfad ziehen. Eigenes Folge-Ticket.
- `~/.claude/sessions/` ist ein undokumentiertes Harness-Internal (beobachtete Version
  `2.1.238`). Ändert sich das Format, entfällt `agent_name` ersatzlos, ohne dass eine Session
  blockiert oder ein Test bricht.
- **`agent_name` kann im Zeitfenster zwischen SessionStart (`register`) und dem ersten
  nachfolgenden `guard`-Aufruf fehlen.** Der Harness schreibt seinen eigenen Registereintrag
  (inkl. `name`) nachweislich einige Millisekunden nach dem eigenen `register`-Aufruf (empirisch
  belegt: `nameSince == startedAt`, ca. 29ms nach dem eigenen `started_at`). Bleibt eine Session
  zwischen `register` und dem ersten `guard`-Aufruf ungewöhnlich lange ohne jeden Tool-Aufruf,
  bleibt `agent_name` bis zum ersten `guard`-Aufruf danach leer.
- `workflow.py sessions` zeigt nur Sessions des eigenen Projekts — keine serverweite Übersicht
  über alle sechs Instanzen dieses Servers.
- Detached-HEAD-Worktrees (kein `ref: refs/heads/...` in der `HEAD`-Datei) liefern kein
  `branch`-Feld; OpenSpec-Worktrees arbeiten nach Konvention immer auf einem Branch, daher ausserhalb
  des Scopes.
- Innerhalb des 60-Sekunden-Throttle-Fensters können `cwd`, `worktree`, `branch`, `workflow`,
  `phase`, `issue` bis zu 60s hinter dem tatsächlichen Zustand zurückliegen (z.B. unmittelbar nach
  einem Phasenwechsel). `agent_name` ist von diesem Fenster ausgenommen (siehe oben).

## Test Plan

### Automated Tests (TDD RED)

Datei `tests/test_session_singleton_guard.py` (Ergänzung, 19 Bestandstests bleiben unverändert):

- [ ] **Test 1 — Heartbeat im Worktree wird aktualisiert:** GIVEN ein vorhandener Lock-Eintrag mit
  `last_seen` vor mehr als 60s, WHEN `_do_guard` mit `tool_name="Edit"` und einem
  `WORKTREE_CWD` aufgerufen wird, THEN ist `last_seen` im gespeicherten Eintrag danach `>=` dem
  Aufrufzeitpunkt (heute: unverändert, weil der Worktree-Ausstieg vorher greift — Test muss gegen
  den Ist-Code fehlschlagen).
- [ ] **Test 2 — Heartbeat feuert bei lesenden Tools:** GIVEN ein vorhandener Lock-Eintrag mit
  `last_seen` vor mehr als 60s, WHEN `_do_guard` mit `tool_name="Read"` und `WORKTREE_CWD`
  aufgerufen wird, THEN ist `last_seen` aktualisiert (heute: unverändert, weil der
  Tool-Filter-Ausstieg vorher greift).
- [ ] **Test 3 — Throttle blockiert Schreiben:** GIVEN ein vorhandener Lock-Eintrag mit
  `last_seen` vor 10 Sekunden (und bereits gesetztem `agent_name`), WHEN `_do_guard` erneut
  aufgerufen wird, THEN bleibt `last_seen` (und der gesamte Dateiinhalt) unverändert.
- [ ] **Test 4 — cwd wird nachgeführt:** GIVEN ein Lock-Eintrag mit `cwd` auf dem Hauptverzeichnis
  und `last_seen` vor mehr als 60s, WHEN `_do_guard` mit `cwd=WORKTREE_CWD` aufgerufen wird, THEN
  steht im gespeicherten Eintrag `cwd == WORKTREE_CWD` und `worktree` enthält den Worktree-Namen.
- [ ] **Test 5 — Dauerläufer-Regression (AC-4-Kernbeweis):** GIVEN ein Lock-Eintrag mit
  `started_at` vor mehr als `_STALE_SECONDS`, toter `pid`, `last_seen` initial ebenfalls stale,
  WHEN dazwischen ein `_do_guard`-Aufruf mit frischem Payload stattfindet, THEN entfernt ein
  anschliessender `_reap_dead`-Lauf diesen Eintrag NICHT (weil `last_seen` durch den Heartbeat
  aktualisiert wurde).
- [ ] **Test 6 — issue/phase werden nachgeführt:** GIVEN ein aktiver Workflow
  `feat-106-session-register` mit `current_phase="phase3_spec"` auflösbar über
  `resolve_active_workflow()`, WHEN der Heartbeat übers Throttle läuft, THEN enthält der Eintrag
  `workflow="feat-106-session-register"`, `issue="106"`, `phase="phase3_spec"`.
- [ ] **Test 7 — Harness-Lookup Erfolgsfall (AC-1-Kernbeweis):** GIVEN eine Datei in
  `~/.claude/sessions/` mit passender `sessionId` und `name="agent-os-openspec-9a"`, WHEN
  `_do_register` mit dieser `session_id` aufgerufen wird, THEN steht im geschriebenen
  Lock-Eintrag `agent_name == "agent-os-openspec-9a"` — exakt dieser Wert.
- [ ] **Test 8 — Harness-Lookup: fehlendes Verzeichnis:** GIVEN `~/.claude/sessions/` existiert
  nicht, WHEN `_harness_agent_name(session_id)` aufgerufen wird, THEN liefert es `None`, keine
  Exception.
- [ ] **Test 9 — Harness-Lookup: kaputte JSON-Datei:** GIVEN eine Datei mit ungültigem JSON im
  Sessions-Verzeichnis, WHEN `_harness_agent_name` aufgerufen wird, THEN `None`, keine Exception,
  andere Dateien werden weiter durchsucht.
- [ ] **Test 10 — Harness-Lookup: fehlendes Feld:** GIVEN eine Datei mit `sessionId`, aber ohne
  `name`, WHEN `_harness_agent_name` mit passender `session_id` aufgerufen wird, THEN `None`.
- [ ] **Test 11 — Harness-Lookup: kein Treffer:** GIVEN mehrere Dateien, keine mit passender
  `sessionId`, WHEN `_harness_agent_name` aufgerufen wird, THEN `None`.
- [ ] **Test 12 — `_do_register` übersteht kaputten Harness-Lookup vollständig:** GIVEN
  `_harness_agent_name` wirft (gemockt) eine Exception, WHEN `_do_register` aufgerufen wird, THEN
  schliesst es normal ab (`sys.exit(0)`) und schreibt `session_id`/`cwd`/`pid`/`started_at`/
  `last_seen` unverändert; `agent_name` fehlt im Eintrag.
- [ ] **Test 13 — Workflow-Name ohne Ziffer:** GIVEN aktiver Workflow `retro-cleanup`, WHEN
  `_extract_issue_number("retro-cleanup")` aufgerufen wird, THEN `None`; der Heartbeat schreibt
  `workflow`, aber kein `issue`-Feld.
- [ ] **Test 14 — Kein aktiver Workflow:** GIVEN `resolve_active_workflow()` liefert `("",
  "none")`, WHEN der Heartbeat läuft, THEN fehlen `workflow`/`phase`/`issue` im Eintrag, kein
  Crash.
- [ ] **Test 15 — Fehlende Lock-Datei bei Guard-Aufruf:** GIVEN kein Lock-Eintrag für die
  `session_id` existiert, WHEN `_do_guard` aufgerufen wird, THEN wird keine Datei angelegt, kein
  Fehler, das bisherige Allow/Block-Verhalten bleibt unverändert.
- [ ] **Test 16 — Regression, alle 19 Bestandstests:** GIVEN der vollständige Bestandslauf, WHEN
  die Datei nach der Änderung ausgeführt wird, THEN sind alle 19 ursprünglichen Tests weiterhin
  grün, ohne Anpassung.
- [ ] **Test 17 — Lazy `agent_name`-Nachführung im Guard (AC-15, Richtung 1):** GIVEN ein
  Lock-Eintrag ohne `agent_name` und eine Harness-Datei mit passender `sessionId` und
  `name="agent-os-openspec-9a"`, dabei `started_at` innerhalb der letzten 60s (sonst greift der
  Zeitdeckel aus AC-16), WHEN `_do_guard` aufgerufen wird (unabhängig vom 60s-Throttle, z.B.
  `last_seen` erst vor 5s), THEN enthält der gespeicherte Eintrag danach
  `agent_name == "agent-os-openspec-9a"`.
- [ ] **Test 18 — Kein Scan wenn `agent_name` bereits gesetzt (AC-15, Richtung 2,
  Hot-Path-Schutz):** GIVEN ein Lock-Eintrag mit bereits gesetztem `agent_name`, WHEN `_do_guard`
  aufgerufen wird und `_harness_agent_name` per Monkeypatch/Spy überwacht wird, THEN wird
  `_harness_agent_name` NICHT aufgerufen.
- [ ] **Test 18b — Zeitdeckel stoppt den Lookup (AC-16):** GIVEN ein Lock-Eintrag ohne
  `agent_name` und `started_at` vor 120 Sekunden, WHEN `_do_guard` aufgerufen wird und
  `_harness_agent_name` per Monkeypatch/Spy überwacht wird, THEN wird `_harness_agent_name`
  NICHT aufgerufen — auch nicht, wenn eine passende Harness-Datei vorhanden wäre.

Neue Datei `tests/test_workflow_sessions.py`:

- [ ] **Test 19 — Tabellenausgabe:** GIVEN ein Fixture-Lock-Verzeichnis mit zwei Einträgen (einer
  mit allen neuen Feldern, einer ohne), WHEN `cmd_sessions([])` aufgerufen wird, THEN enthält die
  Ausgabe beide Session-Kennungen und für den unvollständigen Eintrag Platzhalter statt eines
  Fehlers.
- [ ] **Test 20 — JSON-Ausgabe:** GIVEN dasselbe Fixture-Verzeichnis, WHEN `cmd_sessions(["--json"])`
  aufgerufen wird, THEN ist die komplette stdout-Ausgabe mit `json.loads()` parsebar und enthält
  pro Eintrag mindestens `session_id`.
- [ ] **Test 21 — Leeres Verzeichnis:** GIVEN kein Lock-Verzeichnis oder keine Einträge, WHEN
  `cmd_sessions([])` aufgerufen wird, THEN wird ein Hinweistext ausgegeben, kein Fehler, keine
  leere Tabelle.

## Acceptance Criteria

- **AC-1:** Sobald der Harness-Name für die eigene `session_id` in `~/.claude/sessions/*.json`
  (Feld `sessionId`, Feld `name`) verfügbar ist, trägt der eigene Registereintrag `agent_name` mit
  exakt diesem Wert — nicht zwingend bereits beim allerersten `register` (Race Condition, siehe
  Design-Entscheidung), spätestens aber ab dem ersten `guard`-Aufruf danach, bei dem `agent_name`
  im Eintrag noch fehlt.
- **AC-2:** Vorhandener Registereintrag mit `cwd` auf dem Hauptverzeichnis, `last_seen` älter als
  60s → ein `guard`-Aufruf mit `cwd` auf einem Worktree-Pfad überschreibt `cwd` im Eintrag auf den
  aktuellen Wert und ergänzt `worktree` mit dem Worktree-Namen.
- **AC-3:** Gleiches Szenario wie AC-2, aktiver Workflow via `resolve_active_workflow()` auflösbar
  → der Eintrag enthält danach `workflow` (Name), `phase` (`current_phase` aus dem Workflow-State)
  und `issue` (per Regex aus dem Workflownamen extrahierte erste Ziffernfolge).
- **AC-4:** Ein Registereintrag mit `started_at` vor mehr als `_STALE_SECONDS`, toter `pid`, aber
  `last_seen` durch mindestens einen zwischenzeitlichen `guard`-Aufruf aktualisiert (< 60s alt) →
  ein anschliessender `_reap_dead`-Lauf entfernt diesen Eintrag NICHT.
- **AC-5:** `guard` wird mit einem nicht-blockierenden Tool (z.B. `Read`) in einer
  Worktree-Session aufgerufen, vorhandener Eintrag mit `last_seen` älter als 60s → `last_seen`
  wird trotzdem aktualisiert (Regressionsschutz gegen den heutigen Code, der Read/Grep/Glob nie
  bis zum Heartbeat-Block durchlässt).
- **AC-6:** Zwei `guard`-Aufrufe für dieselbe Session innerhalb von 60 Sekunden → beim zweiten
  Aufruf bleiben `last_seen` und alle anderen Felder unverändert, die Lock-Datei wird nicht neu
  geschrieben.
- **AC-7:** `~/.claude/sessions/` existiert nicht, ODER eine enthaltene JSON-Datei ist
  syntaktisch ungültig, ODER `sessionId`/`name` fehlt in einer Datei, ODER kein Eintrag matcht die
  gesuchte `session_id` → in keinem der vier Fälle bricht `register` mit einer Exception ab; der
  geschriebene Eintrag enthält dann einfach kein `agent_name`.
- **AC-8:** Selbst wenn der komplette Harness-Lookup eine unerwartete Exception wirft, schliesst
  `_do_register` normal ab (`sys.exit(0)`) und schreibt `session_id`, `cwd`, `pid`, `started_at`,
  `last_seen` unverändert zum bisherigen Verhalten.
- **AC-9:** Aktiver Workflow-Name ohne Ziffer (z.B. `retro-cleanup`) → der Eintrag enthält
  `workflow`, aber kein `issue`-Feld; kein Crash.
- **AC-10:** Kein aktiver Workflow auflösbar (`resolve_active_workflow()` liefert `("", "none")`)
  → `workflow`, `phase`, `issue` fehlen im Eintrag; kein Crash.
- **AC-11:** `guard` wird für eine `session_id` aufgerufen, für die keine Lock-Datei existiert →
  es wird keine Datei angelegt, kein Fehler geworfen, das bisherige Allow/Block-Verhalten
  (abhängig von `cwd`) bleibt unverändert.
- **AC-12:** `python3 core/hooks/workflow.py sessions` (ohne Argumente) gibt eine Tabelle aller
  Einträge unter `.claude/session-locks/*.json` des eigenen Projekts aus, inklusive der neuen
  Felder mit einem Platzhalter für fehlende Werte.
- **AC-13:** `python3 core/hooks/workflow.py sessions --json` gibt eine Ausgabe zurück, die
  vollständig mit `json.loads()` parsebar ist und pro Eintrag mindestens `session_id` enthält.
- **AC-14:** Alle 19 bestehenden Tests in `tests/test_session_singleton_guard.py` laufen nach der
  Änderung unverändert grün — keine bestehende Testzeile wird angepasst.
- **AC-15:** Registereintrag ohne `agent_name`, Harness-Datei mit passender `sessionId` und
  vorhandenem `name` existiert → ein `guard`-Aufruf ergänzt `agent_name` im Eintrag mit diesem
  Wert, unabhängig vom 60s-Throttle der übrigen Felder. Gegenprobe: Ist `agent_name` im Eintrag
  bereits gesetzt, findet bei einem weiteren `guard`-Aufruf KEIN Harness-Verzeichnis-Scan mehr
  statt (Hot-Path-Schutz, nachweisbar per Monkeypatch/Spy auf `_harness_agent_name` — die
  Funktion wird dann nicht aufgerufen).
- **AC-16:** Registereintrag ohne `agent_name`, `started_at` älter als 60 Sekunden → ein
  `guard`-Aufruf löst KEINEN Verzeichnis-Scan von `~/.claude/sessions/` mehr aus (per
  Monkeypatch/Spy auf die Lookup-Funktion prüfbar). Schützt den Hot-Path in dem Fall, in dem der
  Harness den Namen dauerhaft nicht liefert (EB-4).

## Architektur-Entscheidung (ADR)

- **ADR-Nr.:** keine
- **Rationale:** Dieses Repo führt kein separates ADR-Log; die Architektur-Entscheidung ist
  vollständig im Abschnitt „Design-Entscheidung" oben dokumentiert (Option A — eigenes Register
  bleibt Wahrheit, Harness nur für `agent_name`, inklusive der nachträglichen Korrektur zur
  Race-Condition-bedingten Lazy-Nachführung — vs. Option B, verworfen) und in
  `docs/context/feat-106-session-register.md` (Analyse-Teil) mit einer Feld-für-Feld-Abwägung
  gegen Option B belegt. Eine eigenständige ADR-Datei würde denselben Inhalt duplizieren, ohne
  zusätzlichen Erkenntniswert.

## Changelog

- 2026-08-21: Initial spec created
- 2026-08-21: Race Condition beim `agent_name`-Lookup korrigiert (lazy Nachführung im
  Guard-Pfad, AC-1 präzisiert, AC-15 ergänzt, EB-3 neu formuliert); Harness-Erfolgsfall-Test
  ergänzt (Test 7); ADR-Rationale verweist jetzt explizit auf den Design-Entscheidung-Abschnitt

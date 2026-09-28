# Phase 7: Validation

You are in **Phase 7 - Validation**.

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/60-validate #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree:

```bash
ISSUE=42   # die übergebene Nummer (ohne #)
python3 - "$ISSUE" <<'PY'
import sys, json, glob, re, os
issue = sys.argv[1].lstrip('#')
pat = re.compile(rf'(^|[-_]){re.escape(issue)}([-_]|$)')
hits = []
for f in glob.glob('.claude/workflows/*.json'):
    name = os.path.basename(f)[:-5]
    if pat.search(name):
        d = json.load(open(f))
        hits.append((name, d.get('current_phase'), d.get('spec_file') or 'Not created', d.get('adversary_verdict'), d.get('affected_files', [])))
if not hits:
    print(f'KEIN laufender Workflow fuer #{issue} (evtl. abgeschlossen -> .claude/workflows/_archive/).')
else:
    for name, ph, spec, verd, aff in hits:
        print(f'GEFUNDEN: {name} | Phase={ph} | Spec={spec} | Verdict={verd}')
        if aff: print(f'  affected_files: {", ".join(aff)}')
    print('\nNAME=' + hits[0][0])
PY
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58):

```bash
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Verdict. Fasse dem User in 2 Sätzen den Stand zusammen (Phase, Verdict) und fahre dann mit den Prerequisites fort.

### Hängende Subagenten

Primärer Schutz gegen einen hängenden Subagenten: Die Sitzung wird automatisch erneut aufgerufen,
sobald der Hintergrund-Agent fertig ist. Liegt beim nächsten eigenen Zug noch kein Bericht vor,
`TaskList` prüfen — ist der Agent dort noch als aktiv gelistet, ihn mit `TaskStop` beenden und
mit präziserem Briefing neu starten. Kein endloses Warten.

Nur falls dieser Befehl innerhalb eines `/loop`-Laufs (Selbsttaktung, dynamischer Modus) läuft,
zusätzlich dieser Rückfall:

```
ScheduleWakeup(1200, "Validierung Rückfall [60-validate], nur im /loop-Kontext: TaskList → noch aktiver Kontext-/Validierungs-/Auto-Fix-/Docs-Updater-Agent? JA → TaskStop, dann User: 'Agent hängt — bitte /60-validate neu starten.' NEIN → ignorieren, fertig.")
```

### Kontext laden (nur bei Wiedereinstieg nach `/clear`)

Bevor du mit den Prerequisites fortfährst, lade den vollständigen Validierungs-Kontext — damit die nachfolgenden Agenten konkrete Werte statt Platzhalter erhalten.

Dispatche einen **Explore/Haiku Subagenten**:

```
Task (Explore/haiku, run_in_background: true): "Lies folgende Ressourcen und extrahiere die konkreten Werte:
  1. [spec_file aus dem Wiedereinstieg-Block oben] → Acceptance Criteria (AC-1 bis AC-N)
  2. docs/artifacts/<workflow-name>/adversary-dialog.md → Adversary-Verdict und Findings
  3. openspec.yaml (Feld test_command) → konkreter Test-Befehl

  Gib zurück:
  - spec_file_path: [konkreter Pfad, bereits aus Wiedereinstieg bekannt]
  - affected_files: [bereits aus Wiedereinstieg bekannt]
  - test_command: [konkreter Befehl]
  - Acceptance Criteria: [Liste aller AC-N]
  - adversary_verdict: [VERIFIED / BROKEN / AMBIGUOUS]"
```

Ersetze alle `[...]`-Platzhalter in Step 1 und Step 3 mit den geladenen Werten — kein Agent darf mit Platzhaltern gestartet werden.

## Prerequisites

- Implementation complete (`phase6_implement`)
- All tests passing (GREEN artifacts registered)
- **Adversary Dialog verified** (`phase6b_adversary` passed, `adversary_verdict` set)

Check status:
```bash
python3 .claude/hooks/workflow.py status
```

### Adversary Dialog Prerequisite

**Du MUSST pruefen, dass der Adversary Dialog valid ist, bevor du fortfaehrst:**

```bash
python3 .claude/hooks/adversary_dialog.py validate docs/artifacts/<workflow-name>/adversary-dialog.md
```

Wenn die Validierung fehlschlaegt: Zurueck zu `/50-implement` Step 8 (Adversary Dialog wiederholen).
Akzeptierte Verdicts: **VERIFIED** oder **AMBIGUOUS** (mit User-OK).

**Gate-Wirkung (#253):** Commit-Gate und Phase 8 (`phase phase8_complete`, `complete`, `finish`)
akzeptieren das Verdict nur mit diesem registrierten (bzw. am Standardpfad liegenden), gestempelten
Artefakt, dessen gehashte Dateien zum aktuellen Code passen. Ein gruener Testlauf aktualisiert nur
`last_test_run` — er setzt kein Verdict. Aendert der Auto-Fix aus Step 2b eine im Dialog zitierte
Datei (`Code reference:`), blockt Phase 8, bis ein neuer Dialog gefuehrt, gestempelt und registriert
ist (`/50-implement` Step 8).

## Your Tasks

### Step 1: Parallele Validierung (4x Haiku)

Dispatche **4 parallele Haiku-Agenten** fuer umfassende Validierung:

```
Task 1 (general-purpose/haiku, run_in_background: true) - TEST CHECK:
  "Fuehre ALLE Tests aus: [test_command]
  Report: Anzahl passed/failed, Laufzeit, Fehlerdetails."

Task 2 (general-purpose/haiku, run_in_background: true) - SPEC COMPLIANCE:
  "Lies die Spec: [spec_file_path]
  Pruefe jeden Acceptance Criterion gegen die Implementation.
  Report: Welche Kriterien sind erfuellt, welche nicht?"

Task 3 (general-purpose/haiku, run_in_background: true) - REGRESSION CHECK:
  "Fuehre die vollstaendige Test-Suite aus (nicht nur Feature-Tests).
  Report: Gibt es Regressionen? Welche Tests die vorher gruen waren
  sind jetzt rot?"

Task 4 (general-purpose/haiku, run_in_background: true) - SCOPE CHECK:
  "Vergleiche die geaenderten Dateien mit der Spec.
  Wurden Dateien ausserhalb des Specs geaendert?
  Wurden mehr als 5 Dateien / 250 LoC geaendert?"
```

### Step 2: Ergebnis-Auswertung

Werte die 4 Reports aus:

**Step 2a: Alle Checks bestanden**
-> Weiter zu Step 3

**Step 2b: Fehler gefunden -> Auto-Fix (general-purpose/Sonnet)**

Bei Fehlern dispatche einen **general-purpose/Sonnet Subagenten**:

```
Task (general-purpose/sonnet, run_in_background: true): "Folgende Validierungsfehler wurden gefunden:
  [Fehler-Liste aus den 4 Haiku-Reports]

  Behebe die Fehler. Beachte:
  - Nur die gemeldeten Fehler fixen, keine anderen Aenderungen
  - Scoping Limits einhalten
  - Tests nach dem Fix erneut ausfuehren"
```

Nach dem Fix: Dispatche die relevanten Haiku-Checks erneut zur Verifikation.

### Step 3: Dokumentation aktualisieren (docs-updater/Sonnet)

Bei erfolgreicher Validierung dispatche den **docs-updater**:

```
Task (general-purpose/sonnet, run_in_background: true): "Du bist der docs-updater Agent.

  Input:
  - changed_files: [Liste der geaenderten Dateien]
  - feature_summary: [Kurzbeschreibung]
  - spec_file_path: [Pfad zur Spec — NUR LESEN, kein Bearbeitungsziel]

  Aktualisiere alle betroffene Dokumentation.

  Die Spec-Datei selbst NICHT bearbeiten — sie ist nach der Freigabe eingefroren
  (#230): kein Status-Feld setzen, keine AC-Checkboxen abhaken."
```

**Warum `spec_file_path` nur Lesekontext ist (#230):** Das PO-Briefing ist per SHA-256 an
die gelesene Spec-Fassung gebunden. Fasst der docs-updater die Spec an, verschiebt sich der
Hash und Step 4 (`phase phase8_complete`) bricht mit „PO-Briefing ist veraltet" ab. Deshalb
gilt: Die Spec ist nach Freigabe eingefroren und darf nicht mehr bearbeitet werden —
`edit_gate.py` (Schritt 1d) blockiert solche Schreibzugriffe technisch. Eine wirklich
gewollte Nachbesserung braucht das Wort „override" vom User.

### Step 4: Workflow State aktualisieren

```bash
python3 .claude/hooks/workflow.py phase phase8_complete
```

## Validation Report

Erstelle eine Zusammenfassung:

```markdown
## Validation Report: [Workflow Name]

### Test Results
- Unit Tests: [N] passed, [N] failed
- Integration Tests: [N] passed, [N] failed
- Full Suite: [N] total, [N] passed

### Spec Compliance
- Acceptance Criteria: [N]/[N] erfuellt
- [Details zu nicht-erfuellten Kriterien]

### Regression Check
- Status: [Keine Regressionen / N Regressionen]

### Scope Check
- Files changed: [N] (Limit: 5)
- LoC changed: +[N]/-[N] (Limit: 250)
- Out-of-scope changes: [Keine / Liste]

### Result: PASS / FAIL
```

## Next Step

### Autonomen Weiterlauf prüfen (PFLICHT, vor der Ausgabe)

Existiert im Projekt ein `/70-deploy` (eigene `.claude/commands/70-deploy.md` oder Skill) UND
dokumentiert das Projekt selbst — in dessen `CLAUDE.md` oder direkt in `70-deploy.md` —
explizit, dass Deploy **ohne Freigabe-Halt autonom** läuft (Formulierungen wie "läuft
autonom", "kein Freigabe-Halt", "ohne manuelle Ausführung")? Dann ist das bindende
Projekt-Policy — nicht erneut zur Diskussion stellen und nicht darauf warten, dass der
User `/70-deploy` selbst eintippt. Das gilt auch dann, wenn "eigentlich" an dieser Stelle
generell auf eine Bestätigung gewartet wird: eine explizite Projekt-Policy sticht die
Default-Ceremony dieses Commands. Committe wie unten beschrieben und rufe danach
`/70-deploy` **im selben Turn selbst auf** — melde dem User das Ergebnis der ganzen Kette,
nicht einen Zwischenstand, der auf seine Eingabe wartet.

Fehlt eine solche explizite Projekt-Policy: Standardverhalten unten (fragen, nicht
autonom weiterlaufen) — Autonomie ist ein Opt-in des Projekts, kein Default des Frameworks.

### Beobachtbare Oberfläche prüfen (PFLICHT, vor der Ausgabe)

Diese Prüfung ersetzt die Autonomie-Prüfung oben nicht, sie tritt daneben. Führe sie aus —
**keine eigene Einschätzung von dir ersetzt den Aufruf**, auch dann nicht, wenn du sicher zu
wissen glaubst, dass nur Hooks oder Tests geändert wurden:

```bash
python3 .claude/hooks/workflow.py observable-surface
```

Die Auskunft endet immer mit Rückgabecode 0 und nennt in fünf Zeilen Urteil (`OBSERVABLE_SURFACE=`),
Begründung, Anzahl geprüfter Dateien, Messwurzel und Config-Quelle.

Fehlt in dieser Ausgabe die Zeile `OBSERVABLE_SURFACE=no` — aus welchem Grund auch immer, also
auch bei `OBSERVABLE_SURFACE=yes`, bei einem Absturz, bei abweichendem Format oder wenn der
Aufruf ganz ausgeblieben ist —, dann gilt das als „Oberfläche vorhanden" und die Schlussfrage
„Soll ich den Code committen?" wird gestellt. Nur die ausdrücklich gelesene Zeile
`OBSERVABLE_SURFACE=no` lässt sie entfallen.

Daraus ergeben sich vier Kombinationen — die Autonomie-Regel sticht, die neue Prüfung wirkt in
genau einer Zeile:

| Oberfläche | Autonomie dokumentiert | Schlusszeile |
|---|---|---|
| `yes` | nein | Frage „Soll ich den Code committen?" — unverändert wie bisher |
| `yes` | ja | Ankündigung: schreibe fest und deploye, Kette im selben Turn |
| `no` | nein | Ankündigung: schreibe jetzt fest, keine Rückfrage |
| `no` | ja | Ankündigung: schreibe fest und deploye, Kette im selben Turn |

### Zusammenfassung an den User

Nach erfolgreicher Validierung, gib dem User folgende Zusammenfassung:

---
✅ **Alles fertig und geprüft.**

**Was wurde umgesetzt:** [Feature/Bugfix in 1–2 Sätzen aus Nutzerperspektive]

**Ergebnis:**
- Alle Qualitätsprüfungen bestanden
- Alle Anforderungen aus dem Plan erfüllt
- Keine bestehenden Funktionen beeinträchtigt

**Bereit für:** Commit[, dann Deploy — falls im Projekt vorgesehen]

Soll ich den Code committen?

---

**Ausnahme bei dokumentierter Autonomie (siehe Prüfung oben):** Ersetze die letzte Zeile
durch die kurze Ankündigung, dass jetzt committet und automatisch weiterdeployt wird —
keine Frage, keine Wartezeile wie "Warte auf /70-deploy". Führe die Kette im selben Turn
aus und melde danach das Endergebnis.

**Ausnahme ohne beobachtbare Oberfläche (siehe Prüfung oben):** Liegt die Zeile
`OBSERVABLE_SURFACE=no` vor und ist keine Autonomie dokumentiert, ersetze die letzte Zeile
durch die kurze Ankündigung, dass du den Code jetzt festschreibst. Es gibt in diesem Fall
nichts, was der User beurteilen könnte — eine Rückfrage wäre inhaltsleer.

## On Failure

If validation fails after auto-fix attempt:
1. Do NOT update state to complete
2. Report the remaining issues to the user
3. User decides: fix manually or re-implement

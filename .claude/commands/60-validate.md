<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->
---
description: "Validate the implementation"
disable-model-invocation: true
---

# Phase 7: Validation

You are in **Phase 7 - Validation**.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

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
$WF switch <NAME-aus-obigem-Output>
$WF status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Verdict. Fasse dem User in 2 Sätzen den Stand zusammen (Phase, Verdict) und fahre dann mit den Prerequisites fort.

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

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(180, "Kontext-Agent Timeout [60-validate Wiedereinstieg]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Kontext-Agent nach 3 Min gestoppt — bitte /60-validate neu starten.' NEIN → ignorieren, fertig.")
```

Ersetze alle `[...]`-Platzhalter in Step 1 und Step 3 mit den geladenen Werten — kein Agent darf mit Platzhaltern gestartet werden.

## Prerequisites

- Implementation complete (`phase6_implement`)
- All tests passing (GREEN artifacts registered)
- **Adversary Dialog verified** (`phase6b_adversary` passed, `adversary_verdict` set)

Check status:
```bash
$WF status
```

### Adversary Dialog Prerequisite

**Du MUSST pruefen, dass der Adversary Dialog valid ist, bevor du fortfaehrst:**

```bash
python3 ${_H}/adversary_dialog.py validate docs/artifacts/<workflow-name>/adversary-dialog.md
```

Wenn die Validierung fehlschlaegt: Zurueck zu `/50-implement` Step 8 (Adversary Dialog wiederholen).
Akzeptierte Verdicts: **VERIFIED** oder **AMBIGUOUS** (mit User-OK).

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

**TIMEOUT-PFLICHT — sofort nach dem Spawn (für alle 4 gemeinsam):**
```
ScheduleWakeup(300, "Validierungs-Agents Timeout [60-validate Step 1]: TaskList → noch aktive Haiku-Agents? JA → alle TaskStop, dann User: 'Validierungs-Agents nach 5 Min gestoppt — bitte /60-validate neu starten.' NEIN → ignorieren, fertig.")
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

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(300, "Auto-Fix Timeout [60-validate Step 2b]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Auto-Fix-Agent nach 5 Min gestoppt — bitte manuell prüfen.' NEIN → ignorieren, fertig.")
```

Nach dem Fix: Dispatche die relevanten Haiku-Checks erneut zur Verifikation.

### Step 3: Dokumentation aktualisieren (docs-updater/Sonnet)

Bei erfolgreicher Validierung dispatche den **docs-updater**:

```
Task (general-purpose/sonnet, run_in_background: true): "Du bist der docs-updater Agent.

  Input:
  - changed_files: [Liste der geaenderten Dateien]
  - feature_summary: [Kurzbeschreibung]
  - spec_file_path: [Pfad zur Spec]

  Aktualisiere alle betroffene Dokumentation."
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(300, "Docs-Updater Timeout [60-validate Step 3]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Docs-Updater nach 5 Min gestoppt — Dokumentation ggf. manuell prüfen.' NEIN → ignorieren, fertig.")
```

### Step 4: Workflow State aktualisieren

```bash
$WF phase phase8_complete
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

## On Failure

If validation fails after auto-fix attempt:
1. Do NOT update state to complete
2. Report the remaining issues to the user
3. User decides: fix manually or re-implement

## Versions-Marker (Pflicht)

Beende deine letzte Nachricht in diesem Befehl mit diesen Zeilen, in dieser Reihenfolge:

❗ Du: `/<befehl> #<N>` — <ein Halbsatz, warum>
ℹ️ Status: Workflow `<name>` · Phase `<x>` von 8
⚙ /60-validate · agent-os-openspec 3.30.0

Die erste Zeile sagt, wer am Zug ist — GENAU EINMAL, nur hier in der Fußzeile, nie zusätzlich als Vokabular mitten im Fließtext davor — und steht in genau einer von zwei Formen: `❗ Du: …`, wenn der PO den Schritt tippen oder eine Entscheidung treffen muss (bei Dringendem `‼️` statt `❗`). Das gilt AUCH, wenn du selbst gerade nichts mehr zu tun hast und nur auf den nächsten Befehl des PO wartest — das ist niemals „nichts zu tun“. Oder `ℹ️ Nichts zu tun: <du arbeitest gerade selbst / wartest auf ein Ergebnis, z. B. einen Hintergrund-Agenten> — danach: /<befehl> #<N>`, ausschließlich wenn du auf etwas ANDERES als den PO wartest. So muss der PO nie raten, ob etwas von ihm erwartet wird.

Schritt und Phase übernimmst du aus dem Hinweis `[agent-os-openspec] AKTIVER WORKFLOW …`, den der Hook bei jeder Nachricht mitliefert (dort heißt der Schritt „Nächster Pflicht-Schritt“) — Phase und Schritt wörtlich von dort. Fehlt der Hinweis (kein Workflow oder `phase8_complete`), entfallen die erste Zeile und die Statuszeile.

Solange die Phase kleiner als 8 ist, ist dieser Schritt **Pflicht**: nie „bei Bedarf“, „optional“ oder „wenn du magst“ — und nie „fertig“, „abgeschlossen“ oder „erledigt“ für den Workflow als Ganzes (das gilt erst ab `phase8_complete`; eine einzelne Phase darfst du abgeschlossen nennen). In frei formulierten Arbeitsstandsmeldungen steht der Pflicht-Schritt vor jeder `/clear`- oder Kosten-Empfehlung, und die Nachricht endet nie mit einer solchen Empfehlung. (Die wörtlich vorgegebenen Übergabe-Blöcke oben bleiben unverändert — dort gehören `/clear` und Folgebefehl zusammen.)

In diesen Zeilen ersetzt du `<name>`, `<x>` und `/<befehl> #<N>` durch die Werte aus dem Hook-Hinweis — Platzhalter bleiben nie stehen. Die ⚙-Zeile übernimmst du wörtlich und unverändert. Alle Zeilen stehen je genau einmal in der Nachricht, **nach** dem Übergabe-Block — auch nach dessen abschließendem `---` —, und die ⚙-Zeile ist immer die allerletzte Zeile der Nachricht, auch wenn die übrigen Zeilen entfallen.

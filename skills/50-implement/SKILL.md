---
description: "Implement the feature (TDD GREEN + Adversary)"
disable-model-invocation: true
---

# Phase 6: Implementation (TDD GREEN)

You are in **Phase 6 - Implementation / TDD GREEN Phase**.

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
QA="python3 ${_H}/qa_gate.py"
AD="python3 ${_H}/adversary_dialog.py"
```

## Purpose

Write the **minimal code** to make failing tests pass. No more, no less.

## Prerequisites

- Spec approved (`phase4_approved`)
- TDD RED complete (`phase5_tdd_red`)
- Test artifacts registered showing failures

Check status:
```bash
$WF status
```

**If TDD RED artifacts are missing, the `tdd_enforcement` hook will BLOCK your edits!**

## Your Tasks

### Step 1: Verify RED Phase Complete

```bash
$WF status
```

### Step 2: Kontext laden (Explore/Haiku)

Dispatche einen **Explore/Haiku Subagenten** um den Implementierungs-Kontext zu laden:

```
Task (Explore/haiku, run_in_background: true): "Lies folgende Dateien und fasse den relevanten Kontext
  zusammen:
  - Spec: [spec_file_path]
  - Betroffene Dateien: [affected_files]
  - Test-Dateien: [test_files]

  Fasse zusammen: Welche Interfaces existieren, welche Methoden muessen
  implementiert werden, welche Imports werden benoetigt."
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(180, "Explore-Agent Timeout [50-implement Step 2]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Kontext-Agent nach 3 Min gestoppt — bitte Step 2 neu starten.' NEIN → ignorieren, fertig.")
```

### Step 3: Developer Agent spawnen (ORCHESTRATOR-PRINZIP)

**Der Hauptkontext schreibt KEINEN Code. Nie. Keine Ausnahmen.**

Der Hauptkontext ist ein **Orchestrator** — er koordiniert, plant, und entscheidet.
Code-Edits gehoeren ausschliesslich dem **Developer Agent**.

```
Task (developer-agent/opus, run_in_background: true):
  "Implementiere gemaess Spec.

  Spec: [spec_file_path einfuegen]
  Betroffene Dateien: [affected_files aus workflow status]
  Test-Dateien: [test_files]
  Test-Command: [test_command aus openspec.yaml oder CLAUDE.md]

  Deine Aufgabe:
  1. Lies Spec vollstaendig — alle AC-N Acceptance Criteria verstehen
  2. Lies failing Tests — was genau wird getestet?
  3. Lies betroffene Dateien — aktueller Stand
  4. Schreibe minimalen Code um jeden failing Test gruen zu machen
  5. Fuehre Tests aus nach jeder wesentlichen Aenderung
  6. Speichere finalen Test-Output:
     [test_command] > docs/artifacts/[workflow]/test-green-output.txt 2>&1
  7. Melde zurueck: Dateien geaendert, Tests gruen/rot, welche ACs erfuellt

  NICHT:
  - Features die nicht in der Spec stehen
  - Refactoring das nicht zum Gruen benoetigt wird
  - Premature optimization
  - Mehr als 3 Loesungsversuche ohne Rueckmeldung"
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(600, "Developer Agent Timeout [50-implement Step 3]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Developer Agent nach 10 Min gestoppt — bitte /50-implement neu starten.' NEIN → ignorieren, fertig.")
```

**Nach Rueckmeldung des Developer Agent:**
- Tests GRUEN → weiter zu Step 4
- Tests noch ROT → Developer Agent erneut beauftragen mit Fehlermeldung (max. 3 Versuche total)
- Nach 3 Versuchen immer noch ROT → Eskalation an User: Root Cause unklar

| Rolle | Darf | Darf NICHT |
|-------|------|------------|
| **Orchestrator** (Hauptkontext) | Read, Grep, Bash (Tests starten, Output lesen), koordinieren | Edit/Write auf Code-Dateien |
| **Developer Agent** (Sub-Task) | Edit, Write, Tests ausfuehren, Code schreiben | Planen, User-Interaktion |

### Step 4: GREEN Artifacts registrieren

Der Developer Agent hat den Test-Output bereits gespeichert.
Orchestrator registriert das Artifact im Workflow-State:

```bash
$WF add-artifact test_output \
    "docs/artifacts/[workflow]/test-green-output.txt" \
    "All tests PASSED" \
    phase6_implement
```

### Step 6: User-Freigabe der GREEN-Ergebnisse (PFLICHT)

**STOP! Du darfst NICHT weitermachen ohne User-Freigabe!**

Praesentiere dem User eine verstaendliche Zusammenfassung:

```markdown
## TDD GREEN Ergebnisse

### Was wurde getestet?
- [Feature/Bug in User-Sprache beschreiben]

### Test-Ergebnisse
- Unit Tests: [N] bestanden, [N] fehlgeschlagen
- UI Tests: [N] bestanden, [N] fehlgeschlagen

### Was die Tests pruefen
- [Beschreibung in User-Sprache]

### Auffaelligkeiten / Warnungen
- [Alles was aufgefallen ist]

Sage "go" wenn du mit den Ergebnissen zufrieden bist.
```

**WICHTIG:**
- Du darfst NICHT selbst entscheiden ob Auffaelligkeiten relevant sind
- Du darfst NICHT "go" simulieren oder die Freigabe umgehen
- Der User gibt frei mit: "go", "weiter", "tests ok", "green ok"

### Step 7: Update Workflow State to Adversary Phase

```bash
$WF phase phase6b_adversary
```

### Step 8: Run Adversary Dialog (MANDATORY)

**Du kannst NICHT direkt zu `/60-validate` springen. Der Adversary-Dialog muss zuerst stattfinden.**

#### 8a. Spec parsen — Checkliste erstellen

```bash
$AD parse <spec-pfad>
```

Das zeigt dir die Expected-Behavior-Punkte die bewiesen werden muessen.

#### 8b. Adversary-Dialog fuehren

Starte den `implementation-validator` Agent mit der Checkliste:

```
Task (implementation-validator, run_in_background: true): "Pruefe den aktuellen Workflow gegen die Spec.
  Hier ist die Checkliste der zu beweisenden Punkte:
  [Punkte aus 8a einfuegen]

  REGELN:
  - Lies NUR die Spec (nicht den Code!)
  - Fordere fuer JEDEN Punkt einen Beweis (Screenshot, Test-Output, konkreter Code-Pfad)
  - Akzeptiere NICHT die erste Antwort — bohre nach, frage nach Edge Cases
  - Mindestens 2 Runden Dialog
  - Fuehre Tests aus und speichere Output
  - Nutze das Structured Findings Schema ($AD schema)"
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(300, "Adversary Validator Timeout [50-implement Step 8b]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Adversary-Agent nach 5 Min gestoppt — bitte Step 8b neu starten.' NEIN → ignorieren, fertig.")
```

Der Dialog laeuft als Hin-und-Her. **Du als Orchestrator koordinierst:**
1. Adversary Agent nennt naechsten offenen Punkt + was er sehen will
2. Du (Orchestrator) beauftragst Developer Agent, Beweis zu sammeln (Test ausfuehren, Screenshot, Code-Pfad)
3. Developer Agent liefert Beweis-Output → du relayierst an Adversary Agent
4. Adversary Agent bewertet: AKZEPTIERT oder NACHFRAGE
5. Wiederholen bis alle AC-N-Punkte bewiesen ODER Defekt gefunden

**Bei BROKEN:** Developer Agent erneut beauftragen (Schritt 3) — nicht selbst fixen!

#### 8c. Dialog-Protokoll speichern

Speichere das Protokoll als Artifact:
```
docs/artifacts/<workflow-name>/adversary-dialog.md
```

Registriere das Artifact im Workflow:
```bash
$WF add-artifact adversary_dialog \
    "docs/artifacts/<workflow-name>/adversary-dialog.md" \
    "Adversary Dialog Protokoll" phase6b_adversary
```

#### 8d. QA-Gate mit Checklist-Validierung

```bash
$QA /tmp/adversary_test_output.txt \
    --checklist docs/artifacts/<workflow-name>/adversary-dialog.md \
    --screenshot /tmp/adversary_screenshot.png

# Fuer Infra-Tickets (ohne UI):
$QA /tmp/adversary_test_output.txt \
    --checklist docs/artifacts/<workflow-name>/adversary-dialog.md \
    --infra --no-visual "Infra-Ticket ohne UI"
```

**Tri-State Verdict:**
- **VERIFIED** — Alle Punkte bewiesen, weiter zu Phase 7
- **BROKEN** — Defekte gefunden, zurueck zu Step 3 (neuer Fix + neuer Dialog!)
- **AMBIGUOUS** — Unklare Befunde, Pipeline NICHT blockiert aber User-Review empfohlen

**Circuit Breaker (max 3 Iterationen):**
Wenn nach 3 QA-Fixer-Loops noch BROKEN: Eskalation an User mit allen Findings.

**Wenn VERIFIED oder AMBIGUOUS (mit User-OK):**
```bash
$WF phase phase7_validate
```

## Implementation Constraints

Follow scoping limits:
- **Max 4-5 files** per change
- **Max +/-250 LoC** total
- **Functions <= 50 LoC**
- **No side effects** outside spec scope

## Next Step

After adversary verification:
> "Implementation complete. Adversary verified. Ready for `/60-validate`."

## Common Mistakes

- **Adding unrequested features** -> Scope creep
- **Skipping tests** -> Not TDD
- **Large functions** -> Hard to test/maintain
- **Not running tests** -> Might still be RED
- **Skipping adversary** -> Commit will be BLOCKED
- **Skipping User-Freigabe** -> Validation BLOCKED without user approval
- **Orchestrator schreibt Code selbst** -> Verletzt Orchestrator-Prinzip, kein Isolation-Schutz

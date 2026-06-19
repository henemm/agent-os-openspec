# Phase 6: Implementation (TDD GREEN)

You are in **Phase 6 - Implementation / TDD GREEN Phase**.

## Purpose

Write the **minimal code** to make failing tests pass. No more, no less.

## Prerequisites

- Spec approved (`phase4_approved`)
- TDD RED complete (`phase5_tdd_red`)
- Test artifacts registered showing failures

Check status:
```bash
python3 .claude/hooks/workflow.py status
```

**If TDD RED artifacts are missing, the `tdd_enforcement` hook will BLOCK your edits!**

## Your Tasks

### Step 0: Workflow-State auflösen (ZUERST — vor allem anderen)

**Wurde dieser Befehl mit einer Issue-Nummer aufgerufen** (z. B. `/50-implement #42` — typisch nach einem `/clear`)? Dann löse den Workflow-Namen von der Platte auf — der komplette State (Phase, Spec, RED-Tests, Verdict) überlebt jeden `/clear` und jeden Worktree:

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
        hits.append((name, d.get('current_phase'), d.get('spec_approved'), d.get('adversary_verdict')))
if not hits:
    print(f'KEIN laufender Workflow fuer #{issue} (evtl. abgeschlossen -> .claude/workflows/_archive/).')
else:
    for name, ph, spec, verd in hits:
        print(f'GEFUNDEN: {name} | Phase={ph} | Spec={spec} | Verdict={verd}')
    print('\nexport OPENSPEC_ACTIVE_WORKFLOW=' + hits[0][0])
PY
```

Setze `OPENSPEC_ACTIVE_WORKFLOW=<name>` und **fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** (Phase, Spec, offene Punkte) — damit sichtbar ist, dass der `/clear` nichts verloren hat.

**Ohne Issue-Argument** (laufende Session):
```bash
python3 .claude/hooks/workflow.py status
```

### Step 1: Verify RED Phase Complete

```bash
python3 .claude/hooks/workflow.py status
```

### Step 2: Kontext laden (Explore/Haiku)

Dispatche einen **Explore/Haiku Subagenten** um den Implementierungs-Kontext zu laden:

```
Task (Explore/haiku): "Lies folgende Dateien und fasse den relevanten Kontext
  zusammen:
  - Spec: [spec_file_path]
  - Betroffene Dateien: [affected_files]
  - Test-Dateien: [test_files]

  Fasse zusammen: Welche Interfaces existieren, welche Methoden muessen
  implementiert werden, welche Imports werden benoetigt."
```

### Step 3: Developer Agent spawnen (ORCHESTRATOR-PRINZIP)

**Der Hauptkontext schreibt KEINEN Code. Nie. Keine Ausnahmen.**

Der Hauptkontext ist ein **Orchestrator** — er koordiniert, plant, und entscheidet.
Code-Edits gehoeren ausschliesslich dem **Developer Agent**.

```
Task (developer-agent/opus):
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
python3 .claude/hooks/workflow.py add-artifact test_output \
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
python3 .claude/hooks/workflow.py phase phase6b_adversary
```

### Step 8: Run Adversary Dialog (MANDATORY)

**Du kannst NICHT direkt zu `/60-validate` springen. Der Adversary-Dialog muss zuerst stattfinden.**

#### 8a. Spec parsen — Checkliste erstellen

```bash
python3 .claude/hooks/adversary_dialog.py parse <spec-pfad>
```

Das zeigt dir die Expected-Behavior-Punkte die bewiesen werden muessen.

#### 8b. Adversary-Dialog fuehren

Starte den `implementation-validator` Agent mit der Checkliste:

```
Task (implementation-validator): "Pruefe den aktuellen Workflow gegen die Spec.
  Hier ist die Checkliste der zu beweisenden Punkte:
  [Punkte aus 8a einfuegen]

  REGELN:
  - Lies NUR die Spec (nicht den Code!)
  - Fordere fuer JEDEN Punkt einen Beweis (Screenshot, Test-Output, konkreter Code-Pfad)
  - Akzeptiere NICHT die erste Antwort — bohre nach, frage nach Edge Cases
  - Mindestens 2 Runden Dialog
  - Fuehre Tests aus und speichere Output
  - Nutze das Structured Findings Schema (python3 .claude/hooks/adversary_dialog.py schema)"
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
python3 .claude/hooks/workflow.py add-artifact adversary_dialog \
    "docs/artifacts/<workflow-name>/adversary-dialog.md" \
    "Adversary Dialog Protokoll" phase6b_adversary
```

#### 8d. QA-Gate mit Checklist-Validierung

```bash
python3 .claude/hooks/qa_gate.py /tmp/adversary_test_output.txt \
    --checklist docs/artifacts/<workflow-name>/adversary-dialog.md \
    --screenshot /tmp/adversary_screenshot.png

# Fuer Infra-Tickets (ohne UI):
python3 .claude/hooks/qa_gate.py /tmp/adversary_test_output.txt \
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
python3 .claude/hooks/workflow.py phase phase7_validate
```

## Implementation Constraints

Follow scoping limits:
- **Max 4-5 files** per change
- **Max +/-250 LoC** total
- **Functions <= 50 LoC**
- **No side effects** outside spec scope

## Next Step

Wenn Adversary VERIFIED (oder AMBIGUOUS mit User-OK): Stelle sicher, dass alle geänderten Dateien committed sind und das Adversary-Verdict im State steht — der nächste Schritt setzt den Gesprächskontext zurück. Gib dann exakt folgendes aus — dann **STOPP**:

---
✅ Phase 6 (Implementierung) abgeschlossen — Adversary VERIFIED.

Workflow: `<name>` · Issue: **#<N>** · Verdict: VERIFIED

Nächster Schritt — Kontext zurücksetzen spart Tokens (der Workflow-State liegt sicher auf der Platte):
1. `/clear`
2. `/60-validate #<N>`   (lädt Spec + State + Verdict automatisch von der Platte)

_Bei kleinem Kontext optional — dann genügt direkt `/60-validate`._

---

**NICHT** selbst mit der Validierung beginnen. Warte bis der User `/60-validate` tippt.

## Common Mistakes

- **Adding unrequested features** -> Scope creep
- **Skipping tests** -> Not TDD
- **Large functions** -> Hard to test/maintain
- **Not running tests** -> Might still be RED
- **Skipping adversary** -> Commit will be BLOCKED
- **Skipping User-Freigabe** -> Validation BLOCKED without user approval
- **Orchestrator schreibt Code selbst** -> Verletzt Orchestrator-Prinzip, kein Isolation-Schutz

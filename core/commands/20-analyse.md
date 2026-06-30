# Phase 2: Analyse

You are in **Phase 2 - Analysis** of the workflow.

## Prerequisites

- Context gathered (`/10-context` completed, or combined with analysis)
- Active workflow exists

Check current workflow:
```bash
python3 .claude/hooks/workflow.py status
```

## Your Tasks

### Step 1: Bug vs. Feature Routing

Bestimme aus dem Kontext:
- **Bug:** User meldet ein Problem, etwas funktioniert nicht wie erwartet
- **Feature:** User wuenscht neue Funktionalitaet oder Aenderung

### Step 2a: Feature-Analyse (3x Explore/Haiku parallel)

Bei Features dispatche **3 parallele Subagenten** fuer schnelle Kontextsammlung:

```
Task 1 (Explore/haiku, run_in_background: true): "Finde alle Dateien die von [Feature-Bereich] betroffen
  sind. Liste: Dateipfad, Typ (MODIFY/CREATE/DELETE), Begruendung."

Task 2 (Explore/haiku, run_in_background: true): "Suche nach bestehenden Specs in docs/specs/ die
  [Feature-Bereich] betreffen. Liste gefundene Specs mit Status."

Task 3 (Explore/haiku, run_in_background: true): "Identifiziere Dependencies und Imports fuer
  [Feature-Bereich]. Welche Module haengen davon ab? Welche werden importiert?"
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn (für alle 3 gemeinsam):**
```
ScheduleWakeup(180, "Explore-Agents Timeout [20-analyse Step 2a]: TaskList → noch aktive Haiku-Agents? JA → alle TaskStop, dann User: 'Analyse-Agenten nach 3 Min gestoppt — bitte /20-analyse neu starten.' NEIN → ignorieren, fertig.")
```

### Step 2b: Bug-Analyse (bug-intake/Haiku)

Bei Bugs dispatche den **bug-intake Agent**:

```
Task (general-purpose/haiku, run_in_background: true): Verwende die bug-intake Instruktionen.
  Input: symptom=[Fehlerbeschreibung], context=[Wo/Wann]
  Fuehre parallele Investigation durch und erstelle Bug Report.
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(180, "Bug-Intake Timeout [20-analyse Step 2b]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Bug-Intake-Agent nach 3 Min gestoppt — bitte /20-analyse neu starten.' NEIN → ignorieren, fertig.")
```

### Step 3: Strategische Bewertung (Plan/Sonnet)

Dispatche einen **Plan/Sonnet Subagenten** fuer die strategische Bewertung:

```
Task (Plan/sonnet, run_in_background: true): "Basierend auf folgenden Investigation-Ergebnissen:
  [Ergebnisse aus Step 2]

  Bewerte:
  1. Technischer Ansatz (wie implementieren?)
  2. Risiko-Bewertung (was koennte brechen?)
  3. Scope-Schaetzung (Dateien, LoC)
  4. Abhaengigkeiten und Reihenfolge
  5. Empfehlung (eine klare Empfehlung)"
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(300, "Plan-Agent Timeout [20-analyse Step 3]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Strategie-Agent nach 5 Min gestoppt — bitte /20-analyse neu starten.' NEIN → ignorieren, fertig.")
```

### Step 4: Synthese praesentieren

Fasse die Ergebnisse zusammen und aktualisiere `docs/context/[workflow-name].md`:

```markdown
## Analysis

### Type
[Bug / Feature]

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| src/auth.py | MODIFY | Add OAuth provider |
| tests/test_auth.py | CREATE | New test file |

### Scope Assessment
- Files: [N]
- Estimated LoC: +[N]/-[N]
- Risk Level: LOW/MEDIUM/HIGH

### Technical Approach
[Empfehlung aus Plan/Sonnet Bewertung]

### Dependencies
[Aus Explore-Ergebnis]

### Open Questions
- [ ] Question 1?
```

### Step 5: Update Workflow State

```bash
python3 .claude/hooks/workflow.py phase phase3_spec
```

## Next Step

Wenn die Analyse abgeschlossen ist, gib dem User folgende Zusammenfassung:

---
**Analyse abgeschlossen.**

**Art der Aufgabe:** [Feature / Bugfix]

**Was steht an?** [1–2 Sätze was konkret geändert oder gebaut wird — aus Nutzerperspektive, ohne Dateinamen oder Code]

**Risiko:** [Niedrig / Mittel / Hoch] — [kurze Begründung ohne Technik, z.B. "betrifft nur einen isolierten Bereich" oder "ändert eine zentrale Funktion"]

Nächster Schritt: `/30-write-spec` — ich schreibe jetzt den detaillierten Plan.

---

Wenn noch offene Fragen bestehen: Zuerst den User fragen, bevor es weitergeht.

**IMPORTANT:** Do NOT start implementation. Analysis -> Spec -> Approve -> TDD RED -> Implement.

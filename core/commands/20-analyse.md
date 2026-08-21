# Phase 2: Analyse

You are in **Phase 2 - Analysis** of the workflow.

## Step 0: Workflow-State auflösen (ZUERST — vor allem anderen)

**Wurde dieser Befehl mit einer Issue-Nummer aufgerufen** (z. B. `/20-analyse #42` — typisch nach einem `/clear`)? Dann aktiviere den Workflow explizit. Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58).

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
        hits.append((name, d.get('current_phase'), d.get('spec_file') or 'Not created'))
if not hits:
    print(f'KEIN laufender Workflow fuer #{issue} (evtl. abgeschlossen -> .claude/workflows/_archive/).')
else:
    for name, ph, spec in hits:
        print(f'GEFUNDEN: {name} | Phase={ph} | Spec={spec}')
    print('\nNAME=' + hits[0][0])
PY
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen) und den Stand verifizieren:

```bash
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht — damit sichtbar ist, dass der `/clear` nichts verloren hat.

**Ohne Issue-Argument** (laufende Session, kein `/clear` dazwischen): `workflow.py status` reicht direkt.

## Prerequisites

- Context gathered (`/10-context` completed, or combined with analysis)
- Active workflow exists

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

---

**Checkpoint — Vorbedingungen prüfen, bevor du unten etwas ausgibst:**

Gib das `✅`-Verdikt nur aus, wenn ALLE zutreffenden Punkte erfüllt sind:
- Phase im Workflow-State geschrieben — `python3 .claude/hooks/workflow.py status` bestätigt sie
- Alle Ergebnisdateien dieser Phase existieren auf der Platte
- Keine uncommitteten Änderungen an Dateien, die `/30-write-spec` braucht
- Ab Phase 5: alle RED-Artefakte per `add-artifact` registriert
- Keine Erkenntnis, die für `/30-write-spec` nötig und nirgends niedergeschrieben ist

Alle zutreffenden Punkte erfüllt → gib den Positiv-Block aus. Mindestens einer verletzt → gib stattdessen den Negativ-Block aus, mit dem konkreten Sicherungsschritt.

**Positiv-Block (alle Vorbedingungen erfüllt):**

---
**Gesichert auf der Platte:**
- `.claude/workflows/<name>.json` — Phase `phase3_spec`, Verdict, Artefakt-Register
- `docs/context/<workflow-name>.md`, Abschnitt `## Analysis` — Art der Aufgabe, betroffene Dateien mit Change-Type, Scope/Risiko, technischer Ansatz, offene Fragen

✅ **`/clear` ist jetzt gefahrlos** — alles oben Gelistete stellt der Folge-Befehl allein aus diesen Dateien wieder her. Im Gesprächsverlauf steht nichts, was verloren ginge.

1. `/clear`
2. `/30-write-spec #<N>`

---

**Negativ-Block (mindestens eine Vorbedingung verletzt):**

---
⚠️ **`/clear` jetzt NICHT** — Folgendes steht nur im Gesprächsverlauf:
- <was fehlt> → sichern mit: <konkreter Befehl oder Schritt>

Erst sichern, dann ist `/clear` gefahrlos.

---

Wenn noch offene Fragen bestehen: Zuerst den User fragen, bevor es weitergeht.

**IMPORTANT:** Do NOT start implementation. Analysis -> Spec -> Approve -> TDD RED -> Implement.

# Phase 3: Write Specification

You are in **Phase 3 - Specification Writing**.

## Step 0: Workflow-State auflösen (ZUERST — vor allem anderen)

**Wurde dieser Befehl mit einer Issue-Nummer aufgerufen** (z. B. `/30-write-spec #42` — typisch nach einem `/clear`)? Dann aktiviere den Workflow explizit. Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58).

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

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Analyse-Stand. Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht — damit sichtbar ist, dass der `/clear` nichts verloren hat.

**Ohne Issue-Argument** (laufende Session, kein `/clear` dazwischen): `workflow.py status` reicht direkt.

## Fast Track (workflow_type == feature-fast)

Prüfe zuerst den Workflow-Typ:
```bash
python3 .claude/hooks/workflow.py status
```

Wenn `workflow_type: feature-fast` → **kein Sonnet-Agent, kein Haiku-Validator**.
Schreibe direkt eine Mini-Spec im Hauptkontext:

- Datei: `docs/specs/fast/[name].md`
- Format: laut `/00-intake` → Mini-Spec-Template
- Dann: `workflow.py set-field spec_file "docs/specs/fast/[name].md"`
- Dann: Freigabe vom User abwarten ("approved")
- Nach Freigabe: direkt zu `/50-implement`

**Standard- und Full-Process-Workflows** folgen dem normalen Ablauf unten.

---

## Prerequisites (Standard / Full Process)

- Analysis completed (`phase2_analyse`)
- Context document exists with affected files list

Check current workflow:
```bash
python3 .claude/hooks/workflow.py status
```

## Your Tasks

### Step 1: Vorbereitung

Lies die Analyse-Ergebnisse aus `docs/context/[workflow-name].md` und das Template aus `docs/specs/_template.md`.

### Step 2: Spec erstellen (general-purpose/Sonnet)

Dispatche einen **general-purpose/Sonnet Subagenten** mit den spec-writer Instruktionen:

```
Task (general-purpose/sonnet, run_in_background: true): "Du bist der spec-writer Agent.

  Input:
  - feature_name: [Name]
  - analysis_summary: [Zusammenfassung aus Phase 2]
  - affected_files: [Liste aus Analyse]
  - dependencies: [Liste aus Analyse]
  - workflow_name: [Workflow-Name]

  Erstelle eine vollstaendige Spec in docs/specs/[category]/[entity].md
  nach dem spec-writer Workflow. Beachte alle Qualitaetsregeln."
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(300, "Spec-Writer Timeout [30-write-spec Step 2]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Spec-Writer nach 5 Min gestoppt — bitte /30-write-spec neu starten.' NEIN → ignorieren, fertig.")
```

### Step 3: Spec validieren (spec-validator/Haiku)

Dispatche den **spec-validator/Haiku** zur Validierung:

```
Task (general-purpose/haiku, run_in_background: true): "Du bist der spec-validator Agent.

  Validiere die Spec: docs/specs/[category]/[entity].md
  Pruefe alle Required Fields, Sections, Placeholders.
  Output: VALID oder INVALID mit Details."
```

**TIMEOUT-PFLICHT — sofort nach dem Spawn:**
```
ScheduleWakeup(180, "Spec-Validator Timeout [30-write-spec Step 3]: TaskList → noch aktiv? JA → TaskStop, dann User: 'Spec-Validator nach 3 Min gestoppt — bitte Step 3 neu starten.' NEIN → ignorieren, fertig.")
```

**Bei INVALID:**
1. Behebe die gemeldeten Fehler in der Spec
2. Dispatche spec-validator erneut
3. Wiederhole bis VALID

### Step 4: Workflow State aktualisieren

```bash
# Update spec file path in workflow
python3 .claude/hooks/workflow.py set-field spec_file "docs/specs/[category]/[entity].md"

# Advance to spec_written phase
python3 .claude/hooks/workflow.py phase phase3_spec
```

## Next Step

Präsentiere die Spec und bitte um Freigabe. Gib dem User folgende Zusammenfassung:

---
**Plan fertig — bitte Freigabe.**

**Was wird gebaut?**
[Feature/Änderung in 1–2 Sätzen aus Nutzerperspektive — keine Dateinamen, kein Code]

**Was ändert sich sichtbar?**
- [Konkretes sichtbares Verhalten 1]
- [Konkretes sichtbares Verhalten 2]

**Was bleibt unverändert?**
[Was explizit nicht angefasst wird — gibt dem PO Sicherheit über den Scope]

**Qualitätsplan:** [N] automatische Tests geplant · Spezifikation geprüft: VALID

Schreibe `approved` wenn der Plan so stimmt — danach geht es in die Umsetzung.

---

## After Approval

When user approves:
1. `workflow_state_updater` hook detects approval phrase
2. State advances to `phase4_approved`
3. Next: `/40-tdd-red` to write failing tests

Nach der Freigabe kannst du dem User zusätzlich anbieten:

---
Nächster Schritt — Kontext zurücksetzen spart Tokens (der Workflow-State liegt sicher auf der Platte):
1. `/clear`
2. `/40-tdd-red #<N>`   (lädt die freigegebene Spec automatisch von der Platte)

_Bei kleinem Kontext optional — dann genügt direkt `/40-tdd-red`._

---

**IMPORTANT:**
- Do NOT implement until approved
- Do NOT skip TDD RED phase after approval

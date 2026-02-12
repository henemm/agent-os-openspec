# Phase 7: Validation

You are in **Phase 7 - Validation**.

## Prerequisites

- Implementation complete (`phase6_implement`)
- All tests passing (GREEN artifacts registered)

Check status:
```bash
python3 .claude/hooks/workflow_state_multi.py status
```

## Your Tasks

### Step 1: Parallele Validierung (4x Haiku)

Dispatche **4 parallele Haiku-Agenten** fuer umfassende Validierung:

```
Task 1 (general-purpose/haiku) - TEST CHECK:
  "Fuehre ALLE Tests aus: [test_command]
  Report: Anzahl passed/failed, Laufzeit, Fehlerdetails."

Task 2 (general-purpose/haiku) - SPEC COMPLIANCE:
  "Lies die Spec: [spec_file_path]
  Pruefe jeden Acceptance Criterion gegen die Implementation.
  Report: Welche Kriterien sind erfuellt, welche nicht?"

Task 3 (general-purpose/haiku) - REGRESSION CHECK:
  "Fuehre die vollstaendige Test-Suite aus (nicht nur Feature-Tests).
  Report: Gibt es Regressionen? Welche Tests die vorher gruen waren
  sind jetzt rot?"

Task 4 (general-purpose/haiku) - SCOPE CHECK:
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
Task (general-purpose/sonnet): "Folgende Validierungsfehler wurden gefunden:
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
Task (general-purpose/sonnet): "Du bist der docs-updater Agent.

  Input:
  - changed_files: [Liste der geaenderten Dateien]
  - feature_summary: [Kurzbeschreibung]
  - spec_file_path: [Pfad zur Spec]

  Aktualisiere alle betroffene Dokumentation."
```

### Step 4: Workflow State aktualisieren

```bash
python3 .claude/hooks/workflow_state_multi.py phase phase8_complete
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

After successful validation:
> "Validation successful. All checks passed. Ready for commit."

## On Failure

If validation fails after auto-fix attempt:
1. Do NOT update state to complete
2. Report the remaining issues to the user
3. User decides: fix manually or re-implement

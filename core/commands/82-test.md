# Tests ausfuehren

Starte den `test-runner` Agenten — eigener Agent-Typ, Start **ohne `model`** (#577):

```
Agent(subagent_type="test-runner", description="Tests ausfuehren", prompt="
  Fuehre die Tests des Projekts aus und fasse das Ergebnis zusammen
  (passed/failed/uebersprungen, bei Failures Fehlermeldungen und betroffene Dateien).
  Kontext (falls Wiedereinstieg): affected_files und test_files aus dem Workflow-State.")
```

**Fallback, wenn der Typ in der Agent-Liste fehlt:** test-runner → `agent-os-openspec:test-runner`, sonst `Agent(subagent_type="general-purpose", model="haiku", prompt="Lies zuerst .claude/agents/test-runner.md (im Framework-Repo core/agents/test-runner.md) und folge ihr. …")`.

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Aufruf als `/82-test #<N>`?** Zuerst Workflow auflösen und aktivieren:

```bash
python3 .claude/hooks/workflow.py find 42   # die übergebene Nummer
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht**; `affected_files` und `test_files` gehören in den Auftrag. Ohne Argument laufen die Tests des aktuellen Projekts.

## Output Format

Ein Lauf mit 0 bestanden und ≥ 1 übersprungen ist nicht grün.

Erfolg: `Tests: X passed, Y failed, Z übersprungen` + `Status: Alles gruen`.
Failures:
```
Tests: X passed, Y failed, Z übersprungen
Fehlgeschlagen:
- TestClass.testMethod: [Fehlermeldung]
Betroffene Dateien:
- [Pfad]
```

Vor Commit muessen ALLE Tests gruen sein.

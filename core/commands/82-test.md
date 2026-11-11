# Tests ausfuehren

Starte den `test-runner` Agenten — eigener Agent-Typ (Projekt-Agent in `.claude/agents/`, lokal auch als Plugin-Agent), Start **ohne `model`**, das Modell steht im Frontmatter (#577):

```
Agent(subagent_type="test-runner", description="Tests ausfuehren", prompt="
  Fuehre die Tests des Projekts aus und fasse das Ergebnis zusammen
  (passed/failed/uebersprungen, bei Failures Fehlermeldungen und betroffene Dateien).
  Kontext (falls Wiedereinstieg): affected_files und test_files aus dem Workflow-State.")
```

**Fallback, wenn der Typ in der Agent-Liste fehlt:** test-runner → `agent-os-openspec:test-runner`, sonst `Agent(subagent_type="general-purpose", model="haiku", prompt="Lies zuerst .claude/agents/test-runner.md (im Framework-Repo core/agents/test-runner.md) und folge ihr. …")`.

---

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/82-test #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — der komplette State überlebt jeden `/clear` und jeden Worktree:

```bash
python3 .claude/hooks/workflow.py find 42   # die übergebene Nummer
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58):

```bash
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — `affected_files` und `test_files` aus dem State gehören in den Auftrag an den Test-Runner.

**Ohne Argument** laufen die Tests des aktuellen Projekts.

---

## Anweisung

1. Ermittle das passende Test-Kommando fuer das Projekt
2. Fuehre alle Tests aus
3. Fasse Ergebnisse kurz und verstaendlich zusammen
4. Bei Failures: Zeige betroffene Dateien und Fehlermeldungen

---

## Output Format

Ein Lauf mit 0 bestanden und ≥ 1 übersprungen ist nicht grün.

**Bei Erfolg:**
```
Tests: X passed, Y failed, Z übersprungen
Status: Alles gruen
```

**Bei Failures:**
```
Tests: X passed, Y failed, Z übersprungen
Fehlgeschlagen:
- TestClass.testMethod: [Fehlermeldung]

Betroffene Dateien:
- [Pfad]
```

---

## Zero Tolerance Policy

- ALLE Tests muessen gruen sein vor Commit
- Bei Failures: Nicht committen, erst fixen
- Keine Ausnahmen

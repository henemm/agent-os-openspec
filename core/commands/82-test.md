# Tests ausfuehren

Starte den `test-runner` Agenten aus `core/agents/test-runner.md`.

---

## Anweisung

1. Ermittle das passende Test-Kommando fuer das Projekt
2. Fuehre alle Tests aus
3. Fasse Ergebnisse kurz und verstaendlich zusammen
4. Bei Failures: Zeige betroffene Dateien und Fehlermeldungen

---

## Output Format

**Bei Erfolg:**
```
Tests: X passed
Status: Alles gruen
```

**Bei Failures:**
```
Tests: X passed, Y failed
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

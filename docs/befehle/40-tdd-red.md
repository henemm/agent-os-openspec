# Hintergrund zu /40-tdd-red

Begründungen und Sonderfälle zu core/commands/40-tdd-red.md; der Befehlstext enthält Ablauf und Pflichtschritte.

## Purpose

Write tests BEFORE implementation. Tests MUST FAIL because the functionality doesn't exist yet.

**If tests pass → you're not doing TDD, you're testing existing code.**

## Step 0: Workflow-State auflösen

**Wurde dieser Befehl mit einer Issue-Nummer aufgerufen** (z. B. `/40-tdd-red #42` — typisch nach einem `/clear`)? Dann aktiviere den Workflow explizit. Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58).

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen) und den Stand verifizieren:

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht — damit sichtbar ist, dass der `/clear` nichts verloren hat.

**Ohne Issue-Argument** (laufende Session, kein `/clear` dazwischen): `workflow.py status` reicht direkt.

## Prerequisites

- Spec approved (`phase4_approved`)
- Test plan defined in spec

## Write Tests Based on Spec

From the spec's Test Plan, create test files:

```python
# tests/test_[feature].py

def test_new_functionality():
    """
    GIVEN: [precondition]
    WHEN: [action]
    THEN: [expected result]
    """
    # This test MUST FAIL because feature doesn't exist
    result = feature_that_doesnt_exist()
    assert result == expected_value
```

## Run Tests und Capture REAL Artifacts

Execute the tests:
```bash
pytest tests/test_[feature].py -v > docs/artifacts/[workflow]/test-output-red.txt 2>&1
```

**Expected:** Tests FAIL with clear error messages.

### 4. Capture REAL Artifacts

Save actual test output as artifacts:

```bash
# Create artifacts directory
mkdir -p docs/artifacts/[workflow-name]

# Save test output
pytest tests/ -v > docs/artifacts/[workflow]/test-red-output.txt 2>&1

# For UI tests, take actual screenshots
# For API tests, save actual responses
```

## Mark RED

Gleich nach dem Registrieren den RED-Stand im Workflow-State melden — damit nennt die Fußzeile
schon jetzt `/50-implement`, auch wenn der Turn vor dem Phasenwechsel endet:

## Artifact Requirements

Each artifact MUST:
- Be a **real file** (not placeholder)
- Have **minimum size** (proves non-empty)
- Include **description** of what it proves
- Show **failure evidence** (error, fail, assertion)

## RED Phase Checklist

Before proceeding to implementation:

- [ ] Tests written for all spec requirements
- [ ] All tests executed
- [ ] All tests FAIL (RED)
- [ ] At least 1 artifact registered
- [ ] Artifact shows failure evidence
- [ ] RED gemeldet: `workflow.py mark-red "<Ergebnis>"` ausgeführt


## Next Step

Sobald alle Artefakte registriert sind und Spec + RED-Testdateien committed sind — der nächste Schritt setzt den Gesprächskontext zurück. Führe zuerst aus:

Danach folgt die Ausgabe an den User, danach rufst du `50-implement` selbst auf (siehe unten).

## Kette zu /50-implement

Ohne `/clear` in derselben Session: Rufe den Skill `50-implement` jetzt sofort selbst
auf — warte nicht auf eine weitere User-Eingabe, die registrierten RED-Artefakte sind
bereits die Voraussetzung, keine zusätzliche Entscheidung steht mehr aus.

Mit `/clear` dazwischen: Der Checkpoint-Block oben zeigt den regulären Wiedereinstieg
über den expliziten Befehl `/50-implement #<N>`.

Diese Kette gilt unabhängig vom Autonomie-Modus — auch bei `AUTONOMY=auto` ist hier nichts zusätzlich zu tun (#472).

## Kontext-Haushalt beim Selbstaufruf

Ein Schritt mit 200k Token Kontext kostet etwa das Fünffache eines Schritts mit 40k. Bei `CONTEXT_STOP=off` (auch mit `CONTEXT_REASON=AUTO_NO_CLEAR`: Auto-Modus, niemand tippt `/clear`, Nachschlagen an Teilagenten abgeben, Claude Code komprimiert automatisch) oder `CONTEXT_TOKENS=unknown`: Kette unverändert selbst fortsetzen (#658).

## Common Mistakes

❌ **Tests that pass** → Test is worthless, proves nothing
❌ **Mock everything** → Not testing real behavior
❌ **Placeholder artifacts** → Hook will block implementation
❌ **Skip to implement** → TDD enforcement hook will block you

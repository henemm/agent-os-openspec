# Add Test Artifact

Register a **REAL** test artifact (screenshot, log, API response, test output) for TDD workflow validation.

Hintergrund (Begründungen, Sonderfälle): `docs/befehle/81-add-artifact.md` im Plugin-Ordner — nur bei Bedarf lesen.

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Aufruf als `/81-add-artifact #<N>`?** Zuerst Workflow auflösen und aktivieren — das Artefakt landet im State des AKTIVEN Workflows:

```bash
python3 .claude/hooks/workflow.py find 42   # die übergebene Nummer
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

**Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — die Phase bestimmt die Artefakt-Phase. Ohne Argument gilt der aktive Workflow.

## Usage

1. **Save the artifact** to `docs/artifacts/[workflow-name]/`
2. **Register it** (Typen: `screenshot`, `email`, `api_response`, `log`, `test_output`, `ui_test_output`, `video`):
```bash
python3 .claude/hooks/workflow.py add-artifact screenshot \
    "docs/artifacts/[workflow]/screenshot.png" \
    "Screenshot showing test failure: expected X but got Y" \
    phase5_tdd_red
```

Artifacts MUST be real, non-empty (Mindestgröße), less than 24 h old and described. `phase5_tdd_red`: description shows failure (fail, error, assertion, expected/actual); `phase7_validate`: success (pass, success, verified, works).

## Shorthand: Mark RED Done

```bash
python3 .claude/hooks/workflow.py mark-red "3 tests failed as expected"
python3 .claude/hooks/workflow.py mark-ui-red "UI test assertion error"
```

# Add Test Artifact

Register a **REAL** test artifact for TDD workflow validation.

## Purpose

TDD requires proof that tests were executed with REAL data:
- Screenshots showing actual test output
- Log files from actual test runs
- API responses from actual calls
- Email content from actual sends

## Wiedereinstieg via Issue-Nummer (nach `/clear`)

**Wurde dieser Befehl als `/81-add-artifact #<N>` aufgerufen** (typisch nach einem `/clear`)? Dann löse zuerst den Workflow von der Platte auf — ein Artefakt landet im State des AKTIVEN Workflows; steht der falsche aktiv, geht der Beweis an die falsche Stelle:

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
        hits.append((name, d.get('current_phase'), d.get('spec_file') or 'Not created', d.get('adversary_verdict'), d.get('affected_files', [])))
if not hits:
    print(f'KEIN laufender Workflow fuer #{issue} (evtl. abgeschlossen -> .claude/workflows/_archive/).')
else:
    for name, ph, spec, verd, aff in hits:
        print(f'GEFUNDEN: {name} | Phase={ph} | Spec={spec} | Verdict={verd}')
        if aff: print(f'  affected_files: {", ".join(aff)}')
    print('\nNAME=' + hits[0][0])
PY
```

**PFLICHT direkt danach** — Workflow wirklich aktivieren (nicht nur die Zeile oben lesen). Ein reines `export OPENSPEC_ACTIVE_WORKFLOW=...` reicht NICHT: Shell-State überlebt keinen Bash-Tool-Aufruf, und in Worktree-Sessions ignoriert `resolve_active_workflow()` die Env-Var ohnehin (Issue #58):

```bash
python3 .claude/hooks/workflow.py switch <NAME-aus-obigem-Output>
python3 .claude/hooks/workflow.py status
```

Das `status`-Kommando ist der eigentliche Wiedereinstiegs-Check: Es zeigt die Quelle (`[file]`) und bestätigt Phase/Spec. **Fasse dem User in 2 Sätzen zusammen, wo der Workflow steht** — die Phase entscheidet, als welche Phase das Artefakt registriert wird.

**Ohne Argument** wird der aktive Workflow verwendet.

## Usage

When you have captured a test artifact:

1. **Save the artifact** to `docs/artifacts/[workflow-name]/`

2. **Register it**:
```bash
python3 .claude/hooks/workflow.py add-artifact screenshot \
    "docs/artifacts/[workflow]/screenshot.png" \
    "Screenshot showing test failure: expected X but got Y" \
    phase5_tdd_red
```

## Artifact Types

| Type | Extensions | Min Size | Use For |
|------|------------|----------|---------|
| `screenshot` | .png, .jpg, .gif | 1KB | UI tests, error screens |
| `email` | .eml, .txt | 100B | Email notifications |
| `api_response` | .json, .xml | 10B | API integration tests |
| `log` | .log, .txt | 10B | Test execution logs |
| `test_output` | .txt, .json | 10B | Test runner output |
| `ui_test_output` | .txt, .log | 10B | UI test runner output |
| `video` | .mp4, .mov | 10KB | UI flow recordings |

## Requirements

Artifacts MUST be:
- **Real files** - Not placeholders
- **Non-empty** - Minimum size enforced
- **Recent** - Less than 24 hours old
- **Described** - What does this prove?

## RED Phase Artifacts

For TDD RED phase (`phase5_tdd_red`), artifacts must show **test failure**:
- Description should mention: fail, error, assertion, expected/actual

## Validate Phase Artifacts

For validation (`phase7_validate`), artifacts show **test success**:
- Description should mention: pass, success, verified, works

## Example

```bash
# After running failing test, capture the output
./run-tests.sh > docs/artifacts/feature-login/test-output-red.txt 2>&1

# Register it
python3 .claude/hooks/workflow.py add-artifact test_output \
    "docs/artifacts/feature-login/test-output-red.txt" \
    "Test failed: LoginService.authenticate() not implemented - assertion error on line 42" \
    phase5_tdd_red
```

## Shorthand: Mark RED Done

```bash
python3 .claude/hooks/workflow.py mark-red "3 tests failed as expected"
python3 .claude/hooks/workflow.py mark-ui-red "UI test assertion error"
```

# Add Test Artifact

Register a **REAL** test artifact for TDD workflow validation.

## Purpose

TDD requires proof that tests were executed with REAL data:
- Screenshots showing actual test output
- Log files from actual test runs
- API responses from actual calls
- Email content from actual sends

## Usage

When you have captured a test artifact:

1. **Save the artifact** to `docs/artifacts/[workflow-name]/`

2. **Register it**:
```bash
python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, '.claude/hooks')
from workflow_state_multi import add_test_artifact, load_state

state = load_state()
active = state.get('active_workflow')
if active:
    add_test_artifact(active, {
        'type': 'screenshot',  # or: email, api_response, log, file, test_output
        'path': 'docs/artifacts/[workflow]/[filename]',
        'description': 'Screenshot showing test failure: expected X but got Y',
        'phase': 'phase5_tdd_red'  # or: phase7_validate
    })
    print(f'Artifact added to {active}')
else:
    print('No active workflow')
"
```

## Artifact Types

| Type | Extensions | Min Size | Use For |
|------|------------|----------|---------|
| `screenshot` | .png, .jpg, .gif | 1KB | UI tests, error screens |
| `email` | .eml, .txt | 100B | Email notifications |
| `api_response` | .json, .xml | 10B | API integration tests |
| `log` | .log, .txt | 10B | Test execution logs |
| `test_output` | .txt, .json | 10B | Test runner output |
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
python3 -c "
import sys; sys.path.insert(0, '.claude/hooks')
from workflow_state_multi import add_test_artifact, load_state
state = load_state()
add_test_artifact(state['active_workflow'], {
    'type': 'test_output',
    'path': 'docs/artifacts/feature-login/test-output-red.txt',
    'description': 'Test failed: LoginService.authenticate() not implemented - assertion error on line 42',
    'phase': 'phase5_tdd_red'
})
"
```

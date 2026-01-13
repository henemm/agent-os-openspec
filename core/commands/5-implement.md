# Phase 6: Implementation (TDD GREEN)

You are in **Phase 6 - Implementation / TDD GREEN Phase**.

## Purpose

Write the **minimal code** to make failing tests pass. No more, no less.

## Prerequisites

- Spec approved (`phase4_approved`)
- TDD RED complete (`phase5_tdd_red`)
- Test artifacts registered showing failures

Check status:
```bash
python3 .claude/hooks/workflow_state_multi.py status
```

**If TDD RED artifacts are missing, the `tdd_enforcement` hook will BLOCK your edits!**

## Your Tasks

### 1. Verify RED Phase Complete

```bash
python3 -c "
import sys; sys.path.insert(0, '.claude/hooks')
from workflow_state_multi import get_active_workflow

w = get_active_workflow()
if w:
    artifacts = [a for a in w.get('test_artifacts', []) if a.get('phase') == 'phase5_tdd_red']
    print(f'RED artifacts: {len(artifacts)}')
    for a in artifacts:
        print(f'  - {a[\"type\"]}: {a[\"description\"][:50]}...')
"
```

### 2. Read the Spec

Open and follow the approved spec exactly:
- Implementation details
- Affected files
- Expected behavior

### 3. Implement - Make Tests GREEN

Write code to make tests pass:

```python
# Implement the minimal code to satisfy tests
def feature_that_was_missing():
    # Now it exists!
    return expected_value
```

**TDD GREEN Rules:**
- Only write code that makes a test pass
- Don't add features not covered by tests
- Don't optimize prematurely
- Don't refactor yet

### 4. Run Tests - MUST BE GREEN

```bash
pytest tests/test_[feature].py -v
```

**Expected:** All tests PASS.

### 5. Capture GREEN Artifacts

```bash
pytest tests/ -v > docs/artifacts/[workflow]/test-green-output.txt 2>&1

python3 -c "
import sys; sys.path.insert(0, '.claude/hooks')
from workflow_state_multi import add_test_artifact, load_state

state = load_state()
active = state['active_workflow']

add_test_artifact(active, {
    'type': 'test_output',
    'path': 'docs/artifacts/[workflow]/test-green-output.txt',
    'description': 'All tests PASSED: 5 passed in 0.3s',
    'phase': 'phase6_implement'
})
"
```

### 6. Update Workflow State

```bash
python3 .claude/hooks/workflow_state_multi.py phase phase7_validate
```

## Implementation Constraints

Follow scoping limits:
- **Max 4-5 files** per change
- **Max +/-250 LoC** total
- **Functions ≤50 LoC**
- **No side effects** outside spec scope

## Next Step

After implementation:
> "Implementation complete. All [N] tests pass. Ready for `/validate` for manual testing."

## Common Mistakes

❌ **Adding unrequested features** → Scope creep
❌ **Skipping tests** → Not TDD
❌ **Large functions** → Hard to test/maintain
❌ **Not running tests** → Might still be RED

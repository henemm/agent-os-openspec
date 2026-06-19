---
description: "Write failing tests (RED phase)"
disable-model-invocation: true
---

# Phase 5: TDD RED - Write Failing Tests

You are in **Phase 5 - TDD RED Phase**.

## Setup

```bash
# Plugin: CLAUDE_PLUGIN_ROOT; Legacy-Fallback: .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"; _H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
```

## Purpose

Write tests BEFORE implementation. Tests MUST FAIL because the functionality doesn't exist yet.

**If tests pass → you're not doing TDD, you're testing existing code.**

## Prerequisites

- Spec approved (`phase4_approved`)
- Test plan defined in spec

Check status:
```bash
$WF status
```

## Your Tasks

### 1. Enter TDD RED Phase

```bash
$WF phase phase5_tdd_red
```

### 2. Write Tests Based on Spec

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

### 3. Run Tests - MUST BE RED

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

### 5. Register Artifacts

```bash
$WF add-artifact test_output \
    "docs/artifacts/[workflow]/test-red-output.txt" \
    "Test FAILED: [function] raises NotImplementedError - assertion error line 42" \
    phase5_tdd_red
```

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

## Next Step

After RED phase is complete:
> "TDD RED complete. [N] tests written, all failing as expected. Artifacts captured. Ready for `/50-implement`."

```bash
$WF phase phase6_implement
```

## Common Mistakes

❌ **Tests that pass** → Test is worthless, proves nothing
❌ **Mock everything** → Not testing real behavior
❌ **Placeholder artifacts** → Hook will block implementation
❌ **Skip to implement** → TDD enforcement hook will block you

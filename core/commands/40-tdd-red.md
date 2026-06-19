# Phase 5: TDD RED - Write Failing Tests

You are in **Phase 5 - TDD RED Phase**.

## Purpose

Write tests BEFORE implementation. Tests MUST FAIL because the functionality doesn't exist yet.

**If tests pass → you're not doing TDD, you're testing existing code.**

## Prerequisites

- Spec approved (`phase4_approved`)
- Test plan defined in spec

Check status:
```bash
python3 .claude/hooks/workflow.py status
```

## Your Tasks

### 1. Enter TDD RED Phase

```bash
python3 .claude/hooks/workflow.py phase phase5_tdd_red
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
python3 .claude/hooks/workflow.py add-artifact test_output \
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

Sobald alle Artefakte registriert sind und Spec + RED-Testdateien committed sind — der nächste Schritt setzt den Gesprächskontext zurück. Führe zuerst aus:

```bash
python3 .claude/hooks/workflow.py phase phase6_implement
```

Dann gib exakt folgendes aus — dann **STOPP**:

---
✅ Phase 5 (TDD RED) abgeschlossen.

Workflow: `<name>` · Issue: **#<N>** · Phase: `phase5_tdd_red` ✓

Nächster Schritt — Kontext zurücksetzen spart Tokens (der Workflow-State liegt sicher auf der Platte):
1. `/clear`
2. `/50-implement #<N>`   (lädt Spec + RED-Tests + State automatisch von der Platte)

_Bei kleinem Kontext optional — dann genügt direkt `/50-implement`._

---

**NICHT** selbst mit der Implementierung beginnen. Warte bis der User `/50-implement` tippt.

## Common Mistakes

❌ **Tests that pass** → Test is worthless, proves nothing
❌ **Mock everything** → Not testing real behavior
❌ **Placeholder artifacts** → Hook will block implementation
❌ **Skip to implement** → TDD enforcement hook will block you

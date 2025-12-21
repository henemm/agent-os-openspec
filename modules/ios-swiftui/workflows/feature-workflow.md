# Feature Workflow

## Overview

Features follow **TDD (Test-Driven Development)** with the Red-Green-Refactor cycle.

**MANDATORY CHECKPOINTS:** Steps marked with ⛔ are BLOCKING.
You MUST complete them before proceeding. No exceptions.

```
┌────────────────────────────────────────────────────────────────┐
│                    TDD: RED-GREEN-REFACTOR                      │
│                                                                 │
│  ⛔ RED      →  ⛔ GREEN    →    REFACTOR   →  (repeat)        │
│  Test FAILS     Test PASSES     Code clean                      │
│  (Step 5)       (Step 8)        (optional)                      │
└────────────────────────────────────────────────────────────────┘
```

## Workflow Steps

### 1. Feature Request
- User describes what they want
- Understand the "why" (user value)
- Clarify category: Primary / Support / Passive

### 2. Check Existing Systems

**CRITICAL - Before designing:**
```bash
# Search for related systems
grep -r "Keyword" --include="*.swift"
```

Ask: "I see [existing system X], should I extend that or build new?"

### 3. Use Feature-Planner Agent
```
/feature [name]
```

The agent will:
- Understand requirements
- Check existing systems
- Create specification
- Add to roadmap

### 4. Define Acceptance Criteria

Write `openspec/changes/[feature-name]/tests.md`:
```markdown
# Acceptance Tests: [Feature Name]

## Unit Tests
- [ ] GIVEN... WHEN... THEN...

## XCUITests
- [ ] [Language 1]: [UI verification]
- [ ] [Language 2]: [UI verification]

## Manual Tests (User)
- [ ] [Real device tests]
```

### ⛔ 5. Write Tests FIRST - RED Phase (MANDATORY)

**TDD Step 1: Write tests that FAIL**

1. **XCUITests** (for UI changes)
2. **Unit Tests** (for logic)
3. **Run tests - MUST be RED**

**⛔ BLOCKER:** Test MUST fail! If green → Test is worthless!

### 6. Create OpenSpec Proposal

Create in `openspec/changes/[feature-name]/`:
- `proposal.md` - What and why
- `tasks.md` - Implementation checklist
- `specs/[domain]/spec.md` - Spec delta

### 7. Review & Approve

- Present spec to user
- Iterate until aligned
- Get explicit approval before coding

### 8. Implement - GREEN Phase

**TDD Step 2: Write minimal code until tests are GREEN**

**Constraints:**
- Follow approved spec exactly
- Max 4-5 files per change
- Max +/-250 LoC
- Functions <= 50 LoC
- **ONLY implement what tests require** - no extras!

### ⛔ 9. Run ALL Tests - GREEN Phase (MANDATORY)

**TDD Step 3: Tests MUST now PASS**

**⛔ BLOCKER:** All tests MUST be green!

If tests fail:
1. DO NOT proceed to manual tests
2. Adjust code until tests green
3. No "I'll test that later" excuses

### 10. Refactor (Optional)

- Clean up code without changing functionality
- Run tests again → stay GREEN
- If RED → revert changes

### 11. Present to User for Manual Testing

**ONLY after ALL automated tests pass:**
- Present ONE test at a time
- Wait for user feedback
- Document results in ACTIVE-todos.md

### 12. Archive Change

Merge spec delta into source specs.

### 13. Update Documentation

- [ ] DOCS/ACTIVE-roadmap.md (update status)
- [ ] openspec/specs/ (updated by archive)
- [ ] Remove openspec/changes/[feature-name]/ after merge

## TDD Checkpoint Summary

| Step | Phase | Checkpoint | Blocking? |
|------|-------|------------|-----------|
| 4 | - | Acceptance Criteria defined | YES |
| 5 | RED | Tests written & failed | ⛔ YES |
| 9 | GREEN | All tests pass | ⛔ YES |
| 11 | - | User Manual Tests pass | ⛔ YES |

## Feature Categories

Design UI based on category:

| Category | UI Approach |
|----------|-------------|
| Primary | Prominent, explicit interaction |
| Support | Visible but secondary |
| Passive | Background, notification-driven |

## Anti-Patterns

❌ **Test AFTER Code** → Tests only verify existing code
❌ **Green tests without prior Red** → Test proves nothing
❌ **Skip tests** → Bugs at user
❌ **No spec:** Starting to code without written spec
❌ **Duplicate system:** Building new when similar exists
❌ **Scope creep:** Adding unrequested functionality

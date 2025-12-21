# Bug Fix Workflow

## Overview

Every bug fix follows the Analysis-First principle. No quick fixes!

## Workflow Steps

### 1. Bug Reported
- User describes problem
- Note exact steps to reproduce
- Understand expected vs actual behavior

### 2. Use Bug-Investigator Agent
```
/bug [description]
```

The agent will:
- Analyze the bug systematically
- Trace data flow
- Identify root cause with certainty
- Create ACTIVE-todos.md entry

### 3. Root Cause Identification

**Before writing ANY fix:**
- [ ] Problem scope fully understood
- [ ] All possible causes listed
- [ ] Root cause identified with certainty (specific code lines)
- [ ] No speculation - evidence only

### 4. Test Case Definition

Define how to verify the fix:
```markdown
### Test Criteria
- [ ] [Specific behavior to verify]
- [ ] [Edge case to check]
- [ ] [Regression check]
```

### 5. Implement Fix

**Constraints:**
- Max 4-5 files changed
- Max +/-250 LoC
- Functions <= 50 LoC
- No side effects outside ticket

### 6. Run Tests

```bash
xcodebuild test -project {{PROJECT_FILE}} \
  -scheme "{{TEST_SCHEME}}" \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro'
```

All tests must pass.

### 7. Commit

```bash
git commit -m "fix: [Brief description]

Problem: [What was wrong]
Root Cause: [Why it happened]
Fix: [What was changed]

Tested: Unit tests passing"
```

### 8. Documentation

Update if applicable:
- [ ] DOCS/ACTIVE-todos.md (mark as GEFIXT)
- [ ] DOCS/bug-index.md (if pattern bug)
- [ ] .agent-os/standards/ (if new lesson)

### 9. UI Testing

Prepare test instructions for user:
- Clear steps
- Expected result
- Edge cases
- All supported languages

## Anti-Patterns

- **Trial-and-error:** Multiple attempts without analysis
- **Quick fix:** Change code without understanding
- **Scope creep:** "While I'm here, let me also..."
- **Skip tests:** "It's a small change..."
- **Guess timing:** Using Task.sleep() for synchronization

# Scoping Limits

> Keep changes small, focused, and reviewable.

## Why Limits Matter

1. **Smaller context** - Easier for Claude to understand and track
2. **Easier review** - User can verify changes quickly
3. **Safer rollback** - Less to undo if something breaks
4. **Better focus** - One thing at a time, done well

## Hard Limits

| Metric | Limit | Reason |
|--------|-------|--------|
| Files per change | 4-5 max | Keeps context manageable |
| Lines of code | ±250 lines | Reviewable in one session |
| Scope | One feature/fix | Clear success criteria |

## When to Split Work

Split your task when:
- More than 5 files would be affected
- More than 250 lines would change
- Multiple unrelated changes are needed
- Feature has distinct implementation phases

## How to Split

**By layer:**
```
1. Data/Schema changes
2. Backend/API logic
3. Frontend/UI components
4. Integration/glue code
```

**By dependency:**
```
1. Independent changes first
2. Dependent changes after
```

**By risk:**
```
1. Low-risk changes first (tests, docs)
2. Higher-risk changes after (core logic)
```

## Example: "Add User Authentication"

**Bad:** One giant change touching everything

**Good:** Split into phases:
1. Database schema + migrations (2 files)
2. Auth service/middleware (2-3 files)
3. API routes for login/logout (2-3 files)
4. UI components (login form, etc.) (3-4 files)
5. Protected routes integration (2-3 files)

Each phase is reviewable and testable independently.

## Exceptions

Large refactors may exceed limits when:
- Pre-approved by user explicitly
- Documented in spec with rationale
- Rollback plan exists
- Tested incrementally (not all at once)

## Enforcement

The `scope_guard.py` hook can enforce these limits.
Configure in `config.yaml`:

```yaml
scoping:
  max_files: 5
  max_lines: 250
  enabled: true  # or false to disable
```

## Benefits for Claude

Smaller scope means:
- Less context to track
- Clearer success criteria
- Faster iteration cycles
- Lower risk of confusion
- Better quality output

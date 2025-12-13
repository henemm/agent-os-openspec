# Scoping Limits

## Per-Change Limits

**Maximum per bug fix or feature:**
- Max **4-5 files** changed
- **+/-250 LoC** total (Additions + Modifications + Deletions)
- Functions: **<=50 LoC**

## No Side Effects

**Outside the ticket scope:**
- No "I'll just quickly change this too"
- No drive-by refactoring
- No unrelated improvements

## Exceeding Limits

**If limits would be exceeded:**
1. STOP and ask with concrete estimate
2. Propose splitting into smaller tickets
3. Get approval before proceeding

## Why This Matters

- Smaller changes are easier to review
- Easier to rollback if something goes wrong
- Reduces cognitive load for testing
- Prevents scope creep

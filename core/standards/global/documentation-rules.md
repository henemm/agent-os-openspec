# Documentation Rules

## No False Completion Claims

**CRITICAL:** Never claim "complete" or "done" without user verification.

**What I CAN confirm:**
- "Implemented X in file Y"
- "Build successful"
- "Tests passing"
- "Syntax valid"

**What I CANNOT confirm:**
- "Feature complete"
- "Working correctly"
- "Done"

**Why:** I can verify builds and tests pass. I CANNOT verify the feature works correctly on real devices or meets user expectations. Only the user can verify end-to-end functionality.

## Check Existing Systems First

**Before building anything new:**

1. Search for related code: `grep -rn "keyword" .`
2. Check existing architecture (models, services, utils)
3. Ask: "Should I extend existing X or build new?"

**Why:** Duplicate systems = double maintenance. User expects integration with existing code.

## After Git Operations

**After merge/rebase/pull:**
```bash
git status              # Verify state
git log -1 --stat       # See what changed
git diff --name-status HEAD@{1} HEAD  # Compare
```

Check nothing was accidentally deleted.

---

*Core principle: Report facts, not assumptions. Let user verify outcomes.*

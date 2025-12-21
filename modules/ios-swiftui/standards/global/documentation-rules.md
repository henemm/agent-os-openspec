# Documentation Rules

## Never Use Checkmarks Without User Verification

**CRITICAL:** Never mark features as "Complete" when unverified.

**What I CAN say:**
- "Implemented X in file Y"
- "Added X functionality"
- "Built successfully"
- "Unit tests passing"

**What I CANNOT say:**
- "Complete"
- "Feature X done"
- "Working"
- Any green checkmarks implying completeness

**Why:**
- I can only verify: builds, compiles, unit tests pass
- I CANNOT verify: full integration, UI correctness, device behavior
- Only USER can verify end-to-end functionality on real device

## Always Check for Existing Systems First

**Before building ANY new system:**

1. Grep for keywords related to the feature
2. Read existing architecture documentation (DOCS/ folder)
3. Check if Models/ or Services/ already have related code
4. Ask user: "I see [existing system X], should I extend that or build new?"
5. ONLY proceed after confirming approach

**Why:**
- Duplicate systems = double maintenance burden
- User expects integration with existing UI/Settings
- Wasted time building wrong architecture

## Git Merge Safety Protocol

**After ANY merge:**
1. Run `git status` - verify no files missing
2. Run `git log -1 --stat` - see what changed
3. Verify DOCS/ directory intact
4. Check `git diff --name-status HEAD@{1} HEAD`

**If files missing:**
- Check `git log --diff-filter=D` to find deleted files
- Restore from previous commit

## Bug Documentation Protocol

**When to create separate bug-*.md file:**
- Bug required multiple solution attempts
- Bug represents a recurring pattern
- Bug solution is non-obvious

**Mandatory artifacts for EVERY bug:**
1. Entry in DOCS/bug-index.md
2. CLAUDE.md Lesson (if generalizable pattern)
3. Detailed commit message (Problem, Root Cause, Fix, Files)

**The Rule:**
- DON'T document everything exhaustively (creates noise)
- DON'T document nothing (lose institutional memory)
- DO document bugs that help prevent future mistakes
- DO ask: "Will this doc help me avoid repeating this mistake?"

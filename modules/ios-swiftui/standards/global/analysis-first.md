# Analysis-First Principle

> "Analyse thoroughly, solve correctly, verify immediately"

## Core Rule

**Identify root cause with CERTAINTY before implementing fix. No speculative fixes!**

## The 5-Step Analysis Framework

1. **WHERE** is data created/loaded?
2. **HOW** is data transformed?
3. **WHERE** is data displayed?
4. **WHERE** is data used for calculations?
5. **Are steps 3 and 4 using THE SAME data?** (If NO → inconsistency!)

## Spec-First Implementation

**CRITICAL:** Never implement features without complete written specification.

**If spec is missing:**
- DO NOT speculate or build "what seems right"
- DO NOT infer requirements from existing code alone
- STOP immediately and ask user for complete spec
- Document spec before writing any code

**Why:**
- User has specific vision that may not match "obvious" implementation
- Breaking changes to existing UX have serious consequences
- Wasted time building wrong feature that must be reverted

## Clean Rollback Strategy

**When implementation is wrong:**
1. Don't try to "fix forward" - this compounds errors
2. Use `git reset --hard <commit>` to clean rollback point
3. Start fresh with correct specification
4. Document what went wrong

## Never Simplify Away Feature Intent

**Problem Pattern:** When facing implementation challenges, suggesting "simplifying" by removing core value.

**The Rule:**
- DON'T change feature goal to simplify implementation
- DON'T remove core value to avoid technical challenges
- DO research how successful apps solve the SAME problem
- DO ask user if feature goal can be adjusted (don't decide alone)

**Why:**
- Implementation complexity is MY problem, not the user's
- User wants the FEATURE, not "whatever is easiest to build"
- Removing core functionality = deleting the feature entirely

## Complete Data Flow Tracing

**CRITICAL:** Always trace the COMPLETE "Entstehungsgeschichte" (origin story).

```
DON'T: Look at isolated code fragments
DO: Trace complete data flow from source to consumption
DO: Map ALL usages before making changes
```

## Debugging Protocol

**When stuck after multiple attempts:**
1. Create minimal reproducible test FIRST
2. Build debug view with simplest possible case
3. Test system works isolated from complex code
4. If debug works → problem is in app code, not system
5. Rewrite complex code based on working minimal example

**The Rule:**
- DON'T delete features when stuck - fix the actual problem
- DO create minimal test, identify root cause, fix systematically
- DO preserve existing features while fixing bugs

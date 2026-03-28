# Analysis-First Principle

> Understand before you act. No code without root cause. No trial-and-error.

## Why Analysis-First Matters

1. **Correct fixes** - Fixing the root cause, not symptoms
2. **No regressions** - Understanding impact before changing
3. **Less wasted effort** - One correct fix vs. multiple guesses
4. **Better documentation** - Analysis becomes knowledge

## The Process

### Step 1: Understand the Problem Completely

- What exactly happens? (Observable symptoms)
- Where does it happen? (Feature, view, context)
- When does it happen? (Always? Sometimes? After specific action?)
- Can you explain the problem in 2 sentences? If not, keep investigating.

### Step 2: List All Possible Causes

- Don't stop at the first plausible explanation
- Consider: data flow, state management, timing, edge cases
- Check git blame: was this area changed recently?

### Step 3: Identify Root Cause with Certainty

- Find the exact code location(s) causing the issue
- Trace the data flow end-to-end
- Prove WHY this code causes the problem
- No speculation — only evidence-backed conclusions

### Step 4: Implement Fix

- Only after root cause is confirmed
- Minimal change that addresses the cause
- No drive-by refactoring

### Step 5: Verify Immediately

- Run tests right after the fix
- Confirm the symptom is gone
- Check for side effects

## Anti-Patterns (FORBIDDEN)

| Anti-Pattern | Why It's Bad |
|-------------|-------------|
| "Let me try this..." | Guessing wastes time and creates new bugs |
| Fixing symptoms | Root cause persists, breaks again later |
| Changing multiple things at once | Can't tell what actually fixed it |
| Skipping verification | "It should work" is not evidence |
| Copy-paste from StackOverflow | Without understanding, it's a time bomb |

## When to STOP and Ask

- Root cause is unclear after thorough analysis
- Multiple equally plausible causes exist
- Fix would require changes beyond scope limits
- Previous fix attempt didn't work (go back to Step 1!)

## Enforcement

The `analysis-challenger` agent can validate your analysis before implementation begins.
It applies a 5-point challenge to ensure thoroughness.

# Phase 3: Implementation

You are starting the **Implementation Phase**.

## Prerequisites:

Check `.claude/workflow_state.json`:
- `current_phase` must be `spec_approved`
- `spec_approved` must be `true`

If not, the `workflow_gate` hook will block your edits!

## Your Tasks:

1. **Read the approved spec** - Follow it exactly
2. **Implement step by step:**
   - Create/modify files as specified
   - Run validation after each change (if applicable)
   - Test incrementally
3. **Document any deviations** - If you must deviate from spec, note why

## Implementation Order (recommended):

1. Core functionality first
2. Tests second
3. Documentation third
4. Integration last

## Update Workflow State:

After completing implementation:
```json
{
  "current_phase": "implemented",
  "implementation_done": true,
  "last_updated": "[ISO timestamp]"
}
```

## Next Step:

> "Implementation complete. Next step: `/validate` to verify everything works."

**IMPORTANT:** Do NOT commit without running `/validate` first!

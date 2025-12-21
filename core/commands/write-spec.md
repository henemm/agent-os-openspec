# Phase 2: Write Specification

You are starting the **Spec Writing Phase**.

## Prerequisites:

Check `.claude/workflow_state.json`:
- `current_phase` must be `analyse_done`

## Your Tasks:

1. **Use the spec-writer agent** or create spec manually
2. **Create spec in docs/specs/** using the template
3. **Fill in all required fields:**
   - entity_id (in frontmatter)
   - Purpose (at least 1 sentence)
   - Source (file + identifier)
   - Dependencies (table with all source entities)
4. **Set approval checkbox to `[ ]`** (not approved yet)

## Spec Template Location:

`docs/specs/_template.md`

## Update Workflow State:

After creating the spec:
```json
{
  "current_phase": "spec_written",
  "feature_name": "[Feature Name]",
  "spec_file": "docs/specs/[category]/[entity_id].md",
  "spec_approved": false,
  "last_updated": "[ISO timestamp]"
}
```

## Next Step:

Present the spec to the user and ask for approval:
> "Spec created at `[path]`. Please review and confirm with 'approved' or 'freigabe'."

**IMPORTANT:** Do NOT implement until the user explicitly approves the spec!

The `workflow_state_updater` hook will automatically detect approval phrases and update the state.

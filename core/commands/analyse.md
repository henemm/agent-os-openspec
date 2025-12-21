# Phase 1: Analyse

You are starting the **Analysis Phase** for a new feature or change.

## Your Tasks:

1. **Understand the request** - What exactly does the user want?
2. **Research the codebase** - Use Explore agent or Grep/Glob
3. **Identify affected files** - Which files need changes?
4. **Check existing specs** - Are there specs that will be affected?
5. **Document findings** - Summarize what you found

## Update Workflow State:

After completing the analysis, update the workflow state:

```bash
# Read current state
cat .claude/workflow_state.json

# Update to analyse_done phase
```

Update `.claude/workflow_state.json`:
```json
{
  "current_phase": "analyse_done",
  "feature_name": "[Feature Name]",
  "spec_file": null,
  "spec_approved": false,
  "last_updated": "[ISO timestamp]"
}
```

## Next Step:

When analysis is complete, inform the user:
> "Analysis complete. Next step: `/write-spec` to create the specification."

**IMPORTANT:** Do NOT start implementation without the user calling `/write-spec`!

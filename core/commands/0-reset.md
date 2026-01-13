# Reset Workflow

Reset the workflow state to start fresh.

## When to Use

| Situation | Action |
|-----------|--------|
| Workflow completed successfully | `/reset` |
| Need to abort current workflow | `/reset` |
| Starting a completely new task | `/reset` |

## What Happens

Resets workflow state to idle:
- Phase → `idle`
- All flags → cleared
- Feature name → cleared
- Spec file → cleared

## Execute Reset

```bash
# If using workflow_state_multi.py
python3 .claude/hooks/workflow_state_multi.py reset

# Or manually clear state
echo '{"current_phase": "idle", "workflows": {}}' > .claude/workflow_state.json
```

## State After Reset

```json
{
  "current_phase": "idle",
  "feature_name": null,
  "spec_file": null,
  "spec_approved": false,
  "implementation_done": false,
  "validation_done": false
}
```

## Next Steps

After reset, start a new workflow:

```
/analyse [feature/bug]  → Start analysis
/context               → Gather context first
```

---

*Use reset for clean starts. Don't carry state from abandoned work.*

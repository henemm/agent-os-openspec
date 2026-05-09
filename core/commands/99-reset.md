# Reset Workflow

Reset the workflow state to start fresh.

## When to Use

| Situation | Action |
|-----------|--------|
| Workflow completed successfully | `/99-reset` |
| Need to abort current workflow | `/99-reset` |
| Starting a completely new task | `/99-reset` |

## What Happens

Completes and archives the current workflow, or removes it if in early phases.

## Execute Reset

```bash
# Complete and archive the current workflow
python3 .claude/hooks/workflow.py complete

# Or start fresh with a new workflow
python3 .claude/hooks/workflow.py start "new-feature"
```

## Next Steps

After reset, start a new workflow:

```
/10-context               → Gather context first
/20-analyse [feature/bug] → Start analysis
```

---

*Use reset for clean starts. Don't carry state from abandoned work.*

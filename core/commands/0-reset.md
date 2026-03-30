# Reset Workflow

Reset the workflow state to start fresh.

## When to Use

| Situation | Action |
|-----------|--------|
| Workflow completed successfully | `/reset` |
| Need to abort current workflow | `/reset` |
| Starting a completely new task | `/reset` |

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
/context               → Gather context first
/analyse [feature/bug] → Start analysis
```

---

*Use reset for clean starts. Don't carry state from abandoned work.*

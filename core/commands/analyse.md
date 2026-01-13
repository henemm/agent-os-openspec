# Phase 2: Analyse

You are in **Phase 2 - Analysis** of the workflow.

## Prerequisites

- Context gathered (`/context` completed, or combined with analysis)
- Active workflow exists

Check current workflow:
```bash
python3 .claude/hooks/workflow_state_multi.py status
```

## Your Tasks

### 1. Deep Analysis

Build on the context gathered:

1. **Understand the request** - What exactly does the user want?
2. **Analyse affected code** - Read the relevant files in detail
3. **Map dependencies** - Trace data flow and call chains
4. **Identify risks** - What could break?
5. **Estimate scope** - How many files, how much change?

### 2. Document Analysis

Update or create `docs/context/[workflow-name].md`:

```markdown
## Analysis

### Affected Files (with changes)
| File | Change Type | Description |
|------|-------------|-------------|
| src/auth.py | MODIFY | Add OAuth provider |
| src/config.py | MODIFY | Add OAuth settings |
| tests/test_auth.py | CREATE | New test file |

### Scope Assessment
- Files: [N]
- Estimated LoC: +[N]/-[N]
- Risk Level: LOW/MEDIUM/HIGH

### Technical Approach
[How we'll implement this]

### Open Questions
- [ ] Question 1?
- [ ] Question 2?
```

### 3. Update Workflow State

```bash
python3 .claude/hooks/workflow_state_multi.py phase phase3_spec
```

## Next Step

When analysis is complete:
> "Analysis complete. Scope: [N] files, ~[N] LoC. Next: `/write-spec` to create the specification."

If you have open questions, ask the user before proceeding.

**IMPORTANT:** Do NOT start implementation. Analysis → Spec → Approve → TDD RED → Implement.

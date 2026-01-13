# Phase 1: Context Generation

You are starting **Phase 1 - Context Generation** for a new workflow.

## Purpose

Before analysing, gather ALL relevant context. This prevents:
- Missing important related code
- Overlooking existing patterns
- Reinventing existing solutions

## Your Tasks

### 1. Start or Resume Workflow

```bash
python3 .claude/hooks/workflow_state_multi.py start "[feature-name]"
```

Or switch to existing:
```bash
python3 .claude/hooks/workflow_state_multi.py switch "[feature-name]"
```

### 2. Gather Context

Search and collect:

1. **Related Files** - Find all files that might be relevant
   ```
   Grep for: keywords, function names, class names
   Glob for: related file patterns
   ```

2. **Existing Specs** - Check `docs/specs/` for related entities

3. **Similar Implementations** - How does the codebase handle similar things?

4. **Dependencies** - What does the affected code depend on?

5. **Dependents** - What depends on the code we'll change?

### 3. Create Context Document

Create `docs/context/[workflow-name].md`:

```markdown
# Context: [Workflow Name]

## Request Summary
[1-2 sentences: what the user wants]

## Related Files
| File | Relevance |
|------|-----------|
| path/to/file.py | Contains X which we need to modify |

## Existing Patterns
- Pattern 1: How similar things are done
- Pattern 2: ...

## Dependencies
- Upstream: [what our code uses]
- Downstream: [what uses our code]

## Existing Specs
- `docs/specs/category/entity.md` - Related spec

## Risks & Considerations
- Risk 1
- Risk 2
```

### 4. Update Workflow State

```bash
python3 .claude/hooks/workflow_state_multi.py phase phase2_analyse
```

## Next Step

Inform the user:
> "Context gathered. Found [N] related files. Next: `/analyse` for detailed analysis."

**IMPORTANT:** Do NOT skip to implementation. Context → Analyse → Spec → Implement.

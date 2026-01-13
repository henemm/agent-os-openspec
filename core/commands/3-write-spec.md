# Phase 3: Write Specification

You are in **Phase 3 - Specification Writing**.

## Prerequisites

- Analysis completed (`phase2_analyse`)
- Context document exists with affected files list

Check current workflow:
```bash
python3 .claude/hooks/workflow_state_multi.py status
```

## Your Tasks

### 1. Create Specification

Use `docs/specs/_template.md` as base.

Create spec at `docs/specs/[category]/[entity_id].md`:

```markdown
---
entity_id: [unique-id]
type: feature|bugfix|refactor
created: [ISO date]
status: draft
workflow: [workflow-name]
---

# [Title]

- [ ] Approved for implementation

## Purpose
[1-2 sentences: what and why]

## Scope
- Files: [list affected files]
- Estimated: +[N]/-[N] LoC

## Implementation Details
[Technical approach from analysis]

## Test Plan

### Automated Tests (TDD RED)
- [ ] Test 1: GIVEN... WHEN... THEN... (expected to FAIL initially)
- [ ] Test 2: ...

### Manual Tests
- [ ] Manual test 1
- [ ] Manual test 2

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
```

### 2. Update Workflow State

```bash
# Update spec file path in workflow
python3 -c "
import sys; sys.path.insert(0, '.claude/hooks')
from workflow_state_multi import load_state, save_state
state = load_state()
active = state.get('active_workflow')
if active:
    state['workflows'][active]['spec_file'] = 'docs/specs/[category]/[entity].md'
    save_state(state)
"

# Advance to spec_written phase
python3 .claude/hooks/workflow_state_multi.py phase phase3_spec
```

## Next Step

Present the spec and request approval:

> "Spec created: `docs/specs/[path]`
>
> Please review:
> - Scope: [N] files, ~[N] LoC
> - Test plan: [N] automated, [N] manual tests
>
> Confirm with 'approved', 'freigabe', or 'lgtm' to proceed."

## After Approval

When user approves:
1. `workflow_state_updater` hook detects approval phrase
2. State advances to `phase4_approved`
3. Next: `/tdd-red` to write failing tests

**IMPORTANT:**
- Do NOT implement until approved
- Do NOT skip TDD RED phase after approval

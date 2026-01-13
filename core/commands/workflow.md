# Workflow Management

Manage multiple parallel workflows in your project.

## Commands

### List All Workflows
```bash
python3 .claude/hooks/workflow_state_multi.py list
```

Output:
```
→ feature-login-oauth: Phase 4 - Spec Approved
  bugfix-crash-on-start: Phase 6 - Implementation
  feature-dark-mode: Phase 2 - Analysis
```

### Check Current Status
```bash
python3 .claude/hooks/workflow_state_multi.py status
```

Output:
```
Workflow: feature-login-oauth
Phase: Phase 4 - Spec Approved
Spec: docs/specs/auth/login-oauth.md
Approved: Yes
Test Artifacts: 2
```

### Start New Workflow
```bash
python3 .claude/hooks/workflow_state_multi.py start "feature-name"
```

### Switch Active Workflow
```bash
python3 .claude/hooks/workflow_state_multi.py switch "other-feature"
```

### Advance to Next Phase
```bash
python3 .claude/hooks/workflow_state_multi.py advance
```

### Set Specific Phase
```bash
python3 .claude/hooks/workflow_state_multi.py phase phase4_approved
```

## Workflow Phases

| Phase | Name | Description |
|-------|------|-------------|
| `phase0_idle` | Idle | No workflow started |
| `phase1_context` | Context | Gathering relevant context |
| `phase2_analyse` | Analysis | Analysing requirements |
| `phase3_spec` | Specification | Writing spec |
| `phase4_approved` | Approved | User approved spec |
| `phase5_tdd_red` | TDD RED | Writing failing tests |
| `phase6_implement` | Implementation | Writing code (TDD GREEN) |
| `phase7_validate` | Validation | Manual testing |
| `phase8_complete` | Complete | Ready for commit |

## Parallel Workflows

You can work on multiple features simultaneously:

1. **Start workflows** for each feature
2. **Switch** between them as needed
3. Each workflow tracks its own:
   - Current phase
   - Spec file
   - Approval status
   - Test artifacts

## Code Modification Rules

Code files can only be modified in:
- `phase6_implement`
- `phase7_validate`
- `phase8_complete`

And only if:
- TDD RED phase artifacts exist
- Artifacts are valid (real files, not placeholders)
- At least one artifact shows test failure

## Automatic Phase Detection

Some phase transitions happen automatically:
- User says "approved" → `phase4_approved`
- `/context` completed → `phase1_context`
- `/analyse` completed → `phase2_analyse`
- `/write-spec` completed → `phase3_spec`

## State File Location

`.claude/workflow_state.json` contains all workflow data.

Format (v2.0):
```json
{
  "version": "2.0",
  "workflows": {
    "feature-name": {
      "current_phase": "phase4_approved",
      "spec_file": "docs/specs/...",
      "test_artifacts": [...]
    }
  },
  "active_workflow": "feature-name"
}
```

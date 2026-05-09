# Workflow Management

Manage multiple parallel workflows with isolated state (v3).

## Commands

### List All Workflows
```bash
python3 .claude/hooks/workflow.py list
```

### Check Current Status
```bash
python3 .claude/hooks/workflow.py status
```

### Start New Workflow
```bash
python3 .claude/hooks/workflow.py start "feature-name"
```

### Switch Active Workflow
```bash
python3 .claude/hooks/workflow.py switch "other-feature"
```

### Set Specific Phase
```bash
python3 .claude/hooks/workflow.py phase phase4_approved
```

### Set Workflow Fields
```bash
python3 .claude/hooks/workflow.py set-field spec_file "docs/specs/auth/login.md"
python3 .claude/hooks/workflow.py set-field context_file "docs/context/login.md"
python3 .claude/hooks/workflow.py set-affected-files src/auth.py src/login.py
```

### Register Test Artifacts
```bash
python3 .claude/hooks/workflow.py add-artifact test_output \
    "docs/artifacts/feature/test-red.txt" \
    "Test FAILED: assertion error" \
    phase5_tdd_red
```

### Mark TDD RED Done
```bash
python3 .claude/hooks/workflow.py mark-red "3 tests failed"
python3 .claude/hooks/workflow.py mark-ui-red "UI test assertion"
```

### Write Execution Log (Required before complete)
```bash
python3 .claude/hooks/workflow.py write-log success
python3 .claude/hooks/workflow.py write-log partial
python3 .claude/hooks/workflow.py write-log reverted
```
Writes `.claude/workflows/_log/YYYY-MM-DD_<name>.yaml` with phases completed,
adversary verdict, fix-loop count, LoC delta, and outcome.

### Override AMBIGUOUS Adversary Verdict
```bash
python3 .claude/hooks/workflow.py override-ambiguous "reason for proceeding"
```
Required when adversary verdict is AMBIGUOUS and all findings are resolved.
Without this, `git commit` is blocked.

### Link to GitHub Issue
```bash
python3 .claude/hooks/workflow.py set-field github_issue 42
```

### Override LoC Limit
```bash
python3 .claude/hooks/workflow.py set-field loc_limit_override 500
```

### Complete Workflow
```bash
# Requires execution log — will fail without write-log first
python3 .claude/hooks/workflow.py complete
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
| `phase6b_adversary` | Adversary | Adversary verification |
| `phase7_validate` | Validation | Final validation |
| `phase8_complete` | Complete | Ready for commit |

## State Architecture (v3)

Each workflow gets its own JSON file in `.claude/workflows/`:

```
.claude/workflows/
├── .active              ← Symlink to active workflow
├── feature-login.json   ← Isolated state
├── bugfix-crash.json    ← Isolated state
└── _archive/            ← Completed workflows
```

## Code Modification Rules

Code files can only be modified in:
- `phase6_implement`
- `phase6b_adversary`
- `phase7_validate`
- `phase8_complete`

And only if:
- TDD RED phase artifacts exist
- Spec has `## Acceptance Criteria` with at least one `AC-N` entry
- LoC delta does not exceed project limit (default 250)

## Phase Transition Audit Trail

Every `workflow.py phase <target>` call is logged:
```json
{"from": "phase3_spec", "to": "phase4_approved", "at": "...", "trigger": "user_keyword"}
```
`trigger` values: `user_keyword` | `command` | `manual`

Manual skips (e.g. phase2 → phase6) emit a warning but are not blocked.
Fix-loop counter increments each time phase6_implement is re-entered from phase6b_adversary.

## Execution Log

Written to `.claude/workflows/_log/YYYY-MM-DD_<name>.yaml`:
```yaml
workflow_id: feature-login
project: my-app
phases_completed: [phase1_context, phase2_analyse, ...]
phases_skipped: []
tdd_red_confirmed: true
adversary_verdict: VERIFIED
adversary_fix_loop_iterations: 1
scope_loc_delta: +142
outcome: success
```

## Automatic Phase Detection

Some phase transitions happen automatically:
- User says "approved" → `phase4_approved`
- `/10-context` completed → `phase1_context`
- `/20-analyse` completed → `phase2_analyse`
- `/30-write-spec` completed → `phase3_spec`

## QA Gate (Adversary Validation)

```bash
# Validate test output and set adversary verdict
python3 .claude/hooks/qa_gate.py docs/artifacts/feature/test-output.txt
python3 .claude/hooks/qa_gate.py docs/artifacts/feature/test-output.txt --screenshot screenshot.png
python3 .claude/hooks/qa_gate.py docs/artifacts/feature/test-output.txt --infra --no-visual "pure infrastructure"
```

## Migration from v2

```bash
python3 .claude/hooks/migrate_state.py          # Dry run
python3 .claude/hooks/migrate_state.py --apply   # Actually migrate
```

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

### Complete Workflow
```bash
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
- Artifacts are valid (real files, not placeholders)

## Automatic Phase Detection

Some phase transitions happen automatically:
- User says "approved" → `phase4_approved`
- `/context` completed → `phase1_context`
- `/analyse` completed → `phase2_analyse`
- `/write-spec` completed → `phase3_spec`

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

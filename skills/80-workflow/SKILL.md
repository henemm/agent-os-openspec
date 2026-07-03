---
description: "Manage workflows"
disable-model-invocation: true
---

# Workflow Management

Manage multiple parallel workflows with isolated state (v3).

## Setup

```bash
# Hook-Pfad: (1) CLAUDE_PLUGIN_ROOT (2) installed_plugins.json (3) .claude/hooks
_H="${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/core/hooks}"
if [ -z "$_H" ]; then _p="$(python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")));print(next((e["installPath"] for k,v in d.get("plugins",{}).items() if k.startswith("agent-os-openspec@") for e in [next((x for x in v if x.get("scope")=="user"),v[0])]),""))' 2>/dev/null)"; [ -n "$_p" ] && [ -d "$_p/core/hooks" ] && _H="$_p/core/hooks"; fi
_H="${_H:-.claude/hooks}"
WF="python3 ${_H}/workflow.py"
QA="python3 ${_H}/qa_gate.py"
MS="python3 ${_H}/migrate_state.py"
```

## Commands

### List All Workflows
```bash
$WF list
```

### Check Current Status
```bash
$WF status
```

### Start New Workflow
```bash
$WF start "feature-name"
```

### Switch Active Workflow
```bash
$WF switch "other-feature"
```

### Set Specific Phase
```bash
$WF phase phase4_approved
```

### Set Workflow Fields
```bash
$WF set-field spec_file "docs/specs/auth/login.md"
$WF set-field context_file "docs/context/login.md"
$WF set-affected-files src/auth.py src/login.py
```

### Register Test Artifacts
```bash
$WF add-artifact test_output \
    "docs/artifacts/feature/test-red.txt" \
    "Test FAILED: assertion error" \
    phase5_tdd_red
```

### Mark TDD RED Done
```bash
$WF mark-red "3 tests failed"
$WF mark-ui-red "UI test assertion"
```

### Write Execution Log (Required before complete)
```bash
$WF write-log success
$WF write-log partial
$WF write-log reverted
```
Writes `.claude/workflows/_log/YYYY-MM-DD_<name>.yaml` with phases completed,
adversary verdict, fix-loop count, LoC delta, and outcome.

### Override AMBIGUOUS Adversary Verdict
```bash
$WF override-ambiguous "reason for proceeding"
```
Required when adversary verdict is AMBIGUOUS and all findings are resolved.
Without this, `git commit` is blocked.

### Link to GitHub Issue
```bash
$WF set-field github_issue 42
```

### Override LoC Limit
```bash
$WF set-field loc_limit_override 500
```

### Complete Workflow
```bash
# Requires execution log — will fail without write-log first
$WF complete
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

Every `$WF phase <target>` call is logged:
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
$QA docs/artifacts/feature/test-output.txt
$QA docs/artifacts/feature/test-output.txt --screenshot screenshot.png
$QA docs/artifacts/feature/test-output.txt --infra --no-visual "pure infrastructure"
```

## Migration from v2

```bash
$MS          # Dry run
$MS --apply   # Actually migrate
```

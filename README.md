# Agent OS + OpenSpec Framework

A modular workflow enforcement system for Claude Code that ensures quality through spec-first development, TDD with real artifacts, and domain-specific standards.

**Version**: 3.0.0

## What is Agent OS + OpenSpec?

This framework combines two complementary approaches to AI-assisted development:

- **Agent OS**: Hook-based workflow enforcement for Claude Code
- **OpenSpec**: Spec-first development - no code without specification

Together they provide:
- **8-Phase Workflow**: Structured progression from context to completion
- **Spec-First Development**: No code without approved specifications
- **TDD with Real Artifacts**: Actual screenshots, logs - no placeholders
- **Hook Enforcement**: 4 consolidated hooks (v3) with short-circuit logic
- **Isolated Workflow State**: Per-workflow JSON files, no race conditions
- **Modular Design**: Core system + domain-specific modules

## Quick Start

```bash
# Clone the framework
git clone https://github.com/henemm/agent-os-openspec.git

# Install for your project (core only)
cd agent-os-openspec
python3 setup.py /path/to/your/project

# With iOS/SwiftUI module
python3 setup.py /path/to/your/project --module ios-swiftui

# Update existing installation
python3 setup.py /path/to/your/project --update --force

# Migrate from v2
python3 .claude/hooks/migrate_state.py --apply
```

## The Workflow (v3)

```
phase0_idle → phase1_context → phase2_analyse → phase3_spec
→ phase4_approved → phase5_tdd_red → phase6_implement
→ phase6b_adversary → phase7_validate → phase8_complete
```

## Project Structure

```
agent-os-openspec/
├── config.yaml              # Configuration template
├── setup.py                 # Installation & update tool (v3.0)
├── CLAUDE.md                # Framework documentation
├── CHANGELOG.md             # Version history
│
├── core/
│   ├── hooks/               # v3: 4 consolidated hooks + utilities
│   │   ├── edit_gate.py             # PreToolUse Edit|Write
│   │   ├── bash_gate.py             # PreToolUse Bash
│   │   ├── post_bash.py             # PostToolUse Bash
│   │   ├── phase_listener.py        # UserPromptSubmit
│   │   ├── workflow.py              # Workflow State CLI
│   │   ├── qa_gate.py              # QA Gate (test validation)
│   │   ├── override_token.py       # Shared token management
│   │   ├── migrate_state.py         # v2 → v3 migration
│   │   ├── hook_utils.py            # Shared bootstrap
│   │   └── config_loader.py         # Configuration loader
│   │
│   ├── agents/
│   │   ├── spec-writer.md
│   │   ├── spec-validator.md
│   │   ├── implementation-validator.md
│   │   ├── docs-updater.md
│   │   ├── bug-intake.md
│   │   └── ...
│   │
│   └── commands/
│       ├── 1-context.md             # Phase 1: Collect context
│       ├── 2-analyse.md             # Phase 2: Analyze
│       ├── 3-write-spec.md          # Phase 3: Write spec
│       ├── 4-tdd-red.md             # Phase 5: Failing tests
│       ├── 5-implement.md           # Phase 6: Implement
│       ├── 6-validate.md            # Phase 7: Validate
│       ├── workflow.md              # Workflow management
│       └── add-artifact.md          # Register test artifacts
│
├── modules/                 # Optional domain-specific modules
│   ├── ios-swiftui/
│   └── home-assistant/
│
└── templates/
```

## Slash Commands

| Command | Phase | Description |
|---------|-------|-------------|
| `/context` | 1 | Collect relevant context |
| `/analyse` | 2 | Analyze requirements |
| `/write-spec` | 3 | Create specification |
| `/tdd-red` | 5 | Write failing tests |
| `/implement` | 6 | Implement (make tests green) |
| `/validate` | 7 | Validation |
| `/workflow` | - | Manage workflows |
| `/add-artifact` | - | Register test artifacts |

## Workflow Management (v3)

```bash
# Start workflows
python3 .claude/hooks/workflow.py start "feature-login"
python3 .claude/hooks/workflow.py start "bugfix-crash"

# Switch between workflows
python3 .claude/hooks/workflow.py switch "bugfix-crash"

# List all workflows
python3 .claude/hooks/workflow.py list

# Check active workflow status
python3 .claude/hooks/workflow.py status

# Set phase (with validation)
python3 .claude/hooks/workflow.py phase phase6_implement

# Complete and archive
python3 .claude/hooks/workflow.py complete
```

State is stored as isolated JSON files in `.claude/workflows/`:
```
.claude/workflows/
├── .active              ← Symlink to active workflow
├── feature-login.json
├── bugfix-crash.json
└── _archive/
```

## TDD with Real Artifacts

```bash
# Register artifact
python3 .claude/hooks/workflow.py add-artifact test_output \
    "docs/artifacts/feature/test-red.txt" \
    "Test FAILED: assertion error" \
    phase5_tdd_red

# Mark RED done
python3 .claude/hooks/workflow.py mark-red "3 tests failed"

# Validate test output and set adversary verdict
python3 .claude/hooks/qa_gate.py docs/artifacts/feature/test-output.txt
```

## Hook Architecture (v3)

4 consolidated hooks replace the previous 30+:

| Hook | Trigger | Purpose |
|------|---------|---------|
| `edit_gate.py` | Edit/Write | Phase check, TDD check, stop-lock, override |
| `bash_gate.py` | Bash | Stop-lock, state integrity, secrets, commit gates |
| `post_bash.py` | Bash (post) | Test output detection, adversary verdict |
| `phase_listener.py` | UserPromptSubmit | Approval, stop-lock, override, green |

## Configuration

Customize `openspec.yaml` in your project:

```yaml
strict_code_gate:
  code_extensions: [".swift", ".py", ".ts", ...]
  always_allowed_dirs: ["Tests/", "docs/", "scripts/"]

secrets_guard:
  sensitive_patterns: ["\\.env", "credentials\\.json"]

pre_commit:
  required_staged_files: ["docs/ACTIVE-todos.md"]

modules:
  ios_swiftui:
    enabled: true
```

## Available Modules

### Core (Always Installed)
- 8-phase workflow enforcement
- Spec-first development with approval gate
- TDD with real artifacts
- QA Gate for test validation
- Override token system
- Stop-lock for immediate pause
- Secrets guard

### iOS/SwiftUI Module
- Sim-enforcer (use sim.sh wrapper)
- Build-lock (prevent parallel xcodebuild)
- UI test preflight checks
- Analysis-first bug fixing

### Home Assistant Module
- Config validation before restart
- Dashboard screenshot QA

## License

MIT License - See LICENSE file.

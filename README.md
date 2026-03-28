# Agent OS + OpenSpec Framework

A modular workflow enforcement system for Claude Code that ensures quality through spec-first development, TDD with real artifacts, and domain-specific standards.

**Version**: 2.0.0

## What is Agent OS + OpenSpec?

This framework combines two complementary approaches to AI-assisted development:

- **Agent OS**: Hook-based workflow enforcement for Claude Code
- **OpenSpec**: Spec-first development - no code without specification

Together they provide:
- **8-Phase Workflow**: Structured progression from context to completion
- **Spec-First Development**: No code without approved specifications
- **TDD with Real Artifacts**: Actual screenshots, logs - no placeholders
- **Hook Enforcement**: Automated blocking of rule violations
- **Multi-Workflow Support**: Work on multiple features in parallel
- **Modular Design**: Core system + domain-specific modules

## Why Use This?

Without guardrails, AI coding assistants can:
- Start implementing before understanding the problem
- Create code without documentation
- Skip validation steps
- Write tests that pass without actually testing anything
- Forget edge cases

OpenSpec prevents these issues through **technical enforcement**, not just documentation.

## Quick Start

```bash
# Clone the framework
git clone https://github.com/henemm/agent-os-openspec.git

# Install for your project (core only)
cd agent-os-openspec
python3 setup.py /path/to/your/project

# With iOS/SwiftUI module
python3 setup.py /path/to/your/project --module ios-swiftui

# With Home Assistant module
python3 setup.py /path/to/your/project --module home-assistant

# Update existing installation
python3 setup.py /path/to/your/project --update
```

## The 8-Phase Workflow (v2.0)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         OPENSPEC WORKFLOW v2.0                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  phase0_idle                                                            │
│       │                                                                 │
│       ▼                                                                 │
│  phase1_context ─── /context ───► Collect relevant context              │
│       │                                                                 │
│       ▼                                                                 │
│  phase2_analyse ─── /analyse ───► Analyze requirements                  │
│       │                                                                 │
│       ▼                                                                 │
│  phase3_spec ────── /write-spec ► Write specification                   │
│       │                                                                 │
│       ▼                                                                 │
│  phase4_approved ── "approved" ─► User approval (GATE)                  │
│       │                                                                 │
│       ▼                                                                 │
│  phase5_tdd_red ─── /tdd-red ───► Write tests, MUST FAIL                │
│       │                           + REAL artifacts required!            │
│       ▼                                                                 │
│  phase6_implement ─ /implement ─► Write code, make tests GREEN          │
│       │                                                                 │
│       ▼                                                                 │
│  phase7_validate ── /validate ──► Manual testing, validation            │
│       │                                                                 │
│       ▼                                                                 │
│  phase8_complete ── /deploy ────► Ready for commit/deploy               │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
agent-os-openspec/
├── config.yaml              # Configuration template
├── setup.py                 # Installation & update tool
├── CLAUDE.md                # Framework documentation
├── CHANGELOG.md             # Version history
│
├── core/                    # Core components (always installed)
│   ├── hooks/
│   │   ├── workflow_state_multi.py   # Multi-workflow state manager (v2.0)
│   │   ├── workflow_gate.py          # Phase gate enforcement
│   │   ├── workflow_state_updater.py # Handle approval phrases
│   │   ├── tdd_enforcement.py        # TDD with real artifacts
│   │   ├── spec_enforcement.py       # Require specs
│   │   ├── red_test_gate.py          # Ensure tests fail first
│   │   ├── scope_guard.py            # Limit change scope
│   │   ├── secrets_guard.py          # Prevent secret commits
│   │   ├── pre_commit_gate.py        # Pre-commit validation
│   │   ├── post_implementation_gate.py
│   │   ├── plan_validator.py
│   │   ├── domain_pattern_guard.py
│   │   ├── ui_screenshot_gate.py
│   │   ├── track_changes.py
│   │   ├── claude_md_protection.py   # Prevent CLAUDE.md bloat
│   │   ├── config_loader.py          # Shared configuration
│   │   └── notify_sound.py           # Notifications
│   │
│   ├── agents/
│   │   ├── spec-writer.md            # Create specifications
│   │   ├── spec-validator.md         # Validate specs
│   │   ├── implementation-validator.md # Validate implementations
│   │   ├── docs-updater.md           # Update documentation
│   │   └── bug-intake.md             # Structured bug reports
│   │
│   └── commands/
│       ├── 0-reset.md                # Reset workflow
│       ├── 1-context.md              # Phase 1: Collect context
│       ├── 2-analyse.md              # Phase 2: Analyze
│       ├── 3-write-spec.md           # Phase 3: Write spec
│       ├── 4-tdd-red.md              # Phase 5: Failing tests
│       ├── 5-implement.md            # Phase 6: Implement
│       ├── 6-validate.md             # Phase 7: Validate
│       ├── 7-deploy.md               # Phase 8: Deploy
│       ├── workflow.md               # Workflow management
│       ├── add-artifact.md           # Register test artifacts
│       └── bug.md                    # Bug intake
│
├── modules/                 # Optional domain-specific modules
│   ├── ios-swiftui/         # iOS/SwiftUI development
│   │   ├── config.yaml
│   │   ├── standards/
│   │   ├── agents/
│   │   ├── workflows/
│   │   ├── commands/
│   │   └── templates/
│   │
│   └── home-assistant/      # Home Assistant configuration
│       ├── config.yaml
│       ├── hooks/
│       └── agents/
│
├── templates/               # Spec templates
└── docs/
    └── specs/
        └── _template.md
```

## Slash Commands

| Command | Phase | Description |
|---------|-------|-------------|
| `/context` | 1 | Collect relevant context |
| `/analyse` | 2 | Analyze requirements |
| `/write-spec` | 3 | Create specification |
| `/tdd-red` | 5 | Write failing tests |
| `/implement` | 6 | Implement (make tests green) |
| `/validate` | 7 | Manual validation |
| `/deploy` | 8 | Deploy/commit |
| `/reset` | - | Reset workflow to idle |
| `/workflow` | - | Manage workflows |
| `/add-artifact` | - | Register test artifacts |
| `/bug` | - | Structured bug intake |

## Multi-Workflow Support

Work on multiple features in parallel:

```bash
# Start workflows
python3 .claude/hooks/workflow_state_multi.py start "feature-login"
python3 .claude/hooks/workflow_state_multi.py start "bugfix-crash"

# Switch between workflows
python3 .claude/hooks/workflow_state_multi.py switch "bugfix-crash"

# List all workflows
python3 .claude/hooks/workflow_state_multi.py list

# Check active workflow status
python3 .claude/hooks/workflow_state_multi.py status
```

## TDD with Real Artifacts

The `tdd_enforcement.py` hook enforces real test artifacts:

**Accepted:**
- Screenshots (PNG, JPG) with real content (>1KB)
- Test output logs with actual errors
- API responses as JSON/XML files
- Emails as .eml or .txt

**Blocked:**
- Placeholder text like "[Screenshot here]"
- Empty files
- Artifacts without description
- Artifacts older than 24 hours

```bash
# Register an artifact
python3 -c "
import sys; sys.path.insert(0, '.claude/hooks')
from workflow_state_multi import add_test_artifact, load_state
state = load_state()
add_test_artifact(state['active_workflow'], {
    'type': 'screenshot',
    'path': 'docs/artifacts/feature-x/test-failed.png',
    'description': 'Test failed: Login button not found',
    'phase': 'phase5_tdd_red'
})
"
```

## Available Modules

### Core (Always Installed)
- 8-phase workflow enforcement
- Spec-first development
- TDD with real artifacts
- Multi-workflow support
- Scope guards and secret protection
- CLAUDE.md size protection
- Notification system

### iOS/SwiftUI Module
Standards and best practices for iOS development:
- **Analysis-First**: No quick fixes, understand before changing
- **Scoping Limits**: Max 4-5 files, +/-250 LoC per change
- **TDD Workflow**: RED → GREEN → REFACTOR cycle
- **Localization**: DE/EN support with proper patterns
- **SwiftUI Patterns**: Lifecycle, state management, guard flags

### Home Assistant Module
- Config validation before restart
- Screenshot-based dashboard QA
- Automation testing
- Edge case detection

## Configuration

After installation, customize `openspec.yaml` in your project:

```yaml
# Protected paths that require the workflow
protected_paths:
  - pattern: ".*\\.swift$"
    spec_type: "swift"
  - pattern: "src/.*\\.py$"
    spec_type: "modules"

# Paths that are always allowed
always_allowed:
  - "\\.claude/"
  - "docs/"
  - "\\.md$"

# Enable modules
modules:
  ios_swiftui:
    enabled: true
  home_assistant:
    enabled: false
```

## How Hooks Work

Hooks are Python scripts that run before Claude executes tools:

| Hook | Trigger | Purpose |
|------|---------|---------|
| `workflow_gate.py` | Edit/Write | Block if workflow phase is wrong |
| `workflow_state_multi.py` | - | Multi-workflow state management |
| `tdd_enforcement.py` | Edit/Write | Require real test artifacts |
| `spec_enforcement.py` | Edit/Write | Block if spec missing |
| `red_test_gate.py` | Edit/Write | Ensure tests fail before green |
| `scope_guard.py` | Edit/Write | Limit files/LoC per change |
| `secrets_guard.py` | Edit/Write | Prevent committing secrets |
| `pre_commit_gate.py` | Bash (git) | Pre-commit validation |
| `workflow_state_updater.py` | UserPromptSubmit | Detect approval phrases |

When a hook returns exit code 2, the tool call is blocked and the error message is shown to Claude.

## Writing Specs

Every entity/component needs a spec before implementation:

```markdown
---
entity_id: user_authentication
type: module
created: 2025-12-21
status: draft
---

# User Authentication

## Approval

- [ ] Approved

## Purpose

Handles user login and session management.

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| database | module | Store user data |

## Implementation Details

[Details here]
```

## Workflow State

The workflow state is tracked in `.claude/workflow_state.json`:

```json
{
  "active_workflow": "feature-login",
  "workflows": {
    "feature-login": {
      "current_phase": "phase5_tdd_red",
      "feature_name": "User Login",
      "spec_file": "docs/specs/feature-login.md",
      "spec_approved": true,
      "test_artifacts": []
    }
  }
}
```

## Contributing

Contributions welcome! Areas of interest:
- New domain modules (Web development, Python, Rust, etc.)
- Additional validation hooks
- Improved spec templates
- Documentation

## License

MIT License - See LICENSE file.

## Credits

Developed from real-world usage enforcing quality in iOS and Home Assistant projects.

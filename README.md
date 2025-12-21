# Agent OS + OpenSpec Framework

A modular workflow enforcement system for Claude Code that ensures quality through spec-first development, automated validation, and domain-specific standards.

## What is Agent OS + OpenSpec?

This framework combines two complementary approaches to AI-assisted development:

- **Agent OS**: Domain-specific standards, agents, and workflows (iOS/SwiftUI, Home Assistant, etc.)
- **OpenSpec**: 4-phase workflow enforcement with Python hooks

Together they provide:
- **4-Phase Workflow**: analyse → write-spec → implement → validate
- **Spec-First Development**: No code without specifications
- **Hook Enforcement**: Automated blocking of rule violations
- **Modular Design**: Core system + domain-specific modules
- **Best Practices**: Curated standards for each domain

## Why Use This?

Without guardrails, AI coding assistants can:
- Start implementing before understanding the problem
- Create code without documentation
- Skip validation steps
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
```

## The 4-Phase Workflow

```
User Request
     │
     ▼
┌─────────────┐
│  /analyse   │ ← Understand request, research codebase
└─────────────┘
     │
     ▼
┌─────────────┐
│ /write-spec │ ← Create specification document
└─────────────┘
     │
     ▼
┌─────────────┐
│  "approved" │ ← User reviews and approves spec
└─────────────┘
     │
     ▼
┌─────────────┐
│ /implement  │ ← NOW you can write code
└─────────────┘
     │
     ▼
┌─────────────┐
│  /validate  │ ← Test and verify implementation
└─────────────┘
     │
     ▼
   Commit
```

## Project Structure

```
openspec-framework/
├── config.yaml              # Configuration template
├── setup.py                 # Installation tool
├── README.md
│
├── core/                    # Core components (always installed)
│   ├── hooks/
│   │   ├── config_loader.py      # Shared configuration
│   │   ├── workflow_gate.py      # Enforce 4-phase workflow
│   │   ├── workflow_state_updater.py  # Handle approvals
│   │   ├── spec_enforcement.py   # Require specs
│   │   ├── claude_md_protection.py    # Prevent bloat
│   │   └── notify_sound.py       # Notifications
│   │
│   ├── agents/
│   │   ├── spec-writer.md        # Create specifications
│   │   ├── spec-validator.md     # Validate specs
│   │   ├── docs-updater.md       # Update documentation
│   │   └── bug-intake.md         # Structured bug reports
│   │
│   └── commands/
│       ├── analyse.md
│       ├── write-spec.md
│       ├── implement.md
│       └── validate.md
│
├── modules/                 # Optional domain-specific modules
│   ├── ios-swiftui/         # iOS/SwiftUI development
│   │   ├── config.yaml
│   │   ├── standards/
│   │   │   ├── global/      # Analysis-First, Scoping, Documentation
│   │   │   └── swiftui/     # Lifecycle, Localization, State
│   │   ├── agents/
│   │   │   ├── bug-investigator.md
│   │   │   ├── feature-planner.md
│   │   │   ├── localizer.md
│   │   │   └── test-runner.md
│   │   ├── workflows/
│   │   │   ├── bug-fix-workflow.md
│   │   │   ├── feature-workflow.md
│   │   │   └── release-workflow.md
│   │   ├── commands/
│   │   │   ├── bug.md
│   │   │   ├── feature.md
│   │   │   ├── test.md
│   │   │   └── localize.md
│   │   └── templates/
│   │
│   ├── home-assistant/      # Home Assistant configuration
│   │   ├── config.yaml
│   │   ├── hooks/
│   │   │   ├── check_ha_restart.py
│   │   │   └── lovelace_screenshot_gate.py
│   │   └── agents/
│   │       ├── ha-validator.md
│   │       ├── lovelace-validator.md
│   │       ├── automation-tester.md
│   │       └── implementation-validator.md
│   │
│   └── generic/             # Generic optional hooks
│
├── docs/
│   └── specs/
│       └── _template.md
│
├── templates/               # Configuration templates
└── examples/               # Example projects
```

## Available Modules

### Core (Always Installed)
- 4-phase workflow enforcement
- Spec-first development
- CLAUDE.md size protection
- Notification system

### iOS/SwiftUI Module
Standards and best practices for iOS development:
- **Analysis-First**: No quick fixes, understand before changing
- **Scoping Limits**: Max 4-5 files, +/-250 LoC per change
- **TDD Workflow**: RED → GREEN → REFACTOR cycle
- **Localization**: DE/EN support with proper patterns
- **SwiftUI Patterns**: Lifecycle, state management, guard flags

Agents:
- `bug-investigator` - Systematic bug analysis
- `feature-planner` - Spec-first feature planning
- `localizer` - Localization management
- `test-runner` - Unit test execution

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
| workflow_gate.py | Edit/Write | Block if workflow phase is wrong |
| spec_enforcement.py | Edit/Write | Block if spec missing |
| workflow_state_updater.py | UserPromptSubmit | Detect approval phrases |
| check_ha_restart.py | Bash | Block restart without config check |

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
  "current_phase": "spec_approved",
  "feature_name": "User Authentication",
  "spec_file": "docs/specs/modules/user_authentication.md",
  "spec_approved": true,
  "implementation_done": false,
  "validation_done": false
}
```

## iOS/SwiftUI Specific Commands

When using the ios-swiftui module:

| Command | Agent | Purpose |
|---------|-------|---------|
| `/bug [desc]` | bug-investigator | Analyze bug with Analysis-First |
| `/feature [name]` | feature-planner | Plan feature with OpenSpec |
| `/test` | test-runner | Run unit tests |
| `/localize` | localizer | Check/add localizations |

## Contributing

Contributions welcome! Areas of interest:
- New domain modules (Web development, Python, Rust, etc.)
- Additional validation hooks
- Improved spec templates
- Documentation

## License

MIT License - See LICENSE file.

## Credits

This framework combines:
- **OpenSpec Framework** - Hook-based workflow enforcement
- **Agent OS** - iOS/SwiftUI standards and best practices

Developed from real-world usage enforcing quality in iOS and Home Assistant projects.

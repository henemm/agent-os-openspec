# Agent OS + OpenSpec Framework

A modular workflow enforcement system for Claude Code that ensures quality through spec-first development, TDD with real artifacts, and hook-enforced phase gating.

**Version**: 3.9.0 · [Changelog](CHANGELOG.md) · [GitHub Issues](https://github.com/henemm/agent-os-openspec/issues)

---

## What is this?

This framework combines two complementary approaches to AI-assisted development:

- **Agent OS**: Hook-based workflow enforcement for Claude Code — rules that Claude cannot bypass
- **OpenSpec**: Spec-first development — no code without an approved, testable specification

The core finding from three projects using this framework: *"CLAUDE.md rules are followed with ~60–70% probability. Hooks with 100%."* Every mandatory step in this framework has a corresponding hook. Documentation is a suggestion; hooks are law.

---

## Quick Start

### Option A — As a Claude Code Plugin (recommended)

Since v3.2, the framework ships as an installable [Claude Code plugin](https://docs.claude.com/en/docs/claude-code/plugins). Hooks, agents, and skills (slash commands) are provided globally by the plugin — no files are copied into your project.

```bash
# 1. Register this repo as a marketplace (one-time, any project)
claude plugin marketplace add henemm/agent-os-openspec

# 2. Install the plugin
claude plugin install agent-os-openspec

# 3. Update to the latest version later
claude plugin marketplace update henemm/agent-os-openspec
claude plugin update agent-os-openspec
```

Slash commands are then available with the `agent-os-openspec:` namespace prefix (e.g. `/agent-os-openspec:50-implement`). To get short aliases (`/50-implement`) in a specific project, generate redirect files once:

```bash
cd /path/to/your/project
python3 /path/to/agent-os-openspec/setup.py . --command-aliases
```

Optional domain modules (iOS/SwiftUI, Home Assistant) are enabled per project via `config.yaml` — see [Available Modules](#available-modules).

### Option B — As Framework Files Copied into Your Project

Without the plugin system, `setup.py` copies hooks/agents/commands directly into your project's `.claude/` directory.

```bash
# Clone the framework
git clone https://github.com/henemm/agent-os-openspec.git

# Install for your project (core only)
python3 setup.py /path/to/your/project

# With iOS/SwiftUI module
python3 setup.py /path/to/your/project --module ios-swiftui

# Add short slash-command aliases (e.g. /50-implement instead of /agent-os-openspec:50-implement)
python3 setup.py ~ --command-aliases   # recommended: global (~), covers all projects

# Update an existing installation
python3 setup.py /path/to/your/project --update --force
```

Already on Option B and want to switch to the plugin? Run `python3 migrate_to_plugin.py /path/to/project --apply` — it removes the now-redundant local hook copies and points your project at the plugin instead.

---

## First Conversation Prompt

After installation, paste this into Claude Code to orient it:

**For a new feature:**
```
This project uses the OpenSpec workflow framework (installed in .claude/).
Start a new workflow: python3 .claude/hooks/workflow.py start "feature-[name]"
Then begin with /10-context.
```

**For a bug fix:**
```
This project uses the OpenSpec workflow framework.
Start a workflow: python3 .claude/hooks/workflow.py start "bug-[short-description]"
Then use /00-bug to analyze the root cause before touching any code.
```

**To check current state (resuming an existing session):**
```
Check the active workflow: python3 .claude/hooks/workflow.py status
Then list all workflows: python3 .claude/hooks/workflow.py list
Continue from the current phase.
```

---

## The 8-Phase Workflow

```
phase0_idle
    │
phase1_context ──── /10-context ────► Collect relevant context
    │
phase2_analyse ──── /20-analyse ────► Analyse requirements
    │
phase3_spec ─────── /30-write-spec ─► Write specification (must include AC-N criteria)
    │
phase4_approved ─── "approved" ──► USER GATE — hooks detect keyword
    │
phase5_tdd_red ──── /40-tdd-red ────► Write failing tests (real artifacts required)
    │
phase6_implement ── /50-implement ──► Implement (TDD GREEN)
    │
phase6b_adversary ─ auto ────────► Adversary verification (VERIFIED required to commit)
    │
phase7_validate ─── /60-validate ───► Final validation
    │
phase8_complete ─── write-log ───► Execution log + archive
```

**Gate summary:**

| Gate | What's checked | Consequence if failed |
|------|---------------|----------------------|
| Approval (phase3→4) | `## Architektur-Entscheidung (ADR)` section filled (ADR number or justified "none") | Approval blocked |
| Edit in phase6+ | RED artifacts + `## Acceptance Criteria` in spec | Edit blocked |
| LoC limit | `git diff HEAD` ≤ 250 lines | Edit blocked |
| git commit | Adversary verdict = VERIFIED | Commit blocked |
| AMBIGUOUS verdict | `override-ambiguous` not set | Commit blocked |
| `complete` | Execution log exists | Archive blocked |

---

## Slash Commands

| Command | Phase | Description |
|---------|-------|-------------|
| `/10-context` | 1 | Collect relevant context |
| `/20-analyse` | 2 | Analyse requirements |
| `/30-write-spec` | 3 | Create specification |
| `/40-tdd-red` | 5 | Write failing tests |
| `/50-implement` | 6 | Implement (make tests green) |
| `/60-validate` | 7 | Final validation |
| `/00-bug` | — | Analyse a bug (Analysis-First, creates GitHub Issue) |
| `/01-feature` | — | Plan a new feature (creates GitHub Issue) |
| `/80-workflow` | — | Manage workflows |
| `/81-add-artifact` | — | Register test artifacts |
| `/83-user-story` | — | JTBD-based user story discovery |
| `/82-test` | — | Run tests via test-runner agent |

---

## Workflow CLI Reference

```bash
# Lifecycle
python3 .claude/hooks/workflow.py start "feature-login"
python3 .claude/hooks/workflow.py switch "bugfix-crash"
python3 .claude/hooks/workflow.py status          # phase, LoC delta, log status
python3 .claude/hooks/workflow.py list

# Phase management
python3 .claude/hooks/workflow.py phase phase4_approved
python3 .claude/hooks/workflow.py set-field spec_file "docs/specs/auth/login.md"
python3 .claude/hooks/workflow.py set-field github_issue 42
python3 .claude/hooks/workflow.py set-affected-files src/auth.py src/login.py

# TDD artifacts
python3 .claude/hooks/workflow.py add-artifact test_output "logs/test.log" "3 failed" phase5_tdd_red
python3 .claude/hooks/workflow.py mark-red "3 tests failed"
python3 .claude/hooks/workflow.py mark-ui-red "UI assertion error"

# Adversary handling
python3 .claude/hooks/workflow.py override-ambiguous "edge case accepted, see issue #42"

# LoC override for bulk changes (e.g. translations)
python3 .claude/hooks/workflow.py set-field loc_limit_override 500

# Completion (execution log required)
python3 .claude/hooks/workflow.py write-log success
python3 .claude/hooks/workflow.py complete
```

---

## Spec Format

Every spec must include an `## Acceptance Criteria` section. Without it, code edits in phase6 are blocked.

```markdown
## Acceptance Criteria

- **AC-1:** Given <precondition> / When <action> / Then <observable outcome>
  - Test: (populated after /tdd-red)

- **AC-2:** Given <precondition> / When <action> / Then <observable outcome>
  - Test: (populated after /tdd-red)

## Approval
- [ ] Approved

## GitHub Issue
- **Issue:** #N
```

Template: `templates/spec_template.md`

---

## GitHub Issues as Backlog

All features and bugs are tracked as GitHub Issues. Agents search for existing issues before creating new ones.

```bash
# Search before creating
gh issue list --label "enhancement" --state open
gh issue list --search "keyword" --state open

# Create
gh issue create --title "feat: ..." --label "enhancement"
gh issue create --title "bug: ..." --label "bug"

# Link to workflow
python3 .claude/hooks/workflow.py set-field github_issue 42
```

---

## Hook Architecture (v3)

4 consolidated hooks replace the previous 30+:

| Hook | Trigger | Checks |
|------|---------|--------|
| `edit_gate.py` | Edit/Write | Phase, RED artifacts, Acceptance Criteria, LoC delta, stop-lock, override |
| `bash_gate.py` | Bash | Stop-lock, state integrity, secrets, commit gates (VERIFIED/AMBIGUOUS) |
| `post_bash.py` | Bash (post) | Test output detection, adversary verdict auto-set |
| `phase_listener.py` | UserPromptSubmit | Approval keyword, stop-lock, override token, GREEN signal |

**Exit codes:** `0` = allowed, `2` = blocked (stderr shown to Claude)

---

## Configuration

Customize `openspec.yaml` in your project root:

```yaml
strict_code_gate:
  code_extensions: [".swift", ".py", ".ts"]
  always_allowed_dirs: ["Tests/", "docs/"]

scope_guard:
  max_loc_delta: 250
  loc_exclude_patterns: ["\\.xcstrings$", "\\.po$"]

secrets_guard:
  sensitive_patterns: ["\\.env", "credentials\\.json"]

pre_commit:
  required_staged_files: ["docs/ACTIVE-todos.md"]
  test_command: "pytest --tb=short -q"
```

---

## Project Structure

```
agent-os-openspec/
├── setup.py                 # Install / update tool
├── config.yaml              # Config template
├── CLAUDE.md                # Framework documentation for this repo
├── CHANGELOG.md             # Version history
│
├── core/
│   ├── hooks/               # 4 consolidated hooks + utilities
│   │   ├── edit_gate.py         # PreToolUse Edit|Write
│   │   ├── bash_gate.py         # PreToolUse Bash
│   │   ├── post_bash.py         # PostToolUse Bash
│   │   ├── phase_listener.py    # UserPromptSubmit
│   │   ├── workflow.py          # Workflow State CLI
│   │   ├── qa_gate.py           # Test output validation
│   │   ├── adversary_dialog.py  # Adversary dialog protocol
│   │   ├── override_token.py    # Override token management
│   │   ├── hook_utils.py        # Shared bootstrap
│   │   └── config_loader.py     # YAML config loader
│   ├── agents/              # Agent definitions (Markdown)
│   └── commands/            # Slash command definitions
│
├── modules/                 # Optional domain-specific modules
│   ├── ios-swiftui/         # iOS/SwiftUI: TDD, localization, UI testing
│   └── home-assistant/      # HA: config validation, dashboard QA
│
├── templates/               # Spec templates
│   ├── spec_template.md
│   └── agent_orchestration.md
│
└── timebox-ios/             # Reference project (iOS app using this framework)
```

> **`timebox-ios/`** is a real iOS project that uses this framework. It shows what a deployed installation looks like in practice (`.claude/hooks/`, `.claude/commands/`, `docs/specs/`, etc.). It is not part of the framework itself.

---

## Available Modules

### Core (Always installed)
- 8-phase workflow enforcement
- Spec-first development with human approval gate
- ADR reflection gate at spec approval (grandfathered if section absent, disable via `config.yaml → adr_gate.enabled: false`)
- TDD with real artifacts (screenshots, logs — no placeholders)
- Adversary verification with tri-state verdict (VERIFIED / BROKEN / AMBIGUOUS)
- Fix-loop counter and phase transition audit trail
- Execution log per workflow
- LoC delta enforcement (default 250 lines/workflow)
- Acceptance Criteria format enforcement
- GitHub Issues as backlog
- Override token for emergency bypass
- Stop-lock for immediate pause
- Secrets guard

### iOS/SwiftUI Module (`--module ios-swiftui`)
- Sim-enforcer (use sim.sh instead of direct xcrun)
- Build-lock (prevent parallel xcodebuild)
- UI test preflight: element ID inspection before writing tests
- Localization gate at commit (blocks untranslated strings)
- Analysis-first bug fixing with iOS-specific patterns

### Home Assistant Module (`--module home-assistant`)
- Config validation before service restart
- Dashboard screenshot QA
- Automation testing

---

## Updating an Existing Installation

```bash
# Dry run — see what would change
python3 setup.py /path/to/project --update

# Apply updates (preserves project-specific files)
python3 setup.py /path/to/project --update --force

# Check installed version
cat /path/to/project/.claude/framework_version.json
```

---

## Contributing Improvements

If a pattern emerges in your project that should be generalized:

1. Distil the project-specific details
2. Open an issue with label `workflow-feedback` in this repo
3. Reference which project, what the evidence was, what the proposed change is

See [docs/improvements/README.md](docs/improvements/README.md) for the improvement tracking workflow.

---

## License

MIT License

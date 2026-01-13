# Changelog

All notable changes to the Agent OS + OpenSpec Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added - Backlog Status Tracking (v2.1)

**New Feature: "Spec Ready" Status**
- Separate backlog status tracking (`open`, `spec_ready`, `in_progress`, `done`, `blocked`)
- Prevents false "Done" marking when user pauses after spec approval
- Auto-derives status from phase (can be overridden)
- Pause detection for German/English phrases ("ich höre hier auf", "später implementieren", etc.)

**New CLI Commands:**
- `workflow_state_multi.py backlog <status>` - Set backlog status explicitly
- `workflow_state_multi.py pause` - Pause workflow with appropriate status

**New Functions in `workflow_state_multi.py`:**
- `get_backlog_status()` - Get current backlog status
- `set_backlog_status()` - Explicitly set status
- `pause_workflow()` - Pause with smart status setting
- `is_pause_message()` - Detect pause intent
- `derive_backlog_status()` - Map phase to status
- `sync_backlog_status_from_phase()` - Auto-sync on phase change

**Updated Templates:**
- `ACTIVE-roadmap.md` - New "Spec Ready" section, status legend
- `ACTIVE-todos.md` - New "Spec Ready" section, status legend

**Updated Documentation:**
- `workflow.md` - Backlog status section with mapping table

### Added - Core Improvements

**Multi-Workflow Support:**
- Run multiple features in parallel
- New phase structure with clear numbering (phase0-phase8)
- Phase 1 Context Generation (`/context`) - explicit context gathering
- Phase 5 TDD RED (`/tdd-red`) - write failing tests first
- `/workflow` command for managing parallel workflows
- `/add-artifact` command for registering test evidence
- Automatic v1 to v2 state migration

**New Hooks (from Home Assistant project analysis):**
- `post_implementation_gate.py` - User must approve, Claude cannot self-approve
- `red_test_gate.py` - Blocks code until RED test is documented
- `ui_screenshot_gate.py` - Enforces before/after screenshots for UI changes
- `scope_guard.py` - Prevents scope creep by limiting edits to task-relevant files
- `plan_validator.py` - Validates implementation plans are complete before coding

**New Agents:**
- `implementation-validator.md` - Auto-generates test plans, validates range compatibility, catches edge-case bugs

**TDD Enforcement:**
- TDD enforcement hook with REAL artifact validation
- Separate RED/GREEN test tracking in workflow state
- `red_test_done`, `red_test_result` fields
- `green_test_done`, `green_test_result` fields
- Functions: `mark_red_test_done()`, `mark_green_test_done()`, `get_tdd_status()`

**Configuration:**
- `settings.local.json` support for local overrides (credentials, paths)
- Local overrides NOT committed to git
- Deep merge of config → local overrides

**New Hooks (from gregor_zwanziger project analysis):**
- `domain_pattern_guard.py` - Enforces Single Source of Truth architectural patterns
- `track_changes.py` - Records file changes for pre-test validation
- `pre_commit_gate.py` - Blocks commits if tests are failing (TDD GREEN enforcement)

**New Tools:**
- `validate.py` - Pre-test validation (syntax, imports) before asking user to test
- `output_validator.py` - Validates output formats (email, HTML, JSON) against specs
- `e2e_test_harness.py` - Playwright-based browser E2E testing with screenshot artifacts

**Config Enhancements:**
- `domain_guards` section for architecture enforcement patterns
- `e2e_tests` section for browser test configuration
- `output_specs` section for output format validation
- `pre_commit` section for commit gate configuration
- `validation` section for pre-test validation settings
- Extended `protected_paths` with spec_type mapping for more file types
- E2E validators are now protected (cannot be modified to pass broken code)
- Word-boundary detection for approval phrases (prevents false positives)

**New Hooks (from helix-mvp project analysis):**
- `secrets_guard.py` - Prevents accidental exposure of sensitive files (.env, credentials, keys)
  - Staging mode support: `touch .claude/staging` to allow .env access during development
  - Credentials/keys always blocked even in staging mode

**New Standards:**
- `.agent-os/standards/global/scoping-limits.md` - Keep changes small and focused
  - Max 4-5 files per change
  - Max ±250 lines
  - Guidelines for splitting large tasks

**New Commands (optional templates):**
- `/bug` - Bug analysis with Analysis-First principle
- `/deploy` - Deployment template (customize for your platform)

**Config Enhancements (from helix-mvp):**
- `secrets_guard` section for sensitive file protection
- `scoping` section for change size limits

**New Standards (from Meditationstimer project analysis):**
- `verify-active-code.md` - Always verify editing the ACTIVE file, not duplicates
- `documentation-rules.md` - No false "complete" claims without user verification

**New Commands (from Meditationstimer):**
- `/reset` - Clear workflow state for fresh start
- Staging mode via `.claude/staging` marker file or `OPENSPEC_ENV` env var

### Changed

- Workflow state format v2.0 with multi-workflow support
- Phase names: `analyse_done` → `phase2_analyse`, etc.
- Implementation phase now requires TDD RED artifacts
- `/analyse` is now Phase 2 (after context)
- `/write-spec` is now Phase 3
- `/implement` is now Phase 6 (TDD GREEN)
- Improved error messages with ASCII art and phase-specific guidance
- `config_loader.py` now supports local override files

### Fixed

- Single workflow limitation removed
- Error messages now show correct next step for each phase

## [1.0.0] - 2025-01-12

### Added
- Initial release
- 4-phase workflow: analyse → write-spec → implement → validate
- Core hooks: workflow_gate, spec_enforcement, claude_md_protection
- iOS/SwiftUI module with TDD workflow
- Home Assistant module with config validation
- Setup tool for project installation
- Spec templates and agent definitions

---

## Version Numbering

- **MAJOR**: Breaking changes to workflow or hook interfaces
- **MINOR**: New features, new modules, new commands
- **PATCH**: Bug fixes, documentation updates

## Upgrade Notes

### From 1.x to 2.x

The workflow state format changed from single-workflow to multi-workflow.

**Automatic Migration:**
- Old format is automatically migrated on first load
- No manual intervention needed

**New Features to Adopt:**
1. Use `/context` before `/analyse` for better context gathering
2. Use `/tdd-red` after spec approval for proper TDD
3. Register test artifacts with `/add-artifact`
4. Use `/workflow list` to see all active workflows

**Breaking Changes:**
- Phase names changed (hooks using old names need update)
- TDD enforcement now requires artifacts (can be disabled in config)

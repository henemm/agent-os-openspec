# Changelog

All notable changes to the Agent OS + OpenSpec Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed - Hooks Migrated to hook_utils.py

- **5 hooks** rewritten to use `hook_utils` bootstrap: `override_token_guard`, `override_token_bash_guard`, `adversary_verdict_guard`, `stop_lock_guard`, `docs_location_guard`
- Average 35% boilerplate reduction per hook
- Consistent import pattern: `from hook_utils import setup_path, ...` + `setup_path()`

### Fixed - Agent Frontmatter Consistency

- **analysis-challenger.md, implementation-validator.md:** Standardized tools format from comma-separated string to YAML list

### Added - Hook Utilities Module

- **core/hooks/hook_utils.py:** New shared bootstrap module for all hooks
  - `setup_path()` — adds hooks directory to sys.path
  - `get_tool_input()` / `get_user_message()` / `get_tool_result()` — standardized input parsing
  - `block()` / `allow()` — exit helpers
  - `is_code_file()` / `is_test_file()` — common file checks
  - New hooks should use this instead of duplicating boilerplate

### Changed - Config Cleanup

- **config.yaml:** Removed dead `e2e_tests` and `output_specs` sections (no hook references them)
- **config.yaml:** Fixed `implementation_validator` model from `haiku` to `sonnet`
- **CLAUDE.md:** Updated model assignment table, hook development guide, TDD documentation

### Changed - TDD Enforcement: Configurable Artifact Categories (from timebox-ios)

- **tdd_enforcement.py:** Artifact requirements are now configurable per category via `tdd.artifact_categories` in config.yaml
- Projects can require e.g. both unit AND UI test artifacts (iOS) or just one generic category (default)
- Added `ui_test_output` as valid artifact type
- Added `validate_artifact_timestamps()` — prevents retroactive artifact creation to bypass TDD
- Added `check_user_override()` — respects `user_override` and `spec_approved` workflow flags
- Added infrastructure file skip (`.claude/hooks/`, `docs/specs/` etc.)
- **config.yaml:** Replaced flat `min_artifacts` with structured `artifact_categories` (with example for iOS)

### Changed - Architecture: Centralized find_project_root()

- **4 hooks** (workflow_cleanup, stop_lock_listener, stop_lock_guard, override_token_listener) now import `find_project_root` from `config_loader.py` instead of duplicating the function
- Fallback inline definition kept for robustness if import fails

### Changed - Architecture: Dynamic Module Hook Loading

- **setup.py:** Module hooks are no longer hardcoded in core hook ordering lists
- Module configs (`modules/*/config.yaml`) now define their own `hooks:` section with `edit_write`, `bash`, `post_bash`, `user_prompt` lists
- `generate_settings_json()` reads module configs and appends module hooks to core lists at generation time
- **ios-swiftui/config.yaml:** Added hook ordering (ui_test_preflight, test_lock_guard, on_ui_test_failure, ui_test_debugger_hint)
- **home-assistant/config.yaml:** Added hook ordering (lovelace_screenshot_gate, check_ha_restart)

### Fixed - Critical Bug Fixes

- **workflow_state_multi.py:** `get_tdd_status()` returned `None` when called with explicit workflow name (inverted conditional logic)
- **config_loader.py:** Missing `yaml` import fallback — entire hook system crashed if PyYAML not installed; now warns and continues with defaults
- **pre_commit_gate.py:** Tests that crash without outputting "failed"/"error" were silently considered passing; now any non-zero exit code means failure
- **setup.py:** Removed non-existent `check_claude_md.py` from STOP_HOOK_ORDER
- **setup.py:** Removed module-specific hooks (`ui_test_preflight.py`, `test_lock_guard.py`, `check_ha_restart.py`, `lovelace_screenshot_gate.py`) from core hook ordering — these belong in module installation only

### Fixed - Agent Model Assignments

- **user-story-planner.md:** Added missing `model: opus` (was undeclared, docs said Opus)
- **analysis-challenger.md:** Changed `model: haiku` → `model: sonnet` (analytical work, not mechanical)
- **implementation-validator.md:** Changed `model: haiku` → `model: sonnet` (investigative edge-case probing)

### Fixed - Broken References

- **bug-investigator.md, feature-planner.md:** Fixed standards path from non-existent `.agent-os/standards/` to `core/standards/global/`
- **config.yaml:** Removed dead `hooks.priority` section (has no effect since v2.1; order is defined in setup.py)

### Added

- **core/standards/global/analysis-first.md:** New standard document — was referenced by agents but never created

## [2.1.0] - 2026-03-12

### Added - Adversary Gate System (from my-dayly-sprints)

**Problem:** Claude can claim tests passed without real evidence.
**Solution:** Validates REAL test output (file freshness <30min, size >500 bytes, magic bytes, framework patterns).

**New Hooks:**
- `adversary_gate.py` - PostToolUse Bash: Validates test output, sets `adversary_verdict` in workflow state
- `adversary_verdict_guard.py` - PreToolUse: Blocks direct JSON manipulation of verdict field

**Config:** `adversary_gate.test_patterns` - Configurable per framework (pytest, jest, xcodebuild, go test, cargo test, npm test)

### Added - Stop Lock System (from my-dayly-sprints)

**Problem:** No way to immediately pause Claude.
**Solution:** User says "stop"/"stopp" -> all Edit/Write/Bash blocked until "resume"/"weiter".

**New Hooks:**
- `stop_lock_guard.py` - PreToolUse: MUST BE FIRST HOOK. Blocks all operations when locked.
- `stop_lock_listener.py` - UserPromptSubmit: Creates/removes `.claude/stop.lock`

**Config:** `stop_lock.stop_keywords` / `resume_keywords` - EN+DE defaults

### Added - Override Token System (from my-dayly-sprints)

**Problem:** Sometimes user needs to consciously bypass a gate.
**Solution:** User says "override" -> one-time token created, consumed after single gate pass.

**New Hooks:**
- `override_token_listener.py` - UserPromptSubmit: Creates token
- `override_token_guard.py` - PreToolUse Edit/Write: Protects token file
- `override_token_bash_guard.py` - PreToolUse Bash: Protects token file

**Config:** `override_token.keywords` - Configurable

### Added - Workflow Cleanup (from my-dayly-sprints)

**Problem:** workflow_state_multi.json grows with completed/stale workflows.
**Solution:** Auto-cleanup of phase8_complete + stale (7+ days inactive) workflows. Rate-limited to 1x/hour.

**New Hook:**
- `workflow_cleanup.py` - UserPromptSubmit

**Config:** `workflow_cleanup.stale_days`, `workflow_cleanup.interval_hours`

### Added - Parallel Test Guard (from my-dayly-sprints)

**Problem:** Parallel workflows can interfere during test runs.
**Solution:** Blocks test commands when other active workflows have pending RED tests.

**New Hook:**
- `parallel_test_guard.py` - PreToolUse Bash

**Config:** `parallel_test_guard.test_command_patterns`, `parallel_test_guard.stale_threshold_hours`

### Added - Analysis Challenger Agent (from my-dayly-sprints)

**New Agent:**
- `analysis-challenger.md` - Devil's Advocate for bug analyses. 5 challenges: Symptom Coverage, Call-Site/Dead-Code, Repeated-Fix, Platform Check, Simpler Explanation.

### Changed - Implementation Validator Rewrite (from my-dayly-sprints)

**Rewritten Agent:**
- `implementation-validator.md` - Now an Adversary Agent that actively tries to BREAK the implementation. Issues VERDICT: HOLDS/BROKEN.
- `modules/ios-swiftui/agents/implementation-validator.md` - iOS-specific override with xcodebuild, Simulator, screenshots.

### Changed - Pre-Commit Gate (3 new features)

- `check_todos_staged()` - Blocks commit if configured files not staged
- `check_adversary_verdict()` - Checks VERIFIED verdict in phase6-8
- Override Token cleanup after successful gate pass
- **Config:** `pre_commit.required_staged_files: []`

### Changed - RED Test Gate

- Added `phase6_implement` to enforced phases (previously only phase4/5)

### Changed - UI Screenshot Gate

- Added magic bytes validation (PNG/JPG/GIF/WebP header check)
- Added minimum size check (1KB) to prevent empty placeholder files

### Added - iOS Module Hooks (from my-dayly-sprints)

**New Hooks:**
- `test_lock_guard.py` - PreToolUse Bash: Prevents parallel xcodebuild runs via `pgrep`
- `ui_test_preflight.py` - PreToolUse Edit/Write: Blocks anti-patterns (sleep(), hard-coded coordinates)
- `on_ui_test_failure.py` - PostToolUse Bash: Diagnoses xcodebuild failures (exit 64/65/70)
- `ui_test_debugger_hint.py` - PostToolUse Bash: Recommends ui-test-debugger agent on UI test failures

### Changed - Setup & Configuration

**setup.py:**
- Explicit hook ordering (stop_lock MUST be first)
- PostToolUse hook support (new hook event type)
- Version bumped to 2.1.0

**config.yaml:**
- New sections: `stop_lock`, `override_token`, `parallel_test_guard`, `workflow_cleanup`, `adversary_gate`
- `pre_commit.required_staged_files` option
- Updated hook priority table

---

## [Unreleased]

### Added - Agent Orchestration & Model Strategy (from gregor_zwanzig)

**Model Assignment Strategy:**
- Haiku: Mechanical tasks (validation, context loading, scope reviews, test running)
- Sonnet: Creative/analytical work (spec writing, bug investigation, planning, docs)
- Opus: Core implementation only (main context, not delegated)

**Updated Agents with Model Assignments:**
- `bug-intake.md` - Rewritten with parallel 3x Explore/Haiku subagent dispatching, input contract
- `docs-updater.md` - Extended with model: sonnet, input contract
- `spec-writer.md` - Extended with model: sonnet, input contract, stricter quality rules
- `spec-validator.md` - Extended with model: haiku, strict VALID/INVALID output format
- `bug-investigator.md` - Added model: sonnet
- `test-runner.md` - Added model: haiku

**New Agent:**
- `user-story-planner.md` - JTBD-based User Story Discovery (runs in main context/Opus)

**Updated Commands with Model Dispatching:**
- `/analyse` (2-analyse.md) - Bug vs. Feature routing, 3x parallel Explore/Haiku, Plan/Sonnet assessment
- `/write-spec` (3-write-spec.md) - Sonnet spec creation + Haiku validation with auto-fix loop
- `/implement` (5-implement.md) - Haiku context loading, Opus implementation, parallel side-tasks
- `/validate` (6-validate.md) - 4x parallel Haiku validation + Sonnet auto-fix + docs-updater

**New Template:**
- `templates/agent_orchestration.md` - Reference template for orchestration patterns and model strategy

**Config Updates:**
- Complete agent model assignments in `config.yaml` agents section
- New agents: bug_investigator, test_runner, feature_planner, user_story_planner, implementation_validator

### Added - Agents & Commands (from timebox-ios)

**New Commands:**
- `/user-story` - JTBD-basierte User Story Discovery
- `/feature` - Startet feature-planner Agent (NEU/AENDERUNG Modus)
- `/test` - Startet test-runner Agent

**Details `/user-story`:**
- JTBD-basiertes (Jobs to be Done) User Story Discovery
- Strukturierter Dialog in 4 Phasen:
  1. Kontext klären (Produkt/Feature/Verbesserung)
  2. JTBD Interview (Situation → Job → Ergebnis)
  3. Zusammenfassung validieren
  4. Dokumentieren in `docs/stories/`
- Dimensionen: Funktional, Emotional, Sozial
- Timeline & Alternativen-Analyse
- Output Template mit JTBD Statement und Feature-Ableitung

**New Core Agents:**
- `feature-planner.md` - NEU vs. AENDERUNG Modus, Scoping, Roadmap-Enforcement
- `bug-investigator.md` - Analysis-First Bug-Analyse, Root Cause Identifikation
- `test-runner.md` - Generischer Test-Runner mit Multi-Platform Support

**New iOS/SwiftUI Module Agents:**
- `mock-data-generator.md` - Mock-Daten fuer UI Tests erstellen
- `ui-test-debugger.md` - XCUITest Diagnose (Environment, Timing, State)

**New Hooks (from timebox-ios):**
- `strict_code_gate.py` - Blocks ALL code changes without active workflow + TDD
  - Whitelist-Approach: Tests, docs, config always allowed
  - Requires phase6+ for implementation
  - Enforces affected_files scope check
  - Configurable via `strict_code_gate` section in config.yaml
- `docs_location_guard.py` - Prevents writing to wrong directories
  - Blocks nested duplicates (e.g., `src/docs/` instead of `docs/`)
  - Configurable blocked paths via `docs_location` section
- `ui_test_gate.py` - Blocks validation without UI tests
  - Requires ui_test_green_done or UI artifacts
  - Disabled by default, enable via `ui_test_gate.enabled: true`

**New Config Sections:**
- `strict_code_gate` - Code extension whitelist, allowed dirs/patterns
- `docs_location` - Blocked path mappings
- `ui_test_gate` - UI test requirements

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

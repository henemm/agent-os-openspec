#!/usr/bin/env python3
"""
OpenSpec Framework - Setup Tool

Installs and configures the OpenSpec framework for a new project.

Usage:
    python3 setup.py /path/to/project [--module home-assistant]
    python3 setup.py /path/to/project --update
    python3 setup.py --help

This tool:
1. Creates .claude/ directory structure
2. Copies core hooks and commands
3. Optionally installs module-specific components
4. Generates settings.json with hook configuration
5. Creates initial docs/ structure
6. Can update existing installations with --update
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime
import hashlib


FRAMEWORK_VERSION = "2.0.0"
FRAMEWORK_ROOT = Path(__file__).parent
CORE_DIR = FRAMEWORK_ROOT / "core"
MODULES_DIR = FRAMEWORK_ROOT / "modules"


def get_file_hash(path: Path) -> str:
    """Get MD5 hash of a file for comparison."""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def should_update_file(src: Path, dst: Path, force: bool = False) -> tuple[bool, str]:
    """
    Determine if a file should be updated.
    Returns (should_update, reason).
    """
    if not dst.exists():
        return True, "new file"

    if force:
        return True, "forced update"

    src_hash = get_file_hash(src)
    dst_hash = get_file_hash(dst)

    if src_hash != dst_hash:
        return True, "content changed"

    return False, "unchanged"


def create_directory_structure(project_path: Path):
    """Create the .claude/, .agent-os/, and docs/ directory structure."""
    dirs = [
        ".claude/hooks",
        ".claude/agents",
        ".claude/commands",
        ".claude/tools",
        ".claude/artifacts/screenshots",
        ".agent-os/standards/global",
        "docs/specs",
        "docs/reference",
        "docs/features",
        "docs/project",
    ]

    for d in dirs:
        (project_path / d).mkdir(parents=True, exist_ok=True)
        print(f"  Created: {d}/")


def copy_core_components(project_path: Path):
    """Copy core hooks, agents, commands, and tools."""
    # Copy hooks
    hooks_src = CORE_DIR / "hooks"
    hooks_dst = project_path / ".claude" / "hooks"

    for hook_file in hooks_src.glob("*.py"):
        shutil.copy(hook_file, hooks_dst / hook_file.name)
        print(f"  Copied hook: {hook_file.name}")

    # Copy agents
    agents_src = CORE_DIR / "agents"
    agents_dst = project_path / ".claude" / "agents"

    for agent_file in agents_src.glob("*.md"):
        shutil.copy(agent_file, agents_dst / agent_file.name)
        print(f"  Copied agent: {agent_file.name}")

    # Copy commands
    commands_src = CORE_DIR / "commands"
    commands_dst = project_path / ".claude" / "commands"

    for cmd_file in commands_src.glob("*.md"):
        shutil.copy(cmd_file, commands_dst / cmd_file.name)
        print(f"  Copied command: {cmd_file.name}")

    # Copy tools (v2.0 - validation, E2E testing, output validation)
    tools_src = CORE_DIR / "tools"
    tools_dst = project_path / ".claude" / "tools"

    if tools_src.exists():
        tools_dst.mkdir(parents=True, exist_ok=True)
        for tool_file in tools_src.glob("*.py"):
            shutil.copy(tool_file, tools_dst / tool_file.name)
            print(f"  Copied tool: {tool_file.name}")

    # Copy standards (v2.0 - scoping limits, testing, etc.)
    standards_src = CORE_DIR / "standards"
    standards_dst = project_path / ".agent-os" / "standards"

    if standards_src.exists():
        for subdir in standards_src.iterdir():
            if subdir.is_dir():
                dst_subdir = standards_dst / subdir.name
                dst_subdir.mkdir(parents=True, exist_ok=True)
                for std_file in subdir.glob("*.md"):
                    shutil.copy(std_file, dst_subdir / std_file.name)
                    print(f"  Copied standard: {subdir.name}/{std_file.name}")


def install_module(project_path: Path, module_name: str):
    """Install a specific module."""
    module_dir = MODULES_DIR / module_name

    if not module_dir.exists():
        print(f"  ERROR: Module '{module_name}' not found")
        return False

    # Copy module hooks
    hooks_src = module_dir / "hooks"
    if hooks_src.exists():
        hooks_dst = project_path / ".claude" / "hooks"
        for hook_file in hooks_src.glob("*.py"):
            shutil.copy(hook_file, hooks_dst / hook_file.name)
            print(f"  Copied module hook: {hook_file.name}")

    # Copy module agents
    agents_src = module_dir / "agents"
    if agents_src.exists():
        agents_dst = project_path / ".claude" / "agents"
        for agent_file in agents_src.glob("*.md"):
            shutil.copy(agent_file, agents_dst / agent_file.name)
            print(f"  Copied module agent: {agent_file.name}")

    # Copy module commands (slash commands)
    commands_src = module_dir / "commands"
    if commands_src.exists():
        commands_dst = project_path / ".claude" / "commands"
        for cmd_file in commands_src.glob("*.md"):
            shutil.copy(cmd_file, commands_dst / cmd_file.name)
            print(f"  Copied module command: {cmd_file.name}")

    # Copy module tools
    tools_src = module_dir / "tools"
    if tools_src.exists():
        tools_dst = project_path / "tools"
        tools_dst.mkdir(exist_ok=True)
        for tool_file in tools_src.glob("*"):
            if tool_file.is_file():
                shutil.copy(tool_file, tools_dst / tool_file.name)
                print(f"  Copied tool: {tool_file.name}")

    # Copy module standards (for ios-swiftui and similar modules)
    standards_src = module_dir / "standards"
    if standards_src.exists():
        standards_dst = project_path / ".agent-os" / "standards"
        for subdir in standards_src.iterdir():
            if subdir.is_dir():
                dst_subdir = standards_dst / subdir.name
                dst_subdir.mkdir(parents=True, exist_ok=True)
                for std_file in subdir.glob("*.md"):
                    shutil.copy(std_file, dst_subdir / std_file.name)
                    print(f"  Copied standard: {subdir.name}/{std_file.name}")

    # Copy module workflows
    workflows_src = module_dir / "workflows"
    if workflows_src.exists():
        workflows_dst = project_path / ".agent-os" / "workflows"
        workflows_dst.mkdir(parents=True, exist_ok=True)
        for wf_file in workflows_src.glob("*.md"):
            shutil.copy(wf_file, workflows_dst / wf_file.name)
            print(f"  Copied workflow: {wf_file.name}")

    # Copy module templates
    templates_src = module_dir / "templates"
    if templates_src.exists():
        docs_dst = project_path / "DOCS"
        docs_dst.mkdir(exist_ok=True)
        for tmpl_file in templates_src.glob("*.md"):
            shutil.copy(tmpl_file, docs_dst / tmpl_file.name)
            print(f"  Copied template: {tmpl_file.name}")

    # Copy module config
    module_config = module_dir / "config.yaml"
    if module_config.exists():
        dst = project_path / ".claude" / f"module_{module_name}.yaml"
        shutil.copy(module_config, dst)
        print(f"  Copied module config: module_{module_name}.yaml")

    return True


def generate_settings_json(project_path: Path, modules: list):
    """Generate .claude/settings.json with hook configuration."""
    hooks_dir = project_path / ".claude" / "hooks"

    # Collect all hooks
    edit_write_hooks = []
    bash_hooks = []
    read_hooks = []
    stop_hooks = []
    user_prompt_hooks = []

    for hook_file in sorted(hooks_dir.glob("*.py")):
        hook_name = hook_file.name
        hook_path = str(hooks_dir / hook_name)

        # Categorize hooks based on their purpose
        # Edit/Write hooks - block file modifications based on workflow state
        if hook_name in [
            # Core workflow hooks
            "workflow_gate.py",
            "spec_enforcement.py",
            "claude_md_protection.py",
            # TDD enforcement (v2.0)
            "tdd_enforcement.py",
            "red_test_gate.py",
            # Quality gates (v2.0 - from Home Assistant)
            "post_implementation_gate.py",
            "scope_guard.py",
            "plan_validator.py",
            # UI validation
            "ui_screenshot_gate.py",
            "lovelace_screenshot_gate.py",
            # Architecture enforcement (v2.0 - from gregor_zwanziger)
            "domain_pattern_guard.py",
            # Change tracking (runs on Edit/Write but never blocks)
            "track_changes.py",
        ]:
            edit_write_hooks.append(hook_path)
        # Bash hooks - validate shell commands
        elif hook_name in [
            "check_ha_restart.py",
            # Commit gate (v2.0 - from gregor_zwanziger)
            "pre_commit_gate.py",
            # Secrets guard (v2.0 - from helix-mvp) - blocks sensitive file access
            "secrets_guard.py",
        ]:
            bash_hooks.append(hook_path)
        # Read hooks - validate file reads (v2.0)
        elif hook_name in [
            # Secrets guard - blocks reading sensitive files
            "secrets_guard.py",
        ]:
            read_hooks.append(hook_path)
        # Stop hooks - run when Claude stops responding
        elif hook_name in ["notify_sound.py", "check_claude_md.py"]:
            stop_hooks.append(hook_path)
        # UserPromptSubmit hooks - process user input
        elif hook_name == "workflow_state_updater.py":
            user_prompt_hooks.append(hook_path)
        # Libraries (imported by hooks, not run directly):
        # - workflow_state_multi.py
        # - config_loader.py

    settings = {
        "permissions": {
            "allow": ["Bash", "WebSearch", "WebFetch"],
            "deny": [],
            "ask": []
        },
        "hooks": {
            "PreToolUse": [],
            "Stop": [],
            "UserPromptSubmit": []
        }
    }

    # Add Edit/Write hooks
    if edit_write_hooks:
        settings["hooks"]["PreToolUse"].append({
            "matcher": "Edit|Write",
            "hooks": [
                {"type": "command", "command": f"python3 {h}", "timeout": 5}
                for h in edit_write_hooks
            ]
        })

    # Add Bash hooks
    if bash_hooks:
        settings["hooks"]["PreToolUse"].append({
            "matcher": "Bash",
            "hooks": [
                {"type": "command", "command": f"python3 {h}", "timeout": 5}
                for h in bash_hooks
            ]
        })

    # Add Read hooks (v2.0 - secrets guard)
    if read_hooks:
        settings["hooks"]["PreToolUse"].append({
            "matcher": "Read",
            "hooks": [
                {"type": "command", "command": f"python3 {h}", "timeout": 5}
                for h in read_hooks
            ]
        })

    # Add Stop hooks
    if stop_hooks:
        settings["hooks"]["Stop"].append({
            "hooks": [
                {"type": "command", "command": f"python3 {h}", "timeout": 5}
                for h in stop_hooks
            ]
        })

    # Add UserPromptSubmit hooks
    if user_prompt_hooks:
        settings["hooks"]["UserPromptSubmit"].append({
            "hooks": [
                {"type": "command", "command": f"python3 {h}", "timeout": 5}
                for h in user_prompt_hooks
            ]
        })

    settings_path = project_path / ".claude" / "settings.json"
    with open(settings_path, 'w') as f:
        json.dump(settings, f, indent=2)

    print(f"  Generated: .claude/settings.json")


def generate_config_yaml(project_path: Path, modules: list):
    """Generate project-level config.yaml."""
    config_src = FRAMEWORK_ROOT / "config.yaml"
    config_dst = project_path / "openspec.yaml"

    if config_src.exists():
        shutil.copy(config_src, config_dst)

        # Update project path in config
        content = config_dst.read_text()
        content = content.replace(
            'base_path: "/path/to/project"',
            f'base_path: "{project_path}"'
        )
        content = content.replace(
            'name: "My Project"',
            f'name: "{project_path.name}"'
        )

        # Enable modules
        for module in modules:
            content = content.replace(
                f'{module.replace("-", "_")}:\n    enabled: false',
                f'{module.replace("-", "_")}:\n    enabled: true'
            )

        config_dst.write_text(content)
        print(f"  Generated: openspec.yaml")


def create_spec_template(project_path: Path):
    """Create the spec template file."""
    template_content = '''---
entity_id: entity_name
type: module
created: {date}
updated: {date}
status: draft
version: "1.0"
tags: []
---

# Entity Name

## Approval

- [ ] Approved

## Purpose

[1-2 sentences: What does this entity do? Why does it exist?]

## Source

- **File:** `path/to/file`
- **Identifier:** `class/function name`

## Dependencies

| Entity | Type | Purpose |
|--------|------|---------|
| | | |

## Implementation Details

```
[Code or logic description]
```

## Expected Behavior

- **Input:** [description]
- **Output:** [description]
- **Side effects:** [if any]

## Known Limitations

- [Any limitations or edge cases]

## Changelog

- {date}: Initial spec created
'''.format(date=datetime.now().strftime("%Y-%m-%d"))

    template_path = project_path / "docs" / "specs" / "_template.md"
    template_path.write_text(template_content)
    print(f"  Created: docs/specs/_template.md")


def create_workflow_state(project_path: Path):
    """Create initial workflow state file."""
    state = {
        "current_phase": "idle",
        "feature_name": None,
        "spec_file": None,
        "spec_approved": False,
        "tasks_created": False,
        "implementation_done": False,
        "validation_done": False,
        "phases_completed": [],
        "last_updated": datetime.now().isoformat()
    }

    state_path = project_path / ".claude" / "workflow_state.json"
    with open(state_path, 'w') as f:
        json.dump(state, f, indent=2)

    print(f"  Created: .claude/workflow_state.json")


def create_claude_md(project_path: Path):
    """Create initial CLAUDE.md file."""
    content = f'''# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Workflow

This project uses the **OpenSpec 4-Phase Workflow**:

| Phase | Command | Purpose |
|-------|---------|---------|
| 1 | `/analyse` | Understand request, research codebase |
| 2 | `/write-spec` | Create specification |
| 3 | User: "approved" | Spec approval |
| 4 | `/implement` | Implement according to spec |
| 5 | `/validate` | Validate before commit |

**Hooks enforce this workflow!** Edit/Write on protected files is blocked unless the workflow is followed.

## Quick Commands

```bash
# Slash commands
/analyse      # Start analysis phase
/write-spec   # Create specification
/implement    # Implement (after approval)
/validate     # Validate implementation
```

## Specs

All entities/components need specs before implementation:
- Template: `docs/specs/_template.md`
- Location: `docs/specs/[category]/[entity].md`

## Documentation Structure

- `docs/specs/` - Entity specifications
- `docs/features/` - Feature documentation
- `docs/reference/` - Technical reference
- `docs/project/` - Project management

---

Generated by OpenSpec Framework on {datetime.now().strftime("%Y-%m-%d")}
'''

    claude_md_path = project_path / "CLAUDE.md"
    if not claude_md_path.exists():
        claude_md_path.write_text(content)
        print(f"  Created: CLAUDE.md")
    else:
        print(f"  Skipped: CLAUDE.md (already exists)")


def update_project(project_path: Path, modules: list, force: bool = False):
    """Update an existing project installation."""
    print(f"\nOpenSpec Framework Update")
    print(f"=========================")
    print(f"Framework version: {FRAMEWORK_VERSION}")
    print(f"Project: {project_path}")
    print()

    # Track changes
    updated = []
    skipped = []
    new_files = []

    # Update core hooks
    hooks_src = CORE_DIR / "hooks"
    hooks_dst = project_path / ".claude" / "hooks"

    if hooks_dst.exists():
        for hook_file in hooks_src.glob("*.py"):
            dst = hooks_dst / hook_file.name
            should_update, reason = should_update_file(hook_file, dst, force)

            if should_update:
                shutil.copy(hook_file, dst)
                if reason == "new file":
                    new_files.append(f"hook: {hook_file.name}")
                else:
                    updated.append(f"hook: {hook_file.name}")
            else:
                skipped.append(f"hook: {hook_file.name}")

    # Update core commands
    commands_src = CORE_DIR / "commands"
    commands_dst = project_path / ".claude" / "commands"

    if commands_dst.exists():
        for cmd_file in commands_src.glob("*.md"):
            dst = commands_dst / cmd_file.name
            should_update, reason = should_update_file(cmd_file, dst, force)

            if should_update:
                shutil.copy(cmd_file, dst)
                if reason == "new file":
                    new_files.append(f"command: {cmd_file.name}")
                else:
                    updated.append(f"command: {cmd_file.name}")
            else:
                skipped.append(f"command: {cmd_file.name}")

    # Update core agents
    agents_src = CORE_DIR / "agents"
    agents_dst = project_path / ".claude" / "agents"

    if agents_dst.exists():
        for agent_file in agents_src.glob("*.md"):
            dst = agents_dst / agent_file.name
            should_update, reason = should_update_file(agent_file, dst, force)

            if should_update:
                shutil.copy(agent_file, dst)
                if reason == "new file":
                    new_files.append(f"agent: {agent_file.name}")
                else:
                    updated.append(f"agent: {agent_file.name}")
            else:
                skipped.append(f"agent: {agent_file.name}")

    # Update core tools (v2.0)
    tools_src = CORE_DIR / "tools"
    tools_dst = project_path / ".claude" / "tools"

    if tools_src.exists():
        tools_dst.mkdir(parents=True, exist_ok=True)
        for tool_file in tools_src.glob("*.py"):
            dst = tools_dst / tool_file.name
            should_update, reason = should_update_file(tool_file, dst, force)

            if should_update:
                shutil.copy(tool_file, dst)
                if reason == "new file":
                    new_files.append(f"tool: {tool_file.name}")
                else:
                    updated.append(f"tool: {tool_file.name}")
            else:
                skipped.append(f"tool: {tool_file.name}")

    # Update modules
    for module in modules:
        module_dir = MODULES_DIR / module
        if module_dir.exists():
            print(f"\nUpdating module: {module}...")
            # Similar logic for module files...
            install_module(project_path, module)

    # Update version tracking
    version_file = project_path / ".claude" / "framework_version.json"
    version_info = {
        "framework_version": FRAMEWORK_VERSION,
        "last_updated": datetime.now().isoformat(),
        "installed_modules": modules,
    }
    with open(version_file, 'w') as f:
        json.dump(version_info, f, indent=2)

    # Print summary
    print("\n" + "=" * 50)
    print("Update Summary")
    print("=" * 50)

    if new_files:
        print(f"\nNew files ({len(new_files)}):")
        for f in new_files:
            print(f"  + {f}")

    if updated:
        print(f"\nUpdated ({len(updated)}):")
        for f in updated:
            print(f"  ~ {f}")

    if skipped and not force:
        print(f"\nUnchanged ({len(skipped)}): Use --force to overwrite all")

    print(f"\nFramework updated to version {FRAMEWORK_VERSION}")


def main():
    parser = argparse.ArgumentParser(
        description="Install or update OpenSpec Framework for a project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fresh installation
  python3 setup.py /path/to/project
  python3 setup.py /path/to/project --module home-assistant

  # Update existing installation
  python3 setup.py /path/to/project --update
  python3 setup.py /path/to/project --update --force

Available modules:
  ios-swiftui     - iOS/SwiftUI standards, agents, and workflows
  home-assistant  - Home Assistant specific hooks and agents
  generic         - Generic optional hooks (bug tracking, etc.)
"""
    )

    parser.add_argument(
        "project_path",
        help="Path to the project to install framework into"
    )

    parser.add_argument(
        "--module", "-m",
        action="append",
        dest="modules",
        default=[],
        help="Install specific module (can be used multiple times)"
    )

    parser.add_argument(
        "--update", "-u",
        action="store_true",
        help="Update existing installation instead of fresh install"
    )

    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force overwrite all files during update"
    )

    parser.add_argument(
        "--skip-hooks",
        action="store_true",
        help="Skip generating settings.json hooks configuration"
    )

    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"OpenSpec Framework {FRAMEWORK_VERSION}"
    )

    args = parser.parse_args()

    project_path = Path(args.project_path).resolve()

    if not project_path.exists():
        print(f"ERROR: Project path does not exist: {project_path}")
        sys.exit(1)

    # Update mode
    if args.update:
        update_project(project_path, args.modules, args.force)
        return

    # Fresh installation
    print(f"\nOpenSpec Framework Setup")
    print(f"========================")
    print(f"Framework version: {FRAMEWORK_VERSION}")
    print(f"Project: {project_path}")
    print(f"Modules: {args.modules or ['core only']}")
    print()

    print("Creating directory structure...")
    create_directory_structure(project_path)

    # Also create artifacts directory for TDD
    (project_path / "docs" / "artifacts").mkdir(parents=True, exist_ok=True)
    (project_path / "docs" / "context").mkdir(parents=True, exist_ok=True)
    print("  Created: docs/artifacts/")
    print("  Created: docs/context/")

    print("\nCopying core components...")
    copy_core_components(project_path)

    for module in args.modules:
        print(f"\nInstalling module: {module}...")
        install_module(project_path, module)

    print("\nGenerating configuration...")
    generate_config_yaml(project_path, args.modules)
    create_spec_template(project_path)
    create_workflow_state(project_path)

    # Save version info
    version_file = project_path / ".claude" / "framework_version.json"
    version_info = {
        "framework_version": FRAMEWORK_VERSION,
        "installed": datetime.now().isoformat(),
        "installed_modules": args.modules,
    }
    with open(version_file, 'w') as f:
        json.dump(version_info, f, indent=2)
    print("  Created: .claude/framework_version.json")

    if not args.skip_hooks:
        generate_settings_json(project_path, args.modules)

    print("\nCreating CLAUDE.md...")
    create_claude_md(project_path)

    print("\n" + "=" * 50)
    print("Setup complete!")
    print("=" * 50)
    print(f"""
Framework version: {FRAMEWORK_VERSION}

New Workflow (v2.0):
  /context   -> Gather relevant context (Phase 1)
  /analyse   -> Analyse requirements (Phase 2)
  /write-spec -> Create specification (Phase 3)
  "approved" -> User approval (Phase 4)
  /tdd-red   -> Write failing tests (Phase 5)
  /implement -> Make tests pass (Phase 6)
  /validate  -> Manual testing (Phase 7)

Parallel workflows supported! Use /workflow to manage.

Next steps:
1. Review openspec.yaml and customize for your project
2. Update protected_paths to match your project structure
3. Add specs to docs/specs/ as you develop
""")


if __name__ == "__main__":
    main()

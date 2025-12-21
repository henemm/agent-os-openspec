#!/usr/bin/env python3
"""
OpenSpec Framework - Setup Tool

Installs and configures the OpenSpec framework for a new project.

Usage:
    python3 setup.py /path/to/project [--module home-assistant]
    python3 setup.py --help

This tool:
1. Creates .claude/ directory structure
2. Copies core hooks and commands
3. Optionally installs module-specific components
4. Generates settings.json with hook configuration
5. Creates initial docs/ structure
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime


FRAMEWORK_ROOT = Path(__file__).parent
CORE_DIR = FRAMEWORK_ROOT / "core"
MODULES_DIR = FRAMEWORK_ROOT / "modules"


def create_directory_structure(project_path: Path):
    """Create the .claude/ and docs/ directory structure."""
    dirs = [
        ".claude/hooks",
        ".claude/agents",
        ".claude/commands",
        "docs/specs",
        "docs/reference",
        "docs/features",
        "docs/project",
    ]

    for d in dirs:
        (project_path / d).mkdir(parents=True, exist_ok=True)
        print(f"  Created: {d}/")


def copy_core_components(project_path: Path):
    """Copy core hooks, agents, and commands."""
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
    stop_hooks = []
    user_prompt_hooks = []

    for hook_file in sorted(hooks_dir.glob("*.py")):
        hook_name = hook_file.name
        hook_path = str(hooks_dir / hook_name)

        # Categorize hooks based on their purpose
        if hook_name in ["workflow_gate.py", "spec_enforcement.py", "claude_md_protection.py"]:
            edit_write_hooks.append(hook_path)
        elif hook_name in ["check_ha_restart.py"]:
            bash_hooks.append(hook_path)
        elif hook_name == "lovelace_screenshot_gate.py":
            edit_write_hooks.append(hook_path)
        elif hook_name in ["notify_sound.py", "check_claude_md.py"]:
            stop_hooks.append(hook_path)
        elif hook_name == "workflow_state_updater.py":
            user_prompt_hooks.append(hook_path)

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


def main():
    parser = argparse.ArgumentParser(
        description="Install OpenSpec Framework for a project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 setup.py /path/to/project
  python3 setup.py /path/to/project --module home-assistant
  python3 setup.py . --module home-assistant

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
        "--skip-hooks",
        action="store_true",
        help="Skip generating settings.json hooks configuration"
    )

    args = parser.parse_args()

    project_path = Path(args.project_path).resolve()

    if not project_path.exists():
        print(f"ERROR: Project path does not exist: {project_path}")
        sys.exit(1)

    print(f"\nOpenSpec Framework Setup")
    print(f"========================")
    print(f"Project: {project_path}")
    print(f"Modules: {args.modules or ['core only']}")
    print()

    print("Creating directory structure...")
    create_directory_structure(project_path)

    print("\nCopying core components...")
    copy_core_components(project_path)

    for module in args.modules:
        print(f"\nInstalling module: {module}...")
        install_module(project_path, module)

    print("\nGenerating configuration...")
    generate_config_yaml(project_path, args.modules)
    create_spec_template(project_path)
    create_workflow_state(project_path)

    if not args.skip_hooks:
        generate_settings_json(project_path, args.modules)

    print("\nCreating CLAUDE.md...")
    create_claude_md(project_path)

    print("\n" + "=" * 50)
    print("Setup complete!")
    print("=" * 50)
    print(f"""
Next steps:
1. Review openspec.yaml and customize for your project
2. Update protected_paths to match your project structure
3. Add specs to docs/specs/ as you develop

Workflow:
  /analyse -> /write-spec -> "approved" -> /implement -> /validate

For more info: https://github.com/your-repo/openspec-framework
""")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
OpenSpec Framework - Scope Guard

Prevents Claude from drifting outside the current task scope.

Problem solved:
- User says: "Create hook and agent"
- Claude creates hook, agent, and then fixes an unrelated bug
- The bug fix was NOT part of the request

This hook:
- Reads current task definition from .claude/current_task.json
- Checks if the file being modified is within allowed paths
- Blocks modifications outside the task scope

Task File: .claude/current_task.json
Contains: {task: "description", allowed_paths: [...], task_type: "..."}

Exit Codes:
- 0: Allowed (no task, path allowed, or exempt)
- 2: Blocked (path not in allowed_paths for current task)
"""

import json
import sys
import os
from pathlib import Path

# Try to import config loader
try:
    from config_loader import get_project_root
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import get_project_root
    except ImportError:
        def get_project_root():
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                if (parent / ".git").exists():
                    return parent
            return cwd


def get_task_file() -> Path:
    """Get path to current task file."""
    return get_project_root() / ".claude" / "current_task.json"


# Mapping of task types to default allowed paths
# Can be extended in config.yaml
TASK_PATH_MAPPING = {
    'hook': ['.claude/hooks/', '.claude/settings'],
    'agent': ['.claude/agents/'],
    'command': ['.claude/commands/'],
    'documentation': ['docs/', 'CLAUDE.md', 'README'],
    'test': ['test', 'spec', '__tests__'],
    'config': ['config', '.yaml', '.yml', '.json', '.toml'],
    'feature': ['src/', 'lib/', 'app/'],
    'bugfix': ['src/', 'lib/', 'app/', 'test'],
}

# Paths that are always allowed regardless of task
ALWAYS_ALLOWED = [
    '.claude/workflow_state.json',
    '.claude/current_task.json',
    '.claude/pending_validation.json',
    'docs/artifacts/',
    'docs/context/',
]


def load_task() -> dict | None:
    """Load current task definition."""
    task_file = get_task_file()
    if not task_file.exists():
        return None
    try:
        with open(task_file, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def is_always_allowed(file_path: str) -> bool:
    """Check if path is always allowed."""
    for allowed in ALWAYS_ALLOWED:
        if allowed in file_path:
            return True
    return False


def is_path_allowed(file_path: str, allowed_paths: list) -> bool:
    """Check if file path matches any allowed paths."""
    for allowed in allowed_paths:
        if allowed in file_path:
            return True
    return False


def detect_task_type(file_path: str) -> str | None:
    """Detect task type based on file path."""
    for task_type, paths in TASK_PATH_MAPPING.items():
        for path in paths:
            if path in file_path:
                return task_type
    return None


def get_allowed_paths_for_type(task_type: str) -> list:
    """Get allowed paths for a task type."""
    return TASK_PATH_MAPPING.get(task_type, [])


def main():
    # Get tool input
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")

    if not tool_input:
        try:
            data = json.load(sys.stdin)
            tool_input = json.dumps(data.get("tool_input", {}))
        except (json.JSONDecodeError, Exception):
            sys.exit(0)

    try:
        data = json.loads(tool_input) if isinstance(tool_input, str) else tool_input
        file_path = data.get("file_path", "")
    except json.JSONDecodeError:
        file_path = ""

    if not file_path:
        sys.exit(0)

    # Always-allowed paths pass through
    if is_always_allowed(file_path):
        sys.exit(0)

    # Load task
    task = load_task()

    if task is None:
        # No task defined - warn but allow for critical paths
        task_type = detect_task_type(file_path)
        if task_type in ['feature', 'bugfix']:
            # These are critical - just warn
            print(f"""
Warning: Modifying critical file without defined task
  File: {file_path}
  Type: {task_type}

  Consider defining the task first with:
  echo '{{"task": "...", "task_type": "{task_type}", "allowed_paths": [...]}}' > .claude/current_task.json
""", file=sys.stderr)
        sys.exit(0)

    # Task exists - check if path is allowed
    allowed_paths = task.get('allowed_paths', [])
    task_type = task.get('task_type')

    # If no explicit allowed_paths, derive from task_type
    if not allowed_paths and task_type:
        allowed_paths = get_allowed_paths_for_type(task_type)

    # If still no paths, allow all (no restriction)
    if not allowed_paths:
        sys.exit(0)

    if is_path_allowed(file_path, allowed_paths):
        sys.exit(0)

    # Path not allowed - BLOCK
    task_desc = task.get('task', 'unknown')[:45]
    allowed_str = ', '.join(allowed_paths[:3])
    if len(allowed_paths) > 3:
        allowed_str += f" (+{len(allowed_paths) - 3} more)"

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  BLOCKED: Outside Current Task Scope                             ║
╠══════════════════════════════════════════════════════════════════╣
║  Current Task: {task_desc:<48}║
║  Allowed Paths: {allowed_str[:47]:<47}║
║                                                                  ║
║  Attempted: {file_path[:52]:<52}║
║                                                                  ║
║  This change is NOT part of the current task!                    ║
║                                                                  ║
║  Options:                                                        ║
║  1. Complete current task first, then ask user about this        ║
║  2. Ask user for permission to expand scope                      ║
║  3. Update task file to include this path:                       ║
║     Edit .claude/current_task.json                               ║
║                                                                  ║
║  DO NOT expand scope without user approval!                      ║
╚══════════════════════════════════════════════════════════════════╝
""", file=sys.stderr)
    sys.exit(2)


if __name__ == '__main__':
    main()

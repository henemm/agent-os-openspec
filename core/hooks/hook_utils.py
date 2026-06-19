#!/usr/bin/env python3
"""
OpenSpec Framework - Hook Utilities

Shared bootstrap module for all hooks. Handles:
- sys.path setup for same-directory imports
- Common input parsing (tool_input from env or stdin)
- Standardized exit helpers

Usage in any hook:
    from hook_utils import setup_path, get_tool_input, block, allow
    setup_path()
    from config_loader import load_config, find_project_root
"""

import json
import os
import sys
from pathlib import Path


def setup_path():
    """Add the hooks directory to sys.path for same-directory imports.
    Call this BEFORE importing config_loader or other hook modules."""
    hooks_dir = str(Path(__file__).parent)
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)


def get_tool_input() -> dict:
    """Parse tool input from CLAUDE_TOOL_INPUT env var or stdin.
    Returns parsed dict or empty dict on failure."""
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")

    if not tool_input:
        try:
            data = json.load(sys.stdin)
            return data.get("tool_input", {})
        except (json.JSONDecodeError, Exception):
            return {}

    try:
        return json.loads(tool_input) if isinstance(tool_input, str) else tool_input
    except json.JSONDecodeError:
        return {}


def get_user_message() -> str:
    """Parse user message from stdin (for UserPromptSubmit hooks)."""
    try:
        data = json.load(sys.stdin)
        return data.get("user_message", "")
    except (json.JSONDecodeError, Exception):
        return ""


def get_tool_result() -> dict:
    """Parse tool result from stdin (for PostToolUse hooks)."""
    try:
        data = json.load(sys.stdin)
        return data
    except (json.JSONDecodeError, Exception):
        return {}


def block(message: str):
    """Block the operation with an error message and exit."""
    print(message, file=sys.stderr)
    sys.exit(2)


def allow():
    """Allow the operation and exit."""
    sys.exit(0)


def get_file_path(tool_input: dict = None) -> str:
    """Extract file_path from tool input."""
    if tool_input is None:
        tool_input = get_tool_input()
    return tool_input.get("file_path", "")


def get_command(tool_input: dict = None) -> str:
    """Extract command from tool input (for Bash hooks)."""
    if tool_input is None:
        tool_input = get_tool_input()
    return tool_input.get("command", "")


def is_code_file(file_path: str) -> bool:
    """Check if a file is a code file based on extension."""
    code_extensions = [
        ".py", ".js", ".ts", ".tsx", ".jsx",
        ".swift", ".kt", ".java",
        ".go", ".rs", ".cpp", ".c", ".h",
        ".rb", ".php", ".cs",
    ]
    return any(file_path.endswith(ext) for ext in code_extensions)


def find_main_repo_from_worktree(start: Path) -> "Path | None":
    """If start is inside a git worktree, return the linked main repo root.

    Git worktrees place a .git FILE (not directory) pointing at the main repo:
      gitdir: <main>/.git/worktrees/<name>
    Returns None if start is not in a worktree.
    """
    current = start
    while current != current.parent:
        git_marker = current / ".git"
        if git_marker.is_file():
            try:
                content = git_marker.read_text(errors="ignore").strip()
            except OSError:
                return None
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("gitdir:"):
                    gitdir = Path(line[len("gitdir:"):].strip())
                    if not gitdir.is_absolute():
                        gitdir = (current / gitdir).resolve()
                    # Walk up until we find the .git directory itself
                    walker = gitdir
                    while walker.name != ".git" and walker != walker.parent:
                        walker = walker.parent
                    if walker.name == ".git":
                        return walker.parent
            return None
        if git_marker.is_dir():
            return None
        current = current.parent
    return None


def find_project_root() -> Path:
    """Find project root. Resolves git worktrees to the main repo root.

    Priority:
    1. CLAUDE_PROJECT_DIR env var (set by Claude Code) — resolved through worktree if needed
    2. Walk up from CWD looking for .git, resolving worktrees transparently
    """
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        p = Path(env_dir)
        main = find_main_repo_from_worktree(p)
        return main if main is not None else p
    cwd = Path.cwd()
    main = find_main_repo_from_worktree(cwd)
    if main is not None:
        return main
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").is_dir():
            return parent
    return cwd


def get_active_workflow_name() -> str:
    """Return the active workflow name.

    Checks env var first (injected by Claude Code from settings.local.json at session
    start). Falls back to reading settings.local.json directly — necessary when
    workflow.py start/switch was called AFTER the current session started, because
    Claude Code only reads settings files at startup, not on every hook invocation.
    """
    name = os.environ.get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
    if name:
        return name
    try:
        settings_path = find_project_root() / ".claude" / "settings.local.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            name = settings.get("env", {}).get("OPENSPEC_ACTIVE_WORKFLOW", "").strip()
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    return name


def find_plugin_root() -> Path:
    """Plugin-Root: wo die Hook-Skripte liegen."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env:
        return Path(env)
    # Fallback: hook_utils.py liegt in plugin_root/core/hooks/
    candidate = Path(__file__).parent.parent.parent
    if (candidate / ".claude-plugin" / "plugin.json").exists():
        return candidate
    return candidate


def is_module_enabled(module_id: str) -> bool:
    """Check if a plugin module is enabled via OPENSPEC_ENABLED_MODULES env var."""
    enabled = os.environ.get("OPENSPEC_ENABLED_MODULES", "")
    return module_id in [m.strip() for m in enabled.split(",") if m.strip()]


def is_test_file(file_path: str) -> bool:
    """Check if a file is a test file."""
    test_patterns = [
        "test_", "_test.", ".test.", "tests/", "spec/", "_spec.",
        "Test.", "Tests/", "UITests/",
    ]
    return any(pattern in file_path for pattern in test_patterns)

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


def find_project_root() -> Path:
    """Find project root by looking for .git directory or CLAUDE_PROJECT_DIR env."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        return Path(env_dir)
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists():
            return parent
    return cwd


def is_test_file(file_path: str) -> bool:
    """Check if a file is a test file."""
    test_patterns = [
        "test_", "_test.", ".test.", "tests/", "spec/", "_spec.",
        "Test.", "Tests/", "UITests/",
    ]
    return any(pattern in file_path for pattern in test_patterns)

#!/usr/bin/env python3
"""
OpenSpec Framework - Track Changes Hook

Records which files have been modified since last validation.
Claude must validate before asking user to test.

This enables the validation tool to know what changed.

State File: .claude/validation_state.json
Contains: {files_changed: [...], last_validation: timestamp}

Exit Codes:
- 0: Always (this hook only records, never blocks)
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Try to get project root
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


def get_state_file() -> Path:
    """Get path to validation state file."""
    return get_project_root() / ".claude" / "validation_state.json"


def load_state() -> dict:
    """Load validation state."""
    state_file = get_state_file()
    if not state_file.exists():
        return {"files_changed": [], "last_validation": None}
    try:
        with open(state_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return {"files_changed": [], "last_validation": None}


def save_state(state: dict):
    """Save validation state."""
    state_file = get_state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)


# File patterns to skip (not code)
SKIP_PATTERNS = [
    ".json",
    "validation_state",
    "__pycache__",
    ".md",
    ".txt",
    ".gitignore",
    ".claude/",
    "node_modules/",
    ".git/",
]

# Code file extensions to track
CODE_EXTENSIONS = [
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".swift",
    ".kt",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
]


def should_track(file_path: str) -> bool:
    """Check if file should be tracked."""
    # Skip patterns
    for pattern in SKIP_PATTERNS:
        if pattern in file_path:
            return False

    # Check if it's a code file
    return any(file_path.endswith(ext) for ext in CODE_EXTENSIONS)


def get_relative_path(file_path: str) -> str:
    """Get relative path from project root."""
    project_root = str(get_project_root())

    if file_path.startswith(project_root):
        return file_path[len(project_root):].lstrip("/")

    # Try common patterns
    for marker in ["/src/", "/lib/", "/app/"]:
        if marker in file_path:
            return file_path.split(marker, 1)[-1]

    return Path(file_path).name


def main():
    # Get tool input
    tool_input_str = os.environ.get("CLAUDE_TOOL_INPUT", "")

    if not tool_input_str:
        try:
            data = json.load(sys.stdin)
            tool_input_str = json.dumps(data.get("tool_input", {}))
        except (json.JSONDecodeError, Exception):
            sys.exit(0)

    try:
        tool_input = json.loads(tool_input_str) if isinstance(tool_input_str, str) else tool_input_str
    except json.JSONDecodeError:
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    # Check if should track
    if not should_track(file_path):
        sys.exit(0)

    # Record the change
    state = load_state()
    if "files_changed" not in state:
        state["files_changed"] = []

    rel_path = get_relative_path(file_path)
    if rel_path not in state["files_changed"]:
        state["files_changed"].append(rel_path)
        state["last_change"] = datetime.now().isoformat()
        save_state(state)

    sys.exit(0)


if __name__ == "__main__":
    main()

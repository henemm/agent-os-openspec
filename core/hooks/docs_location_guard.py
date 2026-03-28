#!/usr/bin/env python3
"""
OpenSpec Framework - Documentation Location Guard

Prevents writing documentation/config to wrong directories.
Enforces proper project structure by blocking nested duplicates.

Configuration via config.yaml:
  docs_location:
    blocked_paths:
      - blocked: "src/docs/"
        correct: "docs/"
        description: "Documentation"

Exit Codes:
- 0: Allowed
- 2: Blocked (wrong location)
"""

import json
import os
import sys
from pathlib import Path

# Try to load config
try:
    from config_loader import load_config
    config = load_config()
except ImportError:
    config = {}

# Default blocked paths (can be overridden via config.yaml)
DEFAULT_BLOCKED_PATHS = [
    {
        "blocked": "src/docs/",
        "correct": "docs/",
        "description": "Documentation"
    },
    {
        "blocked": "src/.claude/",
        "correct": ".claude/",
        "description": "Claude Configuration"
    },
    {
        "blocked": "src/openspec/",
        "correct": "openspec/",
        "description": "OpenSpec Files"
    },
]


def get_blocked_paths() -> list:
    """Get blocked paths from config or use defaults."""
    docs_config = config.get("docs_location", {})
    return docs_config.get("blocked_paths", DEFAULT_BLOCKED_PATHS)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        sys.exit(0)

    blocked_paths = get_blocked_paths()

    for entry in blocked_paths:
        blocked = entry.get("blocked", "")
        correct = entry.get("correct", "")
        description = entry.get("description", "Files")

        if blocked in file_path or blocked.replace("/", "\\") in file_path:
            print(f"""
+======================================================================+
|  BLOCKED: Wrong Directory!                                           |
+======================================================================+
|                                                                      |
|  You're trying to write to: {blocked:<40}|
|                                                                      |
|  {description} should go to:
|    {correct:<60}|
|                                                                      |
|  NOT to: {blocked:<55}|
|                                                                      |
|  Correct the path and try again!                                     |
|                                                                      |
+======================================================================+
""", file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()

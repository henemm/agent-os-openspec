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

from hook_utils import setup_path, get_file_path, block, allow
setup_path()
from config_loader import load_config

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
    try:
        config = load_config()
    except Exception:
        config = {}
    docs_config = config.get("docs_location", {})
    return docs_config.get("blocked_paths", DEFAULT_BLOCKED_PATHS)


def main():
    file_path = get_file_path()

    if not file_path:
        allow()

    blocked_paths = get_blocked_paths()

    for entry in blocked_paths:
        blocked = entry.get("blocked", "")
        correct = entry.get("correct", "")
        description = entry.get("description", "Files")

        if blocked in file_path or blocked.replace("/", "\\") in file_path:
            block(f"""
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
""")

    allow()


if __name__ == "__main__":
    main()

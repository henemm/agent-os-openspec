#!/usr/bin/env python3
"""
OpenSpec Framework - CLAUDE.md Protection Hook

Prevents CLAUDE.md from becoming bloated with content that belongs elsewhere:
- Solution attempts -> docs/project/solution_attempts.md
- Feature documentation -> docs/features/
- Long code examples -> docs/reference/

Also warns if CLAUDE.md exceeds configured line limit.

Exit Codes:
- 0: Allowed (but may print warnings)
- 2: Blocked (forbidden pattern detected)
"""

import json
import os
import sys
import re
from pathlib import Path

try:
    from config_loader import load_config, get_project_root
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import load_config, get_project_root


def check_file_size():
    """Check if CLAUDE.md exceeds line limit."""
    config = load_config()
    max_lines = config.get("claude_md", {}).get("max_lines", 600)

    claude_md = get_project_root() / "CLAUDE.md"
    if not claude_md.exists():
        return

    try:
        lines = claude_md.read_text().splitlines()
        if len(lines) > max_lines:
            print(f"WARNING: CLAUDE.md has {len(lines)} lines (max: {max_lines})")
            print("Consider moving detailed content to /docs/")
    except Exception:
        pass


def check_content_patterns(content: str) -> tuple[bool, str]:
    """Check content for forbidden patterns."""
    config = load_config()
    patterns = config.get("claude_md", {}).get("forbidden_patterns", [])

    for item in patterns:
        pattern = item.get("pattern", "")
        message = item.get("message", "Content belongs elsewhere")

        if pattern and re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            return False, message

    return True, ""


def main():
    # This hook runs on Stop event - check file size
    check_file_size()

    # Also handle PreToolUse for Edit/Write on CLAUDE.md
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_input = data.get('tool_input', {})
    file_path = tool_input.get('file_path', '')

    if 'CLAUDE.md' not in file_path:
        sys.exit(0)

    content = tool_input.get('content', '') or tool_input.get('new_string', '')
    if not content:
        sys.exit(0)

    allowed, message = check_content_patterns(content)
    if not allowed:
        print(f"BLOCKED: {message}", file=sys.stderr)
        print("Write to the appropriate file in /docs/ instead!", file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()

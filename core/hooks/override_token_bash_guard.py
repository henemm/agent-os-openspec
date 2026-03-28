#!/usr/bin/env python3
"""
OpenSpec Framework - Override Token Bash Guard (PreToolUse Bash)

Protects the override token file from shell manipulation.

Exit Codes:
- 0: Allowed
- 2: Blocked (attempt to manipulate token file via shell)
"""

import json
import os
import sys


def get_tool_input() -> dict:
    """Read tool input."""
    tool_input_str = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if tool_input_str:
        try:
            return json.loads(tool_input_str)
        except json.JSONDecodeError:
            pass
    try:
        data = json.load(sys.stdin)
        return data.get("tool_input", data)
    except (json.JSONDecodeError, EOFError, Exception):
        return {}


def main():
    tool_input = get_tool_input()
    command = tool_input.get("command", "")

    if "override_token" in command and any(
        op in command for op in ["echo", "cat >", "write", "sed", "python", "rm ", "unlink"]
    ):
        print(
            "BLOCKED: Shell manipulation of override tokens is not allowed.\n"
            "Override tokens are managed by the user saying 'override'.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()

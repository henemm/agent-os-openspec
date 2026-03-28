#!/usr/bin/env python3
"""
OpenSpec Framework - Override Token Guard (PreToolUse Edit/Write)

Protects the override token file from direct manipulation by Claude.
Only the override_token_listener (UserPromptSubmit) may create/modify tokens.

Exit Codes:
- 0: Allowed
- 2: Blocked (attempt to manipulate token file)
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
    file_path = tool_input.get("file_path", "")

    if "override_token" in file_path:
        print(
            "BLOCKED: Direct manipulation of override tokens is not allowed.\n"
            "Override tokens are created by the user saying 'override'.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()

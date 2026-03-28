#!/usr/bin/env python3
"""
OpenSpec Framework - Override Token Bash Guard (PreToolUse Bash)

Protects the override token file from shell manipulation.

Exit Codes:
- 0: Allowed
- 2: Blocked (attempt to manipulate token file via shell)
"""

from hook_utils import setup_path, get_tool_input, block, allow
setup_path()


def main():
    tool_input = get_tool_input()
    command = tool_input.get("command", "")

    if "override_token" in command and any(
        op in command for op in ["echo", "cat >", "write", "sed", "python", "rm ", "unlink"]
    ):
        block(
            "BLOCKED: Shell manipulation of override tokens is not allowed.\n"
            "Override tokens are managed by the user saying 'override'."
        )

    allow()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
OpenSpec Framework - Adversary Verdict Guard

Blocks direct JSON manipulation of the adversary_verdict field
in workflow state files. Only the adversary_gate.py hook may set this.

Exit Codes:
- 0: Allowed
- 2: Blocked (attempt to manipulate verdict)
"""

import json
import os
import sys
from pathlib import Path


def get_tool_input() -> dict:
    """Read tool input from stdin or environment."""
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
    tool_name = os.environ.get("CLAUDE_TOOL", "")

    # Check Edit/Write operations
    if tool_name in ("Edit", "Write"):
        file_path = tool_input.get("file_path", "")

        # Only guard workflow state files
        if "workflow_state" not in file_path:
            sys.exit(0)

        # Check if content manipulates adversary_verdict
        content = tool_input.get("content", "")
        new_string = tool_input.get("new_string", "")
        check_text = content + new_string

        if "adversary_verdict" in check_text:
            print(
                "BLOCKED: Direct manipulation of adversary_verdict is not allowed.\n"
                "The adversary_verdict can only be set by the adversary_gate hook\n"
                "after validating real test output.",
                file=sys.stderr,
            )
            sys.exit(2)

    # Check Bash operations
    elif tool_name == "Bash":
        command = tool_input.get("command", "")

        # Block echo/cat/sed/python manipulating verdict in state files
        if "adversary_verdict" in command and "workflow_state" in command:
            print(
                "BLOCKED: Direct manipulation of adversary_verdict via shell is not allowed.\n"
                "Run your tests properly and let the adversary_gate validate the output.",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
OpenSpec Framework - Adversary Verdict Guard

Blocks direct JSON manipulation of the adversary_verdict field
in workflow state files. Only the adversary_gate.py hook may set this.

Exit Codes:
- 0: Allowed
- 2: Blocked (attempt to manipulate verdict)
"""

import os
from hook_utils import setup_path, get_tool_input, block, allow
setup_path()


def main():
    tool_input = get_tool_input()
    tool_name = os.environ.get("CLAUDE_TOOL", "")

    # Check Edit/Write operations
    if tool_name in ("Edit", "Write"):
        file_path = tool_input.get("file_path", "")

        # Only guard workflow state files
        if "workflow_state" not in file_path:
            allow()

        # Check if content manipulates adversary_verdict
        content = tool_input.get("content", "")
        new_string = tool_input.get("new_string", "")
        check_text = content + new_string

        if "adversary_verdict" in check_text:
            block(
                "BLOCKED: Direct manipulation of adversary_verdict is not allowed.\n"
                "The adversary_verdict can only be set by the adversary_gate hook\n"
                "after validating real test output."
            )

    # Check Bash operations
    elif tool_name == "Bash":
        command = tool_input.get("command", "")

        if "adversary_verdict" in command and "workflow_state" in command:
            block(
                "BLOCKED: Direct manipulation of adversary_verdict via shell is not allowed.\n"
                "Run your tests properly and let the adversary_gate validate the output."
            )

    allow()


if __name__ == "__main__":
    main()

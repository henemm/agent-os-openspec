#!/usr/bin/env python3
"""
iOS Module - UI Test Debugger Hint (PostToolUse Bash)

Advisory hook that recommends the ui-test-debugger agent when
UI test failures are detected. Never blocks.

Exit Codes:
- 0: Always (advisory only)
"""

import json
import os
import re
import sys

# Module guard — No-Op wenn ios-swiftui nicht aktiv
if "ios-swiftui" not in os.environ.get("OPENSPEC_ENABLED_MODULES", "").split(","):
    sys.exit(0)


def get_tool_result() -> dict:
    """Read tool result from PostToolUse input."""
    result_str = os.environ.get("CLAUDE_TOOL_RESULT", "")
    if result_str:
        try:
            return json.loads(result_str)
        except json.JSONDecodeError:
            return {"output": result_str}

    try:
        data = json.load(sys.stdin)
        return data.get("tool_result", data)
    except (json.JSONDecodeError, EOFError, Exception):
        return {}


def get_tool_input() -> dict:
    """Read original tool input."""
    tool_input_str = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if tool_input_str:
        try:
            return json.loads(tool_input_str)
        except json.JSONDecodeError:
            pass
    return {}


def was_ui_test(tool_input: dict) -> bool:
    """Check if the command was a UI test run."""
    command = tool_input.get("command", "")
    return bool(
        re.search(r"xcodebuild.*test", command, re.IGNORECASE)
        and re.search(r"UITest", command, re.IGNORECASE)
    )


UI_TEST_FAILURE_INDICATORS = [
    r"Test Case .* failed",
    r"No matches found for",
    r"Failed to find",
    r"waitForExistence.*failed",
    r"UI Testing Failure",
    r"element.*not.*found",
    r"accessibility.*not.*found",
]


def has_ui_test_failure(output: str) -> bool:
    """Check if output contains UI test failure indicators."""
    for pattern in UI_TEST_FAILURE_INDICATORS:
        if re.search(pattern, output, re.IGNORECASE):
            return True
    return False


def count_failures(output: str) -> int:
    """Count number of failed test cases."""
    failures = re.findall(r"Test Case .* failed", output)
    return len(failures)


def main():
    tool_input = get_tool_input()

    # Only check UI test commands
    if not was_ui_test(tool_input):
        sys.exit(0)

    tool_result = get_tool_result()
    output = tool_result.get("output", tool_result.get("stdout", ""))
    exit_code = tool_result.get("exit_code", tool_result.get("returncode", 0))

    # No failure - no hint needed
    if exit_code == 0:
        sys.exit(0)

    if not has_ui_test_failure(output):
        sys.exit(0)

    failure_count = count_failures(output)

    print(
        f"\n"
        f"Hint: {failure_count} UI test failure(s) detected.\n"
        f"\n"
        f"Consider using the ui-test-debugger agent for systematic diagnosis:\n"
        f"  - Environment check (Simulator state, accessibility)\n"
        f"  - Timing analysis (race conditions, animations)\n"
        f"  - State verification (navigation, data loading)\n"
        f"\n"
        f"The agent is available in the iOS module: ui-test-debugger.md\n",
        file=sys.stderr,
    )

    sys.exit(0)


if __name__ == "__main__":
    main()

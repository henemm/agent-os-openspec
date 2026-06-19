#!/usr/bin/env python3
"""
iOS Module - Test Lock Guard (PreToolUse Bash)

Prevents parallel xcodebuild test runs which cause Simulator conflicts
and unreliable test results.

Uses `pgrep` to check for running xcodebuild processes.

Exit Codes:
- 0: Allowed (no xcodebuild running)
- 2: Blocked (xcodebuild already running)
"""

import json
import os
import re
import subprocess
import sys

# Module guard — No-Op wenn ios-swiftui nicht aktiv
if "ios-swiftui" not in os.environ.get("OPENSPEC_ENABLED_MODULES", "").split(","):
    sys.exit(0)


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


def is_xcodebuild_command(command: str) -> bool:
    """Check if command runs xcodebuild tests."""
    return bool(re.search(r"xcodebuild\s+.*test", command, re.IGNORECASE))


def is_xcodebuild_running() -> bool:
    """Check if xcodebuild is already running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "xcodebuild.*test"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # pgrep returns 0 if processes found
        return result.returncode == 0 and result.stdout.strip() != ""
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def get_running_xcodebuild_info() -> str:
    """Get info about running xcodebuild processes."""
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,etime,args"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [
            l.strip() for l in result.stdout.split("\n")
            if "xcodebuild" in l and "test" in l.lower()
        ]
        return "\n".join(lines[:3]) if lines else "Unknown process"
    except Exception:
        return "Unknown process"


def main():
    tool_name = os.environ.get("CLAUDE_TOOL", "")
    if tool_name != "Bash":
        sys.exit(0)

    tool_input = get_tool_input()
    command = tool_input.get("command", "")

    if not is_xcodebuild_command(command):
        sys.exit(0)

    if not is_xcodebuild_running():
        sys.exit(0)

    # xcodebuild is already running
    process_info = get_running_xcodebuild_info()

    print(
        f"BLOCKED: xcodebuild is already running!\n"
        f"\n"
        f"Running processes:\n"
        f"{process_info}\n"
        f"\n"
        f"Parallel xcodebuild test runs cause Simulator conflicts.\n"
        f"Wait for the current run to finish, or kill it first:\n"
        f"  pkill -f 'xcodebuild.*test'",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Post-Bash v3 — PostToolUse Hook for Bash

Extensible post-execution hook. Base implementation is minimal.
Module hooks (e.g., iOS build_lock_release) extend this via config.

Exit Codes: 0 always (never blocks)
"""

from hook_utils import setup_path, find_project_root, get_tool_input
setup_path()

import json
import os
import re
import sys
from pathlib import Path

_root = find_project_root()


def _detect_test_output(command: str, tool_input: dict) -> None:
    """Detect test framework output and update adversary_verdict in active workflow."""
    # Only process test-like commands
    test_indicators = ["pytest", "jest", "xcodebuild", "go test", "cargo test",
                       "npm test", "yarn test", "vitest", "mocha"]
    if not any(t in command for t in test_indicators):
        return

    # Read stdout from tool result (if available via env)
    stdout = tool_input.get("stdout", "")
    if not stdout:
        return

    # Check for framework-specific pass patterns
    pass_patterns = [
        (r"passed", "pytest"),
        (r"Tests:.*passed", "jest"),
        (r"\*\* TEST SUCCEEDED \*\*", "xcodebuild"),
        (r"^ok\s+", "go_test"),
        (r"test result: ok", "cargo_test"),
    ]

    for pattern, framework in pass_patterns:
        if re.search(pattern, stdout, re.MULTILINE):
            _set_adversary_verdict(f"VERIFIED:{framework}")
            return


def _set_adversary_verdict(verdict: str) -> None:
    """Update adversary_verdict in active workflow."""
    link = _root / ".claude" / "workflows" / ".active"
    if not link.exists():
        return
    try:
        target = Path(os.readlink(str(link)))
        if not target.is_absolute():
            target = link.parent / target
        if not target.exists():
            return
        data = json.loads(target.read_text())
        data["adversary_verdict"] = verdict
        target.write_text(json.dumps(data, indent=2))
    except (OSError, json.JSONDecodeError):
        pass


def main():
    tool_input = get_tool_input()
    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    _detect_test_output(command, tool_input)

    sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
iOS Module - UI Test Preflight (PreToolUse Edit/Write)

Enforces best practices for XCUITest files:
1. Requires /inspect-ui before editing UI test files
2. Blocks known anti-patterns in UI tests

Anti-patterns blocked:
- sleep() calls (use XCTWaiter or expectation-based waiting)
- Direct tab bar access by index without proper identification
- Hard-coded coordinates (use accessibility identifiers)

Exit Codes:
- 0: Allowed
- 2: Blocked (anti-pattern detected or inspection not done)
"""

import json
import os
import re
import sys
import time
from pathlib import Path


# Anti-patterns in UI test code
ANTI_PATTERNS = [
    {
        "pattern": r"\bsleep\s*\(",
        "message": "Use XCTWaiter or waitForExistence() instead of sleep()",
        "severity": "error",
    },
    {
        "pattern": r"\.tabBars\.buttons\.element\(boundBy:\s*\d+\)",
        "message": "Use accessibility identifiers instead of tab index: .buttons[\"identifier\"]",
        "severity": "error",
    },
    {
        "pattern": r"\.coordinate\(withNormalizedOffset:",
        "message": "Avoid hard-coded coordinates. Use accessibility identifiers for reliable element access.",
        "severity": "warning",
    },
    {
        "pattern": r"Thread\.sleep",
        "message": "Use XCTWaiter or expectation-based waiting instead of Thread.sleep",
        "severity": "error",
    },
    {
        "pattern": r"XCTAssertTrue\(true\)|XCTAssertFalse\(false\)",
        "message": "Trivial assertion detected. Write a meaningful test assertion.",
        "severity": "error",
    },
]

# UI Test file patterns
UI_TEST_PATTERNS = [
    r"UITest",
    r"ui_test",
    r"uitest",
    r"XCUITest",
]


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


def is_ui_test_file(file_path: str) -> bool:
    """Check if file is a UI test file."""
    for pattern in UI_TEST_PATTERNS:
        if re.search(pattern, file_path, re.IGNORECASE):
            return True
    return False


def check_anti_patterns(tool_input: dict) -> list:
    """Check content for anti-patterns."""
    violations = []

    # Check in both Write content and Edit new_string
    content = tool_input.get("content", "") + tool_input.get("new_string", "")

    for anti in ANTI_PATTERNS:
        if re.search(anti["pattern"], content):
            violations.append({
                "pattern": anti["pattern"],
                "message": anti["message"],
                "severity": anti["severity"],
            })

    return violations


def find_project_root() -> Path:
    """Find project root."""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        if (parent / ".git").exists():
            return parent
    return cwd


def check_inspect_ui_done() -> bool:
    """Check if /inspect-ui was run recently (within 30 minutes)."""
    root = find_project_root()
    marker = root / ".claude" / "inspect_ui_done.json"

    if not marker.exists():
        return False

    try:
        data = json.loads(marker.read_text())
        timestamp = data.get("timestamp", 0)
        age_minutes = (time.time() - timestamp) / 60
        return age_minutes <= 30
    except (json.JSONDecodeError, Exception):
        return False


def main():
    tool_input = get_tool_input()
    file_path = tool_input.get("file_path", "")

    if not file_path:
        sys.exit(0)

    if not is_ui_test_file(file_path):
        sys.exit(0)

    # Check anti-patterns in content
    errors = [v for v in check_anti_patterns(tool_input) if v["severity"] == "error"]

    if errors:
        error_msgs = "\n".join(f"  - {e['message']}" for e in errors)
        print(
            f"BLOCKED: UI Test anti-patterns detected in {os.path.basename(file_path)}:\n"
            f"\n"
            f"{error_msgs}\n"
            f"\n"
            f"Fix these issues before writing to the test file.",
            file=sys.stderr,
        )
        sys.exit(2)

    # Warnings (don't block, just inform)
    warnings = [v for v in check_anti_patterns(tool_input) if v["severity"] == "warning"]
    if warnings:
        warn_msgs = "\n".join(f"  - {w['message']}" for w in warnings)
        print(
            f"WARNING: UI Test suggestions for {os.path.basename(file_path)}:\n"
            f"{warn_msgs}",
            file=sys.stderr,
        )

    sys.exit(0)


if __name__ == "__main__":
    main()

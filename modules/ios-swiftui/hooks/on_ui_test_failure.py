#!/usr/bin/env python3
"""
iOS Module - On UI Test Failure (PostToolUse Bash)

Analyzes xcodebuild test failures and provides actionable diagnostics.

Failure categories:
- Exit 64: Build failure (compilation error)
- Exit 65: Test failure (assertion failure)
- Exit 70: Infrastructure error (Simulator issue)

For each category, provides specific remediation advice.

Exit Codes:
- 0: Always (PostToolUse hooks never block, they advise)
"""

import json
import os
import re
import sys
from pathlib import Path

# Module guard — No-Op wenn ios-swiftui nicht aktiv
if "ios-swiftui" not in os.environ.get("OPENSPEC_ENABLED_MODULES", "").split(","):
    sys.exit(0)


def get_tool_result() -> dict:
    """Read tool result from PostToolUse input."""
    # PostToolUse receives the tool result
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


def was_xcodebuild_test(tool_input: dict) -> bool:
    """Check if the command was an xcodebuild test."""
    command = tool_input.get("command", "")
    return bool(re.search(r"xcodebuild\s+.*test", command, re.IGNORECASE))


def analyze_build_failure(output: str) -> list:
    """Analyze exit 64 (build failure) output."""
    diagnostics = []

    # Find compilation errors
    compile_errors = re.findall(
        r"(\S+\.swift):(\d+):(\d+): error: (.+)", output
    )
    for file, line, col, msg in compile_errors[:10]:
        diagnostics.append({
            "type": "compile_error",
            "file": file,
            "line": line,
            "message": msg.strip(),
        })

    # Find linker errors
    if "Undefined symbol" in output or "ld: " in output:
        linker_errors = re.findall(r"Undefined symbol[s]?: (.+)", output)
        for symbol in linker_errors[:5]:
            diagnostics.append({
                "type": "linker_error",
                "message": f"Undefined symbol: {symbol.strip()}",
            })

    # Missing import
    if "No such module" in output:
        modules = re.findall(r"No such module '(\w+)'", output)
        for mod in modules:
            diagnostics.append({
                "type": "missing_module",
                "message": f"Missing module: {mod}. Check Package.swift or Podfile.",
            })

    return diagnostics


def analyze_test_failure(output: str) -> list:
    """Analyze exit 65 (test failure) output."""
    diagnostics = []

    # Find failed test cases
    failed_tests = re.findall(
        r"(Test Case .* failed \(.+ seconds\))", output
    )
    for test in failed_tests[:10]:
        diagnostics.append({
            "type": "test_failure",
            "message": test.strip(),
        })

    # Find assertion failures
    assertions = re.findall(
        r"(\S+\.swift):(\d+): error: .+ : (.+)", output
    )
    for file, line, msg in assertions[:10]:
        diagnostics.append({
            "type": "assertion_failure",
            "file": file,
            "line": line,
            "message": msg.strip(),
        })

    # Element not found (common XCUITest issue)
    not_found = re.findall(
        r"(No matches found for|Failed to find)",
        output
    )
    if not_found:
        diagnostics.append({
            "type": "element_not_found",
            "message": (
                "UI element not found. Common causes:\n"
                "  1. Accessibility identifier mismatch\n"
                "  2. Element not visible (off-screen or hidden)\n"
                "  3. Navigation state wrong (wrong screen)\n"
                "  4. Timing issue (element not yet loaded)\n"
                "  Tip: Use app.debugDescription to inspect the view hierarchy"
            ),
        })

    # Timeout
    if "timed out" in output.lower() or "waitForExistence" in output:
        diagnostics.append({
            "type": "timeout",
            "message": (
                "UI element wait timed out. Increase timeout or check:\n"
                "  1. Is the element actually appearing?\n"
                "  2. Is the accessibility identifier correct?\n"
                "  3. Is there a loading state that needs to complete first?"
            ),
        })

    return diagnostics


def analyze_infrastructure_failure(output: str) -> list:
    """Analyze exit 70 (infrastructure error) output."""
    diagnostics = []

    if "Simulator" in output or "simctl" in output:
        diagnostics.append({
            "type": "simulator_error",
            "message": (
                "Simulator error. Try:\n"
                "  1. xcrun simctl shutdown all\n"
                "  2. xcrun simctl erase all\n"
                "  3. Restart Simulator.app\n"
                "  4. Check available simulators: xcrun simctl list devices available"
            ),
        })

    if "device not found" in output.lower():
        diagnostics.append({
            "type": "device_not_found",
            "message": (
                "Test destination device not found.\n"
                "List available: xcrun simctl list devices available\n"
                "Use a valid destination: -destination 'platform=iOS Simulator,name=iPhone 16'"
            ),
        })

    if not diagnostics:
        diagnostics.append({
            "type": "unknown_infra",
            "message": "Infrastructure error. Check Xcode and Simulator state.",
        })

    return diagnostics


def format_diagnostics(diagnostics: list, exit_code: int) -> str:
    """Format diagnostics into readable output."""
    if not diagnostics:
        return ""

    # Category header
    if exit_code == 64:
        header = "BUILD FAILURE (Exit 64)"
        advice = "Fix compilation errors before running tests."
    elif exit_code == 65:
        header = "TEST FAILURE (Exit 65)"
        advice = "Tests compiled but assertions failed."
    elif exit_code == 70:
        header = "INFRASTRUCTURE ERROR (Exit 70)"
        advice = "Xcode/Simulator issue, not a code problem."
    else:
        header = f"FAILURE (Exit {exit_code})"
        advice = "Check the output for details."

    lines = [
        f"{'=' * 60}",
        f"iOS TEST DIAGNOSTIC: {header}",
        f"{'=' * 60}",
        f"",
        f"{advice}",
        f"",
    ]

    for i, diag in enumerate(diagnostics, 1):
        dtype = diag.get("type", "unknown")
        msg = diag.get("message", "")
        file = diag.get("file", "")
        line = diag.get("line", "")

        location = f" ({file}:{line})" if file else ""
        lines.append(f"  {i}. [{dtype}]{location}")
        for msg_line in msg.split("\n"):
            lines.append(f"     {msg_line}")
        lines.append("")

    lines.append(f"{'=' * 60}")
    return "\n".join(lines)


def main():
    tool_input = get_tool_input()

    # Only process xcodebuild test commands
    if not was_xcodebuild_test(tool_input):
        sys.exit(0)

    tool_result = get_tool_result()
    output = tool_result.get("output", tool_result.get("stdout", ""))
    exit_code = tool_result.get("exit_code", tool_result.get("returncode", 0))

    # Success - no diagnostics needed
    if exit_code == 0:
        sys.exit(0)

    # Analyze based on exit code
    if exit_code == 64:
        diagnostics = analyze_build_failure(output)
    elif exit_code == 65:
        diagnostics = analyze_test_failure(output)
    elif exit_code == 70:
        diagnostics = analyze_infrastructure_failure(output)
    else:
        # Unknown exit code - try all analyzers
        diagnostics = (
            analyze_build_failure(output)
            + analyze_test_failure(output)
            + analyze_infrastructure_failure(output)
        )

    if diagnostics:
        formatted = format_diagnostics(diagnostics, exit_code)
        print(formatted, file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()

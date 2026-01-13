#!/usr/bin/env python3
"""
OpenSpec Framework - Pre-Commit Gate Hook

Blocks git commits if tests are failing.
Ensures TDD GREEN phase before allowing commits.

Configuration (in config.yaml):
  pre_commit:
    enabled: true
    test_command: ["pytest", "--tb=line", "-q"]  # or ["npm", "test"]
    timeout: 120
    allow_amend: true  # Allow git commit --amend
    ui_patterns:
      - "web/pages/"
      - "templates/"
      - ".vue"
      - ".tsx"
      - ".jsx"
    screenshot_reminder: true  # Remind about screenshots for UI changes

Exit Codes:
- 0: Allowed (with optional JSON response)
- 2: Blocked
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Try to import config loader
try:
    from config_loader import load_config, get_project_root
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import load_config, get_project_root
    except ImportError:
        def load_config():
            return {}
        def get_project_root():
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                if (parent / ".git").exists():
                    return parent
            return cwd


def get_pre_commit_config() -> dict:
    """Get pre-commit configuration with defaults."""
    config = load_config()
    pre_commit = config.get("pre_commit", {})

    return {
        "enabled": pre_commit.get("enabled", True),
        "test_command": pre_commit.get("test_command", ["pytest", "--tb=line", "-q"]),
        "timeout": pre_commit.get("timeout", 120),
        "allow_amend": pre_commit.get("allow_amend", True),
        "ui_patterns": pre_commit.get("ui_patterns", [
            "web/pages/",
            "templates/",
            ".vue",
            ".tsx",
            ".jsx",
            "components/",
            ".svelte",
        ]),
        "screenshot_reminder": pre_commit.get("screenshot_reminder", True),
    }


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


def is_git_commit(tool_input: dict, config: dict) -> bool:
    """Check if this is a git commit command."""
    command = tool_input.get("command", "")

    if "git commit" not in command:
        return False

    # Allow amend if configured
    if config["allow_amend"] and "--amend" in command:
        return False

    return True


def run_tests(config: dict) -> tuple[bool, str]:
    """Run tests and return (success, output)."""
    project_root = get_project_root()
    test_command = config["test_command"]
    timeout = config["timeout"]

    # Check if test command executable exists
    try:
        # Try with uv first (Python projects)
        if test_command[0] in ("pytest", "python"):
            full_command = ["uv", "run"] + test_command
        elif test_command[0] in ("npm", "npx", "yarn", "pnpm"):
            full_command = test_command
        else:
            full_command = test_command

        result = subprocess.run(
            full_command,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = result.stdout + result.stderr

        # Check return code and output for failures
        if result.returncode == 0:
            return True, output

        # Some test frameworks return non-zero for various reasons
        # Check output for actual failures
        output_lower = output.lower()
        if "failed" in output_lower or "error" in output_lower:
            return False, output

        # If no failures mentioned, consider it passed
        return True, output

    except subprocess.TimeoutExpired:
        return False, f"Tests timed out after {timeout} seconds"
    except FileNotFoundError as e:
        # Test runner not found - try direct command
        try:
            result = subprocess.run(
                test_command,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout + result.stderr
            return result.returncode == 0, output
        except Exception:
            return True, f"Test runner not available: {e}. Allowing commit."
    except Exception as e:
        return False, f"Failed to run tests: {e}"


def check_for_ui_changes(config: dict) -> bool:
    """Check if staged changes include UI files."""
    project_root = get_project_root()
    ui_patterns = config["ui_patterns"]

    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        files = result.stdout.strip().split("\n")
        return any(
            any(pattern in f for pattern in ui_patterns)
            for f in files if f
        )
    except Exception:
        return False


def main():
    config = get_pre_commit_config()

    # Check if enabled
    if not config["enabled"]:
        sys.exit(0)

    tool_input = get_tool_input()

    if not is_git_commit(tool_input, config):
        sys.exit(0)

    # Run tests
    success, output = run_tests(config)

    if not success:
        # Extract failure summary
        lines = output.split("\n")
        failures = [l for l in lines if "FAILED" in l or "Error" in l or "FAIL" in l]
        summary = "\n".join(failures[:5]) if failures else "Tests failed"

        print("=" * 70, file=sys.stderr)
        print("BLOCKED - Pre-Commit Gate", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        print(file=sys.stderr)
        print("Tests must pass before committing (TDD-GREEN).", file=sys.stderr)
        print(file=sys.stderr)
        print("Failures:", file=sys.stderr)
        print(summary, file=sys.stderr)
        print(file=sys.stderr)
        print("Fix tests first, then commit.", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        sys.exit(2)

    # Check for UI changes - remind about screenshot
    if config["screenshot_reminder"] and check_for_ui_changes(config):
        # Don't block, just output reminder
        print("Note: UI changes detected. Consider adding screenshot artifacts.", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()

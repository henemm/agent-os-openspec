#!/usr/bin/env python3
"""
OpenSpec Framework - Parallel Test Guard (PreToolUse Bash)

Blocks test commands when other active workflows have pending RED tests,
preventing interference between parallel workflows.

Example: Workflow A is in phase5_tdd_red with failing tests.
Running tests for Workflow B might produce confusing mixed results.

Configuration (in openspec.yaml):
  parallel_test_guard:
    enabled: true
    stale_threshold_hours: 48
    test_command_patterns:
      - "pytest"
      - "jest"
      - "xcodebuild.*test"
      - "go test"
      - "cargo test"
      - "npm test"
      - "yarn test"

Exit Codes:
- 0: Allowed
- 2: Blocked (conflicting RED tests in other workflow)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

# Import helpers
try:
    from config_loader import load_config
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import load_config
    except ImportError:
        def load_config():
            return {}

try:
    from workflow_state_multi import load_state
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from workflow_state_multi import load_state
    except ImportError:
        def load_state():
            return {"version": "2.0", "workflows": {}, "active_workflow": None}


DEFAULT_TEST_PATTERNS = [
    r"pytest",
    r"jest",
    r"xcodebuild.*test",
    r"go\s+test",
    r"cargo\s+test",
    r"npm\s+test",
    r"yarn\s+test",
    r"pnpm\s+test",
    r"vitest",
    r"mocha",
]


def get_config() -> dict:
    """Get parallel test guard configuration."""
    config = load_config()
    ptg = config.get("parallel_test_guard", {})
    return {
        "enabled": ptg.get("enabled", True),
        "stale_threshold_hours": ptg.get("stale_threshold_hours", 48),
        "test_command_patterns": ptg.get("test_command_patterns", DEFAULT_TEST_PATTERNS),
    }


def is_test_command(command: str, patterns: list) -> bool:
    """Check if a command is a test command."""
    command_lower = command.lower()
    for pattern in patterns:
        if re.search(pattern, command_lower):
            return True
    return False


def get_conflicting_workflows(state: dict, active_name: str, stale_hours: int) -> list:
    """Find other workflows with pending RED tests."""
    conflicts = []
    stale_threshold = time.time() - (stale_hours * 3600)

    for name, wf in state.get("workflows", {}).items():
        if name == active_name:
            continue

        phase = wf.get("current_phase", "phase0_idle")

        # Only conflict if other workflow is in RED phase
        if phase != "phase5_tdd_red":
            continue

        # Check if it's not stale
        last_updated = wf.get("last_updated", "")
        if last_updated:
            try:
                from datetime import datetime
                updated_time = datetime.fromisoformat(last_updated).timestamp()
                if updated_time < stale_threshold:
                    continue  # Stale workflow, ignore
            except (ValueError, TypeError):
                pass

        # Has RED tests but not done
        red_done = wf.get("red_test_done", False)
        if not red_done:
            conflicts.append({
                "name": name,
                "phase": phase,
            })

    return conflicts


def main():
    config = get_config()

    if not config["enabled"]:
        sys.exit(0)

    # Only check Bash commands
    tool_name = os.environ.get("CLAUDE_TOOL", "")
    if tool_name != "Bash":
        sys.exit(0)

    # Get command
    tool_input_str = os.environ.get("CLAUDE_TOOL_INPUT", "")
    if not tool_input_str:
        try:
            data = json.load(sys.stdin)
            tool_input_str = json.dumps(data.get("tool_input", {}))
        except (json.JSONDecodeError, Exception):
            sys.exit(0)

    try:
        tool_input = json.loads(tool_input_str) if isinstance(tool_input_str, str) else tool_input_str
        command = tool_input.get("command", "")
    except (json.JSONDecodeError, TypeError):
        sys.exit(0)

    if not is_test_command(command, config["test_command_patterns"]):
        sys.exit(0)

    # Load state and check for conflicts
    state = load_state()
    active_name = state.get("active_workflow", "")

    if not active_name:
        sys.exit(0)

    conflicts = get_conflicting_workflows(
        state, active_name, config["stale_threshold_hours"]
    )

    if not conflicts:
        sys.exit(0)

    # Format conflict list
    conflict_list = "\n".join(
        f"  - {c['name']} (phase: {c['phase']})"
        for c in conflicts
    )

    print(
        f"BLOCKED: Parallel test conflict detected!\n"
        f"\n"
        f"Other workflows have pending RED tests:\n"
        f"{conflict_list}\n"
        f"\n"
        f"Running tests now could produce mixed/confusing results.\n"
        f"\n"
        f"Options:\n"
        f"  1. Switch to the conflicting workflow and complete its RED phase\n"
        f"  2. Use /workflow to manage parallel workflows\n"
        f"  3. Say 'override' to bypass this check once",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

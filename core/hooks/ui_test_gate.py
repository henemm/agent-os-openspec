#!/usr/bin/env python3
"""
OpenSpec Framework - UI Test Gate

Blocks validation phase unless UI tests have been completed.

Principle: TDD can require BOTH unit tests AND UI tests.
Unit tests verify logic, UI tests verify user-facing behavior.

This hook enforces:
- Before phase7_validate: Must have ui_test_green_done=true
- Must have at least 1 UI test artifact (screenshot, ui_test_output, video)

Configuration via config.yaml:
  ui_test_gate:
    enabled: true
    require_ui_tests: true
    min_ui_artifacts: 1

Exit Codes:
- 0: Allowed
- 2: Blocked (UI tests not done)
"""

import json
import os
import sys
from pathlib import Path

# Try to import state manager
try:
    from workflow_state_multi import load_state, get_active_workflow
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from workflow_state_multi import load_state, get_active_workflow
    except ImportError:
        def load_state():
            return {"version": "2.0", "workflows": {}, "active_workflow": None}
        def get_active_workflow():
            return None

# Try to load config
try:
    from config_loader import load_config
    config = load_config()
except ImportError:
    config = {}


# UI test artifact types
UI_TEST_TYPES = ["ui_test_output", "screenshot", "video", "screen_recording"]

# Phases that require UI tests to be complete
REQUIRES_UI_TESTS = ["phase7_validate", "phase8_complete"]


def get_config_value(key: str, default):
    """Get config value with fallback to default."""
    gate_config = config.get("ui_test_gate", {})
    return gate_config.get(key, default)


def is_enabled() -> bool:
    """Check if UI test gate is enabled."""
    return get_config_value("enabled", False)  # Disabled by default


def require_ui_tests() -> bool:
    """Check if UI tests are required."""
    return get_config_value("require_ui_tests", True)


def min_ui_artifacts() -> int:
    """Get minimum required UI artifacts."""
    return get_config_value("min_ui_artifacts", 1)


def count_ui_artifacts(workflow: dict, phase_filter: str = None) -> int:
    """Count UI test artifacts, optionally filtered by phase."""
    artifacts = workflow.get("test_artifacts", [])
    ui_artifacts = [a for a in artifacts if a.get("type") in UI_TEST_TYPES]

    if phase_filter:
        ui_artifacts = [a for a in ui_artifacts if a.get("phase") == phase_filter]

    return len(ui_artifacts)


def has_ui_test_green(workflow: dict) -> bool:
    """Check if UI tests have passed (GREEN phase)."""
    # Check explicit flag first
    if workflow.get("ui_test_green_done", False):
        return True

    # Fallback: Check for GREEN phase UI artifacts
    artifacts = workflow.get("test_artifacts", [])
    green_ui_artifacts = [
        a for a in artifacts
        if a.get("type") in UI_TEST_TYPES
        and a.get("phase") == "phase6_implement"
    ]

    return len(green_ui_artifacts) >= min_ui_artifacts()


def check_user_override(workflow: dict) -> bool:
    """Check if user has granted manual override."""
    if workflow.get("user_override", False):
        return True
    if workflow.get("ui_test_override", False):
        return True
    return False


def main():
    """Main hook entry point."""
    # Check if enabled
    if not is_enabled():
        sys.exit(0)

    # Get tool input
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")
    tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")

    if not tool_input:
        try:
            data = json.load(sys.stdin)
            tool_input = json.dumps(data.get("tool_input", {}))
            tool_name = data.get("tool_name", "")
        except (json.JSONDecodeError, Exception):
            sys.exit(0)

    workflow = get_active_workflow()
    if not workflow:
        sys.exit(0)  # No workflow, allow

    # Check for user override
    if check_user_override(workflow):
        sys.exit(0)

    phase = workflow.get("current_phase", "phase0_idle")

    # Only enforce when in validation/complete phases
    if phase not in REQUIRES_UI_TESTS:
        sys.exit(0)

    # Check if UI tests requirement is enabled
    if not require_ui_tests():
        sys.exit(0)

    # Check if UI tests are done
    if not has_ui_test_green(workflow):
        workflow_name = workflow.get("name", "unknown")
        red_ui_count = count_ui_artifacts(workflow, "phase5_tdd_red")
        green_ui_count = count_ui_artifacts(workflow, "phase6_implement")
        required = min_ui_artifacts()

        print(f"""
+======================================================================+
|  BLOCKED: UI Tests Not Completed!                                    |
+======================================================================+
|  You're trying to validate without completing UI tests.              |
|                                                                      |
|  Workflow: {workflow_name[:56]:<56}|
|  Phase: {phase:<59}|
|                                                                      |
|  UI Test Status:                                                     |
|  - RED artifacts: {red_ui_count} (failing UI tests before implementation)    |
|  - GREEN artifacts: {green_ui_count} (need at least {required} passing)              |
|  - ui_test_green_done: {str(workflow.get('ui_test_green_done', False)):<43}|
|                                                                      |
|  TDD requires BOTH unit AND UI tests:                                |
|  1. Write UI tests for user-facing behavior                          |
|  2. Run tests - they FAIL (RED) before implementation                |
|  3. Implement the feature                                            |
|  4. Run tests again - they PASS (GREEN)                              |
|  5. Register GREEN artifact with /add-artifact                       |
|                                                                      |
|  UI Tests verify:                                                    |
|  - Components render correctly                                       |
|  - User interactions work                                            |
|  - Navigation flows are correct                                      |
|                                                                      |
|  Fix with:                                                           |
|  - Run UI tests and capture output                                   |
|  - /add-artifact with type "ui_test_output" or "screenshot"          |
|                                                                      |
|  Or set ui_test_override: true to bypass this check.                 |
+======================================================================+
""", file=sys.stderr)
        sys.exit(2)

    # Check passed
    sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
OpenSpec Framework - Workflow Gate Hook

Enforces the 4-phase workflow for protected files:
1. idle -> analyse_done (/analyse)
2. analyse_done -> spec_written (/write-spec)
3. spec_written -> spec_approved (user says "approved")
4. spec_approved -> implemented (/implement)
5. implemented -> validated (/validate)

Blocks Edit/Write on protected files unless workflow phase allows it.

Exit Codes:
- 0: Allowed
- 2: Blocked (stderr shown to Claude)
"""

import json
import os
import sys
import re
from pathlib import Path

# Import shared config loader
try:
    from config_loader import (
        load_config, get_state_file_path, get_project_root,
        get_protected_paths, get_always_allowed
    )
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, str(Path(__file__).parent))
    from config_loader import (
        load_config, get_state_file_path, get_project_root,
        get_protected_paths, get_always_allowed
    )


def load_state() -> dict:
    """Load current workflow state."""
    state_file = get_state_file_path()

    if not state_file.exists():
        return {
            "current_phase": "idle",
            "feature_name": None,
            "spec_file": None,
            "spec_approved": False,
            "implementation_done": False,
            "validation_done": False,
        }

    with open(state_file, 'r') as f:
        return json.load(f)


def is_always_allowed(file_path: str) -> bool:
    """Check if file is always allowed without workflow."""
    patterns = get_always_allowed()
    for pattern in patterns:
        if re.search(pattern, file_path):
            return True
    return False


def requires_workflow(file_path: str) -> bool:
    """Check if file requires workflow."""
    protected = get_protected_paths()
    for item in protected:
        pattern = item.get("pattern", item) if isinstance(item, dict) else item
        if re.search(pattern, file_path):
            return True
    return False


def get_phase_error(state: dict, file_path: str) -> str | None:
    """Generate error message based on current state."""
    phase = state.get("current_phase", "idle")

    if phase == "idle":
        return """
+======================================================================+
|  WORKFLOW NOT STARTED!                                               |
+======================================================================+
|  You're trying to modify code without starting the workflow.         |
|                                                                      |
|  REQUIRED ORDER:                                                     |
|  1. /analyse     - Understand the request, research codebase         |
|  2. /write-spec  - Create specification                              |
|  3. User says "approved" - Spec approval                             |
|  4. /implement   - NOW you can implement!                            |
|  5. /validate    - Validation before commit                          |
|                                                                      |
|  Start with: /analyse                                                |
+======================================================================+
"""

    if phase == "analyse_done":
        return """
+======================================================================+
|  SPEC MISSING!                                                       |
+======================================================================+
|  Analysis is complete, but no spec has been written.                 |
|                                                                      |
|  Next step: /write-spec                                              |
|                                                                      |
|  NO implementation without a spec!                                   |
+======================================================================+
"""

    if phase == "spec_written" and not state.get("spec_approved"):
        spec_file = state.get("spec_file", "unknown")
        return f"""
+======================================================================+
|  SPEC NOT APPROVED!                                                  |
+======================================================================+
|  Spec exists but user hasn't approved it.                            |
|                                                                      |
|  Spec file: {spec_file[:50]}
|                                                                      |
|  User must confirm with one of:                                      |
|  - "approved"                                                        |
|  - "freigabe"                                                        |
|  - "spec ok"                                                         |
|  - "lgtm"                                                            |
|                                                                      |
|  NO implementation without user approval!                            |
+======================================================================+
"""

    if phase == "implemented" and not state.get("validation_done"):
        return """
+======================================================================+
|  VALIDATION MISSING!                                                 |
+======================================================================+
|  Implementation is complete, but not validated.                      |
|                                                                      |
|  Next step: /validate                                                |
|                                                                      |
|  NO commit without validation!                                       |
+======================================================================+
"""

    return None


def main():
    # Get tool input from environment or stdin
    tool_input = os.environ.get("CLAUDE_TOOL_INPUT", "")

    if not tool_input:
        try:
            data = json.load(sys.stdin)
            tool_input = json.dumps(data.get("tool_input", {}))
        except (json.JSONDecodeError, Exception):
            sys.exit(0)

    try:
        data = json.loads(tool_input) if isinstance(tool_input, str) else tool_input
        file_path = data.get("file_path", "")
    except json.JSONDecodeError:
        file_path = ""

    if not file_path:
        sys.exit(0)  # No file_path, allow through

    # Check if file is always allowed
    if is_always_allowed(file_path):
        sys.exit(0)

    # Check if file requires workflow
    if not requires_workflow(file_path):
        sys.exit(0)

    # Load state and check phase
    state = load_state()
    phase = state.get("current_phase", "idle")

    # Allowed phases for implementation
    allowed_phases = ["spec_approved", "implemented", "validated"]

    if phase in allowed_phases:
        sys.exit(0)  # Workflow correct, allow through

    # Block with appropriate error message
    error = get_phase_error(state, file_path)
    if error:
        print(error, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()

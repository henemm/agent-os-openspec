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

    # Support both old (v1) and new (v2) phase names
    if phase in ["idle", "phase0_idle"]:
        return """
╔══════════════════════════════════════════════════════════════════╗
║  WORKFLOW NOT STARTED!                                           ║
╠══════════════════════════════════════════════════════════════════╣
║  You're trying to modify code without starting the workflow.     ║
║                                                                  ║
║  REQUIRED WORKFLOW:                                              ║
║  ┌─────────────────────────────────────────────────────────────┐ ║
║  │ /context    → Gather relevant context         (Phase 1)     │ ║
║  │ /analyse    → Analyse requirements            (Phase 2)     │ ║
║  │ /write-spec → Create specification            (Phase 3)     │ ║
║  │ "approved"  → User approval                   (Phase 4)     │ ║
║  │ /tdd-red    → Write FAILING tests             (Phase 5)     │ ║
║  │ /implement  → Make tests GREEN                (Phase 6)     │ ║
║  │ /validate   → Manual validation               (Phase 7)     │ ║
║  └─────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  START WITH: /context or /analyse                                ║
╚══════════════════════════════════════════════════════════════════╝
"""

    if phase in ["phase1_context"]:
        return """
╔══════════════════════════════════════════════════════════════════╗
║  CONTEXT PHASE - Analysis Required                               ║
╠══════════════════════════════════════════════════════════════════╣
║  Context is being gathered, but analysis isn't complete.         ║
║                                                                  ║
║  NEXT: /analyse                                                  ║
║                                                                  ║
║  Complete the analysis before modifying code!                    ║
╚══════════════════════════════════════════════════════════════════╝
"""

    if phase in ["analyse_done", "phase2_analyse"]:
        return """
╔══════════════════════════════════════════════════════════════════╗
║  SPEC MISSING!                                                   ║
╠══════════════════════════════════════════════════════════════════╣
║  Analysis is complete, but no spec has been written.             ║
║                                                                  ║
║  NEXT: /write-spec                                               ║
║                                                                  ║
║  The spec defines WHAT to build and HOW to test it.              ║
║  NO implementation without a spec!                               ║
╚══════════════════════════════════════════════════════════════════╝
"""

    if phase in ["spec_written", "phase3_spec"]:
        spec_file = state.get("spec_file", "unknown")
        return f"""
╔══════════════════════════════════════════════════════════════════╗
║  SPEC NOT APPROVED!                                              ║
╠══════════════════════════════════════════════════════════════════╣
║  Spec exists but USER hasn't approved it yet.                    ║
║                                                                  ║
║  Spec: {spec_file[:55]:<55}║
║                                                                  ║
║  USER must confirm with one of:                                  ║
║    "approved" | "freigabe" | "spec ok" | "lgtm"                  ║
║                                                                  ║
║  Claude CANNOT approve specs - only the user can!                ║
╚══════════════════════════════════════════════════════════════════╝
"""

    if phase in ["spec_approved", "phase4_approved"]:
        red_done = state.get("red_test_done", False)
        if not red_done:
            return """
╔══════════════════════════════════════════════════════════════════╗
║  TDD RED PHASE REQUIRED!                                         ║
╠══════════════════════════════════════════════════════════════════╣
║  Spec is approved, but you must write FAILING tests first!       ║
║                                                                  ║
║  TDD = Test-Driven Development:                                  ║
║  ┌─────────────────────────────────────────────────────────────┐ ║
║  │  RED   → Write tests that FAIL (feature doesn't exist)      │ ║
║  │  GREEN → Write code to make tests PASS                      │ ║
║  │  REFACTOR → Clean up (optional)                             │ ║
║  └─────────────────────────────────────────────────────────────┘ ║
║                                                                  ║
║  NEXT: /tdd-red                                                  ║
║                                                                  ║
║  Write tests, run them, capture the FAILURE as artifact!         ║
╚══════════════════════════════════════════════════════════════════╝
"""

    if phase in ["phase5_tdd_red"]:
        return """
╔══════════════════════════════════════════════════════════════════╗
║  TDD RED PHASE - Capture Failure First!                          ║
╠══════════════════════════════════════════════════════════════════╣
║  You're in the RED phase but haven't captured test failure yet.  ║
║                                                                  ║
║  REQUIRED:                                                       ║
║  1. Write tests for the new functionality                        ║
║  2. Run tests - they MUST FAIL                                   ║
║  3. Capture failure: /add-artifact                               ║
║                                                                  ║
║  Only after capturing RED failure can you implement!             ║
╚══════════════════════════════════════════════════════════════════╝
"""

    if phase in ["implemented", "phase6_implement"]:
        if not state.get("validation_done", False) and not state.get("green_test_done", False):
            return """
╔══════════════════════════════════════════════════════════════════╗
║  VALIDATION REQUIRED!                                            ║
╠══════════════════════════════════════════════════════════════════╣
║  Implementation done, but not validated yet.                     ║
║                                                                  ║
║  NEXT: /validate                                                 ║
║                                                                  ║
║  Verify tests are GREEN and do manual testing!                   ║
╚══════════════════════════════════════════════════════════════════╝
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

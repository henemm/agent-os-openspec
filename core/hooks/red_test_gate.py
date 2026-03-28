#!/usr/bin/env python3
"""
OpenSpec Framework - RED Test Gate

Blocks Edit/Write on implementation files until RED test is documented.

TDD Principle: Write failing tests FIRST, then implement.

This hook enforces:
- In phase4_approved or phase5_tdd_red: Block code changes until red_test_done=true
- Test files are always allowed (you need to write tests!)
- Docs and config are always allowed

Exit Codes:
- 0: Allowed
- 2: Blocked (RED test not documented)
"""

import json
import os
import sys
import re
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


# Files ALWAYS allowed (no RED test needed)
ALWAYS_ALLOWED = [
    r"\.claude/",           # Claude config
    r"docs/",               # Documentation
    r"\.md$",               # Markdown
    r"\.gitignore",
    r"tools/",              # Tools
    r"scripts/",            # Scripts
    r"config",              # Config files
    r"\.json$",             # JSON configs
    r"\.yaml$",             # YAML configs (be careful - may need override)
    r"\.yml$",
]

# Test file patterns - always allowed (you WANT to write tests)
TEST_PATTERNS = [
    r"test[_/]",
    r"[_/]test",
    r"\.test\.",
    r"spec[_/]",
    r"[_/]spec",
    r"\.spec\.",
    r"__tests__",
    r"tests/",
]

# Implementation files that require RED test
# Override in config.yaml under tdd.requires_red_test
DEFAULT_REQUIRES_RED_TEST = [
    r"src/.*\.(py|js|ts|swift|kt|java|go|rs|cpp|c)$",
    r"lib/.*\.(py|js|ts|swift|kt|java|go|rs|cpp|c)$",
    r"app/.*\.(py|js|ts|swift|kt|java|go|rs|cpp|c)$",
]


def is_always_allowed(file_path: str) -> bool:
    """Check if file is always allowed."""
    for pattern in ALWAYS_ALLOWED:
        if re.search(pattern, file_path, re.IGNORECASE):
            return True
    return False


def is_test_file(file_path: str) -> bool:
    """Check if file is a test file."""
    for pattern in TEST_PATTERNS:
        if re.search(pattern, file_path, re.IGNORECASE):
            return True
    return False


def requires_red_test(file_path: str) -> bool:
    """Check if file requires RED test before modification."""
    for pattern in DEFAULT_REQUIRES_RED_TEST:
        if re.search(pattern, file_path):
            return True
    return False


def main():
    # Get tool input
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
        sys.exit(0)

    # Always allowed files pass through
    if is_always_allowed(file_path):
        sys.exit(0)

    # Test files always allowed (we want tests!)
    if is_test_file(file_path):
        sys.exit(0)

    # Check if file requires RED test
    if not requires_red_test(file_path):
        sys.exit(0)

    # Get workflow state
    workflow = get_active_workflow()
    if not workflow:
        sys.exit(0)

    phase = workflow.get("current_phase", "phase0_idle")
    red_test_done = workflow.get("red_test_done", False)

    # Only enforce in phases where RED test matters
    # phase4_approved = spec approved, should do RED test
    # phase5_tdd_red = explicitly in RED phase
    if phase not in ["phase4_approved", "phase5_tdd_red", "phase6_implement"]:
        sys.exit(0)

    # If RED test is done, allow
    if red_test_done:
        sys.exit(0)

    # Check for RED artifacts in test_artifacts
    artifacts = workflow.get("test_artifacts", [])
    red_artifacts = [a for a in artifacts if a.get("phase") == "phase5_tdd_red"]

    if red_artifacts:
        # Has RED artifacts, allow
        sys.exit(0)

    # BLOCK - RED test not done
    workflow_name = workflow.get("name", "unknown")

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  BLOCKED: RED Test Not Done!                                     ║
╠══════════════════════════════════════════════════════════════════╣
║  You're trying to modify code without doing the RED test first.  ║
║                                                                  ║
║  Workflow: {workflow_name[:52]:<52}║
║  Phase: {phase:<56}║
║                                                                  ║
║  TDD requires:                                                   ║
║  1. Write tests that exercise the new/changed functionality      ║
║  2. Run the tests - they MUST FAIL (that's the RED!)             ║
║  3. Document the failure with /add-artifact or:                  ║
║     - Save test output to docs/artifacts/                        ║
║     - Register artifact in workflow state                        ║
║                                                                  ║
║  Commands:                                                       ║
║    /tdd-red          - Start RED phase                           ║
║    /add-artifact     - Register test evidence                    ║
║                                                                  ║
║  Only AFTER red_test_done=true can you modify implementation!    ║
╚══════════════════════════════════════════════════════════════════╝
""", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()

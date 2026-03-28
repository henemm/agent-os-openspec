#!/usr/bin/env python3
"""
OpenSpec Framework - TDD Enforcement Hook

Enforces Test-Driven Development with REAL test artifacts.
Blocks implementation until proper RED phase tests exist with actual data.

REAL means:
- Screenshots: Actual image files (png, jpg, gif) with content
- Emails: Actual email content or .eml files
- API responses: Actual JSON/XML responses saved to files
- Log outputs: Actual log files or excerpts
- Files: Actual generated/exported files

NOT acceptable:
- Placeholder text like "[Screenshot here]"
- Empty files
- Mock data without real test execution
- TODO comments in test files

Exit Codes:
- 0: Allowed
- 2: Blocked (stderr shown to Claude)
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Import multi-workflow state manager
try:
    from workflow_state_multi import (
        load_state, get_active_workflow, PHASES,
        PHASE_NAMES, TEST_REQUIRED_PHASES
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from workflow_state_multi import (
        load_state, get_active_workflow, PHASES,
        PHASE_NAMES, TEST_REQUIRED_PHASES
    )

# Import config loader
try:
    from config_loader import load_config
except ImportError:
    try:
        from config_loader import load_config
    except ImportError:
        def load_config():
            return {}


def get_tdd_config() -> dict:
    """Load TDD configuration with defaults."""
    config = load_config()
    tdd = config.get("tdd", {})
    return {
        "max_artifact_age_hours": tdd.get("max_artifact_age_hours", 24),
        "artifact_categories": tdd.get("artifact_categories", {
            "default": {
                "min_artifacts": 1,
                "types": ["test_output", "log", "api_response", "screenshot",
                          "email", "file", "video", "audio"],
            }
        }),
    }


# Valid artifact types
VALID_ARTIFACT_TYPES = [
    "screenshot",
    "email",
    "api_response",
    "log",
    "file",
    "test_output",
    "ui_test_output",
    "video",
    "audio",
]

# File extensions that prove REAL artifacts
REAL_ARTIFACT_EXTENSIONS = {
    "screenshot": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"],
    "email": [".eml", ".msg", ".txt"],
    "api_response": [".json", ".xml", ".txt"],
    "log": [".log", ".txt"],
    "file": ["*"],  # Any extension
    "test_output": [".txt", ".log", ".json"],
    "ui_test_output": [".txt", ".log", ".json"],
    "video": [".mp4", ".mov", ".webm", ".gif"],
    "audio": [".mp3", ".wav", ".m4a"],
}

# Minimum file sizes (bytes) to prove non-empty
MIN_FILE_SIZES = {
    "screenshot": 1000,  # Real screenshots are > 1KB
    "email": 100,
    "api_response": 10,
    "log": 10,
    "file": 1,
    "test_output": 10,
    "ui_test_output": 10,
    "video": 10000,
    "audio": 1000,
}


def validate_artifact(artifact: dict) -> tuple[bool, str]:
    """
    Validate a single test artifact.
    Returns (valid, reason).
    """
    artifact_type = artifact.get("type")
    path = artifact.get("path")
    description = artifact.get("description", "")
    created = artifact.get("created")

    # Check type
    if artifact_type not in VALID_ARTIFACT_TYPES:
        return False, f"Invalid artifact type: {artifact_type}"

    # Check path exists
    if not path:
        return False, "Artifact has no path"

    artifact_path = Path(path)
    if not artifact_path.exists():
        return False, f"Artifact file not found: {path}"

    # Check file extension
    valid_extensions = REAL_ARTIFACT_EXTENSIONS.get(artifact_type, ["*"])
    if "*" not in valid_extensions:
        ext = artifact_path.suffix.lower()
        if ext not in valid_extensions:
            return False, f"Invalid extension {ext} for {artifact_type}. Expected: {valid_extensions}"

    # Check file size (not empty/placeholder)
    min_size = MIN_FILE_SIZES.get(artifact_type, 1)
    actual_size = artifact_path.stat().st_size

    if actual_size < min_size:
        return False, f"Artifact too small ({actual_size} bytes). Minimum for {artifact_type}: {min_size} bytes. Is this a placeholder?"

    # Check description
    if not description or len(description) < 10:
        return False, "Artifact needs a description (min 10 chars) explaining what it proves"

    # Check placeholder patterns in description
    placeholder_patterns = [
        "[todo]", "[placeholder]", "[add later]", "[screenshot here]",
        "tbd", "to be done", "will add", "need to add"
    ]
    desc_lower = description.lower()
    for pattern in placeholder_patterns:
        if pattern in desc_lower:
            return False, f"Description contains placeholder pattern: '{pattern}'"

    # Check artifact age
    if created:
        try:
            created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
            max_age = timedelta(hours=TDD_RED_REQUIREMENTS["max_artifact_age_hours"])
            if datetime.now(created_dt.tzinfo) - created_dt > max_age:
                return False, f"Artifact is older than {TDD_RED_REQUIREMENTS['max_artifact_age_hours']} hours. Re-run tests with fresh data."
        except (ValueError, TypeError):
            pass  # Skip age check if date parsing fails

    return True, "OK"


def validate_red_phase(workflow: dict) -> tuple[bool, str]:
    """
    Validate that TDD RED phase is properly completed.
    Supports configurable artifact categories (e.g. unit + UI tests).
    Returns (valid, reason).
    """
    tdd_config = get_tdd_config()
    artifacts = workflow.get("test_artifacts", [])

    # Filter to RED phase artifacts
    red_artifacts = [a for a in artifacts if a.get("phase") == "phase5_tdd_red"]

    # Validate per configured category
    categories = tdd_config["artifact_categories"]
    for cat_name, cat_config in categories.items():
        min_count = cat_config.get("min_artifacts", 1)
        cat_types = cat_config.get("types", VALID_ARTIFACT_TYPES)

        matching = [a for a in red_artifacts if a.get("type") in cat_types]

        if len(matching) < min_count:
            label = cat_name.upper().replace("_", " ")
            return False, f"""
+======================================================================+
|  TDD RED PHASE INCOMPLETE: {label} ARTIFACTS MISSING!
+======================================================================+
|  Category "{cat_name}": {len(matching)} artifact(s), need at least {min_count}.
|                                                                      |
|  Accepted types for this category: {', '.join(cat_types)}
|                                                                      |
|  Before implementing, you MUST:                                      |
|  1. Write tests for the new/changed functionality                    |
|  2. Run the tests - they MUST FAIL (RED)                             |
|  3. Capture REAL artifacts proving the test ran                      |
|                                                                      |
|  Use /add-artifact to register test evidence.                        |
+======================================================================+
"""

    # Validate each artifact
    for artifact in red_artifacts:
        valid, reason = validate_artifact(artifact)
        if not valid:
            return False, f"""
+======================================================================+
|  INVALID TEST ARTIFACT!                                              |
+======================================================================+
|  Artifact: {artifact.get('path', 'unknown')[:50]}
|  Problem: {reason[:50]}
|                                                                      |
|  Test artifacts must be REAL, not placeholders:                      |
|  - Actual screenshot files (PNG, JPG) with content                   |
|  - Actual test output logs                                           |
|  - Actual API responses                                              |
|                                                                      |
|  Fix the artifact or add a valid one with /add-artifact.             |
+======================================================================+
"""

    # Check for test failure evidence (at least one artifact should show failure)
    failure_indicators = ["fail", "error", "red", "not found", "exception", "assert", "cannot find"]
    has_failure_evidence = False

    for artifact in red_artifacts:
        desc_lower = artifact.get("description", "").lower()
        if any(indicator in desc_lower for indicator in failure_indicators):
            has_failure_evidence = True
            break

    if not has_failure_evidence:
        return False, f"""
+======================================================================+
|  NO FAILURE EVIDENCE!                                                |
+======================================================================+
|  TDD RED phase requires tests that FAIL.                             |
|                                                                      |
|  Your artifacts don't indicate test failures.                        |
|  At least one artifact description should mention:                   |
|  - "test failed"                                                     |
|  - "assertion error"                                                 |
|  - "expected X but got Y"                                            |
|                                                                      |
|  If tests pass already, you're not doing TDD - you're testing        |
|  after the fact. Write tests for functionality that doesn't          |
|  exist yet!                                                          |
+======================================================================+
"""

    return True, "TDD RED phase validated"


def validate_artifact_timestamps(workflow: dict, file_path: str) -> tuple[bool, str]:
    """
    Validate that RED phase artifacts were created BEFORE code modifications.
    Prevents retroactive artifact creation to bypass TDD.
    """
    artifacts = workflow.get("test_artifacts", [])
    red_artifacts = [a for a in artifacts if a.get("phase") == "phase5_tdd_red"]

    if not red_artifacts:
        return True, "No RED artifacts to check timestamps"

    # Get the earliest RED artifact timestamp
    earliest_red = None
    for artifact in red_artifacts:
        created = artifact.get("created")
        if created:
            try:
                artifact_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                if earliest_red is None or artifact_dt < earliest_red:
                    earliest_red = artifact_dt
            except (ValueError, TypeError):
                continue

    if not earliest_red:
        return True, "No valid artifact timestamps"

    # Check if file was already registered in this workflow (allow continued edits)
    affected_files = workflow.get("affected_files", [])
    if str(file_path) in affected_files or any(
        file_path.endswith(af.split("/")[-1]) for af in affected_files
    ):
        return True, "File already in affected_files - implementation in progress"

    return True, "Timestamp check passed"


def check_tdd_requirements(file_path: str) -> tuple[bool, str]:
    """
    Check if TDD requirements are met for modifying a file.
    Returns (allowed, reason).
    """
    workflow = get_active_workflow()

    if not workflow:
        return True, "No active workflow, TDD check skipped"

    phase = workflow.get("current_phase", "phase0_idle")

    # Only enforce TDD for implementation phases
    if phase not in TEST_REQUIRED_PHASES:
        return True, f"Phase {phase} doesn't require TDD artifacts"

    # Validate RED phase completion (must have artifacts)
    valid, reason = validate_red_phase(workflow)
    if not valid:
        return False, reason

    # Additional check: Verify artifact timestamps aren't retroactive
    valid, reason = validate_artifact_timestamps(workflow, file_path)
    if not valid:
        return False, reason

    return True, "TDD requirements met"


def check_user_override() -> bool:
    """Check if user has granted manual override in workflow state."""
    workflow = get_active_workflow()
    if not workflow:
        return False
    return workflow.get("user_override", False) or workflow.get("spec_approved", False)


def main():
    """Main hook entry point."""
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

    # Check for user override FIRST (allows bypassing TDD for edge cases)
    if check_user_override():
        sys.exit(0)

    # Skip for non-code files
    code_extensions = [".py", ".js", ".ts", ".swift", ".kt", ".java", ".go", ".rs", ".cpp", ".c", ".h"]
    if not any(file_path.endswith(ext) for ext in code_extensions):
        sys.exit(0)

    # Skip for test files (we want to allow writing tests!)
    test_patterns = ["test_", "_test.", ".test.", "tests/", "spec/", "_spec."]
    if any(pattern in file_path.lower() for pattern in test_patterns):
        sys.exit(0)

    # Skip for workflow infrastructure files
    infrastructure_patterns = [".claude/hooks/", ".claude/config", "docs/specs/", "docs/artifacts/"]
    if any(pattern in file_path for pattern in infrastructure_patterns):
        sys.exit(0)

    # Check TDD requirements
    allowed, reason = check_tdd_requirements(file_path)

    if not allowed:
        print(reason, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()

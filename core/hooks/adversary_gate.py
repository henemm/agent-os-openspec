#!/usr/bin/env python3
"""
OpenSpec Framework - Adversary Gate

Validates REAL test output to prevent false "tests passed" claims.
Checks file freshness, size, magic bytes, and framework-specific patterns.

This hook sets `adversary_verdict` in workflow state:
- "VERIFIED": Real test output confirmed
- "UNVERIFIED": No valid test output found

Configuration (in openspec.yaml):
  adversary_gate:
    enabled: true
    max_age_minutes: 30
    min_size_bytes: 500
    test_patterns:
      - framework: "pytest"
        pass_pattern: "passed"
        fail_pattern: "FAILED|ERROR"
      - framework: "jest"
        pass_pattern: "Tests:.*passed"
        fail_pattern: "Tests:.*failed"
      - framework: "xcodebuild"
        pass_pattern: "\\*\\* TEST SUCCEEDED \\*\\*"
        fail_pattern: "\\*\\* TEST FAILED \\*\\*"
      - framework: "go_test"
        pass_pattern: "^ok\\s+"
        fail_pattern: "^FAIL\\s+"
      - framework: "cargo_test"
        pass_pattern: "test result: ok"
        fail_pattern: "test result: FAILED"

Exit Codes:
- 0: Always passes (advisory hook, sets verdict in state)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

# Import helpers
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

try:
    from workflow_state_multi import load_state, save_state, get_active_workflow
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from workflow_state_multi import load_state, save_state, get_active_workflow
    except ImportError:
        def load_state():
            return {"version": "2.0", "workflows": {}, "active_workflow": None}
        def save_state(s):
            pass
        def get_active_workflow():
            return None


# Magic bytes for image files (screenshot validation)
MAGIC_BYTES = {
    ".png": b"\x89PNG",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".gif": b"GIF8",
    ".webp": b"RIFF",
}

# Default test framework patterns
DEFAULT_TEST_PATTERNS = [
    {
        "framework": "pytest",
        "pass_pattern": r"passed",
        "fail_pattern": r"FAILED|ERROR",
    },
    {
        "framework": "jest",
        "pass_pattern": r"Tests:.*passed",
        "fail_pattern": r"Tests:.*failed",
    },
    {
        "framework": "xcodebuild",
        "pass_pattern": r"\*\* TEST SUCCEEDED \*\*",
        "fail_pattern": r"\*\* TEST FAILED \*\*",
    },
    {
        "framework": "go_test",
        "pass_pattern": r"^ok\s+",
        "fail_pattern": r"^FAIL\s+",
    },
    {
        "framework": "cargo_test",
        "pass_pattern": r"test result: ok",
        "fail_pattern": r"test result: FAILED",
    },
    {
        "framework": "npm_test",
        "pass_pattern": r"passing",
        "fail_pattern": r"failing",
    },
]


def get_adversary_config() -> dict:
    """Get adversary gate configuration."""
    config = load_config()
    adv = config.get("adversary_gate", {})
    return {
        "enabled": adv.get("enabled", True),
        "max_age_minutes": adv.get("max_age_minutes", 30),
        "min_size_bytes": adv.get("min_size_bytes", 500),
        "test_patterns": adv.get("test_patterns", DEFAULT_TEST_PATTERNS),
    }


def validate_file_freshness(file_path: Path, max_age_minutes: int) -> bool:
    """Check if file was modified within the allowed time window."""
    if not file_path.exists():
        return False
    mtime = file_path.stat().st_mtime
    age_minutes = (time.time() - mtime) / 60
    return age_minutes <= max_age_minutes


def validate_file_size(file_path: Path, min_size: int) -> bool:
    """Check if file meets minimum size requirement."""
    if not file_path.exists():
        return False
    return file_path.stat().st_size >= min_size


def validate_magic_bytes(file_path: Path) -> bool:
    """Validate file has correct magic bytes for its extension."""
    suffix = file_path.suffix.lower()
    expected = MAGIC_BYTES.get(suffix)
    if not expected:
        return True  # No magic bytes check for non-image files

    try:
        with open(file_path, "rb") as f:
            header = f.read(len(expected))
        return header.startswith(expected)
    except (OSError, IOError):
        return False


def validate_test_output(content: str, patterns: list) -> dict | None:
    """Check test output for framework-specific patterns."""
    for pattern_set in patterns:
        framework = pattern_set.get("framework", "unknown")
        pass_pat = pattern_set.get("pass_pattern", "")
        fail_pat = pattern_set.get("fail_pattern", "")

        has_pass = bool(re.search(pass_pat, content, re.MULTILINE)) if pass_pat else False
        has_fail = bool(re.search(fail_pat, content, re.MULTILINE)) if fail_pat else False

        if has_pass or has_fail:
            return {
                "framework": framework,
                "passed": has_pass and not has_fail,
                "failed": has_fail,
            }

    return None


def find_test_artifacts(project_root: Path, workflow_name: str) -> list[Path]:
    """Find test output files in artifact directories."""
    candidates = []

    # Standard artifact locations
    artifact_dirs = [
        project_root / "docs" / "artifacts" / workflow_name,
        project_root / "docs" / "artifacts",
        project_root / ".claude" / "artifacts",
    ]

    for artifact_dir in artifact_dirs:
        if not artifact_dir.exists():
            continue
        for f in artifact_dir.rglob("*"):
            if f.is_file() and f.suffix in (".log", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".webp"):
                candidates.append(f)

    return candidates


def set_verdict(verdict: str, details: str = ""):
    """Set adversary verdict in workflow state."""
    try:
        state = load_state()
        active_name = state.get("active_workflow")
        if active_name and active_name in state.get("workflows", {}):
            wf = state["workflows"][active_name]
            wf["adversary_verdict"] = verdict
            wf["adversary_details"] = details
            wf["adversary_timestamp"] = time.time()
            save_state(state)
    except Exception:
        pass


def main():
    config = get_adversary_config()

    if not config["enabled"]:
        sys.exit(0)

    # Only run on Bash tool (test commands)
    tool_name = os.environ.get("CLAUDE_TOOL", "")
    if tool_name != "Bash":
        sys.exit(0)

    # Check tool input for test-related commands
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

    # Only validate on test-like commands
    test_keywords = ["test", "pytest", "jest", "xcodebuild", "cargo test", "go test", "npm test"]
    if not any(kw in command.lower() for kw in test_keywords):
        sys.exit(0)

    # Get active workflow
    workflow = get_active_workflow()
    if not workflow:
        sys.exit(0)

    workflow_name = workflow.get("name", "default")
    project_root = get_project_root()

    # Find and validate test artifacts
    artifacts = find_test_artifacts(project_root, workflow_name)
    max_age = config["max_age_minutes"]
    min_size = config["min_size_bytes"]

    verified_artifacts = []
    for artifact in artifacts:
        if not validate_file_freshness(artifact, max_age):
            continue
        if not validate_file_size(artifact, min_size):
            continue
        if not validate_magic_bytes(artifact):
            continue

        # For text files, check for test framework output
        if artifact.suffix in (".log", ".txt"):
            try:
                content = artifact.read_text(errors="replace")
                result = validate_test_output(content, config["test_patterns"])
                if result:
                    verified_artifacts.append({
                        "path": str(artifact),
                        "framework": result["framework"],
                        "passed": result["passed"],
                    })
            except Exception:
                continue
        else:
            # Image files - validated via magic bytes + size
            verified_artifacts.append({
                "path": str(artifact),
                "type": "screenshot",
            })

    if verified_artifacts:
        details = f"Found {len(verified_artifacts)} valid artifact(s)"
        set_verdict("VERIFIED", details)
        print(f"Adversary Gate: VERIFIED - {details}", file=sys.stderr)
    else:
        set_verdict("UNVERIFIED", "No valid test artifacts found")
        print(
            "Adversary Gate: UNVERIFIED - No valid test artifacts found. "
            "Run tests and save output to docs/artifacts/.",
            file=sys.stderr,
        )

    # Advisory only - never blocks
    sys.exit(0)


if __name__ == "__main__":
    main()

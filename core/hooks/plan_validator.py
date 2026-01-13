#!/usr/bin/env python3
"""
OpenSpec Framework - Plan Validator

Validates that implementation plans are complete before allowing code changes.

Checks:
1. Required sections exist (Goal, Changes, Affected Files, Test Plan)
2. Test plan has concrete checkpoints (numbered or checkbox items)
3. Acceptance criteria are defined
4. UI changes reference existing patterns (optional)

Plan Directory: .claude/plans/ or docs/plans/
Plan Format: Markdown with specific sections

Exit Codes:
- 0: No plan, plan complete, or non-implementation file
- 2: Plan incomplete (blocks with details)

Ignores:
- Plan files themselves
- Spec files
- Hook files
- Documentation
"""

import json
import sys
import os
import re
from pathlib import Path
from datetime import datetime
import time

# Try to import config loader
try:
    from config_loader import get_project_root, load_config
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import get_project_root, load_config
    except ImportError:
        def get_project_root():
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                if (parent / ".git").exists():
                    return parent
            return cwd
        def load_config():
            return {}


# Required sections in a plan (header, description)
REQUIRED_SECTIONS = [
    ('## Goal', 'Goal/purpose of the change'),
    ('## Changes', 'List of changes to make'),
    ('## Affected Files', 'Which files will be modified'),
    ('## Test Plan', 'How to test the changes'),
]

# Alternative section names (internationalization)
SECTION_ALIASES = {
    '## Goal': ['## Ziel', '## Purpose', '## Objective'],
    '## Changes': ['## Änderungen', '## Modifications'],
    '## Affected Files': ['## Betroffene Dateien', '## Files'],
    '## Test Plan': ['## Test-Plan', '## Testing', '## Testplan'],
}

# Paths that are ignored (no plan validation)
IGNORED_PATHS = [
    r'\.claude/plans/',
    r'docs/specs/',
    r'docs/plans/',
    r'\.claude/hooks/',
    r'\.claude/settings',
    r'\.claude/agents/',
    r'\.claude/commands/',
    r'CLAUDE\.md',
    r'README',
    r'\.md$',
]

# Implementation paths that require plan validation
IMPLEMENTATION_PATHS = [
    r'src/',
    r'lib/',
    r'app/',
    r'packages/',
]


def get_plan_dirs() -> list[Path]:
    """Get possible plan directories."""
    project_root = get_project_root()
    return [
        project_root / ".claude" / "plans",
        project_root / "docs" / "plans",
    ]


def find_latest_plan() -> Path | None:
    """Find the most recent plan file."""
    for plan_dir in get_plan_dirs():
        if not plan_dir.exists():
            continue

        plan_files = list(plan_dir.glob("*.md"))
        if not plan_files:
            continue

        # Sort by modification time, newest first
        plan_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        return plan_files[0]

    return None


def is_plan_recent(plan_path: Path, max_age_hours: int = 24) -> bool:
    """Check if plan is recent enough."""
    try:
        mtime = plan_path.stat().st_mtime
        age_hours = (time.time() - mtime) / 3600
        return age_hours < max_age_hours
    except Exception:
        return False


def section_exists(content: str, section: str) -> bool:
    """Check if a section exists (including aliases)."""
    content_lower = content.lower()

    # Check main section
    if section.lower() in content_lower:
        return True

    # Check aliases
    for alias in SECTION_ALIASES.get(section, []):
        if alias.lower() in content_lower:
            return True

    return False


def check_required_sections(content: str) -> list[str]:
    """Check for missing required sections."""
    missing = []
    for section, description in REQUIRED_SECTIONS:
        if not section_exists(content, section):
            missing.append(f"'{section}' ({description})")
    return missing


def check_test_plan_quality(content: str) -> list[str]:
    """Check if test plan has concrete items."""
    warnings = []

    # Find test plan section
    test_patterns = ['## Test Plan', '## Test-Plan', '## Testing', '## Testplan']
    test_content = ""

    for pattern in test_patterns:
        match = re.search(
            rf'{re.escape(pattern)}\s*\n(.*?)(?=\n##|\Z)',
            content,
            re.DOTALL | re.IGNORECASE
        )
        if match:
            test_content = match.group(1)
            break

    if not test_content:
        return ["No test plan section found"]

    # Check for concrete items (checkboxes or numbered list)
    has_checklist = bool(re.search(r'^\s*[-*]\s*\[[ x]\]', test_content, re.MULTILINE))
    has_numbered = bool(re.search(r'^\s*\d+\.', test_content, re.MULTILINE))

    if not has_checklist and not has_numbered:
        warnings.append("Test plan should have concrete checkpoints (checkboxes or numbered list)")

    # Count test items
    test_items = re.findall(r'^\s*(?:[-*]\s*\[[ x]\]|\d+\.)', test_content, re.MULTILINE)
    if len(test_items) < 2:
        warnings.append(f"Test plan has only {len(test_items)} item(s) - at least 2 recommended")

    return warnings


def check_acceptance_criteria(content: str) -> list[str]:
    """Check if acceptance criteria are defined."""
    warnings = []

    acceptance_patterns = [
        r'acceptance criteria',
        r'akzeptanzkriterien',
        r'expected result',
        r'erwartetes ergebnis',
        r'should\s+show',
        r'must\s+display',
        r'soll.*zeigen',
        r'muss.*anzeigen',
    ]

    content_lower = content.lower()
    has_criteria = any(re.search(p, content_lower) for p in acceptance_patterns)

    if not has_criteria:
        # Check if goal section is detailed enough
        goal_match = re.search(
            r'## (?:Goal|Ziel)\s*\n(.*?)(?=\n##|\Z)',
            content,
            re.DOTALL | re.IGNORECASE
        )
        if goal_match:
            goal_content = goal_match.group(1).strip()
            if len(goal_content) < 50:
                warnings.append("Goal section too short - add concrete acceptance criteria")

    return warnings


def validate_plan(plan_path: Path) -> tuple[bool, list[str]]:
    """Validate a plan. Returns (valid, issues)."""
    errors = []
    warnings = []

    try:
        content = plan_path.read_text()
    except Exception as e:
        return False, [f"Cannot read plan file: {e}"]

    # Check required sections
    missing = check_required_sections(content)
    if missing:
        errors.extend([f"Missing section: {m}" for m in missing])

    # Check test plan quality
    test_warnings = check_test_plan_quality(content)
    warnings.extend(test_warnings)

    # Check acceptance criteria
    criteria_warnings = check_acceptance_criteria(content)
    warnings.extend(criteria_warnings)

    # Combine: errors block, warnings inform
    all_issues = errors + [f"WARNING: {w}" for w in warnings]

    return len(errors) == 0, all_issues


def is_ignored_path(file_path: str) -> bool:
    """Check if path should be ignored."""
    for pattern in IGNORED_PATHS:
        if re.search(pattern, file_path, re.IGNORECASE):
            return True
    return False


def is_implementation_path(file_path: str) -> bool:
    """Check if path is an implementation file."""
    for pattern in IMPLEMENTATION_PATHS:
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

    # Skip ignored paths
    if is_ignored_path(file_path):
        sys.exit(0)

    # Only check implementation files
    if not is_implementation_path(file_path):
        sys.exit(0)

    # Find latest plan
    plan_path = find_latest_plan()

    if not plan_path:
        # No plan found - OK, not every change needs a plan
        sys.exit(0)

    # Check if plan is recent
    if not is_plan_recent(plan_path):
        # Old plan - ignore
        sys.exit(0)

    # Validate plan
    valid, issues = validate_plan(plan_path)

    if issues:
        print("=" * 60, file=sys.stderr)
        print("PLAN VALIDATION", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print(f"Plan: {plan_path.name}", file=sys.stderr)
        print(f"Target: {file_path}", file=sys.stderr)
        print("", file=sys.stderr)

        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        print("", file=sys.stderr)

        if not valid:
            print("Plan incomplete - please complete before implementing!", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            sys.exit(2)
        else:
            print("Plan has warnings - please review.", file=sys.stderr)
            print("=" * 60, file=sys.stderr)

    sys.exit(0)


if __name__ == '__main__':
    main()

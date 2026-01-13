#!/usr/bin/env python3
"""
OpenSpec Framework - Post-Implementation Gate

Blocks further changes until USER (not Claude!) approves.

Key Principle: Claude cannot approve its own work.
The user must explicitly validate and approve changes.

Features:
- Batch Mode: Changes within N minutes are treated as one batch
- User Approval: Only user can approve (via file marker or chat phrase)
- Domain-Specific Validation: Different requirements per file type (configurable)

Lock File: .claude/pending_validation.json
Contains: {files, first_change, last_change, user_approved: false, requires: [...]}

Exit Codes:
- 0: Allowed (no lock, user approved, or within batch window)
- 2: Blocked (lock exists, batch expired, no user approval)
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

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


def get_lock_file() -> Path:
    """Get path to lock file."""
    return get_project_root() / ".claude" / "pending_validation.json"


def get_approval_file() -> Path:
    """Get path to user approval marker file."""
    return get_project_root() / ".claude" / "user_approved_validation"


# Default settings (can be overridden in config.yaml)
BATCH_WINDOW_MINUTES = 5

# Default protected paths (override in config.yaml)
DEFAULT_PROTECTED_PATHS = [
    r"src/",
    r"lib/",
    r"app/",
]

# Default exempt paths (override in config.yaml)
DEFAULT_EXEMPT_PATHS = [
    r"\.claude/",
    r"docs/",
    r"\.md$",
    r"\.git/",
    r"test",
    r"spec",
]


def get_protected_paths() -> list:
    """Get protected paths from config or defaults."""
    config = load_config()
    return config.get("post_implementation", {}).get("protected_paths", DEFAULT_PROTECTED_PATHS)


def get_exempt_paths() -> list:
    """Get exempt paths from config or defaults."""
    config = load_config()
    return config.get("post_implementation", {}).get("exempt_paths", DEFAULT_EXEMPT_PATHS)


def get_batch_window() -> int:
    """Get batch window in minutes from config or default."""
    config = load_config()
    return config.get("post_implementation", {}).get("batch_window_minutes", BATCH_WINDOW_MINUTES)


def is_protected_file(file_path: str) -> bool:
    """Check if file requires validation."""
    import re

    exempt_paths = get_exempt_paths()
    protected_paths = get_protected_paths()

    # Check exemptions first
    for exempt in exempt_paths:
        if re.search(exempt, file_path):
            return False

    # Then check protected paths
    for protected in protected_paths:
        if re.search(protected, file_path):
            return True

    return False


def load_lock() -> dict | None:
    """Load lock file if exists."""
    lock_file = get_lock_file()
    if not lock_file.exists():
        return None
    try:
        with open(lock_file, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def save_lock(lock_data: dict):
    """Save lock file."""
    lock_file = get_lock_file()
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_file, 'w') as f:
        json.dump(lock_data, f, indent=2)


def clear_lock():
    """Clear lock and approval files."""
    lock_file = get_lock_file()
    approval_file = get_approval_file()

    if lock_file.exists():
        lock_file.unlink()
    if approval_file.exists():
        approval_file.unlink()


def check_user_approval() -> bool:
    """
    Check if user has approved.

    Approval happens ONLY via:
    1. Existence of approval marker file (user must create manually)
    2. OR: User message contains approval phrase (handled by workflow_state_updater)

    Claude MUST NOT create this file!
    """
    return get_approval_file().exists()


def is_within_batch_window(lock: dict) -> bool:
    """Check if still within batch window."""
    try:
        last_change = datetime.fromisoformat(lock.get('last_change', lock.get('timestamp', '')))
        batch_minutes = get_batch_window()
        return datetime.now() - last_change < timedelta(minutes=batch_minutes)
    except (ValueError, TypeError):
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

    # Non-protected files pass through
    if not is_protected_file(file_path):
        sys.exit(0)

    # Check lock
    lock = load_lock()

    if lock is None:
        # No lock - allow change, create new lock
        now = datetime.now().isoformat()
        new_lock = {
            'files': [file_path],
            'first_change': now,
            'last_change': now,
            'user_approved': False,
            'requires_validation': True,
        }
        save_lock(new_lock)
        sys.exit(0)

    # Lock exists - check if user approved
    if check_user_approval():
        # User approved - clear lock and allow
        clear_lock()
        sys.exit(0)

    # Lock exists - check if within batch window
    if is_within_batch_window(lock):
        # Still in batch window - add file and allow
        files = lock.get('files', [])
        if file_path not in files:
            files.append(file_path)
        lock['files'] = files
        lock['last_change'] = datetime.now().isoformat()
        save_lock(lock)
        sys.exit(0)

    # Lock exists, batch expired, no approval - BLOCK
    files_list = lock.get('files', ['unknown'])
    files_str = ', '.join(files_list[:3])
    if len(files_list) > 3:
        files_str += f" (+{len(files_list) - 3} more)"

    batch_minutes = get_batch_window()
    approval_file = get_approval_file()

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  BLOCKED: Pending User Validation                                ║
╠══════════════════════════════════════════════════════════════════╣
║  Previous changes have not been validated by USER!               ║
║                                                                  ║
║  Changed files: {files_str[:47]:<47}║
║  Batch started: {lock.get('first_change', 'unknown')[:20]:<20}                        ║
║  Batch window ({batch_minutes} min) expired.                                 ║
║                                                                  ║
║  NO further changes until USER approves:                         ║
║                                                                  ║
║  Option 1: Create approval file                                  ║
║    touch {str(approval_file)[:52]:<52}║
║                                                                  ║
║  Option 2: Say in chat:                                          ║
║    "approved" / "validated" / "test ok" / "freigabe"             ║
║                                                                  ║
║  IMPORTANT: Claude cannot approve its own work!                  ║
╚══════════════════════════════════════════════════════════════════╝
""", file=sys.stderr)
    sys.exit(2)


if __name__ == '__main__':
    main()

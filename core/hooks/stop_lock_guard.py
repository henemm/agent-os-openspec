#!/usr/bin/env python3
"""
OpenSpec Framework - Stop Lock Guard (PreToolUse)

MUST be the FIRST hook in the chain.

When the user says "stop"/"stopp", the stop_lock_listener creates a lock file.
This guard blocks ALL Edit/Write/Bash operations until the user says "resume"/"weiter".

Lock File: .claude/stop.lock

Configuration (in openspec.yaml):
  stop_lock:
    enabled: true

Exit Codes:
- 0: Allowed (no lock)
- 2: Blocked (lock active)
"""

import json
import os
import sys
from pathlib import Path

try:
    from config_loader import find_project_root
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from config_loader import find_project_root
    except ImportError:
        def find_project_root():
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents):
                if (parent / ".git").exists():
                    return parent
            return cwd


def get_lock_file() -> Path:
    """Get path to stop lock file."""
    return find_project_root() / ".claude" / "stop.lock"


def main():
    tool_name = os.environ.get("CLAUDE_TOOL", "")

    # Only guard destructive tools
    if tool_name not in ("Edit", "Write", "Bash"):
        sys.exit(0)

    lock_file = get_lock_file()

    if not lock_file.exists():
        sys.exit(0)

    # Lock is active - read lock info
    try:
        lock_data = json.loads(lock_file.read_text())
        reason = lock_data.get("reason", "User requested stop")
    except (json.JSONDecodeError, Exception):
        reason = "User requested stop"

    print(
        f"STOPPED: All operations are paused.\n"
        f"Reason: {reason}\n"
        f"\n"
        f"Say 'resume', 'weiter', or 'continue' to unlock.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

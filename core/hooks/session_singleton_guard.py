#!/usr/bin/env python3
"""
Session Singleton Guard — Warns when multiple Claude sessions share a working tree.

Prevents uncommitted-file conflicts and workflow state corruption when two Claude
instances work in the same directory simultaneously.

Hook type: UserPromptSubmit (check/create lock) + Stop (cleanup)

Register in .claude/settings.json:
{
  "hooks": {
    "UserPromptSubmit": [
      {"matcher": "", "hooks": [{"type": "command",
        "command": "python3 .claude/hooks/session_singleton_guard.py"}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command",
        "command": "python3 .claude/hooks/session_singleton_guard.py --cleanup"}]}
    ]
  }
}

Exit Codes: 0 always (warns but never blocks)
"""

from hook_utils import setup_path, find_project_root
setup_path()

import json
import os
import sys
from datetime import datetime
from pathlib import Path

_root = find_project_root()


def _lock_dir() -> Path:
    return _root / ".claude" / "session-locks"


def _session_pid() -> int:
    """Return the parent PID of this hook process (= the Claude Code session PID)."""
    return os.getppid()


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _cleanup_stale_locks() -> None:
    lock_dir = _lock_dir()
    if not lock_dir.exists():
        return
    for lock_file in lock_dir.glob("*.lock"):
        try:
            pid = int(lock_file.stem)
            if not _is_running(pid):
                lock_file.unlink(missing_ok=True)
        except (ValueError, OSError):
            try:
                lock_file.unlink(missing_ok=True)
            except OSError:
                pass


def check_singleton() -> None:
    lock_dir = _lock_dir()
    lock_dir.mkdir(parents=True, exist_ok=True)

    my_pid = _session_pid()
    my_lock = lock_dir / f"{my_pid}.lock"

    _cleanup_stale_locks()

    for lock_file in lock_dir.glob("*.lock"):
        if lock_file == my_lock:
            continue
        try:
            other_pid = int(lock_file.stem)
            if _is_running(other_pid):
                print(
                    f"WARNING: Another Claude session (PID {other_pid}) is already active "
                    f"in this working tree.\n"
                    f"  Risk: uncommitted-file conflicts, workflow state corruption, "
                    f"'git add -A' capturing foreign changes.\n"
                    f"  Solution: use EnterWorktree to isolate this session.",
                    file=sys.stderr,
                )
        except (ValueError, OSError):
            pass

    try:
        my_lock.write_text(json.dumps({
            "pid": my_pid,
            "started": datetime.now().isoformat(),
        }))
    except OSError:
        pass


def cleanup() -> None:
    my_pid = _session_pid()
    my_lock = _lock_dir() / f"{my_pid}.lock"
    try:
        my_lock.unlink(missing_ok=True)
    except OSError:
        pass


def main():
    if "--cleanup" in sys.argv:
        cleanup()
    else:
        check_singleton()
    sys.exit(0)


if __name__ == "__main__":
    main()

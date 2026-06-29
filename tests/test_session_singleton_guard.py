"""Tests for session_singleton_guard._is_alive — shell-PID regression.

Core bug: os.getppid() in a hook returns the transient shell subprocess PID,
not Claude's PID. The shell exits immediately after the hook completes, so the
stored PID is dead on the very next guard call. Without the last_seen fallback,
every live session's lock file would be reaped on first PreToolUse.
"""

import json
import sys
import time
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import session_singleton_guard as ssg


# ---------------------------------------------------------------------------
# _is_alive — shell-PID fallback
# ---------------------------------------------------------------------------

def test_is_alive_live_pid():
    """Entry with a live PID is alive."""
    entry = {"pid": 1, "last_seen": time.time() - 9999}  # pid 1 (init) is always alive
    assert ssg._is_alive(entry, time.time()) is True


def test_is_alive_dead_pid_recent_last_seen():
    """Entry with dead PID but fresh last_seen is considered alive.

    This is the shell-PID bug: the hook stores the transient shell PID which
    dies immediately. The session should survive via last_seen.
    """
    entry = {"pid": 999999999, "last_seen": time.time() - 10}  # dead PID, fresh timestamp
    assert ssg._is_alive(entry, time.time()) is True


def test_is_alive_dead_pid_stale_last_seen():
    """Entry with dead PID AND stale last_seen is dead (genuinely crashed session)."""
    entry = {"pid": 999999999, "last_seen": time.time() - 9999}  # dead, stale
    assert ssg._is_alive(entry, time.time()) is False


def test_is_alive_no_pid_recent_last_seen():
    """Entry without PID falls back to last_seen only."""
    entry = {"last_seen": time.time() - 10}
    assert ssg._is_alive(entry, time.time()) is True


def test_is_alive_no_pid_stale_last_seen():
    """Entry without PID and stale last_seen is dead."""
    entry = {"last_seen": time.time() - 9999}
    assert ssg._is_alive(entry, time.time()) is False


# ---------------------------------------------------------------------------
# _reap_dead — lock file survives despite dead shell PID
# ---------------------------------------------------------------------------

def test_reap_dead_keeps_entry_with_dead_pid_fresh_last_seen(tmp_path):
    """Lock file is NOT deleted when PID is dead but last_seen is fresh.

    Regression test for the shell-PID bug: without the last_seen fallback,
    _reap_dead would delete every live session's lock file on first guard call.
    """
    locks = tmp_path / ".claude" / "session-locks"
    locks.mkdir(parents=True)

    lock_file = locks / "session-abc.json"
    entry = {"session_id": "abc", "pid": 999999999, "last_seen": time.time() - 10}
    lock_file.write_text(json.dumps(entry))

    entries = ssg._read_entries(locks)
    alive = ssg._reap_dead(entries, time.time())

    assert "abc" in alive, "Live session reaped despite fresh last_seen"
    assert lock_file.exists(), "Lock file deleted despite fresh last_seen"


def test_reap_dead_removes_entry_with_dead_pid_stale_last_seen(tmp_path):
    """Lock file IS deleted when PID is dead AND last_seen is stale (genuine crash)."""
    locks = tmp_path / ".claude" / "session-locks"
    locks.mkdir(parents=True)

    lock_file = locks / "session-xyz.json"
    entry = {"session_id": "xyz", "pid": 999999999, "last_seen": time.time() - 9999}
    lock_file.write_text(json.dumps(entry))

    entries = ssg._read_entries(locks)
    alive = ssg._reap_dead(entries, time.time())

    assert "xyz" not in alive, "Crashed session not reaped"
    assert not lock_file.exists(), "Lock file of crashed session not deleted"

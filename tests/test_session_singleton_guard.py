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


# ---------------------------------------------------------------------------
# _do_guard — worktree-mandatory logic (3.4.10)
# ---------------------------------------------------------------------------

def _make_guard_payload(tool_name: str, cwd: str, session_id: str = "sess-abc") -> dict:
    return {
        "session_id": session_id,
        "cwd": cwd,
        "tool_name": tool_name,
        "tool_input": {},
    }


MAIN_CWD = "/home/user/myproject"
WORKTREE_CWD = "/home/user/myproject/.claude/worktrees/my-feature"


def _run_guard(payload: dict) -> int:
    """Run _do_guard and return the exit code (0 = allow, 2 = block)."""
    import io
    import contextlib
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            ssg._do_guard(payload)
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0


def test_guard_read_tool_always_allowed_in_main_repo():
    """Read tool is never blocked, even in main repo (non-blocking tool)."""
    payload = _make_guard_payload("Read", MAIN_CWD)
    assert _run_guard(payload) == 0


def test_guard_grep_always_allowed_in_main_repo():
    """Grep is non-blocking — never blocked."""
    payload = _make_guard_payload("Grep", MAIN_CWD)
    assert _run_guard(payload) == 0


def test_guard_toolsearch_always_allowed_in_main_repo():
    """ToolSearch (schema loader) must never be blocked — EnterWorktree depends on it."""
    payload = _make_guard_payload("ToolSearch", MAIN_CWD)
    assert _run_guard(payload) == 0


def test_guard_edit_blocked_in_main_repo():
    """Edit is a blocking tool — blocked in main repo."""
    payload = _make_guard_payload("Edit", MAIN_CWD)
    assert _run_guard(payload) == 2


def test_guard_write_blocked_in_main_repo():
    """Write is a blocking tool — blocked in main repo."""
    payload = _make_guard_payload("Write", MAIN_CWD)
    assert _run_guard(payload) == 2


def test_guard_bash_blocked_in_main_repo():
    """Bash is a blocking tool — blocked in main repo."""
    payload = _make_guard_payload("Bash", MAIN_CWD)
    assert _run_guard(payload) == 2


def test_guard_edit_allowed_in_worktree():
    """Edit is allowed inside a worktree path."""
    payload = _make_guard_payload("Edit", WORKTREE_CWD)
    assert _run_guard(payload) == 0


def test_guard_bash_allowed_in_worktree():
    """Bash is allowed inside a worktree path."""
    payload = _make_guard_payload("Bash", WORKTREE_CWD)
    assert _run_guard(payload) == 0


def test_guard_enter_worktree_always_allowed_in_main_repo():
    """EnterWorktree is the rescue command — must never be blocked."""
    payload = _make_guard_payload("EnterWorktree", MAIN_CWD)
    assert _run_guard(payload) == 0


def test_guard_missing_session_id_allows():
    """Missing session_id → fail-safe allow."""
    payload = {"session_id": "", "cwd": MAIN_CWD, "tool_name": "Edit", "tool_input": {}}
    assert _run_guard(payload) == 0


def test_guard_missing_cwd_allows():
    """Missing cwd → fail-safe allow."""
    payload = {"session_id": "sess-abc", "cwd": "", "tool_name": "Edit", "tool_input": {}}
    assert _run_guard(payload) == 0


def test_guard_override_token_bypasses_block(tmp_path, monkeypatch):
    """Valid override token bypasses the main-repo block."""
    monkeypatch.setattr(ssg, "_has_override_token", lambda: True)
    payload = _make_guard_payload("Edit", MAIN_CWD)
    assert _run_guard(payload) == 0

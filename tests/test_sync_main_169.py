"""#169 — Haupt-Ordner nachziehen: Guard-Ausnahme und `sync-main`-Modus."""

import contextlib
import io
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import session_singleton_guard as ssg

GUARD = str(HOOKS_DIR / "session_singleton_guard.py")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(ssg, "_has_override_token", lambda: False)
    monkeypatch.setattr(ssg, "_locks_dir", lambda: tmp_path / "locks")


def _git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def _guard(tool, cwd, command=None):
    payload = {
        "session_id": "s1",
        "cwd": str(cwd),
        "tool_name": tool,
        "tool_input": {"command": command} if command is not None else {},
    }
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            ssg._do_guard(payload)
        return 0
    except SystemExit as e:
        return int(e.code or 0)


@pytest.fixture
def clones(tmp_path):
    """origin (bare) + main-Clone (Haupt-Ordner) + Pusher-Clone."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    main = tmp_path / "main"
    _git(tmp_path, "clone", "-q", str(origin), str(main))
    (main / "a.txt").write_text("1\n")
    _git(main, "add", "a.txt")
    _git(main, "commit", "-q", "-m", "init")
    _git(main, "push", "-q", "-u", "origin", "main")
    pusher = tmp_path / "pusher"
    _git(tmp_path, "clone", "-q", str(origin), str(pusher))
    return main, pusher


def _push_new_commit(pusher, name="b.txt"):
    (pusher / name).write_text("x\n")
    _git(pusher, "add", name)
    _git(pusher, "commit", "-q", "-m", "more")
    _git(pusher, "push", "-q", "origin", "main")


def _sync(cwd, monkeypatch):
    monkeypatch.chdir(cwd)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        with pytest.raises(SystemExit) as exc:
            ssg._do_sync_main()
    return int(exc.value.code or 0), out.getvalue()


# --- Guard-Ausnahme (AC-1..3) ------------------------------------------------

def test_exact_sync_main_call_allowed_in_main(tmp_path):
    assert _guard("Bash", tmp_path, f"python3 {GUARD} sync-main") == 0


def test_project_shim_path_allowed_in_main(tmp_path):
    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "session_singleton_guard.py").write_text("# shim\n")
    assert _guard("Bash", tmp_path,
                  "python3 .claude/hooks/session_singleton_guard.py sync-main") == 0


@pytest.mark.parametrize("cmd", [
    "git pull --ff-only",
    f"python3 {GUARD} sync-main; rm -rf x",
    f"python3 {GUARD} sync-main && ls",
    f"python3 {GUARD} sync-main | cat",
    f"python3 {GUARD} sync-main --foo",
    f"python3 {GUARD} sync-main $(id)",
    f"python3 {GUARD} claim --issue 1",
    "python3 /tmp/evil/session_singleton_guard.py sync-main",
    "python3 .claude/hooks/session_singleton_guard.py sync-main",  # Datei fehlt
    "bash session_singleton_guard.py sync-main",
    "",
])
def test_other_bash_blocked_in_main(tmp_path, cmd):
    assert _guard("Bash", tmp_path, cmd) == 2


@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit", "Task", "Agent"])
def test_other_tools_still_blocked(tmp_path, tool):
    assert _guard(tool, tmp_path, f"python3 {GUARD} sync-main") == 2


# --- sync-main (AC-4..8) -----------------------------------------------------

def test_sync_fast_forwards_clean_main(clones, monkeypatch):
    main, pusher = clones
    _push_new_commit(pusher)
    code, out = _sync(main, monkeypatch)
    assert code == 0, out
    assert (main / "b.txt").exists()


def test_sync_already_up_to_date(clones, monkeypatch):
    main, _ = clones
    code, out = _sync(main, monkeypatch)
    assert code == 0
    assert "aktuell" in out


def test_sync_aborts_on_modified_tracked_file(clones, monkeypatch):
    main, pusher = clones
    _push_new_commit(pusher)
    (main / "a.txt").write_text("lokal geaendert\n")
    code, out = _sync(main, monkeypatch)
    assert code != 0
    assert not (main / "b.txt").exists()
    assert (main / "a.txt").read_text() == "lokal geaendert\n"
    assert "a.txt" in out or "Änderungen" in out


def test_sync_aborts_on_diverged_history(clones, monkeypatch):
    main, pusher = clones
    _push_new_commit(pusher)
    (main / "lokal.txt").write_text("l\n")
    _git(main, "add", "lokal.txt")
    _git(main, "commit", "-q", "-m", "lokal")
    head_before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=main,
                                 capture_output=True, text=True).stdout
    code, out = _sync(main, monkeypatch)
    assert code != 0
    assert not (main / "b.txt").exists()
    head_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=main,
                                capture_output=True, text=True).stdout
    assert head_before == head_after


def test_sync_local_ahead_reports_nothing_to_do(clones, monkeypatch):
    main, _ = clones
    (main / "lokal.txt").write_text("l\n")
    _git(main, "add", "lokal.txt")
    _git(main, "commit", "-q", "-m", "lokal")
    code, out = _sync(main, monkeypatch)
    assert code == 0
    assert "voraus" in out
    assert "nachgezogen" not in out


def test_sync_upstream_with_slash_in_remote_name(clones, monkeypatch):
    main, pusher = clones
    _git(main, "remote", "rename", "origin", "team/up")
    _git(main, "branch", "--set-upstream-to=team/up/main", "main")
    _push_new_commit(pusher)
    code, out = _sync(main, monkeypatch)
    assert code == 0, out
    assert (main / "b.txt").exists()


def test_sync_aborts_when_upstream_is_local_branch(tmp_path, monkeypatch):
    repo = tmp_path / "solo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "f").write_text("1")
    _git(repo, "add", "f")
    _git(repo, "commit", "-q", "-m", "i")
    _git(repo, "branch", "dev")
    _git(repo, "branch", "--set-upstream-to=dev", "main")
    code, out = _sync(repo, monkeypatch)
    assert code != 0
    assert "Remote" in out


def test_carriage_return_not_allowed(tmp_path):
    assert _guard("Bash", tmp_path, f"python3 {GUARD} sync-main\r") == 2


def test_sync_aborts_in_worktree(clones, monkeypatch):
    main, _ = clones
    wt = main / ".claude" / "worktrees" / "w1"
    wt.mkdir(parents=True)
    code, out = _sync(wt, monkeypatch)
    assert code != 0
    assert "Worktree" in out


def test_sync_aborts_without_upstream(tmp_path, monkeypatch):
    repo = tmp_path / "solo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "f").write_text("1")
    _git(repo, "add", "f")
    _git(repo, "commit", "-q", "-m", "i")
    code, out = _sync(repo, monkeypatch)
    assert code != 0
    assert "Upstream" in out


def test_sync_aborts_outside_repo_root(clones, monkeypatch):
    main, _ = clones
    sub = main / "sub"
    sub.mkdir()
    code, out = _sync(sub, monkeypatch)
    assert code != 0

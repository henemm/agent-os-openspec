"""Issue #185: Banner warnt, wenn der Haupt-Ordner hinter origin liegt.

Echte Repos: ein Bare-Remote, ein Haupt-Ordner (Klon) und ein zweiter Klon,
der einen Commit pusht. Gemessen wird der Zweig des Haupt-Ordners — auch aus
einer Worktree-Sitzung heraus. Scheitert der Fetch, erscheint keine Zeile.
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import session_banner  # noqa: E402


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _identity(repo):
    _git(["config", "user.email", "t@example.invalid"], repo)
    _git(["config", "user.name", "T"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)


@pytest.fixture
def repos(tmp_path):
    origin = tmp_path / "origin.git"
    _git(["init", "-q", "--bare", "-b", "main", str(origin)], tmp_path)
    main = tmp_path / "main"
    _git(["clone", "-q", str(origin), str(main)], tmp_path)
    _identity(main)
    (main / "a.txt").write_text("1\n")
    _git(["add", "-A"], main)
    _git(["commit", "-qm", "init"], main)
    _git(["push", "-q", "-u", "origin", "main"], main)
    return origin, main


def _push_foreign_commit(origin, tmp_path, n=1):
    other = tmp_path / "other"
    _git(["clone", "-q", str(origin), str(other)], tmp_path)
    _identity(other)
    for i in range(n):
        (other / f"b{i}.txt").write_text("x\n")
        _git(["add", "-A"], other)
        _git(["commit", "-qm", f"c{i}"], other)
    _git(["push", "-q"], other)


def test_up_to_date_no_line(repos):
    _, main = repos
    assert session_banner.behind_lines(main) == []


def test_behind_shows_count_and_sync_main(repos, tmp_path):
    origin, main = repos
    _push_foreign_commit(origin, tmp_path, n=2)
    lines = session_banner.behind_lines(main)
    assert len(lines) == 1 and "2 Commit(s) hinter origin/main" in lines[0], lines
    assert "sync-main" in lines[0]


def test_worktree_session_measures_main_folder(repos, tmp_path):
    origin, main = repos
    wt = tmp_path / "wt"
    _git(["worktree", "add", "-q", "-b", "feat", str(wt)], main)
    _push_foreign_commit(origin, tmp_path)
    lines = session_banner.behind_lines(wt)
    assert lines and "1 Commit(s) hinter origin/main" in lines[0], lines
    assert (main / "a.txt").exists() and not (main / "b0.txt").exists(), "Haupt-Ordner unberuehrt"


def test_failed_fetch_shows_nothing_and_is_fast(repos, tmp_path):
    origin, main = repos
    _push_foreign_commit(origin, tmp_path)
    _git(["remote", "set-url", "origin", str(tmp_path / "gone.git")], main)
    start = time.monotonic()
    assert session_banner.behind_lines(main) == []
    assert time.monotonic() - start < 5


def test_not_a_repo_no_line(tmp_path):
    assert session_banner.behind_lines(tmp_path) == []

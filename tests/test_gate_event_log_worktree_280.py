"""Regressionstest fuer Issue #280, Befund 2 (#265): Gate-Event-Log
respektiert die Worktree-Wurzel.

`log_gate_event()` loeste ihren Schreibort ueber `find_project_root()` auf —
eine Funktion, die jede Worktree-Sitzung bewusst auf den Haupt-Ordner abbildet
(richtig fuer geteilten Zustand, falsch fuer eine reine Beobachtung). Folgen:
(1) Blockaden einer Worktree-Sitzung landen im Log des Haupt-Ordners;
(2) zwei Testdateien, die den Guard in-process aufrufen, haengen bei jedem
Testlauf reale Zeilen an das echte `.claude/gate-events.jsonl` an.

Aufbau analog zu tests/test_loc_gate_worktree_root_96.py: echtes Haupt-Repo,
echter `git worktree add`, `monkeypatch.chdir()` statt injizierter Root. Die
Blockade laeuft ueber die echte Produktionsfunktion `hook_utils.block()`.
"""

import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import hook_utils  # noqa: E402

LOG_REL = Path(".claude") / "gate-events.jsonl"


def _git(args: list, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _lines(path: Path) -> list:
    if not path.exists():
        return []
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


@pytest.fixture
def repo_and_worktree(tmp_path, monkeypatch):
    """Echtes Hauptrepo mit einem daran gelinkten, echten Git-Worktree."""
    # Root-Aufloesung darf nur ueber die cwd laufen, nicht ueber die Umgebung
    # der aufrufenden Sitzung.
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_TOOL_INPUT", raising=False)

    main = tmp_path / "main_repo"
    main.mkdir()
    _git(["init", "-b", "main"], main)
    _git(["config", "user.email", "test@example.invalid"], main)
    _git(["config", "user.name", "Test"], main)
    _git(["config", "commit.gpgsign", "false"], main)
    (main / "README.md").write_text("base\n")
    _git(["add", "-A"], main)
    _git(["commit", "-m", "init"], main)

    worktree = tmp_path / "worktrees" / "fix-280"
    _git(["worktree", "add", str(worktree), "-b", "fix-280"], main)
    return main, worktree


def _real_block(reason: str) -> int:
    """Echte Gate-Blockade ueber hook_utils.block() — Exit-2-Pfad."""
    with contextlib.redirect_stderr(io.StringIO()):
        with pytest.raises(SystemExit) as exc:
            hook_utils.block(reason, hook="test_280_gate", tool="Edit",
                             command_excerpt="src/app.py")
    return int(exc.value.code or 0)


def test_worktree_session_logs_to_worktree_not_main_repo(repo_and_worktree, monkeypatch):
    """AC-1: Blockade aus dem Worktree landet im Worktree-Log, nicht im Haupt-Repo."""
    main, worktree = repo_and_worktree
    monkeypatch.chdir(worktree)

    assert _real_block("BLOCKED: AC-1 worktree probe") == 2

    wt_lines = _lines(worktree / LOG_REL)
    main_lines = _lines(main / LOG_REL)
    assert main_lines == [], (
        "Worktree-Blockade darf NICHT im Log des Haupt-Repos landen — "
        f"gefunden: {main_lines!r}"
    )
    assert len(wt_lines) == 1, (
        f"Genau eine Event-Zeile im Worktree-Log erwartet, gefunden: {wt_lines!r}"
    )
    assert json.loads(wt_lines[0])["hook"] == "test_280_gate"


def test_main_repo_session_unchanged(repo_and_worktree, monkeypatch):
    """AC-2: Sitzung im Haupt-Repo loggt weiterhin ins Haupt-Repo."""
    main, worktree = repo_and_worktree
    monkeypatch.chdir(main)

    assert _real_block("BLOCKED: AC-2 main probe") == 2

    main_lines = _lines(main / LOG_REL)
    assert len(main_lines) == 1, (
        f"Haupt-Repo-Sitzung muss ins Haupt-Repo-Log schreiben: {main_lines!r}"
    )
    event = json.loads(main_lines[0])
    assert event["hook"] == "test_280_gate"
    assert event["reason"] == "BLOCKED: AC-2 main probe"
    assert _lines(worktree / LOG_REL) == [], "Worktree-Log darf unberuehrt bleiben"


def test_worktree_blockage_is_still_logged_not_silently_dropped(
    repo_and_worktree, monkeypatch
):
    """AC-3: Gegenprobe gegen Fail-Open — genau eine Zeile, nicht null, und
    zwar am Schreibort der Sitzung."""
    main, worktree = repo_and_worktree
    monkeypatch.chdir(worktree)

    assert _real_block("BLOCKED: AC-3 fail-open probe") == 2

    wt_lines = _lines(worktree / LOG_REL)
    main_lines = _lines(main / LOG_REL)
    assert len(wt_lines) + len(main_lines) == 1, (
        "Die Blockade muss genau einmal geloggt werden, nicht verschluckt "
        f"(Worktree: {wt_lines!r}, Haupt-Repo: {main_lines!r})"
    )
    assert len(wt_lines) == 1, (
        f"Das eine Event gehoert ins Worktree-Log, gefunden: {wt_lines!r}"
    )
    assert json.loads(wt_lines[0])["reason"] == "BLOCKED: AC-3 fail-open probe"


def _real_log_candidates() -> list:
    """Alle echten Logs, in die ein Leck heute oder nach dem Fix fallen koennte:
    die Wurzel dieses Checkouts und — falls dies ein Worktree ist — der
    Haupt-Ordner, auf den find_project_root() aufloest."""
    roots = [REPO_ROOT]
    main = hook_utils.find_main_repo_from_worktree(REPO_ROOT)
    if main is not None and Path(main) != REPO_ROOT:
        roots.append(Path(main))
    return [r / LOG_REL for r in roots]


def test_previously_leaky_suites_do_not_touch_the_real_log():
    """AC-4: die beiden vormals leckenden Testdateien hinterlassen 0 Zeilen im
    echten Log dieses Repositories."""
    logs = _real_log_candidates()
    before = {str(p): len(_lines(p)) for p in logs}

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_sync_main_169.py", "tests/test_session_singleton_guard.py"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=600,
    )

    after = {str(p): len(_lines(p)) for p in logs}
    assert proc.returncode == 0, (
        "Die beiden Testdateien muessen selbst gruen laufen:\n"
        + proc.stdout[-3000:] + proc.stderr[-2000:]
    )
    assert after == before, (
        "Testlauf hat Zeilen an das echte Gate-Event-Log angehaengt "
        f"(vorher {before}, nachher {after})"
    )

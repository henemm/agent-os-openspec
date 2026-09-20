"""Regressionstest fuer Issue #155 (bash_gate misst den Commit-Inhalt im
Hauptrepo statt im Worktree).

`bash_gate.main()` ermittelt die vorgemerkten Dateien mit
`git diff --cached --name-only` und `cwd=_root`, wobei `_root =
find_project_root()` einen Git-Worktree bewusst auf den HAUPTREPO-Root
aufloest. Fuer geteilten Zustand (`.claude/workflows/*.json`) ist das richtig,
fuer eine Messung am ARBEITSBAUM falsch: der Commit passiert im Worktree, im
Hauptrepo ist nichts vorgemerkt → die Liste ist leer.

Zwei Folgen:

1. `_detect_e2e_scope` sieht keine Non-Doc-Datei und meldet immer `docs-only`.
   `/70-deploy` ueberspringt daraufhin die Staging-Validierung — ein Deploy
   geht ungeprueft durch (gemeldet live aus henemm/gregor_zwanzig, 2026-09-20).
2. `required_staged_files` prueft gegen dieselbe leere Liste; auch der
   Fallback (`git diff --name-only -- <datei>`) laeuft im falschen Baum und
   sieht die Aenderung nie → das Gate blockt nie.

Gleiche Fehlerklasse wie #96 (LoC-Gate) und #144 (Spec-/Briefing-Pfade).

Kein Mock-Theater: echte Git-Repos, echter `git worktree add`, echter Commit-
Versuch. Der Hook laeuft als SUBPROZESS mit `cwd=worktree` — nur so wird das
tatsaechliche `cwd=`-Verhalten geprueft. Ein Direktaufruf von
`_detect_e2e_scope()` wuerde vor UND nach dem Fix identisch bestehen, weil der
Defekt nicht im Klassifikator liegt, sondern darin, was in ihn hineingereicht
wird.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
BASH_GATE = HOOKS_DIR / "bash_gate.py"

WF_NAME = "fix-155"


def _git(args: list, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo_and_worktree(tmp_path):
    """Echtes Hauptrepo mit daran gelinktem, echtem Git-Worktree.

    Der Workflow-State liegt — wie in Produktion — ausschliesslich im
    Hauptrepo; der Worktree traegt nur seine `active_workflow`-Identitaet
    (resolve_active_workflow ignoriert in Worktrees bewusst die Env-Var, #58).
    """
    main = tmp_path / "main_repo"
    main.mkdir()
    _git(["init", "-b", "main"], main)
    _git(["config", "user.email", "test@example.invalid"], main)
    _git(["config", "user.name", "Test"], main)
    _git(["config", "commit.gpgsign", "false"], main)

    (main / "src").mkdir()
    (main / "src" / "app.py").write_text("BASE = 0\n")
    (main / "docs").mkdir()
    (main / "docs" / "readme.md").write_text("# doc\n")
    (main / "CHANGELOG.md").write_text("# Changelog\n")
    _git(["add", "-A"], main)
    _git(["commit", "-m", "init"], main)

    worktree = tmp_path / "worktrees" / WF_NAME
    _git(["worktree", "add", str(worktree), "-b", WF_NAME], main)

    # Workflow-State im Hauptrepo. `workflow_type: bug` laesst das
    # Adversary-Gate (5c) passieren, damit die Scope-Erkennung (5d) ueberhaupt
    # erreicht wird — 5c blockt sonst vorher und der Hook endet mit Exit 2.
    wf_dir = main / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / f"{WF_NAME}.json").write_text(json.dumps({
        "name": WF_NAME,
        "current_phase": "phase6_implement",
        "workflow_type": "bug",
    }))
    (worktree / ".claude").mkdir(parents=True, exist_ok=True)
    (worktree / ".claude" / "active_workflow").write_text(WF_NAME)

    return main, worktree


def _run_gate(cwd: Path, command: str = "git commit -m 'x'"):
    """Ruft bash_gate.py als Hook auf. Gibt (returncode, stderr) zurueck."""
    env = dict(os.environ)
    # Die Sitzungs-Env zeigt auf das ECHTE Repo — sie wuerde `_root` dorthin
    # umbiegen und den Test am Testobjekt vorbeilaufen lassen.
    for var in ("CLAUDE_PROJECT_DIR", "CLAUDE_TOOL_INPUT",
                "OPENSPEC_ACTIVE_WORKFLOW", "OPENSPEC_FRAMEWORK"):
        env.pop(var, None)
    payload = json.dumps({"tool_input": {"command": command}})
    proc = subprocess.run(
        [sys.executable, str(BASH_GATE)],
        cwd=str(cwd), input=payload, capture_output=True, text=True, timeout=60,
    )
    return proc.returncode, proc.stderr


def _scope(main: Path) -> str:
    state = json.loads((main / ".claude" / "workflows" / f"{WF_NAME}.json").read_text())
    return state.get("e2e_scope", "<nicht gesetzt>")


class TestE2eScopeMeasuresWorktree:
    def test_production_file_in_worktree_is_not_docs_only(self, repo_and_worktree):
        """Kern-Regression: im Worktree ist eine Produktivdatei vorgemerkt.

        Vor dem Fix sah das Gate den leeren Hauptrepo-Index, meldete
        `docs-only` — und `/70-deploy` ueberspringt die Staging-Validierung,
        die die Spec ausdruecklich verlangt.
        """
        main, worktree = repo_and_worktree
        (worktree / "src" / "app.py").write_text("BASE = 1\n")
        _git(["add", "src/app.py"], worktree)

        rc, stderr = _run_gate(worktree)

        assert rc == 0, f"Die Scope-Erkennung darf nie blocken — stderr: {stderr!r}"
        assert _scope(main) == "backend", (
            "Eine vorgemerkte Produktivdatei im Worktree muss als `backend` "
            f"erkannt werden, gemeldet wurde {_scope(main)!r} — das Gate hat "
            "den (leeren) Hauptrepo-Index gemessen"
        )

    def test_docs_only_commit_stays_docs_only(self, repo_and_worktree):
        """Gegenprobe: ein reiner Doku-Commit bleibt `docs-only`. Der Fix darf
        nicht einfach jeden Commit hochstufen."""
        main, worktree = repo_and_worktree
        (worktree / "docs" / "readme.md").write_text("# doc geaendert\n")
        _git(["add", "docs/readme.md"], worktree)

        rc, stderr = _run_gate(worktree)

        assert rc == 0, f"stderr: {stderr!r}"
        assert _scope(main) == "docs-only", (
            f"Reiner Doku-Commit muss `docs-only` bleiben, war {_scope(main)!r}"
        )

    def test_worktree_does_not_inherit_main_repo_index(self, repo_and_worktree):
        """Gegenrichtung: das HAUPTREPO hat eine Produktivdatei vorgemerkt, der
        Worktree committet nur Doku. Fremder Index darf dem eigenen Commit
        nicht zugeschrieben werden."""
        main, worktree = repo_and_worktree
        (main / "src" / "app.py").write_text("BASE = 99\n")
        _git(["add", "src/app.py"], main)
        (worktree / "docs" / "readme.md").write_text("# nur doku\n")
        _git(["add", "docs/readme.md"], worktree)

        rc, stderr = _run_gate(worktree)

        assert rc == 0, f"stderr: {stderr!r}"
        assert _scope(main) == "docs-only", (
            "Der eigene Commit enthaelt nur Doku — der Produktiv-Index eines "
            f"fremden Baums darf nicht einfliessen, war {_scope(main)!r}"
        )

    def test_main_repo_session_unchanged(self, repo_and_worktree):
        """Rueckwaertskompatibilitaet: laeuft die Sitzung im Hauptrepo, bleibt
        das Verhalten identisch zum Bestand."""
        main, _worktree = repo_and_worktree
        (main / ".claude" / "active_workflow").write_text(WF_NAME)
        (main / "src" / "app.py").write_text("BASE = 2\n")
        _git(["add", "src/app.py"], main)

        rc, stderr = _run_gate(main)

        assert rc == 0, f"stderr: {stderr!r}"
        assert _scope(main) == "backend", (
            f"Hauptrepo-Sitzung muss ihren eigenen Index messen, war {_scope(main)!r}"
        )

    def test_commit_dash_a_is_not_docs_only(self, repo_and_worktree):
        """`git commit -a` merkt erst beim Commit vor — zum Zeitpunkt des Hooks
        ist der Index leer. Ohne Rueckfallebene meldet die Scope-Erkennung auch
        nach der Worktree-Korrektur `docs-only` und `/70-deploy` ueberspringt
        weiterhin die Staging-Validierung."""
        main, worktree = repo_and_worktree
        (worktree / "src" / "app.py").write_text("BASE = 3\n")  # bewusst NICHT gestaged

        rc, stderr = _run_gate(worktree, command="git commit -am 'x'")

        assert rc == 0, f"stderr: {stderr!r}"
        assert _scope(main) == "backend", (
            "Bei `git commit -a` muss der geaenderte Arbeitsbaum als Inhalt "
            f"gelten, gemeldet wurde {_scope(main)!r}"
        )


    def test_amend_of_production_commit_is_not_docs_only(self, repo_and_worktree):
        """`git commit --amend` bei sauberem Baum: der Index ist leer UND
        `git diff HEAD` ist leer — der Rueckfall auf den Arbeitsbaum greift
        nicht. Ohne eigene Behandlung meldet das Gate `docs-only` und
        ueberschreibt damit einen zuvor korrekten `backend`-Wert."""
        main, worktree = repo_and_worktree
        (worktree / "src" / "app.py").write_text("BASE = 6\n")
        _git(["add", "src/app.py"], worktree)
        _git(["commit", "-m", "prod"], worktree)

        rc, stderr = _run_gate(worktree, command="git commit --amend --no-edit")

        assert rc == 0, f"stderr: {stderr!r}"
        assert _scope(main) == "backend", (
            "Der nachgebesserte Commit traegt Produktivcode — gemeldet wurde "
            f"{_scope(main)!r}"
        )

    def test_amend_of_docs_commit_stays_docs_only(self, repo_and_worktree):
        """Gegenprobe zum Amend-Pfad: ein nachgebesserter Doku-Commit bleibt
        `docs-only`."""
        main, worktree = repo_and_worktree
        (worktree / "docs" / "readme.md").write_text("# nur doku\n")
        _git(["add", "docs/readme.md"], worktree)
        _git(["commit", "-m", "docs"], worktree)

        rc, stderr = _run_gate(worktree, command="git commit --amend --no-edit")

        assert rc == 0, f"stderr: {stderr!r}"
        assert _scope(main) == "docs-only", (
            f"Nachgebesserter Doku-Commit muss `docs-only` bleiben, war {_scope(main)!r}"
        )

    def test_amend_includes_newly_staged_file(self, repo_and_worktree):
        """Beim Amend zaehlt der Inhalt des ERGEBNIS-Commits: vorgemerkte
        Nachbesserung UND der urspruengliche Commit."""
        main, worktree = repo_and_worktree
        (worktree / "src" / "app.py").write_text("BASE = 7\n")
        _git(["add", "src/app.py"], worktree)
        _git(["commit", "-m", "prod"], worktree)
        (worktree / "docs" / "readme.md").write_text("# nachtrag\n")
        _git(["add", "docs/readme.md"], worktree)

        rc, stderr = _run_gate(worktree, command="git commit --amend --no-edit")

        assert rc == 0, f"stderr: {stderr!r}"
        assert _scope(main) == "backend", (
            "Der Produktivcode aus dem urspruenglichen Commit gehoert zum "
            f"Ergebnis-Commit — gemeldet wurde {_scope(main)!r}"
        )


class TestRequiredStagedFilesInWorktree:
    """Zweite Haelfte von #155: dieselbe Wurzel macht `required_staged_files`
    wirkungslos."""

    @staticmethod
    def _write_config(main: Path) -> None:
        (main / "config.yaml").write_text(
            "pre_commit:\n  required_staged_files:\n    - CHANGELOG.md\n"
        )

    def test_unstaged_required_file_blocks_in_worktree(self, repo_and_worktree):
        """Die Pflichtdatei ist im Worktree geaendert, aber nicht vorgemerkt →
        das Gate muss blocken. Vor dem Fix sah der Fallback-`git diff` den
        sauberen Hauptrepo-Baum und liess still durch."""
        main, worktree = repo_and_worktree
        self._write_config(main)
        (worktree / "CHANGELOG.md").write_text("# Changelog\n- neu\n")
        (worktree / "src" / "app.py").write_text("BASE = 4\n")
        _git(["add", "src/app.py"], worktree)

        rc, stderr = _run_gate(worktree)

        assert rc == 2, (
            "Ungestagte Pflichtdatei muss blocken — das Gate hat den "
            f"Hauptrepo-Baum geprueft. rc={rc}, stderr={stderr!r}"
        )
        assert "CHANGELOG.md" in stderr

    def test_staged_required_file_passes_in_worktree(self, repo_and_worktree):
        """Gegenprobe: ist die Pflichtdatei vorgemerkt, darf nichts blocken."""
        main, worktree = repo_and_worktree
        self._write_config(main)
        (worktree / "CHANGELOG.md").write_text("# Changelog\n- neu\n")
        _git(["add", "CHANGELOG.md"], worktree)

        rc, stderr = _run_gate(worktree)

        assert rc == 0, (
            f"Vorgemerkte Pflichtdatei darf nicht blocken. stderr={stderr!r}"
        )


class TestStateStaysInMainRepo:
    def test_scope_is_written_to_main_repo_state(self, repo_and_worktree):
        """Die andere Haelfte der Trennung: gemessen wird im Worktree, der Wert
        landet weiterhin im GETEILTEN State im Hauptrepo."""
        main, worktree = repo_and_worktree
        (worktree / "src" / "app.py").write_text("BASE = 5\n")
        _git(["add", "src/app.py"], worktree)

        rc, _ = _run_gate(worktree)

        assert rc == 0
        assert _scope(main) == "backend"
        assert not (worktree / ".claude" / "workflows").exists(), (
            "Der Fix darf keine zweite, worktree-lokale Workflow-Ablage anlegen"
        )

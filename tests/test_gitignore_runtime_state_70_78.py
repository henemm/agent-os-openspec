"""Laufzeit-Zustand gehoert nie in ein Repository (Issues #70, #78).

Zwei Befunde derselben Klasse:

- **#78:** `workflow.py start <name>` legt `.claude/active_workflow` im
  Projektrepo an. Die Datei ist reiner Werkzeug-Zustand, erscheint aber als
  untracked im `git status` — und existiert genau waehrend des Workflows, also
  genau dann, wenn committet wird. Ein `git add -A` nimmt sie mit. In
  gregor_zwanzig #1409 hat ein Pruef-Agent sie zu Recht als Regelverstoss
  gemeldet; die Ursache lag im Werkzeug, nicht im Projekt.
- **#70:** `.worktrees/` fehlt in der `.gitignore` dieses Repos selbst.
  `git worktree add .worktrees/<name>` hinterlaesst dadurch einen untracked
  Eintrag — im Repo, dessen eigener Release-Waechter einen sauberen
  Arbeitsbaum verlangt.

Das Framework kennt die Liste seiner Laufzeit-Dateien als einziges: es legt
sie an. Also traegt es sie auch ein, statt es jedem Konsumenten-Projekt
einzeln zu ueberlassen.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import setup as setup_py  # noqa: E402


class TestFrameworkRepoGitignore:
    def test_worktrees_directory_is_ignored(self):
        """Issue #70."""
        entries = [
            line.strip()
            for line in (REPO_ROOT / ".gitignore").read_text().splitlines()
        ]
        assert ".worktrees/" in entries


class TestRuntimeEntryList:
    def test_list_contains_active_workflow(self):
        """Issue #78 — der ausloesende Eintrag."""
        assert ".claude/active_workflow" in setup_py.GITIGNORE_RUNTIME_ENTRIES

    def test_list_covers_the_other_runtime_state(self):
        """Dieselbe Kategorie, gleiche Behandlung — sonst faengt man den
        naechsten Einzelfall wieder einzeln."""
        for entry in (".claude/workflows/", ".claude/session-locks/",
                      ".claude/stop_lock.json", ".claude/user_override_token.json"):
            assert entry in setup_py.GITIGNORE_RUNTIME_ENTRIES


class TestEnsureGitignoreEntries:
    def test_creates_file_when_missing(self, tmp_path, capsys):
        setup_py.ensure_gitignore_entries(tmp_path)
        capsys.readouterr()

        text = (tmp_path / ".gitignore").read_text()
        for entry in setup_py.GITIGNORE_RUNTIME_ENTRIES:
            assert entry in text

    def test_keeps_existing_content(self, tmp_path, capsys):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n*.log\n")

        setup_py.ensure_gitignore_entries(tmp_path)
        capsys.readouterr()

        text = gitignore.read_text()
        assert "node_modules/" in text
        assert "*.log" in text
        assert ".claude/active_workflow" in text

    def test_is_idempotent(self, tmp_path, capsys):
        setup_py.ensure_gitignore_entries(tmp_path)
        first = (tmp_path / ".gitignore").read_text()
        setup_py.ensure_gitignore_entries(tmp_path)
        capsys.readouterr()

        assert (tmp_path / ".gitignore").read_text() == first

    def test_does_not_duplicate_an_existing_entry(self, tmp_path, capsys):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(".claude/active_workflow\n")

        setup_py.ensure_gitignore_entries(tmp_path)
        capsys.readouterr()

        lines = [l.strip() for l in gitignore.read_text().splitlines()]
        assert lines.count(".claude/active_workflow") == 1

    def test_tolerates_missing_trailing_newline(self, tmp_path, capsys):
        """Eine Datei ohne Schlusszeilenumbruch darf nicht dazu fuehren, dass
        der erste neue Eintrag an die letzte Zeile klebt."""
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("build/")

        setup_py.ensure_gitignore_entries(tmp_path)
        capsys.readouterr()

        lines = [l.strip() for l in gitignore.read_text().splitlines()]
        assert "build/" in lines
        assert ".claude/active_workflow" in lines


class TestInstallersWriteGitignore:
    def test_plugin_mode_install_writes_entries(self, tmp_path, capsys):
        setup_py.install_plugin_mode(tmp_path, [])
        capsys.readouterr()

        text = (tmp_path / ".gitignore").read_text()
        assert ".claude/active_workflow" in text

    def test_update_writes_entries_for_existing_project(self, tmp_path, capsys):
        setup_py.install_plugin_mode(tmp_path, [])
        (tmp_path / ".gitignore").unlink()

        setup_py.update_project(tmp_path, [])
        capsys.readouterr()

        assert ".claude/active_workflow" in (tmp_path / ".gitignore").read_text()

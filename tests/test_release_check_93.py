"""Tests fuer den Release-Waechter aus Issue #93.

Das Repo ist gleichzeitig Arbeitsordner und Auslieferungsquelle. Der Waechter
soll genau die Zustaende abfangen, die im Issue gemessen wurden: ein
Arbeitsbranch statt `main`, ein ungemergter Commit vor `origin/main`, dazu
unversionierte Dateien.

Getestet wird gegen echte Git-Repos auf `tmp_path` — der Waechter arbeitet
ausschliesslich mit `git`-Aufrufen, gemockte Ausgaben wuerden nichts belegen.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import release_check  # noqa: E402


def _git(args: list, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Klon-Paar (origin + Arbeitskopie), damit der Abgleich echt ist."""
    origin = tmp_path / "origin.git"
    _git(["init", "--bare", "-b", "main", str(origin)], tmp_path)

    work = tmp_path / "work"
    work.mkdir()
    _git(["init", "-b", "main"], work)
    _git(["config", "user.email", "test@example.invalid"], work)
    _git(["config", "user.name", "Test"], work)
    _git(["config", "commit.gpgsign", "false"], work)
    (work / "README.md").write_text("# x\n")
    _git(["add", "-A"], work)
    _git(["commit", "-m", "init"], work)
    _git(["remote", "add", "origin", str(origin)], work)
    _git(["push", "-u", "origin", "main"], work)

    monkeypatch.setattr(release_check, "REPO_ROOT", work)
    return work


class TestChangelogParsing:
    def test_reads_topmost_version(self):
        text = "# Changelog\n\n## [3.11.4] - 2026-08-10\n\nx\n\n## [3.11.3] - 2026-08-09\n"
        assert release_check.latest_changelog_version(text) == "3.11.4"

    def test_unreleased_block_is_not_a_version(self):
        """Ein offener Unreleased-Block heisst: der Stand ist nicht fertig
        dokumentiert — daraus darf kein Release entstehen."""
        text = "# Changelog\n\n## [Unreleased]\n\n- wip\n\n## [3.11.3] - 2026-08-09\n"
        assert release_check.latest_changelog_version(text) is None

    def test_no_version_heading_at_all(self):
        assert release_check.latest_changelog_version("# Changelog\n\nnichts\n") is None


class TestChangelogSection:
    """Der Text des GitHub-Releases kommt aus dem CHANGELOG — es gibt nur eine
    Quelle, damit Release-Notiz und CHANGELOG nicht auseinanderlaufen."""

    TEXT = (
        "# Changelog\n\nVorspann\n\n"
        "## [3.11.4] - 2026-08-10\n\n### Added\n\nNeues Ding.\n\n"
        "## [3.11.3] - 2026-08-09\n\n### Fixed\n\nAelteres Ding.\n"
    )

    def test_extracts_only_the_requested_section(self):
        section = release_check.changelog_section(self.TEXT, "3.11.4")
        assert "Neues Ding." in section
        assert "Aelteres Ding." not in section, "Nachbarabschnitt darf nicht mitkommen"
        assert "Vorspann" not in section

    def test_own_heading_is_not_repeated(self):
        """Der Release-Titel ist schon der Tag — die Ueberschrift noch einmal im
        Text waere doppelt."""
        section = release_check.changelog_section(self.TEXT, "3.11.4")
        assert not section.startswith("## [3.11.4]")

    def test_last_section_runs_to_end_of_file(self):
        section = release_check.changelog_section(self.TEXT, "3.11.3")
        assert "Aelteres Ding." in section

    def test_unknown_version_yields_empty(self):
        assert release_check.changelog_section(self.TEXT, "9.9.9") == ""


class TestVersionMatch:
    def test_match_passes(self):
        ok, _ = release_check.check_version_match("3.11.4", "3.11.4")
        assert ok

    def test_mismatch_names_both(self):
        ok, detail = release_check.check_version_match("3.11.4", "3.11.3")
        assert not ok
        assert "3.11.4" in detail and "3.11.3" in detail

    def test_unreleased_blocks(self):
        ok, detail = release_check.check_version_match("3.11.4", None)
        assert not ok and "Unreleased" in detail


class TestGitState:
    def test_clean_main_in_sync_passes_all_three(self, repo):
        assert release_check.check_branch()[0]
        assert release_check.check_clean_tree()[0]
        assert release_check.check_in_sync()[0]

    def test_working_branch_is_rejected(self, repo):
        """Der gemessene Zustand aus dem Issue: ein Arbeitsbranch war
        ausgecheckt, als der Katalog ausgeliefert haette."""
        _git(["checkout", "-b", "fix-1478-gate-false-positives-teil1"], repo)
        ok, detail = release_check.check_branch()
        assert not ok
        assert "fix-1478-gate-false-positives-teil1" in detail

    def test_untracked_files_are_rejected(self, repo):
        """Ebenfalls gemessen: unversionierte .claude/pending_validation_*.json."""
        (repo / ".claude").mkdir()
        (repo / ".claude" / "pending_validation_fix-53.json").write_text("{}")
        ok, detail = release_check.check_clean_tree()
        assert not ok
        assert "pending_validation" in detail

    def test_modified_file_is_rejected(self, repo):
        (repo / "README.md").write_text("# geaendert\n")
        assert not release_check.check_clean_tree()[0]

    def test_unpushed_commit_is_rejected(self, repo):
        """Der Kern des Issues: ein Commit vor origin/main. Genau das haette
        eine ungepruefte Aenderung an bash_gate.py ausgeliefert."""
        (repo / "hook.py").write_text("x = 1\n")
        _git(["add", "-A"], repo)
        _git(["commit", "-m", "ungemergt"], repo)
        ok, detail = release_check.check_in_sync()
        assert not ok
        assert "1 Commit(s) vor" in detail

    def test_behind_origin_is_rejected(self, repo, tmp_path):
        """Auch die Gegenrichtung: ein veralteter Arbeitsordner wuerde einen
        Tag auf einen Stand setzen, den niemand sonst hat."""
        other = tmp_path / "other"
        _git(["clone", str(tmp_path / "origin.git"), str(other)], tmp_path)
        _git(["config", "user.email", "test@example.invalid"], other)
        _git(["config", "user.name", "Test"], other)
        _git(["config", "commit.gpgsign", "false"], other)
        (other / "neu.txt").write_text("neu\n")
        _git(["add", "-A"], other)
        _git(["commit", "-m", "von woanders"], other)
        _git(["push"], other)

        ok, detail = release_check.check_in_sync()
        assert not ok
        assert "hinter" in detail


class TestTagCheck:
    def test_free_tag_passes(self, repo):
        ok, _ = release_check.check_tag_free("agent-os-openspec--v9.9.9")
        assert ok

    def test_existing_tag_is_rejected(self, repo):
        _git(["tag", "agent-os-openspec--v3.11.4"], repo)
        ok, detail = release_check.check_tag_free("agent-os-openspec--v3.11.4")
        assert not ok
        assert "existiert bereits" in detail


class TestTagNaming:
    def test_tag_follows_claude_code_dependency_convention(self):
        """`{plugin-name}--v{version}` ist die Form, die Claude Code fuer
        Plugin-Abhaengigkeiten versteht."""
        tag = release_check.TAG_TEMPLATE.format(name="agent-os-openspec", version="3.11.4")
        assert tag == "agent-os-openspec--v3.11.4"

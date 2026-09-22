"""Die Release-Automatik darf nicht still scheitern (Issue #204).

## Der Vorfall

Am 21./22.09.2026 lag `main` auf 3.27.2, der letzte Tag war
`agent-os-openspec--v3.27.0`. **Zwei fertige Versionen wurden nie
veroeffentlicht** — die Konsumenten-Projekte liefen weiter auf 3.27.0, obwohl
CHANGELOG und Issues beide Versionen als erledigt auswiesen. Innerhalb von
zwoelf Stunden trat der Fehlschlag dreimal auf (Release-Laeufe #43, #44, #45).

## Zwei Fehler, zwei Tests

1. **Ein LEERER `## [Unreleased]`-Abschnitt blockierte das Release.**
   `latest_changelog_version` liefert `None`, sobald der oberste Eintrag
   `Unreleased` heisst. Die Absicht ist richtig — ein Release mit offenem,
   *gefuelltem* Unreleased-Block waere unvollstaendig dokumentiert. Eine leere
   Ueberschrift dokumentiert aber gar nichts; sie ist der Keep-a-Changelog-
   Platzhalter, den jeder stehen laesst.

2. **Der Fehlschlag war unsichtbar.** `release_check.py` laeuft ausschliesslich
   in `release.yml`, also NACH dem Merge. Der Job wird rot, aber nach dem Merge
   schaut niemand in die Actions. Deshalb gibt es jetzt `--content-only`: die
   inhaltlichen Pruefungen laufen schon im Pull Request, wo ein rotes Kreuz
   gesehen wird. Ergaenzt um eine Pruefung, die den Vorfall selbst erkennt —
   liegt auf `main` eine Version ohne Tag, ist das letzte Release nicht
   herausgekommen.

Die Trennung ist inhaltlich: `Branch`, `Arbeitsbaum` und `Abgleich` beschreiben
den *Zustand des Release-Laufs* und koennen im PR gar nicht erfuellt sein.
`Version`, `README`, `Tag` und `Skills` beschreiben den *Inhalt des Commits*
und gelten auf jedem Branch.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import release_check  # noqa: E402


HEADER = (
    "# Changelog\n"
    "\n"
    "Beschreibung.\n"
    "\n"
)


class TestEmptyUnreleasedDoesNotBlock:
    def test_empty_unreleased_falls_through_to_version(self):
        """Der ausloesende Fall: Ueberschrift ohne Inhalt."""
        text = HEADER + "## [Unreleased]\n\n## [3.28.0] - 2026-09-21\n\n### Fixed\n\nEtwas.\n"
        assert release_check.latest_changelog_version(text) == "3.28.0"

    def test_unreleased_with_only_blank_lines_falls_through(self):
        text = HEADER + "## [Unreleased]\n\n\n   \n\n## [3.28.0] - 2026-09-21\n\nEtwas.\n"
        assert release_check.latest_changelog_version(text) == "3.28.0"

    def test_filled_unreleased_still_blocks(self):
        """Die urspruengliche Absicht bleibt: dokumentierte, aber nicht
        versionierte Aenderungen duerfen kein Release ausloesen."""
        text = (
            HEADER
            + "## [Unreleased]\n\n### Added\n\nEin neues Feature, noch ohne Version.\n\n"
            + "## [3.28.0] - 2026-09-21\n\nEtwas.\n"
        )
        assert release_check.latest_changelog_version(text) is None

    def test_unreleased_with_bare_subheading_still_blocks(self):
        """Eine angefangene Rubrik zaehlt als Inhalt — wer `### Added` schreibt,
        hat etwas vor. Im Zweifel blockieren."""
        text = HEADER + "## [Unreleased]\n\n### Added\n\n## [3.28.0] - 2026-09-21\n\nEtwas.\n"
        assert release_check.latest_changelog_version(text) is None

    def test_empty_unreleased_as_only_heading_yields_none(self):
        text = HEADER + "## [Unreleased]\n\n"
        assert release_check.latest_changelog_version(text) is None

    def test_regular_changelog_unchanged(self):
        text = HEADER + "## [3.28.0] - 2026-09-21\n\nEtwas.\n\n## [3.27.0] - 2026-09-20\n"
        assert release_check.latest_changelog_version(text) == "3.28.0"

    def test_no_headings_yields_none(self):
        assert release_check.latest_changelog_version("# Changelog\n\nnichts\n") is None

    def test_real_repo_changelog_resolves(self):
        """Gegenprobe am echten Stand — der Fix darf den Normalfall nicht brechen."""
        found = release_check.latest_changelog_version(
            (REPO_ROOT / "CHANGELOG.md").read_text()
        )
        assert found is not None, "das CHANGELOG dieses Repos blockiert das Release"


class TestPreviousReleasePublished:
    """Erkennt den Vorfall selbst: eine Version auf `main` ohne Tag."""

    def test_tagged_main_version_passes(self):
        ok, _ = release_check.check_main_release_published("3.28.0", "3.28.0")
        assert ok

    def test_untagged_main_version_fails(self):
        """Der reale Zustand am 21.09.: main 3.27.2, letzter Tag 3.27.0."""
        ok, detail = release_check.check_main_release_published("3.27.2", "3.27.0")
        assert not ok
        assert "3.27.2" in detail
        assert "3.27.0" in detail

    def test_tag_ahead_of_main_passes(self):
        """Kann bei laufendem Release kurz auftreten — kein Fehlerfall."""
        ok, _ = release_check.check_main_release_published("3.28.0", "3.29.0")
        assert ok

    def test_no_tags_at_all_passes(self):
        """Ein Repo vor dem ersten Release darf nicht blockiert werden."""
        ok, _ = release_check.check_main_release_published("0.1.0", None)
        assert ok

    def test_unknown_main_version_passes(self):
        """Laesst sich `main` nicht lesen (flacher Klon), wird nicht blockiert —
        eine Pruefung, die an einer Git-Eigenheit scheitert, ist schlimmer als
        der Fehler, den sie sucht."""
        ok, _ = release_check.check_main_release_published(None, "3.27.0")
        assert ok


class TestTagVersionParsing:
    def test_extracts_versions_from_tag_names(self):
        tags = [
            "agent-os-openspec--v3.26.7",
            "agent-os-openspec--v3.27.0",
            "archive/issue-53-secrets-guard",
        ]
        assert release_check.latest_tagged_version(tags, "agent-os-openspec") == "3.27.0"

    def test_sorts_numerically_not_lexically(self):
        """'3.9.0' ist kleiner als '3.28.0' — als Text waere es groesser."""
        tags = ["agent-os-openspec--v3.9.0", "agent-os-openspec--v3.28.0"]
        assert release_check.latest_tagged_version(tags, "agent-os-openspec") == "3.28.0"

    def test_ignores_other_plugins(self):
        tags = ["anderes-plugin--v9.9.9", "agent-os-openspec--v1.0.0"]
        assert release_check.latest_tagged_version(tags, "agent-os-openspec") == "1.0.0"

    def test_returns_none_without_matching_tags(self):
        assert release_check.latest_tagged_version(["archive/x"], "agent-os-openspec") is None


class TestContentOnlyMode:
    """Die inhaltlichen Pruefungen muessen im Pull Request laufen koennen."""

    def _run(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "release_check.py"), *extra],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )

    def test_content_only_skips_release_state_checks(self):
        """Branch/Arbeitsbaum/Abgleich sind im PR nie erfuellbar — sie duerfen
        dort nicht mitgeprueft werden, sonst ist der Check immer rot und wird
        genauso ignoriert wie der Release-Job."""
        out = self._run("--content-only", "--no-tests").stdout
        for label in ("Branch", "Arbeitsbaum", "Abgleich"):
            assert label not in out, f"'{label}' gehoert nicht in die Inhaltspruefung"

    def test_content_only_runs_the_content_checks(self):
        out = self._run("--content-only", "--no-tests").stdout
        for label in ("Version", "README", "Skills", "Release"):
            assert label in out, f"'{label}' fehlt in der Inhaltspruefung:\n{out}"

    def test_content_only_passes_on_a_healthy_repo(self):
        result = self._run("--content-only", "--no-tests")
        assert result.returncode == 0, (
            "Inhaltspruefung scheitert auf sauberem Stand:\n"
            + result.stdout + result.stderr
        )

    def test_full_mode_still_checks_release_state(self):
        """Der Release-Lauf selbst prueft weiterhin alles."""
        out = self._run("--no-tests").stdout
        for label in ("Branch", "Arbeitsbaum", "Abgleich", "Version", "README"):
            assert label in out


class TestCiWiring:
    """Eine Pruefung, die nirgends laeuft, schuetzt nichts — derselbe Fehler,
    den dieses Issue behebt."""

    def test_ci_workflow_runs_the_content_check(self):
        text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "--content-only" in text, (
            "ci.yml ruft die Inhaltspruefung nicht auf — sie bliebe wirkungslos"
        )

    def test_ci_workflow_fetches_tags(self):
        """Ohne Tags kann die Release-Pruefung nichts feststellen."""
        text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "fetch-depth: 0" in text

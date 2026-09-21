"""`migrate_to_plugin.py --apply` darf keine projekteigenen Befehle loeschen
(Issue #160).

`_find_removable_command_files` haelt jede `.claude/commands/<name>.md` fuer
eine „legacy duplicate", sobald ein Plugin-Skill gleichen Namens existiert.
Einzige Schutzvorrichtung ist der `openspec-alias:`-Marker, den nur
generierte Kurz-Aliase tragen. Der Docstring verspricht ausdruecklich
„never touch project-specific custom commands" — der Code haelt das nicht.

Gemessen am 2026-09-20 gegen /home/hem/gregor_zwanzig: das Werkzeug meldete
`.claude/commands/70-deploy.md` als entfernbar. Diese Datei ist die
vollstaendige Produktions-Deploy-Prozedur des Projekts (Staging-Poll,
e2e-verify, Prod-Deploy, Selftest, Issue-Close) und sagt in ihrer zweiten
Zeile selbst, dass sie das generische Plugin-Template ersetzt. Ein `--apply`
haette sie geloescht; `/70-deploy` waere danach auf Vercel/Heroku-Beispiele
zurueckgefallen, und aufgefallen waere es beim naechsten Deploy.

## Warum keine Aehnlichkeitsschwelle

Gemessen an echten Daten (Plugin 3.26.1):

    Alt-Kopien (/var/www/henemm, Framework 3.3.0)   0.221 ... 0.640
    Echte Anpassung (gregor 70-deploy)              0.028

Eine Schwelle dazwischen waere aus zwei Stichproben geraten. Fuer eine
LOESCHENDE Operation ist das die falsche Art von Sicherheit. Entfernt wird
deshalb nur noch, was nachweislich eine Kopie ist: inhaltsgleich zum
ausgelieferten Skill, nachdem Alias-Kommentar und Versions-Marker
normalisiert wurden. Alles andere bleibt stehen und wird berichtet — der
Mensch entscheidet.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import migrate_to_plugin  # noqa: E402

SKILL_BODY = """# Phase 8: Deploy to Production

## Purpose

Generic deployment template. Adapt per project.

## Steps

1. Build
2. Deploy
3. Verify
"""

CUSTOM_BODY = """# Phase 8: Auslieferung nach Produktion (Projekt X)

Ersetzt das generische `70-deploy`-Template des Plugins. Der Ablauf hier ist
der einzige gueltige.

## Schritt 1 — Staging-Poll

Warte auf gruenen Staging-Verdict, dann weiter.
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Projekt mit .claude/commands/ und ein Plugin mit skills/70-deploy/."""
    plugin = tmp_path / "plugin"
    (plugin / "skills" / "70-deploy").mkdir(parents=True)
    (plugin / "skills" / "70-deploy" / "SKILL.md").write_text(SKILL_BODY)
    (plugin / "skills" / "50-implement").mkdir(parents=True)
    (plugin / "skills" / "50-implement" / "SKILL.md").write_text("# Implement\n\nbody\n")
    monkeypatch.setattr(migrate_to_plugin, "PLUGIN_ROOT", plugin)

    proj = tmp_path / "project"
    (proj / ".claude" / "commands").mkdir(parents=True)
    return proj


def _cmd(project: Path, name: str, body: str) -> Path:
    f = project / ".claude" / "commands" / f"{name}.md"
    f.write_text(body)
    return f


def _removable_names(project: Path) -> set:
    return {f.stem for f in migrate_to_plugin._find_removable_command_files(project)}


class TestCustomCommandsSurvive:
    def test_custom_command_is_not_removable(self, project):
        """Der Fundfall: eine projekteigene Fassung ohne Alias-Marker darf
        nicht als Duplikat gelten."""
        _cmd(project, "70-deploy", CUSTOM_BODY)

        assert "70-deploy" not in _removable_names(project), (
            "Eine projekteigene Deploy-Prozedur darf nicht geloescht werden"
        )

    def test_stale_copy_is_not_removable_either(self, project):
        """Eine alte Framework-Kopie weicht inhaltlich ab. Ohne Beweis, dass
        es eine Kopie IST, wird nicht geloescht — berichtet statt zerstoert."""
        _cmd(project, "70-deploy", SKILL_BODY.replace("Generic deployment template.",
                                                      "Alte Fassung aus 3.3.0.") + "\nExtra.\n")

        assert "70-deploy" not in _removable_names(project)


class TestRealDuplicatesStillRemoved:
    def test_identical_copy_is_removable(self, project):
        """Der eigentliche Zweck des Werkzeugs bleibt erhalten: eine echte,
        inhaltsgleiche Doppelung verschwindet weiterhin."""
        _cmd(project, "70-deploy", SKILL_BODY)

        assert "70-deploy" in _removable_names(project)

    def test_copy_differing_only_in_version_marker_is_removable(self, project):
        """Der Versions-Marker (3.24.0) unterscheidet zwei ansonsten gleiche
        Fassungen. Er darf eine Kopie nicht vor dem Aufraeumen schuetzen."""
        _cmd(project, "70-deploy", SKILL_BODY + "\n⚙ /70-deploy · agent-os-openspec 3.20.0\n")

        assert "70-deploy" in _removable_names(project)

    def test_copy_with_trailing_whitespace_is_removable(self, project):
        _cmd(project, "70-deploy", SKILL_BODY + "\n\n   \n")

        assert "70-deploy" in _removable_names(project)


class TestExistingBehaviourPreserved:
    def test_alias_marker_still_protects(self, project):
        """Bestandsverhalten: generierte Kurz-Aliase bleiben unangetastet,
        auch wenn sie inhaltsgleich sind."""
        _cmd(project, "70-deploy",
             "<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->\n" + SKILL_BODY)

        assert "70-deploy" not in _removable_names(project)

    def test_command_without_matching_skill_is_untouched(self, project):
        """Projekt-eigene Befehle ohne gleichnamigen Skill waren nie betroffen
        und bleiben es."""
        _cmd(project, "radar", "# Radar\n\nprojekteigen\n")

        assert "radar" not in _removable_names(project)

    def test_unreadable_file_is_kept(self, project):
        """Fail-safe bleibt fail-safe."""
        f = project / ".claude" / "commands" / "70-deploy.md"
        f.write_bytes(b"\xff\xfe\x00broken")

        assert "70-deploy" not in _removable_names(project)


class TestDryRunReportsWhatItKeeps:
    def test_kept_files_are_named_in_the_output(self, project, capsys):
        """Stillschweigen ist das eigentliche Problem: wird eine Datei wegen
        Abweichung verschont, muss der Trockenlauf das sagen — sonst weiss
        niemand, dass dort eine Entscheidung ansteht."""
        (project / ".claude" / "settings.json").write_text("{}")
        _cmd(project, "70-deploy", CUSTOM_BODY)
        _cmd(project, "50-implement", "# Implement\n\nbody\n")

        migrate_to_plugin.migrate(project, dry_run=True)
        out = capsys.readouterr().out

        assert "70-deploy" in out, f"Die verschonte Datei muss genannt werden: {out!r}"
        assert "eigene" in out.lower() or "abweich" in out.lower(), (
            f"Die Ausgabe muss den Grund nennen, nicht nur den Namen: {out!r}"
        )

    def test_removable_and_kept_are_not_mixed_up(self, project, capsys):
        """Die entfernbare und die verschonte Datei duerfen nicht in derselben
        Liste landen — sonst loescht man beim Lesen die falsche."""
        (project / ".claude" / "settings.json").write_text("{}")
        _cmd(project, "70-deploy", CUSTOM_BODY)
        _cmd(project, "50-implement", "# Implement\n\nbody\n")

        migrate_to_plugin.migrate(project, dry_run=True)
        out = capsys.readouterr().out

        removal_block = out.split("duplicate a plugin skill")[1].split("\n\n")[0] \
            if "duplicate a plugin skill" in out else ""
        assert "70-deploy" not in removal_block, (
            f"Die eigene Fassung steht faelschlich in der Loesch-Liste: {removal_block!r}"
        )
        assert "50-implement" in removal_block, (
            f"Die echte Doppelung muss in der Loesch-Liste stehen: {removal_block!r}"
        )

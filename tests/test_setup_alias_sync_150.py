"""Alias-Inhalt hat genau eine Quelle (Issue #150).

Nach 3.23.0 liegt die Logik fuer den Inhalt einer Alias-Datei in
`core/hooks/alias_sync.py` (`ALIAS_MARKER`, `alias_content`,
`embeds_full_skill`, `skill_names`). Das SessionStart-Banner nutzt sie, um
veraltete Kopien zu erkennen.

`setup.py::generate_command_aliases` trug dieselbe Logik ein zweites Mal —
eigener `ALIAS_MARKER`, eigene Fallunterscheidung ueber
`disable-model-invocation`. Heute identisch; driftet eine Seite, meldet der
Banner falsch, und zwar in die unangenehme Richtung: er haelt aktuelle Aliase
fuer veraltet oder umgekehrt.

Zweiter Punkt desselben Issues: `core/commands/30-write-spec.md` enthaelt den
Platzhalter `{{OPENSPEC_VERSION}}`. `scripts/sync_skills.py` ersetzt ihn beim
Erzeugen von `skills/`, der Kopiermodus in `setup.py` kopierte die Befehle
aber unveraendert — im Zielprojekt landete die rohe Platzhalter-Zeile.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import setup as setup_py  # noqa: E402
import alias_sync  # noqa: E402

SKILLS_DIR = REPO_ROOT / "skills"


class TestSingleSourceOfTruth:
    def test_setup_uses_the_shared_marker(self):
        assert setup_py.ALIAS_MARKER == alias_sync.ALIAS_MARKER

    def test_setup_keeps_no_own_alias_body_logic(self):
        """Die Fallunterscheidung lebt in `alias_sync`, nicht in `setup.py`.

        Solange `setup.py` das Frontmatter selbst auswertet, gibt es zwei
        Stellen, die auseinanderlaufen koennen — genau der Befund.
        """
        source = (REPO_ROOT / "setup.py").read_text()
        assert "disable-model-invocation: true" not in source, (
            "setup.py entscheidet noch selbst ueber die Alias-Form — "
            "alias_sync.embeds_full_skill() ist die einzige Quelle"
        )

    def test_generated_aliases_match_alias_sync_exactly(self, tmp_path, capsys):
        setup_py.generate_command_aliases(tmp_path)
        capsys.readouterr()

        names = alias_sync.skill_names(SKILLS_DIR)
        assert names, "ohne Skills belegt dieser Test nichts"

        for name in names:
            produced = (tmp_path / ".claude" / "commands" / f"{name}.md").read_text()
            expected = alias_sync.alias_content(
                name, (SKILLS_DIR / name / "SKILL.md").read_text()
            )
            assert produced == expected, f"Alias {name}.md weicht von alias_sync ab"

    def test_generated_aliases_are_recognised_as_alias_files(self, tmp_path, capsys):
        """Was setup.py schreibt, muss der Banner auch als eigenes Werk erkennen."""
        setup_py.generate_command_aliases(tmp_path)
        capsys.readouterr()

        for name in alias_sync.skill_names(SKILLS_DIR):
            text = (tmp_path / ".claude" / "commands" / f"{name}.md").read_text()
            assert alias_sync.is_alias_file(text)


class TestOverwriteRulesUnchanged:
    def test_custom_command_is_not_overwritten(self, tmp_path, capsys):
        commands = tmp_path / ".claude" / "commands"
        commands.mkdir(parents=True)
        custom = commands / "70-deploy.md"
        custom.write_text("# eigener Befehl des Projekts\n")

        setup_py.generate_command_aliases(tmp_path)
        capsys.readouterr()

        assert custom.read_text() == "# eigener Befehl des Projekts\n"

    def test_own_alias_is_overwritten(self, tmp_path, capsys):
        commands = tmp_path / ".claude" / "commands"
        commands.mkdir(parents=True)
        stale = commands / "80-workflow.md"
        stale.write_text(f"{alias_sync.ALIAS_MARKER}\nveralteter Inhalt\n")

        setup_py.generate_command_aliases(tmp_path)
        capsys.readouterr()

        assert "veralteter Inhalt" not in stale.read_text()


class TestCopyModeVersionPlaceholder:
    def test_placeholder_is_replaced_in_copied_commands(self, tmp_path, capsys):
        setup_py.create_directory_structure(tmp_path)
        setup_py.copy_core_components(tmp_path)
        capsys.readouterr()

        text = (tmp_path / ".claude" / "commands" / "30-write-spec.md").read_text()
        assert alias_sync.ALIAS_MARKER not in text  # Befehl, kein Alias
        assert "{{OPENSPEC_VERSION}}" not in text, "roher Platzhalter im Zielprojekt"
        assert setup_py.FRAMEWORK_VERSION in text

    def test_source_file_keeps_the_placeholder(self):
        """Ersetzt wird beim Kopieren, nicht in der Quelle."""
        source = (REPO_ROOT / "core" / "commands" / "30-write-spec.md").read_text()
        assert "{{OPENSPEC_VERSION}}" in source

    def test_other_commands_are_copied_unchanged(self, tmp_path, capsys):
        setup_py.create_directory_structure(tmp_path)
        setup_py.copy_core_components(tmp_path)
        capsys.readouterr()

        for name in ("50-implement.md", "99-reset.md"):
            src = (REPO_ROOT / "core" / "commands" / name).read_text()
            dst = (tmp_path / ".claude" / "commands" / name).read_text()
            assert dst == src, f"{name} darf beim Kopieren nicht veraendert werden"

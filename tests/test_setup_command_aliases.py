"""Tests für setup.generate_command_aliases (short-command-aliases Spec).

Direktimport-Pattern wie in tests/test_migrate_command_cleanup.py:
sys.path.insert auf REPO_ROOT, dann `import setup`.
tmp_path-Fixtures für isolierte project_path-Verzeichnisse.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import setup

MARKER = "<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->"


def _skill_names():
    """Kanonische Liste der Skill-Namen (Verzeichnisse mit SKILL.md)."""
    skills_dir = setup.FRAMEWORK_ROOT / "skills"
    return sorted(
        p.name
        for p in skills_dir.iterdir()
        if p.is_dir() and (p / "SKILL.md").exists()
    )


def _is_model_invocable(name: str) -> bool:
    skill_text = (setup.FRAMEWORK_ROOT / "skills" / name / "SKILL.md").read_text()
    return "disable-model-invocation: true" not in skill_text


def test_generates_alias_file_per_skill_with_marker_and_redirect(tmp_path):
    """AC-1: Für jeden Skill entsteht eine Alias-Datei mit Marker.

    Skills mit disable-model-invocation:false bekommen einen Text-Redirect
    (das Modell darf ihn per Skill-Tool aufloesen). Skills mit
    disable-model-invocation:true bekommen den vollen SKILL.md-Inhalt
    eingebettet, weil ein Text-Redirect am Skill-Tool-Gate scheitern wuerde
    (siehe generate_command_aliases-Docstring).
    """
    setup.generate_command_aliases(tmp_path)

    commands_dir = tmp_path / ".claude" / "commands"
    names = _skill_names()
    assert names, "Erwartet mindestens einen Skill unter FRAMEWORK_ROOT/skills/"

    for name in names:
        alias = commands_dir / f"{name}.md"
        assert alias.exists(), f"Alias-Datei fehlt: {name}.md"
        content = alias.read_text()
        # Erste Zeile ist exakt der Marker
        assert content.splitlines()[0] == MARKER, (
            f"Erste Zeile von {name}.md ist nicht der Marker"
        )
        if _is_model_invocable(name):
            # Redirect-Zeile vorhanden
            assert f"/agent-os-openspec:{name} $ARGUMENTS" in content
            # YAML-Frontmatter description
            assert f"description: Kurz-Alias für /agent-os-openspec:{name}" in content
        else:
            # Voller SKILL.md-Inhalt eingebettet, kein Redirect (kein Skill-Tool-Aufruf noetig)
            skill_text = (setup.FRAMEWORK_ROOT / "skills" / name / "SKILL.md").read_text()
            assert content == f"{MARKER}\n{skill_text}"
            assert f"/agent-os-openspec:{name} $ARGUMENTS" not in content


def test_updates_existing_marker_file(tmp_path):
    """AC-3: Vorhandene Marker-Datei mit veraltetem Inhalt wird überschrieben."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    stale = commands_dir / "10-context.md"
    stale.write_text(MARKER + "\nveralteter inhalt der ueberschrieben werden muss\n")

    setup.generate_command_aliases(tmp_path)

    content = stale.read_text()
    assert content.splitlines()[0] == MARKER
    assert "/agent-os-openspec:10-context $ARGUMENTS" in content
    assert "veralteter inhalt" not in content


def test_updates_existing_marker_file_for_disabled_model_invocation_skill(tmp_path):
    """AC-3b: Gilt auch fuer Skills mit disable-model-invocation:true (voller Embed)."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    stale = commands_dir / "50-implement.md"
    stale.write_text(MARKER + "\nveralteter inhalt der ueberschrieben werden muss\n")

    setup.generate_command_aliases(tmp_path)

    content = stale.read_text()
    assert content.splitlines()[0] == MARKER
    assert "veralteter inhalt" not in content
    skill_text = (setup.FRAMEWORK_ROOT / "skills" / "50-implement" / "SKILL.md").read_text()
    assert content == f"{MARKER}\n{skill_text}"


def test_skips_custom_command_without_marker(tmp_path):
    """AC-4: Datei ohne Marker (Custom-Command) bleibt unverändert."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    custom = commands_dir / "50-implement.md"
    original = "custom user command"
    custom.write_text(original)

    setup.generate_command_aliases(tmp_path)

    assert custom.read_text() == original


def test_creates_commands_dir_when_missing(tmp_path):
    """AC-2: .claude/commands/ wird automatisch angelegt."""
    commands_dir = tmp_path / ".claude" / "commands"
    assert not commands_dir.exists()

    setup.generate_command_aliases(tmp_path)

    assert commands_dir.is_dir()
    names = _skill_names()
    for name in names:
        assert (commands_dir / f"{name}.md").exists()

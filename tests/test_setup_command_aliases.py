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


# --- refresh_command_aliases (#205: sicherer Update-only-Modus) -------------

def test_refresh_updates_existing_stale_marker_file(tmp_path):
    """AC-1: Vorhandene, veraltete markierte Kopie wird auf den Soll-Inhalt gebracht."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    stale = commands_dir / "10-context.md"
    stale.write_text(MARKER + "\nveralteter inhalt der ueberschrieben werden muss\n")

    setup.refresh_command_aliases(tmp_path)

    content = stale.read_text()
    assert content.splitlines()[0] == MARKER
    assert "/agent-os-openspec:10-context $ARGUMENTS" in content
    assert "veralteter inhalt" not in content


def test_refresh_never_creates_missing_files(tmp_path):
    """AC-2: Fuer Skills ohne vorhandene Datei im Scope wird nichts angelegt —
    das ist der ganze Sinn des Modus (kann nichts ueberschatten, #87/#205)."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "10-context.md").write_text(MARKER + "\nveraltet\n")

    setup.refresh_command_aliases(tmp_path)

    for name in _skill_names():
        if name == "10-context":
            continue
        assert not (commands_dir / f"{name}.md").exists()


def test_refresh_leaves_unmarked_custom_command_untouched(tmp_path):
    """AC-3: Datei ohne Marker (Custom-Command) bleibt unveraendert."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    custom = commands_dir / "50-implement.md"
    original = "custom user command"
    custom.write_text(original)

    setup.refresh_command_aliases(tmp_path)

    assert custom.read_text() == original


def test_refresh_leaves_newer_marked_copy_untouched(tmp_path):
    """AC-3: Eine Kopie mit beweisbar neuerem Versions-Marker als die
    geladene FRAMEWORK_VERSION wird nicht herabgestuft."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    target = commands_dir / "10-context.md"
    newer_version = ".".join(
        str(int(p) + 1) if i == 0 else p
        for i, p in enumerate(setup.FRAMEWORK_VERSION.split("."))
    )
    content = (
        f"{MARKER}\nirgendein inhalt\n\n"
        f"⚙ /10-context · agent-os-openspec {newer_version}\n"
    )
    target.write_text(content)

    setup.refresh_command_aliases(tmp_path)

    assert target.read_text() == content


def test_refresh_is_idempotent_on_already_current_copy(tmp_path):
    """Ein bereits aktueller Alias bleibt unangetastet — kein unnoetiger Schreibvorgang."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    setup.generate_command_aliases(tmp_path)
    before = {p.name: p.read_text() for p in commands_dir.glob("*.md")}

    setup.refresh_command_aliases(tmp_path)

    after = {p.name: p.read_text() for p in commands_dir.glob("*.md")}
    assert after == before

    assert commands_dir.is_dir()
    names = _skill_names()
    for name in names:
        assert (commands_dir / f"{name}.md").exists()

"""Tests für _find_removable_command_files in migrate_to_plugin.py (Issue #24)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import migrate_to_plugin as mig

MARKER = "<!-- openspec-alias: do-not-treat-as-legacy-duplicate -->"


def test_removes_only_files_matching_a_plugin_skill(tmp_path):
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)

    # Duplicates a real plugin skill (see skills/00-intake, skills/90-retro)
    (commands_dir / "00-intake.md").write_text("legacy")
    (commands_dir / "90-retro.md").write_text("legacy")

    # Project-specific, no matching skill — must survive
    (commands_dir / "e2e-verify.md").write_text("custom")
    (commands_dir / "README.md").write_text("custom")

    removable = mig._find_removable_command_files(tmp_path)
    removable_names = {f.name for f in removable}

    assert removable_names == {"00-intake.md", "90-retro.md"}


def test_no_commands_dir_returns_empty(tmp_path):
    assert mig._find_removable_command_files(tmp_path) == []


def test_marker_alias_file_is_not_removable(tmp_path):
    """AC-8: Datei mit Marker in der ersten Zeile ist kein Legacy-Duplikat."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)

    # Matching skill name, but content carries the framework marker → keep it.
    (commands_dir / "00-intake.md").write_text(
        MARKER + "\n---\ndescription: Kurz-Alias\n---\n\n/agent-os-openspec:00-intake $ARGUMENTS\n"
    )

    removable = mig._find_removable_command_files(tmp_path)
    removable_names = {f.name for f in removable}

    assert "00-intake.md" not in removable_names


def test_legacy_file_without_marker_still_removable(tmp_path):
    """AC-9: Datei ohne Marker mit Skill-Namen bleibt entfernbar (Alt-Verhalten)."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)

    # Legacy full-text copy, no marker → still a removable duplicate.
    (commands_dir / "90-retro.md").write_text("legacy full-text command copy")

    removable = mig._find_removable_command_files(tmp_path)
    removable_names = {f.name for f in removable}

    assert "90-retro.md" in removable_names

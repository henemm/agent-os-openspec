"""Tests fuer #165 — Hook-Pfade an ${CLAUDE_PROJECT_DIR} verankern.

Gemeldet aus Meditationstimer: jede Nutzer-Nachricht brach ab mit

    can't open file '.../Meditationstimer iOS/Media/.claude/hooks/phase_listener.py'

Die Hook-Datei existierte — unter dem Projekt-Root. Der Eintrag in
settings.json war cwd-relativ (`python3 .claude/hooks/phase_listener.py`), und
Hook-Kommandos laufen im AKTUELLEN Arbeitsverzeichnis der Sitzung, nicht im
Projekt-Root (https://code.claude.com/docs/en/hooks). Stand die Sitzung in
einem Unterordner, zeigte der Pfad ins Leere.

Ein Test je "Expected Behavior"-Zeile aus docs/specs/hook-paths-project-dir.md.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import setup as setup_mod  # noqa: E402
from migrate_to_plugin import _anchor_command, _patch_settings, migrate  # noqa: E402

PLACEHOLDER = "${CLAUDE_PROJECT_DIR}"


# --- Helpers ---------------------------------------------------------------

def _make_project(tmp_path: Path, name: str = "My Project") -> Path:
    """Fake-Projekt — Name mit Leerzeichen, wie 'Meditationstimer iOS'."""
    proj = tmp_path / name
    (proj / ".claude" / "hooks").mkdir(parents=True)
    return proj


def _install_hook_files(proj: Path, *names: str) -> None:
    for n in names:
        (proj / ".claude" / "hooks" / n).write_text("# hook\n")


def _hook_commands(settings: dict) -> list[str]:
    out = []
    for entries in settings.get("hooks", {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                out.append(hook["command"])
    return out


def _settings_with(*commands: str, event: str = "PreToolUse") -> dict:
    return {
        "hooks": {
            event: [{"matcher": "Bash", "hooks": [{"command": c} for c in commands]}]
        }
    }


# --- setup.py: Erzeugung ---------------------------------------------------

def test_generated_commands_use_project_dir_placeholder(tmp_path):
    """Kein erzeugtes Hook-Kommando ist cwd-relativ."""
    proj = _make_project(tmp_path)
    _install_hook_files(proj, "edit_gate.py", "bash_gate.py", "post_bash.py",
                        "phase_listener.py")

    setup_mod.generate_settings_json(proj, modules=[])

    settings = json.loads((proj / ".claude" / "settings.json").read_text())
    commands = _hook_commands(settings)
    assert commands, "Es wurde kein Hook-Kommando erzeugt"
    for cmd in commands:
        assert PLACEHOLDER in cmd, f"Kommando ohne Verankerung: {cmd}"
        assert "python3 .claude/hooks/" not in cmd, f"cwd-relativ: {cmd}"


def test_generated_commands_bake_in_no_absolute_project_path(tmp_path):
    """Der Projektpfad wird nicht eingebacken — sonst bricht Verschieben."""
    proj = _make_project(tmp_path)
    _install_hook_files(proj, "edit_gate.py")

    setup_mod.generate_settings_json(proj, modules=[])

    settings = json.loads((proj / ".claude" / "settings.json").read_text())
    for cmd in _hook_commands(settings):
        assert str(proj) not in cmd, f"Absoluter Projektpfad eingebacken: {cmd}"


def test_generated_commands_quote_the_placeholder(tmp_path):
    """Ordner mit Leerzeichen: der Platzhalter steht in Anfuehrungszeichen."""
    proj = _make_project(tmp_path, name="Meditationstimer iOS")
    _install_hook_files(proj, "phase_listener.py")

    setup_mod.generate_settings_json(proj, modules=[])

    settings = json.loads((proj / ".claude" / "settings.json").read_text())
    for cmd in _hook_commands(settings):
        assert f'"{PLACEHOLDER}/' in cmd, f"Platzhalter nicht gequotet: {cmd}"


# --- migrate_to_plugin.py: Reparatur --------------------------------------

def test_project_own_hook_command_is_anchored():
    """Projekteigener Hook (kein Plugin-Hook) wird verankert statt entfernt."""
    settings = _settings_with("python3 .claude/hooks/session_start.py",
                              event="SessionStart")

    changes = _patch_settings(settings, dry_run=False)

    assert len(changes) == 1
    assert _hook_commands(settings) == [
        f'python3 "{PLACEHOLDER}/.claude/hooks/session_start.py"'
    ]


def test_extra_arguments_survive_the_rewrite():
    """`qa_gate.py --hook-mode` behaelt sein Argument."""
    anchored = _anchor_command("python3 .claude/hooks/qa_gate.py --hook-mode")
    assert anchored == f'python3 "{PLACEHOLDER}/.claude/hooks/qa_gate.py" --hook-mode'


def test_env_prefix_survives_the_rewrite():
    """Vorangestellte Env-Zuweisungen bleiben erhalten."""
    anchored = _anchor_command(
        "WORKFLOW_CALLER=phase_listener python3 .claude/hooks/workflow.py status"
    )
    assert anchored == (
        f'WORKFLOW_CALLER=phase_listener python3 '
        f'"{PLACEHOLDER}/.claude/hooks/workflow.py" status'
    )


def test_absolute_path_is_anchored_too():
    """Eingebackener absoluter Pfad (auch mit Leerzeichen) wird verankert."""
    anchored = _anchor_command(
        'python3 "/Users/hem/Developer/My Project/.claude/hooks/session_start.py"'
    )
    assert anchored == f'python3 "{PLACEHOLDER}/.claude/hooks/session_start.py"'


def test_rewrite_is_idempotent():
    """Zweiter Lauf aendert nichts mehr."""
    once = _anchor_command("python3 .claude/hooks/session_start.py")
    assert _anchor_command(once) == once

    settings = _settings_with(once, event="SessionStart")
    assert _patch_settings(settings, dry_run=False) == []


def test_plugin_hooks_are_still_removed_not_anchored():
    """Bestehendes Verhalten: Plugin-Hooks verschwinden, sie werden nicht verankert."""
    settings = _settings_with("python3 .claude/hooks/edit_gate.py",
                              "python3 .claude/hooks/session_start.py")

    _patch_settings(settings, dry_run=False)

    assert _hook_commands(settings) == [
        f'python3 "{PLACEHOLDER}/.claude/hooks/session_start.py"'
    ]


def test_dry_run_changes_nothing():
    """Trockenlauf meldet, aber schreibt nicht."""
    settings = _settings_with("python3 .claude/hooks/session_start.py",
                              event="SessionStart")

    changes = _patch_settings(settings, dry_run=True)

    assert len(changes) == 1
    assert _hook_commands(settings) == ["python3 .claude/hooks/session_start.py"]


# --- settings.local.json ---------------------------------------------------

def test_local_settings_hooks_are_migrated(tmp_path, capsys):
    """settings.local.json wird mitgenommen, permissions bleibt unangetastet."""
    proj = _make_project(tmp_path)
    (proj / ".claude" / "settings.json").write_text(json.dumps(
        _settings_with("python3 .claude/hooks/session_start.py", event="SessionStart")
    ))
    local = proj / ".claude" / "settings.local.json"
    local.write_text(json.dumps({
        "permissions": {"allow": ["Bash(python3 .claude/hooks/workflow.py status)"]},
        "hooks": {"SessionStart": [{"hooks": [
            {"command": "python3 .claude/hooks/project_banner.py"}
        ]}]},
    }))

    migrate(proj, dry_run=False)

    result = json.loads(local.read_text())
    assert _hook_commands(result) == [
        f'python3 "{PLACEHOLDER}/.claude/hooks/project_banner.py"'
    ]
    # permissions ist kein Hook-Kommando und wird nicht umgeschrieben
    assert result["permissions"]["allow"] == [
        "Bash(python3 .claude/hooks/workflow.py status)"
    ]


def test_local_settings_without_hooks_is_untouched(tmp_path):
    """Keine Hooks in settings.local.json → Datei bleibt byte-gleich."""
    proj = _make_project(tmp_path)
    (proj / ".claude" / "settings.json").write_text(json.dumps(
        _settings_with("python3 .claude/hooks/session_start.py", event="SessionStart")
    ))
    local = proj / ".claude" / "settings.local.json"
    original = json.dumps({"permissions": {"allow": ["Bash"]}}, indent=2)
    local.write_text(original)

    migrate(proj, dry_run=False)

    assert local.read_text() == original


def test_broken_local_settings_does_not_abort_migration(tmp_path, capsys):
    """Unlesbares JSON: Warnung, settings.json wird trotzdem migriert."""
    proj = _make_project(tmp_path)
    settings_path = proj / ".claude" / "settings.json"
    settings_path.write_text(json.dumps(
        _settings_with("python3 .claude/hooks/session_start.py", event="SessionStart")
    ))
    (proj / ".claude" / "settings.local.json").write_text("{ kaputt")

    migrate(proj, dry_run=False)

    assert "WARNUNG" in capsys.readouterr().out
    result = json.loads(settings_path.read_text())
    assert _hook_commands(result) == [
        f'python3 "{PLACEHOLDER}/.claude/hooks/session_start.py"'
    ]


# --- Der gemeldete Fall ----------------------------------------------------

def test_reported_meditationstimer_case_is_repaired(tmp_path):
    """Der gemeldete Fall: 4 Plugin-Hooks weg, session_start.py verankert."""
    proj = _make_project(tmp_path, name="Meditationstimer")
    _install_hook_files(proj, "edit_gate.py", "bash_gate.py", "post_bash.py",
                        "phase_listener.py", "session_start.py")
    settings_path = proj / ".claude" / "settings.json"
    settings_path.write_text(json.dumps({"hooks": {
        "PreToolUse": [
            {"matcher": "Edit|Write", "hooks": [{"command": "python3 .claude/hooks/edit_gate.py"}]},
            {"matcher": "Bash", "hooks": [{"command": "python3 .claude/hooks/bash_gate.py"}]},
        ],
        "PostToolUse": [{"matcher": "Bash", "hooks": [{"command": "python3 .claude/hooks/post_bash.py"}]}],
        "UserPromptSubmit": [{"hooks": [{"command": "python3 .claude/hooks/phase_listener.py"}]}],
        "SessionStart": [{"hooks": [{"command": "python3 .claude/hooks/session_start.py"}]}],
    }}))

    migrate(proj, dry_run=False)

    remaining = _hook_commands(json.loads(settings_path.read_text()))
    assert remaining == [f'python3 "{PLACEHOLDER}/.claude/hooks/session_start.py"']
    # Kein einziges verbleibendes Kommando ist noch cwd-relativ
    assert not [c for c in remaining if "python3 .claude/hooks/" in c]

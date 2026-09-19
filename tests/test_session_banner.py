"""Tests fuer core/hooks/session_banner.py (SessionStart, 3.23.0).

Der Banner beweist dem User, welche Framework-Version wirklich geladen ist, und
warnt vor veralteten Befehls-Kopien, die `setup.py --command-aliases` erzeugt
hat. Alle Tests hermetisch: Fake-Plugin-Wurzel, Fake-HOME und Fake-Projekt im
tmp_path, Hook als Subprozess — so wie Claude Code ihn startet.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
BANNER = HOOKS_DIR / "session_banner.py"
sys.path.insert(0, str(HOOKS_DIR))
sys.path.insert(0, str(REPO_ROOT))

from alias_sync import ALIAS_MARKER, alias_content, find_stale_aliases  # noqa: E402

SKILL_INVOCABLE = (
    "---\ndescription: \"Write failing tests\"\ndisable-model-invocation: false\n---\n\n"
    "# TDD RED\n\nNeue Fassung.\n"
)
SKILL_BLOCKED = (
    "---\ndescription: \"Implement\"\ndisable-model-invocation: true\n---\n\n"
    "# Implement\n\nNeue Fassung.\n"
)


# --- Helpers ---------------------------------------------------------------

def _plugin(tmp_path: Path, version: str = "9.9.9") -> Path:
    root = tmp_path / "plugin"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "agent-os-openspec", "version": version})
    )
    for name, text in (("40-tdd-red", SKILL_INVOCABLE), ("50-implement", SKILL_BLOCKED)):
        (root / "skills" / name).mkdir(parents=True)
        (root / "skills" / name / "SKILL.md").write_text(text)
    return root


def _dirs(tmp_path: Path) -> "tuple[Path, Path]":
    home = tmp_path / "home"
    (home / ".claude" / "commands").mkdir(parents=True)
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / ".claude" / "commands").mkdir(parents=True)
    return home, project


def _run(plugin: Path, home: Path, project: Path, stdin: str = "", **extra_env):
    env = {k: v for k, v in os.environ.items()
           if k not in ("OPENSPEC_FRAMEWORK", "CLAUDE_PLUGIN_ROOT")}
    env.update({
        "HOME": str(home),
        "CLAUDE_PLUGIN_ROOT": str(plugin),
        "CLAUDE_PROJECT_DIR": str(project),
    })
    env.update(extra_env)
    return subprocess.run([sys.executable, str(BANNER)], input=stdin,
                          capture_output=True, text=True, env=env, cwd=str(project))


def _message(result) -> str:
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), f"keine Ausgabe, stderr={result.stderr!r}"
    return json.loads(result.stdout)["systemMessage"]


# --- Version ----------------------------------------------------------------

def test_banner_shows_plugin_version(tmp_path):
    plugin = _plugin(tmp_path, "9.9.9")
    home, project = _dirs(tmp_path)
    msg = _message(_run(plugin, home, project))
    assert msg == "agent-os-openspec 9.9.9 aktiv"


def test_banner_uses_real_plugin_json_without_env(tmp_path):
    """Ohne CLAUDE_PLUGIN_ROOT: Version aus plugin.json relativ zum Skript."""
    home, project = _dirs(tmp_path)
    expected = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
    result = _run(Path(""), home, project, CLAUDE_PLUGIN_ROOT="")
    assert _message(result).splitlines()[0] == f"agent-os-openspec {expected} aktiv"


# --- Stale-Alias-Erkennung ----------------------------------------------------

def test_full_copy_for_now_invocable_skill_is_stale(tmp_path):
    """Live-Fall: ~/.claude/commands/40-tdd-red.md ist eine Vollkopie mit
    disable-model-invocation: true, der Skill ist inzwischen false."""
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    old = SKILL_INVOCABLE.replace("false", "true").replace("Neue", "Alte")
    (home / ".claude" / "commands" / "40-tdd-red.md").write_text(f"{ALIAS_MARKER}\n{old}")
    msg = _message(_run(plugin, home, project))
    lines = msg.splitlines()
    assert lines[0] == "agent-os-openspec 9.9.9 aktiv"
    assert len(lines) == 2, msg
    assert "Veraltete Befehls-Kopien: 40-tdd-red" in lines[1]
    assert f"python3 {plugin / 'setup.py'} ~ --command-aliases" in lines[1]


def test_outdated_full_copy_in_project_is_stale(tmp_path):
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    old = SKILL_BLOCKED.replace("Neue", "Alte")
    (project / ".claude" / "commands" / "50-implement.md").write_text(f"{ALIAS_MARKER}\n{old}")
    msg = _message(_run(plugin, home, project))
    assert "Veraltete Befehls-Kopien: 50-implement" in msg
    assert f"setup.py {project} --command-aliases" in msg
    assert "setup.py ~" not in msg


def test_current_aliases_and_custom_commands_are_not_flagged(tmp_path):
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    cmds = home / ".claude" / "commands"
    (cmds / "40-tdd-red.md").write_text(alias_content("40-tdd-red", SKILL_INVOCABLE))
    (cmds / "50-implement.md").write_text(alias_content("50-implement", SKILL_BLOCKED))
    # Projekteigener Befehl ohne Marker: tabu, auch wenn er anders aussieht.
    (project / ".claude" / "commands" / "50-implement.md").write_text("# Eigene Fassung\n")
    msg = _message(_run(plugin, home, project))
    assert msg == "agent-os-openspec 9.9.9 aktiv"


def test_setup_generated_aliases_match_banner_expectation(tmp_path):
    """Keine duplizierte Logik: was setup.py schreibt, haelt der Banner fuer aktuell."""
    import setup

    project = tmp_path / "project"
    setup.generate_command_aliases(project)
    stale = find_stale_aliases(REPO_ROOT / "skills", project / ".claude" / "commands")
    assert stale == []
    for path in (project / ".claude" / "commands").glob("*.md"):
        skill = (REPO_ROOT / "skills" / path.stem / "SKILL.md").read_text()
        assert path.read_text() == alias_content(path.stem, skill)


# --- Framework abgeschaltet --------------------------------------------------

def test_framework_off_env_prints_nothing(tmp_path):
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    result = _run(plugin, home, project, OPENSPEC_FRAMEWORK="off")
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_framework_disabled_in_config_prints_nothing(tmp_path):
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    (project / "openspec.yaml").write_text("framework:\n  enabled: false\n")
    result = _run(plugin, home, project)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# --- Robustheit ----------------------------------------------------------------

def test_broken_plugin_json_exits_silently(tmp_path):
    plugin = _plugin(tmp_path)
    (plugin / ".claude-plugin" / "plugin.json").write_text("{kaputt")
    home, project = _dirs(tmp_path)
    result = _run(plugin, home, project)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_missing_plugin_root_exits_silently(tmp_path):
    home, project = _dirs(tmp_path)
    result = _run(tmp_path / "gibtsnicht", home, project)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_garbage_stdin_and_unreadable_alias_do_not_break(tmp_path):
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    # Verzeichnis statt Datei: read_text() wirft — der Banner muss trotzdem laufen.
    (home / ".claude" / "commands" / "40-tdd-red.md").mkdir()
    result = _run(plugin, home, project, stdin="kein json {")
    assert _message(result).startswith("agent-os-openspec 9.9.9 aktiv")


def test_registered_in_hooks_json():
    hooks = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text())
    commands = [h["command"] for entry in hooks["hooks"]["SessionStart"] for h in entry["hooks"]]
    assert "${CLAUDE_PLUGIN_ROOT}/core/hooks/session_banner.py" in commands
    assert os.access(BANNER, os.X_OK), "Hook wird direkt ausgefuehrt — braucht +x"

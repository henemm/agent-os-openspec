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

from alias_sync import (  # noqa: E402
    ALIAS_MARKER,
    alias_content,
    alias_version,
    find_stale_aliases,
    is_newer_than,
)

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


def _installed(tmp_path: Path, home: Path, version: str = "3.26.2",
               with_setup: bool = True) -> Path:
    """Fake-Installation samt `installed_plugins.json` im Fake-HOME."""
    root = tmp_path / "installed" / version
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "agent-os-openspec", "version": version})
    )
    if with_setup:
        (root / "setup.py").write_text("# fake setup\n")
    registry = home / ".claude" / "plugins"
    registry.mkdir(parents=True, exist_ok=True)
    (registry / "installed_plugins.json").write_text(json.dumps({
        "version": 2,
        "plugins": {
            "agent-os-openspec@henemm-private": [
                {"scope": "user", "installPath": str(root), "version": version}
            ]
        },
    }))
    return root


def _marked(name: str, skill_text: str, version: str) -> str:
    """Alias-Kopie mit Versions-Marker, wie `sync_skills.py` ihn anhaengt."""
    return (
        f"{alias_content(name, skill_text).rstrip()}\n\n"
        f"⚙ /{name} · agent-os-openspec {version}\n"
        "Die ⚙-Zeile uebernimmst du woertlich.\n"
    )


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


def _context(result) -> str:
    """`hookSpecificOutput.additionalContext` (#399) oder "" wenn nicht vorhanden."""
    if not result.stdout.strip():
        return ""
    data = json.loads(result.stdout)
    return (data.get("hookSpecificOutput") or {}).get("additionalContext") or ""


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


# --- Stale-Alias-Erkennung (#399: Wartung statt Befehl) ---------------------

def test_outdated_full_copy_in_project_is_stale(tmp_path):
    """#399 AC-4: Der Projekt-Hinweis steht nur noch im Claude-Kontext und
    zeigt auf die installierte Fassung, nicht auf die eingefrorene Plugin-Wurzel."""
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    installed = _installed(tmp_path, home)
    old = SKILL_BLOCKED.replace("Neue", "Alte")
    (project / ".claude" / "commands" / "50-implement.md").write_text(f"{ALIAS_MARKER}\n{old}")
    result = _run(plugin, home, project)
    msg = _message(result)
    ctx = _context(result)
    assert "Veraltete Befehls-Kopien" not in msg
    assert "python3" not in msg
    assert "50-implement" in ctx
    assert str(installed / "setup.py") in ctx
    assert "--refresh-aliases" in ctx
    assert "--command-aliases" not in ctx
    assert str(plugin / "setup.py") not in ctx


def test_copy_with_newer_marker_is_not_reported(tmp_path):
    """AC-1 (#163): Eine Kopie, die beweisbar neuer ist als die geladene Version,
    wuerde durch den Reparatur-Befehl herabgestuft — also kein Wort darueber."""
    plugin = _plugin(tmp_path, "3.24.0")
    home, project = _dirs(tmp_path)
    _installed(tmp_path, home)
    (project / ".claude" / "commands" / "50-implement.md").write_text(
        _marked("50-implement", SKILL_BLOCKED, "3.25.0")
    )
    result = _run(plugin, home, project)
    assert _message(result) == "agent-os-openspec 3.24.0 aktiv"
    assert "50-implement" not in _context(result)


def test_copy_with_older_marker_points_to_installed_version(tmp_path):
    """AC-2/AC-5: 3.9.0 ist aelter als 3.25.0 — numerisch, nicht als String.
    #399: Hinweis nur im Claude-Kontext."""
    plugin = _plugin(tmp_path, "3.25.0")
    home, project = _dirs(tmp_path)
    installed = _installed(tmp_path, home, "3.26.2")
    (project / ".claude" / "commands" / "50-implement.md").write_text(
        _marked("50-implement", SKILL_BLOCKED, "3.9.0")
    )
    result = _run(plugin, home, project)
    msg = _message(result)
    ctx = _context(result)
    assert "Veraltete Befehls-Kopien" not in msg
    assert "python3" not in msg
    assert "50-implement" in ctx
    assert str(installed / "setup.py") in ctx
    assert str(plugin / "setup.py") not in ctx


def test_unresolvable_installation_yields_no_setup_py_path(tmp_path):
    """AC-4 (#205): Ohne `installed_plugins.json` lieber kein Pfad als ein falscher."""
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    old = SKILL_BLOCKED.replace("Neue", "Alte")
    (project / ".claude" / "commands" / "50-implement.md").write_text(f"{ALIAS_MARKER}\n{old}")
    result = _run(plugin, home, project)
    msg = _message(result)
    ctx = _context(result)
    assert "Veraltete Befehls-Kopien" not in msg
    assert "python3" not in msg
    assert "50-implement" in ctx
    assert "/setup.py" not in ctx


def test_installation_without_setup_py_yields_no_path(tmp_path):
    """AC-4 (#205): Eintrag vorhanden, Installation aber unbrauchbar — kein Pfad."""
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    _installed(tmp_path, home, with_setup=False)
    old = SKILL_BLOCKED.replace("Neue", "Alte")
    (project / ".claude" / "commands" / "50-implement.md").write_text(f"{ALIAS_MARKER}\n{old}")
    result = _run(plugin, home, project)
    msg = _message(result)
    ctx = _context(result)
    assert "Veraltete Befehls-Kopien" not in msg
    assert "python3" not in msg
    assert "50-implement" in ctx
    assert "/setup.py" not in ctx


# --- Wartung beim Start (#399) -------------------------------------------------

def test_start_frischt_veraltete_kopie_in_home_auf(tmp_path):
    """AC-1 (#399):
    GIVEN eine veraltete markierte Kopie ~/.claude/commands/40-tdd-red.md
    WHEN der Banner beim Start laeuft
    THEN entspricht sie der geladenen Fassung, die sichtbare Ausgabe meldet
    "Kurzbefehle aktualisiert" und enthaelt keinen Befehl (kein python3/setup.py).
    """
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    _installed(tmp_path, home)
    target = home / ".claude" / "commands" / "40-tdd-red.md"
    old = SKILL_INVOCABLE.replace("false", "true").replace("Neue", "Alte")
    target.write_text(f"{ALIAS_MARKER}\n{old}")
    msg = _message(_run(plugin, home, project))
    assert target.read_text() == alias_content("40-tdd-red", SKILL_INVOCABLE)
    assert find_stale_aliases(plugin / "skills", home / ".claude" / "commands") == []
    assert msg.splitlines()[0] == "agent-os-openspec 9.9.9 aktiv"
    assert "Kurzbefehle aktualisiert" in msg
    assert "python3" not in msg
    assert "setup.py" not in msg


def test_start_stuft_kopie_mit_neuerem_marker_nicht_herab(tmp_path):
    """AC-2 (#399, #163):
    GIVEN eine Kopie in ~ mit neuerem Versions-Marker (3.25.0) als die geladene
          Fassung (3.24.0) und abweichendem Inhalt
    WHEN der Banner laeuft
    THEN bleibt die Datei byte-identisch und es erscheint keine Aktualisierungszeile.
    """
    plugin = _plugin(tmp_path, "3.24.0")
    home, project = _dirs(tmp_path)
    target = home / ".claude" / "commands" / "40-tdd-red.md"
    newer = _marked("40-tdd-red", SKILL_INVOCABLE.replace("Neue", "Neuere"), "3.25.0")
    target.write_bytes(newer.encode())
    msg = _message(_run(plugin, home, project))
    assert target.read_bytes() == newer.encode()
    assert "Kurzbefehle aktualisiert" not in msg


def test_start_loescht_markierten_alias_entfernter_befehle_nicht_fremde_datei(tmp_path):
    """AC-3 (#399, #333, #353):
    GIVEN ein markierter Alias des entfernten Befehls 00-bug in ~/.claude/commands,
          eine unmarkierte Datei gleichen Namens in einem anderen Ordner unter ~
          und ein eigener unmarkierter Befehl
    WHEN der Banner laeuft
    THEN ist der markierte Alias geloescht, die unmarkierten Dateien bleiben unveraendert.
    """
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    cmds = home / ".claude" / "commands"
    marked = cmds / "00-bug.md"
    marked.write_text(f"{ALIAS_MARKER}\n# Bug\n\nAlte Fassung.\n")
    other_dir = cmds / "eigene"
    other_dir.mkdir()
    foreign = other_dir / "00-bug.md"
    foreign.write_bytes(b"# Mein eigener Bug-Befehl\n")
    own = cmds / "eigener.md"
    own.write_bytes(b"# Eigener Befehl\n")
    _message(_run(plugin, home, project))
    assert not marked.exists()
    assert foreign.read_bytes() == b"# Mein eigener Bug-Befehl\n"
    assert own.read_bytes() == b"# Eigener Befehl\n"


def test_projekt_kopie_wird_nicht_geschrieben_nur_claude_hinweis(tmp_path):
    """AC-4 (#399):
    GIVEN eine veraltete markierte Kopie in <projekt>/.claude/commands/50-implement.md
    WHEN der Banner laeuft
    THEN ist die Datei byte-identisch, der Hinweis steht nur in additionalContext.
    """
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    _installed(tmp_path, home)
    target = project / ".claude" / "commands" / "50-implement.md"
    old = f"{ALIAS_MARKER}\n{SKILL_BLOCKED.replace('Neue', 'Alte')}".encode()
    target.write_bytes(old)
    result = _run(plugin, home, project)
    msg = _message(result)
    assert target.read_bytes() == old
    assert "50-implement" in _context(result)
    assert "50-implement" not in msg
    assert "python3" not in msg


def test_source_compact_fuehrt_keine_wartung_aus(tmp_path):
    """AC-8 (#399):
    GIVEN Payload source == "compact" und eine veraltete Kopie in ~
    WHEN der Banner laeuft
    THEN wird nichts aufgefrischt, ausgegeben wird nur die Versionszeile.
    """
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    _installed(tmp_path, home)
    target = home / ".claude" / "commands" / "40-tdd-red.md"
    old = f"{ALIAS_MARKER}\n{SKILL_INVOCABLE.replace('Neue', 'Alte')}".encode()
    target.write_bytes(old)
    result = _run(plugin, home, project, stdin=json.dumps({"source": "compact"}))
    assert _message(result) == "agent-os-openspec 9.9.9 aktiv"
    assert _context(result) == ""
    assert target.read_bytes() == old


def test_exception_in_wartung_bleibt_fail_open(tmp_path):
    """AC-10 (#399):
    GIVEN ein schreibgeschuetztes ~/.claude/commands mit veralteter markierter
          Kopie und einem markierten Alias eines entfernten Befehls
    WHEN der Banner laeuft
    THEN endet er mit Exit 0, ohne Traceback; stdout ist leer oder gueltiges JSON.
    """
    plugin = _plugin(tmp_path)
    home, project = _dirs(tmp_path)
    cmds = home / ".claude" / "commands"
    stale = cmds / "40-tdd-red.md"
    stale.write_text(f"{ALIAS_MARKER}\n{SKILL_INVOCABLE.replace('Neue', 'Alte')}")
    (cmds / "00-bug.md").write_text(f"{ALIAS_MARKER}\n# Bug\n")
    stale.chmod(0o444)
    cmds.chmod(0o500)
    try:
        result = _run(plugin, home, project)
    finally:
        cmds.chmod(0o755)
        stale.chmod(0o644)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stdout
    if result.stdout.strip():
        json.loads(result.stdout)


def test_hooks_json_banner_timeout_ist_10():
    """AC-11 (#399):
    GIVEN hooks/hooks.json
    WHEN der SessionStart-Eintrag fuer session_banner.py gelesen wird
    THEN ist sein timeout 10.
    """
    hooks = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text())
    entries = [h for entry in hooks["hooks"]["SessionStart"] for h in entry["hooks"]
               if h.get("command") == "${CLAUDE_PLUGIN_ROOT}/core/hooks/session_banner.py"]
    assert len(entries) == 1
    assert entries[0].get("timeout") == 10


# --- Versions-Marker (alias_sync) ---------------------------------------------

def test_alias_version_reads_last_marker_line():
    text = _marked("50-implement", SKILL_BLOCKED, "3.26.2")
    assert alias_version(text) == "3.26.2"
    assert alias_version(f"⚙ /x · agent-os-openspec 3.1.0\n{text}") == "3.26.2"
    assert alias_version(alias_content("50-implement", SKILL_BLOCKED)) is None
    assert alias_version("⚙ /x · agent-os-openspec unbekannt\n") is None


def test_version_comparison_is_numeric_not_lexicographic():
    """AC-5: Als String waere '3.9.0' > '3.25.0' — genau der Fehler."""
    newer = _marked("50-implement", SKILL_BLOCKED, "3.25.0")
    older = _marked("50-implement", SKILL_BLOCKED, "3.9.0")
    assert is_newer_than(newer, "3.9.0") is True
    assert is_newer_than(older, "3.25.0") is False
    assert is_newer_than(newer, "3.25.0") is False
    # Ohne lesbare Version kein Beweis — also nie unterdruecken.
    assert is_newer_than(alias_content("50-implement", SKILL_BLOCKED), "3.9.0") is False
    assert is_newer_than(newer, None) is False


def test_find_stale_aliases_keeps_signature_for_other_callers(tmp_path):
    """Ohne `loaded_version` bleibt die Semantik fuer setup.py unveraendert."""
    plugin = _plugin(tmp_path, "3.24.0")
    commands = tmp_path / "cmds"
    commands.mkdir()
    (commands / "50-implement.md").write_text(_marked("50-implement", SKILL_BLOCKED, "3.25.0"))
    assert find_stale_aliases(plugin / "skills", commands) == ["50-implement"]
    assert find_stale_aliases(plugin / "skills", commands, loaded_version="3.24.0") == []


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

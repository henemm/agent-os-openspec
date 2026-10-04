"""`setup.py --remove-aliases [--global]` und Schutz projekteigener Befehle
(Issue #251, Teil #244).

Bisher gab es keinen Weg, markierte Kurz-Befehle in einem Bereich wieder zu
entfernen, ohne Dateien von Hand zu loeschen. Soll laut Spec
`docs/specs/feat-251-kurzbefehle.md`:
- `--remove-aliases` loescht ausschliesslich markierte Dateien in
  `<scope>/.claude/commands/`, meldet `Removed: <name>.md` und `Kept: <name>.md`
  und schliesst mit `Command aliases: N removed, M kept.`
- Ohne markierte Dateien oder ohne Verzeichnis: No-op, `0 removed`, Exit 0.
- `--global` waehlt das Home-Verzeichnis statt des Projektordners.
- `migrate_to_plugin.py` loescht weiterhin keine projekteigenen Befehle, auch
  wenn Alias-Dateien das neue Marker-Format tragen.

Alle Aufrufe von setup.py laufen als echter Prozess mit Test-Home, damit
weder `~/.claude/commands/` des Rechners noch das Repo beruehrt wird.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import alias_sync  # noqa: E402
import migrate_to_plugin  # noqa: E402

SKILLS_DIR = REPO_ROOT / "skills"
SETUP_PY = REPO_ROOT / "setup.py"
MARKER = alias_sync.ALIAS_MARKER


def _new_format_redirect(name: str) -> str:
    """Weiterleitung im neuen Format (Marker direkt nach dem Frontmatter)."""
    return (
        "---\n"
        f"description: Kurz-Alias für /agent-os-openspec:{name}\n"
        "---\n"
        f"{MARKER}\n"
        "\n"
        f"/agent-os-openspec:{name} $ARGUMENTS\n"
    )


def _old_format_redirect(name: str) -> str:
    return f"{MARKER}\n" + _new_format_redirect(name).replace(f"{MARKER}\n", "", 1)


# Projekteigene Datei: Marker-Text steht mitten im Inhalt, nicht an einer der
# beiden erkannten Positionen.
CUSTOM_WITH_MARKER_TEXT = (
    "---\n"
    "description: Eigene Deploy-Prozedur des Projekts\n"
    "---\n"
    "# Deploy (Projekt X)\n"
    "\n"
    "Hinweis: generierte Aliase tragen die Zeile\n"
    f"{MARKER}\n"
    "— diese Datei ist KEIN Alias.\n"
)
CUSTOM_PLAIN = "# Radar\n\nprojekteigener Befehl\n"


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def _run_setup(home: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, HOME=str(home))
    return subprocess.run(
        [sys.executable, str(SETUP_PY), *args],
        capture_output=True, text=True, env=env, cwd=str(home),
    )


def _commands(base: Path) -> Path:
    d = base / ".claude" / "commands"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- AC-5 ---------------------------------------------------------------------

def test_unmarked_file_untouched_by_detection_refresh_and_remove(tmp_path, home):
    project = tmp_path / "project"
    commands = _commands(project)
    # Gleichnamig mit einem Skill, damit refresh die Datei ueberhaupt betrachtet.
    custom = commands / "70-deploy.md"
    custom.write_text(CUSTOM_WITH_MARKER_TEXT)
    plain = commands / "radar.md"
    plain.write_text(CUSTOM_PLAIN)
    before_custom = custom.read_bytes()
    before_plain = plain.read_bytes()

    assert alias_sync.is_alias_file(CUSTOM_WITH_MARKER_TEXT) is False
    assert alias_sync.is_alias_file(CUSTOM_PLAIN) is False

    refresh = _run_setup(home, str(project), "--refresh-aliases")
    assert refresh.returncode == 0, refresh.stdout + refresh.stderr
    assert custom.read_bytes() == before_custom
    assert plain.read_bytes() == before_plain

    remove = _run_setup(home, str(project), "--remove-aliases")
    assert remove.returncode == 0, remove.stdout + remove.stderr
    assert custom.exists() and custom.read_bytes() == before_custom
    assert plain.exists() and plain.read_bytes() == before_plain


# --- AC-6 ---------------------------------------------------------------------

def test_remove_deletes_marked_and_reports_removed_and_kept(tmp_path, home):
    project = tmp_path / "project"
    commands = _commands(project)
    new_marked = commands / "10-context.md"
    new_marked.write_text(_new_format_redirect("10-context"))
    old_marked = commands / "20-analyse.md"
    old_marked.write_text(_old_format_redirect("20-analyse"))
    full_copy = commands / "70-deploy.md"
    full_copy.write_text(
        f"{MARKER}\n" + (SKILLS_DIR / "70-deploy" / "SKILL.md").read_text()
    )
    custom = commands / "radar.md"
    custom.write_text(CUSTOM_PLAIN)

    result = _run_setup(home, str(project), "--remove-aliases")
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout

    assert not new_marked.exists()
    assert not old_marked.exists()
    assert not full_copy.exists()
    assert custom.exists() and custom.read_text() == CUSTOM_PLAIN

    for name in ("10-context.md", "20-analyse.md", "70-deploy.md"):
        assert f"Removed: {name}" in out, f"{name} nicht als geloescht gemeldet: {out!r}"
    assert "Kept: radar.md" in out, f"radar.md nicht als behalten gemeldet: {out!r}"
    assert "Command aliases: 3 removed, 1 kept." in out, out


# --- AC-7 ---------------------------------------------------------------------

def test_remove_without_marked_files_is_noop(tmp_path, home):
    # (a) Bereich ohne .claude/commands/
    bare = tmp_path / "bare"
    bare.mkdir()
    result = _run_setup(home, str(bare), "--remove-aliases")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 removed" in result.stdout, result.stdout
    assert not (bare / ".claude" / "commands").exists(), (
        "--remove-aliases darf nichts anlegen"
    )

    # (b) Bereich nur mit unmarkierten Dateien
    project = tmp_path / "project"
    commands = _commands(project)
    custom = commands / "radar.md"
    custom.write_text(CUSTOM_PLAIN)
    result = _run_setup(home, str(project), "--remove-aliases")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 removed" in result.stdout, result.stdout
    assert custom.exists() and custom.read_text() == CUSTOM_PLAIN
    assert sorted(p.name for p in commands.iterdir()) == ["radar.md"]


# --- AC-8 ---------------------------------------------------------------------

def test_remove_global_targets_home_commands_dir(tmp_path, home):
    home_commands = _commands(home)
    home_alias = home_commands / "50-implement.md"
    home_alias.write_text(_new_format_redirect("50-implement"))

    project = tmp_path / "project"
    project_commands = _commands(project)
    project_alias = project_commands / "50-implement.md"
    project_alias.write_text(_new_format_redirect("50-implement"))

    result = _run_setup(home, str(project), "--remove-aliases", "--global")
    assert result.returncode == 0, result.stdout + result.stderr

    assert not home_alias.exists(), "--global muss <home>/.claude/commands/ treffen"
    assert project_alias.exists(), "--global darf den Projektordner nicht anfassen"
    assert "Removed: 50-implement.md" in result.stdout, result.stdout


# --- AC-9 ---------------------------------------------------------------------

SKILL_BODY = "---\ndescription: Deploy\n---\n# Deploy\n\nGeneric template.\n"
CUSTOM_DEPLOY = "# Deploy (Projekt X)\n\nEigene Produktions-Prozedur.\n"


def test_migrate_to_plugin_keeps_project_commands_with_new_marker_files(
        tmp_path, monkeypatch, capsys):
    plugin = tmp_path / "plugin"
    for name, body in (("70-deploy", SKILL_BODY),
                       ("10-context", "---\ndescription: Kontext\n---\n# Kontext\n"),
                       ("20-analyse", "---\ndescription: Analyse\n---\n# Analyse\n")):
        (plugin / "skills" / name).mkdir(parents=True)
        (plugin / "skills" / name / "SKILL.md").write_text(body)
    monkeypatch.setattr(migrate_to_plugin, "PLUGIN_ROOT", plugin)

    project = tmp_path / "project"
    commands = _commands(project)
    (project / ".claude" / "settings.json").write_text(json.dumps({}))

    custom = commands / "70-deploy.md"
    custom.write_text(CUSTOM_DEPLOY)
    # Alias im neuen Format: Marker hinter dem Frontmatter, inhaltlich eine
    # Weiterleitung — muss weiter als Alias geschuetzt sein.
    new_alias = commands / "10-context.md"
    new_alias.write_text(_new_format_redirect("10-context"))
    # Vollkopie im neuen Format: ohne Marker waere sie inhaltsgleich zum Skill.
    new_full = commands / "20-analyse.md"
    skill_20 = (plugin / "skills" / "20-analyse" / "SKILL.md").read_text()
    s_lines = skill_20.split("\n")
    s_close = s_lines.index("---", 1)
    new_full.write_text(
        "\n".join(s_lines[:s_close + 1] + [MARKER] + s_lines[s_close + 1:])
    )
    before = {p.name: p.read_bytes() for p in commands.iterdir()}

    migrate_to_plugin.migrate(project, dry_run=False)
    capsys.readouterr()

    after = {p.name: p.read_bytes() for p in commands.iterdir()}
    assert after == before, (
        "Migration hat projekteigene Befehle oder markierte Aliase veraendert/geloescht"
    )

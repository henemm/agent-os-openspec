"""Kurzbefehl-Wartung bleibt in ihrem Schreibbereich und stoppt nicht an einer
einzelnen Datei (Issue #400, Folge der Gegenpruefung zu #399).

Soll laut Spec `docs/specs/fix-400-alias-robust.md`:
- Symlinks in `commands_dir` werden weder beschrieben noch geloescht, sondern
  mit Grund in `skipped` gemeldet.
- Ein `OSError` an einer Datei (z. B. 0444) bricht die Schleife nicht ab.
- `refresh_aliases(..., skipped=None)` bleibt abwaertskompatibel: Rueckgabe ist
  weiter `(erneuert, geloescht)`.
- Start-Hinweis und `setup.py --refresh-aliases` nennen Uebersprungenes.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "core" / "hooks"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(HOOKS_DIR))

import alias_sync  # noqa: E402
import session_banner  # noqa: E402

SETUP_PY = REPO_ROOT / "setup.py"
MARKER = alias_sync.ALIAS_MARKER

SKILL_TEXT = (
    "---\n"
    "description: Testbefehl\n"
    "disable-model-invocation: true\n"
    "---\n"
    "Neue Fassung\n"
)
OLD_COPY = f"{MARKER}\nAlte Fassung\n"

needs_non_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="als root hindert 0444 das Schreiben nicht",
)


def _skills(tmp_path: Path, *names: str) -> Path:
    skills = tmp_path / "skills"
    for name in names:
        (skills / name).mkdir(parents=True, exist_ok=True)
        (skills / name / "SKILL.md").write_text(SKILL_TEXT)
    return skills


def _commands(tmp_path: Path) -> Path:
    commands = tmp_path / "home" / ".claude" / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    return commands


def _external(tmp_path: Path, content: str = OLD_COPY) -> Path:
    target = tmp_path / "dotfiles" / "extern.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target


def test_symlink_wird_nicht_beschrieben(tmp_path):
    """AC-1: veralteter markierter Alias als Symlink — Ziel bleibt unveraendert."""
    skills = _skills(tmp_path, "10-alpha")
    commands = _commands(tmp_path)
    target = _external(tmp_path)
    link = commands / "10-alpha.md"
    link.symlink_to(target)

    skipped: list = []
    refreshed, removed = alias_sync.refresh_aliases(skills, commands, None, skipped=skipped)

    assert target.read_text() == OLD_COPY
    assert link.is_symlink()
    assert refreshed == []
    assert any(e.startswith("10-alpha") and "Symlink" in e for e in skipped), skipped


def test_symlink_als_entfernter_alias_wird_nicht_geloescht(tmp_path):
    """AC-2: markierter Alias eines entfernten Befehls als Symlink bleibt stehen."""
    skills = _skills(tmp_path, "10-alpha")
    commands = _commands(tmp_path)
    target = _external(tmp_path)
    link = commands / "00-bug.md"
    link.symlink_to(target)

    skipped: list = []
    _, removed = alias_sync.refresh_aliases(skills, commands, None, skipped=skipped)

    assert link.is_symlink()
    assert target.read_text() == OLD_COPY
    assert removed == []
    assert any(e.startswith("00-bug") for e in skipped), skipped
    assert "00-bug: Symlink" in skipped, skipped


@needs_non_root
def test_schreibgeschuetzte_datei_bricht_schleife_nicht_ab(tmp_path):
    """AC-3: 0444-Datei wird uebersprungen, die uebrigen Dateien werden bedient."""
    skills = _skills(tmp_path, "10-alpha", "20-beta")
    commands = _commands(tmp_path)
    locked = commands / "10-alpha.md"
    locked.write_text(OLD_COPY)
    locked.chmod(0o444)
    other = commands / "20-beta.md"
    other.write_text(OLD_COPY)
    removed_alias = commands / "00-bug.md"
    removed_alias.write_text(OLD_COPY)

    skipped: list = []
    try:
        refreshed, removed = alias_sync.refresh_aliases(skills, commands, None, skipped=skipped)
    finally:
        locked.chmod(0o644)

    assert refreshed == ["20-beta"]
    assert other.read_text() == alias_sync.alias_content("20-beta", SKILL_TEXT)
    assert removed == ["00-bug.md"]
    assert not removed_alias.exists()
    assert locked.read_text() == OLD_COPY
    assert any(e.startswith("10-alpha") for e in skipped), skipped
    assert "10-alpha: schreibgeschützt" in skipped, skipped


def test_unlesbarer_skill_text_wird_uebersprungen_statt_abzubrechen(tmp_path, monkeypatch):
    """F003: nicht dekodierbare SKILL.md (Race nach find_stale_aliases) bricht nicht ab."""
    skills = tmp_path / "skills"
    (skills / "10-alpha").mkdir(parents=True)
    (skills / "10-alpha" / "SKILL.md").write_bytes(b"\xff\xfe")
    commands = _commands(tmp_path)
    (commands / "10-alpha.md").write_text(OLD_COPY)
    monkeypatch.setattr(alias_sync, "find_stale_aliases", lambda *a, **k: ["10-alpha"])

    skipped: list = []
    refreshed, _ = alias_sync.refresh_aliases(skills, commands, None, skipped=skipped)

    assert refreshed == []
    assert "10-alpha: Skill nicht lesbar" in skipped, skipped


def test_rueckgabe_tupel_und_optionaler_skipped_parameter(tmp_path):
    """AC-4: ohne `skipped` weiter Zweier-Tupel; mit Liste wird sie gefuellt."""
    skills = _skills(tmp_path, "10-alpha")
    commands = _commands(tmp_path)
    (commands / "10-alpha.md").write_text(OLD_COPY)

    result = alias_sync.refresh_aliases(skills, commands, None)
    assert result == (["10-alpha"], [])
    assert (commands / "10-alpha.md").read_text() == alias_sync.alias_content("10-alpha", SKILL_TEXT)

    link = commands / "10-alpha.md"
    link.unlink()
    link.symlink_to(_external(tmp_path))
    skipped: list = []
    alias_sync.refresh_aliases(skills, commands, None, skipped=skipped)
    assert len(skipped) == 1


def _plugin_root(tmp_path: Path, *names: str) -> Path:
    root = tmp_path / "plugin"
    root.mkdir(exist_ok=True)
    (root / ".claude-plugin").mkdir(exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"version": "9.9.9"}')
    (root / "skills").mkdir(exist_ok=True)
    for name in names:
        (root / "skills" / name).mkdir(exist_ok=True)
        (root / "skills" / name / "SKILL.md").write_text(SKILL_TEXT)
    return root


def test_start_hinweis_zaehlt_erfolge_und_nennt_uebersprungene(tmp_path, monkeypatch):
    """AC-5: Zaehlung nur Erfolge, Uebersprungene als Zusatz; nur-Uebersprungene eigene Zeile."""
    root = _plugin_root(tmp_path, "10-alpha", "20-beta")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    commands = _commands(tmp_path)
    (commands / "20-beta.md").write_text(OLD_COPY)
    (commands / "10-alpha.md").symlink_to(_external(tmp_path))

    lines = session_banner.refresh_home_aliases(root)

    assert lines == ["Kurzbefehle aktualisiert (1) · 1 übersprungen"]
    assert (commands / "20-beta.md").read_text() == alias_sync.alias_content("20-beta", SKILL_TEXT)

    # Zweiter Lauf: nichts mehr zu erneuern, nur noch der Symlink.
    assert session_banner.refresh_home_aliases(root) == ["Kurzbefehle: 1 übersprungen"]


def test_refresh_aliases_cli_meldet_uebersprungene(tmp_path):
    """AC-6: `setup.py --refresh-aliases` als echter Prozess nennt Skipped-Eintraege."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    commands = project / ".claude" / "commands"
    commands.mkdir(parents=True)
    home.mkdir(exist_ok=True)
    (commands / "40-tdd-red.md").write_text(OLD_COPY)
    (commands / "50-implement.md").symlink_to(_external(tmp_path))
    env = dict(os.environ, HOME=str(home))

    def run():
        return subprocess.run(
            [sys.executable, str(SETUP_PY), str(project), "--refresh-aliases"],
            capture_output=True, text=True, env=env, cwd=str(home),
        )

    first = run()
    assert first.returncode == 0, first.stdout + first.stderr
    assert "  Refreshed: 40-tdd-red.md" in first.stdout
    assert "  Skipped: 50-implement" in first.stdout
    assert "1 skipped" in first.stdout.strip().splitlines()[-1]

    (commands / "50-implement.md").unlink()
    second = run()
    assert second.returncode == 0, second.stdout + second.stderr
    last = second.stdout.strip().splitlines()[-1]
    assert last.startswith("Command aliases:") and last.endswith("none created.")
    assert "skipped" not in last

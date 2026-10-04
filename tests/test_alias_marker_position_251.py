"""Alias-Marker hinter das Frontmatter (Issue #251, Teil #238).

Der Marker `<!-- openspec-alias: ... -->` stand bisher in Zeile 1 jeder
generierten Kurz-Befehl-Datei — VOR dem Frontmatter. Damit beginnt die Datei
nicht mit `---`, das Frontmatter wird nicht geparst, und die Befehlsauswahl
zeigt den Marker statt der Beschreibung (reproduziert am 2026-10-03 mit
Claude Code 2.1.285).

Soll laut Spec `docs/specs/feat-251-kurzbefehle.md`:
- `alias_content` setzt den Marker als erste Zeile DIREKT NACH dem schliessenden
  `---` des Frontmatters (Weiterleitung und Vollkopie).
- `is_alias_file` erkennt alte (Zeile 1) und neue Position.
- Altformat-Dateien gelten als veraltet und werden per `--refresh-aliases`
  angehoben.
- Die 15 versionierten Kopien in `.claude/commands/` tragen die neue Position.
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core" / "hooks"))

import alias_sync  # noqa: E402

SKILLS_DIR = REPO_ROOT / "skills"
COMMANDS_DIR = REPO_ROOT / ".claude" / "commands"
SETUP_PY = REPO_ROOT / "setup.py"

# Vollkopie: ein echter Skill mit `disable-model-invocation: true`.
# (50-implement ist seit #147 entsperrt und damit eine Weiterleitung.)
FULL_COPY_SKILL = "70-deploy"
REDIRECT_SKILL = "50-implement"


def _split_frontmatter(text: str):
    """(Frontmatter-Dict, erste Zeile nach dem schliessenden `---`, Rest ab dort).

    Scheitert der Test hier, beginnt die Datei nicht mit einem geschlossenen
    Frontmatter — genau der Mangel aus #238.
    """
    lines = text.split("\n")
    assert lines[0] == "---", (
        f"Datei beginnt nicht mit '---', sondern mit {lines[0]!r} — "
        "das Frontmatter ist so nicht parsbar (#238)"
    )
    try:
        close = lines.index("---", 1)
    except ValueError:
        raise AssertionError("Frontmatter wird nicht mit '---' geschlossen")
    meta = yaml.safe_load("\n".join(lines[1:close]))
    assert isinstance(meta, dict), f"Frontmatter ist kein Mapping: {meta!r}"
    first_after = lines[close + 1] if close + 1 < len(lines) else ""
    return meta, first_after


def _old_format(name: str, skill_text: str) -> str:
    """Inhalt, den alias_content VOR #251 erzeugte (Marker in Zeile 1)."""
    if alias_sync.embeds_full_skill(skill_text):
        return f"{alias_sync.ALIAS_MARKER}\n{skill_text}"
    return (
        f"{alias_sync.ALIAS_MARKER}\n"
        "---\n"
        f"description: Kurz-Alias für /agent-os-openspec:{name}\n"
        "---\n"
        "\n"
        f"/agent-os-openspec:{name} $ARGUMENTS\n"
    )


# --- AC-1 ---------------------------------------------------------------------

def test_redirect_frontmatter_parses_and_marker_follows_it():
    skill_text = (SKILLS_DIR / REDIRECT_SKILL / "SKILL.md").read_text()
    assert not alias_sync.embeds_full_skill(skill_text), (
        "Testvoraussetzung: der Skill muss eine Weiterleitung erzeugen"
    )
    content = alias_sync.alias_content(REDIRECT_SKILL, skill_text)

    meta, first_after = _split_frontmatter(content)

    assert meta.get("description") == f"Kurz-Alias für /agent-os-openspec:{REDIRECT_SKILL}"
    assert first_after == alias_sync.ALIAS_MARKER, (
        f"Erste Zeile nach dem Frontmatter ist {first_after!r}, erwartet der Marker"
    )
    assert f"/agent-os-openspec:{REDIRECT_SKILL} $ARGUMENTS" in content
    assert alias_sync.is_alias_file(content)


# --- AC-2 ---------------------------------------------------------------------

def test_full_copy_frontmatter_parses_and_marker_follows_it():
    skill_text = (SKILLS_DIR / FULL_COPY_SKILL / "SKILL.md").read_text()
    assert alias_sync.embeds_full_skill(skill_text), (
        "Testvoraussetzung: der Skill muss eine Vollkopie erzeugen"
    )
    skill_meta, _ = _split_frontmatter(skill_text)

    content = alias_sync.alias_content(FULL_COPY_SKILL, skill_text)
    meta, first_after = _split_frontmatter(content)

    assert meta.get("description") == skill_meta["description"], (
        "description der Vollkopie muss die echte Beschreibung aus SKILL.md sein"
    )
    assert first_after == alias_sync.ALIAS_MARKER, (
        f"Erste Zeile nach dem Frontmatter ist {first_after!r}, erwartet der Marker"
    )
    # Rest byte-gleich: ohne die eine Marker-Zeile ergibt sich exakt SKILL.md.
    assert content.replace(alias_sync.ALIAS_MARKER + "\n", "", 1) == skill_text, (
        "Ausser der eingefuegten Marker-Zeile muss der Skill-Inhalt unveraendert sein"
    )
    assert alias_sync.is_alias_file(content)


# --- AC-3 ---------------------------------------------------------------------

def test_old_marker_in_line_one_still_recognized_and_stale(tmp_path):
    commands = tmp_path / ".claude" / "commands"
    commands.mkdir(parents=True)
    for name in (REDIRECT_SKILL, FULL_COPY_SKILL):
        skill_text = (SKILLS_DIR / name / "SKILL.md").read_text()
        old = _old_format(name, skill_text)
        (commands / f"{name}.md").write_text(old)
        assert alias_sync.is_alias_file(old), f"Altformat {name} gilt nicht als generiert"

    stale = alias_sync.find_stale_aliases(SKILLS_DIR, commands)

    assert sorted(stale) == sorted([REDIRECT_SKILL, FULL_COPY_SKILL]), (
        f"Altformat-Dateien muessen als veraltet gemeldet werden, gemeldet: {stale}"
    )


# --- AC-4 ---------------------------------------------------------------------

def test_refresh_lifts_old_format_to_new_position(tmp_path):
    project = tmp_path / "project"
    commands = project / ".claude" / "commands"
    commands.mkdir(parents=True)
    names = (REDIRECT_SKILL, FULL_COPY_SKILL)
    for name in names:
        skill_text = (SKILLS_DIR / name / "SKILL.md").read_text()
        (commands / f"{name}.md").write_text(_old_format(name, skill_text))

    env = dict(os.environ, HOME=str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    result = subprocess.run(
        [sys.executable, str(SETUP_PY), str(project), "--refresh-aliases"],
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    for name in names:
        skill_text = (SKILLS_DIR / name / "SKILL.md").read_text()
        text = (commands / f"{name}.md").read_text()
        assert text == alias_sync.alias_content(name, skill_text)
        _, first_after = _split_frontmatter(text)
        assert first_after == alias_sync.ALIAS_MARKER, (
            f"{name}.md wurde nicht auf die neue Marker-Position angehoben"
        )
    assert alias_sync.find_stale_aliases(SKILLS_DIR, commands) == []


# --- AC-10 --------------------------------------------------------------------

def test_repo_copies_carry_marker_in_new_position():
    copies = sorted(COMMANDS_DIR.glob("*.md"))
    assert len(copies) == 15, f"Erwartet 15 versionierte Kopien, gefunden {len(copies)}"

    assert alias_sync.find_stale_aliases(SKILLS_DIR, COMMANDS_DIR) == []

    wrong = []
    for path in copies:
        text = path.read_text()
        try:
            _, first_after = _split_frontmatter(text)
        except AssertionError:
            wrong.append(path.name)
            continue
        if first_after != alias_sync.ALIAS_MARKER:
            wrong.append(path.name)
    assert wrong == [], f"Marker nicht in neuer Position: {wrong}"
